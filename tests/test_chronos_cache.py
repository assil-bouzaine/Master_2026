"""Keep Chronos smoke runs and incompatible caches apart (analysis plan §7b).

Use three wells from the existing panel and a zero-output pipeline stub. No
Chronos import, model download, GPU use or fitting is needed for these checks.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_chronos_cache
"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import pandas as pd
import torch

from src.config import ROOT
from src.models import chronos2 as C, evaluate as E

SCRATCH = ROOT / "results" / "_agents" / "tmp"


class StubPipeline:
    def __init__(self):
        self.loads = []
        self.predictions = 0
        self.fits = []
        self.selection_path = None

    def from_pretrained(self, model, device_map):
        assert device_map == "cpu"
        assert self.selection_path.is_file(), "selection must be saved before loading or predicting"
        self.loads.append(model)
        return self

    def predict_quantiles(self, inputs, prediction_length, batch_size, cross_learning=False):
        assert self.selection_path.is_file()
        assert inputs and prediction_length == max(C.HORIZONS)
        if cross_learning:
            assert batch_size == len(inputs)
        self.predictions += 1
        return None, torch.zeros((len(inputs), prediction_length))

    def fit(self, inputs, prediction_length, validation_inputs, batch_size, num_steps, output_dir):
        assert inputs and validation_inputs and prediction_length == max(C.HORIZONS)
        assert batch_size == 64
        self.fits.append(num_steps)
        checkpoint = Path(output_dir) / "finetuned-ckpt"
        checkpoint.mkdir(parents=True)
        (checkpoint / "stub.json").write_text("{}\n", encoding="utf-8")
        return self


def small_panel():
    panel = pd.read_parquet(E.RESULTS / "_cache" / "panel.parquet")
    codes = sorted(panel.loc[panel["mu"].notna(), "code_bss"].unique())[:3]
    validation = panel.loc[panel["split"] == "validation", "week"].min()
    keep = panel["week"].between(validation - pd.Timedelta(weeks=C.CONTEXT + 1),
                                 validation + pd.Timedelta(weeks=max(C.HORIZONS) + 2))
    return panel[panel["code_bss"].isin(codes) & keep].copy()


def invoke(root, panel, pipe, argv):
    mode = argv[argv.index("--mode") + 1]
    smoke = f"_smoke{argv[argv.index('--wells') + 1]}" if "--wells" in argv else ""
    pipe.selection_path = root / (C.RUNS[mode] + smoke) / "selection.json"
    columns = ["group", "variant", "task", "horizon", "split", "n_wells", "NSE", "skill", "KGE", "RMSE"]
    with patch.object(C, "RESULTS", root), patch.object(E, "RESULTS", root), \
            patch.object(C, "build_panel", return_value=panel), \
            patch.object(C, "evaluate_run", return_value=pd.DataFrame(columns=columns)) as scoring, \
            patch.object(C.torch.cuda, "is_available", return_value=False), \
            patch.dict("sys.modules", {"chronos": None}), redirect_stdout(StringIO()):
        C.main(argv, pipeline_factory=pipe)
        scoring.assert_called_once_with(C.RUNS[mode] + smoke)


def expect_stop(root, panel, pipe, argv, fields):
    before = (len(pipe.loads), pipe.predictions, len(pipe.fits))
    try:
        invoke(root, panel, pipe, argv)
    except SystemExit as error:
        message = str(error)
        assert "use a clean folder" in message, message
        assert all(field in message for field in fields), message
    else:
        raise AssertionError("an incompatible cache was accepted")
    assert before == (len(pipe.loads), pipe.predictions, len(pipe.fits)), "a rejected run used the pipeline"


def test_smoke_and_full(root, panel, pipe):
    invoke(root, panel, pipe, ["--mode", "xl", "--wells", "1"])
    assert not (root / C.RUNS["xl"]).exists(), "smoke run created the folder of record"
    smoke = root / (C.RUNS["xl"] + "_smoke1")
    assert pd.read_parquet(smoke / "predictions.parquet")["code_bss"].nunique() == 1
    saved = json.loads((smoke / "selection.json").read_text())
    assert saved["wells"] == sorted(panel["code_bss"].unique())[:1]
    assert saved["model"] == C.MODEL and saved["mode"] == "xl"
    assert saved["context"] == C.CONTEXT and saved["horizons"] == list(C.HORIZONS)
    assert saved["past_covariates"] == C.past_cols(panel) and saved["future_covariates"] == C.FUTURE
    assert "ft_steps" not in saved
    calls = pipe.predictions
    invoke(root, panel, pipe, ["--mode", "xl"])
    full = root / C.RUNS["xl"]
    pred = pd.read_parquet(full / "predictions.parquet")
    assert pipe.predictions > calls and sorted(pred["code_bss"].unique()) == sorted(panel["code_bss"].unique())
    calls = pipe.predictions
    invoke(root, panel, pipe, ["--mode", "xl"])
    assert pipe.predictions == calls, "an identical xl run did not reuse its cache"
    print("  1. XL smoke uses its own folder; the full run predicts all three wells and then reuses its cache.")


def test_wrong_and_legacy(root, panel, pipe):
    source = root / C.RUNS["xl"]
    wrong = root / "wrong" / C.RUNS["xl"]
    wrong.mkdir(parents=True)
    selection = json.loads((source / "selection.json").read_text())
    selection["wells"] = ["another well"]
    path = wrong / "selection.json"
    path.write_text(json.dumps(selection), encoding="utf-8")
    before = path.read_bytes()
    expect_stop(wrong.parent, panel, pipe, ["--mode", "xl"], ["wells"])
    assert path.read_bytes() == before
    legacy = root / "legacy" / C.RUNS["xl"] / "wells"
    legacy.mkdir(parents=True)
    cached = legacy / "all_wells.parquet"
    cached.write_bytes((source / "wells" / "all_wells.parquet").read_bytes())
    before = cached.read_bytes()
    expect_stop(legacy.parent.parent, panel, pipe, ["--mode", "xl"], ["selection.json"])
    assert cached.read_bytes() == before and not (legacy.parent / "selection.json").exists()
    print("  2. Changed well selections and legacy caches without metadata stop before loading a pipeline.")


def test_zeroshot_and_ft(root, panel, pipe):
    invoke(root, panel, pipe, ["--mode", "zeroshot"])
    calls = pipe.predictions
    invoke(root, panel, pipe, ["--mode", "zeroshot"])
    assert pipe.predictions == calls
    invoke(root, panel, pipe, ["--mode", "ft", "--ft-steps", "7"])
    assert pipe.fits == [7]
    ft = root / C.RUNS["ft"]
    selection = json.loads((ft / "selection.json").read_text())
    assert selection["ft_steps"] == 7
    calls = pipe.predictions
    invoke(root, panel, pipe, ["--mode", "ft", "--ft-steps", "7"])
    assert pipe.fits == [7] and pipe.predictions == calls
    assert pipe.loads[-1] == str(ft / "ckpt" / "finetuned-ckpt")
    expect_stop(root, panel, pipe, ["--mode", "ft", "--ft-steps", "8"], ["ft_steps"])
    with patch.object(C, "CONTEXT", C.CONTEXT + 1):
        expect_stop(root, panel, pipe, ["--mode", "ft", "--ft-steps", "7"], ["context"])
    with patch.object(C, "MODEL", C.MODEL + "-changed"), patch.object(C, "HORIZONS", (4, 13)):
        expect_stop(root, panel, pipe, ["--mode", "ft", "--ft-steps", "7"], ["model", "horizons"])
    print("  3. Zero-shot caches and FT checkpoints resume unchanged; altered steps, context, model or horizons stop.")


def main():
    started = time.perf_counter()
    panel = small_panel()
    assert panel["code_bss"].nunique() == 3
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as tmp:
        root, pipe = Path(tmp), StubPipeline()
        test_smoke_and_full(root, panel, pipe)
        test_wrong_and_legacy(root, panel, pipe)
        test_zeroshot_and_ft(root, panel, pipe)
    print(f"test_chronos_cache: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
