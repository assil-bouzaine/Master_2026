"""Offline checks of the pre-matcher alignment scorer (v5 plan R2.3, subject SO1).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_align_eval

Small fixtures have hand-calculated denominators. The real EuroCrops mapping is only read;
hcat-gold writes to temporary paths in tests. No matcher, network or fitting is involved.
"""
import csv
import io
import math
import os
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.kg import align_eval as E


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (actual, expected)


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def agrovoc_row(code, concept="c_3360", relation="exactMatch", area="1", split="eval", alternatives=""):
    return dict(code=code, concept=concept, relation=relation, area_ha=area, split=split,
                alternatives=alternatives)


def prediction(code, target="c_3360", rank="1", relation="", score=""):
    return dict(code=code, target=target, rank=rank, relation=relation, score=score)


def evaluate(rows, predictions, kind="agrovoc", split="eval"):
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        gold_path = write_csv(base / "gold.csv", rows, tuple(rows[0]))
        pred_path = write_csv(base / "pred.csv", predictions, ("code", "rank", "target", "relation", "score"))
        return E.score(E.load_gold(kind, split, gold_path), E.load_predictions(pred_path, kind), kind, split)


def assert_metric(metric, numerator, denominator):
    close(metric["numerator"], numerator)
    close(metric["denominator"], denominator)
    close(metric["value"], numerator / denominator if denominator else 0)


def test_real_hcat_gold():
    with tempfile.TemporaryDirectory() as directory:
        first, second = (Path(directory) / name for name in ("first.csv", "second.csv"))
        command = [sys.executable, "-m", "src.kg.align_eval", "hcat-gold", "--out"]
        env = {**os.environ, "PFE_DATASET": "v5", "PYTHONIOENCODING": "utf-8"}
        first_run = subprocess.run([*command, str(first)], cwd=E.ROOT, env=env, capture_output=True,
                                   text=True, check=True)
        subprocess.run([*command, str(second)], cwd=E.ROOT, env=env, capture_output=True, text=True, check=True)
        assert first.read_bytes() == second.read_bytes()
        rows = E._read_csv(first, E.HCAT_COLUMNS)
        template = E._read_csv(E.AGROVOC_GOLD, ("code", "split", "area_ha"))
        assert len(rows) == 198
        assert [(row["code"], row["split"], row["area_ha"]) for row in rows] == [
            (row["code"], row["split"], row["area_ha"]) for row in template]
        included = [row for row in rows if row["in_gold"] == "yes"]
        excluded = [row for row in rows if row["in_gold"] == "no"]
        assert len(included) == 183 and len(excluded) == 15
        assert len({row["hcat_code"] for row in included}) == 119
        assert all(row["hcat_code"] and row["hcat_name"] and row["source_file"] for row in included)
        assert all(not row["hcat_code"] and not row["source_file"] for row in excluded)
        for split, count, omitted, distinct in (("dev", 37, 3, 33), ("eval", 146, 12, 99)):
            subset = [row for row in included if row["split"] == split]
            assert len(subset) == count
            assert sum(row["split"] == split for row in excluded) == omitted
            assert len({row["hcat_code"] for row in subset}) == distinct
            gold = E.load_gold("hcat", split, first)
            predictions = {row["code"]: [{"rank": 1, "target": row["hcat_code"], "relation": ""}]
                           for row in included}
            result = E.score(gold, predictions, "hcat", split)
            assert result["counts"]["scored_codes"] == count
            assert result["counts"]["gold_none"] == 0
            assert len(result["excluded"]) == omitted
            assert result["relation_accuracy"] is None
            assert all(metric["value"] == 1 for group in result["scores"].values() for metric in group.values())
        metadata = first.read_text(encoding="utf-8")
        assert E.EUROCROPS_COMMIT in metadata and "CC BY-SA 4.0" in metadata
        assert "CSE: fr_2018.csv=3301061000; fr_other_years.csv=3399000000" in metadata
        assert "Source conflict: CSE" in first_run.stdout
    print("  1. Real HCAT gold: deterministic bytes, 183 in gold / 15 excluded / 119 targets; split counts pass")


def test_hcat_precedence_and_exclusion():
    # CSE is outside the 198 study codes, so a temporary study template exercises the real conflict.
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        template = write_csv(base / "template.csv", [
            dict(code="CSE", label="", area_ha="3", split="eval"),
            dict(code="JAC", label="", area_ha="7", split="eval"),
        ], ("code", "label", "area_ha", "split"))
        out = base / "hcat.csv"
        rows, conflicts = E.hcat_gold(out, template)
        assert len(conflicts) == 1
        assert rows[0]["hcat_code"] == "3301061000" and rows[0]["source_file"] == "fr_2018.csv"
        assert rows[1]["in_gold"] == "no"
        pred = write_csv(base / "pred.csv", [dict(code="CSE", rank="1", target="3301061000"),
                                             dict(code="JAC", rank="1", target="3399000000")],
                         ("code", "rank", "target"))
        result = E.score(E.load_gold("hcat", "eval", out), E.load_predictions(pred, "hcat"), "hcat", "eval")
        assert_metric(result["scores"]["strict"]["precision"], 1, 1)
        assert_metric(result["scores"]["area_strict"]["recall"], 3, 3)
        assert result["excluded"] == ["JAC"]
        assert "JAC" in E.markdown_report(result)
    print("  2. Actual CSE conflict follows 2018 priority; predictions for excluded codes have no effect")


def test_perfect_abstentions_and_none():
    rows = [agrovoc_row("A"), agrovoc_row("B", "c_3360"),
            agrovoc_row("N", "", "none"), agrovoc_row("M", "", "none")]
    perfect = evaluate(rows, [prediction("A"), prediction("B", E.normalise_target("c_3360", "agrovoc")),
                              prediction("N", "none")])
    for group in perfect["scores"].values():
        assert all(metric["value"] == 1 for metric in group.values())
    assert perfect["counts"]["correct_strict_including_none"] == 4
    assert_metric(perfect["scores"]["strict"]["precision"], 2, 2)
    assert_metric(perfect["ranking"]["Hits@1"], 2, 2)
    for predictions in ([], [prediction("A", ""), prediction("B", "none")]):
        abstain = evaluate(rows, predictions)
        for group in abstain["scores"].values():
            assert all(metric["value"] == 0 for metric in group.values())
        assert abstain["counts"]["abstentions"] == 4
        assert [row["strict"] for row in abstain["per_code"]] == [False, False, True, True]
        assert_metric(abstain["scores"]["strict"]["precision"], 0, 0)
        assert_metric(abstain["scores"]["strict"]["recall"], 0, 2)
    false_positives = evaluate(rows, [prediction(code) for code in ("A", "B", "N", "M")])
    assert_metric(false_positives["scores"]["strict"]["precision"], 2, 4)
    assert_metric(false_positives["scores"]["strict"]["recall"], 2, 2)
    assert_metric(false_positives["scores"]["strict"]["f1"], 4, 6)
    assert_metric(false_positives["ranking"]["MRR"], 2, 2)
    print("  3. Perfect scores = 1; abstentions = 0; two gold-none false positives give P=1/2, R=1, F1=2/3")


def test_alternatives_relations_and_area():
    rows = [agrovoc_row("A", area="1", alternatives="c_1; c_2"),
            agrovoc_row("B", area="3"), agrovoc_row("C", area="5"),
            agrovoc_row("D", area="7"), agrovoc_row("N", "", "none", area="9")]
    result = evaluate(rows, [prediction("A", "c_1", relation="exactMatch"),
                             prediction("B", relation="closeMatch"),
                             prediction("C", relation="exactMatch"), prediction("D"),
                             prediction("N", relation="broadMatch")])
    assert_metric(result["scores"]["strict"]["precision"], 3, 5)
    assert_metric(result["scores"]["strict"]["recall"], 3, 4)
    assert_metric(result["scores"]["strict"]["f1"], 6, 9)
    assert_metric(result["scores"]["lenient"]["precision"], 4, 5)
    assert_metric(result["scores"]["lenient"]["recall"], 4, 4)
    assert_metric(result["scores"]["lenient"]["f1"], 8, 9)
    # A's alternative and D's missing relation never enter relation accuracy; N is a wrong target.
    assert_metric(result["relation_accuracy"], 1, 2)
    assert_metric(result["scores"]["area_strict"]["precision"], 15, 25)
    assert_metric(result["scores"]["area_strict"]["recall"], 15, 16)
    assert_metric(result["scores"]["area_strict"]["f1"], 30, 41)
    assert_metric(result["scores"]["area_lenient"]["precision"], 16, 25)
    assert_metric(result["scores"]["area_lenient"]["recall"], 16, 16)
    assert_metric(result["scores"]["area_lenient"]["f1"], 32, 41)
    assert result["per_code"][0]["strict"] is False and result["per_code"][0]["lenient"] is True
    assert result["per_code"][0]["gold_rank"] is None  # Ranking is always the exact gold concept.
    report = E.markdown_report(result)
    assert "| relation accuracy | 0.500000 | 1 | 2 |" in report
    assert "| area_strict f1 | 0.731707 | 30 | 41 |" in report
    zero = evaluate([agrovoc_row("Z", area="0")], [prediction("Z")])
    assert all(metric["value"] == 0 for metric in zero["scores"]["area_strict"].values())
    assert_metric(zero["relation_accuracy"], 0, 0)
    print("  4. Alternatives, relation accuracy=1/2, unequal-area fractions, and zero-weight ratios pass")


def test_rankings_and_ties():
    rows = [agrovoc_row(code) for code in ("A", "B", "C", "D", "E")]
    rows.append(agrovoc_row("N", "", "none"))
    predictions = [prediction("A", "c_1", rank="1", score="-1"),
                   prediction("A", rank="1", score="999"),  # Tie: first row decides top-1 only.
                   prediction("A", rank="1"),               # Duplicate earns no extra hit.
                   prediction("B", "c_1", rank="1"), prediction("B", rank="2"),
                   prediction("B", "c_2", rank="2"),
                   prediction("C", rank="5"), prediction("C", "c_1", rank="1"),
                   prediction("D", "c_1", rank="1"), prediction("D", rank="6"),
                   prediction("E", "none", rank="1"), prediction("E", rank="3")]
    result = evaluate(rows, predictions)
    assert [row["gold_rank"] for row in result["per_code"]] == [1, 2, 5, 6, 3, None]
    assert_metric(result["ranking"]["Hits@1"], 1, 5)
    assert_metric(result["ranking"]["Hits@5"], 4, 5)
    assert_metric(result["ranking"]["MRR"], 1 + 1/2 + 1/5 + 1/6 + 1/3, 5)
    assert_metric(result["scores"]["strict"]["precision"], 0, 4)
    assert not result["per_code"][0]["strict"]
    assert result["per_code"][-1]["strict"]
    no_top1 = evaluate([agrovoc_row("A")], [prediction("A", rank="2")])
    assert no_top1["counts"]["abstentions"] == 1
    assert_metric(no_top1["ranking"]["MRR"], 1/2, 1)
    print("  5. Supplied ranks, gaps, duplicate targets, tied ranks, score independence and top-1 abstention pass")


def test_missing_gold_and_split_filter():
    rows = [agrovoc_row("D", split="dev"), agrovoc_row("E", relation="", split="eval"),
            agrovoc_row("F", relation="", split="eval")]
    result = evaluate(rows, [prediction("D")], split="dev")
    assert_metric(result["scores"]["strict"]["recall"], 1, 1)
    try:
        evaluate(rows, [], split="eval")
    except ValueError as error:
        assert "2 missing gold judgements" in str(error)
    else:
        raise AssertionError("Unjudged eval gold was accepted")
    rows = [agrovoc_row("D", split="dev"), agrovoc_row("E", split="eval")]
    result = evaluate(rows, [prediction("D"), prediction("E", "c_1"), prediction("UNKNOWN")], split="eval")
    assert result["counts"]["split_codes"] == 1 and result["counts"]["non_abstaining"] == 1
    assert result["ignored_prediction_codes"] == ["D", "UNKNOWN"]
    assert_metric(result["scores"]["strict"]["recall"], 0, 1)
    # A matcher-supplied split column must not change which gold codes are scored.
    with tempfile.TemporaryDirectory() as directory:
        path = write_csv(Path(directory) / "pred.csv", [dict(code="E", rank="1", target="c_3360", split="dev")],
                         ("code", "rank", "target", "split"))
        loaded = E.load_predictions(path, "agrovoc")
        assert loaded["E"][0]["target"] == E.normalise_target("c_3360", "agrovoc")
        gold_path = write_csv(Path(directory) / "gold.csv", rows, tuple(rows[0]))
        result = E.score(E.load_gold("agrovoc", "eval", gold_path), loaded, "agrovoc", "eval")
        assert_metric(result["scores"]["strict"]["recall"], 1, 1)
    missing_hcat = [dict(code="A", area_ha="1", split="eval", in_gold="yes", hcat_code=""),
                    dict(code="B", area_ha="1", split="eval", in_gold="no", hcat_code="")]
    try:
        evaluate(missing_hcat, [], "hcat")
    except ValueError as error:
        assert "1 missing gold judgements: A" in str(error)
    else:
        raise AssertionError("HCAT included code without a target was accepted")
    only_none = evaluate([agrovoc_row("N", "", "none")], [])
    assert_metric(only_none["ranking"]["MRR"], 0, 0)
    assert_metric(only_none["scores"]["strict"]["recall"], 0, 0)
    print("  6. Missing-judgement counts and split isolation pass; prediction split is ignored")


def test_validation_and_cli():
    assert E.normalise_target(" c_3360 ", "agrovoc") == "http://aims.fao.org/aos/agrovoc/c_3360"
    assert E.normalise_target("c_ab12-XY_z", "agrovoc").endswith("/c_ab12-XY_z")
    assert E.normalise_target(" 00123 ", "hcat") == "00123"
    for kind, value in (("hcat", "123.0"), ("hcat", "1e3"), ("hcat", "abc"),
                        ("agrovoc", "3360"), ("agrovoc", "https://example.org/c_3360")):
        try:
            E.normalise_target(value, kind)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Bad target accepted: {value}")
    for row in (prediction("A", rank="0"), prediction("A", rank="1.5"), prediction(""),
                prediction("A", relation="invalid"), prediction("A", relation="none"),
                prediction("A", target="none", relation="none")):
        try:
            evaluate([agrovoc_row("A")], [row])
        except ValueError:
            pass
        else:
            raise AssertionError(f"Bad prediction accepted: {row}")
    for rows in ([agrovoc_row("A"), agrovoc_row("A")], [agrovoc_row("A", area="nan")],
                 [agrovoc_row("A", area="-1")], [agrovoc_row("A", "", "exactMatch")],
                 [agrovoc_row("A", "c_3360", "none")], [agrovoc_row("A", "", "none", alternatives="c_1")]):
        try:
            evaluate(rows, [])
        except ValueError:
            pass
        else:
            raise AssertionError(f"Bad gold accepted: {rows}")
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        rows = [agrovoc_row("A"), agrovoc_row("N", "", "none")]
        gold_path = write_csv(base / "gold.csv", rows, tuple(rows[0]))
        pred_path = write_csv(base / "pred.csv", [prediction("A", relation="exactMatch")],
                              ("code", "rank", "target", "relation", "score"))
        report_path = base / "report.md"
        arguments = ["score", "--gold", "agrovoc", "--pred", str(pred_path), "--split", "eval"]
        with patch.object(E, "AGROVOC_GOLD", gold_path):
            printed = io.StringIO()
            with redirect_stdout(printed):
                E.main([*arguments, "--out", str(report_path)])
            assert printed.getvalue() == report_path.read_text(encoding="utf-8")
            assert "| strict precision | 1.000000 | 1 | 1 |" in printed.getvalue()
            for protected in (gold_path, pred_path, E.HCAT_GOLD, E.EUROCROPS / "fr_2018.csv"):
                with redirect_stderr(io.StringIO()):
                    try:
                        E.main([*arguments, "--out", str(protected)])
                    except SystemExit as error:
                        assert error.code == 2
                    else:
                        raise AssertionError("CLI overwrote an input")
            gold_path.write_text("code,area_ha,split,relation,concept,alternatives\nA,1,eval,,,\n", encoding="utf-8")
            errors, printed = io.StringIO(), io.StringIO()
            with redirect_stderr(errors), redirect_stdout(printed):
                try:
                    E.main([*arguments, "--out", str(base / "must_not_exist.md")])
                except SystemExit as error:
                    assert error.code == 2
                else:
                    raise AssertionError("CLI scored unjudged gold")
            assert "1 missing gold judgements" in errors.getvalue()
            assert not printed.getvalue() and not (base / "must_not_exist.md").exists()
        # A multiline quoted cell starting with '#' is data, rather than a provenance comment.
        pred_path.write_text('code,rank,target,score\nA,1,c_3360,"line one\n# line two"\n', encoding="utf-8")
        assert E.load_predictions(pred_path, "agrovoc")["A"][0]["rank"] == 1
        pred_path.write_text("code,rank,target\nA,1,c_3360,extra\n", encoding="utf-8")
        try:
            E.load_predictions(pred_path, "agrovoc")
        except ValueError as error:
            assert "number of cells" in str(error)
        else:
            raise AssertionError("Malformed CSV accepted")
    print("  7. Normalization, invalid inputs, CLI errors, stdout/file equality and input protection pass")


if __name__ == "__main__":
    started = time.perf_counter()
    test_real_hcat_gold()
    test_hcat_precedence_and_exclusion()
    test_perfect_abstentions_and_none()
    test_alternatives_relations_and_area()
    test_rankings_and_ties()
    test_missing_gold_and_split_filter()
    test_validation_and_cli()
    print(f"test_align_eval: all checks passed ({time.perf_counter() - started:.2f}s)")
