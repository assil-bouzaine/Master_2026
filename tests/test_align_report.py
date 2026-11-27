"""Offline checks of the SO1 HCAT results report (docs/v5_plan.md, R2.3).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_align_report

Tiny gold and run folders exercise exclusion, abstention, tied ranks and area weights.
The scorer is the reference; no matcher, model fitting or network is needed.
"""
import csv
import hashlib
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import numpy as np

from src.kg import align_eval as E
from src.kg import align_report as R


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def fixture(directory):
    """The excluded code has a prediction; the missing included code is an abstention."""
    base = Path(directory)
    gold_path = base / "gold.csv"
    rows = [("D", "dev", 2, "yes", "101"), ("DX", "dev", 1, "no", ""),
            ("A", "eval", 1, "yes", "101"), ("B", "eval", 3, "yes", "102"),
            ("C", "eval", 5, "yes", "103"), ("M", "eval", 7, "yes", "104"),
            ("X", "eval", 9, "no", "")]
    write_csv(gold_path, ("code", "split", "area_ha", "in_gold", "hcat_code"), rows)
    runs = base / "alignment"
    runs.mkdir()
    predictions = [("D", 1, "101"), ("A", 1, "101"), ("B", 1, "999"),
                   ("C", 1, "none"), ("X", 1, "101")]
    write_run(runs / "hcat_fuzzy", "fuzzy", predictions, mtime=1000000000)
    # Tied rank 1: the first B row decides identification, but ranking sees its gold.
    ranked = [*predictions, ("B", 1, "102"), ("B", 2, "102"), ("C", 5, "103"),
              ("C", 5, "103"), ("M", 10, "104")]
    write_run(runs / "hcat_retrieval", "retrieval", ranked, mtime=1000000100)
    return gold_path, runs


def write_run(folder, matcher, predictions, *, mtime):
    folder.mkdir()
    models = {} if matcher == "fuzzy" else {"fixture/model": "requested-commit"}
    config = {"dataset": "v5", "target": "hcat", "matcher": matcher, "models": models}
    (folder / "config.json").write_text(json.dumps(config, sort_keys=True) + "\n", encoding="utf-8")
    meta = {"target": "hcat", "matcher": matcher, "models": models,
            "resolved_commits": {} if not models else {"fixture/model": "resolved-commit"},
            "versions": {"fixture-package": "1.2.3"}, "n_predictions": len(predictions),
            "n_targets": 4, "parse_failures": [{"code": "C", "error": "fixture failure"}]
            if matcher == "llm" else []}
    run_path = folder / "run.json"
    run_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")
    os.utime(run_path, (mtime, mtime))
    write_csv(folder / "predictions.csv", ("code", "rank", "target"), predictions)


def test_scores_and_provenance():
    with TemporaryDirectory() as directory:
        gold_path, runs = fixture(directory)
        result = R.evaluate(directory=runs, gold_path=gold_path)
        assert [record["meta"]["matcher"] for record in result["runs"]] == ["fuzzy", "retrieval"]
        text = R.report(result)
        for record in result["runs"]:
            predictions = E.load_predictions(record["folder"] / "predictions.csv", "hcat")
            for split in R.SPLITS:
                expected = E.score(E.load_gold("hcat", split, gold_path), predictions, "hcat", split)
                assert record["scores"][split] == expected
                strict = expected["scores"]["strict"]
                row = (f"| {record['meta']['matcher']} | {record['folder'].name} | {split} | "
                       f"{expected['counts']['scored_codes']} | {expected['counts']['abstentions']} | "
                       + " | ".join(f"{strict[name]['value']:.6f}" for name in ("precision", "recall", "f1"))
                       + f" | {expected['scores']['area_strict']['f1']['value']:.6f} | ")
                if record["ranked"]:
                    row += " | ".join(f"{expected['ranking'][name]['value']:.6f}"
                                      for name in R._ranking_names([record])) + " |"
                else:
                    row += "— | — | — |"
                assert row in R.main_table(result), row
            digest = hashlib.sha256((record["folder"] / "config.json").read_bytes()).hexdigest()
            assert record["config_sha256"] == digest and digest in text
            assert record["prediction_count"] == sum(map(len, predictions.values()))
        fuzzy, retrieval = result["runs"]
        assert fuzzy["scores"]["eval"]["counts"]["abstentions"] == 2
        assert retrieval["scores"]["eval"]["ranking"]["Hits@1"]["value"] == 0.5
        assert retrieval["scores"]["eval"]["scores"]["strict"]["recall"]["value"] == 0.25
        assert "resolved-commit" in text and "requested-commit" in text and "fixture-package: 1.2.3" in text
        newest = R.datetime.fromtimestamp(1000000100, R.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        assert newest in text
        assert "5 codes have a gold class and 2 are excluded" in text
    print("  1. table matches scorer on both splits; ties, abstentions, exclusions, area and provenance pass")


def test_rank1_and_missing_runs():
    with TemporaryDirectory() as directory:
        gold_path, runs = fixture(directory)
        fuzzy_path = runs / "hcat_fuzzy"
        result = R.evaluate([fuzzy_path], gold_path=gold_path)
        assert not result["runs"][0]["ranked"]
        assert "Hits@" not in R.main_table(result) and "MRR" not in R.main_table(result)
        assert not (runs / "hcat_llm").exists()
        # Neither unrelated runs nor partially copied runs belong to the default list.
        write_run(runs / "other_run", "fuzzy", [], mtime=1000000200)
        (runs / "hcat_pending").mkdir()
        (runs / "hcat_pending" / "run.json").write_text("{}", encoding="utf-8")
        assert [path.name for path in R.discover_runs(runs)] == ["hcat_fuzzy", "hcat_retrieval"]
        assert len(R.evaluate(directory=runs, gold_path=gold_path)["runs"]) == 2
        empty = Path(directory) / "empty"
        empty.mkdir()
        assert "No completed HCAT runs" in R.report(R.evaluate(directory=empty, gold_path=gold_path))
    print("  2. rank-1-only table has no ranking columns; absent LLM, partial and empty run sets pass")


def test_bootstrap():
    with TemporaryDirectory() as directory:
        gold_path, runs = fixture(directory)
        gold = sorted(E.load_gold("hcat", "eval", gold_path), key=lambda row: row["code"])
        predictions = E.load_predictions(runs / "hcat_retrieval" / "predictions.csv", "hcat")
        original = E.score
        with patch.object(E, "score", wraps=original) as scorer:
            first = R.bootstrap(gold, predictions, ranked=True)
        assert scorer.call_count == R.RESAMPLES + 1
        second = R.bootstrap(gold, predictions, ranked=True)
        assert first == second
        estimate = original(gold, predictions, "hcat", "eval")["scores"]["strict"]["f1"]["value"]
        assert first["strict F1"][0] <= estimate <= first["strict F1"][1]
        # Reconstruct the specified draw sequence independently, including duplicate/excluded draws.
        rng = np.random.default_rng(R.SEED)
        values = []
        for _ in range(R.RESAMPLES):
            sample = [gold[index] for index in rng.integers(0, len(gold), size=len(gold))]
            values.append(original(sample, predictions, "hcat", "eval")["scores"]["strict"]["f1"]["value"])
        assert first["strict F1"] == tuple(np.percentile(values, (2.5, 97.5)))
        assert set(first) == {"strict F1"}  # The frozen scorer has no Hits@10.
        assert first != R.bootstrap(gold, predictions, ranked=True, resamples=21, seed=7)

        def scorer_with_optional_measure(*args, **kwargs):
            result = original(*args, **kwargs)
            # A stand-in checks delegation if a future scorer supplies an extra measure.
            result["ranking"]["Hits@10"] = {"value": 0.375}
            return result

        with patch.object(E, "score", side_effect=scorer_with_optional_measure):
            interval = R.bootstrap(gold, predictions, ranked=True, resamples=10)
            assert interval["Hits@10"] == (0.375, 0.375)
            assert "Hits@10" not in R.bootstrap(gold, predictions, ranked=False, resamples=10)
    print("  3. 2,000 scorer-based resamples reproduce exact percentiles and contain the point estimate")
    print("     optional Hits@10 is delegated when supplied; no extra measure is invented")


def test_llm_and_repeatable_cli():
    with TemporaryDirectory() as directory:
        gold_path, runs = fixture(directory)
        write_run(runs / "hcat_llm", "llm", [("D", 1, "101"), ("A", 1, "101"),
                                            ("B", 1, "999"), ("C", 1, "")], mtime=1000000050)
        result = R.evaluate(directory=runs, gold_path=gold_path)
        llm = next(record for record in result["runs"] if record["meta"]["matcher"] == "llm")
        assert llm["scores"]["eval"]["counts"]["abstentions"] == 2
        text = R.report(result)
        assert f"| {llm['prediction_count']} | 1 |" in text
        output = Path(directory) / "report.md"
        original_write = R.write_report
        arguments = ["--runs", *(str(path) for path in reversed(R.discover_runs(runs)))]
        with (patch.object(E, "HCAT_GOLD", gold_path),
              patch.object(R, "write_report", side_effect=lambda value: original_write(value, output))):
            with redirect_stdout(io.StringIO()) as printed:
                R.main(arguments)
            first = output.read_bytes()
            assert R.main_table(result) in printed.getvalue()
            with redirect_stdout(io.StringIO()):
                R.main(arguments)
            assert first == output.read_bytes() == text.encode("utf-8")
            with patch.object(R, "discover_runs", return_value=R.discover_runs(runs)):
                with redirect_stdout(io.StringIO()):
                    R.main([])
            assert first == output.read_bytes()
        shuffled = R.evaluate(list(reversed(R.discover_runs(runs))), gold_path=gold_path)
        assert R.report(shuffled) == text
    print("  4. LLM parse failures, explicit/default CLI, sorted runs and identical generated bytes pass")


def test_bad_provenance():
    with TemporaryDirectory() as directory:
        gold_path, runs = fixture(directory)
        path = runs / "hcat_fuzzy"
        run_path = path / "run.json"
        meta = json.loads(run_path.read_text(encoding="utf-8"))
        meta["n_predictions"] += 1
        run_path.write_text(json.dumps(meta), encoding="utf-8")
        try:
            R.evaluate([path], gold_path=gold_path)
        except ValueError as error:
            assert "n_predictions" in str(error)
        else:
            raise AssertionError("Mismatched prediction count accepted")
        output = Path(directory) / "must_not_exist.md"
        with (patch.object(E, "HCAT_GOLD", gold_path), patch.object(R, "OUTPUT", output),
              redirect_stderr(io.StringIO())):
            try:
                R.main(["--runs", str(path)])
            except SystemExit as error:
                assert error.code == 2
            else:
                raise AssertionError("CLI accepted invalid provenance")
        assert not output.exists()
    print("  5. inconsistent provenance is refused before writing a report")


if __name__ == "__main__":
    started = perf_counter()
    test_scores_and_provenance()
    test_rank1_and_missing_runs()
    test_bootstrap()
    test_llm_and_repeatable_cli()
    test_bad_provenance()
    print(f"test_align_report: all checks passed ({perf_counter() - started:.2f}s)")
