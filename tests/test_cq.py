"""Competency-question queries (task 12.7): the SPARQL files of tests/cq/, run with pyoxigraph.

    PFE_DATASET=v4 python -m src.kg.build_kg && PFE_DATASET=v4 python -m src.kg.apply_rules
    PFE_DATASET=v4 python -m tests.test_cq

Each file of tests/cq/ answers one competency question or one part of it (docs/competency_questions.md
§6): its header states the parameters, what it reads (asserted facts or SHACL-AF rule outputs; no
OWL reasoning) and its columns. Parameters are bound by a VALUES clause placed at the top of the
query's WHERE block (standard SPARQL 1.1, any engine), and every query returns them on each row.
pyoxigraph's own substitutions (SEP-0007) act as a join after evaluation in 0.5, too late for the
status queries: a well-year without data must still give a row (and cq07_status took over 60 s).
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
   CQ4   in W1's search zone, X's outcrop is 0.8 inside cells: partial, weights 0.625 / 0.375 over the
         covered part, its polygon and the cells' effective-rainfall series; A fully covered; B (only
         below order 1) and Y (outcrop elsewhere) "no mapped outcrop in S", supported; Y in the
         forcing extent, which holds 1 of its 1.25 km² of mapped outcrop: partial ("S clips the
         unit"); U (not in BD LISA) unknown; a well as unit or a crop zone as extent not_applicable;
         the facts without the
         rule outputs answer unknown for A, never "no mapped outcrop"
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
   CQ4   for every search zone and the forcing extent, coverages and cell weights = the GeoPandas
         oracle of tests.test_kg_rules (BD LISA and the raw SAFRAN grid); partial exactly where part of
         the outcrop is outside the cells; each well's recorded unit without outcrop in its zone:
         "no mapped outcrop", supported; in the forcing extent, partial exactly for the units whose
         mapped outcrop reaches beyond the cells; MILLAS C2-1 / 718BP02: 27.08 km² (Codex review of
         2026-10-26); the facts without the rule outputs: unknown for it
   The data checks run only on a validated release (src.kg.release.check).
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pyoxigraph as ox
import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, RDFS, SKOS, XSD

from src.analysis.bdlisa_profile import GPKG
from src.analysis.bnpe_profile import load as load_bnpe
from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, DATASET, DATASET_DIR, INTERIM
from src.dataset.crop_demand import AREA_OUT, code_to_class, load_classes
from src.kg import pump_attribution as pa
from src.kg.apply_rules import RULES, SHAPES, check, ontology_network, rule_records, run_rules
from src.kg.build_kg import BNPE_SNAPSHOT, PLAIN_MARGIN_DEG
from src.kg import release
from src.kg.cq import ask, iris, local, one
from tests.test_kg_rules import (GEO, KG, L, RADIUS, SOSA, TIME, build_fixture, d, l93,
                                 oracle_coverage, oracle_mapped_outcrop, oracle_relations, store_of,
                                 violations)

MAIN, CONF_ONLY = d("policy/main"), d("policy/confident-only")


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
    # CQ2 / CQ12: F6, a deep borehole whose record says V (rank 2, possible) and whose depth says U
    # (rank 1, probable); annual declarations of 2020 for F1-F6 in a reporting extent
    f6 = fx.facility("F6", 500, 0, u["U"], L.Probable)
    fx.attribution("facility/F6", f6, L.AbstractionRole, u["V"], conf=L.Possible, rank=2)
    extent, year = d("extent/test"), d("interval/year/2020")
    a((extent, RDF.type, GEO.Feature))
    a((year, RDF.type, TIME.ProperInterval))
    a((year, TIME.hasBeginning, d("instant/2020-01-01")))
    a((d("instant/2020-01-01"), TIME.inXSDDate, Literal("2020-01-01", datatype=XSD.date)))
    for code, use, m3 in FIXTURE_DECLARATIONS:
        f, o = d(f"facility/{code}"), d(f"abstraction/{code}/2020/{use or 'none'}")
        a((f, GEO.sfWithin, extent))
        for p, v in ((RDF.type, L.AnnualAbstractionRecord), (SOSA.hasFeatureOfInterest, f),
                     (SOSA.observedProperty, L.DeclaredAnnualVolume),
                     (SOSA.hasSimpleResult, Literal(m3, datatype=XSD.double)),
                     (SOSA.phenomenonTime, year), (L.waterSource, L.GroundwaterSource),
                     (L.recordKind, L.DeclaredRecord), (L.inRelease, fx.rel)):
            a((o, p, v))
        if use:
            a((o, L.waterUse, L[use]))
    # CQ7: the three crop codes aligned to synthetic concepts of our own namespace (a stand-in for
    # the AGROVOC alignments of task 12.9; no unverified external IRI)
    for code in ("PEC", "AGR", "ZZZ"):
        a((d(f"crop-code/{code}"), SKOS.closeMatch, d(f"test-concept/{code.lower()}")))
    return fx, u


# facility, use, declared m³ in 2020: F1 exact U probable, F2 group G probable, F3 unknown,
# F4 exact U possible, F5 exact U confident, F6 two alternatives (U rank 1, V rank 2)
FIXTURE_DECLARATIONS = (("F1", "DrinkingWaterUse", 100.0), ("F1", None, 5.0),
                        ("F2", "IrrigationUse", 20.0), ("F3", "IrrigationUse", 50.0),
                        ("F4", "DrinkingWaterUse", 30.0), ("F5", "DrinkingWaterUse", 10.0),
                        ("F6", "DrinkingWaterUse", 100.0))


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


def test_cq2_fixture(s):
    w1 = d("piezometer/W1")

    def cand(policy):
        return [(r["bnpeCode"], round(r["distanceM"], 6), r["rank"], local(r["resolution"]),
                 r["candidateCode"], local(r["confidence"]), r["selected"], r["alternatives"])
                for r in ask(s, "cq02_candidates", W=w1, r=5000.0, policy=policy)]
    main = cand(MAIN)
    assert main == [("F1", 100.0, 1, "ExactUnitResolution", "U", "Probable", True, None),
                    ("F2", 200.0, 1, "UnitGroupResolution", "group g", "Probable", True, None),
                    ("F4", 400.0, 1, "ExactUnitResolution", "U", "Possible", False, None),
                    ("F6", 500.0, 1, "ExactUnitResolution", "U", "Probable", True,
                     "rank 2: V (Possible)")], main                    # F5 is 20 km away
    allp, conf = cand(d("policy/all-links")), cand(CONF_ONLY)
    assert [r[6] for r in allp] == [True] * 4 and [r[6] for r in conf] == [False] * 4
    assert [r[:6] + r[7:] for r in allp] == [r[:6] + r[7:] for r in main] == [r[:6] + r[7:] for r in conf], \
        "a policy changed the evidence, not only the selection"
    rows = ask(s, "cq02_candidates", W=w1, r=5000.0, policy=MAIN)
    assert set(rows[0]["uses"].split()) == {"DrinkingWaterUse", "UseNotRecorded"}
    assert (rows[0]["firstYear"], rows[0]["lastYear"]) == (2020, 2020)
    un = ask(s, "cq02_unresolved", W=w1, r=5000.0)
    assert [(r["bnpeCode"], round(r["distanceM"], 6)) for r in un] == [("F3", 300.0)] and un[0]["unknownReason"]
    assert one(s, "cq02_status", W=w1, r=5000.0)["status"] == "supported"
    assert one(s, "cq02_status", W=d("piezometer/W6"), r=5000.0)["status"] == "unknown"
    assert one(s, "cq02_status", W=d("facility/F1"), r=5000.0)["status"] == "not_applicable"
    print("  4. CQ2 fixtures: exact and group-level candidates with their resolution, the alternative "
          "of a two-candidate borehole kept, the unknown reported apart; policies change the "
          "selection only")


def test_cq12_fixture(s):
    ext = d("extent/test")
    declared = {}
    for r in ask(s, "cq12_declared", year=2020, extent=ext):
        declared[r["use"]] = declared.get(r["use"], 0.0) + r["volumeM3"]
    assert declared == {"DrinkingWaterUse": 240.0, "IrrigationUse": 70.0, "UseNotRecorded": 5.0}, declared
    want = {
        MAIN: {("DrinkingWaterUse", "unit", "U"): 210.0, ("DrinkingWaterUse", "unresolved", None): 30.0,
               ("IrrigationUse", "unit group", "group g"): 20.0, ("IrrigationUse", "unresolved", None): 50.0,
               ("UseNotRecorded", "unit", "U"): 5.0},
        CONF_ONLY: {("DrinkingWaterUse", "unit", "U"): 10.0, ("DrinkingWaterUse", "unresolved", None): 230.0,
                    ("IrrigationUse", "unresolved", None): 70.0, ("UseNotRecorded", "unresolved", None): 5.0},
        d("policy/all-links"): {("DrinkingWaterUse", "unit", "U"): 240.0,
                                ("IrrigationUse", "unit group", "group g"): 20.0,
                                ("IrrigationUse", "unresolved", None): 50.0, ("UseNotRecorded", "unit", "U"): 5.0},
    }
    for policy, w in want.items():
        rows = ask(s, "cq12_accounting", year=2020, extent=ext, policy=policy)
        got = {(r["use"], r["allocation"], r["targetCode"]): r["volumeM3"] for r in rows}
        assert got == w, (local(str(policy)), got)
        for use, total in declared.items():   # the parts add up to the declared total, never more
            assert abs(sum(v for (u, _, _), v in got.items() if u == use) - total) < 1e-9, (policy, use)
        assert not any(t == "V" for _, _, t in got), "F6's alternative received volume"
    assert ask(s, "cq12_accounting", year=2019, extent=ext, policy=MAIN) == []   # no declaration: no row
    print("  5. CQ12 fixtures: the two-candidate borehole counted once (100 m³, never 200), unresolved "
          "and group-level volume kept apart, the parts add up to the declared total under every policy")


def test_cq7_fixture(s):
    w1 = d("piezometer/W1")
    crops = {r["code"]: (r["areaHa"], r["class"], local(r["irrigationAssumption"]), local(r["alignment"]))
             for r in ask(s, "cq07_crops", W=w1, year=2023)}
    assert crops == {"PEC": (4.0, "orchard", "UsuallyIrrigated", "pec"),
                     "AGR": (2.0, "citrus", "UsuallyIrrigated", "agr"),
                     "ZZZ": (1.0, "unmapped", None, "zzz")}, crops      # an override beats the group
    classes = {r["class"]: (r["areaHa"], r["codes"]) for r in ask(s, "cq07_classes", W=w1, year=2023)}
    assert classes == {"orchard": (4.0, 1), "citrus": (2.0, 1), "unmapped": (1.0, 1)}, classes
    assert sum(a for a, _ in classes.values()) == sum(c[0] for c in crops.values())   # unmapped kept
    dem = {local(r["property"]): (r["demandM3"], local(r["category"]), r["thresholdM3"])
           for r in ask(s, "cq07_demand", W=w1, year=2023)}
    assert dem == {"PotentialIrrigationDemandMain": (2000.0, "HighIrrigationDemand", 800.0),
                   "PotentialIrrigationDemandWide": (2500.0, None, None)}, dem
    assert one(s, "cq07_status", W=w1, year=2023)["status"] == "supported"
    for y in (2020, 2016):        # no RPG edition of 2020; 2016 has a demand estimate but no crops
        st = one(s, "cq07_status", W=w1, year=y)
        assert st["status"] == "unknown" and ask(s, "cq07_crops", W=w1, year=y) == [], (y, st)
    assert one(s, "cq07_status", W=d("facility/F1"), year=2023)["status"] == "not_applicable"
    print("  6. CQ7 fixtures: original codes, their classes (override before group) and alignments, "
          "the unmapped area kept in the total, the dated demand category; a 2023 edition does not "
          "answer 2020")


def test_cq8_fixture(s):
    w1 = d("piezometer/W1")

    def infl(policy):
        return {(r["driverCode"], local(r["resolution"])): (local(r["responseSign"]), local(r["eligibility"]),
                                                            local(r["confidence"]), r["viaCode"], r["selected"])
                for r in ask(s, "cq08_influences", W=w1, policy=policy)}
    main = infl(MAIN)
    assert main == {("F1", "ExactUnitResolution"): ("NegativeResponse", "EligibleConstraint", "Probable", "U", True),
                    ("F2", "UnitGroupResolution"): ("UnknownResponse", "IneligibleConstraint", "Probable", "g", True),
                    ("F4", "ExactUnitResolution"): ("NegativeResponse", "EligibleConstraint", "Possible", "U", False),
                    ("F6", "ExactUnitResolution"): ("NegativeResponse", "EligibleConstraint", "Probable", "U", True)}, main
    assert all(v[4] for v in infl(d("policy/all-links")).values())
    assert not any(v[4] for v in infl(CONF_ONLY).values())        # every facility path is probable or less
    st = one(s, "cq08_status", W=w1)
    assert st["status"] == "partial" and st["drivers"] == "PumpingDrawdown", st
    assert ask(s, "cq08_influences", W=d("piezometer/W6"), policy=MAIN) == []
    assert one(s, "cq08_status", W=d("piezometer/W6"))["status"] == "unknown"
    print("  7. CQ8 fixtures: a supported pumping path gives a conditional non-increasing sign, a "
          "group-level path no sign; an unaccepted segment blocks the path; partial: pumping only")


def test_cq4_fixture(s, u):
    zone, forcing, rule = d("outcrop-zone/W1"), d("extent/forcing-cells-test"), d("rule/outcrop-coverage")
    cov = one(s, "cq04_coverage", U=u["X"], S=zone)
    assert (cov["outcropAreaM2"], cov["coveredAreaM2"], cov["coveredFraction"], cov["polygons"], cov["rule"]) == \
        (1.0e6, 8.0e5, 0.8, 1, str(rule)), cov
    cells = [(local(r["cell"]), r["weight"], r["coveredAreaM2"], r["effectiveRainfallIn"], r["soilDrainageIn"])
             for r in ask(s, "cq04_cells", U=u["X"], S=zone)]
    assert cells == [("c1", 0.625, 5.0e5, "forcing_weekly.parquet [cell_id = c1, column PE]", None),
                     ("c2", 0.375, 3.0e5, "forcing_weekly.parquet [cell_id = c2, column PE]", None)], cells
    out = [(r["polygonCode"], r["areaInExtentM2"], r["areaInCellsM2"]) for r in ask(s, "cq04_outcrop", U=u["X"], S=zone)]
    assert out == [(2, 1.0e6, 8.0e5)], out
    status = {k: (r["status"], r["reason"]) for k, uu, ss in (
        ("A", u["A"], zone), ("X", u["X"], zone), ("B", u["B"], zone), ("Y in zone", u["Y"], zone),
        ("Y in forcing", u["Y"], forcing), ("U", u["U"], zone), ("a well", d("piezometer/W1"), zone),
        ("a crop zone", u["A"], d("zone/W1"))) for r in [one(s, "cq04_status", U=uu, S=ss)]}
    assert {k: v[0] for k, v in status.items()} == {
        "A": "supported", "X": "partial", "B": "supported", "Y in zone": "supported", "Y in forcing": "partial",
        "U": "unknown", "a well": "not_applicable", "a crop zone": "not_applicable"}, status
    assert status["B"][1].startswith("no mapped outcrop") and "not described by BD LISA" in status["U"][1]
    y = one(s, "cq04_status", U=u["Y"], S=forcing)      # Y: 1 of its 1.25 km² inside the forcing extent
    assert y["status"] == "partial" and y["reason"].startswith("S clips the unit") and y["unitShareInS"] == 0.8, y
    assert one(s, "cq04_coverage", U=u["X"], S=zone)["unitShareInS"] == 0.5   # a search zone: reported only
    assert ask(s, "cq04_coverage", U=u["B"], S=zone) == [] and ask(s, "cq04_cells", U=u["B"], S=zone) == []
    # the facts without the rule outputs: the outcrop of A is there, its coverage is not, so the answer
    # is unknown, never "no mapped outcrop" (Codex review of 2026-10-26, §1)
    facts_only = to_store(cq_fixture()[0].g)
    st = one(facts_only, "cq04_status", U=u["A"], S=zone)
    assert st["status"] == "unknown" and "no coverage was derived" in st["reason"], st
    assert one(facts_only, "cq04_status", U=u["B"], S=zone)["status"] == "supported"   # searched: none
    print("  8. CQ4 fixtures: outcrop, covered fraction 0.8 and weights 0.625 / 0.375 renormalised over the "
          "covered part; no outcrop of B in S (supported, not zero recharge); U not in BD LISA (unknown); "
          "a unit-wide extent that clips the unit: partial; outcrop facts without a derived coverage: "
          "unknown, not a negative answer")


# ----------------------------------------------------------------------------------- 2. data
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
    print(f"  9. data: CQ1 anchors hold; {len(pz)} wells (statuses {n}) = the dataset, the BD LISA "
          f"polygons and stacks, no screen; CQ3 {len(units)} units, {n_rel} relation-polygon rows = the "
          f"stacks ({len(units) - len(in_stack)} units in no stack: unknown); CQ11 {n_links // 2} "
          f"neighbour pairs = the dataset, selections follow the policies")
    test_data_pumps(store, wells, pz, x, y)
    test_data_landuse(store, wells, pz)


BNPE_USE = {"AEP": "DrinkingWaterUse", "IRR": "IrrigationUse", "IND": "IndustryUse",
            "CAN": "CanalSupplyUse", "ENE": "EnergyUse"}   # BNPE code_usage -> lulcw water use
ADMITS = {"main": {"confident", "probable"}, "confident-only": {"confident"},
          "all-links": {"confident", "probable", "possible"}}


def pump_oracle():
    """Facilities (BNPE snapshot, groundwater) with Lambert-93 points, and each facility's rank-1
    candidate with its confidence at the two resolutions, restated from the attribution table of
    task 12.3 and its rule evaluation: a measured rule (flag_true, flag_false) is probable at a
    resolution only if it fired on enough recorded boreholes, at enough precision, for the
    facility's main use; where the exact unit is less certain than its group, the group keeps the
    table's confidence."""
    bnpe = load_bnpe(BNPE_SNAPSHOT)
    gw = bnpe[bnpe["source"] == "groundwater"].copy()
    fac = gw.groupby("code_ouvrage")[["longitude", "latitude"]].first()
    fac["x93"], fac["y93"] = l93(fac["longitude"], fac["latitude"])
    attr = pd.read_parquet(INTERIM / "pump_unit_attribution.parquet")
    use_main = pd.read_parquet(INTERIM / "pump_unit_evidence.parquet").set_index("code_ouvrage")["usage_main"]
    ev = json.loads((INTERIM / "pump_unit_attribution_eval.json").read_text())["rules"]
    rank = {"possible": 0, "probable": 1, "confident": 2}
    best = attr.dropna(subset=["unit"]).sort_values("rank").groupby("code_ouvrage").first()
    exact, group = {}, {}
    for code, r in best.iterrows():
        conf = r["confidence"]
        exact[code] = conf
        if r["rule"] in ("flag_true", "flag_false"):
            e = ev[r["rule"]]
            ok = (e["fires_on"] >= pa.MIN_EVAL and e["precision_entity"] >= pa.PRECISION_PROBABLE
                  and use_main.get(code) in e["by_use"])
            e_conf = "probable" if ok else "possible"
            if rank[e_conf] < rank[conf]:
                exact[code], group[code] = e_conf, conf
    best = best.assign(exact_conf=pd.Series(exact), group_conf=pd.Series(group))
    return gw, fac, attr, best


def test_data_pumps(store, wells, pz, x, y):
    gw, fac, attr, best = pump_oracle()
    with_unit = attr.dropna(subset=["unit"])
    with_unit = with_unit[with_unit["code_ouvrage"].isin(fac.index)].join(fac[["x93", "y93"]], on="code_ouvrage")
    unresolved = fac[~fac.index.isin(set(with_unit["code_ouvrage"]))]
    rule_of = attr.set_index(["code_ouvrage", "rank"])["rule"]

    # CQ2: every well with a unit, against the attribution table and the BNPE points
    w = wells.assign(x93=x, y93=y)
    n_exact = n_group = n_unres = n_infl = 0
    for _, b in w.iterrows():
        iri = pz[b["code_bss"]]
        if not isinstance(b["code_bdlisa"], str):
            assert one(store, "cq02_status", W=iri, r=RADIUS)["status"] == "unknown"
            assert one(store, "cq08_status", W=iri)["status"] == "unknown"
            continue
        rows = ask(store, "cq02_candidates", W=iri, r=RADIUS, policy=MAIN)
        m = with_unit[with_unit["unit"] == b["code_bdlisa"]]
        dist = np.hypot(m["x93"] - b["x93"], m["y93"] - b["y93"])
        want = {(c, int(k)): float(dd) for c, k, dd in zip(m["code_ouvrage"], m["rank"], dist) if dd <= RADIUS}
        got = {(r["bnpeCode"], r["rank"]): r["distanceM"] for r in rows if local(r["resolution"]) == "ExactUnitResolution"}
        assert set(got) == set(want), (b["code_bss"], sorted(set(got) ^ set(want))[:5])
        assert all(abs(got[k] - want[k]) < 0.15 for k in want), b["code_bss"]
        for r in rows:
            assert r["selected"] == (local(r["confidence"]).lower() in ADMITS["main"]), r
            if local(r["resolution"]) == "UnitGroupResolution":   # the split of a measured rule
                assert rule_of[(r["bnpeCode"], r["rank"])] in ("flag_true", "flag_false"), r
                n_group += 1
            if local(r["rule"]) in ("pump-flag-true", "pump-flag-false") and local(r["confidence"]) == "Probable":
                assert r["applicableUse"], f"{r['bnpeCode']}: a probable measured rule without its use"
        d2 = np.hypot(unresolved["x93"] - b["x93"], unresolved["y93"] - b["y93"])
        want_u = set(unresolved.index[d2 <= RADIUS])
        assert {r["bnpeCode"] for r in ask(store, "cq02_unresolved", W=iri, r=RADIUS)} == want_u, b["code_bss"]
        assert one(store, "cq02_status", W=iri, r=RADIUS)["status"] == "supported"
        n_exact += len(want)
        n_unres += len(want_u)
        # CQ8: the influences (rule outputs) against the CQ2 candidates (read from the attributions)
        inf = {(r["driverCode"], local(r["resolution"])): r for r in ask(store, "cq08_influences", W=iri, policy=MAIN)}
        cand = {(r["bnpeCode"], local(r["resolution"])): r for r in rows}
        assert inf.keys() == cand.keys(), (b["code_bss"], sorted(set(inf) ^ set(cand))[:4])
        for k, r in inf.items():
            exact = k[1] == "ExactUnitResolution"
            assert (local(r["responseSign"]), local(r["eligibility"])) == (
                ("NegativeResponse", "EligibleConstraint") if exact else ("UnknownResponse", "IneligibleConstraint")), k
            assert r["selected"] == cand[k]["selected"] and abs(r["distanceM"] - cand[k]["distanceM"]) < 1e-6, k
        assert one(store, "cq08_status", W=iri)["status"] == "partial"
        n_infl += len(inf)

    # CQ12: every year, the plain's facility extent, the three policies
    ext = iris(store, 'SELECT ?k ?e WHERE { ?e a <http://www.opengis.net/ont/geosparql#Feature> . '
                      'BIND (STRAFTER(STR(?e), "/extent/") AS ?k) }')["plain-box-margin"]
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    mg = PLAIN_MARGIN_DEG
    inside = fac[fac["longitude"].between(lon0 - mg, lon1 + mg) & fac["latitude"].between(lat0 - mg, lat1 + mg)].index
    rec = gw[gw["code_ouvrage"].isin(inside)].assign(
        use=lambda t: t["code_usage"].map(BNPE_USE).fillna("UseNotRecorded"), year=lambda t: t["annee"].astype(int))
    rec = rec.join(best[["unit", "exact_conf", "group_conf"]], on="code_ouvrage")
    totals = {"declared": 0.0, "main unit": 0.0, "main unit or group": 0.0}
    for year in sorted(rec["year"].unique()):
        ry = rec[rec["year"] == year]
        declared = {}
        for r in ask(store, "cq12_declared", year=int(year), extent=ext):
            declared[r["use"]] = declared.get(r["use"], 0.0) + r["volumeM3"]
        want_decl = ry.groupby("use")["volume"].sum().to_dict()
        assert declared.keys() == want_decl.keys() and all(
            abs(declared[k] - v) <= 1e-6 * max(1.0, v) for k, v in want_decl.items()), (year, declared, want_decl)
        for policy, levels in ADMITS.items():
            rows = ask(store, "cq12_accounting", year=int(year), extent=ext, policy=d(f"policy/{policy}"))
            got = {}
            for r in rows:
                key = (r["use"], r["allocation"], r["targetCode"] if r["allocation"] == "unit" else None)
                got[key] = got.get(key, 0.0) + r["volumeM3"]
            kind = np.where(ry["exact_conf"].isin(levels), "unit",
                            np.where(ry["group_conf"].isin(levels), "unit group", "unresolved"))
            target = np.where(kind == "unit", ry["unit"], None)
            want = ry.assign(kind=kind, target=target).groupby(["use", "kind", "target"], dropna=False)["volume"].sum()
            want = {(u, k, t if isinstance(t, str) else None): v for (u, k, t), v in want.items()}
            assert got.keys() == want.keys(), (year, policy, sorted(set(got) ^ set(want))[:4])
            assert all(abs(got[k] - v) <= 1e-6 * max(1.0, v) for k, v in want.items()), (year, policy)
            for use, total in declared.items():
                assert abs(sum(v for (u, _, _), v in got.items() if u == use) - total) <= 1e-6 * max(1.0, total)
            if policy == "main" and 2012 <= year <= 2024:
                totals["main unit"] += sum(v for (_, k, _), v in got.items() if k == "unit")
                totals["main unit or group"] += sum(v for (_, k, _), v in got.items() if k != "unresolved")
        if 2012 <= year <= 2024:
            totals["declared"] += sum(declared.values())
    share = {k: 100 * v / totals["declared"] for k, v in totals.items() if k != "declared"}
    print(f"  10. data: CQ2 {n_exact} exact and {n_group} group-level candidate rows within 5 km of the wells "
          f"= the attribution table and the BNPE points, {n_unres} unresolved neighbours; CQ8 {n_infl} "
          f"influences = the CQ2 candidates (signs and eligibility by resolution); CQ12 every year "
          f"{rec['year'].min()}-{rec['year'].max()}: declared totals = the BNPE snapshot, allocations = the table "
          f"under the three policies, parts add up to the totals; main policy 2012-2024: "
          f"{share['main unit']:.1f} % at exact unit, {share['main unit or group']:.1f} % with the unit groups "
          f"(of {totals['declared'] / 1e6:.1f} Mm³ declared; docs/pump_coverage.md, on the dataset's "
          f"reconstruction: 61.8 % and 72.3 %)")


def test_data_landuse(store, wells, pz):
    """CQ7 for every well and RPG year, against the clipped areas, the class table and the index."""
    ar = pd.read_parquet(AREA_OUT)
    groups = ar.groupby("CODE_CULTU")["CODE_GROUP"].first()
    spec = dict(zip(groups.index, code_to_class(groups.index.to_numpy(), groups.to_numpy(), load_classes())))
    ar = ar.assign(cls=ar["CODE_CULTU"].map(spec).fillna("unmapped"))
    by_code = ar.groupby(["code_bss", "rpg_year", "CODE_CULTU"])["ha"].sum()
    by_class = ar.groupby(["code_bss", "rpg_year", "cls"])["ha"].sum()
    dem = pd.read_parquet(INTERIM / f"crop_demand_weekly_{DATASET}.parquet",
                          columns=["code_bss", "week", "demand_main_m3", "demand_wide_m3"])
    days = dem.loc[dem.index.repeat(7)].reset_index(drop=True)   # each week spread over its 7 days
    days["day"] = days["week"] - pd.to_timedelta(np.tile(np.arange(6, -1, -1), len(dem)), unit="D")
    tot = days.groupby(["code_bss", days["day"].dt.year])[["demand_main_m3", "demand_wide_m3"]].sum() / 7.0
    thr = float(np.quantile(tot.loc[(slice(None), list(range(2015, 2020))), "demand_main_m3"], 2 / 3))
    years = sorted(ar["rpg_year"].unique())
    has_code, has_class = set(by_code.index.droplevel(2)), set(by_class.index.droplevel(2))
    n_rows = 0
    for code, iri in pz.items():
        for y in years:
            y = int(y)
            crops = {r["code"]: r for r in ask(store, "cq07_crops", W=iri, year=y)}
            want = by_code.loc[code, y] if (code, y) in has_code else pd.Series(dtype=float)
            assert set(crops) == set(want.index), (code, y, sorted(set(crops) ^ set(want.index))[:4])
            assert all(abs(crops[k]["areaHa"] - v) <= 1e-6 for k, v in want.items()), (code, y)
            assert all(crops[k]["class"] == spec.get(k, "unmapped") for k in crops), (code, y)
            assert not any(r["alignment"] for r in crops.values())       # no alignment before 12.9
            cls = {r["class"]: r["areaHa"] for r in ask(store, "cq07_classes", W=iri, year=y)}
            wc = by_class.loc[code, y] if (code, y) in has_class else pd.Series(dtype=float)
            assert cls.keys() == set(wc.index) and all(abs(cls[k] - v) <= 1e-4 for k, v in wc.items()), (code, y)
            dm = {local(r["property"]): r for r in ask(store, "cq07_demand", W=iri, year=y)}
            main, wide = tot.loc[(code, y)]
            assert abs(dm["PotentialIrrigationDemandMain"]["demandM3"] - main) <= 0.051, (code, y)
            assert abs(dm["PotentialIrrigationDemandWide"]["demandM3"] - wide) <= 0.051, (code, y)
            cat = local(dm["PotentialIrrigationDemandMain"]["category"])
            assert cat == ("HighIrrigationDemand" if dm["PotentialIrrigationDemandMain"]["demandM3"]
                           >= dm["PotentialIrrigationDemandMain"]["thresholdM3"] else "BelowHighIrrigationDemand")
            assert abs(dm["PotentialIrrigationDemandMain"]["thresholdM3"] - thr) <= 0.11
            st = one(store, "cq07_status", W=iri, year=y)
            assert st["status"] == "partial" and st["unalignedCodes"] == len(crops), (code, y, st)
            n_rows += len(crops)
        for y in (min(years) - 1, max(years) + 1):                      # no edition: unknown
            assert one(store, "cq07_status", W=iri, year=int(y))["status"] == "unknown", (code, y)
    print(f"  11. data: CQ7 {len(pz)} wells x {len(years)} RPG editions: {n_rows} code rows, class areas and "
          f"demand estimates = the clipped areas, the class table and the weekly index (threshold "
          f"{thr:,.0f} m³); every answer partial (codes not yet aligned); {years[0] - 1} and "
          f"{years[-1] + 1} unknown")


def test_data_forcing(store, facts_file):
    """CQ4 for every well's search zone and the forcing extent, against the GeoPandas oracle of
    tests/test_kg_rules.py (BD LISA and the raw SAFRAN grid); the MILLAS anchor; and the facts
    without their rule outputs, which must answer unknown, not "no mapped outcrop"."""
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    unit = iris(store, "SELECT ?c ?u WHERE { ?u lulcw:bdlisaCode ?c }")
    described = {c for c, in ((r[0].value,) for r in store.query(
        "PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#> "
        "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }"))}
    zone = iris(store, "SELECT ?c ?z WHERE { ?z a lulcw:OutcropSearchZone ; lulcw:zoneOf/lulcw:bssCode ?c }")
    assert set(zone) == set(wells["code_bss"]), "search zones differ from the dataset's wells"
    extent = {**zone, "forcing-cells": ox.NamedNode(str(d("extent/forcing-cells")))}
    want = {k: v for k, v in oracle_coverage(described, wells).items() if v[0] >= 50.0}
    unit_m2 = oracle_mapped_outcrop(described)
    n_cells, statuses = 0, {}
    for (key, code), (o, c, by_cell) in want.items():
        S, U = extent[key], unit[code]
        r = one(store, "cq04_coverage", U=U, S=S)
        assert abs(r["outcropAreaM2"] - o) <= 50 and abs(r["coveredAreaM2"] - c) <= 50, (key, code, r, o, c)
        cells = {f"{x['gridXHm']}_{x['gridYHm']}": x["weight"] for x in ask(store, "cq04_cells", U=U, S=S)}
        assert abs(sum(cells.values()) - 1) <= 1e-9 if c > 0 else not cells, (key, code)
        assert all(abs(cells.get(k, 0.0) - a / c) <= 1e-5 for k, a in by_cell.items()), (key, code)
        n_cells += len(cells)
        st = one(store, "cq04_status", U=U, S=S)["status"]
        clipped = key == "forcing-cells" and o < unit_m2[code] * (1 - 1e-6) - 10
        assert st == ("partial" if c < o - 1e-6 * o or clipped else "supported"), (key, code, st, c, o)
        statuses[st] = statuses.get(st, 0) + 1
    # each well's recorded unit: with outcrop in its zone, the coverage above; without, a completed
    # search that found none (supported, "no mapped outcrop"); not in BD LISA, unknown
    rec = dict(zip(wells["code_bss"], wells["code_bdlisa"]))
    none_found = 0
    for b, z in zone.items():
        code = rec.get(b)
        if not isinstance(code, str) or code not in unit:
            continue
        st = one(store, "cq04_status", U=unit[code], S=z)
        if code not in described:
            assert st["status"] == "unknown", (b, code, st)
        elif (b, code) not in want:
            assert st["status"] == "supported" and st["reason"].startswith("no mapped outcrop"), (b, code, st)
            none_found += 1
    millas = one(store, "cq04_coverage", U=unit["718BP02"], S=zone["10906X0039/C2-1"])
    assert abs(millas["outcropAreaM2"] / 1e6 - 27.08) < 0.01, millas    # Codex review of 2026-10-26, §1
    # the facts alone (rule outputs missing): MILLAS's unit has outcrop facts in its zone, so the
    # answer is unknown, never the negative "no mapped outcrop" of the stale pair Codex found
    facts_only = store_of(facts_file)
    st = one(facts_only, "cq04_status", U=unit["718BP02"], S=zone["10906X0039/C2-1"])
    assert st["status"] == "unknown" and "no coverage was derived" in st["reason"], st
    print(f"  12. data: CQ4 {len(want)} (extent, unit) coverages = the GeoPandas oracle (areas, {n_cells} cell "
          f"weights), statuses {statuses}; {none_found} recorded units without outcrop in their well's zone: "
          f"supported, 'no mapped outcrop'; MILLAS C2-1 / 718BP02: {millas['outcropAreaM2'] / 1e6:.2f} km² "
          f"(fraction {millas['coveredFraction']:.3f}); facts without rule outputs: unknown")


def main():
    s, u = fixture_store()
    test_cq1_fixture(s)
    test_cq3_fixture(s, u)
    test_cq11_fixture(s)
    test_cq2_fixture(s)
    test_cq12_fixture(s)
    test_cq7_fixture(s)
    test_cq8_fixture(s)
    test_cq4_fixture(s, u)
    facts, derived = KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"
    if facts.exists() and derived.exists():
        release.check()            # the files must form a validated release (src.kg.release)
        store = store_of(facts, derived)
        test_data(store)
        test_data_forcing(store, facts)
    else:
        print("  9-12. skipped: run src.kg.build_kg and src.kg.apply_rules first")
    print("test_cq: all checks passed")


if __name__ == "__main__":
    main()
