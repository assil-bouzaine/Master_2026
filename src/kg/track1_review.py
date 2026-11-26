"""Prepare and score Assil's paper-statement review (v5 plan R2.1, Track 1).

There is no gold set for the papers. The reported rate is accepted / judged statements,
with unjudged statements counted separately. The two pilot papers never enter that rate.
Statement ids bind each answer to its source, position and extracted content.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

from src.config import INTERIM, ROOT
from src.kg.extract_llm import (
    TRACK1_SCHEMA_PATH, TRACK1_SPLIT_PATH, _atomic_write_text, _reject_constant, load_split,
)

WORKSHEET = INTERIM / "track1_review.xlsx"
REVIEW = ROOT / "configs" / "track1_review.csv"
DECISIONS = ("accept", "reject")
REASONS = ("wrong_polarity", "wrong_driver", "wrong_effect", "not_causal",
           "not_supported_by_quote", "duplicate", "other")
ANSWERS = ("statement_id", "decision", "reason", "note")
FIELDS = ("quote", "driver", "driver_category", "effect", "effect_category", "polarity",
          "evidence_type", "place")
HEADERS = ("statement_id", "paper_title", "doi", "page", *FIELDS, "decision", "reason", "note", "split")


def statements(pred_path, split_path=TRACK1_SPLIT_PATH):
    """Return valid predictions in paper/page/position order, and invalid-item diagnostics."""
    split = load_split(split_path)
    papers = {p["document"]: p for p in split["papers"]}
    locations = {(p["document"], p["page"]): role for role in ("pilot", "main")
                 for p in split["pages"][role]}
    schema = json.loads(TRACK1_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema["items"])
    payload = json.loads(Path(pred_path).read_text(encoding="utf-8"), parse_constant=_reject_constant)
    if not isinstance(payload, list):
        raise ValueError("Predictions must be a JSON array")
    rows, invalid = [], []
    positions = defaultdict(int)
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            invalid.append(f"[{index}]: expected an object")
            continue
        content = {key: value for key, value in item.items() if key not in ("document", "page")}
        errors = list(validator.iter_errors(content))
        if errors:
            invalid.append(f"[{index}]: " + "; ".join(error.message for error in errors))
            continue
        doc, page = item.get("document"), item.get("page")
        if not isinstance(doc, str) or not isinstance(page, str) or (doc, page) not in locations:
            raise ValueError(f"Prediction [{index}] has no source page in the frozen Track 1 split")
        positions[(doc, page)] += 1
        position = positions[(doc, page)]
        digest = hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        sid = f"{doc}:p{int(page):03d}:s{position:03d}:{digest}"
        paper = papers[doc]
        rows.append({"statement_id": sid, "paper_title": paper["title"], "doi": paper["doi"],
                     "page": page, **content, "decision": "", "reason": "", "note": "",
                     "split": locations[(doc, page)], "document": doc, "order": paper["order"],
                     "position": position})
    rows.sort(key=lambda row: (row["order"], int(row["page"]), row["position"]))
    return rows, invalid


def worksheet(pred_path, out=None, force=False, *, split_path=TRACK1_SPLIT_PATH):
    """Write a readable workbook; never overwrite a sitting without --force."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    out = Path(out) if out is not None else WORKSHEET
    if out.exists() and not force:
        raise ValueError(f"{out} exists and may hold answers: import first; use --force to overwrite")
    rows, invalid = statements(pred_path, split_path)
    book = Workbook()
    guide = book.active
    guide.title = "Guide"
    instructions = [
        "Track 1: review every extracted cause-effect statement.",
        "Accept when the quote supports the driver, the effect and the polarity as extracted.",
        "Otherwise reject with one reason. Read the source page if the quote needs context.",
        "Check the categories, evidence type and place too; use other and explain in note if needed.",
        "Fill decision (accept/reject), reason (reject only), and an optional note. Leave unjudged decisions blank.",
        "Do not change statement ids or the extracted text, or remove rows. Import after each sitting.",
        "Pilot rows are marked and shaded blue. They are reported separately and excluded from the main rate.",
        "Acceptance rate = accepted / (accepted + rejected). Unjudged statements are reported separately.",
        "This review measures acceptance, not recall: missed statements have not been counted.",
        "Reasons: " + ", ".join(REASONS),
        "Import: PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.kg.track1_review import --worksheet PATH",
        f"Valid statements: {len(rows)}; invalid prediction items omitted: {len(invalid)}.",
        *invalid,
    ]
    for line in instructions:
        guide.append([line])
        guide.cell(guide.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
        guide.row_dimensions[guide.max_row].height = 32
    guide.column_dimensions["A"].width = 115
    # Keep a manifest inside the workbook so import can catch lost or invented rows.
    guide.cell(1, 2, "statement_id")
    for i, row in enumerate(rows, 2):
        guide.cell(i, 2, row["statement_id"])
    guide.column_dimensions["B"].hidden = True
    sheet = book.create_sheet("Statements")
    sheet.append(HEADERS)
    for row in rows:
        sheet.append([row[key] for key in HEADERS])
    sheet.freeze_panes = "E2"
    sheet.auto_filter.ref = sheet.dimensions
    widths = (48, 55, 40, 8, 100, 40, 30, 40, 32, 16, 28, 30, 14, 30, 55, 12)
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
        sheet.cell(1, i).font = Font(bold=True)
    for excel_row, row in zip(sheet.iter_rows(min_row=2), rows):
        for cell in excel_row:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # A copied quote starting with '=' stays literal text.
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if row["split"] == "pilot":
                cell.fill = PatternFill("solid", fgColor="DDEBF7")
            if cell.column in (13, 14, 15):
                cell.fill = PatternFill("solid", fgColor="FFF2CC")
        sheet.row_dimensions[excel_row[0].row].height = 75
    if rows:
        for name, choices in (("decision", DECISIONS), ("reason", REASONS)):
            dropdown = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
            dropdown.errorTitle = f"Choose a {name}"
            dropdown.error = "Choose a listed value or leave the cell blank."
            dropdown.showErrorMessage = True
            dropdown.errorStyle = "stop"
            sheet.add_data_validation(dropdown)
            column = get_column_letter(HEADERS.index(name) + 1)
            dropdown.add(f"{column}2:{column}{sheet.max_row}")
    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)
    book.close()
    return out, len(rows), invalid


def _validate_answers(rows):
    """Validate the whole sitting before callers write or calculate anything."""
    seen = set()
    for row in rows:
        sid, decision, reason = (row[key] for key in ANSWERS[:3])
        if not sid or sid in seen:
            raise ValueError(f"Missing or duplicate statement_id: {sid!r}")
        seen.add(sid)
        if decision and decision not in DECISIONS:
            raise ValueError(f"{sid}: invalid decision {decision!r}")
        if decision == "reject" and reason not in REASONS:
            raise ValueError(f"{sid}: a reject needs a listed reason")
        if decision != "reject" and reason:
            raise ValueError(f"{sid}: an accept or unjudged statement must have no reason")


def import_worksheet(path=None, out=None):
    """Check ids, headers and decision/reason pairs, then atomically save the review CSV."""
    from openpyxl import load_workbook

    path = Path(path) if path is not None else WORKSHEET
    out = Path(out) if out is not None else REVIEW
    book = load_workbook(path)
    try:
        if not {"Guide", "Statements"} <= set(book.sheetnames):
            raise ValueError("Workbook needs Guide and Statements sheets")
        sheet = book["Statements"]
        headers = [cell.value for cell in sheet[1]]
        if any(headers.count(key) != 1 for key in ANSWERS):
            raise ValueError("Statements headers must contain each answer column exactly once")
        if book["Guide"].cell(1, 2).value != "statement_id":
            raise ValueError("Guide statement-id manifest is missing")
        expected = [cell[0].value for cell in book["Guide"].iter_rows(min_row=2, min_col=2, max_col=2)
                    if cell[0].value is not None]
        rows = []
        for cells in sheet.iter_rows(min_row=2):
            if all(cell.value is None or str(cell.value).strip() == "" for cell in cells):
                continue
            row = {}
            for key in ANSWERS:
                cell = cells[headers.index(key)]
                if cell.data_type == "f":
                    raise ValueError(f"{cell.coordinate}: formulas are not review answers")
                row[key] = "" if cell.value is None else str(cell.value).strip()
            rows.append(row)
        _validate_answers(rows)
        if len(expected) != len(set(expected)) or {r["statement_id"] for r in rows} != set(expected):
            raise ValueError("Statements differ from the workbook manifest: missing or unknown ids")
    finally:
        book.close()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=ANSWERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out, buffer.getvalue())
    return out, len(rows)


def _counts(rows):
    accepted = sum(r["decision"] == "accept" for r in rows)
    rejected = sum(r["decision"] == "reject" for r in rows)
    judged = accepted + rejected
    return {"total": len(rows), "accepted": accepted, "rejected": rejected,
            "judged": judged, "unjudged": len(rows) - judged,
            "acceptance_rate": accepted / judged if judged else None,
            "unjudged_share": (len(rows) - judged) / len(rows) if rows else None}


def score(pred_path, review_path=REVIEW, out=None, *, split_path=TRACK1_SPLIT_PATH):
    """Report main acceptance and coverage overall and by category; keep pilot apart."""
    rows, invalid = statements(pred_path, split_path)
    split = load_split(split_path)
    with Path(review_path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(ANSWERS):
            raise ValueError(f"Review CSV headers must be {ANSWERS}")
        answers = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in answers):
        raise ValueError("Review CSV has a malformed row")
    _validate_answers(answers)
    by_id = {r["statement_id"]: r for r in answers}
    unknown = set(by_id) - {r["statement_id"] for r in rows}
    if unknown:
        raise ValueError(f"Review has ids outside these predictions (possibly changed content): {sorted(unknown)}")
    for row in rows:
        row.update(by_id.get(row["statement_id"], {}))
    result = {"invalid_predictions": len(invalid)}
    dimensions = ("driver_category", "effect_category", "evidence_type", "document")
    for role in ("main", "pilot"):
        subset = [row for row in rows if row["split"] == role]
        result[role] = {"overall": _counts(subset)}
        for dimension in dimensions:
            groups = defaultdict(list)
            if dimension == "document":
                # A paper with no extracted statement still appears, with an undefined rate.
                for paper in split["papers"]:
                    if (paper["document"] in split["pilot_documents"]) == (role == "pilot"):
                        groups[paper["document"]] = []
            for row in subset:
                groups[row[dimension]].append(row)
            result[role][dimension] = {key: _counts(group) for key, group in groups.items()}
    lines = ["# Track 1 statement review", "",
             "Acceptance rate = accepted / judged (accepted + rejected). Unjudged share = unjudged / total.",
             "Pilot papers are excluded from every main rate. This measures acceptance, not recall.",
             f"Invalid prediction items excluded before review: {len(invalid)}.", ""]

    def percent(value):
        return "n/a" if value is None else f"{value:.1%}"

    for role in ("main", "pilot"):
        lines += [f"## {role.title()} papers" + (" (excluded from main)" if role == "pilot" else ""), ""]
        for dimension in ("overall", *dimensions):
            lines += [f"### {dimension}", "",
                      "| Group | Accepted | Rejected | Judged | Total | Acceptance rate | Unjudged | Unjudged share |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|"]
            groups = {"all": result[role][dimension]} if dimension == "overall" else result[role][dimension]
            for key, counts in groups.items():
                lines.append(f"| {key} | {counts['accepted']} | {counts['rejected']} | {counts['judged']} | "
                             f"{counts['total']} | {percent(counts['acceptance_rate'])} | "
                             f"{counts['unjudged']} | {percent(counts['unjudged_share'])} |")
            lines.append("")
    report = "\n".join(lines)
    out = Path(out) if out is not None else Path(pred_path).parent / "score_track1.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out, report)
    return result, out, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("worksheet")
    p.add_argument("--pred", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("import")
    p.add_argument("--worksheet", type=Path, default=WORKSHEET)
    p.add_argument("--out", type=Path, default=REVIEW)
    p = sub.add_parser("score")
    p.add_argument("--pred", type=Path, required=True)
    p.add_argument("--review", type=Path, default=REVIEW)
    p.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "worksheet":
            path, count, invalid = worksheet(args.pred, args.out, args.force)
            print(f"-> {path}: {count} statements; {len(invalid)} invalid items omitted")
        elif args.cmd == "import":
            path, count = import_worksheet(args.worksheet, args.out)
            print(f"-> {path}: {count} answers saved")
        else:
            _, path, report = score(args.pred, args.review, args.out)
            print(report, end="")
            print(f"Saved report to {path}")
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
