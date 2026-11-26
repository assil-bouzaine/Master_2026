"""Offline checks for the pre-model extraction scorer (v5 plan R2.1, Track 2).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_extract_eval

The checked CSV is its own perfect prediction. Controlled errors have scores calculated below
by hand. Small ambiguous cases pin down greedy pairing, ties and the exact overlap threshold.
"""
import copy
import csv
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

from src.kg.extract_eval import (
    FIELDS, GOLD, ROOT, SCHEMA, SETS, load_gold, load_predictions, markdown_report,
    match_statements, normalize_quote, quote_overlap, score, validate_predictions,
)


def prediction(gold):
    return copy.deepcopy({key: value for key, value in gold.items() if key != "id"})


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def test_schema_and_self_score():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    properties = schema["items"]["properties"]
    with GOLD.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 32
    assert set(schema["items"]["required"]) == set(properties)
    for field in ("document", *FIELDS):
        assert set(properties[field]["enum"]) == {row[field] for row in rows}
    for field in SETS:
        assert set(properties[field]["items"]["enum"]) == {
            code for row in rows for code in row[field].split(";") if code
        }
    gold = load_gold()
    assert {item["id"] for item in gold} == {row["id"] for row in rows}
    for row, item in zip(rows, gold):
        for field in properties:
            expected = [code for code in row[field].split(";") if code] if field in SETS else row[field]
            assert item[field] == expected
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "self.json"
        path.write_text(json.dumps([prediction(item) for item in gold], ensure_ascii=False), encoding="utf-8")
        predictions = load_predictions(path)
    result = score(gold, predictions)
    assert result["counts"] == {"gold": 32, "predictions": 32, "valid": 32, "invalid": 0,
                                "matched": 32, "strict_matches": 32}
    for group in ("statement", "strict", "field_accuracy", "set_f1"):
        assert all(value == 1.0 for value in result[group].values()), result
    assert not result["unmatched_gold_ids"] and not result["unmatched_predictions"]
    print("  1. CSV vocabulary and 32 self-predictions: every score = 1")


def test_hand_computed_errors():
    gold = load_gold()
    payload = [prediction(item) for item in gold[:-1]]  # One omission: 31 true candidates.
    payload[0]["direction"] = "equilibrium"           # One of the 31 pairs is not strict.
    old_quote = payload[17]["quote"]
    payload[17]["quote"] = "Reworded passage: " + old_quote[15:]
    overlap = quote_overlap(old_quote, payload[17]["quote"])
    assert Fraction(2, 5) <= overlap < 1
    extra = prediction(gold[-1])
    extra["quote"] = "Ω" * 80                         # Valid schema; no quote overlaps it.
    payload.append(extra)                             # Back to 32 submitted predictions.
    result = score(gold, validate_predictions(payload))
    assert result["counts"]["matched"] == 31 and result["counts"]["strict_matches"] == 30
    for metric in ("precision", "recall", "f1"):
        close(result["statement"][metric], 31 / 32)
        close(result["strict"][metric], 30 / 32)
    for field in FIELDS:
        close(result["field_accuracy"][field], 30 / 31 if field == "direction" else 1)
    assert result["set_f1"] == {"units": 1.0, "watercourses": 1.0}
    assert result["unmatched_gold_ids"] == [gold[-1]["id"]]
    assert [item["index"] for item in result["unmatched_predictions"]] == [31]
    assert any(pair["gold_id"] == gold[17]["id"] and pair["prediction_index"] == 17
               for pair in result["matches"])
    print("  2. dropped + wrong direction + extra + reworded: P/R/F1 = 31/32, strict = 30/32")


def test_invalid_items():
    good = prediction(load_gold()[0])
    cases = []
    for key, value in (("direction", "unknown"), ("page", 3), ("quote", " \t\n"),
                       ("document", "unknown"), ("units", ["unknown"]),
                       ("watercourses", "Y0110540"), ("units", ["671AA00", "671AA00"]),
                       ("watercourses", ["Y0110540", "Y0110540"]),
                       ("units", [None]), ("quote", False)):
        item = copy.deepcopy(good)
        item[key] = value
        cases.append(item)
    missing = copy.deepcopy(good)
    del missing["method"]
    del missing["hedging"]
    cases.extend([missing, {**good, "unexpected": 1}, None, [], "text", 1])
    payload = [good, *cases]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "invalid.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        predictions = load_predictions(path)
    assert predictions.total == 17 and list(predictions.valid) == [0]
    assert len(predictions.invalid) == 16
    assert [item["index"] for item in predictions.invalid] == list(range(1, 17))
    assert all(item["errors"] and item["item"] == payload[item["index"]] for item in predictions.invalid)
    assert len(predictions.invalid[10]["errors"]) == 2  # Count items, not validation errors.
    result = score(load_gold()[:1], predictions)
    close(result["statement"]["precision"], 1 / 17)
    close(result["statement"]["recall"], 1)
    close(result["statement"]["f1"], 2 / 18)
    assert result["counts"]["invalid"] == 16
    assert result["unmatched_predictions"] == predictions.invalid
    report = markdown_report(result)
    for item in predictions.invalid:
        assert f"Prediction {item['index']} (invalid)" in report
        assert json.dumps(item["item"], ensure_ascii=False) in report
        assert all(error in report for error in item["errors"])
    print("  3. all 16 invalid items retained with errors; precision = 1/17")


def test_matching():
    assert normalize_quote("  ÉTÉ\n\t  À L’EAU ") == "été à l’eau"
    assert quote_overlap("ÉTÉ", "été") == 1
    assert quote_overlap("été", "ete") == Fraction(1, 3)  # Only the unaccented t is shared.
    assert quote_overlap("abcdeXXXXX", "abcdeYYYYY") == Fraction(1, 2)
    assert quote_overlap("abcdXXXXXX", "abcdYYYYYY") == Fraction(2, 5)
    assert quote_overlap("abcXXXXXXX", "abcYYYYYYY") == Fraction(3, 10)
    assert quote_overlap("", "not empty") == 0
    assert quote_overlap("a" * 220 + "b", "c" + "a" * 220) == Fraction(220, 221)
    base = load_gold()[0]
    gold = [{**copy.deepcopy(base), "id": name, "quote": "abcdXXXXXX"} for name in ("b", "a")]
    payload = [prediction({**base, "quote": "abcdYYYYYY"}) for _ in range(3)]
    predictions = validate_predictions(payload)
    matches = match_statements(gold, predictions)
    assert [(pair["gold_id"], pair["prediction_index"]) for pair in matches] == [("a", 0), ("b", 1)]
    assert match_statements(list(reversed(gold)), predictions) == matches
    result = score(gold, predictions)
    assert result["counts"]["matched"] == 2
    close(result["statement"]["precision"], 2 / 3)
    close(result["statement"]["recall"], 1)
    close(result["statement"]["f1"], 4 / 5)
    assert [item["index"] for item in result["unmatched_predictions"]] == [2]
    assert score(gold[:1], predictions)["counts"]["matched"] == 1
    below = validate_predictions([prediction({**base, "quote": "abcYYYYYYY"})])
    assert not match_statements(gold, below)

    # The strongest pair wins even when it comes later and the weaker gold id sorts first.
    gold = [{**base, "id": "a", "quote": "abcdeXXXXX"}, {**base, "id": "z", "quote": "abcdefghij"}]
    predictions = validate_predictions([prediction({**base, "quote": "abcdefghij"})])
    assert match_statements(gold, predictions)[0]["gold_id"] == "z"
    for key, value in (("document", "sierm-frdg243"), ("page", "web page")):
        different = validate_predictions([{**prediction(base), key: value}])
        assert not match_statements([base], different)

    # Mechanism and direction must not influence a quote tie or trigger strict re-matching.
    gold = [{**base, "id": "a", "direction": "equilibrium"}, {**base, "id": "b"}]
    result = score(gold, validate_predictions([prediction(base)]))
    assert result["matches"][0]["gold_id"] == "a" and result["strict"]["f1"] == 0
    print("  4. threshold, accents, repeated text, location, greedy order and one-to-one ties pass")


def test_field_and_set_scores():
    gold = load_gold()[0]
    changed = prediction(gold)
    properties = json.loads(SCHEMA.read_text(encoding="utf-8"))["items"]["properties"]
    for field in FIELDS:
        changed[field] = next(value for value in properties[field]["enum"] if value != gold[field])
    result = score([gold], validate_predictions([changed]))
    assert result["statement"]["f1"] == 1 and result["strict"]["f1"] == 0
    assert result["field_accuracy"] == dict.fromkeys(FIELDS, 0.0)

    gold = [{**prediction(gold), "id": str(i), "page": str(i)} for i in range(3)]
    gold[0].update(units=["671AB01", "671AB02"], watercourses=[])
    gold[1].update(units=["671AB01"], watercourses=["Y03-0400"])
    gold[2].update(units=[], watercourses=[])
    payload = [prediction(item) for item in gold]
    payload[0]["units"] = ["671AB02", "718BP01"]   # Set-F1 = 1/2.
    payload[1].update(units=[], watercourses=["Y03-0400", "Y0320500"])  # 0 and 2/3.
    payload[2]["watercourses"] = ["Y0110540"]        # Empty vs nonempty = 0.
    result = score(gold, validate_predictions(payload))
    close(result["set_f1"]["units"], (1 / 2 + 0 + 1) / 3)
    close(result["set_f1"]["watercourses"], (1 + 2 / 3 + 0) / 3)
    reversed_codes = prediction(load_gold()[0])
    reversed_codes["units"].reverse()
    assert score(load_gold()[:1], validate_predictions([reversed_codes]))["set_f1"]["units"] == 1
    for empty_gold, empty_payload in (([], []), (gold, []), ([], payload), (gold, [None])):
        result = score(empty_gold, validate_predictions(empty_payload))
        for group in ("statement", "strict", "field_accuracy", "set_f1"):
            assert all(value == 0 for value in result[group].values())
    print("  5. all field errors, macro set-F1, empty sets and zero denominators pass")


def test_cli_and_bad_files():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "predictions.json"
        out = Path(directory) / "nested" / "report.md"
        path.write_text(json.dumps([prediction(item) for item in load_gold()], ensure_ascii=False), encoding="utf-8")
        command = [sys.executable, "-m", "src.kg.extract_eval", str(path)]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PFE_DATASET": "v5"}
        result = subprocess.run([*command, "--out", str(out)], cwd=ROOT, env=env, text=True,
                                capture_output=True, encoding="utf-8", check=True)
        assert result.stdout == out.read_text(encoding="utf-8")
        assert "| strict | 1.000000 | 1.000000 | 1.000000 |" in result.stdout
        printed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=True)
        assert printed.stdout == result.stdout
        protected = subprocess.run([*command, "--out", str(path)], cwd=ROOT, env=env, text=True,
                                   capture_output=True)
        assert protected.returncode == 2 and "must not overwrite" in protected.stderr
        assert len(json.loads(path.read_text(encoding="utf-8"))) == 32
        path.write_text(json.dumps([None]), encoding="utf-8")
        invalid = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=True)
        assert "| invalid | 1 |" in invalid.stdout and "Prediction 0 (invalid)" in invalid.stdout
        for bad in ("{", "{}", "null", "[NaN]"):
            path.write_text(bad, encoding="utf-8")
            try:
                load_predictions(path)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Invalid JSON document accepted: {bad}")
            failed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
            assert failed.returncode == 2 and "error:" in failed.stderr and not failed.stdout
    print("  6. CLI stdout/file equality, invalid-item report and bad-file errors pass")


if __name__ == "__main__":
    started = time.perf_counter()
    test_schema_and_self_score()
    test_hand_computed_errors()
    test_invalid_items()
    test_matching()
    test_field_and_set_scores()
    test_cli_and_bad_files()
    print(f"test_extract_eval: all checks passed ({time.perf_counter() - started:.2f}s)")
