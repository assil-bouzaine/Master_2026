"""Decode response seeds with their encoding scale (analysis plan §14 item 18).

Read the saved free-response run without fitting or changing its files. Its
decoded heads must equal the mean, intercept and saved contributions, even
for a well whose training standard deviation is nearly zero.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_response_decode
"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.analysis import ladder_report as L
from src.config import ROOT
from src.models import evaluate as E, response as R

SCRATCH = ROOT / "results" / "_agents" / "tmp"
CONSTANT_WELL = "10984X0003/AIGUAN"
KEYS = ["code_bss", "week"]


def fixtures():
    panel = pd.read_parquet(E.RESULTS / "_cache" / "panel.parquet")
    run = E.RESULTS / "resp_free"
    seed = pd.read_parquet(run / "seed_0.parquet")
    contrib = pd.read_parquet(run / "contrib_seed_0.parquet")
    params = pd.read_csv(run / "params_seed_0.csv")
    return panel, seed, contrib, params


def test_saved_decomposition(panel, seed, contrib, params):
    decoded = L.seed_frames("resp_free")[0]
    scale = panel[KEYS + ["mu", "sd"]]
    raw = seed.merge(scale, on=KEYS, validate="one_to_one")
    raw["old_pred"] = raw["mu"] + raw["sd"] * raw["z"]
    names = [column for column in contrib if column not in KEYS]
    truth = contrib.merge(params[["code_bss", "d_m"]], on="code_bss", validate="many_to_one")
    truth = truth.merge(scale[KEYS + ["mu"]], on=KEYS, validate="one_to_one")
    truth["expected"] = truth["mu"] + truth["d_m"] + truth[names].astype(float).sum(axis=1)
    joined = decoded.merge(raw[KEYS + ["old_pred", "mu", "sd"]], on=KEYS, validate="one_to_one")
    joined = joined.merge(truth[KEYS + ["expected"]], on=KEYS, validate="one_to_one")
    assert len(joined) == len(decoded) == len(seed) == len(truth)
    assert set(joined["code_bss"]) == set(seed["code_bss"])
    np.testing.assert_allclose(joined["pred"], joined["expected"], rtol=0, atol=1e-5)
    constant = joined["code_bss"].eq(CONSTANT_WELL)
    assert constant.any() and joined.loc[constant, "sd"].lt(R.SD_FLOOR).all()
    assert joined.loc[~constant, "sd"].gt(R.SD_FLOOR).all()
    np.testing.assert_array_equal(joined.loc[~constant, "pred"], joined.loc[~constant, "old_pred"])
    assert (joined.loc[constant, "pred"] - joined.loc[constant, "old_pred"]).abs().max() > 1e-5
    gap = (joined["pred"] - joined["expected"]).abs().max()
    anomaly = (joined.loc[constant, "pred"] - joined.loc[constant, "mu"]).abs().max()
    print(f"  1. {len(joined)} seed-0 heads over {joined['code_bss'].nunique()} wells match their "
          f"decomposition (max difference {gap:.2e} m); AIGUAN's maximum anomaly is {anomaly:.6f} m. "
          "All other wells are exactly unchanged.")


def test_model_names(root, panel, seed):
    sample = seed[seed["code_bss"].eq(CONSTANT_WELL)].sort_values("z").head(2)
    scale = panel.merge(sample[KEYS], on=KEYS, validate="one_to_one")[KEYS + ["mu", "sd"]]
    cache = root / "_cache"
    cache.mkdir()
    scale.to_parquet(cache / "panel.parquet", index=False)
    runs = ("resp_fixture", "p4_fixture", "p4_fixture/fold_0", "lstm_fixture")
    for run in runs:
        out = root / run
        out.mkdir(parents=True, exist_ok=True)
        sample.to_parquet(out / "seed_0.parquet", index=False)
    with patch.object(L, "RESULTS", root):
        for run in runs:
            decoded = L.seed_frames(run)[0].merge(sample, on=KEYS).merge(scale, on=KEYS)
            sd = decoded["sd"] if run == "lstm_fixture" else decoded["sd"].clip(lower=R.SD_FLOOR)
            np.testing.assert_array_equal(decoded["pred"], decoded["mu"] + sd * decoded["z"])
    print("  2. Response and Phase 4 seeds, including folds, use the floor; other model seeds keep raw sd.")


def test_response_main(root, panel, seed):
    codes = [CONSTANT_WELL, sorted(set(seed["code_bss"]) - {CONSTANT_WELL})[0]]
    selected = panel[panel["code_bss"].isin(codes)].copy()
    before = selected.copy(deep=True)
    run = "resp_decode_fixture"
    out = root / run
    out.mkdir()
    seed[seed["code_bss"].isin(codes)].to_parquet(out / "seed_0.parquet", index=False)
    columns = ["group", "variant", "split", "n_wells", "NSE", "skill", "KGE", "RMSE"]
    argv = ["response", "--mode", "free", "--run", run, "--seeds", "0"]
    with patch.object(R, "RESULTS", root), patch.object(E, "RESULTS", root), \
            patch.object(R, "build_panel", return_value=selected), \
            patch.object(R, "cached_seed", return_value=True), \
            patch.object(R, "train_seed", side_effect=AssertionError("fitting is forbidden")) as training, \
            patch.object(R, "seed_mean_predictions", wraps=R.seed_mean_predictions) as decoding, \
            patch.object(R, "evaluate_run", return_value=pd.DataFrame(columns=columns)), \
            patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
        R.main()
        training.assert_not_called()
    passed = decoding.call_args.args[1]
    assert passed is not selected and passed["sd"].ge(R.SD_FLOOR).all()
    pd.testing.assert_frame_equal(selected, before, check_exact=True)
    written = pd.read_parquet(out / "predictions.parquet")
    expected = seed.merge(selected[KEYS + ["mu", "sd"]], on=KEYS, validate="one_to_one")
    expected["expected"] = expected["mu"] + expected["sd"].clip(lower=R.SD_FLOOR) * expected["z"]
    joined = written.merge(expected[KEYS + ["expected"]], on=KEYS, validate="one_to_one")
    assert len(joined) == len(expected) and set(joined["code_bss"]) == set(codes)
    np.testing.assert_allclose(joined["pred"], joined["expected"], rtol=0, atol=1e-5)
    print("  3. response.main writes the correctly decoded cached seed and leaves its input panel unchanged.")


def main():
    started = time.perf_counter()
    panel, seed, contrib, params = fixtures()
    test_saved_decomposition(panel, seed, contrib, params)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as tmp:
        root = Path(tmp)
        test_model_names(root, panel, seed)
        test_response_main(root, panel, seed)
    print(f"test_response_decode: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
