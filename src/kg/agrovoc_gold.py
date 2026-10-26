"""The RPG -> AGROVOC gold set (task 12.9, step 3): a template to fill in, a search, a check.

    python -m src.kg.agrovoc_gold template        # writes configs/lu_agrovoc_gold.csv if absent
    python -m src.kg.agrovoc_gold search "pêcher"  # concepts whose French or English labels hold
                                                   # these words (accents, case, plurals ignored)
    python -m src.kg.agrovoc_gold check           # validates the filled file

The gold set is Assil's judgement, one row per crop code of the well zones (most area first):
  relation  exactMatch | closeMatch | broadMatch | narrowMatch | none, read as "code <relation>
            concept" (SKOS): broadMatch = the AGROVOC concept is broader than the code ("Autre
            verger" broadMatch "verger"), narrowMatch = it is narrower ("Pêche (y compris
            nectarine, brugnon)" narrowMatch peaches); none = no concept fits
  concept   an AGROVOC concept IRI of the snapshot (empty for none)
  note      why, when it is not obvious (homonyms, plant vs product, several fits)
Protocol (docs/notes/step12_ontology.md, 12.9): start from configs/lu_agrovoc_candidates.csv, and
search before choosing none or a weak candidate: the candidates come from word matching, which
misses concepts named differently, and a gold set limited to them would favour word matchers.
One concept per code: the best-fitting one, the others in the note. The matchers (step 4) are
scored against this file, so it is not edited after their outputs have been seen.
"""
import re
import sys

import pandas as pd

from src.config import ROOT
from src.ingest.agrovoc import BROADER, LABELS
from src.kg.agrovoc_candidates import norm

GOLD = ROOT / "configs" / "lu_agrovoc_gold.csv"
CANDIDATES = ROOT / "configs" / "lu_agrovoc_candidates.csv"
RELATIONS = ("exactMatch", "closeMatch", "broadMatch", "narrowMatch", "none")
COLUMNS = ["code", "label", "area_ha", "relation", "concept", "note"]


def template():
    if GOLD.exists():
        sys.exit(f"{GOLD.relative_to(ROOT)} exists: not overwritten")
    c = pd.read_csv(CANDIDATES)
    t = c.groupby(["code", "label"], sort=False)["area_ha"].first().reset_index()
    t["relation"] = t["concept"] = t["note"] = ""
    t[COLUMNS].to_csv(GOLD, index=False)
    print(f"-> {GOLD.relative_to(ROOT)}: {len(t)} codes to judge, most area first")


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
    if problems:
        sys.exit("gold set not valid:\n  " + "\n  ".join(problems))
    print("gold set valid" + ("" if len(done) == len(g) else " so far"))


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["template"]:
        template()
    elif cmd == ["search"] and len(sys.argv) > 2:
        search(" ".join(sys.argv[2:]))
    elif cmd == ["check"]:
        check()
    else:
        sys.exit(__doc__)
