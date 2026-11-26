"""Score RPG crop-code alignments before running matchers (v5 plan R2.3, subject SO1).

    python -m src.kg.align_eval hcat-gold [--out configs/lu_hcat_gold.csv]
    python -m src.kg.align_eval score --gold agrovoc|hcat --pred FILE --split dev|eval

Prediction CSV columns: code, rank, target, with optional relation and score. Rank is a
positive integer; scores never affect ordering. Targets are AGROVOC short ids/full IRIs or
digit strings for HCAT3. Empty targets and 'none' mean abstention. Missing rank 1 also means
abstention. If rank 1 is tied, the first row in the file supplies the single prediction.
Ranking measures use the best supplied rank of the exact gold target: ties share that rank,
gaps stay, and duplicates cannot earn extra credit. Thus Hits@1 can differ from top-1 accuracy
when rank 1 is tied. These choices are fixed here before any matcher output is seen.

Strict identification uses the gold target; lenient identification also accepts AGROVOC's
pre-labelled alternatives. A gold-none abstention is correct in the audit table but earns no
true positive. Gold-none concept predictions enter precision, while recall and ranking use
only gold codes with concepts. Area weighting sums hectares over those same denominator sets
(the explicit T87 rule). Relation accuracy uses non-abstaining, strictly correct targets with
a supplied relation. Undefined ratios are zero. HCAT in_gold=no means excluded, never none.

EuroCrops gold keeps its CC BY-SA 4.0 provenance separate from the ontology. No model, fitting
or network is used. Invalid input is refused rather than silently repaired or discarded.
"""
import argparse
import csv
import io
import math
import re
from itertools import dropwhile
from pathlib import Path

from src.config import ROOT
from src.kg.agrovoc_gold import RELATIONS, _normalise_concept

AGROVOC_GOLD = ROOT / "configs" / "lu_agrovoc_gold.csv"
HCAT_GOLD = ROOT / "configs" / "lu_hcat_gold.csv"
EUROCROPS = ROOT / "data" / "raw" / "eurocrops" / "2026-11-26"
EUROCROPS_COMMIT = "b4331adc3dec584ca0e86f0f2d5c881e53cb3b68"
HCAT_COLUMNS = ("code", "label", "area_ha", "split", "hcat_code", "hcat_name", "in_gold", "source_file")


def _read_csv(path, required):
    """Allow a leading provenance comment block, while preserving quoted multiline cells."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(dropwhile(lambda line: line.startswith("#"), stream))
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)) or not set(required).issubset(columns):
            raise ValueError(f"{path}: expected unique columns including {', '.join(required)}")
        rows = list(reader)
    for number, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{path}: row {number} has the wrong number of cells")
    return rows


def normalise_target(value, kind):
    """Match worksheet normalization exactly; keep HCAT codes as strings, never floats."""
    value = value.strip()
    if not value or value.lower() == "none":
        return ""
    if kind == "agrovoc":
        return _normalise_concept(value)
    if kind != "hcat" or not re.fullmatch(r"[0-9]+", value):
        raise ValueError(f"{value!r}: expected an HCAT code containing only digits")
    return value


def _unique_codes(rows, field, source):
    seen = set()
    for row in rows:
        code = row[field].strip()
        if not code or code in seen:
            raise ValueError(f"{source}: empty or duplicate code {code!r}")
        seen.add(code)


def hcat_gold(out=HCAT_GOLD, agrovoc=AGROVOC_GOLD, eurocrops=EUROCROPS):
    """Prefer the 2018 mapping and retain every RPG code, its order, split and provenance."""
    eurocrops, out = Path(eurocrops), Path(out)
    sources = [eurocrops / name for name in ("fr_2018.csv", "fr_other_years.csv")]
    protected = [Path(agrovoc), *sources, eurocrops / "HCAT3.csv", eurocrops / "LICENSE"]
    _protect_output(out, protected)
    rows = _read_csv(agrovoc, ("code", "label", "area_ha", "split"))
    _unique_codes(rows, "code", agrovoc)
    mappings = []
    for source in sources:
        table = _read_csv(source, ("original_code", "HCAT3_code", "HCAT3_name"))
        _unique_codes(table, "original_code", source)
        mappings.append({row["original_code"]: row for row in table})
    canonical = _read_csv(eurocrops / "HCAT3.csv", ("HCAT3_code", "HCAT3_name"))
    _unique_codes(canonical, "HCAT3_code", eurocrops / "HCAT3.csv")
    names = {row["HCAT3_code"]: row["HCAT3_name"] for row in canonical}
    conflicts = []
    for code in sorted(mappings[0].keys() & mappings[1].keys()):
        first, other = (mapping[code] for mapping in mappings)
        if first["HCAT3_code"] != other["HCAT3_code"]:
            conflicts.append(f"{code}: fr_2018.csv={first['HCAT3_code']}; "
                             f"fr_other_years.csv={other['HCAT3_code']}; fr_2018.csv wins")
    output = []
    for row in rows:
        if row["split"] not in ("dev", "eval"):
            raise ValueError(f"{row['code']}: invalid split {row['split']!r}")
        item = {key: row[key] for key in ("code", "label", "area_ha", "split")}
        item.update(hcat_code="", hcat_name="", in_gold="no", source_file="")
        for source, mapping in zip(sources, mappings):
            if row["code"] not in mapping:
                continue
            match = mapping[row["code"]]
            target = normalise_target(match["HCAT3_code"], "hcat")
            if not target or names.get(target) != match["HCAT3_name"]:
                raise ValueError(f"{row['code']}: mapped target/name is absent from HCAT3.csv")
            item.update(hcat_code=target, hcat_name=match["HCAT3_name"], in_gold="yes",
                        source_file=source.name)
            break
        output.append(item)
    buffer = io.StringIO(newline="")
    buffer.write("# Derived from the EuroCrops authors' French RPG mapping; licence CC BY-SA 4.0.\n")
    buffer.write(f"# EuroCrops commit: {EUROCROPS_COMMIT}\n")
    buffer.write("# Source: csvs/country_mappings/fr_2018.csv, fr_other_years.csv; hcat_core/HCAT3.csv\n")
    buffer.write("# Snapshot: data/raw/eurocrops/2026-11-26/; 2018 mapping takes priority.\n")
    for conflict in conflicts:
        buffer.write(f"# Source conflict: {conflict}\n")
    writer = csv.DictWriter(buffer, fieldnames=HCAT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buffer.getvalue().encode("utf-8"))
    return output, conflicts


def load_gold(kind, split, path=None):
    """Refuse incomplete judgements in the requested split before examining predictions."""
    if kind not in ("agrovoc", "hcat") or split not in ("dev", "eval"):
        raise ValueError("Expected gold agrovoc|hcat and split dev|eval")
    path = path if path is not None else (AGROVOC_GOLD if kind == "agrovoc" else HCAT_GOLD)
    fields = ("relation", "concept", "alternatives") if kind == "agrovoc" else ("in_gold", "hcat_code")
    rows = _read_csv(path, ("code", "split", "area_ha", *fields))
    _unique_codes(rows, "code", path)
    if any(row["split"] not in ("dev", "eval") for row in rows):
        raise ValueError(f"{path}: every split must be dev or eval")
    rows = [row for row in rows if row["split"] == split]
    if not rows:
        raise ValueError(f"{path}: no gold codes for split {split}")
    if kind == "hcat" and any(row["in_gold"] not in ("yes", "no") for row in rows):
        raise ValueError(f"{path}: in_gold must be yes or no")
    missing = [row["code"] for row in rows if (
        not row["relation"].strip() if kind == "agrovoc"
        else row["in_gold"] == "yes" and not normalise_target(row["hcat_code"], kind))]
    if missing:
        raise ValueError(f"{kind} {split}: {len(missing)} missing gold judgements: {', '.join(missing)}")
    gold = []
    for row in rows:
        code = row["code"].strip()
        area = float(row["area_ha"])
        if not math.isfinite(area) or area < 0:
            raise ValueError(f"{code}: area_ha must be finite and non-negative")
        included = kind == "agrovoc" or row["in_gold"] == "yes"
        target = normalise_target(row["concept"] if kind == "agrovoc" else row["hcat_code"], kind)
        relation = row["relation"].strip() if kind == "agrovoc" else ""
        alternatives = []
        if kind == "agrovoc":
            if relation not in RELATIONS or (relation == "none") != (not target):
                raise ValueError(f"{code}: gold relation and concept are inconsistent")
            alternatives = [normalise_target(value, kind) for value in row["alternatives"].split(";")
                            if value.strip()]
            if any(not value for value in alternatives) or (alternatives and not target):
                raise ValueError(f"{code}: alternatives require concept targets")
        elif not included and target:
            raise ValueError(f"{code}: excluded HCAT code must have no gold target")
        gold.append({"code": code, "area_ha": area, "target": target, "relation": relation,
                     "alternatives": alternatives, "in_gold": included})
    return gold


def load_predictions(path, kind):
    """Keep CSV row order to break top-1 ties; malformed targets/ranks are file errors."""
    predictions = {}
    for number, row in enumerate(_read_csv(path, ("code", "rank", "target")), 2):
        code, rank = row["code"].strip(), row["rank"].strip()
        if not code or not re.fullmatch(r"[0-9]+", rank) or int(rank) < 1:
            raise ValueError(f"{path}: row {number}: code and positive integer rank required")
        target = normalise_target(row["target"], kind)
        relation = row.get("relation", "").strip() if kind == "agrovoc" else ""
        if relation and relation not in RELATIONS[:-1]:
            raise ValueError(f"{path}: row {number}: invalid predicted relation {relation!r}")
        predictions.setdefault(code, []).append({"rank": int(rank), "target": target,
                                                 "relation": relation})
    return predictions


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def _metric(numerator, denominator):
    return {"value": _ratio(numerator, denominator), "numerator": numerator, "denominator": denominator}


def _identification(rows, mode, weighted):
    """Gold-none abstentions are auditable correctness, but never a precision/recall hit."""
    weight = lambda row: row["area_ha"] if weighted else 1
    correct = sum(weight(row) for row in rows if row["rank1"] and row[mode])
    predicted = sum(weight(row) for row in rows if row["rank1"])
    concepts = sum(weight(row) for row in rows if row["gold"])
    return {"precision": _metric(correct, predicted), "recall": _metric(correct, concepts),
            "f1": _metric(2 * correct, predicted + concepts)}


def score(gold, predictions, kind, split):
    """Each gold code contributes once; excluded and other-split predictions add no weight."""
    rows, excluded = [], []
    for item in gold:
        code = item["code"]
        if not item["in_gold"]:
            excluded.append(code)
            continue
        ranking = predictions.get(code, [])
        best = next((row for row in ranking if row["rank"] == 1), {})
        target = best.get("target", "")
        strict = target == item["target"]
        lenient = strict or bool(target and target in item["alternatives"])
        ranks = [row["rank"] for row in ranking if item["target"] and row["target"] == item["target"]]
        rows.append({"code": code, "gold": item["target"], "rank1": target, "strict": strict,
                     "lenient": lenient, "gold_rank": min(ranks) if ranks else None,
                     "area_ha": item["area_ha"], "gold_relation": item["relation"],
                     "predicted_relation": best.get("relation", "")})
    concept_rows = [row for row in rows if row["gold"]]
    relation_rows = [row for row in rows if row["rank1"] and row["strict"] and row["predicted_relation"]]
    result = {
        "gold_kind": kind, "split": split,
        "counts": {"split_codes": len(gold), "scored_codes": len(rows), "excluded_codes": len(excluded),
                   "gold_concepts": len(concept_rows), "gold_none": len(rows) - len(concept_rows),
                   "non_abstaining": sum(bool(row["rank1"]) for row in rows),
                   "abstentions": sum(not row["rank1"] for row in rows),
                   "correct_strict_including_none": sum(row["strict"] for row in rows),
                   "correct_lenient_including_none": sum(row["lenient"] for row in rows)},
        "scores": {name: _identification(rows, mode, weighted)
                   for name, mode, weighted in (("strict", "strict", False), ("lenient", "lenient", False),
                                                ("area_strict", "strict", True), ("area_lenient", "lenient", True))},
        "ranking": {f"Hits@{k}": _metric(sum(row["gold_rank"] is not None and row["gold_rank"] <= k
                                            for row in concept_rows), len(concept_rows)) for k in (1, 5)},
        "excluded": excluded,
        "ignored_prediction_codes": sorted(set(predictions) - {item["code"] for item in gold}),
        "per_code": rows,
    }
    result["ranking"]["MRR"] = _metric(sum(1 / row["gold_rank"] for row in concept_rows if row["gold_rank"]),
                                       len(concept_rows))
    result["relation_accuracy"] = (_metric(sum(row["gold_relation"] == row["predicted_relation"]
                                               for row in relation_rows), len(relation_rows))
                                   if kind == "agrovoc" else None)
    return result


def _cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def markdown_report(result):
    """Show every ratio's counts and every code so scores can be checked by hand."""
    lines = [f"# RPG → {result['gold_kind'].upper()} alignment scores ({result['split']})", "",
             "| Count | Value |", "|---|---:|"]
    lines.extend(f"| {key} | {value} |" for key, value in result["counts"].items())
    lines.extend(["", "| Score | Value | Numerator | Denominator |", "|---|---:|---:|---:|"])
    metrics = [(f"{group} {name}", values) for group, scores in result["scores"].items()
               for name, values in scores.items()]
    metrics.extend(result["ranking"].items())
    if result["relation_accuracy"] is not None:
        metrics.append(("relation accuracy", result["relation_accuracy"]))
    for name, values in metrics:
        lines.append(f"| {name} | {values['value']:.6f} | {values['numerator']:.12g} | "
                     f"{values['denominator']:.12g} |")
    lines.extend(["", "Precision = correct non-abstaining / non-abstaining; recall = correct / gold concepts. "
                  "F1 = 2 × correct / (non-abstaining + gold concepts). Area scores sum hectares over the same "
                  "sets. Gold-none abstentions earn no true positives. Undefined ratios are 0.", "",
                  "Strict means the exact gold target; lenient also accepts pre-labelled AGROVOC alternatives. "
                  "Relation accuracy uses strictly correct non-abstaining targets with a supplied relation.", "",
                  "Rank-1 ties use the first CSV row for identification. Ranking measures use the exact gold "
                  "target's best supplied rank, including ties and gaps; scores are ignored. Hits@1 can therefore "
                  "differ from top-1 correctness on tied rank 1. Gold-none codes are excluded from ranking. "
                  "Missing rank 1, an empty target, and none are abstentions.", "",
                  "## Excluded HCAT codes (never counted as none)", "",
                  ", ".join(map(_cell, result["excluded"])) or "None.", "",
                  "## Prediction codes outside the requested gold split (ignored)", "",
                  ", ".join(map(_cell, result["ignored_prediction_codes"])) or "None.", "",
                  "## Per-code audit", "",
                  "| Code | Gold | Rank-1 | Strict | Lenient | Gold rank | Area (ha) | Gold relation | Predicted relation |",
                  "|---|---|---|---|---|---:|---:|---|---|"])
    for row in result["per_code"]:
        values = (row["code"], row["gold"] or "none", row["rank1"] or "none",
                  "yes" if row["strict"] else "no", "yes" if row["lenient"] else "no",
                  row["gold_rank"] if row["gold_rank"] is not None else "—", f"{row['area_ha']:.12g}",
                  row["gold_relation"], row["predicted_relation"])
        lines.append("| " + " | ".join(map(_cell, values)) + " |")
    return "\n".join(lines) + "\n"


def _protect_output(out, inputs):
    if out is not None and Path(out).resolve() in {Path(path).resolve() for path in inputs}:
        raise ValueError("--out must not overwrite an input or gold file")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("hcat-gold", help="derive the separate CC BY-SA 4.0 HCAT gold CSV")
    build.add_argument("--out", type=Path, default=HCAT_GOLD)
    evaluate = commands.add_parser("score", help="score a frozen matcher's CSV predictions")
    evaluate.add_argument("--gold", choices=("agrovoc", "hcat"), required=True)
    evaluate.add_argument("--pred", type=Path, required=True)
    evaluate.add_argument("--split", choices=("dev", "eval"), required=True)
    evaluate.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "hcat-gold":
            rows, conflicts = hcat_gold(args.out)
            print(f"-> {args.out}: {sum(row['in_gold'] == 'yes' for row in rows)} in gold, "
                  f"{sum(row['in_gold'] == 'no' for row in rows)} excluded")
            for split in ("dev", "eval"):
                subset = [row for row in rows if row["split"] == split]
                included = [row for row in subset if row["in_gold"] == "yes"]
                print(f"{split}: {len(included)} in gold; {len(subset) - len(included)} excluded; "
                      f"{len({row['hcat_code'] for row in included})} distinct targets")
            print("Excluded: " + ", ".join(row["code"] for row in rows if row["in_gold"] == "no"))
            for conflict in conflicts:
                print("Source conflict: " + conflict)
            return
        _protect_output(args.out, [args.pred, AGROVOC_GOLD, HCAT_GOLD, *EUROCROPS.glob("*")])
        gold = load_gold(args.gold, args.split)
        predictions = load_predictions(args.pred, args.gold)
        report = markdown_report(score(gold, predictions, args.gold, args.split))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(report, encoding="utf-8")
        print(report, end="")
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
