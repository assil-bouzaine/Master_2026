"""Check frozen matcher inputs and GPU-run contracts without models (v5 plan R2.3).

Small stubs exercise retrieval, candidate selection, resumable raw answers and
the unchanged scorer. No dependency installation, network or training is used.
Run with PFE_DATASET=v5 python -m tests.test_align_match.
"""
import copy
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from src.config import ROOT
from src.kg import align_eval, align_match

TEMPLATE = """## System
Choose one candidate or none. Return only {"target": "id or none"}.
## User
Source: {source}
Candidates: {candidates}
"""


def _raises(error, fragment, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except error as caught:
        assert fragment in str(caught), str(caught)
    else:
        raise AssertionError(f"Expected {error.__name__}: {fragment}")


def _fixture(folder, target="hcat"):
    data = {"format": 1, "target": target, "sha256": {},
            "sources": [{"code": code, "label": f"Culture {code}", "group_label": "Groupe"}
                        for code in "ABC"],
            "targets": [{"id": str(i), "label": f"Target {i}", "ancestors": ["Crops"]}
                        for i in range(10, 22)]}
    path = folder / f"inputs_{target}.json"
    path.write_text(align_match._json(data), encoding="utf-8")
    prompt = folder / "prompt.md"
    prompt.write_text(TEMPLATE, encoding="utf-8")
    return data, path, prompt


def _rankings(data):
    return {source["code"]: [{"target": target["id"], "score": 1.0 - index / 20}
                            for index, target in enumerate(data["targets"][:10])]
            for source in data["sources"]}


def test_inputs():
    """Changing every non-code gold cell cannot change a byte of frozen inputs."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        first, second = folder / "first.json", folder / "second.json"
        data = align_match.write_inputs(first)
        align_match.write_inputs(second)
        assert first.read_bytes() == second.read_bytes()
        rows = align_eval._read_csv(align_eval.HCAT_GOLD, ("code",))
        fields = list(rows[0])
        shuffled = copy.deepcopy(rows)
        for index, row in enumerate(shuffled):
            for field in fields:
                if field != "code":
                    row[field] = rows[-index - 1][field]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(reversed(shuffled))
        changed = folder / "gold.csv"
        changed.write_text(buffer.getvalue(), encoding="utf-8")
        align_match.write_inputs(second, codes_path=changed)
        assert first.read_bytes() == second.read_bytes()
        assert len(data["sources"]) == 198 and len(data["targets"]) == 384
        assert set(data["sources"][0]) == {"code", "label", "group", "group_label"}
        assert all(set(row) == {"id", "label", "ancestors"} for row in data["targets"])
        for name, digest in data["sha256"].items():
            assert align_match._sha256_file(ROOT / name) == digest
        targets = {row["id"]: row for row in data["targets"]}
        assert targets["3301010101"]["ancestors"] == [
            "characteristics", "crop type", "arable crops", "cereal", "common soft wheat"]
        assert targets["3000000000"]["ancestors"] == []
        assert "_" not in targets["3301010101"]["label"]
        print("  inputs: 198 sources, 384 targets; deterministic, gold-independent, hashes and ancestors pass")


def test_stub_runner_and_score():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        data, path, prompt = _fixture(folder)
        answers = iter(['{"target":"10"}', '{"target":"10"}', '{"target":"none"}'])
        calls = []

        def generate(msgs):
            calls.append(msgs)
            return next(answers)

        out = folder / "llm"
        pred, meta = align_match.run_alignment("llm", "hcat", out, inputs_path=path,
            prompt_path=prompt, matcher_stub=_rankings, generator=generate)
        assert len(calls) == 3 and len(meta["parse_failures"]) == 0
        loaded = align_eval.load_predictions(pred, "hcat")
        gold = [{"code": code, "target": str(i), "area_ha": float(i - 9),
                 "relation": "", "alternatives": [], "in_gold": True}
                for code, i in zip("ABC", range(10, 13))]
        score = align_eval.score(gold, loaded, "hcat", "dev")
        strict = score["scores"]["strict"]
        assert strict["precision"]["value"] == 0.5
        assert strict["recall"]["value"] == 1 / 3
        assert strict["f1"]["value"] == 0.4
        assert score["counts"]["abstentions"] == 1
        original = pred.read_bytes()
        times = {f.name: f.stat().st_mtime_ns for f in (out / "raw").iterdir()}

        def forbidden(*args):
            raise AssertionError("A complete run must reuse raw outputs")

        align_match.run_alignment("llm", "hcat", out, inputs_path=path, prompt_path=prompt,
                                  matcher_stub=forbidden, generator=forbidden)
        assert pred.read_bytes() == original
        assert times == {f.name: f.stat().st_mtime_ns for f in (out / "raw").iterdir()}
        retrieval, meta = align_match.run_alignment("retrieval", "hcat", folder / "retrieval",
                                                    inputs_path=path, matcher_stub=_rankings)
        loaded = align_eval.load_predictions(retrieval, "hcat")
        assert meta["n_predictions"] == 30
        assert all([row["rank"] for row in rows] == list(range(1, 11)) for rows in loaded.values())
        assert all(len(rows) == 10 for rows in loaded.values())
        with retrieval.open(encoding="utf-8", newline="") as stream:
            assert all(float(row["score"]) > 0 for row in csv.DictReader(stream))
        fuzzy, _ = align_match.run_alignment("fuzzy", "hcat", folder / "fuzzy", inputs_path=path,
            matcher_stub=lambda payload: {code: rows[:1] for code, rows in _rankings(payload).items()})
        assert len(align_eval.load_predictions(fuzzy, "hcat")) == 3
        # A second target uses the same runner and only a different input file.
        _, other, _ = _fixture(folder, "agrovoc")
        align_match.run_alignment("retrieval", "agrovoc", folder / "agrovoc",
                                  inputs_path=other, matcher_stub=_rankings)
        assert "gold" not in json.dumps(calls)
        print("  stubs and scorer: P=1/2, R=1/3, F1=0.4; ranks 1..10, raw reuse and second target pass")


def test_config_lock():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        data, path, prompt = _fixture(folder)
        out = folder / "run"
        arguments = dict(inputs_path=path, prompt_path=prompt,
                         matcher_stub=_rankings, generator=lambda msgs: '{"target":"none"}')
        align_match.run_alignment("llm", "hcat", out, **arguments)
        pred_before = (out / "predictions.csv").read_bytes()
        prompt.write_text(TEMPLATE + "\nChanged prompt.\n", encoding="utf-8")
        _raises(ValueError, "sha256.prompt", align_match.run_alignment, "llm", "hcat", out, **arguments)
        prompt.write_text(TEMPLATE, encoding="utf-8")
        data["sources"][0]["label"] = "Changed label"
        path.write_text(align_match._json(data), encoding="utf-8")
        _raises(ValueError, "sha256.inputs", align_match.run_alignment, "llm", "hcat", out, **arguments)
        assert (out / "predictions.csv").read_bytes() == pred_before
        data, _, _ = _fixture(folder)
        with patch.object(align_match, "LLM_COMMIT", "changed"):
            _raises(ValueError, "models", align_match.run_alignment, "llm", "hcat", out, **arguments)
        _raises(ValueError, "matcher", align_match.run_alignment, "retrieval", "hcat", out,
                inputs_path=path, matcher_stub=_rankings)
        other = folder / "nonempty"
        other.mkdir()
        (other / "untracked.txt").write_text("Keep", encoding="utf-8")
        _raises(ValueError, "nonempty", align_match.run_alignment, "retrieval", "hcat", other,
                inputs_path=path, matcher_stub=_rankings)
        print("  config lock: changed prompt, inputs, matcher and unowned nonempty folder refused")


def test_component_adapters():
    """Check the inspected OntoAligner interfaces and pinned load arguments without importing it."""
    # Load the C extension before patch.dict snapshots sys.modules. Restoring that
    # snapshot must not unload torch and force an unsupported second import.
    import torch

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        data, path, _ = _fixture(folder)
        expected = _rankings(data)
        fuzzy = Mock()
        fuzzy.generate.return_value = [{"source": code, **rows[0]} for code, rows in expected.items()]
        fuzzy_class = Mock(return_value=fuzzy)
        retriever = Mock()
        retriever.generate.return_value = [{"source": code,
            "target-cands": [row["target"] for row in rows],
            "score-cands": [row["score"] for row in rows]} for code, rows in expected.items()]
        retriever_class = Mock(return_value=retriever)
        model = MagicMock()
        model[0].auto_model.config._commit_hash = align_match.RETRIEVAL_COMMIT
        loader = Mock(return_value=model)
        modules = {
            "ontoaligner.aligner.lightweight.models": SimpleNamespace(SimpleFuzzySMLightweight=fuzzy_class),
            "ontoaligner.aligner.retrieval.models": SimpleNamespace(SBERTRetrieval=retriever_class),
            "sentence_transformers": SimpleNamespace(SentenceTransformer=loader),
        }
        with patch.dict(sys.modules, modules), patch.object(
                align_match, "_package_version", return_value="1.9.4"), patch.object(
                torch.cuda, "is_available", return_value=True):
            result, _ = align_match._fuzzy(data)
            assert result == {code: rows[:1] for code, rows in expected.items()}
            fuzzy_class.assert_called_once_with(fuzzy_sm_threshold=0.0)
            assert all("RPG group" not in row["text"] for row in fuzzy.generate.call_args.args[0][0])
            pred, meta = align_match.run_alignment("retrieval", "hcat", folder / "retrieval", inputs_path=path)
            assert len(align_eval.load_predictions(pred, "hcat")["A"]) == 10
            loader.assert_called_once_with(align_match.RETRIEVAL_MODEL,
                revision=align_match.RETRIEVAL_COMMIT, device="cuda")
            retriever_class.assert_called_once_with(device="cuda", top_k=10, batch_size=16)
            assert meta["resolved_commits"] == {align_match.RETRIEVAL_MODEL: align_match.RETRIEVAL_COMMIT}
            encoded = retriever.generate.call_args.args[0]
            assert "RPG group: Groupe" in encoded[0][0]["text"]
            assert "ancestors: Crops" in encoded[1][0]["text"]
            model[0].auto_model.config._commit_hash = "wrong revision"
            _raises(RuntimeError, "resolved", align_match._retrieve, data)
        # Exercise the actual frozen prompt and direct Qwen loader arguments too.
        with patch("torch.cuda.is_available", return_value=True), patch(
                "torch.cuda.empty_cache"), patch.object(align_match, "_load_hf_generator",
                return_value=(lambda msgs: '{"target":"none"}', align_match.LLM_COMMIT)) as llm:
            _, meta = align_match.run_alignment("llm", "hcat", folder / "llm", inputs_path=path,
                                                matcher_stub=_rankings)
            llm.assert_called_once_with(align_match.LLM_MODEL, align_match.LLM_COMMIT,
                                       "bfloat16", 128, {"enable_thinking": False})
            assert meta["resolved_commits"][align_match.LLM_MODEL] == align_match.LLM_COMMIT
            assert meta["sha256"]["prompt"] == align_match._sha256_file(align_match.PROMPT)
        print("  component adapters: fuzzy/SBERT interfaces, pinned commits, context and Qwen thinking-off pass")


def test_no_cuda_and_parsing():
    with tempfile.TemporaryDirectory() as tmp, patch("torch.cuda.is_available", return_value=False):
        folder = Path(tmp)
        _, path, prompt = _fixture(folder)
        for matcher in ("retrieval", "llm"):
            out = folder / matcher
            _raises(RuntimeError, "No CUDA", align_match.run_alignment, matcher, "hcat", out,
                    inputs_path=path, prompt_path=prompt)
            assert not out.exists()
        candidates = [{"target": "10", "score": 0.5}]
        assert align_match.parse_answer('{"target":"none"}', candidates) == ("", None)
        assert align_match.parse_answer('<think>reason</think>\n```json\n{"target":"10"}\n```',
                                        candidates) == ("10", None)
        for invalid in ('{"target":"11"}', '[]', 'garbage', '{"target":null}',
                        '{"target":"10","explanation":"extra"}'):
            target, error = align_match.parse_answer(invalid, candidates)
            assert target == "" and error
        pred, meta = align_match.run_alignment("llm", "hcat", folder / "invalid", inputs_path=path,
            prompt_path=prompt, matcher_stub=_rankings, generator=lambda msgs: '{"target":"unknown"}')
        assert len(meta["parse_failures"]) == 3
        assert all(rows[0]["target"] == "" for rows in align_eval.load_predictions(pred, "hcat").values())
        # Incomplete runs retain every already-written raw answer after a failure.
        attempts = iter(['{"target":"10"}', RuntimeError("interrupted")])

        def interrupted(msgs):
            value = next(attempts)
            if isinstance(value, Exception):
                raise value
            return value

        out = folder / "interrupted"
        _raises(RuntimeError, "interrupted", align_match.run_alignment, "llm", "hcat", out,
            inputs_path=path, prompt_path=prompt, matcher_stub=_rankings, generator=interrupted)
        assert len(list((out / "raw").glob("*.txt"))) == 1
        count = []

        def resume(msgs):
            count.append(msgs)
            return '{"target":"none"}'

        align_match.run_alignment("llm", "hcat", out, inputs_path=path, prompt_path=prompt,
                                  matcher_stub=_rankings, generator=resume)
        assert len(count) == 2
        print("  CUDA refusal, strict candidate parsing, visible parse failures and partial resume pass")


def test_gpu_step_and_bundle():
    """Execute the actual case arm with a recording Python shim, without installing anything."""
    script = ROOT / "scripts" / "run_gpu.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    arm = script.read_text(encoding="utf-8").split("    align)", 1)[1].split("    extract)", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        shim = folder / "python"
        log = folder / "calls.jsonl"
        shim.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                        "with open(os.environ['T92_LOG'], 'a') as stream:\n"
                        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n", encoding="utf-8")
        shim.chmod(0o755)
        for target, override in ((None, None), ("agrovoc", str(folder / "results override"))):
            log.write_text("", encoding="utf-8")
            env = {**os.environ, "T92_LOG": str(log), "PY": str(shim), "PFE_DATASET": "v5",
                   "ALIGN_MATCHER": "llm", "ALIGN_RUN": "test run"}
            env.pop("ALIGN_TARGET", None)
            env.pop("PFE_RESULTS", None)
            if target:
                env["ALIGN_TARGET"] = target
            if override:
                env["PFE_RESULTS"] = override
            result = subprocess.run(["bash", "-uc", "case align in\n align)" + arm + "\nesac"],
                                    env=env, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            assert calls[0] == ["-m", "pip", "install", "ontoaligner==1.9.4"]
            assert calls[1] == ["-m", "src.kg.align_match", "run", "--matcher", "llm", "--target",
                               target or "hcat", "--out",
                               f"{override or 'results/v5'}/alignment/test run"]
        from scripts.make_gpu_bundle import bundle_files
        files = set(bundle_files())
        assert align_match.INPUTS in files
        assert align_match.PROMPT in files
        # Test the actual archive writer without generating a large project artifact.
        import zipfile
        from scripts import make_gpu_bundle
        archive = folder / "bundle.zip"
        archive_sources = [align_match.INPUTS, align_match.PROMPT]
        with patch.object(make_gpu_bundle, "OUT", archive), patch.object(
                make_gpu_bundle, "bundle_files", return_value=iter(archive_sources)):
            make_gpu_bundle.main()
        with zipfile.ZipFile(archive) as zipped:
            assert "data/interim/align_inputs_hcat.json" in zipped.namelist()
            assert zipped.read("configs/align_prompt_hcat.md") == align_match.PROMPT.read_bytes()
        assert align_match.HCAT_GOLD not in files
        print("  bash -n, session-only install, ALIGN variables, output override and bundle membership pass")


if __name__ == "__main__":
    started = time.perf_counter()
    test_inputs()
    test_stub_runner_and_score()
    test_config_lock()
    test_component_adapters()
    test_no_cuda_and_parsing()
    test_gpu_step_and_bundle()
    print(f"test_align_match: all checks passed ({time.perf_counter() - started:.2f}s)")
