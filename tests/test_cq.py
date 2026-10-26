"""Competency-question queries (task 12.7): the SPARQL files of tests/cq/, run with pyoxigraph.

    PFE_DATASET=v4 python -m src.kg.build_kg && PFE_DATASET=v4 python -m src.kg.apply_rules
    PFE_DATASET=v4 python -m tests.test_cq

Each file of tests/cq/ answers one competency question or one part of it (docs/competency_questions.md
§6): its header states the parameters, what it reads (asserted facts or SHACL-AF rule outputs; no
OWL reasoning) and its columns. Parameters are pre-bound with pyoxigraph's substitutions (SEP-0007),
which apply only to variables of the SELECT list, so every query returns its parameters on each row.
Each question has a status query (supported, partial, unknown, conflicting, not_applicable, with a
reason: the common answer contract, §2), so that an empty answer from a search that covered nothing
is never read as "none".

1. Fixtures: the graph of tests/test_kg_rules.py (its acceptance cases), plus, for CQ1, a well with
   two recorded candidate units in a mapped polygon, with a groundwater body and a head series (W5),
   a well with an explicit unknown (W6) and a local stack for W1; run through the same rules
   (src.kg.apply_rules.run_rules), checked by the shapes, then queried:
   CQ1   W1 supported (depth 50 m, stack A > B > C); W2 partial (no depth, no polygon) but in the
         answer; W5 conflicting, both candidates with their sources, its body and series; W6 unknown
         with its reason; a facility not_applicable; no screen from an investigation depth
   CQ3   A: direct A-B, indirect A-C via B (polygon 1); Y: X-Y (polygon 2) and Y-Z (polygon 3), and
         no X-Z anywhere; U (in no stack) unknown; a well not_applicable
   CQ11  W1 within 5 km: W2 at 4,999 m, depth difference missing, probable, selected by main but not
         by confident-only; W2: W3 (2 m) and W1; W1 within 4 km: none, and supported (searched);
         6 km: partial (links derived within 5 km only); W6 unknown; W4 (alone in its unit) supported
2. Data (dataset v4, facts + rule outputs), against pandas / GeoPandas on the source tables:
   CQ1   the two anchors of the CQ document (W1 = 10964X0119/NYLS-1: 97 m, 671AA00; W2 =
         10906X0039/C2-1: stack 718BP02 > 671AA00); for every well, the candidate unit = the
         dataset's recorded unit, the investigation depth = the dataset's, the polygon = the BD LISA
         polygon containing the point and its stack = TABLE_PILE_ENTITES_NIV3; no screen; statuses
         from the dataset (unknown without a recorded unit, partial without a depth)
   CQ3   for every unit, the relations = the pairs of the BD LISA stacks of the graph's polygons
         (tests.test_kg_rules.oracle_relations); status unknown exactly for the units in no stack
   CQ11  for every well, the neighbours within 5 km = the same-unit pairs of wells.parquet, with
         distances and depth differences; a link is selected exactly when the policy admits its
         confidence
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pyoxigraph as ox
import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, RDFS, XSD

from src.analysis.bdlisa_profile import GPKG
from src.config import CRS_L93, DATASET, DATASET_DIR
from src.kg.apply_rules import RULES, SHAPES, check, ontology_network, rule_records, run_rules
from tests.test_kg_rules import (KG, L, RADIUS, build_fixture, d, l93, oracle_relations, store_of,
                                 violations)

CQ = Path(__file__).resolve().parent / "cq"
XSD_DOUBLE = ox.NamedNode(str(XSD.double))
XSD_INTEGER = ox.NamedNode(str(XSD.integer))
MAIN, CONF_ONLY = d("policy/main"), d("policy/confident-only")


def term(v):
    """A Python value as a pyoxigraph term: IRIs for rdflib URIRefs, xsd:double for floats."""
    if isinstance(v, (ox.NamedNode, ox.Literal)):
        return v
    if isinstance(v, rdflib.URIRef):
        return ox.NamedNode(str(v))
    if isinstance(v, float):
        return ox.Literal(repr(v), datatype=XSD_DOUBLE)
    if isinstance(v, int):
        return ox.Literal(str(v), datatype=XSD_INTEGER)
    return ox.Literal(str(v))


def py(v):
    if v is None:
        return None
    if isinstance(v, ox.Literal):
        dt = v.datatype.value
        if dt.endswith(("#double", "#decimal", "#float")):
            return float(v.value)
        if dt.endswith(("#integer", "#int", "#long")):
            return int(v.value)
        if dt.endswith("#boolean"):
            return v.value == "true"
        return v.value
    return v.value


def ask(store, name, **params):
    """Run tests/cq/<name>.rq with the parameters pre-bound; rows as dicts of Python values."""
    res = store.query((CQ / f"{name}.rq").read_text(),
                      substitutions={ox.Variable(k): term(v) for k, v in params.items()})
    cols = [v.value for v in res.variables]
    return [{c: py(r[c]) for c in cols} for r in res]


def one(store, name, **params):
    rows = ask(store, name, **params)
    assert len(rows) == 1, f"{name} {params}: {len(rows)} rows"
    return rows[0]


def local(iri):
    return iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1] if iri else iri


def to_store(g):
    s = ox.Store()
    s.load(g.serialize(format="nt", encoding="utf-8"), format=ox.RdfFormat.N_TRIPLES)
    return s


# ------------------------------------------------------------------------------- 1. fixtures
def cq_fixture():
    """The fixture of tests/test_kg_rules.py plus the CQ1 cases (module docstring)."""
    fx, u = build_fixture()
    a = fx.g.add
    a((d("piezometer/W1"), L.locatedInPolygon, d("polygon/1")))       # stack A > B > C
    w5 = fx.well("W5", 50000, 50000, u["X"], L.Confident, depth=30)  # far from every other point
    fx.attribution("piezometer/W5", w5, L.MonitoringRole, u["Y"], conf=L.Probable, rank=2)
    a((w5, L.locatedInPolygon, d("polygon/2")))                      # stack X > Y
    body = d("groundwater-body/FRDG999")
    a((body, RDF.type, L.GroundwaterBody))
    a((body, L.groundwaterBodyCode, Literal("FRDG999")))
    a((body, RDFS.label, Literal("masse d'eau de test", lang="fr")))
    a((w5, L.inGroundwaterBody, body))
    se = d("series/head-weekly-test/W5")
    a((se, RDF.type, L.ObservationSeries))
    a((d("station/W5"), L.hasObservationSeries, se))
    for p, v in ((L.seriesVariable, L.GroundwaterHead), (L.verticalDatum, Literal("NGF-IGN69")),
                 (L.temporalResolution, Literal("P7D")),
                 (L.coverageStart, Literal("2005-01-02", datatype=XSD.date)),
                 (L.coverageEnd, Literal("2026-10-18", datatype=XSD.date)),
                 (L.inRelease, fx.rel)):
        a((se, p, v))
    fx.well("W6", 60000, 60000, None, None)                          # an explicit unknown
    return fx, u


def fixture_store():
    net = ontology_network()
    rules, shapes = rdflib.Graph().parse(RULES), rdflib.Graph().parse(SHAPES)
    fx, u = cq_fixture()
    records = rule_records(rules, "test", fx.g)
    g = fx.g + records + run_rules(fx.g, rules, records)
    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, f"the CQ fixture violates the shapes: {results}"
    return to_store(g), u


def test_cq1_fixture(s):
    w = {k: d(f"piezometer/{k}") for k in ("W1", "W2", "W5", "W6")}
    rows = ask(s, "cq01_assignments", W=w["W1"])
    assert [(r["unitCode"], r["rank"], local(r["confidence"]), local(r["resolution"])) for r in rows] == \
        [("U", 1, "Confident", "ExactUnitResolution")], rows
    assert rows[0]["investigationDepthM"] == 50.0 and rows[0]["source"]
    assert [r["unitCode"] for r in ask(s, "cq01_stack", W=w["W1"])] == ["A", "B", "C"]
    assert one(s, "cq01_status", W=w["W1"])["status"] == "supported"

    rows = ask(s, "cq01_assignments", W=w["W2"])                     # no depth: still answered
    assert [(r["unitCode"], local(r["confidence"])) for r in rows] == [("U", "Probable")]
    assert rows[0]["investigationDepthM"] is None
    st = one(s, "cq01_status", W=w["W2"])
    assert st["status"] == "partial" and "depth" in st["reason"], st

    rows = ask(s, "cq01_assignments", W=w["W5"])                     # two recorded candidates
    assert [(r["unitCode"], r["rank"], local(r["confidence"])) for r in rows] == \
        [("X", 1, "Confident"), ("Y", 2, "Probable")], rows
    assert all(r["source"] for r in rows)
    assert one(s, "cq01_status", W=w["W5"])["status"] == "conflicting"
    assert [r["bodyCode"] for r in ask(s, "cq01_bodies", W=w["W5"])] == ["FRDG999"]
    se = one(s, "cq01_series", W=w["W5"])
    assert (local(se["variable"]), se["verticalDatum"], se["coverageEnd"]) == \
        ("GroundwaterHead", "NGF-IGN69", "2026-10-18"), se
    assert [(r["layerOrder"], r["unitCode"]) for r in ask(s, "cq01_stack", W=w["W5"])] == [(1, "X"), (2, "Y")]

    rows = ask(s, "cq01_assignments", W=w["W6"])                     # an explicit unknown
    assert len(rows) == 1 and rows[0]["unit"] is None and rows[0]["unknownReason"], rows
    st = one(s, "cq01_status", W=w["W6"])
    assert st["status"] == "unknown" and st["reason"] == rows[0]["unknownReason"], st

    assert one(s, "cq01_status", W=d("facility/F1"))["status"] == "not_applicable"
    assert ask(s, "cq01_assignments", W=d("facility/F1")) == []
    assert not any(r["screenTopM"] or r["screenBottomM"] for k in w for r in ask(s, "cq01_assignments", W=w[k]))
    print("  1. CQ1 fixtures: supported, partial (missing depth kept), conflicting (both candidates), "
          "unknown (with its reason), not applicable; no screen from an investigation depth")


def test_cq3_fixture(s, u):
    def rel(unit):
        return {(r["upperCode"], r["lowerCode"], local(r["kind"]), r["polygonCode"],
                 tuple(sorted((r["intervening"] or "").split()))) for r in ask(s, "cq03_relations", U=u[unit])}
    assert rel("A") == {("A", "B", "DirectContact", 1, ()), ("A", "C", "IndirectOrdering", 1, ("B",))}
    assert rel("Y") == {("X", "Y", "DirectContact", 2, ()), ("Y", "Z", "DirectContact", 3, ())}
    assert not any(("X", "Z") == x[:2] for x in rel("X") | rel("Z")), "an ordering chained across polygons"
    st = one(s, "cq03_status", U=u["A"])
    assert (st["status"], st["polygons"]) == ("supported", 1), st
    assert one(s, "cq03_status", U=u["U"])["status"] == "unknown"    # monitored, but in no stack
    assert ask(s, "cq03_relations", U=u["U"]) == []
    assert one(s, "cq03_status", U=d("piezometer/W1"))["status"] == "not_applicable"
    print("  2. CQ3 fixtures: direct and indirect relations inside one stack, none across polygons; "
          "unknown for a unit in no stack")


def test_cq11_fixture(s):
    w1, w2 = d("piezometer/W1"), d("piezometer/W2")
    rows = ask(s, "cq11_neighbours", W=w1, r=5000.0, policy=MAIN)
    assert [(r["neighbourCode"], r["unitCode"], round(r["distanceM"], 6), r["depthDifferenceM"],
             local(r["confidence"]), r["selected"]) for r in rows] == \
        [("W2", "U", 4999.0, None, "Probable", True)], rows           # W3 is 5,001 m away
    assert [r["selected"] for r in ask(s, "cq11_neighbours", W=w1, r=5000.0, policy=CONF_ONLY)] == [False]
    assert [r["neighbourCode"] for r in ask(s, "cq11_neighbours", W=w2, r=5000.0, policy=MAIN)] == ["W3", "W1"]
    assert ask(s, "cq11_neighbours", W=w1, r=4000.0, policy=MAIN) == []
    assert one(s, "cq11_status", W=w1, r=4000.0)["status"] == "supported"    # searched: none
    st = one(s, "cq11_status", W=w1, r=6000.0)
    assert st["status"] == "partial" and st["ruleRadiusM"] == RADIUS, st
    assert one(s, "cq11_status", W=d("piezometer/W6"), r=5000.0)["status"] == "unknown"
    assert ask(s, "cq11_neighbours", W=d("piezometer/W4"), r=5000.0, policy=MAIN) == []
    assert one(s, "cq11_status", W=d("piezometer/W4"), r=5000.0)["status"] == "supported"
    assert one(s, "cq11_status", W=d("facility/F1"), r=5000.0)["status"] == "not_applicable"
    print("  3. CQ11 fixtures: 4,999 m in, 5,001 m out, missing depth difference kept missing, policy "
          "selection, empty but supported, partial beyond the rule radius, unknown without a unit")


# ----------------------------------------------------------------------------------- 2. data
def iris(store, q):
    """{literal value: IRI term} from a two-column query."""
    return {r[0].value: r[1] for r in store.query("PREFIX lulcw: <https://w3id.org/lulcw#> " + q)}


def test_data(store):
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    pz = iris(store, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    assert set(pz) == set(wells["code_bss"]), "piezometers differ from the dataset's wells"

    # CQ1: the two anchors of the CQ document
    rows = ask(store, "cq01_assignments", W=pz["10964X0119/NYLS-1"])
    assert [(r["unitCode"], r["investigationDepthM"]) for r in rows] == [("671AA00", 97.0)], rows
    assert [r["unitCode"] for r in ask(store, "cq01_stack", W=pz["10906X0039/C2-1"])] == ["718BP02", "671AA00"]
    # CQ1: every well against the dataset, the BD LISA polygons and their stacks
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", columns=["codepoly"]).to_crs(CRS_L93)
    x, y = l93(wells["x"], wells["y"])
    pts = gpd.GeoDataFrame(wells[["code_bss"]], geometry=gpd.points_from_xy(x, y), crs=CRS_L93)
    inside = gpd.sjoin(pts, poly, predicate="intersects").groupby("code_bss")["codepoly"].agg(
        lambda c: {int(v) for v in c})
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    pile = pile.assign(cp=pile["CodePoly"].astype(int)).sort_values(["cp", "OrdRelatif"])
    stack_of = pile.groupby("cp")["CodeEH"].agg(list)
    statuses = {}
    for _, w in wells.iterrows():
        rows = ask(store, "cq01_assignments", W=pz[w["code_bss"]])
        units = [r["unitCode"] for r in rows if r["unitCode"]]
        want = [w["code_bdlisa"]] if isinstance(w["code_bdlisa"], str) else []
        assert units == want, (w["code_bss"], units, want)
        depth = w["profondeur_investigation"]
        assert all((r["investigationDepthM"] is None) == pd.isna(depth) for r in rows), w["code_bss"]
        assert all(pd.isna(depth) or abs(r["investigationDepthM"] - depth) < 1e-9 for r in rows)
        assert not any(r["screenTopM"] or r["screenBottomM"] for r in rows), "a screen appeared"
        assert all(r["source"] and r["release"] for r in rows), w["code_bss"]
        st = ask(store, "cq01_stack", W=pz[w["code_bss"]])
        cps = {r["polygonCode"] for r in st}
        assert len(cps) == 1 and cps <= inside.get(w["code_bss"], set()), (w["code_bss"], cps)
        assert [r["unitCode"] for r in st] == stack_of[cps.pop()], w["code_bss"]
        statuses[w["code_bss"]] = one(store, "cq01_status", W=pz[w["code_bss"]])["status"]
    want = {c: ("unknown" if not isinstance(u, str) else "partial" if pd.isna(z) else "supported")
            for c, u, z in zip(wells["code_bss"], wells["code_bdlisa"], wells["profondeur_investigation"])}
    assert statuses == want, {c: (statuses[c], want[c]) for c in want if statuses[c] != want[c]}
    n = pd.Series(statuses).value_counts().to_dict()

    # CQ3: every unit of the graph, against the BD LISA stacks of the graph's polygons
    units = iris(store, "SELECT ?c ?u WHERE { ?u lulcw:bdlisaCode ?c }")
    polys = {int(c) for c in iris(store, "SELECT ?c ?p WHERE { ?p a lulcw:ElementaryPolygon ; lulcw:polygonCode ?c }")}
    oracle = oracle_relations(polys)
    in_stack = {c for c in units if any(c in stack_of[p] for p in polys if p in stack_of.index)}
    n_rel = 0
    for code, unit in units.items():
        got = {(r["polygonCode"], r["upperCode"], r["lowerCode"], local(r["kind"]),
                tuple(sorted((r["intervening"] or "").split()))) for r in ask(store, "cq03_relations", U=unit)}
        assert got == {o for o in oracle if code in o[1:3]}, code
        n_rel += len(got)
        assert one(store, "cq03_status", U=unit)["status"] == ("supported" if code in in_stack else "unknown"), code

    # CQ11: every well, against the same-unit pairs of the dataset
    w = wells.assign(x93=x, y93=y)
    w = w[w["code_bdlisa"].notna()]
    pairs = {}
    for _, a in w.iterrows():
        for _, b in w.iterrows():
            if a["code_bss"] != b["code_bss"] and a["code_bdlisa"] == b["code_bdlisa"]:
                dist = float(np.hypot(a["x93"] - b["x93"], a["y93"] - b["y93"]))
                if dist <= RADIUS:
                    za, zb = a["profondeur_investigation"], b["profondeur_investigation"]
                    pairs.setdefault(a["code_bss"], {})[b["code_bss"]] = (
                        dist, abs(za - zb) if pd.notna(za) and pd.notna(zb) else None)
    admits = {MAIN: {"Confident", "Probable"}, CONF_ONLY: {"Confident"}}
    n_links = 0
    for code, iri in pz.items():
        for policy, levels in admits.items():
            rows = ask(store, "cq11_neighbours", W=iri, r=RADIUS, policy=policy)
            got = {r["neighbourCode"]: (r["distanceM"], r["depthDifferenceM"]) for r in rows}
            want = pairs.get(code, {})
            assert set(got) == set(want), (code, sorted(set(got) ^ set(want)))
            for k, (dist, dz) in want.items():
                assert abs(got[k][0] - dist) < 0.15 and (dz is None) == (got[k][1] is None), (code, k)
                assert dz is None or abs(got[k][1] - dz) < 1e-6, (code, k)
            assert all(r["selected"] == (local(r["confidence"]) in levels) for r in rows), (code, policy)
        n_links += len(pairs.get(code, {}))
        st = one(store, "cq11_status", W=iri, r=RADIUS)["status"]
        assert st == ("supported" if code in set(w["code_bss"]) else "unknown"), (code, st)
    print(f"  4. data: CQ1 anchors hold; {len(pz)} wells (statuses {n}) = the dataset, the BD LISA "
          f"polygons and stacks, no screen; CQ3 {len(units)} units, {n_rel} relation-polygon rows = the "
          f"stacks ({len(units) - len(in_stack)} units in no stack: unknown); CQ11 {n_links // 2} "
          f"neighbour pairs = the dataset, selections follow the policies")


def main():
    s, u = fixture_store()
    test_cq1_fixture(s)
    test_cq3_fixture(s, u)
    test_cq11_fixture(s)
    facts, derived = KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"
    if facts.exists() and derived.exists():
        test_data(store_of(facts, derived))
    else:
        print("  4. skipped: run src.kg.build_kg and src.kg.apply_rules first")
    print("test_cq: all checks passed")


if __name__ == "__main__":
    main()
