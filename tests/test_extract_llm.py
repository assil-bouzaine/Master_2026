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

import pandas as pd

from src.config import DATASET_DIR, ROOT
from src.kg import extract_eval
from src.kg.extract_llm import (
    DEV_STATEMENT_PAGES,
    PASSAGES_PATH,
    PROMPT_PATH,
    SCHEMA_PATH,
    SPLIT_PATH,
    build_split,
    format_code_table,
    format_watercourses_table,
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
from src.kg.rivers import snapshot


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def _snapshot_tree(root):
    return {
        str(p.relative_to(root)): (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(Path(root).rglob("*"))
        if p.is_file()
    }


def test_passages_and_gold_quotes():
    passages = build_passages()
    assert len(passages) == 66, len(passages)
    assert all(len(p["text"]) <= MAX_PASSAGE_CHARS for p in passages)
    assert len({p["passage_id"] for p in passages}) == len(passages)

    # Every (document, page) key must be unique and no passage may retain the raw '?' label.
    keys = [(p["document"], p["page"]) for p in passages]
    assert len(set(keys)) == len(passages), "Duplicate (document, page) pairs found"
    assert all(p["page"] != "?" for p in passages), "Raw '?' page label leaked into passages"

    by_id = {p["passage_id"]: p for p in passages}
    expected_unnumbered = {
        "brgm-rp-71486-fr:p000": "unnumbered p000",
        "brgm-rp-71486-fr:p001": "unnumbered p001",
        "brgm-rp-71486-fr:p002": "unnumbered p002",
        "brgm-rp-71486-fr:p049": "unnumbered p049",
    }
    for pid, expected_label in expected_unnumbered.items():
        assert by_id[pid]["page"] == expected_label, (pid, by_id[pid]["page"], expected_label)
    actual_unnumbered = [p["passage_id"] for p in passages if p["page"].startswith("unnumbered ")]
    assert actual_unnumbered == sorted(expected_unnumbered), actual_unnumbered

    # build_split refuses duplicate (document, page) keys.
    dup_passages = copy.deepcopy(passages)
    dup_passages[1]["page"] = dup_passages[0]["page"]
    try:
        build_split(dup_passages)
    except ValueError as error:
        assert "Duplicate (document, page)" in str(error), str(error)
    else:
        raise AssertionError("build_split accepted duplicate (document, page) keys")

    by_doc_page = {(p["document"], p["page"]): p["text"] for p in passages}
    gold = extract_eval.load_gold()
    assert len(gold) == 32
    missing = [
        item["id"]
        for item in gold
        if norm(item["quote"]) not in by_doc_page.get((item["document"], item["page"]), "")
    ]
    assert not missing, f"Gold quotes missing from passages: {missing}"
    print(f"  1. {len(passages)} unique (document, page) passages (4 unnumbered BRGM labels), all 32 gold quotes found")


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

    dev_page_set = {(e["document"], e["page"]) for e in split_data["pages"]["dev"]}
    eval_page_set = {(e["document"], e["page"]) for e in split_data["pages"]["eval"]}
    assert not (dev_page_set & eval_page_set), f"Overlap between dev and eval pages: {dev_page_set & eval_page_set}"
    assert len(dev_page_set) + len(eval_page_set) == len(passages)

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

    # Independently rebuild expected watercourse rows from BD TOPO and Hub'Eau gauge tables.
    reaches = pd.read_parquet(
        snapshot("bdtopo_hydro") / "troncon_hydrographique.parquet",
        columns=["code_du_cours_d_eau_bdcarthage", "cpx_toponyme_de_cours_d_eau"],
    )
    gauges = pd.read_parquet(
        DATASET_DIR / "gauges.parquet",
        columns=["code_cours_eau", "libelle_cours_eau"],
    )
    expected_rows = ["| Code | BD TOPO name | Hub'Eau name |", "|---|---|---|"]
    non_empty_hubeau = []
    for code in wc_codes:
        bd = reaches.loc[reaches["code_du_cours_d_eau_bdcarthage"] == code, "cpx_toponyme_de_cours_d_eau"]
        bd = bd.dropna().astype(str).str.strip()
        bd = bd[bd != ""]
        bd_name = sorted(bd.mode().tolist())[0] if len(bd) else ""

        hb = gauges.loc[gauges["code_cours_eau"] == code, "libelle_cours_eau"]
        hb = hb.dropna().astype(str).str.strip()
        hb = hb[hb != ""]
        hb_name = sorted(hb.mode().tolist())[0] if len(hb) else ""
        if hb_name:
            non_empty_hubeau.append(code)

        assert live_tables["watercourses"][code] == {"bdtopo": bd_name, "hubeau": hb_name}
        expected_rows.append(f"| {code} | {bd_name} | {hb_name} |")

    assert len(non_empty_hubeau) == 7 and "Y0470560" not in non_empty_hubeau, non_empty_hubeau
    assert live_tables["watercourses"]["Y0470560"]["hubeau"] == ""
    assert live_tables["watercourses"]["Y0470560"]["bdtopo"] != ""

    units_md = format_code_table(live_tables["units"], "Code", "BD LISA name")
    wc_md = format_watercourses_table(live_tables["watercourses"])
    assert wc_md == "\n".join(expected_rows), (wc_md, "\n".join(expected_rows))
    assert f"| Y0470560 | {live_tables['watercourses']['Y0470560']['bdtopo']} |  |" in wc_md.splitlines()

    template = PROMPT_PATH.read_text(encoding="utf-8")

    # Passage with braces tests literal substitution without str.format failure.
    sample = {"text": "Passage de test avec {accolades} et accents été."}
    msgs = messages(sample)
    assert len(msgs) == 2 and msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert sample["text"] in msgs[1]["content"]
    assert wc_md in msgs[0]["content"]
    assert units_md in msgs[0]["content"]
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
    print("  3. prompt holds 3-column watercourse table (7 gauged + empty Y0470560), all codes/enums, zero gold quotes")


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

    # Empty and non-empty leading <think>...</think> blocks are removed before fence/JSON parsing.
    items, err = parse_answer(f"<think></think>\n{bare}", passage)
    assert err is None and len(items) == 1 and items[0]["quote"] == "Un extrait."

    items, err = parse_answer(f"  <think>\n\n</think>\n\n{fenced}", passage)
    assert err is None and len(items) == 1 and items[0]["document"] == "sierm-frdg351"

    items, err = parse_answer(f"<think>Je vérifie le passage.\nDeuxième ligne.</think>\n{fenced}", passage)
    assert err is None and len(items) == 1 and items[0]["page"] == "3"

    items, err = parse_answer("<think>Aucun échange mentionné.</think> []", passage)
    assert err is None and items == []

    # A <think> block in the middle of a quote is preserved; in the middle of JSON it is NOT removed.
    mid_quote_item = {**raw_item, "quote": "Avant <think>milieu</think> après."}
    items, err = parse_answer(json.dumps([mid_quote_item], ensure_ascii=False), passage)
    assert err is None and items[0]["quote"] == "Avant <think>milieu</think> après."

    for bad in (
        "not json at all",
        "[{broken",
        '{"quote": "an object"}',
        "null",
        "[NaN]",
        "[\n<think>middle</think>\n]",
        "<think>first</think>\n<think>second</think>\n[]",
        "[]\n<think>trailing</think>",
    ):
        items, err = parse_answer(bad, passage)
        assert items is None and err is not None, f"Bad payload accepted: {bad!r}"
    print("  4. parsing handles fenced/bare arrays, leading think blocks (empty/non-empty), mid-text preservation, errors")


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
        idx = len(calls)
        calls.append(msgs)
        user_msg = msgs[1]["content"]
        for text, items in dev_gold_by_text.items():
            if text in user_msg and items:
                prefix = "<think>Checking exchange statements.</think>\n" if idx % 2 == 0 else ""
                return f"{prefix}```json\n{json.dumps(items, ensure_ascii=False)}\n```"
        if idx == 0:
            return "<think></think>\n[]"
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
        assert meta["n_think_blocks"] >= 1, meta["n_think_blocks"]
        assert meta["decoding"] == {"do_sample": False, "max_new_tokens": 4096}
        assert meta["chat_template_kwargs"] == {"enable_thinking": False}
        assert set(meta["sha256"]) == {"prompt_template", "schema", "split", "passages"}
        assert len(meta["per_passage_seconds"]) == n_dev
        assert meta["versions"]["transformers"] and meta["versions"]["torch"]

        config_path = out_perfect / "config.json"
        assert config_path.is_file()
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_config["model"] == "stub/perfect"
        assert saved_config["requested_revision"] == "stub-rev-1"
        assert saved_config["dtype"] == "bfloat16"
        assert saved_config["max_new_tokens"] == 4096
        assert saved_config["chat_template_kwargs"] == {"enable_thinking": False}
        assert saved_config["split"] == "dev"
        assert saved_config["sha256"] == meta["sha256"]

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

        # Resume with a changed model id is refused and writes nothing.
        second_calls = []

        def fail_if_called(msgs):
            second_calls.append(msgs)
            raise AssertionError("Stub should not be called when resuming or refusing")

        before_tree = _snapshot_tree(out_perfect)
        try:
            run_extraction(
                "stub/other-model",
                "dev",
                out_perfect,
                revision="stub-rev-1",
                chat_template_kwargs={"enable_thinking": False},
                generator=fail_if_called,
            )
        except ValueError as error:
            assert "model" in str(error), str(error)
        else:
            raise AssertionError("Resume with changed model id was not refused")
        assert not second_calls
        assert _snapshot_tree(out_perfect) == before_tree, "Refused resume modified files on disk"

        # Resume with changed dtype/revision is also refused and names those fields.
        try:
            run_extraction(
                "stub/perfect",
                "dev",
                out_perfect,
                revision="stub-rev-2",
                dtype="float16",
                chat_template_kwargs={"enable_thinking": False},
                generator=fail_if_called,
            )
        except ValueError as error:
            msg = str(error)
            assert "requested_revision" in msg and "dtype" in msg, msg
        else:
            raise AssertionError("Resume with changed revision/dtype was not refused")
        assert _snapshot_tree(out_perfect) == before_tree

        # Resume with identical config calls the stub 0 times and leaves raw/ and config.json untouched.
        raw_dir = out_perfect / "raw"
        before_raw = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in raw_dir.iterdir()}
        before_cfg = (config_path.stat().st_mtime_ns, config_path.read_bytes())

        pred_path_2, meta_2 = run_extraction(
            "stub/perfect",
            "dev",
            out_perfect,
            revision="stub-rev-1",
            chat_template_kwargs={"enable_thinking": False},
            generator=fail_if_called,
        )
        after_raw = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in raw_dir.iterdir()}
        assert not second_calls and before_raw == after_raw
        assert (config_path.stat().st_mtime_ns, config_path.read_bytes()) == before_cfg
        assert pred_path_2.read_bytes() == pred_path.read_bytes()
        assert meta_2["per_passage_seconds"] == meta["per_passage_seconds"]
        assert meta_2["n_think_blocks"] == meta["n_think_blocks"]

        # Extra invented item on a dev page lowers precision to 10/11 while keeping recall = 1.
        injected = False

        def extra_stub(msgs):
            nonlocal injected
            raw = perfect_stub(msgs)
            if not injected and "```json" in raw:
                injected = True
                fenced_part = raw.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
                arr = json.loads(fenced_part)
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

    print("  5. stub pipeline (P=R=F1=1, think count, config lock on resume, extra item, parse failure) passes")


def test_scoring_guards():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PFE_DATASET": "v5"}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)

        # 1. A dev predictions file scored with --split eval is refused (via run.json and config.json).
        dev_dir = tmp / "dev_run"
        pred_dev, _ = run_extraction("stub/empty", "dev", dev_dir, generator=lambda msgs: "[]")
        try:
            score_split(pred_dev, "eval")
        except ValueError as error:
            assert "dev" in str(error) and "eval" in str(error), str(error)
        else:
            raise AssertionError("score_split accepted a dev run when scoring --split eval")
        assert not (dev_dir / "score_eval.md").exists()

        proc = subprocess.run(
            [sys.executable, "-m", "src.kg.extract_llm", "score", "--pred", str(pred_dev), "--split", "eval"],
            cwd=ROOT, env=env, text=True, capture_output=True, encoding="utf-8",
        )
        assert proc.returncode != 0 and "dev" in proc.stderr, (proc.returncode, proc.stderr)
        assert not (dev_dir / "score_eval.md").exists()

        # Also check config.json alone (without run.json).
        (dev_dir / "run.json").unlink()
        try:
            score_split(pred_dev, "eval")
        except ValueError as error:
            assert "config.json" in str(error), str(error)
        else:
            raise AssertionError("score_split ignored config.json split mismatch")

        # 2. A prediction on an eval page inside a dev predictions file is refused and listed.
        mixed_dir = tmp / "mixed_pages"
        mixed_dir.mkdir()
        eval_item = {
            "document": "brgm-rp-71486-fr",
            "page": "25",
            "quote": "Extrait sur une page eval.",
            "mechanism": "RiverExchange",
            "direction": "surface_to_aquifer",
            "hedging": "stated",
            "method": "synthesis",
            "subject": "unit",
            "units": ["671AB02"],
            "watercourses": ["Y04-0400"],
        }
        mixed_pred = mixed_dir / "predictions_dev.json"
        mixed_pred.write_text(json.dumps([eval_item], ensure_ascii=False), encoding="utf-8")
        try:
            score_split(mixed_pred, "dev")
        except ValueError as error:
            msg = str(error)
            assert "brgm-rp-71486-fr" in msg and "'25'" in msg, msg
        else:
            raise AssertionError("score_split silently dropped an eval-page prediction when scoring dev")
        assert not (mixed_dir / "score_dev.md").exists()

    print("  6. scoring guards refuse cross-split runs and predictions on pages outside the split")


def test_refuses_without_cuda():
    import torch
    if torch.cuda.is_available():
        print("  7. skipped no-CUDA guard test because CUDA is available on this machine")
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
    print("  7. run without CUDA and without a stub refuses with 'runs on a Colab GPU'")


if __name__ == "__main__":
    started = time.perf_counter()
    test_passages_and_gold_quotes()
    test_split_and_determinism()
    test_prompt_and_code_tables()
    test_answer_parsing()
    test_stub_pipeline_and_resumability()
    test_scoring_guards()
    test_refuses_without_cuda()
    print(f"test_extract_llm: all checks passed ({time.perf_counter() - started:.2f}s)")
