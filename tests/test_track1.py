"""Offline paper passages, runner and human-review checks (v5 plan R2.1, Track 1).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_track1

Two temporary PDFs exercise real pdftotext. All model answers come from CPU stubs.
"""
import copy
import csv
import hashlib
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import load_workbook

from src.kg import extract_llm as E
from src.kg import extract_passages as P
from src.kg import track1_review as R


def refuses(call, contains):
    try:
        call()
    except ValueError as error:
        assert contains in str(error), str(error)
    else:
        raise AssertionError(f"Expected refusal containing {contains!r}")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def harvest(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("order", "openalex_id", "download_status", "title", "doi"))
        writer.writeheader()
        writer.writerows({"order": order, "openalex_id": f"https://openalex.org/W{order}",
                         "download_status": status, "title": f"Paper {order}", "doi": ""}
                        for order, status in rows)
    return path


def pdf(path, texts):
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure

    with PdfPages(path) as output:
        for text in texts:
            figure = Figure(figsize=(8, 10))
            if text:
                figure.text(0.1, 0.9, text, va="top")
            output.savefig(figure)


def test_paper_passages():
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        papers = harvest(tmp / "papers.csv", [(4, "downloaded"), (1, "failed"), (2, "downloaded")])
        pdf(tmp / "W2.pdf", ["References in a sentence do not cut this page.", "",
                             "Last causal sentence.\nReferences\nNever keep this citation.",
                             "Never keep this later page."])
        pdf(tmp / "W4.pdf", ["" if i == 2 else f"Body on physical page {i}." for i in range(1, 23)])
        p1, s1 = tmp / "passages.jsonl", tmp / "split.json"
        passages, split = E.write_paper_passages_and_split(p1, s1, papers_path=papers, pdf_dir=tmp)
        assert split["pilot_documents"] == ["W2", "W4"]
        assert split["pages_kept"] == {"W2": 2, "W4": 19}
        first = [p for p in passages if p["document"] == "W2"]
        assert [p["page"] for p in first] == ["1", "3"]
        assert [p["passage_id"] for p in first] == ["W2:p001", "W2:p003"]
        assert first[1]["text"] == "Last causal sentence."
        assert all("Never keep" not in p["text"] for p in passages)
        assert passages[-1]["page"] == "20"
        for p in passages:
            assert p["text"] == P.norm(p["text"])
            assert p["sha256"] == hashlib.sha256(p["text"].encode("utf-8")).hexdigest()
            assert set(p) == {"passage_id", "document", "page", "order", "text", "sha256"}
        before = (p1.read_bytes(), s1.read_bytes())
        E.write_paper_passages_and_split(p1, s1, papers_path=papers, pdf_dir=tmp)
        assert before == (p1.read_bytes(), s1.read_bytes())
        # Every allowed heading cuts before normalisation. An empty heading page is dropped.
        for heading in ("References", "REFERENCES", "Bibliography", "Références",
                        "Literature cited", "Literature Cited"):
            with patch.object(P.subprocess, "run", return_value=SimpleNamespace(
                    stdout=f"Body with References inside a line.\f  {heading}  \nCitation\fLater\f")) as run:
                kept = P.build_paper_passages(papers, tmp)
                assert len(kept) == 2 and all(p["page"] == "1" for p in kept)
                assert all(call.args[0][:2] == ["pdftotext", "-layout"] for call in run.call_args_list)
        # More failed/late papers do not displace the first two successful downloads.
        papers = harvest(papers, [(6, "downloaded"), (4, "downloaded"), (1, "failed"),
                                  (2, "downloaded"), (3, "failed")])
        split = E.build_paper_split(passages + [dict(passages[0], document="W6", passage_id="W6:p001", order=6)],
                                    P.downloaded_papers(papers))
        assert split["pilot_documents"] == ["W2", "W4"] and split["passages"]["W6:p001"] == "main"
    print("  1. real PDFs: references cut, physical page ids, blank dropped, 20-page cap, deterministic bytes; split order")


def fixture(tmp):
    papers = [{"document": f"W{i}", "order": i, "title": f"Paper {i}", "doi": ""} for i in (2, 4, 6)]
    passages = [{"passage_id": f"W{i}:p001", "document": f"W{i}", "page": "1", "order": i,
                 "text": f"Paper {i}: pumping lowers groundwater levels.", "sha256": "fixture"} for i in (2, 4, 6)]
    split = E.build_paper_split(passages, papers)
    passages_path = tmp / "passages.jsonl"
    passages_path.write_text("".join(json.dumps(p) + "\n" for p in passages), encoding="utf-8")
    split_path = write_json(tmp / "split.json", split)
    return passages_path, split_path


def statement(**kwargs):
    return {"driver": "pumping", "driver_category": "groundwater_abstraction",
            "effect": "groundwater levels", "effect_category": "groundwater_level",
            "polarity": "decreases", "evidence_type": "measured", "place": "", "quote": "=literal quote",
            **kwargs}


def test_runner():
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        passages, split = fixture(tmp)
        inputs = {"passages_path": passages, "split_path": split}
        calls = []

        def generate(msgs):
            calls.append(msgs)
            assert "BD LISA" not in msgs[0]["content"]
            assert "{passage}" not in msgs[1]["content"]
            return '<think>Reasoning</think>\n```json\n' + json.dumps([statement(document="bad", page="bad")]) + '\n```'

        for role, expected in (("pilot", ["W2", "W4"]), ("main", ["W6"]), ("all", ["W2", "W4", "W6"])):
            out = tmp / role
            pred, meta = E.run_extraction("stub/track1", role, out, track=1, generator=generate, **inputs)
            payload = json.loads(pred.read_text())
            assert [p["document"] for p in payload] == expected and all(p["page"] == "1" for p in payload)
            assert meta["track"] == 1 and meta["n_think_blocks"] == len(expected)
            assert meta["parse_failures"] == [] and meta["decoding"]["do_sample"] is False
            config = json.loads((out / "config.json").read_text())
            assert config["track"] == 1
            assert config["sha256"]["schema"] == E._sha256_file(E.TRACK1_SCHEMA_PATH)
            assert config["sha256"]["prompt_template"] == E._sha256_file(E.TRACK1_PROMPT_PATH)
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (out / "raw").iterdir()}
            count = len(calls)
            again, _ = E.run_extraction("stub/track1", role, out, track=1, generator=generate, **inputs)
            assert len(calls) == count and again.read_bytes() == pred.read_bytes()
            assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (out / "raw").iterdir()}
        # Give both modes identical paths and split, so only track can break the lock.
        dual = json.loads(split.read_text())
        dual["code_tables"] = {"units": {}, "watercourses": {}}
        write_json(split, dual)
        paths = {**inputs, "prompt_path": E.PROMPT_PATH, "schema_path": E.SCHEMA_PATH}
        for old, new in ((1, 2), (2, 1)):
            out = tmp / f"lock{old}"
            E.run_extraction("stub/lock", "all", out, track=old, generator=lambda _: "[]", **paths)
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in out.rglob("*") if p.is_file()}
            refuses(lambda: E.run_extraction("stub/lock", "all", out, track=new,
                                             generator=lambda _: "[]", **paths), "track")
            assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in out.rglob("*") if p.is_file()}
        refuses(lambda: E.run_extraction("stub", "dev", tmp / "bad", track=1, generator=generate), "split")
        refuses(lambda: E.run_extraction("stub", "main", tmp / "bad", generator=generate), "split")
        # CLI dispatch without loading a model or writing project artifacts.
        with patch.object(E, "run_extraction", return_value=(tmp / "pred.json", meta)) as run:
            E.main(["run", "--track", "1", "--split", "main", "--model", "stub", "--out", str(tmp)])
            assert run.call_args.kwargs["track"] == 1
        with patch.object(E, "write_paper_passages_and_split", return_value=([], dual)) as build:
            E.main(["passages", "--track", "1"])
            build.assert_called_once()
    print("  2. Track 1 runner: pilot/main/all, source override, parsing, caching, track lock in both directions, CLI")


def test_review():
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        _, split = fixture(tmp)
        # Scrambled paper order, duplicate statements and an invalid item.
        payload = [statement(document="W6", page="1"), statement(document="W2", page="1"),
                   statement(document="W6", page="1"),
                   statement(document="W6", page="1", driver_category="drought_or_climate",
                             effect_category="groundwater_recharge", evidence_type="modelled"),
                   statement(document="W4", page="1"), {"driver": "invalid"}]
        pred = write_json(tmp / "pred.json", payload)
        book_path = tmp / "review.xlsx"
        out, count, invalid = R.worksheet(pred, book_path, split_path=split)
        assert count == 5 and len(invalid) == 1
        before = out.read_bytes()
        refuses(lambda: R.worksheet(pred, book_path, split_path=split), "--force")
        assert before == out.read_bytes()
        book = load_workbook(out)
        assert book.sheetnames == ["Guide", "Statements"]
        sheet = book["Statements"]
        assert tuple(cell.value for cell in sheet[1]) == R.HEADERS
        assert [sheet.cell(i, 2).value for i in range(2, 7)] == ["Paper 2", "Paper 4", "Paper 6", "Paper 6", "Paper 6"]
        assert sheet["E2"].data_type == "s" and sheet["E2"].value == "=literal quote"
        assert sheet["P2"].value == "pilot" and sheet["P4"].value == "main"
        assert len(sheet.data_validations.dataValidation) == 2
        assert all(v.errorStyle == "stop" for v in sheet.data_validations.dataValidation)
        # Pilot: 2 accepts. Main: accept, reject, blank -> rate 1/2, unjudged share 1/3.
        for i in (2, 3, 4):
            sheet.cell(i, 13, "accept")
        sheet.cell(5, 13, "reject")
        sheet.cell(5, 14, "wrong_polarity")
        sheet.cell(5, 15, "A reason, with a comma\nand newline")
        book.save(out)
        csv_path, _ = R.import_worksheet(out, tmp / "review.csv")
        good = csv_path.read_bytes()
        result, report_path, report = R.score(pred, csv_path, split_path=split)
        counts = result["main"]["overall"]
        assert counts == {"total": 3, "accepted": 1, "rejected": 1, "judged": 2, "unjudged": 1,
                          "acceptance_rate": 0.5, "unjudged_share": 1 / 3}
        assert result["pilot"]["overall"]["acceptance_rate"] == 1.0
        assert result["main"]["driver_category"]["groundwater_abstraction"]["acceptance_rate"] == 0.5
        assert result["main"]["driver_category"]["drought_or_climate"]["acceptance_rate"] is None
        assert result["main"]["effect_category"]["groundwater_level"]["judged"] == 2
        assert result["main"]["evidence_type"]["modelled"]["unjudged_share"] == 1
        assert result["main"]["document"]["W6"]["accepted"] == 1
        assert result["invalid_predictions"] == 1 and report_path.read_text() == report
        assert "50.0%" in report and "33.3%" in report and "excluded from main" in report
        for decision, reason, message in (("reject", None, "needs"), ("accept", "other", "no reason"),
                                          (None, "other", "no reason"), ("maybe", None, "invalid decision")):
            sheet.cell(5, 13).value = decision
            sheet.cell(5, 14).value = reason
            book.save(out)
            refuses(lambda: R.import_worksheet(out, csv_path), message)
            assert csv_path.read_bytes() == good
        sheet.cell(5, 13, "reject")
        sheet.cell(5, 14, "other")
        sheet.delete_rows(6)
        book.save(out)
        refuses(lambda: R.import_worksheet(out, csv_path), "manifest")
        assert csv_path.read_bytes() == good
        book.close()
        # Old answers must not attach to changed extracted content.
        changed = copy.deepcopy(payload)
        changed[0]["quote"] = "Changed quote"
        write_json(pred, changed)
        prior_report = report_path.read_bytes()
        refuses(lambda: R.score(pred, csv_path, split_path=split), "outside these predictions")
        assert report_path.read_bytes() == prior_report
        # Empty output still has a useful workbook and n/a rates rather than division by zero.
        empty = write_json(tmp / "empty.json", [])
        empty_book, n, _ = R.worksheet(empty, tmp / "empty.xlsx", split_path=split)
        assert n == 0
        empty_csv, _ = R.import_worksheet(empty_book, tmp / "empty.csv")
        result, _, _ = R.score(empty, empty_csv, split_path=split)
        assert result["main"]["overall"]["acceptance_rate"] is None
        assert result["main"]["document"]["W6"]["total"] == 0
    print("  3. review: safe workbook, sorted/pilot rows, dropdowns, round trip, invalid answers preserve CSV, hand rates")


if __name__ == "__main__":
    started = time.perf_counter()
    test_paper_passages()
    test_runner()
    test_review()
    print(f"test_track1: all checks passed ({time.perf_counter() - started:.2f}s)")
