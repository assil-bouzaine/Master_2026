"""Check the task 12.9 worksheet without touching Assil's real labels.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_agrovoc_gold

The workbook is an editing aid, so format errors must leave the CSV untouched. A validly
formatted answer must survive even when the snapshot check finds a mistake to correct.
"""
import csv
import hashlib
import io
import time
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import load_workbook

from src.kg import agrovoc_gold as A

HEADERS = ["code", "label", "area_ha", "split", "relation", "concept", "alternatives", "note"]
HEADERS += [f"candidate_{i}" for i in range(1, 9)]
PREFIX = "http://aims.fao.org/aos/agrovoc/"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@contextmanager
def temporary_files():
    """Redirect every writable command path, plus its input tables, to a separate copy."""
    with TemporaryDirectory(prefix="agrovoc-gold-") as directory:
        directory = Path(directory)
        gold, candidates, labels = [directory / p.name for p in (A.GOLD, A.CANDIDATES, A.LABELS)]
        for source, target in ((A.GOLD, gold), (A.CANDIDATES, candidates), (A.LABELS, labels)):
            target.write_bytes(source.read_bytes())
        with (patch.object(A, "GOLD", gold), patch.object(A, "CANDIDATES", candidates),
              patch.object(A, "LABELS", labels), patch.object(A, "SECOND", directory / "second.csv"),
              patch.object(A, "WORKSHEET", directory / "worksheet.xlsx")):
            yield directory


def expect_exit_one(call):
    output = io.StringIO()
    with redirect_stdout(output):
        try:
            call()
        except SystemExit as exc:
            assert exc.code == 1, exc.code
        else:
            raise AssertionError("Expected exit 1")
    return output.getvalue()


def cells_by_code(sheet):
    columns = {c.value: c.column for c in sheet[1]}
    return {str(sheet.cell(row, columns["code"]).value):
            {name: sheet.cell(row, column) for name, column in columns.items()}
            for row in range(2, sheet.max_row + 1)}


def test_worksheet():
    with temporary_files():
        A.worksheet()
        book = load_workbook(A.WORKSHEET)
        try:
            assert book.sheetnames == ["Rules", "Labels"]
            labels = book["Labels"]
            assert labels.max_row == 199
            assert [c.value for c in labels[1]] == HEADERS
            rows = list(labels.iter_rows(min_row=2, values_only=True))
            original = read_csv(A.GOLD)
            expected = sorted(original, key=lambda r: (r["split"] != "dev", -float(r["area_ha"])))
            assert [r[0] for r in rows] == [r["code"] for r in expected]
            assert sum(r[3] == "dev" for r in rows) == 40
            assert labels.freeze_panes == "C2"
            assert all(c.font.bold for c in labels[1])
            assert labels["B2"].alignment.wrap_text
            assert all(labels.cell(2, col).fill.fgColor.rgb.endswith("FFF2CC") for col in range(5, 9))
            assert all(labels.cell(2, col).font.color.rgb.endswith("777777") for col in range(9, 17))
            dropdowns = list(labels.data_validations.dataValidation)
            assert len(dropdowns) == 1
            dropdown = dropdowns[0]
            assert dropdown.type == "list" and dropdown.allow_blank
            assert dropdown.formula1 == '"exactMatch,closeMatch,broadMatch,narrowMatch,none"'
            assert all(f"E{row}" in dropdown for row in range(2, 200))

            # This oracle uses csv, in file order, independently of the command's pandas grouping.
            candidate_rows = read_csv(A.CANDIDATES)
            by_code = cells_by_code(labels)
            for code in ("SPH", "VRC", "CML"):
                seen, expected = set(), []
                for row in candidate_rows:
                    if row["code"] != code or row["concept"] in seen:
                        continue
                    seen.add(row["concept"])
                    text = row["concept"].removeprefix(PREFIX) + " · " + row["pref_fr"] + " | " + row["pref_en"]
                    if row["broader_fr"]:
                        text += " · ↑ " + row["broader_fr"]
                    expected.append(text)
                expected = expected[:8]
                expected += [None] * (8 - len(expected))
                assert [by_code[code][f"candidate_{i}"].value for i in range(1, 9)] == expected, code

            note = (A.ROOT / "docs" / "notes" / "step12_ontology.md").read_text(encoding="utf-8")
            section = note.split("### 12.9 gold-set decision rules (Assil, 2026-11-26, before any label)", 1)[1]
            section = section.split("\n## ", 1)[0].strip()
            rule_cells = [r[0].value for r in book["Rules"]]
            assert all(paragraph in rule_cells for paragraph in section.split("\n\n"))
        finally:
            book.close()
        before = sha256(A.WORKSHEET)
        message = expect_exit_one(A.worksheet)
        assert "Assil's answers" in message and "import first" in message
        assert sha256(A.WORKSHEET) == before
    print("  1. Rules first, 198 sorted codes (40 dev), headers, all dropdown cells, styling, three candidate oracles; overwrite refused")


def test_round_trip():
    with temporary_files():
        original = read_csv(A.GOLD)
        A.worksheet()
        book = load_workbook(A.WORKSHEET)
        labels = book["Labels"]
        cells = cells_by_code(labels)
        answers = {
            "VRC": {"relation": "closeMatch", "concept": PREFIX + "c_3360",
                    "alternatives": PREFIX + "c_5638; " + PREFIX + "c_15203", "note": 'Plant, "fruit"; vérifié'},
            "VRG": {"relation": "broadMatch", "concept": PREFIX + "c_5379", "alternatives": "", "note": "Orchard"},
            "SNE": {"relation": "none", "concept": "", "alternatives": "", "note": "Administrative"},
        }
        for code, values in answers.items():
            for name, value in values.items():
                cells[code][name].value = " " + value + " "
        cells["VRC"]["concept"].value = " c_3360 "
        cells["VRC"]["alternatives"].value = " c_5638 ; http://aims.fao.org/aos/agrovoc/c_15203 "
        # Swap code/note and relation/concept, including headers: import must use header names.
        for left, right in ((1, 8), (5, 6)):
            for row in range(1, labels.max_row + 1):
                a, b = labels.cell(row, left), labels.cell(row, right)
                a.value, b.value = b.value, a.value
        book.save(A.WORKSHEET)
        book.close()
        output = io.StringIO()
        with redirect_stdout(output):
            A.import_worksheet()
            A.check()
        assert "3 of 198 codes judged" in output.getvalue()
        assert output.getvalue().count("gold set valid so far") == 2
        imported = read_csv(A.GOLD)
        assert [r["code"] for r in imported] == [r["code"] for r in original]
        for before, after in zip(original, imported):
            for name in before:
                if name not in A.LABEL_COLUMNS:
                    assert after[name] == before[name], (before["code"], name)
                else:
                    assert after[name] == answers.get(before["code"], before)[name], (before["code"], name)

        A.worksheet(force=True)
        book = load_workbook(A.WORKSHEET)
        try:
            regenerated = cells_by_code(book["Labels"])
            for code, values in answers.items():
                for name, value in values.items():
                    assert (regenerated[code][name].value or "") == value
        finally:
            book.close()
        # An unchanged regenerated workbook preserves all bytes, including CSV quotes and UTF-8 accents.
        before = sha256(A.GOLD)
        A.import_worksheet()
        assert sha256(A.GOLD) == before
    print("  2. Reordered-header round trip: short/full IRIs, alternatives, none, stripped notes; metadata preserved; check accepts; regeneration retains answers")


def test_format_errors():
    with temporary_files():
        A.worksheet()
        pristine = A.WORKSHEET.read_bytes()
        before = sha256(A.GOLD)
        for kind in ("concept", "unknown", "duplicate", "missing", "blank_code", "alternative", "relation", "headers", "sheet"):
            A.WORKSHEET.write_bytes(pristine)
            book = load_workbook(A.WORKSHEET)
            labels = book["Labels"]
            cells = cells_by_code(labels)
            cell = cells["VRC"]["concept"].coordinate
            if kind == "concept":
                cells["VRC"]["concept"].value = "grapevines"
            elif kind == "unknown":
                cells["VRC"]["code"].value = "NOT_A_GOLD_CODE"
            elif kind == "duplicate":
                cells["VRG"]["code"].value = "VRC"
            elif kind == "missing":
                labels.delete_rows(cells["VRC"]["code"].row)
            elif kind == "blank_code":
                cells["VRC"]["code"].value = None
            elif kind == "alternative":
                cells["VRC"]["alternatives"].value = "c_3360; grapevines; https://example.org/c_5379"
            elif kind == "relation":
                cells["VRC"]["relation"].value = "exact"
            elif kind == "headers":
                labels["F1"] = "wrong_header"
            else:
                labels.title = "Wrong"
            book.save(A.WORKSHEET)
            book.close()
            message = expect_exit_one(A.import_worksheet)
            assert sha256(A.GOLD) == before, kind
            assert "Labels" in message
            if kind == "concept":
                assert "VRC" in message and cell in message and "grapevines" in message
            elif kind == "unknown":
                assert "NOT_A_GOLD_CODE" in message and "VRC" in message
            elif kind == "alternative":
                assert "grapevines" in message and "https://example.org/c_5379" in message

        # Several bad cells must all be reported in one pass.
        A.WORKSHEET.write_bytes(pristine)
        book = load_workbook(A.WORKSHEET)
        cells = cells_by_code(book["Labels"])
        bad_cells = [("VRC", "concept", "grapevines"), ("VRG", "relation", "bad relation"),
                     ("SNE", "alternatives", "bad alternative")]
        for code, name, value in bad_cells:
            cells[code][name].value = value
        coordinates = [cells[code][name].coordinate for code, name, _ in bad_cells]
        book.save(A.WORKSHEET)
        book.close()
        message = expect_exit_one(A.import_worksheet)
        assert all(value in message and code in message for code, _, value in bad_cells)
        assert all(coordinate in message for coordinate in coordinates)
        assert sha256(A.GOLD) == before
    print("  3. Nine format-error cases and combined errors exit 1 with cell details; CSV SHA-256 unchanged")


def test_snapshot_error_saves():
    with temporary_files() as directory:
        # Use an empty temporary snapshot, so a real ID is absent without inventing a concept.
        import pandas as pd

        snapshot = pd.read_parquet(A.LABELS)
        snapshot.iloc[:0].to_parquet(A.LABELS)
        output = directory / "custom.xlsx"
        A.worksheet(output)
        book = load_workbook(output)
        cells = cells_by_code(book["Labels"])
        cells["VRC"]["relation"].value = "closeMatch"
        cells["VRC"]["concept"].value = "c_3360"
        book.save(output)
        book.close()
        stream = io.StringIO()
        with redirect_stdout(stream):
            try:
                A.import_worksheet(output)
            except SystemExit as exc:
                assert "not a concept of the AGROVOC snapshot" in str(exc)
            else:
                raise AssertionError("The empty snapshot must reject the answer")
        assert "answers saved" in stream.getvalue() and "fix the workbook" in stream.getvalue()
        row = next(r for r in read_csv(A.GOLD) if r["code"] == "VRC")
        assert row["relation"] == "closeMatch" and row["concept"] == PREFIX + "c_3360"
    print("  4. Snapshot failure after import keeps the answers and explains how to correct them; custom paths work")


def test_csv_format():
    with temporary_files():
        # LibreOffice users may also keep their CSV with a UTF-8 BOM and Windows line endings.
        text = A.GOLD.read_text(encoding="utf-8-sig")
        A.GOLD.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
        before = sha256(A.GOLD)
        A.worksheet()
        A.import_worksheet()
        assert sha256(A.GOLD) == before
    print("  5. Unchanged CSV round trip preserves UTF-8 BOM and CRLF bytes too")


if __name__ == "__main__":
    started = time.perf_counter()
    real_gold, real_second = A.GOLD, A.SECOND
    before = sha256(real_gold)
    second_before = sha256(real_second) if real_second.exists() else None
    try:
        test_worksheet()
        test_round_trip()
        test_format_errors()
        test_snapshot_error_saves()
        test_csv_format()
    finally:
        assert sha256(real_gold) == before, "Assil's real gold CSV changed"
        assert (sha256(real_second) if real_second.exists() else None) == second_before
        print(f"  Real gold SHA-256 unchanged: {before}; second-annotator file unchanged")
    print(f"test_agrovoc_gold: all checks passed ({time.perf_counter() - started:.2f}s)")
