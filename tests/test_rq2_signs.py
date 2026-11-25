"""Check saved-parameter RQ2 sign counts (analysis plan section 10).

    PFE_DATASET=v4 python -m tests.test_rq2_signs

Known gains check rates, strict majorities, zero, medians and no-rule slots.
The frozen hard runs must respect the constrained signs in every start and
fold. A failure is a finding to investigate, rather than a reason to filter.
"""
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis import rq2_signs as R


def synthetic_params():
    """Two wells × four starts; only well A has a constrained river edge."""
    return pd.DataFrame({
        "code_bss": ["A"] * 4 + ["B"] * 4,
        "seed": [0, 1, 2, 3] * 2,
        "gain_recharge": [-1, -3, -5, 0, 2, 2, 2, 2],
        "gain_pumping": [2, 4, 0, -2, 0, -1, -1, -1],
        "gain_pumping_unattributed": [0, 0, 0, 0, 1, 3, 5, -1],
        "gain_river": [-2, 0, 4, 4, -100, -100, -100, -100],
        "gain_canal": [-100] * 8,
        "river_constrained": [True] * 4 + [False] * 4,
    })


def test_exact_shares():
    summary = R.summarise(synthetic_params())
    expected = {"recharge": (3, 3 / 8, 1 / 2, 3),
                "pumping": (2, 1 / 4, 0, 3),
                "pumping_unattributed": (3, 3 / 8, 1 / 2, 3),
                "river_c": (1, 1 / 4, 0, 2)}
    for slot, (count, rate, majority, median) in expected.items():
        row = summary.loc[slot]
        assert row["n_wrong"] == count, (slot, row)
        assert row["share_wrong"] == rate, (slot, row)
        assert row["share_majority_wrong"] == majority, (slot, row)
        assert row["median_abs_wrong"] == median, (slot, row)
    assert summary.loc["river_c", "n_gains"] == 4
    assert summary.loc["river_c", "n_wells"] == 1
    zeros = synthetic_params()
    zeros[[c for c in zeros.columns if c.startswith("gain_")]] = 0
    summary = R.summarise(zeros)
    assert summary["n_wrong"].sum() == 0
    assert summary.loc["recharge", "share_majority_wrong"] == 0
    assert np.isnan(summary.loc["recharge", "median_abs_wrong"])
    assert R.cell(summary.loc["recharge"]) == "0.0% / 0.0% / —"
    print("  1. exact shares, strict majority, ties, zeros and wrong-gain medians pass")


def test_no_rule():
    summary = R.summarise(synthetic_params())
    for slot in ("river", "canal"):
        assert summary.loc[slot, "n_wrong"] == 0
        assert np.isnan(summary.loc[slot, "share_wrong"])
        assert np.isnan(summary.loc[slot, "share_majority_wrong"])
        assert np.isnan(summary.loc[slot, "median_abs_wrong"])
        assert R.cell(summary.loc[slot]) == "no rule"
    no_river = synthetic_params().assign(river_constrained=False)
    summary = R.summarise(no_river)
    assert summary.loc["river_c", "n_gains"] == 0
    assert R.cell(summary.loc["river_c"]) == "no eligible wells"
    print("  2. negative plain-river and canal gains are never violations; empty rule support is explicit")


def test_lwo_selection():
    """Different fold values expose double counting or selecting training wells."""
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp) / "p4_B4_D_none_r1_lwo"
        for fold in (0, 1):
            folder = run / f"fold_{fold}"
            folder.mkdir(parents=True)
            cfg = {"seeds": [0, 1, 2, 3], "dataset": "v4", "arm": "D", "policy": "main",
                   "export_release": "saved", "fold": fold, "signs": "none", "sign_ref": "gate3",
                   "river_constrained_wells": ["A"]}
            (folder / "config.json").write_text(json.dumps(cfg))
            frame = synthetic_params()
            for seed in range(4):
                params = frame.loc[frame["seed"].eq(seed)].copy()
                params["gain_recharge"] = [-1, 1] if fold == 0 else [1, -1]
                params.to_csv(folder / f"params_seed_{seed}.csv", index=False)
        lwo = {"n_folds": 2, "fold_of_well": {"A": 0, "B": 1}}
        params, files, starts = R.load_run(run, "none", {"A", "B"}, {"A"}, lwo, "saved", False)
        assert (files, starts, len(params)) == (8, 4, 8)
        assert R.summarise(params).loc["recharge", "share_wrong"] == 1
        path = run / "fold_0" / "params_seed_0.csv"
        frame = pd.read_csv(path)
        frame["river_constrained"] = False
        frame.to_csv(path, index=False)
        try:
            R.saved_params(path, {"A"}, False)
        except ValueError as error:
            assert "frozen export" in str(error)
        else:
            raise AssertionError("A changed river mask must fail")
    print("  3. every fold is read; each well uses only its held-out fold; changed river masks fail")


def test_hard_runs():
    core, river_wells, lwo, release = R.frozen_inputs(False)
    assert len(core) == 33, len(core)
    files, gains = 0, 0
    for suffix in ("", "_lwo"):
        for reconstruction in (1, 2, 3):
            run = R.RESULTS / f"p4_B4_D_hard_r{reconstruction}{suffix}"
            assert run.is_dir(), f"Missing hard run: {run}"
            selected, n_files, starts = R.load_run(run, "hard", core, river_wells, lwo, release, False)
            assert len(selected) == len(core) * starts
            summary = R.summarise(selected)
            assert summary["n_wrong"].sum() == 0, (run, summary)
            # Also check core wells in training folds, though the R2 report uses
            # held-out folds only. A hard sign should hold in every saved model.
            paths = sorted(run.glob("fold_*/params_seed_*.csv") if suffix
                           else run.glob("params_seed_*.csv"))
            assert len(paths) == n_files
            for path in paths:
                params = R.saved_params(path, river_wells, False)
                params = params.loc[params["code_bss"].isin(core)]
                summary = R.summarise(params)
                assert summary["n_wrong"].sum() == 0, (path, summary)
                gains += int(summary.loc[summary["sign"].ne(0), "n_gains"].sum())
            files += n_files
    print(f"  4. hard: {files} saved files, {gains} constrained core gains, zero violations "
          "including training folds")


if __name__ == "__main__":
    started = time.perf_counter()
    test_exact_shares()
    test_no_rule()
    test_lwo_selection()
    test_hard_runs()
    print(f"test_rq2_signs: all checks passed ({time.perf_counter() - started:.2f}s)")
