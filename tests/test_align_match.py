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
    if target == "agrovoc":
        # Use IRIs actually present in the local snapshot, without reading gold judgements.
        import pandas as pd
        from src.ingest.agrovoc import LABELS

        ids = sorted(pd.read_parquet(LABELS, columns=["concept"])["concept"].unique())[:12]
        for row, ident in zip(data["targets"], ids):
            row.update(id=ident, label_en=row["label"], alt=[])
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


def test_agrovoc_inputs():
    """Only the real gold's code column is read; every other test cell is synthetic."""
    import pandas as pd
    from src.ingest.agrovoc import BROADER, LABELS

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        first, second = folder / "first.json", folder / "second.json"
        data = align_match.write_inputs(first, target="agrovoc")
        align_match.write_inputs(second, target="agrovoc")
        assert first.read_bytes() == second.read_bytes()
        # Inspect the header only; do not read any real non-code gold cells.
        with align_eval.AGROVOC_GOLD.open(encoding="utf-8", newline="") as stream:
            fields = next(csv.reader(stream))
        codes = pd.read_csv(align_eval.AGROVOC_GOLD, usecols=["code"], dtype=str)["code"].tolist()
        synthetic = [{field: code if field == "code" else f"synthetic {field} {index}"
                      for field in fields} for index, code in enumerate(codes)]
        changed = folder / "gold.csv"
        with changed.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(synthetic)
        align_match.write_inputs(second, target="agrovoc", codes_path=changed)
        assert first.read_bytes() == second.read_bytes()
        for index, row in enumerate(synthetic):
            for field in fields:
                if field != "code":
                    row[field] = f"shuffled {field} {len(codes) - index}"
        with changed.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(reversed(synthetic))
        align_match.write_inputs(second, target="agrovoc", codes_path=changed)
        assert first.read_bytes() == second.read_bytes()
        labels = pd.read_parquet(LABELS)
        deprecated = set(labels.loc[labels["deprecated"], "concept"])
        ids = [row["id"] for row in data["targets"]]
        assert len(ids) == len(set(ids))
        assert set(ids) == set(labels["concept"]) - deprecated
        assert all(set(row) == {"id", "label", "label_en", "alt", "ancestors"}
                   and len(row["alt"]) <= 5 and len(row["ancestors"]) <= 3 for row in data["targets"])
        assert data["sources"] == align_match.build_inputs()["sources"]
        assert data["release"] == "2026-10-26"
        for path in (LABELS, BROADER):
            assert data["sha256"][align_match._path_name(path)] == align_match._sha256_file(path)
        print(f"  AGROVOC inputs: {len(data['sources'])} sources, {len(ids)} live concepts; "
              "deterministic, code-only gold, release and both table hashes pass")


def test_agrovoc_target_fixture():
    """Two live concepts expose language fallback, alias limits and direct-parent text."""
    import pandas as pd
    from src.ingest.agrovoc import LABELS

    real = pd.read_parquet(LABELS)
    child, parent = real.loc[~real["deprecated"], "concept"].drop_duplicates().iloc[:2]
    dead = real.loc[real["deprecated"], "concept"].iloc[0]
    rows = [(child, "Culture", "fr", "pref"), (child, "Crop", "en", "pref"),
            (parent, "Parent", "en", "pref"), (dead, "Deprecated", "en", "pref")]
    rows += [(child, label, "fr", "alt") for label in ("Z", "A", "C", "B")]
    rows += [(child, label, "en", "alt") for label in ("Y", "E", "D", "A")]
    rows += [(child, "Culture", "fr", "pref")]  # Duplicate SKOS/SKOS-XL label.
    table = pd.DataFrame(rows, columns=["concept", "label", "lang", "kind"])
    table["vocab"], table["release"] = "skos", "2026-10-26"
    table["deprecated"] = table["concept"].eq(dead)
    edges = pd.DataFrame([(child, parent, "2026-10-26")], columns=["concept", "broader", "release"])
    with tempfile.TemporaryDirectory() as tmp:
        labels, broader = Path(tmp) / "labels.parquet", Path(tmp) / "broader.parquet"
        table.to_parquet(labels, index=False)
        edges.to_parquet(broader, index=False)
        targets, release = align_match._agrovoc_targets(labels, broader)
        lookup = {row["id"]: row for row in targets}
        assert set(lookup) == {child, parent} and release == "2026-10-26"
        assert lookup[child] == {"id": child, "label": "Culture", "label_en": "Crop",
                                 "alt": ["A", "B", "C", "Z", "D"], "ancestors": ["Parent"]}
        assert lookup[parent] == {"id": parent, "label": "Parent", "label_en": "Parent",
                                  "alt": [], "ancestors": []}
        data = {"target": "agrovoc", "sources": [{"code": "A", "label": "Culture",
                "group_label": "Groupe"}], "targets": [lookup[child], lookup[parent]]}
        encoded = align_match._encoded(data, context=True)
        assert encoded[1][0]["text"] == "Culture; en: Crop; also: A; B; C; Z; D; broader: Parent"
        assert encoded[1][1]["text"] == "Parent; en: Parent"
        assert align_match._encoded(data, context=False)[1][0]["text"] == "Culture"
        data["targets"][0] = {**lookup[child], "label_en": "", "alt": [], "ancestors": []}
        assert align_match._encoded(data, context=True)[1][0]["text"] == "Culture"
        table.sample(frac=1, random_state=97).to_parquet(labels, index=False)
        assert align_match._agrovoc_targets(labels, broader) == (targets, release)
        print("  AGROVOC two-concept fixture: French/English fallback, deduplication, "
              "five sorted aliases, direct broader text and empty-part omission pass")


def test_agrovoc_parsing_and_score():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        data, path, _ = _fixture(folder, "agrovoc")
        ident = data["targets"][0]["id"]
        candidates = [{"target": ident}]
        for relation in align_match.RELATIONS:
            raw = json.dumps({"target": ident, "relation": relation})
            assert align_match.parse_answer(raw, candidates, "agrovoc") == (ident, relation, None)
        raw = '<think>reason</think>\n```json\n' + raw + '\n```'
        assert align_match.parse_answer(raw, candidates, "agrovoc") == (ident, "narrowMatch", None)
        assert align_match.parse_answer('{"target":"none","relation":"exactMatch"}',
                                         candidates, "agrovoc") == ("", "", None)
        for raw in ('{"target":"none"}', '{"target":"none","relation":"none"}',
                    '{"target":"none","relation":null}', '[]', 'garbage',
                    json.dumps({"target": ident, "relation": "unknown"}),
                    json.dumps({"target": ident, "relation": "exactMatch", "extra": "x"}),
                    '{"target":"outside","relation":"exactMatch"}'):
            target, relation, error = align_match.parse_answer(raw, candidates, "agrovoc")
            assert target == relation == "" and error
        answers = iter([json.dumps({"target": ident, "relation": "broadMatch"}),
                        json.dumps({"target": ident, "relation": "unknown"}),
                        '{"target":"none","relation":"exactMatch"}'])
        calls = []

        def generate(messages):
            calls.append(messages)
            return next(answers)

        out = folder / "llm"
        pred, meta = align_match.run_alignment("llm", "agrovoc", out, inputs_path=path,
                                               matcher_stub=_rankings, generator=generate)
        assert meta["sha256"]["prompt"] == align_match._sha256_file(align_match.AGROVOC_PROMPT)
        assert meta["parse_failures"] == [{"code": "B", "error": "Unknown AGROVOC relation"}]
        assert json.loads((out / "run.json").read_text())["parse_failures"] == meta["parse_failures"]
        supplied = json.loads(calls[0][1]["content"].split("Candidate targets:\n", 1)[1])
        assert set(supplied[0]) == {"id", "label", "label_en", "alt", "ancestors", "rank"}
        loaded = align_eval.load_predictions(pred, "agrovoc")
        assert loaded["A"][0]["relation"] == "broadMatch"
        assert loaded["B"][0]["target"] == loaded["B"][0]["relation"] == ""
        assert loaded["C"][0]["target"] == loaded["C"][0]["relation"] == ""
        gold_path = folder / "fake_gold.csv"
        # This is hand-made fake gold, never Assil's pending judgements.
        with gold_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("code", "split", "area_ha", "relation",
                                                       "concept", "alternatives"))
            writer.writeheader()
            for code, relation, concept in (("A", "broadMatch", ident), ("B", "exactMatch", ident),
                                             ("C", "none", "")):
                writer.writerow(dict(code=code, split="eval", area_ha=1, relation=relation,
                                     concept=concept, alternatives=""))
        with patch.object(align_eval, "AGROVOC_GOLD", gold_path):
            score = align_eval.score(align_eval.load_gold("agrovoc", "eval"), loaded, "agrovoc", "eval")
        assert score["relation_accuracy"] == {"value": 1.0, "numerator": 1, "denominator": 1}
        assert score["scores"]["strict"]["f1"]["value"] == 2 / 3
        assert score["counts"]["abstentions"] == 2
        before = pred.read_bytes()

        def forbidden(*args):
            raise AssertionError("A resumed run must reuse raw results")

        align_match.run_alignment("llm", "agrovoc", out, inputs_path=path,
                                  matcher_stub=forbidden, generator=forbidden)
        assert pred.read_bytes() == before
        retrieval, _ = align_match.run_alignment("retrieval", "agrovoc", folder / "retrieval",
                                                  inputs_path=path, matcher_stub=_rankings)
        assert len(align_eval.load_predictions(retrieval, "agrovoc")["A"]) == 10
        print("  AGROVOC answers: four relations, strict schema, unknown-relation abstention, "
              "run.json failure, default prompt, resumed CSV and unchanged scorer pass "
              "(fake gold strict F1=2/3, relation accuracy=1/1)")


def test_hcat_byte_compatibility():
    """Hashes captured before T97 protect historical inputs, prompts and all three configs."""
    expected = {
        "fuzzy": "e49f7a886996ed0df6208ffaa170806762470294bdbc25e87640bbda52457a9b",
        "retrieval": "6c5ef3d3a3344cd9c08185f3128a843f8996b7590cc6192f3bf6b75caede8888",
        "llm": "6897bca947d6838865283f58f6400f392f92cd8ea14c995e94977ca2c183f3a1",
    }
    assert align_match._sha256_file(align_match.INPUTS) == (
        "efb866b1e8d5bc5e028ced81a950303959b7b6c185f3a088e86c5223cb949937")
    assert align_match._sha256_file(align_match.PROMPT) == (
        "dddeef7db55743db01bc47afdb78d1711dad12f63d575380e1448447d1e95fea")
    assert align_match._json(align_match.build_inputs()).encode("utf-8") == align_match.INPUTS.read_bytes()
    paths = sorted((ROOT / "results" / "v5" / "alignment").glob("hcat_*/config.json"))
    before = {path: align_match._sha256_file(path) for path in paths}
    with tempfile.TemporaryDirectory() as tmp:
        for matcher in expected:
            def rankings(data):
                return {s["code"]: [{"target": t["id"], "score": 1.0}
                        for t in data["targets"][:1 if matcher == "fuzzy" else 10]]
                        for s in data["sources"]}

            kwargs = {"matcher_stub": rankings}
            if matcher == "llm":
                kwargs["generator"] = lambda msgs: '{"target":"none"}'
            out = Path(tmp) / matcher
            with patch.object(align_match, "_package_version", return_value="stub"):
                align_match.run_alignment(matcher, "hcat", out, **kwargs)
            assert align_match._sha256_file(out / "config.json") == expected[matcher]
            # Also compare with actual GPU configurations when their outputs are present.
            for path in paths:
                previous = json.loads(path.read_text(encoding="utf-8"))
                if previous["matcher"] == matcher:
                    previous.update(matcher_stub=True, generator_stub=matcher == "llm")
                    assert (out / "config.json").read_text(encoding="utf-8") == align_match._json(previous)
    assert before == {path: align_match._sha256_file(path) for path in paths}
    print("  HCAT compatibility: original input/prompt hashes, regenerated input bytes and "
          "all three pre-T97 config hashes pass; existing GPU configs unchanged")


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
        loader = Mock(return_value=model)
        snap = folder / "snapshots" / align_match.RETRIEVAL_COMMIT
        snapshot = Mock(return_value=(snap, align_match.RETRIEVAL_COMMIT))
        modules = {
            "ontoaligner.aligner.lightweight.models": SimpleNamespace(SimpleFuzzySMLightweight=fuzzy_class),
            "ontoaligner.aligner.retrieval.models": SimpleNamespace(SBERTRetrieval=retriever_class),
            "sentence_transformers": SimpleNamespace(SentenceTransformer=loader),
        }
        with patch.dict(sys.modules, modules), patch.object(
                align_match, "_package_version", return_value="1.9.4"), patch.object(
                torch.cuda, "is_available", return_value=True), patch.object(
                align_match, "_snapshot", snapshot):
            result, _ = align_match._fuzzy(data)
            assert result == {code: rows[:1] for code, rows in expected.items()}
            fuzzy_class.assert_called_once_with(fuzzy_sm_threshold=0.0)
            assert all("RPG group" not in row["text"] for row in fuzzy.generate.call_args.args[0][0])
            pred, meta = align_match.run_alignment("retrieval", "hcat", folder / "retrieval", inputs_path=path)
            assert len(align_eval.load_predictions(pred, "hcat")["A"]) == 10
            snapshot.assert_called_once_with(align_match.RETRIEVAL_MODEL, align_match.RETRIEVAL_COMMIT)
            loader.assert_called_once_with(str(snap), device="cuda")
            retriever_class.assert_called_once_with(device="cuda", top_k=10, batch_size=16)
            assert meta["resolved_commits"] == {align_match.RETRIEVAL_MODEL: align_match.RETRIEVAL_COMMIT}
            encoded = retriever.generate.call_args.args[0]
            assert "RPG group: Groupe" in encoded[0][0]["text"]
            assert "ancestors: Crops" in encoded[1][0]["text"]
            snapshot.return_value = (folder / "snapshots" / "wrong revision", "wrong revision")
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
            # bitsandbytes is removed before OntoAligner is imported (run_gpu.sh: optimizer-name clash)
            assert calls[1] == ["-m", "pip", "uninstall", "-y", "-q", "bitsandbytes"]
            assert calls[2] == ["-m", "src.kg.align_match", "run", "--matcher", "llm", "--target",
                               target or "hcat", "--out",
                               f"{override or 'results/v5'}/alignment/test run"]
        # Run the actual multi-step case arm with ALIGN_TARGET=agrovoc, without pip or a GPU.
        multi = script.read_text(encoding="utf-8").split("    align:*)", 1)[1].split("    align)", 1)[0]
        log.write_text("", encoding="utf-8")
        env = {**os.environ, "T92_LOG": str(log), "PY": str(shim), "PFE_DATASET": "v5",
               "ALIGN_TARGET": "agrovoc", "STEPS": "align:retrieval align:llm"}
        env.pop("PFE_RESULTS", None)
        result = subprocess.run(["bash", "-uc", 'for s in $STEPS; do\ncase "$s" in\n align:*)'
                                 + multi + "\nesac\ndone"], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert len(calls) == 6
        for index, matcher in enumerate(("retrieval", "llm")):
            assert calls[index * 3 + 2] == ["-m", "src.kg.align_match", "run", "--matcher", matcher,
                "--target", "agrovoc", "--out", f"results/v5/alignment/agrovoc_{matcher}"]
        from scripts.make_gpu_bundle import bundle_files
        files = set(bundle_files())
        assert align_match.INPUTS in files
        assert align_match.PROMPT in files
        assert align_match.AGROVOC_INPUTS in files
        assert align_match.AGROVOC_PROMPT in files
        # Test the actual archive writer without generating a large project artifact.
        import zipfile
        from scripts import make_gpu_bundle
        archive = folder / "bundle.zip"
        archive_sources = [align_match.INPUTS, align_match.PROMPT,
                           align_match.AGROVOC_INPUTS, align_match.AGROVOC_PROMPT]
        with patch.object(make_gpu_bundle, "OUT", archive), patch.object(
                make_gpu_bundle, "bundle_files", return_value=iter(archive_sources)):
            make_gpu_bundle.main()
        with zipfile.ZipFile(archive) as zipped:
            assert "data/interim/align_inputs_hcat.json" in zipped.namelist()
            assert zipped.read("configs/align_prompt_hcat.md") == align_match.PROMPT.read_bytes()
            assert zipped.read("data/interim/align_inputs_agrovoc.json") == align_match.AGROVOC_INPUTS.read_bytes()
            assert zipped.read("configs/align_prompt_agrovoc.md") == align_match.AGROVOC_PROMPT.read_bytes()
        assert align_match.HCAT_GOLD not in files
        assert align_eval.AGROVOC_GOLD not in files
        print("  bash -n, session-only install, ALIGN variables, output override and bundle membership pass")


if __name__ == "__main__":
    started = time.perf_counter()
    test_inputs()
    test_agrovoc_inputs()
    test_agrovoc_target_fixture()
    test_agrovoc_parsing_and_score()
    test_hcat_byte_compatibility()
    test_stub_runner_and_score()
    test_config_lock()
    test_component_adapters()
    test_no_cuda_and_parsing()
    test_gpu_step_and_bundle()
    print(f"test_align_match: all checks passed ({time.perf_counter() - started:.2f}s)")
