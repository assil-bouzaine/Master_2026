"""The RPG -> AGROVOC gold set (task 12.9, step 3): a template to fill in, a search, a check.

    python -m src.kg.agrovoc_gold template        # writes configs/lu_agrovoc_gold.csv if absent
    python -m src.kg.agrovoc_gold upgrade         # adds the protocol columns to an existing file
    python -m src.kg.agrovoc_gold search "pêcher"  # concepts whose French or English labels hold
                                                   # these words (accents, case, plurals ignored)
    python -m src.kg.agrovoc_gold blind           # the second annotator's sheet (no candidates)
    python -m src.kg.agrovoc_gold worksheet       # the Rules and Labels workbook for LibreOffice
    python -m src.kg.agrovoc_gold import          # saves workbook answers, then checks the gold set
    python -m src.kg.agrovoc_gold check           # validates the filled files, reports agreement

The gold set is Assil's judgement, one row per crop code of the well zones (most area first):
  split     dev | eval, fixed before any label (every fifth code by area rank, from the third,
            is dev: 40 codes): prompts, thresholds and matcher settings are chosen on dev only;
            eval stays untouched until the matcher configuration is frozen
  second    yes for the codes a second annotator also judges (below), else no
  relation  exactMatch | closeMatch | broadMatch | narrowMatch | none, read as "code <relation>
            concept" (SKOS): broadMatch = the AGROVOC concept is broader than the code ("Autre
            verger" broadMatch "verger"), narrowMatch = it is narrower ("Pêche (y compris
            nectarine, brugnon)" narrowMatch peaches); none = no concept fits
  concept   an AGROVOC concept IRI of the snapshot (empty for none)
  alternatives  other concepts that are also acceptable targets, "; "-separated, decided while
            labelling (never after a matcher's output has been seen)
  note      why, when it is not obvious (homonyms, plant vs product, several fits)
Protocol (Codex review of 2026-10-26, §6; docs/notes/step12_ontology.md, 12.9):
- Before the first label, write the decision rules into the step note and apply them to every
  code: plant (taxon) vs harvested product vs land-use or land-cover concept; mixed codes
  (mixtures, "X et Y"); residual codes ("Autre ..."); and what counts as no match.
- Start from configs/lu_agrovoc_candidates.csv, and search before choosing none or a weak
  candidate: the candidates come from word matching, which misses concepts named differently,
  and a gold set limited to them would favour word matchers.
- One concept per code, the best-fitting one; the other acceptable ones in `alternatives`.
  Broad, narrow and close matches are never collapsed into exact to raise a score: their
  semantics differ (skos:exactMatch is transitive, skos:closeMatch is not; W3C SKOS Reference,
  §10). An alignment does not validate the project's irrigation assumptions or Kc values.
- Second annotator: the eval codes among the 30 largest by area, the codes without a candidate
  from their own label, and the eval "Autre ..." codes up to 30 in all, judged from the code label and
  the search command only, without the candidate table (`blind` writes the sheet,
  configs/lu_agrovoc_gold_second.csv). `check` reports agreement on the concept and Cohen's kappa
  on the relation; disagreements are adjudicated in a note, keeping both judgements. Without a
  second annotator, the thesis says so.
- Scoring (step 4) per code, the primary result: target identification (the concept is the
  gold one: strict; or one of its alternatives: lenient), and relation correctness on the codes
  whose target is right; precision, recall and F1 over the eval codes, the "none" codes
  included (a matcher that proposes a concept for them is wrong). Area-weighted scores (weights
  = clipped area of the code in the well zones, denominator = the area of all eval codes) are
  secondary: success on the large codes can hide failure on the rare ones.
- The matchers are scored against these files, so they are not edited after their outputs
  have been seen.
"""
import argparse
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from src.config import ROOT
from src.ingest.agrovoc import BROADER, LABELS
from src.kg.agrovoc_candidates import norm

GOLD = ROOT / "configs" / "lu_agrovoc_gold.csv"
SECOND = ROOT / "configs" / "lu_agrovoc_gold_second.csv"
CANDIDATES = ROOT / "configs" / "lu_agrovoc_candidates.csv"
WORKSHEET = ROOT / "data" / "interim" / "agrovoc_gold_worksheet.xlsx"
RELATIONS = ("exactMatch", "closeMatch", "broadMatch", "narrowMatch", "none")
COLUMNS = ["code", "label", "area_ha", "split", "second", "relation", "concept", "alternatives", "note"]
LABEL_COLUMNS = ["relation", "concept", "alternatives", "note"]
N_SECOND, TOP_SECOND = 30, 30


def protocol_columns(t):
    """split and second for codes ordered by area (largest first), fixed before any label."""
    t = t.reset_index(drop=True)
    t["split"] = ["dev" if i % 5 == 2 else "eval" for i in range(len(t))]
    cand = pd.read_csv(CANDIDATES)
    own = cand[cand["source"].isin(["label", "head", "tail"])].dropna(subset=["concept"])
    no_candidate = set(t["code"]) - set(own["code"])      # none from the code's own label (CML, PAQ, VER)
    ev = t["split"] == "eval"
    pick = list(t.loc[ev & (t.index < TOP_SECOND), "code"])
    pick += [c for c in t.loc[t["code"].isin(no_candidate), "code"] if c not in pick]
    pick += [c for c in t.loc[ev & t["label"].str.startswith("Autre"), "code"] if c not in pick]
    t["second"] = t["code"].isin(pick[:N_SECOND]).map({True: "yes", False: "no"})
    return t


def template():
    if GOLD.exists():
        sys.exit(f"{GOLD.relative_to(ROOT)} exists: not overwritten (use upgrade)")
    c = pd.read_csv(CANDIDATES)
    t = protocol_columns(c.groupby(["code", "label"], sort=False)["area_ha"].first().reset_index())
    for k in LABEL_COLUMNS:
        t[k] = ""
    t[COLUMNS].to_csv(GOLD, index=False)
    print(f"-> {GOLD.relative_to(ROOT)}: {len(t)} codes to judge, most area first")


def upgrade():
    """Add the protocol columns to a gold file written before them; labels are kept."""
    g = pd.read_csv(GOLD, dtype=str, keep_default_na=False)
    if g["relation"].ne("").any():
        sys.exit("labels exist: the split would be fixed after labelling; ask before changing it")
    t = protocol_columns(g)
    for k in LABEL_COLUMNS:
        t[k] = g[k] if k in g else ""
    t[COLUMNS].to_csv(GOLD, index=False)
    print(f"-> {GOLD.relative_to(ROOT)}: split {t['split'].value_counts().to_dict()}, "
          f"second annotator {int((t['second'] == 'yes').sum())} codes")


def blind():
    """The second annotator's sheet: the `second` codes, their labels and areas, no candidates."""
    if SECOND.exists():
        sys.exit(f"{SECOND.relative_to(ROOT)} exists: not overwritten")
    g = pd.read_csv(GOLD, dtype=str, keep_default_na=False)
    t = g[g["second"] == "yes"][["code", "label", "area_ha"]].copy()
    for k in LABEL_COLUMNS:
        t[k] = ""
    t.to_csv(SECOND, index=False)
    print(f"-> {SECOND.relative_to(ROOT)}: {len(t)} codes; give it with the search command only")


def worksheet(out=None, force=False):
    """Put the task 12.9 rules and word candidates beside the answers, without losing a sitting."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    out = Path(out) if out is not None else WORKSHEET
    if out.exists() and not force:
        print(f"{out} exists and may hold Assil's answers: run import first; use --force to overwrite.")
        sys.exit(1)
    g = pd.read_csv(GOLD, dtype=str, keep_default_na=False)
    candidates = pd.read_csv(CANDIDATES, dtype=str, keep_default_na=False)
    by_code = {}
    for code, rows in candidates.groupby("code", sort=False):
        values = []
        for r in rows.drop_duplicates("concept").head(8).itertuples():
            value = f"{r.concept.rsplit('/', 1)[-1]} · {r.pref_fr} | {r.pref_en}"
            if r.broader_fr:
                value += f" · ↑ {r.broader_fr}"
            values.append(value)
        by_code[code] = values

    book = Workbook()
    rules = book.active
    rules.title = "Rules"
    note = (ROOT / "docs" / "notes" / "step12_ontology.md").read_text(encoding="utf-8")
    heading = "### 12.9 gold-set decision rules (Assil, 2026-11-26, before any label)"
    # Keep all paragraphs, including the annotator and eval-example cautions, verbatim.
    section = note.split(heading, 1)[1].split("\n## ", 1)[0].strip()
    lines = [heading, *section.split("\n\n"), "Read: code <relation> concept",
             "exactMatch: same meaning", "closeMatch: nearly the same meaning",
             "broadMatch: the concept is broader than the code",
             "narrowMatch: the concept is narrower than the code", "none: no concept fits",
             "Fill relation, concept, alternatives, note. Dev codes come first: they are needed first.",
             "concept and alternatives: short id (c_3360) or full IRI; separate alternatives with ;",
             "To find a concept outside the candidates, in a terminal at the repository root:",
             'PYTHONIOENCODING=utf-8 .venv/bin/python -m src.kg.agrovoc_gold search "mots"',
             "Or use https://agrovoc.fao.org/browse/agrovoc/fr/",
             "The website shows the current release. check refuses concepts added after the 2026-10-26 snapshot.",
             "Save the file, then run after every sitting:",
             "PYTHONIOENCODING=utf-8 .venv/bin/python -m src.kg.agrovoc_gold import",
             "import saves the answers into configs/lu_agrovoc_gold.csv and checks them."]
    rules.column_dimensions["A"].width = 115
    for line in lines:
        rules.append([line])
        cell = rules.cell(rules.max_row, 1)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        rules.row_dimensions[cell.row].height = 16 * sum(max(1, (len(s) + 109) // 110)
                                                        for s in line.splitlines())
    rules["A1"].font = Font(bold=True)

    labels = book.create_sheet("Labels")
    headers = ["code", "label", "area_ha", "split", *LABEL_COLUMNS]
    headers += [f"candidate_{i}" for i in range(1, 9)]
    labels.append(headers)
    ordered = g.assign(_area=pd.to_numeric(g["area_ha"]))
    ordered = ordered.sort_values(["split", "_area"], ascending=[True, False], kind="stable")
    for _, r in ordered.iterrows():
        values = [r[k] for k in headers[:8]]
        values[2] = float(r["area_ha"])
        cand = by_code.get(r["code"], [])
        labels.append(values + cand + [""] * (8 - len(cand)))
    labels.freeze_panes = "C2"
    labels.auto_filter.ref = labels.dimensions
    dropdown = DataValidation(type="list", formula1='"' + ",".join(RELATIONS) + '"', allow_blank=True)
    dropdown.errorTitle = "Choose a relation"
    dropdown.error = "Use one of the five relations, or leave the cell empty."
    dropdown.showErrorMessage = True
    labels.add_data_validation(dropdown)
    dropdown.add(f"E2:E{labels.max_row}")
    widths = [12, 52, 15, 10, 18, 48, 60, 60] + [65] * 8
    for col, width in enumerate(widths, 1):
        labels.column_dimensions[get_column_letter(col)].width = width
        labels.cell(1, col).font = Font(bold=True)
    for row in labels.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # A note beginning with '=' remains literal text on regeneration.
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column != 1)
            if 5 <= cell.column <= 8:
                cell.fill = PatternFill("solid", fgColor="FFF2CC")
            elif cell.column >= 9:
                cell.font = Font(color="777777")
        labels.row_dimensions[row[0].row].height = 60
    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)
    book.close()
    print(f"-> {out}: {len(g)} codes, dev first; import after every sitting")


def _normalise_concept(value):
    """Accept AGROVOC short ids (including the snapshot's hexadecimal ids) or their full IRIs."""
    prefix = "http://aims.fao.org/aos/agrovoc/"
    short = value[len(prefix):] if value.startswith(prefix) else value
    if not re.fullmatch(r"c_[A-Za-z0-9_-]+", short):
        raise ValueError(f"{value!r}: expected a short id such as c_3360 or its full AGROVOC IRI")
    return prefix + short


def import_worksheet(path=None):
    """Validate every worksheet row before saving answers; snapshot errors never discard a sitting."""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    path = Path(path) if path is not None else WORKSHEET
    g = pd.read_csv(GOLD, dtype=str, keep_default_na=False)
    book = load_workbook(path)
    problems, answers, seen = [], {}, set()
    try:
        if "Labels" not in book.sheetnames:
            print("Labels: missing sheet")
            sys.exit(1)
        labels = book["Labels"]
        headers = [c.value for c in labels[1]]
        for name in ["code", *LABEL_COLUMNS]:
            if headers.count(name) != 1:
                problems.append(f"Labels!1: header {name!r} must occur exactly once")
        if not problems:
            columns = {name: headers.index(name) + 1 for name in ["code", *LABEL_COLUMNS]}
            known = set(g["code"])
            for row in labels.iter_rows(min_row=2):
                if all(c.value is None or str(c.value).strip() == "" for c in row):
                    continue
                values = {name: "" if row[col - 1].value is None else str(row[col - 1].value).strip()
                          for name, col in columns.items()}
                code = values.pop("code")

                def error(name, message):
                    cell = f"{get_column_letter(columns[name])}{row[0].row}"
                    problems.append(f"{code or '(missing code)'} Labels!{cell} ({name}): {message}")

                if not code or code not in known:
                    error("code", "missing code" if not code else "unknown code")
                elif code in seen:
                    error("code", "code occurs twice")
                seen.add(code)
                if values["relation"] and values["relation"] not in RELATIONS:
                    error("relation", f"{values['relation']!r} is not in {RELATIONS}")
                if values["concept"]:
                    try:
                        values["concept"] = _normalise_concept(values["concept"])
                    except ValueError as exc:
                        error("concept", str(exc))
                alternatives = []
                for value in values["alternatives"].split(";"):
                    if not value.strip():
                        continue
                    try:
                        alternatives.append(_normalise_concept(value.strip()))
                    except ValueError as exc:
                        error("alternatives", str(exc))
                values["alternatives"] = "; ".join(alternatives)
                answers[code] = values
            for code in sorted(known - seen):
                problems.append(f"{code} Labels!{get_column_letter(columns['code'])}: code missing from worksheet")
    finally:
        book.close()
    if problems:
        print("Worksheet format errors; gold CSV unchanged:\n  " + "\n  ".join(problems))
        sys.exit(1)
    for name in LABEL_COLUMNS:
        g[name] = [answers[code][name] for code in g["code"]]
    # Match template/upgrade's CSV format, keeping the existing UTF-8 BOM and line endings too.
    original = GOLD.read_bytes()
    encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
    newline = "\r\n" if b"\r\n" in original else "\n"
    with NamedTemporaryFile(dir=GOLD.parent, suffix=".csv", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        g.to_csv(temporary, index=False, encoding=encoding, lineterminator=newline)
        temporary.replace(GOLD)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"-> {GOLD}: answers saved. If check fails, fix the workbook and import again.")
    check()


def kappa(a, b):
    """Cohen's kappa of two label lists."""
    a, b = pd.Series(list(a)), pd.Series(list(b))
    po = float((a == b).mean())
    pe = sum(float((a == k).mean()) * float((b == k).mean()) for k in set(a) | set(b))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def search(text):
    lab = pd.read_parquet(LABELS)
    lab = lab[~lab["deprecated"]]
    q = re.compile(rf"\b{re.escape(norm(text))}\b")
    hit = lab[[bool(q.search(norm(x))) for x in lab["label"]]]
    pref = lab[lab["kind"] == "pref"].pivot_table(index="concept", columns="lang", values="label",
                                                   aggfunc="first")
    up = pd.read_parquet(BROADER).groupby("concept")["broader"].apply(list)
    for c, g in list(hit.groupby("concept"))[:40]:
        via = "; ".join(sorted(set(f"{r.label} ({r.lang} {r.kind})" for r in g.itertuples())))[:90]
        ups = " | ".join(pref.at[b, "fr"] for b in up.get(c, []) if b in pref.index)
        print(f"{c}\n    {pref.at[c, 'fr']} | {pref.at[c, 'en']}   via {via}   broader: {ups}")
    print(f"{hit['concept'].nunique()} concepts" + (" (first 40 shown)" if hit["concept"].nunique() > 40 else ""))


def check():
    g = pd.read_csv(GOLD, dtype=str, keep_default_na=False)
    codes = pd.read_csv(CANDIDATES).groupby("code", sort=False)["area_ha"].first()
    known = set(pd.read_parquet(LABELS).query("~deprecated")["concept"])
    problems = []
    if list(g.columns) != COLUMNS:
        problems.append(f"columns {list(g.columns)} instead of {COLUMNS}")
    dup = g["code"][g["code"].duplicated()].tolist()
    missing = sorted(set(codes.index) - set(g["code"]))
    extra = sorted(set(g["code"]) - set(codes.index))
    problems += [f"codes twice: {dup}"] * bool(dup) + [f"codes missing: {missing}"] * bool(missing)
    problems += [f"codes not in the zones: {extra}"] * bool(extra)
    if list(g.columns) == COLUMNS:
        problems += [f"{r.code}: split {r.split!r}" for r in g.itertuples() if r.split not in ("dev", "eval")]
        problems += [f"{r.code}: second {r.second!r}" for r in g.itertuples() if r.second not in ("yes", "no")]
        for r in g.itertuples():
            alts = [a.strip() for a in r.alternatives.split(";") if a.strip()]
            if alts and r.relation in ("none", ""):
                problems.append(f"{r.code}: alternatives without a judged concept")
            problems += [f"{r.code}: alternative {a!r} not in the snapshot" for a in alts if a not in known]
            problems += [f"{r.code}: the concept is also an alternative" for a in alts if a == r.concept]
    done = g[g["relation"] != ""]
    bad = done[~done["relation"].isin(RELATIONS)]
    problems += [f"{r.code}: relation {r.relation!r} not in {RELATIONS}" for r in bad.itertuples()]
    for r in done[done["relation"].isin(RELATIONS)].itertuples():
        if r.relation == "none" and r.concept:
            problems.append(f"{r.code}: relation none with a concept")
        if r.relation != "none" and r.concept not in known:
            problems.append(f"{r.code}: {r.concept!r} is not a concept of the AGROVOC snapshot")
    share = codes.reindex(done["code"]).sum() / codes.sum()
    print(f"{len(done)} of {len(g)} codes judged ({share:.1%} of the zone area); by relation: "
          f"{done['relation'].value_counts().to_dict()}")
    if SECOND.exists():
        b = pd.read_csv(SECOND, dtype=str, keep_default_na=False).set_index("code")
        both = done.set_index("code").join(b[b["relation"] != ""], rsuffix="_2", how="inner")
        if len(both):
            print(f"second annotator: {len(both)} codes judged by both; same concept "
                  f"{(both['concept'] == both['concept_2']).mean():.0%}, relation kappa "
                  f"{kappa(both['relation'], both['relation_2']):.2f}")
    if problems:
        sys.exit("gold set not valid:\n  " + "\n  ".join(problems))
    print("gold set valid" + ("" if len(done) == len(g) else " so far"))


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["template"]:
        template()
    elif cmd == ["upgrade"]:
        upgrade()
    elif cmd == ["blind"]:
        blind()
    elif cmd == ["worksheet"]:
        parser = argparse.ArgumentParser(description="Make Assil's AGROVOC worksheet")
        parser.add_argument("--out", type=Path)
        parser.add_argument("--force", action="store_true")
        args = parser.parse_args(sys.argv[2:])
        worksheet(args.out, args.force)
    elif cmd == ["import"]:
        parser = argparse.ArgumentParser(description="Save worksheet answers and check the gold set")
        parser.add_argument("path", nargs="?", type=Path)
        args = parser.parse_args(sys.argv[2:])
        import_worksheet(args.path)
    elif cmd == ["search"] and len(sys.argv) > 2:
        search(" ".join(sys.argv[2:]))
    elif cmd == ["check"]:
        check()
    else:
        sys.exit(__doc__)
