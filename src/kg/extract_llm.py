"""Track 2 LLM extraction pipeline: passages, split, prompt, runner and split scoring (v5 plan R2.1).

Everything that can change a Track 2 extraction score is frozen before any model output is seen:
the page passages, the dev/eval split, the prompt template with BD LISA and BD TOPO code tables,
greedy decoding and answer parsing. Model selection uses the dev split only; eval is scored once.

CLI:
    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.kg.extract_llm passages
    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.kg.extract_llm run --model ID --split dev --out DIR
    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.kg.extract_llm score --pred FILE --split dev
"""
import argparse
import copy
import csv
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.config import INTERIM, ROOT
from src.kg import extract_eval
from src.kg.extract_passages import build_passages
from src.kg.rivers import snapshot

PASSAGES_PATH = INTERIM / "extraction_passages_track2.jsonl"
SPLIT_PATH = ROOT / "configs" / "extraction_split_track2.json"
PROMPT_PATH = ROOT / "configs" / "extraction_prompt_track2.md"
SCHEMA_PATH = extract_eval.SCHEMA
GOLD_PATH = extract_eval.GOLD
BDLISA_PLAIN = INTERIM / "bdlisa_entities_plain.csv"

DEV_STATEMENT_PAGES = (
    ("brgm-rp-71486-fr", "24"),
    ("brgm-rp-71486-fr", "29"),
    ("sierm-frdg351", "3"),
    ("smnpr-fonctionnement-des-nappes", "web page"),
)
SPLIT_RULE = (
    "Dev statement pages are fixed before running any model: sierm-frdg351 page 3, "
    "brgm-rp-71486-fr pages 24 and 29, and smnpr-fonctionnement-des-nappes web page "
    "(10 gold statements: 6 RiverExchange, 4 CanalReturnFlow). Every other page holding "
    "a gold statement is eval (22 statements). Pages without a gold statement are dev "
    "when 0-based physical_index % 4 == 0, else eval."
)
SYSTEM_MARKER = "## System"
USER_MARKER = "## User"


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _reject_constant(value):
    raise ValueError(f"{value} is not valid JSON")


def _package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def read_code_tables(schema_path=SCHEMA_PATH, bdlisa_path=BDLISA_PLAIN):
    """Read unit and watercourse names from project tables for every code in the schema.

    Never invents a name: any code missing from the project tables receives an empty string.
    """
    import pandas as pd

    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    props = schema["items"]["properties"]
    unit_codes = list(props["units"]["items"]["enum"])
    wc_codes = list(props["watercourses"]["items"]["enum"])

    bdlisa_names = {}
    with Path(bdlisa_path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            code = (row.get("CodeEH") or "").strip()
            label = (row.get("libelleeh") or "").strip()
            if code and label:
                bdlisa_names[code] = label
    units = {code: bdlisa_names.get(code, "") for code in unit_codes}

    snap = snapshot("bdtopo_hydro")
    reaches = pd.read_parquet(
        snap / "troncon_hydrographique.parquet",
        columns=["code_du_cours_d_eau_bdcarthage", "cpx_toponyme_de_cours_d_eau"],
    )
    watercourses = {}
    for code in wc_codes:
        own = reaches[reaches["code_du_cours_d_eau_bdcarthage"] == code]
        names = own["cpx_toponyme_de_cours_d_eau"].dropna().astype(str).str.strip()
        names = names[names != ""]
        if len(names):
            modes = sorted(names.mode().tolist())
            watercourses[code] = modes[0]
        else:
            watercourses[code] = ""
    return {"units": units, "watercourses": watercourses}


def format_code_table(mapping, code_header, name_header):
    """Render a deterministic Markdown table of code -> name entries."""
    lines = [f"| {code_header} | {name_header} |", "|---|---|"]
    for code, name in mapping.items():
        lines.append(f"| {code} | {name} |")
    return "\n".join(lines)


def build_split(passages, gold=None, code_tables=None):
    """Assign every passage and gold statement deterministically to dev or eval."""
    gold = extract_eval.load_gold() if gold is None else gold
    code_tables = read_code_tables() if code_tables is None else code_tables
    dev_stmt_pages = set(DEV_STATEMENT_PAGES)
    gold_pages = {(item["document"], item["page"]) for item in gold}

    missing_dev = dev_stmt_pages - gold_pages
    if missing_dev:
        raise ValueError(f"Dev statement pages missing from gold CSV: {sorted(missing_dev)}")
    passage_pages = {(p["document"], p["page"]) for p in passages}
    missing_passages = gold_pages - passage_pages
    if missing_passages:
        raise ValueError(f"Gold pages missing from passages: {sorted(missing_passages)}")

    split_by_passage = {}
    pages_by_split = {"dev": set(), "eval": set()}
    for passage in passages:
        loc = (passage["document"], passage["page"])
        if loc in dev_stmt_pages:
            split = "dev"
        elif loc in gold_pages:
            split = "eval"
        else:
            split = "dev" if passage["physical_index"] % 4 == 0 else "eval"
        split_by_passage[passage["passage_id"]] = split
        pages_by_split[split].add(loc)

    dev_gold_ids = sorted(item["id"] for item in gold if (item["document"], item["page"]) in dev_stmt_pages)
    eval_gold_ids = sorted(item["id"] for item in gold if (item["document"], item["page"]) not in dev_stmt_pages)

    return {
        "rule": SPLIT_RULE,
        "dev_statement_pages": [{"document": doc, "page": page} for doc, page in sorted(DEV_STATEMENT_PAGES)],
        "gold_ids": {"dev": dev_gold_ids, "eval": eval_gold_ids},
        "passages": split_by_passage,
        "pages": {
            split: [{"document": doc, "page": page} for doc, page in sorted(pages_by_split[split])]
            for split in ("dev", "eval")
        },
        "code_tables": code_tables,
    }


def write_passages_and_split(passages_path=PASSAGES_PATH, split_path=SPLIT_PATH):
    """Build and write deterministic passages JSONL and split JSON files."""
    passages = build_passages()
    split_data = build_split(passages)

    passages_path = Path(passages_path)
    passages_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl = "".join(json.dumps(passage, ensure_ascii=False) + "\n" for passage in passages)
    passages_path.write_text(jsonl, encoding="utf-8")

    split_path = Path(split_path)
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps(split_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return passages, split_data


def load_passages(path=PASSAGES_PATH):
    """Read passages from the JSONL file written by `passages`."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_split(path=SPLIT_PATH):
    """Read the frozen split and code tables from configs/extraction_split_track2.json."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def split_prompt_template(template):
    """Split configs/extraction_prompt_track2.md into (system_template, user_template)."""
    if SYSTEM_MARKER not in template or USER_MARKER not in template:
        raise ValueError(f"Prompt template must contain {SYSTEM_MARKER!r} and {USER_MARKER!r} sections")
    _, after_system = template.split(SYSTEM_MARKER, 1)
    system_part, user_part = after_system.split(USER_MARKER, 1)
    system_text, user_text = system_part.strip(), user_part.strip()
    for placeholder in ("{units_table}", "{watercourses_table}"):
        if placeholder not in system_text:
            raise ValueError(f"System prompt section is missing placeholder {placeholder}")
    if "{passage}" not in user_text:
        raise ValueError("User prompt section is missing placeholder {passage}")
    return system_text, user_text


def messages(passage, *, template=None, units_table=None, watercourses_table=None,
             prompt_path=PROMPT_PATH, split_path=SPLIT_PATH):
    """Build [system, user] chat messages for one passage (pure function of inputs)."""
    passage_text = passage["text"] if isinstance(passage, dict) else str(passage)
    if template is None:
        template = Path(prompt_path).read_text(encoding="utf-8")
    if units_table is None or watercourses_table is None:
        code_tables = load_split(split_path)["code_tables"]
        if units_table is None:
            units_table = format_code_table(code_tables["units"], "Code", "BD LISA name")
        if watercourses_table is None:
            watercourses_table = format_code_table(code_tables["watercourses"], "Code", "Watercourse name")
    system_tpl, user_tpl = split_prompt_template(template)
    # Replace placeholders literally so braces in French text or JSON hints never break formatting.
    system_content = (
        system_tpl.replace("{units_table}", units_table)
        .replace("{watercourses_table}", watercourses_table)
    )
    user_content = user_tpl.replace("{passage}", passage_text)
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def strip_json_fence(raw_text):
    """Remove a single outer ```json ... ``` or ``` ... ``` Markdown code fence if present."""
    text = raw_text.strip()
    if text.startswith("```") and text.endswith("```") and len(text) >= 6:
        inner = text[3:-3]
        if inner.lower().startswith("json"):
            rest = inner[4:]
            if not rest or rest[0] in (" ", "\t", "\r", "\n"):
                inner = rest
        return inner.strip()
    return text


def parse_answer(raw_text, passage):
    """Parse one raw model answer into (items, None) or (None, error_message)."""
    cleaned = strip_json_fence(raw_text)
    try:
        parsed = json.loads(cleaned, parse_constant=_reject_constant)
    except ValueError as error:
        return None, f"JSON parse error: {error}"
    if not isinstance(parsed, list):
        return None, f"Expected a JSON array, got {type(parsed).__name__}"
    items = []
    for entry in parsed:
        if isinstance(entry, dict):
            item = copy.deepcopy(entry)
            item["document"] = passage["document"]
            item["page"] = passage["page"]
            items.append(item)
        else:
            items.append(entry)
    return items, None


def _atomic_write_text(path, content):
    path = Path(path)
    with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as tmp:
        tmp.write(content)
    Path(tmp.name).replace(path)


def _load_hf_generator(model_id, revision, dtype, max_new_tokens, chat_template_kwargs):
    """Load an open causal LM on CUDA with greedy decoding; returns (callable, resolved_revision)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
        "auto": "auto",
    }
    if dtype not in dtype_map:
        raise ValueError(f"Unsupported dtype {dtype!r}; choose from {sorted(dtype_map)}")

    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=revision,
        dtype=dtype_map[dtype],
        device_map="auto",
    )
    model.eval()
    resolved_revision = getattr(model.config, "_commit_hash", None) or revision
    template_kwargs = dict(chat_template_kwargs or {})

    def generate(msgs):
        prompt_text = tokenizer.apply_chat_template(
            msgs,
            tokenize=False,
            add_generation_prompt=True,
            **template_kwargs,
        )
        inputs = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
        inputs = {key: value.to(model.device) for key, value in inputs.items()}
        gen_cfg = copy.deepcopy(model.generation_config)
        gen_cfg.do_sample = False
        gen_cfg.max_new_tokens = max_new_tokens
        gen_cfg.temperature = None
        gen_cfg.top_p = None
        gen_cfg.top_k = None
        with torch.inference_mode():
            output_ids = model.generate(**inputs, generation_config=gen_cfg)
        new_ids = output_ids[0, inputs["input_ids"].shape[1]:]
        return tokenizer.decode(new_ids, skip_special_tokens=True)

    return generate, resolved_revision


def run_extraction(
    model_id,
    split,
    out_dir,
    *,
    revision=None,
    dtype="bfloat16",
    max_new_tokens=4096,
    chat_template_kwargs=None,
    generator=None,
    passages_path=PASSAGES_PATH,
    split_path=SPLIT_PATH,
    prompt_path=PROMPT_PATH,
    schema_path=SCHEMA_PATH,
):
    """Run greedy LLM extraction (or a test stub) over one split, saving resumable raw outputs."""
    if split not in ("dev", "eval", "all"):
        raise ValueError(f"Unsupported split {split!r}; choose dev, eval or all")
    if chat_template_kwargs is not None and not isinstance(chat_template_kwargs, dict):
        raise ValueError("chat_template_kwargs must be a JSON object")
    template_kwargs = dict(chat_template_kwargs or {})

    if generator is None:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("No CUDA device available: LLM extraction runs on a Colab GPU.")

    passages = load_passages(passages_path)
    split_data = load_split(split_path)
    prompt_template = Path(prompt_path).read_text(encoding="utf-8")
    code_tables = split_data["code_tables"]
    units_table = format_code_table(code_tables["units"], "Code", "BD LISA name")
    watercourses_table = format_code_table(code_tables["watercourses"], "Code", "Watercourse name")

    selected = (
        passages
        if split == "all"
        else [p for p in passages if split_data["passages"][p["passage_id"]] == split]
    )

    out_dir = Path(out_dir)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    run_meta_path = out_dir / "run.json"
    prior_meta = json.loads(run_meta_path.read_text(encoding="utf-8")) if run_meta_path.exists() else {}
    prior_seconds = prior_meta.get("per_passage_seconds", {})

    pending = [p for p in selected if not (raw_dir / f"{p['passage_id']}.txt").exists()]
    resolved_revision = revision or prior_meta.get("resolved_revision")
    generate_fn = generator
    if generate_fn is None and pending:
        generate_fn, resolved_revision = _load_hf_generator(
            model_id, revision, dtype, max_new_tokens, template_kwargs
        )

    predictions = []
    parse_failures = []
    per_passage_seconds = {}

    for passage in selected:
        pid = passage["passage_id"]
        raw_path = raw_dir / f"{pid}.txt"
        if raw_path.exists():
            raw_text = raw_path.read_text(encoding="utf-8")
            per_passage_seconds[pid] = prior_seconds.get(pid, 0.0)
        else:
            msgs = messages(
                passage,
                template=prompt_template,
                units_table=units_table,
                watercourses_table=watercourses_table,
            )
            started = time.perf_counter()
            raw_text = generate_fn(msgs)
            elapsed = round(time.perf_counter() - started, 4)
            _atomic_write_text(raw_path, raw_text)
            per_passage_seconds[pid] = elapsed

        items, error = parse_answer(raw_text, passage)
        if error is not None:
            parse_failures.append({
                "passage_id": pid,
                "document": passage["document"],
                "page": passage["page"],
                "error": error,
            })
        else:
            predictions.extend(items)

    pred_path = out_dir / f"predictions_{split}.json"
    _atomic_write_text(pred_path, json.dumps(predictions, indent=2, ensure_ascii=False) + "\n")

    run_meta = {
        "model": model_id,
        "requested_revision": revision,
        "resolved_revision": resolved_revision,
        "dtype": dtype,
        "decoding": {"do_sample": False, "max_new_tokens": max_new_tokens},
        "chat_template_kwargs": template_kwargs,
        "sha256": {
            "prompt_template": _sha256_file(prompt_path),
            "schema": _sha256_file(schema_path),
            "split": _sha256_file(split_path),
            "passages": _sha256_file(passages_path),
        },
        "split": split,
        "n_passages": len(selected),
        "n_predictions": len(predictions),
        "per_passage_seconds": per_passage_seconds,
        "parse_failures": parse_failures,
        "versions": {
            "transformers": _package_version("transformers"),
            "torch": _package_version("torch"),
        },
    }
    _atomic_write_text(run_meta_path, json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n")
    return pred_path, run_meta


def score_split(pred_path, split, *, split_path=SPLIT_PATH, gold_path=GOLD_PATH):
    """Score predictions on one split using extract_eval.score and write score_<split>.md."""
    if split not in ("dev", "eval"):
        raise ValueError(f"Split for scoring must be 'dev' or 'eval', got {split!r}")
    pred_path = Path(pred_path)
    split_data = load_split(split_path)
    split_pages = {(entry["document"], entry["page"]) for entry in split_data["pages"][split]}

    gold_all = extract_eval.load_gold(gold_path)
    gold_subset = [item for item in gold_all if (item["document"], item["page"]) in split_pages]
    if {item["id"] for item in gold_subset} != set(split_data["gold_ids"][split]):
        raise ValueError(f"Gold statements on {split} pages do not match gold_ids[{split!r}] in {split_path}")

    payload = json.loads(pred_path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    if not isinstance(payload, list):
        raise ValueError("Predictions must be a JSON array of statements")
    filtered = [
        item for item in payload
        if isinstance(item, dict) and (item.get("document"), item.get("page")) in split_pages
    ]

    validated = extract_eval.validate_predictions(filtered)
    result = extract_eval.score(gold_subset, validated)
    report = extract_eval.markdown_report(result)
    report_path = pred_path.parent / f"score_{split}.md"
    report_path.write_text(report, encoding="utf-8")
    return result, report_path, report


def _parse_json_object(raw):
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid JSON for --chat-template-kwargs: {error}") from error
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("--chat-template-kwargs must be a JSON object")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("passages", help="extract page passages and write the fixed dev/eval split")

    p_run = sub.add_parser("run", help="run greedy LLM extraction on a split (Colab GPU)")
    p_run.add_argument("--model", required=True, help="Hugging Face model id")
    p_run.add_argument("--revision", default=None, help="optional Hugging Face revision/commit")
    p_run.add_argument("--split", choices=("dev", "eval", "all"), required=True)
    p_run.add_argument("--out", type=Path, required=True, help="output run directory")
    p_run.add_argument("--dtype", default="bfloat16", choices=("bfloat16", "float16", "float32", "auto"))
    p_run.add_argument("--max-new-tokens", type=int, default=4096)
    p_run.add_argument("--chat-template-kwargs", type=_parse_json_object, default={})

    p_score = sub.add_parser("score", help="score predictions on dev or eval with extract_eval")
    p_score.add_argument("--pred", type=Path, required=True, help="predictions JSON file")
    p_score.add_argument("--split", choices=("dev", "eval"), required=True)

    args = parser.parse_args(argv)
    if args.cmd == "passages":
        passages, split_data = write_passages_and_split()
        longest = max(passages, key=lambda p: len(p["text"]))
        by_doc = {}
        for p in passages:
            s = split_data["passages"][p["passage_id"]]
            by_doc.setdefault(p["document"], {"dev": 0, "eval": 0})[s] += 1
        print(f"Wrote {len(passages)} passages to {PASSAGES_PATH.relative_to(ROOT)} and split to {SPLIT_PATH.relative_to(ROOT)}")
        for doc, counts in by_doc.items():
            print(f"  {doc}: total={counts['dev'] + counts['eval']} (dev={counts['dev']}, eval={counts['eval']})")
        print(f"  gold statements: dev={len(split_data['gold_ids']['dev'])}, eval={len(split_data['gold_ids']['eval'])}")
        print(f"  longest passage: {longest['passage_id']} (page {longest['page']!r}, {len(longest['text'])} chars)")
        for kind, mapping in split_data["code_tables"].items():
            missing = [code for code, name in mapping.items() if not name]
            print(f"  code table {kind}: {len(mapping)} codes, missing names={missing}")
    elif args.cmd == "run":
        try:
            pred_path, run_meta = run_extraction(
                args.model,
                args.split,
                args.out,
                revision=args.revision,
                dtype=args.dtype,
                max_new_tokens=args.max_new_tokens,
                chat_template_kwargs=args.chat_template_kwargs,
            )
        except (RuntimeError, ValueError, OSError) as error:
            sys.exit(str(error))
        print(
            f"Wrote {run_meta['n_predictions']} predictions ({len(run_meta['parse_failures'])} parse failures) "
            f"across {run_meta['n_passages']} passages to {pred_path}"
        )
    elif args.cmd == "score":
        try:
            _, report_path, report = score_split(args.pred, args.split)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(report, end="")
        print(f"Saved report to {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
