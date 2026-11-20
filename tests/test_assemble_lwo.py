"""Check the saved-seed scale for the leave-wells-out regime (analysis plan §4).

Run with PFE_DATASET=v4 python -m tests.test_assemble_lwo. Assemble small fake
folds in a temporary results folder without fitting models.
"""
import json
import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd


def main():
    # The standalone assembler is used offline on Kaggle, where Optuna may be absent.
    with patch.dict(sys.modules, {"optuna": None}):
        from src.models import regimes
        from src.models.response import SD_FLOOR

        with TemporaryDirectory() as folder:
            root = Path(folder)
            splits = {"leave_wells_out": {"fold_of_well": {"A": 0, "B": 1}}}
            (root / "splits.json").write_text(json.dumps(splits))
            panel = pd.DataFrame({"code_bss": ["A", "B"], "mu": [0.0, 20.0], "sd": [1e-13, 2.0]})
            week = pd.Timestamp("2024-01-07").as_unit("ns")
            for run, scale in (("p4_example_lwo", SD_FLOOR), ("resp_example_lwo", SD_FLOOR),
                               ("lstm_example_lwo", 1e-13)):
                for fold in range(2):
                    out = root / run / f"fold_{fold}"
                    out.mkdir(parents=True)
                    for seed in range(2):
                        z = [1.0 + 2 * seed, 100.0] if fold == 0 else [100.0, 3.0 + 2 * seed]
                        pd.DataFrame({"code_bss": ["A", "B"], "week": week, "z": z}).to_parquet(
                            out / f"seed_{seed}.parquet", index=False)
                with (patch.object(regimes, "DS", root), patch.object(regimes, "RESULTS", root),
                      patch.object(regimes, "N_FOLDS", 2), patch.object(regimes, "build_panel", return_value=panel),
                      patch.object(regimes, "evaluate_run") as evaluate):
                    regimes.assemble_lwo(run, seeds=[0, 1])
                evaluate.assert_called_once_with(run)
                actual = root / run / "predictions.parquet"
                expected = pd.DataFrame({"code_bss": ["A", "B"], "week": week, "pred": [2 * scale, 28.0],
                                         "pred_seed_sd": [math.sqrt(2) * scale, math.sqrt(2) * 2],
                                         "task": "simulation", "horizon": 0})
                pd.testing.assert_frame_equal(pd.read_parquet(actual), expected, check_exact=True)
                if run.startswith("lstm_"):
                    legacy = root / "legacy.parquet"
                    expected.to_parquet(legacy, index=False)
                    assert actual.read_bytes() == legacy.read_bytes()
    print("test_assemble_lwo: response predictions and spreads use SD_FLOOR, legacy LSTM bytes match")


if __name__ == "__main__":
    main()
