"""Score offline exchange extraction against the checked passages (v5 plan R2.1, Track 2).

The schema and this rule are fixed before running an LLM. Match only within a document and
page, using the longest common substring after lower-casing and collapsing whitespace. Accents
and punctuation stay. Overlap is that substring's length divided by the shorter quote's length.
Take eligible pairs greedily by decreasing overlap, then gold id, then input prediction index.
Fields never choose the pairing. Strict scores use those same pairs, requiring mechanism and
direction to agree too. Invalid items cannot match but count in the precision denominator.

Set scores are the mean of each matched pair's set-F1; two empty sets score 1. A score with no
denominator is 0, including field scores when there are no matches. Malformed JSON or a non-array
root is an input error, since no statement count can be inferred. No model or network is used.
"""
import argparse
import csv
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path

from src.config import ROOT

GOLD = ROOT / "configs" / "exchange_evidence.csv"
SCHEMA = ROOT / "configs" / "extraction_schema.json"
FIELDS = ("mechanism", "direction", "hedging", "method", "subject")
SETS = ("units", "watercourses")


@dataclass
class Predictions:
    """Valid items and rejected items, retaining their original zero-based JSON indices."""

    valid: dict[int, dict]
    invalid: list[dict]

    @property
    def total(self):
        return len(self.valid) + len(self.invalid)


def load_gold(path=GOLD):
    """Keep CSV ids for audit, and split semicolon code lists as rivers.py does."""
    properties = json.loads(SCHEMA.read_text(encoding="utf-8"))["items"]["properties"]
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    gold = [{"id": row["id"], **{key: row[key] for key in properties}} for row in rows]
    for item in gold:
        for field in SETS:
            item[field] = [code for code in item[field].split(";") if code]
    if len({item["id"] for item in gold}) != len(gold):
        raise ValueError("Gold statement ids must be unique")
    return gold


def _schema_errors(value, schema, location="item"):
    """Validate the keywords used by our fixed schema without an unpinned dependency.

    The schema uses only objects, arrays, strings, enums, patterns, required properties and
    unique items. This small recursive validator covers those rules, not arbitrary JSON Schema.
    """
    kind = schema["type"]
    types = {"object": dict, "array": list, "string": str}
    if not isinstance(value, types[kind]):
        return [f"{location}: expected {kind}"]
    errors = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: value is not in {schema['enum']}")
    if kind == "string" and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{location}: must contain non-whitespace text")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{location}.{key}: required property is missing")
        for key, item in value.items():
            if key in schema["properties"]:
                errors.extend(_schema_errors(item, schema["properties"][key], f"{location}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{location}.{key}: unexpected property")
    if kind == "array":
        if schema.get("uniqueItems") and any(item in value[:i] for i, item in enumerate(value)):
            errors.append(f"{location}: duplicate items are not allowed")
        for i, item in enumerate(value):
            errors.extend(_schema_errors(item, schema["items"], f"{location}[{i}]"))
    return errors


def validate_predictions(payload):
    """Reject invalid items individually, keeping their values and all validation errors."""
    if not isinstance(payload, list):
        raise ValueError("Predictions must be a JSON array of statements")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    valid, invalid = {}, []
    for index, item in enumerate(payload):
        errors = _schema_errors(item, schema["items"])
        if errors:
            invalid.append({"index": index, "item": item, "errors": errors})
        else:
            valid[index] = item
    return Predictions(valid, invalid)


def load_predictions(path):
    """Read a UTF-8 JSON array and validate it against configs/extraction_schema.json."""
    def reject_constant(value):
        raise ValueError(f"{value} is not valid JSON")

    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)
    return validate_predictions(payload)


def normalize_quote(quote):
    return " ".join(quote.lower().split())


def quote_overlap(first, second):
    """Exact overlap fraction; disable difflib's heuristic so repeated text is kept."""
    first, second = normalize_quote(first), normalize_quote(second)
    shorter = min(len(first), len(second))
    if not shorter:
        return Fraction(0)
    size = SequenceMatcher(None, first, second, autojunk=False).find_longest_match().size
    return Fraction(size, shorter)


def match_statements(gold, predictions):
    """One-to-one greedy pairs, sorted by overlap, gold id, then prediction index."""
    candidates = []
    for item in gold:
        for index, prediction in predictions.valid.items():
            if (item["document"], item["page"]) != (prediction["document"], prediction["page"]):
                continue
            overlap = quote_overlap(item["quote"], prediction["quote"])
            if overlap >= Fraction(2, 5):
                candidates.append((-overlap, item["id"], index))
    used_gold, used_predictions, matches = set(), set(), []
    for negative_overlap, gold_id, index in sorted(candidates):
        if gold_id in used_gold or index in used_predictions:
            continue
        used_gold.add(gold_id)
        used_predictions.add(index)
        matches.append({"gold_id": gold_id, "prediction_index": index, "overlap": float(-negative_overlap)})
    return matches


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def _scores(matches, predictions, gold):
    return {"precision": _ratio(matches, predictions), "recall": _ratio(matches, gold),
            "f1": _ratio(2 * matches, predictions + gold)}


def set_f1(first, second):
    first, second = set(first), set(second)
    return 2 * len(first & second) / (len(first) + len(second)) if first or second else 1.0


def score(gold, predictions):
    """Count every submitted item, even if invalid; field scores use matched pairs only."""
    matches = match_statements(gold, predictions)
    by_id = {item["id"]: item for item in gold}
    pairs = [(by_id[match["gold_id"]], predictions.valid[match["prediction_index"]]) for match in matches]
    strict = sum(all(a[field] == b[field] for field in ("mechanism", "direction")) for a, b in pairs)
    gold_ids = {match["gold_id"] for match in matches}
    prediction_indices = {match["prediction_index"] for match in matches}
    unmatched = [{"index": index, "item": item, "errors": []}
                 for index, item in predictions.valid.items() if index not in prediction_indices]
    unmatched.extend(predictions.invalid)
    return {
        "counts": {"gold": len(gold), "predictions": predictions.total, "valid": len(predictions.valid),
                   "invalid": len(predictions.invalid), "matched": len(matches), "strict_matches": strict},
        "statement": _scores(len(matches), predictions.total, len(gold)),
        "strict": _scores(strict, predictions.total, len(gold)),
        "field_accuracy": {field: _ratio(sum(a[field] == b[field] for a, b in pairs), len(pairs))
                           for field in FIELDS},
        "set_f1": {field: _ratio(sum(set_f1(a[field], b[field]) for a, b in pairs), len(pairs))
                   for field in SETS},
        "matches": matches,
        "unmatched_gold_ids": sorted(set(by_id) - gold_ids),
        "unmatched_predictions": sorted(unmatched, key=lambda item: item["index"]),
    }


def markdown_report(result):
    """Show denominators and rejected items so invalid output cannot inflate precision."""
    lines = ["# Track 2 extraction scores", "", "| Count | Value |", "|---|---:|"]
    lines.extend(f"| {name} | {value} |" for name, value in result["counts"].items())
    lines.extend(["", "| Score | Precision | Recall | F1 |", "|---|---:|---:|---:|"])
    for name in ("statement", "strict"):
        values = result[name]
        lines.append(f"| {name} | {values['precision']:.6f} | {values['recall']:.6f} | {values['f1']:.6f} |")
    lines.extend(["", "| Matched-pair field | Accuracy / mean set-F1 |", "|---|---:|"])
    for group in ("field_accuracy", "set_f1"):
        lines.extend(f"| {field} | {value:.6f} |" for field, value in result[group].items())
    lines.extend(["", "Invalid items count as false positives. All submitted items enter precision; all gold "
                  "items enter recall. Strict matches also require mechanism and direction to agree.", "",
                  "Quote overlap = longest common substring / shorter normalised quote length, at least 0.4. "
                  "Greedy order: decreasing overlap, gold id, then zero-based prediction index. "
                  "Matching requires identical document and page labels and never uses predicted fields.", "",
                  "Set-F1 is averaged over matched pairs; two empty sets score 1. Undefined scores are 0.",
                  "", "## Unmatched gold ids", ""])
    lines.extend(f"- {gold_id}" for gold_id in result["unmatched_gold_ids"])
    if not result["unmatched_gold_ids"]:
        lines.append("None.")
    lines.extend(["", "## Unmatched predictions (zero-based indices)", ""])
    for item in result["unmatched_predictions"]:
        state = "invalid" if item["errors"] else "valid, no match"
        lines.extend([f"### Prediction {item['index']} ({state})", ""])
        lines.extend(f"- {error}" for error in item["errors"])
        # Indented code keeps even quotes containing Markdown fences readable as data.
        lines.extend(["", "    " + json.dumps(item["item"], ensure_ascii=False), ""])
    if not result["unmatched_predictions"]:
        lines.append("None.")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--out", type=Path, help="also save the Markdown report here")
    args = parser.parse_args(argv)
    if args.out and args.out.resolve() in (args.predictions.resolve(), GOLD.resolve(), SCHEMA.resolve()):
        parser.error("--out must not overwrite the input, gold CSV or extraction schema")
    try:
        predictions = load_predictions(args.predictions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    report = markdown_report(score(load_gold(), predictions))
    print(report, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
