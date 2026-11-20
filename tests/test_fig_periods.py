"""Check the periods figure against the observed heads and the split rule.

    PFE_DATASET=v4 python -m tests.test_fig_periods
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import pandas as pd

from paper.tools.fig_periods import draw_periods
from src.config import PROCESSED, TEST_PERIODS


def observed_months():
    """Take one row per core well and month, then aggregate across wells."""
    source = PROCESSED / "dataset_v4"
    heads = pd.read_parquet(source / "heads_weekly.parquet")
    wells = pd.read_parquet(source / "wells.parquet")
    splits = json.loads((source / "splits.json").read_text(encoding="utf-8"))
    core = wells.loc[wells["core"], "code_bss"]
    assert len(core) == 33

    heads["month"] = pd.PeriodIndex(heads["week"], freq="M")
    unique_sgi = heads.drop_duplicates(["month", "code_bss", "sgi"])
    assert not unique_sgi.duplicated(["month", "code_bss"]).any()
    monthly_core = unique_sgi.loc[unique_sgi["code_bss"].isin(core)].groupby("month")["sgi"]
    months = pd.period_range(splits["model_start"], heads["month"].max(), freq="M", name="month")
    median = monthly_core.median().reindex(months)
    counts = monthly_core.count().reindex(months, fill_value=0).rename("core_wells")

    start, end = (pd.Period(day, freq="M") for day in splits["test"])
    test = median.loc[start:end]
    trough = min(test.dropna().index, key=test.get)
    recovery = next(month for month in test.index if trough < month <= end - 2
                    and all(test.loc[month + offset] >= -0.5 for offset in range(3)))
    return median, trough, recovery, counts


def test_periods():
    expected_median, expected_trough, expected_recovery, expected_counts = observed_months()
    assert expected_recovery == pd.Period(TEST_PERIODS["test_recovery"][0], freq="M")

    with TemporaryDirectory() as directory:
        out = Path(directory)
        median, trough, recovery, counts = draw_periods(out / "first")
        draw_periods(out / "second")
        pd.testing.assert_series_equal(median, expected_median, check_exact=True)
        pd.testing.assert_series_equal(counts, expected_counts, check_exact=True)
        assert (trough, recovery) == (expected_trough, expected_recovery)
        for name in ("periods.pdf", "periods.png"):
            original = out / "first" / name
            repeat = out / "second" / name
            assert original.is_file() and repeat.is_file()
            assert original.stat().st_size > 0
            assert original.read_bytes() == repeat.read_bytes(), name
    print(f"All {len(median)} medians and counts agree. Trough {trough}, recovery {recovery}.")
    print("The PDF and PNG rebuild byte for byte.")


if __name__ == "__main__":
    start = perf_counter()
    test_periods()
    print(f"test_fig_periods: all checks passed ({perf_counter() - start:.2f}s)")
