"""Report frozen RPG → HCAT3 matcher runs (docs/v5_plan.md, R2.3, subject SO1).

    PFE_DATASET=v5 python -m src.kg.align_report [--runs DIR ...]

The fixed align_eval scorer supplies every measure, including bootstrap replicates.
Missing matchers are allowed because GPU runs may arrive separately. Only local run
files and gold are read; nothing is fitted and no network connection is needed.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np

from src.config import ROOT
from src.kg import align_eval as E

RUNS = ROOT / "results" / "v5" / "alignment"
OUTPUT = ROOT / "docs" / "alignment_hcat_v5.md"
SPLITS = ("dev", "eval")
RESAMPLES = 2000
SEED = 20261127


def discover_runs(directory=RUNS):
    """Ignore incomplete folders until both the predictions and run metadata arrive."""
    return sorted(path for path in Path(directory).glob("hcat_*")
                  if path.is_dir() and all((path / name).is_file()
                                          for name in ("predictions.csv", "run.json")))


def bootstrap(gold, predictions, *, ranked, resamples=RESAMPLES, seed=SEED):
    """Resample split codes, retaining duplicates, and call the scorer each time.

    Excluded codes can be drawn but the scorer still excludes them. Resetting the
    seed for each run gives all matchers the same code samples for comparison.
    Hits@10 is included only if the fixed scorer actually supplies that measure.
    """
    if not gold or resamples < 1:
        raise ValueError("Bootstrap needs gold codes and at least one resample")
    point = E.score(gold, predictions, "hcat", "eval")
    values = {"strict F1": []}
    if ranked and "Hits@10" in point["ranking"]:
        values["Hits@10"] = []
    rng = np.random.default_rng(seed)
    for _ in range(resamples):
        sample = [gold[index] for index in rng.integers(0, len(gold), size=len(gold))]
        result = E.score(sample, predictions, "hcat", "eval")
        values["strict F1"].append(result["scores"]["strict"]["f1"]["value"])
        if "Hits@10" in values:
            values["Hits@10"].append(result["ranking"]["Hits@10"]["value"])
    return {name: tuple(float(value) for value in np.percentile(samples, (2.5, 97.5)))
            for name, samples in values.items()}


def evaluate(runs=None, *, directory=RUNS, gold_path=None):
    """Read provenance and use the same gold and scoring functions for every run."""
    gold = {split: sorted(E.load_gold("hcat", split, gold_path), key=lambda row: row["code"])
            for split in SPLITS}
    paths = discover_runs(directory) if runs is None else sorted({Path(path).resolve() for path in runs})
    records = []
    for path in paths:
        run_path = path / "run.json"
        meta = json.loads(run_path.read_text(encoding="utf-8"))
        config_path = path / "config.json"
        config_bytes = config_path.read_bytes()
        config = json.loads(config_bytes)
        if meta.get("target") != "hcat" or config.get("target") != "hcat":
            raise ValueError(f"{path}: expected HCAT run and configuration")
        if config.get("dataset") != "v5" or meta.get("matcher") != config.get("matcher"):
            raise ValueError(f"{path}: expected dataset v5 and matching matcher metadata")
        predictions = E.load_predictions(path / "predictions.csv", "hcat")
        count = sum(len(rows) for rows in predictions.values())
        if "n_predictions" in meta and meta["n_predictions"] != count:
            raise ValueError(f"{path}: n_predictions differs from the prediction CSV row count")
        ranked = any(row["rank"] > 1 for rows in predictions.values() for row in rows)
        records.append({"folder": path, "meta": meta, "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
                        "prediction_count": count, "ranked": ranked, "mtime": run_path.stat().st_mtime,
                        "scores": {split: E.score(gold[split], predictions, "hcat", split) for split in SPLITS},
                        "intervals": bootstrap(gold["eval"], predictions, ranked=ranked)})
    records.sort(key=lambda record: (record["meta"]["matcher"], str(record["folder"])))
    return {"gold": gold, "runs": records}


def _cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _path(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _mapping(values):
    return "; ".join(f"{_cell(key)}: {_cell(value)}" for key, value in sorted(values.items())) or "none"


def _ranking_names(records):
    names = {name for record in records if record["ranked"]
             for result in record["scores"].values() for name in result["ranking"]}
    return sorted(names, key=lambda name: (0, int(name.split("@")[1]))
                  if name.startswith("Hits@") else (1, name))


def main_table(result):
    """Keep ranking cells empty for runs that supply only rank 1."""
    names = _ranking_names(result["runs"])
    headers = ["Matcher", "Run", "Split", "Scored codes", "Abstentions", "Strict P", "Strict R",
               "Strict F1", "Area-weighted strict F1", *names]
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * 3 + ["---:"] * (len(headers) - 3)) + " |"]
    for record in result["runs"]:
        for split in SPLITS:
            score = record["scores"][split]
            strict = score["scores"]["strict"]
            cells = [record["meta"]["matcher"], record["folder"].name, split,
                     score["counts"]["scored_codes"], score["counts"]["abstentions"],
                     *(f"{strict[name]['value']:.6f}" for name in ("precision", "recall", "f1")),
                     f"{score['scores']['area_strict']['f1']['value']:.6f}"]
            cells += [f"{score['ranking'][name]['value']:.6f}" if record["ranked"] and name in score["ranking"]
                      else "—" for name in names]
            lines.append("| " + " | ".join(map(_cell, cells)) + " |")
    return "\n".join(lines)


def report(result):
    records, gold = result["runs"], result["gold"]
    all_gold = [item for rows in gold.values() for item in rows]
    included = sum(item["in_gold"] for item in all_gold)
    targets = sorted({record["meta"]["n_targets"] for record in records if "n_targets" in record["meta"]})
    target_text = "/".join(map(str, targets)) if targets else "384"
    summaries = [f"{_cell(record['meta']['matcher'])} (run `{_cell(record['folder'].name)}`; "
                 f"models and requested commits: {_mapping(record['meta'].get('models', {}))}; "
                 f"resolved commits: {_mapping(record['meta'].get('resolved_commits', {}))}; "
                 f"package versions: {_mapping(record['meta'].get('versions', {}))})" for record in records]
    lines = ["# RPG → HCAT3 alignment results (v5, generated)", "",
             "Generated by `python -m src.kg.align_report`. Do not edit by hand.", ""]
    if records:
        newest = datetime.fromtimestamp(max(record["mtime"] for record in records), timezone.utc)
        lines += [f"Newest run.json modification time (UTC): {newest:%Y-%m-%d %H:%M:%S}. "
                  "The run files contain no explicit run timestamp; file modification time is used.", ""]
    lines += [f"The task maps {len(all_gold)} RPG crop codes, using their French labels, to one of "
              f"{target_text} HCAT3 classes. Gold is the EuroCrops authors' French mapping "
              f"(CC BY-SA 4.0): {included} codes have a gold class and {len(all_gold) - included} are excluded. "
              f"The fixed splits contain {len(gold['dev'])} dev codes and {len(gold['eval'])} eval codes "
              "before exclusions. The three planned matchers are fuzzy label matching, retrieval and LLM "
              "selection from retrieved candidates. Available runs: " + ("; ".join(summaries) or "none") + ". "
              "The prompt and settings were fixed before any run. The eval split is reported; the dev split "
              "was never used to choose anything.", "", "## Scores", "", main_table(result), "",
              "All values come from `align_eval.score`, on a 0–1 scale. Excluded gold codes are omitted "
              "from every measure. Abstentions include empty targets, none and missing rank 1. Strict "
              "identification uses the first CSV row at rank 1, even when tied. Ranking uses the exact gold "
              "target's best supplied rank; ties and gaps are preserved and scores do not change ordering. "
              "Area weighting uses the scorer's hectare denominators. Ranking columns appear only when "
              "a run supplies ranks beyond 1; — means that ranking is not reported for that run.", "",
              "## Eval uncertainty", "",
              f"95% percentile bootstrap intervals use {RESAMPLES:,} resamples and seed {SEED}. "
              "Codes are drawn with replacement from the full eval split, including excluded codes, which "
              "the scorer still excludes. Each resample is scored by calling `align_eval.score` on the "
              "resampled gold; duplicate draws retain their multiplicity. The same draws are used for "
              "every run. Endpoints are the 2.5th and 97.5th percentiles with linear interpolation. "
              "No dev interval is computed.", "",
              "| Matcher | Run | Measure | Point estimate | 95% interval |", "|---|---|---|---:|---|"]
    for record in records:
        for name, (low, high) in record["intervals"].items():
            score = record["scores"]["eval"]
            point = (score["scores"]["strict"]["f1"]["value"] if name == "strict F1"
                     else score["ranking"][name]["value"])
            lines.append(f"| {_cell(record['meta']['matcher'])} | {_cell(record['folder'].name)} | "
                         f"{name} | {point:.6f} | [{low:.6f}, {high:.6f}] |")
    if not any("Hits@10" in record["intervals"] for record in records):
        lines += ["", "No Hits@10 interval is reported: it requires both ranks beyond 1 and a Hits@10 "
                  "measure returned by the fixed scorer. The current scorer returns Hits@1, Hits@5 and "
                  "MRR, without Hits@10; this report does not add a measure to it."]
    lines += ["", "## Run provenance", "",
              "Prediction counts are CSV rows, including ranked candidates and excluded codes. "
              "Configuration SHA-256 hashes cover the exact config.json bytes. Parse failures are read "
              "from run.json for LLM runs; they remain abstentions in the scores.", "",
              "| Matcher | Folder | config.json SHA-256 | Predictions | LLM parse failures |",
              "|---|---|---|---:|---:|"]
    for record in records:
        meta = record["meta"]
        failures = len(meta["parse_failures"]) if "parse_failures" in meta else "not recorded"
        lines.append(f"| {_cell(meta['matcher'])} | `{_cell(_path(record['folder']))}` | "
                     f"`{record['config_sha256']}` | {record['prediction_count']} | "
                     f"{failures if meta['matcher'] == 'llm' else '—'} |")
    if not records:
        lines += ["", "No completed HCAT runs are available. Regenerate when run folders arrive."]
    return "\n".join(lines) + "\n"


def write_report(result, output=OUTPUT):
    Path(output).write_text(report(result), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", type=Path, help="run folders; default: completed hcat_* folders")
    args = parser.parse_args(argv)
    started = perf_counter()
    try:
        result = evaluate(args.runs)
        write_report(result)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(main_table(result))
    print(f"-> {OUTPUT.relative_to(ROOT)} ({perf_counter() - started:.2f}s)")


if __name__ == "__main__":
    main()
