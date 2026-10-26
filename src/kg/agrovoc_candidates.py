"""Candidate AGROVOC concepts for every RPG crop code of the well zones (task 12.9, step 2).

    python -m src.kg.agrovoc_candidates          # after python -m src.ingest.agrovoc

Each crop code found in the 3 km zones (data/interim/crop_area_3km.parquet) has an official French
label (src.kg.landuse.nomenclature). The label, its head and its tail (the text before and after
" : ", " - " or "(") and the code's RPG group label are compared with the French and English
preferred and alternative labels of the AGROVOC snapshot (data/interim/agrovoc_labels.parquet,
one dated release). Both sides are normalised the same way: lower case, accents and punctuation
removed, a final s or x dropped from words of four letters or more, stop words removed (but
not negations: "terre non arable" is not "terre arable"). A tail that excludes ("sauf ...",
"hors ...") is not matched. Then:
  exact    a normalised label of the concept equals the normalised text; among exact matches
           the full label ranks before the head, the head before the tail
  overlap  they share content words: score = Dice coefficient of the word sets,
           2|A ∩ B| / (|A| + |B|), ties broken by character similarity (difflib ratio)
Per code, the 8 best concepts from its own label (full, head, tail), then up to 2 more from its
group label, French labels only and score >= 0.5 (candidates for a broadMatch). No threshold on
the code's own candidates: the gold set decides. AGROVOC separates French homonyms with a
qualifier ("pêche (fruits)" for peaches, "pêche" for fishing), so a qualified label also matches
on its base ("pêche"). Equal lexical scores are broken in favour of the branches that crop and
land-cover codes belong to (concepts under "plants", "Plantae", "plant products", "land
resources" or "land cover", found by their English labels in the snapshot), then by character
similarity. The English label is shown for the remaining homonyms. Each row
shows the concept's preferred labels and its broader concepts, so that a broader or narrower
relation can be judged from the table. Every IRI comes from the snapshot (working rule 12).
A candidate list built by word matching can miss the right concept: the gold set may name any
concept of the snapshot, and src.kg.agrovoc_gold checks that it exists there.

Output: configs/lu_agrovoc_candidates.csv, one row per code and candidate:
        code, label, group, group_label, crop_class, area_ha (all zones and editions), source
        (label | head | tail | group), rank, concept, pref_fr, pref_en, matched_label,
        matched_lang, matched_kind, match (exact | overlap), score, crop_or_land_branch,
        broader_fr, release
"""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

import pandas as pd

from src.analysis.rpg_profile import group_labels
from src.config import ROOT
from src.dataset.crop_demand import AREA_OUT, code_to_class, load_classes
from src.ingest.agrovoc import BROADER, LABELS
from src.kg.landuse import nomenclature

OUT = ROOT / "configs" / "lu_agrovoc_candidates.csv"
TOP, TOP_GROUP, GROUP_MIN = 8, 2, 0.5
STOP = set("""a au aux avec d de des du en et l la le les ou par plus pour sur un une y compris autre
autres an ans moins dont leur leurs the of and or other""".split())
SOURCE_RANK = {"label": 3, "head": 2, "tail": 1, "group": 0}
EXCLUDES = ("sauf ", "hors ")
SPLIT = re.compile(r"\s+[:\-–]\s+|\s*\(")
QUALIFIED = re.compile(r"^(.*\S)\s*\([^()]*\)$")
DOMAIN = ("plants", "Plantae", "plant products", "land resources", "land cover")


def norm(text):
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[’'`]", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    words = [w[:-1] if len(w) >= 4 and w[-1] in "sx" else w for w in t.split()]
    return " ".join(w for w in words if w not in STOP and not w.isdigit())


def variants(label):
    """(source, normalised text) for the label, its head and its tail."""
    out = [("label", norm(label))]
    parts = [p for p in SPLIT.split(label, maxsplit=1) if p.strip()]
    if len(parts) == 2:
        out.append(("head", norm(parts[0])))
        if not parts[1].strip().lower().startswith(EXCLUDES):
            out.append(("tail", norm(parts[1].rstrip(") "))))
    seen, uniq = set(), []
    for src, t in out:
        if t and t not in seen:
            seen.add(t)
            uniq.append((src, t))
    return uniq


def in_domain(pref, broader):
    """Concepts that have one of the DOMAIN concepts (by English label) among their ancestors."""
    anchors = set(pref.index[pref["en"].isin(DOMAIN)])
    if len(anchors) != len(DOMAIN):
        raise LookupError(f"domain anchors not found by label in the snapshot: {DOMAIN}")
    down = broader.groupby("broader")["concept"].apply(list).to_dict()
    seen, todo = set(anchors), list(anchors)
    while todo:
        for c in down.get(todo.pop(), []):
            if c not in seen:
                seen.add(c)
                todo.append(c)
    return seen


class Index:
    """Normalised label forms: every label, and the base of a qualified one ("pêche (fruits)")."""
    def __init__(self, labels, domain):
        self.rows = labels.reset_index(drop=True)
        self.domain = domain
        self.forms = []                          # (row, normalised text)
        for i, lab in enumerate(self.rows["label"]):
            self.forms.append((i, norm(lab)))
            q = QUALIFIED.match(lab)
            if q:
                self.forms.append((i, norm(q.group(1))))
        self.by_word = defaultdict(set)
        self.by_text = defaultdict(set)
        for f, (i, t) in enumerate(self.forms):
            self.by_text[t].add(f)
            for w in set(t.split()):
                self.by_word[w].add(f)

    def match(self, text, source, langs=("fr", "en")):
        """Best label row per concept for one normalised text: (concept, key, row)."""
        a = set(text.split())
        hits = set().union(*(self.by_word.get(w, set()) for w in a)) | self.by_text.get(text, set())
        best = {}
        for f in hits:
            i, t = self.forms[f]
            r = self.rows.iloc[i]
            if r["lang"] not in langs or not t:
                continue
            b = set(t.split())
            exact = t == text
            dice = 1.0 if exact else 2 * len(a & b) / (len(a) + len(b))
            c = r["concept"]
            # exact first (full label, then head, then tail), then Dice, then the crop and land
            # branches, then character similarity; preferred French labels win the last ties
            key = (exact, SOURCE_RANK[source] if exact else 0, round(dice, 6), c in self.domain,
                   SequenceMatcher(None, text, t).ratio(), r["kind"] == "pref", r["lang"] == "fr")
            if c not in best or key > best[c][0]:
                best[c] = (key, i)
        return [(c, key, i) for c, (key, i) in best.items()]


def main():
    labels = pd.read_parquet(LABELS)
    release = labels["release"].iloc[0]
    labels = labels[~labels["deprecated"]]
    pref = labels[labels["kind"] == "pref"].pivot_table(index="concept", columns="lang", values="label",
                                                         aggfunc="first")
    broader = pd.read_parquet(BROADER)
    domain = in_domain(pref, broader)
    idx = Index(labels, domain)
    up = broader.groupby("concept")["broader"].apply(list)
    nom, groups = nomenclature(), group_labels()
    area = pd.read_parquet(AREA_OUT)
    codes = (area.groupby(["CODE_CULTU", "CODE_GROUP"])["ha"].sum().reset_index()
             .sort_values("ha", ascending=False))
    codes["crop_class"] = code_to_class(codes["CODE_CULTU"].to_numpy(), codes["CODE_GROUP"].to_numpy(),
                                        load_classes()).to_numpy()
    rows = []
    for code, group, ha, cls in codes[["CODE_CULTU", "CODE_GROUP", "ha", "crop_class"]].itertuples(index=False):
        label, glabel = nom[code][0], groups.get(int(group), "")
        found = {}
        for src, text in variants(label):
            for c, key, i in idx.match(text, src):
                if c not in found or key > found[c][0]:
                    found[c] = (key, i, src)
        ranked = sorted(found.items(), key=lambda kv: kv[1][0], reverse=True)[:TOP]
        chosen = {c for c, _ in ranked}
        gnorm = norm(glabel)
        gm = sorted(((c, (key, i, "group")) for c, key, i in idx.match(gnorm, "group", ("fr",))
                     if c not in chosen and key[2] >= GROUP_MIN),
                    key=lambda kv: kv[1][0], reverse=True)[:TOP_GROUP] if gnorm else []
        for rank, (c, (key, i, src)) in enumerate(ranked + gm, start=1):
            r = idx.rows.iloc[i]
            rows.append({
                "code": code, "label": label, "group": int(group), "group_label": glabel,
                "crop_class": cls, "area_ha": round(ha, 1), "source": src, "rank": rank, "concept": c,
                "pref_fr": pref.at[c, "fr"] if c in pref.index else "",
                "pref_en": pref.at[c, "en"] if c in pref.index else "",
                "matched_label": r["label"], "matched_lang": r["lang"], "matched_kind": r["kind"],
                "match": "exact" if key[0] else "overlap", "score": round(key[2], 3),
                "crop_or_land_branch": key[3],
                "broader_fr": " | ".join(pref.at[b, "fr"] for b in up.get(c, []) if b in pref.index),
                "release": release})
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    lab = out[out["source"] != "group"]
    per_code = lab.groupby("code")["match"].agg(lambda s: "exact" if (s == "exact").any() else "overlap")
    none = sorted(set(codes["CODE_CULTU"]) - set(lab["code"]))
    print(f"AGROVOC {release}: {len(idx.rows)} labels, {len(domain)} concepts in the crop and land "
          f"branches; {len(codes)} codes -> {OUT.relative_to(ROOT)} "
          f"({len(out)} rows)")
    print(f"codes with an exact label match: {(per_code == 'exact').sum()}, word overlap only: "
          f"{(per_code == 'overlap').sum()}, no label candidate: {len(none)} {none}")
    top = codes.head(13)["CODE_CULTU"]
    print(f"the 13 codes covering 90 % of the zone area: "
          f"{', '.join(f'{c} ({per_code.get(c, 'none')})' for c in top)}")


if __name__ == "__main__":
    main()
