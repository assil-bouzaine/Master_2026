"""Check the post-hoc LWO offset diagnostic (docs/v5_plan.md section 1, C2).

    PFE_DATASET=v4 python -m tests.test_lwo_centring

Synthetic means and temporal shapes are checked first. Real ensembles must
equal the frozen predictions. A complete real-run diagnostic writes to a
temporary directory, with hashes proving that all its frozen files stay intact.
"""
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from src.analysis import lwo_centring as C
from src.models import evaluate


def test_synthetic():
    weeks = pd.date_range("2019-12-08", periods=5, freq="W-SUN")
    panel = pd.DataFrame({"code_bss": np.repeat(["A", "B"], 5), "week": list(weeks) * 2,
                          "split": ["train"] * 4 + ["validation"] + ["train"] * 4 + ["validation"],
                          "head": [8., 10., np.nan, 12., 500., 18., np.nan, 20., 22., -500.],
                          "mu": [10.] * 5 + [20.] * 5, "core": True})
    # A has a known +7 m offset on W. Values outside W must not affect its correction.
    pred = panel[C.KEYS].assign(pred=[15., 17., 100., 19., 200., 18., -100., 20., 22., -200.],
                                pred_seed_sd=0.5, task="simulation", horizon=0)
    centred, offsets = C.centre_predictions(pred, panel)
    assert offsets.set_index("code_bss")["offset_m"].to_dict() == {"A": 7., "B": 0.}
    window = panel.loc[panel["split"].eq("train") & panel["head"].notna(), C.KEYS]
    means = window.merge(centred, on=C.KEYS).groupby("code_bss")["pred"].mean()
    np.testing.assert_array_equal(means.to_numpy(), [10., 20.])
    for code in ["A", "B"]:
        before = pred.loc[pred["code_bss"].eq(code), "pred"].to_numpy()
        after = centred.loc[centred["code_bss"].eq(code), "pred"].to_numpy()
        np.testing.assert_array_equal(before - before.mean(), after - after.mean())
    pd.testing.assert_frame_equal(pred.drop(columns="pred"), centred.drop(columns="pred"))
    try:
        C.centre_predictions(pred.drop(index=0), panel)
    except ValueError as error:
        assert "exact W" in str(error)
    else:
        raise AssertionError("Missing observed training predictions must be rejected")
    print("  1. synthetic: exact training means, known offset, unchanged shape and seed spread")


def file_hashes(folder):
    out = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(1 << 20):
                    digest.update(block)
            out[str(path.relative_to(folder))] = digest.hexdigest()
    return out


def test_real():
    panel = C.frozen_panel()
    splits = json.loads((evaluate.DS / "splits.json").read_text())
    run = evaluate.RESULTS / "p4_B2_D_r1_lwo"
    before = file_hashes(run)
    for name in (run.name, "lstm_tuned_lwo", "lgbm_noclim_tuned_lwo", "taccari_tuned_lwo"):
        actual, seeds = C.rebuild_predictions(evaluate.RESULTS / name, panel, splits)
        checks = C.assert_frozen_predictions(actual, evaluate.RESULTS / name)
        frozen = pd.read_parquet(evaluate.RESULTS / name / "predictions.parquet")
        if name != "lgbm_noclim_tuned_lwo":
            keys = evaluate.PREDICTION_KEYS
            pd.testing.assert_frame_equal(actual.sort_values(keys).reset_index(drop=True),
                                          frozen.sort_values(keys).reset_index(drop=True), check_exact=True)
        print(f"  2. {name}: {len(actual)} rows match frozen predictions ({len(seeds)} seeds); {checks}")
    with TemporaryDirectory() as folder:
        output = Path(folder)
        row = C.diagnostic_run(run, panel, splits, output)
        target = output / run.name
        centred = pd.read_parquet(target / "predictions.parquet")
        recomputed = evaluate.score(centred)
        saved = pd.read_csv(target / "metrics_per_well.csv")
        pd.testing.assert_frame_equal(saved, recomputed.where(recomputed.notna(), np.nan),
                                      check_exact=False, rtol=1e-12, atol=1e-12)
        window = panel.loc[panel["split"].eq("train") & panel["head"].notna(), C.KEYS + ["mu"]]
        means = window.merge(centred, on=C.KEYS).groupby("code_bss").agg(pred=("pred", "mean"), mu=("mu", "first"))
        np.testing.assert_allclose(means["pred"], means["mu"], rtol=0, atol=1e-12)
        assert len(list(target.iterdir())) == 4
        print(f"  3. real diagnostic: validation NSE {row['validation_NSE_before']:.6f} -> "
              f"{row['validation_NSE_after']:.6f}; drought RMSE {row['drought_RMSE_before_m']:.6f} -> "
              f"{row['drought_RMSE_after_m']:.6f} m")
    assert file_hashes(run) == before
    print(f"  4. all {len(before)} frozen files retain their SHA-256 hashes")


if __name__ == "__main__":
    started = time.perf_counter()
    test_synthetic()
    test_real()
    print(f"test_lwo_centring: all checks passed ({time.perf_counter() - started:.1f}s)")
