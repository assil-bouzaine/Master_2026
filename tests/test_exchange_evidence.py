"""The curated exchange statements (configs/exchange_evidence.csv) against their sources (CQ5, CQ6).

    python -m tests.test_exchange_evidence      # needs pdftotext (poppler)

1. Every document a statement cites is stored (data/raw/documents, src/ingest/documents.py) and its
   md5 still matches documents.json.
2. Every quote occurs verbatim (whitespace normalised) in its document, on the stated printed page:
   the page number is read from the page's own footer (BRGM: the report line ends or starts with the
   number, or, on the landscape annex pages, stands on a line of its own; the groundwater-body sheets:
   "... Page N"). A web page has no pages and is searched whole.
3. The coordinates of the points that delimit a between-points section occur on the page given.
4. Every code is real: units in BD LISA V3 (TME), watercourses in the BD TOPO snapshot, water bodies
   in the Sandre snapshot; enumerations have their allowed values; a between-points or water-body
   statement names its section, a watercourse statement its watercourse.
5. Negative controls: a quote changed by one word, or a right quote on a wrong page, is refused.
"""
import csv
import html
import json
import re
import subprocess
from functools import lru_cache

import pandas as pd
import pyogrio

from src.analysis.bdlisa_profile import GPKG
from src.config import RAW, ROOT

CSV = ROOT / "configs" / "exchange_evidence.csv"
DOCS = RAW / "documents"
ENUM = {"mechanism": {"RiverExchange", "CanalReturnFlow"},
        "section_kind": {"water_body", "between_points", "watercourse", "none"},
        "unit_mapping": {"listed_by_source", "by_name"},
        "direction": {"aquifer_to_surface", "surface_to_aquifer", "equilibrium", "no_exchange",
                      "not_qualified"},
        "hedging": {"stated", "hedged"}}


def norm(s):
    return " ".join(s.replace(" ", " ").split())


@lru_cache(maxsize=None)
def pages(doc):
    """[(printed page label, normalised text)] of a stored document."""
    index = json.loads((DOCS / "documents.json").read_text())
    f = DOCS / index[doc]["file"]
    if f.suffix == ".html":
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", f.read_text(encoding="utf-8"), flags=re.S)
        return [("web page", norm(html.unescape(re.sub(r"<[^>]+>", " ", t))))]
    out = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True,
                         check=True).stdout
    result = []
    for chunk in out.split("\f"):
        m = re.findall(r"(?:^|\n)\s*(\d{1,3})\s+BRGM/RP-71486-FR|BRGM/RP-71486-FR[^\n]*?Roussillon\s+(\d{1,3})\s*(?:\n|$)",
                       chunk)
        # the footer line of a portrait page; the annex's landscape pages put the number on a line
        # of its own; the groundwater-body sheets end each page with "... Page N"
        nums = ([a or b for a, b in m] or re.findall(r"Page\s+(\d+)", chunk)
                or re.findall(r"(?m)^\s*(\d{1,3})\s*$", chunk))
        result.append((nums[-1] if nums else "?", norm(chunk)))
    return result


def found_on(doc, text):
    """Printed pages of doc whose text holds `text` (normalised)."""
    t = norm(text)
    return [p for p, chunk in pages(doc) if t in chunk]


def rows():
    with open(CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_documents():
    index = json.loads((DOCS / "documents.json").read_text())
    import hashlib
    for doc in sorted({r["document"] for r in rows()}):
        assert doc in index, f"{doc}: not in documents.json"
        f = DOCS / index[doc]["file"]
        assert hashlib.md5(f.read_bytes()).hexdigest() == index[doc]["md5"], f"{doc}: stored copy changed"
    print(f"  1. {len(index)} documents stored, checksums match")


def test_quotes():
    bad = []
    for r in rows():
        where = found_on(r["document"], r["quote"])
        if r["page"] not in where:
            bad.append(f"{r['id']}: quote on pages {where or 'none'}, stated {r['page']}")
    assert not bad, "\n".join(bad)
    print(f"  2. {len(rows())} quotes found verbatim on their stated pages")


def test_points():
    n, bad = 0, []
    for r in rows():
        if r["section_kind"] != "between_points":
            continue
        for end in ("from", "to"):
            xy = f"{r[end + '_x']} {r[end + '_y']}"
            where = found_on(r["document"] if r["document"] == "brgm-rp-71486-fr" else "brgm-rp-71486-fr", xy)
            n += 1
            if r["points_page"] not in where:
                bad.append(f"{r['id']} {end}: {xy} on pages {where or 'none'}, stated {r['points_page']}")
    assert not bad, "\n".join(bad)
    print(f"  3. {n} section end points found on their annex page")


def test_codes():
    tme = set(pyogrio.read_dataframe(GPKG, layer="TME", read_geometry=False)["codeeh"])
    snap = sorted((RAW / "bdtopo_hydro").glob("????-??-??"))[-1]
    wc = set(pd.read_parquet(snap / "troncon_hydrographique.parquet",
                             columns=["code_du_cours_d_eau_bdcarthage"])["code_du_cours_d_eau_bdcarthage"].dropna())
    sw = sorted((RAW / "sandre_water_bodies").glob("????-??-??"))[-1]
    wb = {c.upper() for c in pd.read_parquet(sw / "masses_eau_riviere_vrap2022.parquet",
                                             columns=["CdEuMasseDEau"])["CdEuMasseDEau"]}
    ids = [r["id"] for r in rows()]
    assert len(ids) == len(set(ids)), "duplicate statement ids"
    for r in rows():
        for k, allowed in ENUM.items():
            assert r[k] in allowed, f"{r['id']}: {k} = {r[k]!r}"
        units = [u for u in r["units"].split(";") if u]
        assert units and set(units) <= tme, f"{r['id']}: units {set(units) - tme} not in BD LISA V3"
        codes = [c for c in r["watercourses"].split(";") if c]
        assert set(codes) <= wc, f"{r['id']}: watercourses {set(codes) - wc} not in BD TOPO"
        if r["section_kind"] == "water_body":
            assert r["section"].upper() in wb, f"{r['id']}: {r['section']} not a Sandre water body"
        if r["section_kind"] == "between_points":
            assert r["section"] and len(codes) == 1 and all(r[k] for k in ("from_x", "from_y", "to_x", "to_y")), r["id"]
        if r["section_kind"] == "watercourse":
            assert codes, f"{r['id']}: a watercourse statement names no watercourse"
        for k in ("period_start", "period_end"):
            assert not r[k] or re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[k]), f"{r['id']}: {k}"
    print(f"  4. codes and enumerations valid ({len(rows())} statements)")


def test_negative_controls():
    r = next(x for x in rows() if x["id"] == "frdg351-frdr224")
    assert r["page"] in found_on(r["document"], r["quote"])
    assert not found_on(r["document"], r["quote"].replace("perdant", "drainant")), "a changed word passed"
    assert "3" not in found_on(r["document"], r["quote"]), "a wrong page passed"
    print("  5. negative controls: a changed word and a wrong page are refused")


if __name__ == "__main__":
    test_documents()
    test_quotes()
    test_points()
    test_codes()
    test_negative_controls()
    print("test_exchange_evidence: all checks passed")
