"""Freeze crop-code inputs and run alignment matchers (v5 plan R2.3, subject SO1).

The laptop builds a label-only JSON file. Colab runs OntoAligner 1.9.4's
SimpleFuzzySMLightweight and SBERTRetrieval, without training anything.
SBERTRetrieval.load cannot pin a revision, so we attach a SentenceTransformer
loaded at the fixed commit to that component. Its misleadingly named `fit`
only encodes target strings. Qwen runs through the Track 2 transformers loader:
OntoAligner's default LLM loader does not pass model/tokenizer revisions or
Qwen's thinking-off chat-template option, and forces 8-bit loading on a GPU.

Gold judgements never enter matching. The gold CSV contributes only a sorted
code projection, hashed separately: hashing its full bytes would contradict
the requirement that shuffling gold judgements leaves frozen inputs unchanged.
All other input files have full byte hashes. EuroCrops labels remain a separate
CC BY-SA 4.0 evaluation resource, outside the ontology.
"""
import argparse
import csv
import gc
import hashlib
import io
import json
import math
import re
import sys
import time
from pathlib import Path

from src.config import DATASET, INTERIM, ROOT
from src.kg.align_eval import AGROVOC_GOLD, EUROCROPS, HCAT_GOLD, _read_csv
from src.kg.extract_llm import (
    _atomic_write_text, _config_diff_fields, _load_hf_generator,
    _package_version, _sha256_file, strip_json_fence, strip_leading_think_block,
)

INPUTS = INTERIM / "align_inputs_hcat.json"
PROMPT = ROOT / "configs" / "align_prompt_hcat.md"
AGROVOC_INPUTS = INTERIM / "align_inputs_agrovoc.json"
AGROVOC_PROMPT = ROOT / "configs" / "align_prompt_agrovoc.md"
RELATIONS = ("exactMatch", "closeMatch", "broadMatch", "narrowMatch")
RETRIEVAL_MODEL = "BAAI/bge-m3"
RETRIEVAL_COMMIT = "5617a9f61b028005a4858fdac845db406aefb181"
LLM_MODEL = "Qwen/Qwen3-8B"
LLM_COMMIT = "b968826d9c46dd6066d109eabc6255188de91218"
K = 10


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _path_name(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _source_inputs(codes_path, *, code_only):
    """Use only the code column of gold; get labels and groups from independent RPG tables."""
    import pandas as pd
    from src.analysis.rpg_profile import group_labels
    from src.config import RAW
    from src.dataset.crop_demand import AREA_OUT
    from src.kg.landuse import NOMENCLATURE, nomenclature

    # Project at read time: no gold label, split, area or judgement is inspected.
    if code_only:
        codes = pd.read_csv(codes_path, usecols=["code"], dtype=str, keep_default_na=False,
                            comment="#")["code"].str.strip().tolist()
    else:
        # Preserve HCAT's existing CSV validation as well as its frozen bytes.
        codes = [row["code"].strip() for row in _read_csv(codes_path, ("code",))]
    if any(not code for code in codes) or len(set(codes)) != len(codes):
        raise ValueError("Source codes must be nonempty and unique")
    codes.sort()
    # Hash a real, canonical one-column CSV, independent of row order and judgements.
    projection = io.StringIO(newline="")
    writer = csv.writer(projection, lineterminator="\n")
    writer.writerow(["code"])
    writer.writerows([code] for code in codes)
    code_hash = hashlib.sha256(projection.getvalue().encode("utf-8")).hexdigest()
    nom, groups = nomenclature(), group_labels()
    area = pd.read_parquet(AREA_OUT, columns=["CODE_CULTU", "CODE_GROUP"])
    pairs = area.drop_duplicates()
    if pairs.groupby("CODE_CULTU")["CODE_GROUP"].nunique().gt(1).any():
        raise ValueError("A crop code has several observed RPG groups; resolve before freezing inputs")
    code_groups = pairs.set_index("CODE_CULTU")["CODE_GROUP"].to_dict()
    sources = []
    for code in codes:
        if code not in nom or code not in code_groups:
            raise ValueError(f"{code}: missing official label or observed group")
        group = int(code_groups[code])
        group_label = groups.get(group, "")
        if not group_label:
            raise ValueError(f"{code}: missing group label for {group}")
        sources.append({"code": code, "label": nom[code][0], "group": group,
                        "group_label": group_label})
    files = [AREA_OUT]
    files += [RAW / "rpg" / "docs" / name for name, _ in NOMENCLATURE.values()]
    return sources, code_hash, files


def _agrovoc_targets(labels_path, broader_path):
    """Keep one live concept, with bilingual labels and direct parents from one release."""
    import pandas as pd

    labels, broader = pd.read_parquet(labels_path), pd.read_parquet(broader_path)
    releases = set(labels["release"]) | set(broader["release"])
    if len(releases) != 1 or not all(isinstance(day, str) and day for day in releases):
        raise ValueError("AGROVOC tables must belong to one dated release")
    preferred = {}
    for (concept, lang), rows in labels[labels["kind"].eq("pref")].groupby(["concept", "lang"]):
        names = sorted(set(rows["label"]))
        if len(names) != 1 or not names[0].strip():
            raise ValueError(f"{concept}: expected one preferred label per language")
        preferred.setdefault(concept, {})[lang] = names[0]
    names = {concept: langs.get("fr") or langs.get("en", "")
             for concept, langs in preferred.items()}
    parents = broader.groupby("concept")["broader"].agg(set).to_dict()
    aliases = {key: sorted(set(rows["label"])) for key, rows in
               labels[labels["kind"].eq("alt")].groupby(["concept", "lang"])}
    targets = []
    for concept, deprecated in labels.groupby("concept", sort=True)["deprecated"].any().items():
        if deprecated:
            continue
        if not names.get(concept):
            raise ValueError(f"{concept}: missing French or English preferred label")
        alt = list(dict.fromkeys(label for lang in ("fr", "en")
                                for label in aliases.get((concept, lang), [])
                                if label.strip()))[:5]
        direct = parents.get(concept, set())
        if any(not names.get(parent) for parent in direct):
            raise ValueError(f"{concept}: a direct broader concept has no preferred label")
        targets.append({"id": concept, "label": names[concept],
                        "label_en": preferred[concept].get("en", ""), "alt": alt,
                        "ancestors": sorted({names[parent] for parent in direct})[:3]})
    return targets, next(iter(releases))


def build_inputs(*, target="hcat", codes_path=None, hcat_path=EUROCROPS / "HCAT3.csv",
                 labels_path=None, broader_path=None):
    """Freeze the same independent RPG sources against HCAT or the local AGROVOC snapshot."""
    if target not in ("hcat", "agrovoc"):
        raise ValueError("Target must be hcat or agrovoc")
    codes_path = codes_path or (HCAT_GOLD if target == "hcat" else AGROVOC_GOLD)
    sources, code_hash, files = _source_inputs(codes_path, code_only=target == "agrovoc")
    if target == "agrovoc":
        from src.ingest.agrovoc import BROADER, LABELS

        labels_path, broader_path = Path(labels_path or LABELS), Path(broader_path or BROADER)
        targets, release = _agrovoc_targets(labels_path, broader_path)
        files += [labels_path, broader_path]
        return {"format": 1, "target": target, "sources": sources, "targets": targets,
                "sha256": {_path_name(path): _sha256_file(path) for path in sorted(files)},
                "source_codes": {"file": "configs/lu_agrovoc_gold.csv",
                                 "projection": "sorted code column only", "sha256": code_hash},
                "release": release, "target_licence": "AGROVOC CC BY 4.0 (FAO)"}
    rows = _read_csv(hcat_path, ("HCAT3_code", "HCAT3_name"))
    names = {row["HCAT3_code"]: row["HCAT3_name"].replace("_", " ") for row in rows}
    if len(names) != len(rows) or any(not re.fullmatch(r"[0-9]{10}", code) for code in names):
        raise ValueError("HCAT codes must be unique ten-digit strings")
    targets = []
    for code, label in sorted(names.items()):
        # Every named zero-padded prefix is an ancestor, in root-to-parent order.
        ancestors = list(dict.fromkeys(code[:i].ljust(10, "0") for i in range(1, 10)))
        targets.append({"id": code, "label": label,
                        "ancestors": [names[p] for p in ancestors if p in names and p != code]})
    files += [Path(hcat_path)]
    return {"format": 1, "target": "hcat", "sources": sources, "targets": targets,
            "sha256": {_path_name(path): _sha256_file(path) for path in sorted(files)},
            "source_codes": {"file": "configs/lu_hcat_gold.csv", "projection": "sorted code column only",
                             "sha256": code_hash},
            "target_licence": "EuroCrops CC BY-SA 4.0"}


def write_inputs(out=None, **kwargs):
    payload = build_inputs(**kwargs)
    out = Path(out or (AGROVOC_INPUTS if kwargs.get("target") == "agrovoc" else INPUTS))
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out, _json(payload))
    return payload


def load_inputs(path, target):
    """The same runner accepts another target's label-only JSON file later."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != 1 or data.get("target") != target:
        raise ValueError("Input format or target does not match the requested run")
    for field, id_field in (("sources", "code"), ("targets", "id")):
        rows = data.get(field)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Inputs need a nonempty {field} list")
        seen = set()
        for row in rows:
            ident = row.get(id_field)
            if not isinstance(ident, str) or not ident or ident in seen:
                raise ValueError(f"Empty or duplicate {field} id")
            seen.add(ident)
            if not isinstance(row.get("label"), str) or not row["label"].strip():
                raise ValueError(f"{ident}: missing label")
            if field == "sources" and not isinstance(row.get("group_label"), str):
                raise ValueError(f"{ident}: missing group_label")
            if field == "targets" and (not isinstance(row.get("ancestors"), list)
                                       or any(not isinstance(p, str) for p in row["ancestors"])):
                raise ValueError(f"{ident}: ancestors must be a list of names")
    return data


def _encoded(data, *, context):
    sources = [{"iri": s["code"], "text": s["label"] + (
        "; RPG group: " + s["group_label"] if context else "")} for s in data["sources"]]
    if data["target"] == "agrovoc" and context:
        targets = [{"iri": t["id"], "text": "; ".join([t["label"]]
                   + (["en: " + t["label_en"]] if t["label_en"] else [])
                   + (["also: " + "; ".join(t["alt"])] if t["alt"] else [])
                   + (["broader: " + "; ".join(t["ancestors"])] if t["ancestors"] else []))}
                   for t in data["targets"]]
    else:
        targets = [{"iri": t["id"], "text": t["label"] + (
            "; ancestors: " + " > ".join(t["ancestors"]) if context and t["ancestors"] else "")}
            for t in data["targets"]]
    return [sources, targets]


def _ontoaligner_version():
    if _package_version("ontoaligner") != "1.9.4":
        raise RuntimeError("This step needs ontoaligner==1.9.4 in the Colab session")


def _fuzzy(data):
    _ontoaligner_version()
    from ontoaligner.aligner.lightweight.models import SimpleFuzzySMLightweight

    matcher = SimpleFuzzySMLightweight(fuzzy_sm_threshold=0.0)
    rows = matcher.generate(_encoded(data, context=False))
    return {row["source"]: [{"target": row["target"], "score": float(row["score"])}] for row in rows}, {}


def _snapshot(repo, commit):
    """Download (or reuse) the model's files at the pinned commit; returns (folder, resolved commit). The Hub
    cache names a snapshot folder by the commit it resolved, which is the check: sentence-transformers 5 leaves
    the loaded config's `_commit_hash` empty (Colab, 2026-11-27: the first check read None). The repository's
    ONNX export (several GB, unused by sentence-transformers) is skipped."""
    from huggingface_hub import snapshot_download
    path = Path(snapshot_download(repo, revision=commit, ignore_patterns=["onnx/*", "*.onnx", "*.onnx_data"]))
    return path, path.name


def _retrieve(data):
    _ontoaligner_version()
    from ontoaligner.aligner.retrieval.models import SBERTRetrieval
    from sentence_transformers import SentenceTransformer

    retriever = SBERTRetrieval(device="cuda", top_k=min(K, len(data["targets"])), batch_size=16)
    # OntoAligner.load ignores revision; loading here from the pinned snapshot prevents an unpinned download.
    path, resolved = _snapshot(RETRIEVAL_MODEL, RETRIEVAL_COMMIT)
    if resolved != RETRIEVAL_COMMIT:
        raise RuntimeError(f"BGE-M3 resolved to {resolved!r}, expected {RETRIEVAL_COMMIT}")
    retriever.model = SentenceTransformer(str(path), device="cuda")
    rows = retriever.generate(_encoded(data, context=True))
    rankings = {row["source"]: [{"target": t, "score": float(s)}
                for t, s in zip(row["target-cands"], row["score-cands"])] for row in rows}
    return rankings, {RETRIEVAL_MODEL: resolved}


def _validate_rankings(rankings, data, count):
    """Refuse missing codes, out-of-vocabulary targets and truncated retrieval lists."""
    if set(rankings) != {s["code"] for s in data["sources"]}:
        raise ValueError("Matcher output must contain exactly the frozen source codes")
    targets = {t["id"] for t in data["targets"]}
    for code, rows in rankings.items():
        if len(rows) != count or len({r["target"] for r in rows}) != count:
            raise ValueError(f"{code}: expected {count} distinct ranked targets")
        for row in rows:
            if row["target"] not in targets or not math.isfinite(float(row["score"])):
                raise ValueError(f"{code}: unknown target or non-finite score")


def messages(source, candidates, targets, template):
    """Render only the source labels and retrieved candidates, with no gold examples."""
    if "## System" not in template or "## User" not in template:
        raise ValueError("Prompt needs ## System and ## User sections")
    _, rest = template.split("## System", 1)
    system, user = rest.split("## User", 1)
    if "{source}" not in user or "{candidates}" not in user:
        raise ValueError("User prompt needs {source} and {candidates}")
    candidate_data = []
    for rank, row in enumerate(candidates, 1):
        item = targets[row["target"]]
        candidate = {"id": row["target"], "label": item["label"],
                     "ancestors": item["ancestors"], "rank": rank}
        if "label_en" in item:
            candidate.update(label_en=item["label_en"], alt=item["alt"])
        candidate_data.append(candidate)
    # Simultaneous substitution keeps braces inside labels literal.
    values = {"source": _json(source).strip(), "candidates": _json(candidate_data).strip()}
    user = re.sub(r"\{(source|candidates)\}", lambda match: values[match[1]], user)
    return [{"role": "system", "content": system.strip()}, {"role": "user", "content": user.strip()}]


def parse_answer(raw, candidates, target="hcat"):
    """Return (id, error) for HCAT, or (id, relation, error) for AGROVOC.

    Keep the HCAT interface for existing callers. AGROVOC failures abstain in
    both fields and remain visible in run.json, including invalid relations.
    """
    if target == "agrovoc":
        raw, _ = strip_leading_think_block(raw)
        try:
            item = json.loads(strip_json_fence(raw))
        except ValueError:
            return "", "", "Expected a JSON object with exactly target and relation fields"
        if (not isinstance(item, dict) or set(item) != {"target", "relation"}
                or not all(isinstance(value, str) for value in item.values())):
            return "", "", "Expected exactly two string fields: target and relation"
        if item["relation"] not in RELATIONS:
            return "", "", "Unknown AGROVOC relation"
        if item["target"] == "none":
            return "", "", None
        if item["target"] not in {row["target"] for row in candidates}:
            return "", "", "Chosen target is outside the retrieved candidates"
        return item["target"], item["relation"], None
    raw, _ = strip_leading_think_block(raw)
    try:
        item = json.loads(strip_json_fence(raw))
    except ValueError:
        return "", "Expected a JSON object with exactly one target field"
    if not isinstance(item, dict) or set(item) != {"target"} or not isinstance(item["target"], str):
        return "", "Expected a JSON object with exactly one string target field"
    target = item["target"]
    if target == "none":
        return "", None
    if target not in {row["target"] for row in candidates}:
        return "", "Chosen target is outside the retrieved candidates"
    return target, None


def run_alignment(matcher, target, out_dir, *, inputs_path=None, prompt_path=None,
                  matcher_stub=None, generator=None):
    """Lock configuration, cache candidates and raw LLM answers, then write scorer CSV."""
    if matcher not in ("fuzzy", "retrieval", "llm"):
        raise ValueError("Matcher must be fuzzy, retrieval or llm")
    if generator is not None and matcher != "llm":
        raise ValueError("A generator applies only to the llm matcher")
    if matcher != "fuzzy" and (matcher_stub is None or (matcher == "llm" and generator is None)):
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("No CUDA device available: retrieval and LLM alignment run on a Colab GPU")
    inputs_path = Path(inputs_path or INTERIM / f"align_inputs_{target}.json")
    prompt_path = Path(prompt_path or ROOT / "configs" / f"align_prompt_{target}.md")
    data = load_inputs(inputs_path, target)
    template = Path(prompt_path).read_text(encoding="utf-8") if matcher == "llm" else None
    if template is not None:
        messages(data["sources"][0], [], {}, template)
    models = {}
    if matcher != "fuzzy":
        models[RETRIEVAL_MODEL] = RETRIEVAL_COMMIT
    if matcher == "llm":
        models[LLM_MODEL] = LLM_COMMIT
    hashes = {"inputs": _sha256_file(inputs_path), **data.get("sha256", {})}
    if matcher == "llm":
        hashes["prompt"] = _sha256_file(prompt_path)
    config = {"format": 1, "dataset": DATASET, "matcher": matcher, "target": target,
              "sha256": hashes, "source_codes": data.get("source_codes"), "models": models,
              "k": K, "fuzzy_threshold": 0.0, "fuzzy_component": "SimpleFuzzySMLightweight",
              "retrieval_component": "SBERTRetrieval", "ontoaligner": "1.9.4",
              "text_policy": "fuzzy labels only; retrieval labels with group/ancestor context",
              "decoding": {"do_sample": False, "max_new_tokens": 128, "dtype": "bfloat16",
                           "chat_template_kwargs": {"enable_thinking": False}},
              "matcher_stub": matcher_stub is not None, "generator_stub": generator is not None}
    if target == "agrovoc":
        config["text_policy"] = "fuzzy labels only; retrieval source group and target French/English, alt, broader labels"
    out_dir = Path(out_dir)
    config_path = out_dir / "config.json"
    if config_path.exists():
        diff = _config_diff_fields(json.loads(config_path.read_text(encoding="utf-8")), config)
        if diff:
            raise ValueError(f"Refusing to resume in {out_dir}: config.json differs in {', '.join(diff)}")
    else:
        if out_dir.exists() and any(out_dir.iterdir()):
            raise ValueError("Refusing a nonempty run folder without config.json")
        out_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(config_path, _json(config))
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    cached = raw_dir / "candidates.json"
    if cached.exists():
        cache = json.loads(cached.read_text(encoding="utf-8"))
    else:
        started = time.perf_counter()
        if matcher_stub is not None:
            rankings, resolved = matcher_stub(data), {}
        else:
            rankings, resolved = _fuzzy(data) if matcher == "fuzzy" else _retrieve(data)
        _validate_rankings(rankings, data, 1 if matcher == "fuzzy" else min(K, len(data["targets"])))
        cache = {"rankings": rankings, "resolved_commits": resolved,
                 "seconds": round(time.perf_counter() - started, 4)}
        _atomic_write_text(cached, _json(cache))
    rankings = cache["rankings"]
    _validate_rankings(rankings, data, 1 if matcher == "fuzzy" else min(K, len(data["targets"])))
    run_path = out_dir / "run.json"
    prior = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {}
    meta = {"matcher": matcher, "target": target, "models": models,
            "resolved_commits": {**prior.get("resolved_commits", {}), **cache["resolved_commits"]},
            "sha256": hashes, "k": K, "n_sources": len(data["sources"]), "n_targets": len(data["targets"]),
            "decoding": config["decoding"], "matcher_stub": config["matcher_stub"],
            "generator_stub": config["generator_stub"], "candidate_seconds": cache["seconds"],
            "versions": {name: _package_version(name) for name in (
                "ontoaligner", "rapidfuzz", "sentence-transformers", "transformers", "torch",
                "huggingface-hub", "numpy", "scikit-learn")}}
    _atomic_write_text(run_path, _json(meta))
    failures, timings = [], dict(prior.get("per_code_seconds", {}))
    if matcher == "llm":
        pending = [i for i in range(len(data["sources"])) if not (raw_dir / f"{i:04d}.txt").exists()]
        if pending and generator is None:
            import torch
            gc.collect()
            torch.cuda.empty_cache()
            generator, resolved = _load_hf_generator(
                LLM_MODEL, LLM_COMMIT, "bfloat16", 128, {"enable_thinking": False})
            if resolved != LLM_COMMIT:
                raise RuntimeError(f"Qwen resolved to {resolved!r}, expected {LLM_COMMIT}")
            meta["resolved_commits"][LLM_MODEL] = resolved
            _atomic_write_text(run_path, _json(meta))
        targets = {t["id"]: t for t in data["targets"]}
        chosen = {}
        for index, source in enumerate(data["sources"]):
            code = source["code"]
            raw_path = raw_dir / f"{index:04d}.txt"
            if raw_path.exists():
                raw = raw_path.read_text(encoding="utf-8")
            else:
                started = time.perf_counter()
                raw = generator(messages(source, rankings[code], targets, template))
                timings[code] = round(time.perf_counter() - started, 4)
                _atomic_write_text(raw_path, raw)
            if target == "agrovoc":
                result, relation, error = parse_answer(raw, rankings[code], target)
            else:
                result, error = parse_answer(raw, rankings[code])
            if error:
                failures.append({"code": code, "error": error})
            # A chosen candidate's retrieval score is not an LLM probability.
            chosen[code] = [{"target": result, "score": ""}]
            if target == "agrovoc":
                chosen[code][0]["relation"] = relation
        rankings = chosen
    buffer = io.StringIO(newline="")
    fields = ("code", "rank", "target", "score") + (("relation",) if target == "agrovoc" else ())
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for source in data["sources"]:
        for rank, row in enumerate(rankings[source["code"]], 1):
            writer.writerow({"code": source["code"], "rank": rank, **row})
    pred_path = out_dir / "predictions.csv"
    _atomic_write_text(pred_path, buffer.getvalue())
    meta.update(n_predictions=sum(len(rows) for rows in rankings.values()), parse_failures=failures,
                per_code_seconds=timings)
    _atomic_write_text(run_path, _json(meta))
    return pred_path, meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    inputs = sub.add_parser("inputs", help="freeze label-only inputs on the laptop")
    inputs.add_argument("--target", choices=("hcat", "agrovoc"), default="hcat")
    run = sub.add_parser("run", help="run a frozen matcher in the Colab session")
    run.add_argument("--matcher", choices=("fuzzy", "retrieval", "llm"), required=True)
    run.add_argument("--target", default="hcat")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--inputs", type=Path, default=None)
    run.add_argument("--prompt", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "inputs":
            data = write_inputs(target=args.target)
            path = INTERIM / f"align_inputs_{args.target}.json"
            print(f"Wrote {len(data['sources'])} sources and {len(data['targets'])} targets to {path}")
        else:
            path, meta = run_alignment(args.matcher, args.target, args.out,
                                       inputs_path=args.inputs, prompt_path=args.prompt)
            print(f"Wrote {meta['n_predictions']} predictions to {path}; "
                  f"{len(meta['parse_failures'])} parse failures")
    except (ValueError, RuntimeError, OSError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
