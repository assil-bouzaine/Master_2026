"""Offline checks for the Track 2 passage builder, prompt, split and LLM runner (v5 plan R2.1).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_extract_llm

Uses a toy Python stub generator on CPU; no LLM is downloaded or executed.
"""
import copy
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from src.config import ROOT
from src.kg import extract_eval
from src.kg.extract_llm import (
    DEV_STATEMENT_PAGES,
    PASSAGES_PATH,
    PROMPT_PATH,
    SCHEMA_PATH,
    SPLIT_PATH,
    format_code_table,
    load_passages,
    load_split,
    messages,
    parse_answer,
    read_code_tables,
    run_extraction,
    score_split,
    write_passages_and_split,
)
from src.kg.extract_passages import MAX_PASSAGE_CHARS, build_passages, norm


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def test_passages_and_gold_quotes():
    passages = build_passages()
    assert len(passages) == 66, len(passages)
    assert all(len(p["text"]) <= MAX_PASSAGE_CHARS for p in passages)
    assert len({p["passage_id"] for p in passages}) == len(passages)

    by_doc_page = {}
    for p in passages:
        by_doc_page.setdefault((p["document"], p["page"]), []).append(p["text"])

    gold = extract_eval.load_gold()
    assert len(gold) == 32
    missing = []
    for item in gold:
        texts = by_doc_page.get((item["document"], item["page"]), [])
        if not any(norm(item["quote"]) in text for text in texts):
            missing.append(item["id"])
    assert not missing, f"Gold quotes missing from passages: {missing}"
    print(f"  1. all 32 gold quotes occur verbatim (after norm) in their {len(passages)} passages")


def test_split_and_determinism():
    gold = extract_eval.load_gold()
    dev_pages = set(DEV_STATEMENT_PAGES)
    expected_dev_gold = sorted(g["id"] for g in gold if (g["document"], g["page"]) in dev_pages)
    expected_eval_gold = sorted(g["id"] for g in gold if (g["document"], g["page"]) not in dev_pages)
    assert len(expected_dev_gold) == 10 and len(expected_eval_gold) == 22
    dev_mechs = Counter(g["mechanism"] for g in gold if (g["document"], g["page"]) in dev_pages)
    assert dev_mechs == {"RiverExchange": 6, "CanalReturnFlow": 4}, dev_mechs

    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        p1, s1 = tmp / "p1.jsonl", tmp / "s1.json"
        p2, s2 = tmp / "p2.jsonl", tmp / "s2.json"
        passages, split_data = write_passages_and_split(p1, s1)
        write_passages_and_split(p2, s2)
        assert p1.read_bytes() == p2.read_bytes(), "passages JSONL is not byte-identical across runs"
        assert s1.read_bytes() == s2.read_bytes(), "split JSON is not byte-identical across runs"

        # Verify committed/generated artifacts match a fresh build.
        assert PASSAGES_PATH.read_bytes() == p1.read_bytes(), "data/interim passages file is stale"
        assert SPLIT_PATH.read_bytes() == s1.read_bytes(), "configs/extraction_split_track2.json is stale"

    assert split_data["gold_ids"]["dev"] == expected_dev_gold
    assert split_data["gold_ids"]["eval"] == expected_eval_gold
    assert set(split_data["passages"]) == {p["passage_id"] for p in passages}
    assert set(split_data["passages"].values()) == {"dev", "eval"}

    gold_pages = {(g["document"], g["page"]) for g in gold}
    for p in passages:
        loc = (p["document"], p["page"])
        assigned = split_data["passages"][p["passage_id"]]
        if loc in dev_pages:
            assert assigned == "dev"
        elif loc in gold_pages:
            assert assigned == "eval"
        else:
            assert assigned == ("dev" if p["physical_index"] % 4 == 0 else "eval")
    n_dev = sum(v == "dev" for v in split_data["passages"].values())
    n_eval = sum(v == "eval" for v in split_data["passages"].values())
    assert n_dev + n_eval == len(passages)
    print(f"  2. split verified (dev: 10 gold / {n_dev} passages, eval: 22 gold / {n_eval} passages) and byte-identical")


def test_prompt_and_code_tables():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    props = schema["items"]["properties"]
    unit_codes = props["units"]["items"]["enum"]
    wc_codes = props["watercourses"]["items"]["enum"]

    live_tables = read_code_tables()
    split_data = load_split()
    assert split_data["code_tables"] == live_tables, "split code_tables differ from project tables"

    units_md = format_code_table(live_tables["units"], "Code", "BD LISA name")
    wc_md = format_code_table(live_tables["watercourses"], "Code", "Watercourse name")
    template = PROMPT_PATH.read_text(encoding="utf-8")

    # Passage with braces tests literal substitution without str.format failure.
    sample = {"text": "Passage de test avec {accolades} et accents été."}
    msgs = messages(sample)
    assert len(msgs) == 2 and msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert sample["text"] in msgs[1]["content"]
    for code in unit_codes:
        assert code in msgs[0]["content"], f"unit code {code} missing from system message"
    for code in wc_codes:
        assert code in msgs[0]["content"], f"watercourse code {code} missing from system message"
    for field in ("mechanism", "direction", "hedging", "method", "subject"):
        for value in props[field]["enum"]:
            assert value in msgs[0]["content"], f"enum value {field}={value} missing from system message"

    # No gold quote (normalised) may appear in the template or code tables.
    haystacks = (
        norm(template),
        extract_eval.normalize_quote(template),
        norm(units_md),
        extract_eval.normalize_quote(units_md),
        norm(wc_md),
        extract_eval.normalize_quote(wc_md),
        norm(msgs[0]["content"]),
        extract_eval.normalize_quote(msgs[0]["content"]),
    )
    for item in extract_eval.load_gold():
        q_norm = norm(item["quote"])
        q_eval = extract_eval.normalize_quote(item["quote"])
        for hay in haystacks:
            assert q_norm not in hay and q_eval not in hay, f"Gold quote leaked into prompt: {item['id']}"
    print("  3. prompt holds passage verbatim, all schema codes/enums, and zero gold quotes")


def test_answer_parsing():
    passage = {"passage_id": "sierm-frdg351:p002", "document": "sierm-frdg351", "page": "3"}
    raw_item = {
        "document": "wrong-doc",
        "page": "999",
        "quote": "Un extrait.",
        "mechanism": "RiverExchange",
        "direction": "aquifer_to_surface",
        "hedging": "stated",
        "method": "synthesis",
        "subject": "aggregate",
        "units": ["671AB01"],
        "watercourses": ["Y06-0400"],
    }

    fenced = f"```json\n{json.dumps([raw_item], ensure_ascii=False)}\n```"
    items, err = parse_answer(fenced, passage)
    assert err is None and len(items) == 1
    assert items[0]["document"] == "sierm-frdg351" and items[0]["page"] == "3"

    bare = json.dumps([{k: v for k, v in raw_item.items() if k not in ("document", "page")}])
    items, err = parse_answer(bare, passage)
    assert err is None and len(items) == 1
    assert items[0]["document"] == "sierm-frdg351" and items[0]["page"] == "3"

    items, err = parse_answer("[]", passage)
    assert err is None and items == []

    items, err = parse_answer("```\n[]\n```", passage)
    assert err is None and items == []

    for bad in ("not json at all", "[{broken", '{"quote": "an object"}', "null", "[NaN]"):
        items, err = parse_answer(bad, passage)
        assert items is None and err is not None, f"Bad payload accepted: {bad!r}"
    print("  4. parsing handles fenced/bare arrays, [], invalid JSON, objects, and document/page overwrite")


def test_stub_pipeline_and_resumability():
    passages = load_passages()
    split_data = load_split()
    gold = extract_eval.load_gold()
    dev_gold_by_text = {}
    for p in passages:
        if split_data["passages"][p["passage_id"]] != "dev":
            continue
        page_gold = [
            {k: v for k, v in copy.deepcopy(g).items() if k not in ("id", "document", "page")}
            for g in gold
            if (g["document"], g["page"]) == (p["document"], p["page"])
        ]
        dev_gold_by_text[p["text"]] = page_gold

    calls = []

    def perfect_stub(msgs):
        calls.append(msgs)
        user_msg = msgs[1]["content"]
        for text, items in dev_gold_by_text.items():
            if text in user_msg and items:
                return f"```json\n{json.dumps(items, ensure_ascii=False)}\n```"
        return "[]"

    with tempfile.TemporaryDirectory() as directory:
        out_perfect = Path(directory) / "perfect"
        pred_path, meta = run_extraction(
            "stub/perfect",
            "dev",
            out_perfect,
            revision="stub-rev-1",
            chat_template_kwargs={"enable_thinking": False},
            generator=perfect_stub,
        )
        n_dev = sum(v == "dev" for v in split_data["passages"].values())
        assert len(calls) == n_dev
        assert meta["n_passages"] == n_dev and meta["n_predictions"] == 10
        assert meta["parse_failures"] == []
        assert meta["decoding"] == {"do_sample": False, "max_new_tokens": 4096}
        assert meta["chat_template_kwargs"] == {"enable_thinking": False}
        assert set(meta["sha256"]) == {"prompt_template", "schema", "split", "passages"}
        assert len(meta["per_passage_seconds"]) == n_dev
        assert meta["versions"]["transformers"] and meta["versions"]["torch"]

        # Score via CLI subprocess to exercise the full CLI path.
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PFE_DATASET": "v5"}
        proc = subprocess.run(
            [sys.executable, "-m", "src.kg.extract_llm", "score", "--pred", str(pred_path), "--split", "dev"],
            cwd=ROOT, env=env, text=True, capture_output=True, encoding="utf-8", check=True,
        )
        report_path = out_perfect / "score_dev.md"
        assert report_path.is_file() and report_path.read_text(encoding="utf-8") == proc.stdout
        result, _, _ = score_split(pred_path, "dev")
        assert result["counts"]["gold"] == 10 and result["counts"]["matched"] == 10
        assert result["counts"]["strict_matches"] == 10
        for group in ("statement", "strict"):
            for metric in ("precision", "recall", "f1"):
                close(result[group][metric], 1.0)

        # Resumability: a second run with the same out_dir calls the stub 0 times and writes nothing new.
        raw_dir = out_perfect / "raw"
        before_raw = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in raw_dir.iterdir()}
        second_calls = []

        def fail_if_called(msgs):
            second_calls.append(msgs)
            raise AssertionError("Stub should not be called when resuming completed passages")

        pred_path_2, meta_2 = run_extraction("stub/perfect", "dev", out_perfect, generator=fail_if_called)
        after_raw = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in raw_dir.iterdir()}
        assert not second_calls and before_raw == after_raw
        assert pred_path_2.read_bytes() == pred_path.read_bytes()
        assert meta_2["per_passage_seconds"] == meta["per_passage_seconds"]

        # Extra invented item on a dev page lowers precision to 10/11 while keeping recall = 1.
        injected = False

        def extra_stub(msgs):
            nonlocal injected
            raw = perfect_stub(msgs)
            if not injected and raw != "[]":
                injected = True
                arr = json.loads(raw.split("\n", 1)[1].rsplit("\n", 1)[0])
                invented = copy.deepcopy(arr[0])
                invented["quote"] = "Phrase inventée sans rapport avec le passage source."
                arr.append(invented)
                return json.dumps(arr, ensure_ascii=False)
            return raw

        out_extra = Path(directory) / "extra"
        pred_extra, _ = run_extraction("stub/extra", "dev", out_extra, generator=extra_stub)
        res_extra, _, _ = score_split(pred_extra, "dev")
        assert res_extra["counts"]["matched"] == 10 and res_extra["counts"]["predictions"] == 11
        close(res_extra["statement"]["precision"], 10 / 11)
        close(res_extra["statement"]["recall"], 1.0)
        close(res_extra["statement"]["f1"], 20 / 21)

        # Parse failure on one passage is recorded in run.json and contributes no items.
        first_fail = True

        def broken_once_stub(msgs):
            nonlocal first_fail
            if first_fail:
                first_fail = False
                return '{"not": "an array"}'
            return "[]"

        out_fail = Path(directory) / "parse_fail"
        _, meta_fail = run_extraction("stub/fail", "dev", out_fail, generator=broken_once_stub)
        assert len(meta_fail["parse_failures"]) == 1 and meta_fail["n_predictions"] == 0

    print("  5. stub pipeline (perfect P=R=F1=1, extra item P=10/11, parse failure, resumability) passes")


def test_refuses_without_cuda():
    import torch
    if torch.cuda.is_available():
        print("  6. skipped no-CUDA guard test because CUDA is available on this machine")
        return

    with tempfile.TemporaryDirectory() as directory:
        out_dir = Path(directory) / "no_cuda"
        try:
            run_extraction("Qwen/Qwen2.5-7B-Instruct", "dev", out_dir)
        except RuntimeError as error:
            assert "runs on a Colab GPU" in str(error), str(error)
        else:
            raise AssertionError("run_extraction succeeded without CUDA and without a stub")

        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PFE_DATASET": "v5"}
        proc = subprocess.run(
            [
                sys.executable, "-m", "src.kg.extract_llm", "run",
                "--model", "Qwen/Qwen2.5-7B-Instruct",
                "--split", "dev",
                "--out", str(out_dir),
            ],
            cwd=ROOT, env=env, text=True, capture_output=True, encoding="utf-8",
        )
        assert proc.returncode != 0 and "runs on a Colab GPU" in proc.stderr, (proc.returncode, proc.stderr)
    print("  6. run without CUDA and without a stub refuses with 'runs on a Colab GPU'")


if __name__ == "__main__":
    started = time.perf_counter()
    test_passages_and_gold_quotes()
    test_split_and_determinism()
    test_prompt_and_code_tables()
    test_answer_parsing()
    test_stub_pipeline_and_resumability()
    test_refuses_without_cuda()
    print(f"test_extract_llm: all checks passed ({time.perf_counter() - started:.2f}s)")
