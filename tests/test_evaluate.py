"""Check scoring robustness and complete naive runs (analysis plan §4).

The first score must already have its forecast benchmark. Run the baselines
in a temporary results folder so these checks cannot replace stored runs.
Duplicate keys must fail before joining, and short support must return a
usable empty table. Small fixtures use a core well's real drought weeks.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_evaluate
"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import pandas as pd

from src.config import ROOT
from src.models import evaluate as E, naive as N

SCRATCH = ROOT / "results" / "_agents" / "tmp"
EXPECTED_COLUMNS = ["code_bss", "task", "horizon", "split", "variant", "n_weeks", "support",
                    "NSE", "KGE", "RMSE", "bias", "r", "alpha", "beta_n", "skill",
                    "group", "core", "libelle_pe"]


def test_naive_run_order():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as tmp, \
            patch.object(E, "RESULTS", Path(tmp)), patch.object(N, "RESULTS", Path(tmp)):
        runs = ("naive_climatology", "naive_persistence", "naive_anomaly_persist")
        with redirect_stdout(StringIO()):
            N.main()
        first = {run: pd.read_csv(Path(tmp) / run / "metrics_per_well.csv") for run in runs}
        for run in runs:
            E.evaluate_run(run)
            again = pd.read_csv(Path(tmp) / run / "metrics_per_well.csv")
            pd.testing.assert_frame_equal(first[run], again, check_exact=True)
        keys = ["code_bss", "task", "horizon", "split", "variant"]
        persistence = first["naive_persistence"]
        benchmark = first["naive_anomaly_persist"]
        paired = persistence.merge(benchmark[keys + ["support"]], on=keys,
                                   suffixes=("", "_benchmark"), validate="one_to_one")
        same_weeks = (paired["task"] == "forecast") & (paired["support"] == paired["support_benchmark"])
        assert same_weeks.any(), "no persistence forecast row has the benchmark's scored weeks"
        assert paired.loc[same_weeks, "skill"].notna().all(), \
            "persistence forecasts with benchmark coverage have missing skill"
        counts = ", ".join(f"{run}: {len(first[run])}" for run in runs)
        print(f"  1. First-run metrics equal rescored metrics exactly ({counts}); "
              f"{same_weeks.sum()} persistence rows with the benchmark's weeks have skill.")


def drought_predictions():
    """Use 30 fully validated, unmasked drought weeks from the first eligible core well."""
    heads = pd.read_parquet(E.DS / "heads_weekly.parquet")
    wells = pd.read_parquet(E.DS / "wells.parquet")
    start, end = E.TEST_PERIODS["test_drought"]
    eligible = heads[heads["code_bss"].isin(wells.loc[wells["core"], "code_bss"])
                     & heads["week"].between(start, end) & heads["head"].notna()
                     & heads["share_not_validated"].eq(0)]
    mask = E.load_mask()
    if mask is not None:
        flagged = pd.MultiIndex.from_frame(eligible[["code_bss", "week"]]).isin(
            pd.MultiIndex.from_frame(mask[["code_bss", "week"]]))
        eligible = eligible[~flagged]
    counts = eligible.groupby("code_bss")["week"].nunique()
    codes = sorted(counts[counts >= 30].index)
    assert codes, "no core well has 30 fully validated drought weeks"
    sample = eligible[eligible["code_bss"] == codes[0]].sort_values("week").head(30)
    pred = sample[["code_bss", "week"]].assign(pred=sample["head"] + 0.25,
                                               task="simulation", horizon=0)
    return heads, pred.reset_index(drop=True)


def expect_duplicates(pred, name, repeated):
    try:
        E.score(pred)
    except ValueError as error:
        message = str(error)
        assert f"{name}: {len(repeated)} duplicated keys" in message, message
        assert "first five:" in message, message
        for _, row in repeated.head(5).iterrows():
            assert row["code_bss"] in message and row["week"].date().isoformat() in message, message
        if len(repeated) > 5:
            assert repeated.iloc[5]["week"].date().isoformat() not in message, message
    else:
        raise AssertionError(f"duplicate keys in {name} were accepted")


def test_duplicate_keys(heads, pred):
    short = pred.head(13)
    expect_duplicates(pd.concat([short, short], ignore_index=True), "predictions", short)
    duplicate_heads = heads.merge(short[["code_bss", "week"]], on=["code_bss", "week"])
    bad_heads = pd.concat([heads, duplicate_heads], ignore_index=True)
    read_parquet = pd.read_parquet

    def read_table(path, *args, **kwargs):
        if Path(path) == E.DS / "heads_weekly.parquet":
            return bad_heads
        return read_parquet(path, *args, **kwargs)

    with patch.object(E.pd, "read_parquet", side_effect=read_table):
        expect_duplicates(pred, "heads", short)
    benchmark = pd.concat([short, short], ignore_index=True).rename(columns={"pred": "bench"})
    with patch.object(E, "benchmark_predictions", return_value=benchmark):
        expect_duplicates(pred, "benchmark", short)
    print("  2. Duplicate keys in predictions, heads and benchmark raise clear errors with 13 keys and five examples.")


def test_week_coverage(pred):
    short = E.score(pred.head(13))
    assert short.empty and short.columns.tolist() == EXPECTED_COLUMNS, short
    assert E.summarise(short).empty, "an empty score table must remain usable by callers"
    full = E.score(pred)
    assert full.columns.tolist() == EXPECTED_COLUMNS
    drought = full[(full["split"] == "test_drought") & (full["variant"] == "all")]
    assert len(drought) == 1 and drought.iloc[0]["n_weeks"] == 30, drought
    assert full["n_weeks"].eq(30).all(), full[["split", "variant", "n_weeks"]]
    print(f"  3. {pred.iloc[0]['code_bss']}: 13 distinct drought weeks return an empty 18-column table; "
          "30 weeks are scored with n_weeks = 30.")


def main():
    started = time.perf_counter()
    test_naive_run_order()
    heads, pred = drought_predictions()
    test_duplicate_keys(heads, pred)
    test_week_coverage(pred)
    print(f"test_evaluate: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
