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
   CQ8   W1: pumping paths as in tests/test_kg_rules.py, recharge unknown (its unit U is not in BD
         LISA); W7: two recharge proxies (c1 0.625, c2 0.375 of X's outcrop in its zone), effective
         rainfall for groundwater recharge, non-decreasing, eligible, with the four omitted pathways,
         recharge derived; W8: none in its zone (a completed search: none_found), one unit-wide
         (c2), not selected by confident-only (probable); W2 (no search zone) unknown; the facts
         without the rule outputs: W7 unknown, never "none"; W8 none_found
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
   CQ8   recharge proxies of every well = the cells and weights of cq04_cells for its recorded unit
         in its zone and in the forcing extent; statuses derived / none_found (cq04_status "no mapped
         outcrop") / unknown (a unit outside BD LISA, no unit)
   The data checks run only on a validated release (src.kg.release.check).
"""
import json
from collections import Counter

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
from tests.test_kg_rules import (GEO, KG, L, PROV, RADIUS, SOSA, TIME, build_fixture, d, l93,
                                 oracle_coverage, oracle_mapped_outcrop, oracle_relations, oracle_rivers,
                                 store_of, violations)

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
    # CQ5, CQ6: R2 and R4 have C as a second candidate (possible), which no reach of their zones runs
    # on or over (R4's zone has 50 m of river off the map: an incomplete search); S6 states that C is
    # independent of WC1 in FRDRT1 (R1's zone), where no well monitors C; G1's series has its coverage
    for key in ("R2", "R4"):
        fx.attribution(f"piezometer/{key}", d(f"piezometer/{key}"), L.MonitoringRole, u["C"],
                       conf=L.Possible, rank=2)
    pa, st6 = d("passage/S6"), d("exchange-statement/S6")
    for t in ((pa, RDF.type, L.DocumentPassage), (pa, L.inDocument, d("document/test")),
              (pa, L.pageLabel, Literal("2")), (pa, L.quote, Literal("a verbatim quote of statement S6", lang="fr")),
              (st6, RDF.type, L.ExchangeStatement), (st6, L.statedMechanism, L.RiverExchange),
              (st6, L.aboutSection, d("water-body/FRDRT1")), (st6, L.aboutWatercourse, d("watercourse/WC1")),
              (st6, L.aboutUnit, u["C"]), (st6, L.unitAsNamed, Literal("unit C", lang="fr")),
              (st6, L.unitMapping, L.UnitListedBySource), (st6, L.exchangeDirection, L.NoExchange),
              (st6, L.hedging, L.StatedFinding), (st6, L.stateDescription, Literal("low flow (fixture)", lang="en")),
              (st6, L.evidenceKind, L.ExpertHypothesis), (st6, PROV.wasDerivedFrom, pa),
              (d("series/rivers-test/G1"), L.coverageStart, Literal("2005-01-02", datatype=XSD.date)),
              (d("series/rivers-test/G1"), L.coverageEnd, Literal("2026-10-18", datatype=XSD.date))):
        a(t)
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
    return to_store(g), u, g


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
    assert (st["status"], st["drivers"], st["recharge"]) == ("partial", "PumpingDrawdown", "unknown"), st
    assert "not described by BD LISA" in st["reason"]             # W1's unit U: its outcrop is not known
    assert ask(s, "cq08_influences", W=d("piezometer/W6"), policy=MAIN) == []
    assert one(s, "cq08_status", W=d("piezometer/W6"))["status"] == "unknown"

    # recharge proxies: W7 (unit X at outcrop in its zone, 0.8 inside the cells), W8 (no Y outcrop in
    # its zone: a completed search; only the unit-wide sensitivity connects it), W2 (no search zone)
    w7, w8 = d("piezometer/W7"), d("piezometer/W8")
    r7 = {r["driverCode"]: r for r in ask(s, "cq08_influences", W=w7, policy=CONF_ONLY)}
    assert {k: (r["cellWeight"], local(r["mechanism"]), local(r["responseSign"]), local(r["eligibility"]),
                local(r["driverVariable"]), local(r["proxyFor"]), local(r["driverGroup"]), r["viaCode"],
                local(r["extent"]), r["selected"]) for k, r in r7.items()} == {
        "c1": (0.625, "DiffuseRecharge", "PositiveResponse", "EligibleConstraint", "EffectiveRainfall",
               "GroundwaterRecharge", "RechargeProxies", "X", "W7", True),
        "c2": (0.375, "DiffuseRecharge", "PositiveResponse", "EligibleConstraint", "EffectiveRainfall",
               "GroundwaterRecharge", "RechargeProxies", "X", "W7", True)}, r7
    assert all(set(r["omittedPathways"].split()) == {"LateralInflow", "VerticalLeakage", "RiverExchange",
                                                     "CanalReturnFlow"} for r in r7.values())
    assert all(r["distanceM"] is None and r["driverAttribution"] is None for r in r7.values())
    st = one(s, "cq08_status", W=w7)
    assert (st["status"], st["drivers"], st["recharge"]) == ("partial", "DiffuseRecharge", "derived"), st
    r8 = ask(s, "cq08_influences", W=w8, policy=MAIN)
    assert [(r["driverCode"], r["cellWeight"], local(r["extent"]), r["selected"]) for r in r8] == \
        [("c2", 1.0, "forcing-cells", True)], r8                   # the unit-wide sensitivity only
    assert [r["selected"] for r in ask(s, "cq08_influences", W=w8, policy=CONF_ONLY)] == [False]   # probable
    st = one(s, "cq08_status", W=w8)
    assert st["recharge"] == "none_found" and "completed search" in st["reason"], st
    assert one(s, "cq08_status", W=d("piezometer/W2"))["recharge"] == "unknown"        # no search zone
    # the facts without the rule outputs: W7's unit is at outcrop in its zone, so its recharge is
    # unknown, never "none"; W8's search found no outcrop of its unit, with or without the rules
    facts_only = to_store(cq_fixture()[0].g)
    assert one(facts_only, "cq08_status", W=w7)["recharge"] == "unknown"
    assert one(facts_only, "cq08_status", W=w8)["recharge"] == "none_found"
    print("  7. CQ8 fixtures: a supported pumping path gives a conditional non-increasing sign, a "
          "group-level path no sign; an unaccepted segment blocks the path; recharge proxies: one per cell "
          "over the outcrop of the well's unit, non-decreasing, with the pathways they omit; none for a unit "
          "without outcrop in the zone (a completed search), unknown without a search or a derivation; "
          "partial: lateral inflow and vertical leakage are never derived")


def test_cq4_fixture(s, u):
    zone, forcing, rule = d("outcrop-zone/W1"), d("extent/forcing-cells"), d("rule/outcrop-coverage")
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


RZ = {k: d(f"reach-zone/{k}") for k in ("R1", "R2", "R3", "R4", "R5", "R6")}


def test_cq5_fixture(s, u):
    """The river cases of tests/test_kg_rules.add_rivers, plus C as a second candidate of R2 and R4
    and statement S6 (cq_fixture)."""
    got = {k: [(r["watercourseCode"], r["unitCode"], r["type"], r["lengthOnOutcropM"], r["lengthOverCoverM"],
                r["coverUnits"], r["pieces"], r["statements"]) for r in ask(s, "cq05_associations", S=z)]
           for k, z in RZ.items()}
    assert got == {"R1": [("WC1", "X", "OnOutcrop", 1500.0, None, None, 1, 1)],
                   "R2": [("WC2", "Z", "OverCover", None, 1200.0, "Y", 1, 0)],
                   "R3": [("WC1", "B", "DocumentedLateral", None, None, None, 1, 1)],
                   "R4": [("WC1", "X", "OnOutcrop", 900.0, None, None, 2, 0)],     # 50 m off the map not counted
                   "R5": [("WC1", "X", "OnOutcrop", 600.0, None, None, 1, 2)],
                   "R6": [("WC3", "A", "OnOutcrop", 1000.0, None, None, 1, 0)]}, got
    cases = {"X in R1": (u["X"], RZ["R1"]), "Z in R2": (u["Z"], RZ["R2"]), "C in R2": (u["C"], RZ["R2"]),
             "B in R3": (u["B"], RZ["R3"]), "X in R4": (u["X"], RZ["R4"]), "C in R4": (u["C"], RZ["R4"]),
             "X in R5": (u["X"], RZ["R5"]), "A in R6": (u["A"], RZ["R6"]), "Y in R1": (u["Y"], RZ["R1"]),
             "U in R1": (u["U"], RZ["R1"]), "a well": (d("piezometer/R1"), RZ["R1"]),
             "an outcrop zone": (u["X"], d("outcrop-zone/W1"))}
    st = {k: one(s, "cq05_status", U=uu, S=ss) for k, (uu, ss) in cases.items()}
    assert {k: v["status"] for k, v in st.items()} == {
        "X in R1": "supported", "Z in R2": "partial", "C in R2": "supported", "B in R3": "supported",
        "X in R4": "partial", "C in R4": "partial", "X in R5": "conflicting", "A in R6": "partial",
        "Y in R1": "unknown", "U in R1": "unknown", "a well": "not_applicable",
        "an outcrop zone": "not_applicable"}, {k: (v["status"], v["reason"]) for k, v in st.items()}
    assert (st["X in R1"]["associations"], st["B in R3"]["associations"], st["C in R2"]["associations"]) == \
        ("OnOutcrop", "DocumentedLateral", "")
    assert st["C in R2"]["reason"].startswith("no searched watercourse") and "completed search" in st["C in R2"]["reason"]
    assert "off the geological map" in st["C in R4"]["reason"]
    assert st["X in R4"]["reason"].startswith("associated by geometry only")
    assert st["Y in R1"]["reason"].startswith("not searched") and "not described by BD LISA" in st["U in R1"]["reason"]

    def stm(k, unit):
        return [(local(r["statement"]), r["applies"], r["listedBecause"], r["direction"], r["hedging"])
                for r in ask(s, "cq05_statements", S=RZ[k], U=u[unit])]
    assert stm("R1", "X") == [("S1", True, "applies", "AquiferToSurface", "StatedFinding"),
                              ("S5", False, "stretch not delimited", "SurfaceToAquifer", "StatedFinding")], stm("R1", "X")
    assert stm("R5", "X") == [("S3", True, "applies", "NoExchange", "StatedFinding"),     # kept side by side
                              ("S4", True, "applies", "SurfaceToAquifer", "StatedFinding"),
                              ("S5", False, "stretch not delimited", "SurfaceToAquifer", "StatedFinding")], stm("R5", "X")
    assert stm("R3", "B") == [("S2", True, "applies", "ExchangeEquilibrium", "StatedFinding")]
    assert stm("R4", "X") == [("S5", False, "stretch not delimited", "SurfaceToAquifer", "StatedFinding")]
    assert stm("R1", "C") == [("S6", False, "section in zone", "NoExchange", "StatedFinding")]   # no well monitors C
    r = ask(s, "cq05_statements", S=RZ["R1"], U=u["X"])[0]
    assert (r["section"], r["document"], r["page"], r["quote"], r["unitAsNamed"], local(r["unitMapping"]), r["state"]) == \
        ("section FRDRT1", "test report", "1", "a verbatim quote of statement S1", "unit X", "UnitListedBySource",
         "low flow (fixture)"), r

    gz = [(r["gaugeCode"], r["distanceM"], r["position"], r["alongRiverM"], r["inPool"], r["used"])
          for r in ask(s, "cq05_gauges", S=RZ["R1"])]
    assert gz == [("G3", 500.0, "AlongZoneStretch", 0.0, False, False),     # nearest, but not in the pool
                  ("G1", 1000.0, "UpstreamOfZone", 2000.0, True, True),
                  ("G2", 3000.0, "DownstreamOfZone", 5000.0, True, False)], gz
    g1 = next(r for r in ask(s, "cq05_gauges", S=RZ["R1"]) if r["gaugeCode"] == "G1")
    assert (g1["observedTrainingWeeks"], g1["trainingWeeks"], g1["coverageStart"], g1["coverageEnd"]) == \
        (700, 783, "2005-01-02", "2026-10-18"), g1
    assert [(r["gaugeCode"], r["position"], r["alongRiverM"], r["used"]) for r in ask(s, "cq05_gauges", S=RZ["R3"])] == \
        [("G3", "OffMainStem", None, False), ("G2", "DownstreamOfZone", 3000.0, True), ("G1", "UpstreamOfZone", 6000.0, False)]
    assert [(r["gaugeCode"], r["inPool"], r["used"]) for r in ask(s, "cq05_gauges", S=RZ["R6"])] == [("G5", False, False)]
    # the facts without the rule outputs: pieces on X's outcrop, or a documented exchange of B with a
    # section of the zone, without an association: unknown, never "none found"; C in R2, where no fact
    # leads to an association, is a completed search with or without the rules
    facts_only = to_store(cq_fixture()[0].g)
    for uu, z in ((u["X"], RZ["R1"]), (u["B"], RZ["R3"]), (u["Z"], RZ["R2"])):
        st = one(facts_only, "cq05_status", U=uu, S=z)
        assert st["status"] == "unknown" and "missing or stale" in st["reason"], st
    assert one(facts_only, "cq05_status", U=u["C"], S=RZ["R2"])["status"] == "supported"
    print("  9. CQ5 fixtures: on outcrop, over cover (cover unit named) and documented lateral associations; "
          "an exchange documented (supported), only geometric (partial), independence beside an exchange "
          "(conflicting, both kept); a statement without a delimited stretch listed, never applied; the "
          "nearest pool gauge used, a nearer gauge outside the pool listed; a unit no well of the zone "
          "monitors: not searched; off-map reaches: an incomplete search; facts without rule outputs: unknown")


def test_cq6_fixture(s, u):
    cases = {"X in R1": (u["X"], RZ["R1"]), "A in R6": (u["A"], RZ["R6"]), "Z in R2": (u["Z"], RZ["R2"]),
             "X in R4": (u["X"], RZ["R4"]), "C in R4": (u["C"], RZ["R4"]), "Y in R1": (u["Y"], RZ["R1"]),
             "U in R1": (u["U"], RZ["R1"]), "an outcrop zone": (u["X"], d("outcrop-zone/W1"))}
    st = {k: one(s, "cq06_status", U=uu, S=ss) for k, (uu, ss) in cases.items()}
    assert {k: (v["status"], v["documented"], v["stated"]) for k, v in st.items()} == {
        "X in R1": ("partial", True, True), "A in R6": ("partial", True, False), "Z in R2": ("supported", False, False),
        "X in R4": ("supported", False, False), "C in R4": ("supported", False, False),
        "Y in R1": ("unknown", False, False), "U in R1": ("unknown", False, False),
        "an outcrop zone": ("not_applicable", False, False)}, {k: (v["status"], v["reason"]) for k, v in st.items()}
    assert "states canal return flow" in st["X in R1"]["reason"] and "hedged" in st["A in R6"]["reason"]
    assert st["Z in R2"]["reason"].startswith("no BD TOPO canal reach") and st["Y in R1"]["reason"].startswith("not searched")
    chain = [(r["lengthOnOutcropM"], r["canals"], r["intakes"], r["intakesWithWatercourse"], r["commandArea"],
              local(r["statement"]), r["direction"], r["hedging"], r["document"], r["page"])
             for r in ask(s, "cq06_chain", S=RZ["R1"], U=u["X"])]
    assert chain == [(800.0, "reach k1", 1, 0, "not mapped", "C1", "SurfaceToAquifer", "StatedFinding",
                      "test report", "1")], chain
    assert [(r["lengthOnOutcropM"], local(r["statement"]), r["hedging"]) for r in ask(s, "cq06_chain", S=RZ["R6"], U=u["A"])] == \
        [(400.0, "C2", "HedgedFinding")]
    assert ask(s, "cq06_chain", S=RZ["R2"], U=u["Z"]) == []
    facts_only = to_store(cq_fixture()[0].g)
    st = one(facts_only, "cq06_status", U=u["X"], S=RZ["R1"])
    assert st["status"] == "unknown" and "missing or stale" in st["reason"], st
    assert one(facts_only, "cq06_status", U=u["Z"], S=RZ["R2"])["status"] == "supported"
    print("  10. CQ6 fixtures: a canal on the unit's outcrop with a stated return statement, and one with a hedged "
          "statement: partial chains (no command area, no local return amount); no canal on the outcrop: a "
          "completed search; a unit no well of the zone monitors: not searched; facts without rule outputs: unknown")


def test_cq8_rivers_fixture(s, g):
    """CQ8 for the river and canal fixture (R1-R6), and the statuses on graphs whose rule outputs are
    missing (facts only) or lack the river or the canal influences."""
    def infl(k, policy=MAIN):
        return {local(r["mechanism"]): (r["driverCode"], local(r["responseSign"]), local(r["eligibility"]),
                                        local(r["driverVariable"]), local(r["proxyFor"]), local(r["driverGroup"]),
                                        r["viaCode"], r["associationType"], local(r["extent"]), local(r["confidence"]),
                                        r["selected"])
                for r in ask(s, "cq08_influences", W=d(f"piezometer/{k}"), policy=policy)}
    river = ("RiverDischarge", "RiverStage", "RiverDischargeGroup")
    canal = ("CanalDiversionVolume", None, "SummerDemand")
    want = {"R1": {"RiverExchange": ("G1", "PositiveResponse", "EligibleConstraint", *river, "X", "OnOutcrop", "R1"),
                   "CanalReturnFlow": ("canal-intakes:plain", "PositiveResponse", "EligibleConstraint", *canal, "X", None, "R1")},
            "R2": {"RiverExchange": ("G4", "UnknownResponse", "IneligibleConstraint", *river, "Z", "OverCover", "R2")},
            "R3": {"RiverExchange": ("G2", "PositiveResponse", "EligibleConstraint", *river, "B", "DocumentedLateral", "R3")},
            "R4": {"RiverExchange": ("G1", "PositiveResponse", "IneligibleConstraint", *river, "X", "OnOutcrop", "R4")},
            "R5": {"RiverExchange": ("G1", "PositiveResponse", "IneligibleConstraint", *river, "X", "OnOutcrop", "R5")},
            "R6": {"CanalReturnFlow": ("canal-intakes:plain", "PositiveResponse", "IneligibleConstraint", *canal, "A", None, "R6")}}
    for k, w in want.items():
        got = infl(k)
        assert got == {m: v + ("Confident", True) for m, v in w.items()}, (k, got)
        assert all(v[-1] for v in infl(k, CONF_ONLY).values())            # confident attributions
    reasons = {(k, local(r["mechanism"])): r["eligibilityReason"] for k in want
               for r in ask(s, "cq08_influences", W=d(f"piezometer/{k}"), policy=MAIN)}
    assert "doi:10.3133/tm6A16" in reasons[("R1", "RiverExchange")] and "Gate 3" in reasons[("R1", "RiverExchange")]
    assert "vertical leakage" in reasons[("R2", "RiverExchange")]
    assert "geometric only" in reasons[("R4", "RiverExchange")] and "independent" in reasons[("R5", "RiverExchange")]
    assert "hedged" in reasons[("R6", "CanalReturnFlow")]
    st = {k: one(s, "cq08_status", W=d(f"piezometer/{k}")) for k in ("R1", "R2", "R3", "R4", "R5", "R6", "W7", "W1")}
    assert {k: (v["status"], v["river"], v["canal"]) for k, v in st.items()} == {
        "R1": ("partial", "derived", "derived"), "R2": ("partial", "derived", "none_found"),
        "R3": ("partial", "derived", "none_found"), "R4": ("partial", "derived", "none_found"),
        "R5": ("partial", "derived", "none_found"), "R6": ("partial", "no_pool_gauge", "derived"),
        "W7": ("partial", "unknown", "unknown"), "W1": ("partial", "unknown", "unknown")}, st
    assert set(st["R1"]["drivers"].split()) == {"CanalReturnFlow", "RiverExchange"}
    assert st["W7"]["riverReason"] == "the well has no reach search zone" and "BD LISA" in st["W1"]["riverReason"]
    assert "no pool gauge" in st["R6"]["riverReason"] or "none has a gauge of arm C's pool" in st["R6"]["riverReason"]

    # incomplete rule outputs: never a negative answer
    def without(mech):
        drop = set(g.subjects(L.mechanism, mech))
        g2 = rdflib.Graph()
        for t in g:
            if t[0] not in drop:
                g2.add(t)
        return to_store(g2)
    st = one(without(L.RiverExchange), "cq08_status", W=d("piezometer/R1"))
    assert (st["river"], st["canal"]) == ("unknown", "derived") and "missing or stale" in st["riverReason"], st
    st = one(without(L.CanalReturnFlow), "cq08_status", W=d("piezometer/R1"))
    assert (st["river"], st["canal"]) == ("derived", "unknown") and "missing or stale" in st["canalReason"], st
    facts_only = to_store(cq_fixture()[0].g)
    st = {k: one(facts_only, "cq08_status", W=d(f"piezometer/{k}")) for k in ("R1", "R3", "R6")}
    assert {k: (v["river"], v["canal"]) for k, v in st.items()} == {
        "R1": ("unknown", "unknown"), "R3": ("unknown", "none_found"), "R6": ("unknown", "unknown")}, st
    print("  11. CQ8 river and canal fixtures: the nearest pool gauge drives a river influence, non-decreasing "
          "and eligible on outcrop or documented lateral with a documented exchange, conditional over cover, "
          "ineligible when only geometric or contradicted; canal influences only where a return is documented, "
          "eligible only when stated; a river without a pool gauge: no influence, a reported gap; missing "
          "rule outputs: unknown, never none_found")


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
    print(f"  12. data: CQ1 anchors hold; {len(pz)} wells (statuses {n}) = the dataset, the BD LISA "
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
        inf = {(r["driverCode"], local(r["resolution"])): r for r in ask(store, "cq08_influences", W=iri, policy=MAIN)
               if local(r["mechanism"]) == "PumpingDrawdown"}
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
    print(f"  13. data: CQ2 {n_exact} exact and {n_group} group-level candidate rows within 5 km of the wells "
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
    print(f"  14. data: CQ7 {len(pz)} wells x {len(years)} RPG editions: {n_rows} code rows, class areas and "
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
    print(f"  15. data: CQ4 {len(want)} (extent, unit) coverages = the GeoPandas oracle (areas, {n_cells} cell "
          f"weights), statuses {statuses}; {none_found} recorded units without outcrop in their well's zone: "
          f"supported, 'no mapped outcrop'; MILLAS C2-1 / 718BP02: {millas['outcropAreaM2'] / 1e6:.2f} km² "
          f"(fraction {millas['coveredFraction']:.3f}); facts without rule outputs: unknown")


def test_data_recharge(store):
    """CQ8 recharge proxies for every well, against CQ4's own answers on the same graph: in the
    well's search zone, the influences are the cells of cq04_cells for its recorded unit, with the
    same weights; unit-wide, those of the forcing extent. Status: derived where the unit has outcrop
    in the zone, none_found for a unit described by BD LISA without outcrop there (cq04_status: "no
    mapped outcrop"), unknown for a unit outside BD LISA and for the wells without a unit."""
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    pz = iris(store, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    unit = iris(store, "SELECT ?c ?u WHERE { ?u lulcw:bdlisaCode ?c }")
    zone = iris(store, "SELECT ?c ?z WHERE { ?z a lulcw:OutcropSearchZone ; lulcw:zoneOf/lulcw:bssCode ?c }")
    described = {r[0].value for r in store.query(
        "PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#> "
        "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }")}
    forcing = ox.NamedNode(str(d("extent/forcing-cells")))
    status, n_local, n_wide, none_found = {}, 0, 0, []
    for b, code in zip(wells["code_bss"], wells["code_bdlisa"]):
        st = one(store, "cq08_status", W=pz[b])
        rech = [r for r in ask(store, "cq08_influences", W=pz[b], policy=MAIN)
                if local(r["mechanism"]) == "DiffuseRecharge"]
        if not isinstance(code, str):
            assert (st["status"], st["recharge"], rech) == ("unknown", "unknown", []), (b, st)
            status["no unit"] = status.get("no unit", 0) + 1
            continue
        for S, kind in ((zone[b], "local"), (forcing, "unit-wide")):
            want = {f"{x['gridXHm']}_{x['gridYHm']}": x["weight"] for x in ask(store, "cq04_cells", U=unit[code], S=S)}
            got = {r["driverCode"]: r["cellWeight"] for r in rech if r["extent"] == S.value}
            assert got == want, (b, kind, got, want)
            assert all(r["selected"] for r in rech), b          # the 60 recorded units: confident or probable
            n_local += len(got) if kind == "local" else 0
            n_wide += len(got) if kind == "unit-wide" else 0
        c4 = one(store, "cq04_status", U=unit[code], S=zone[b])
        has_local = any(r["extent"] == zone[b].value for r in rech)
        expect = "derived" if has_local else ("none_found" if code in described else "unknown")
        assert st["recharge"] == expect and st["status"] == "partial", (b, code, st, expect)
        if expect == "none_found":
            assert c4["reason"].startswith("no mapped outcrop"), (b, c4)
            none_found.append(b)
        status[expect] = status.get(expect, 0) + 1
    print(f"  16. data: CQ8 recharge proxies of every well = CQ4's cells and weights for its recorded unit "
          f"({n_local} in the 5 km zones, {n_wide} unit-wide); statuses {status}; no outcrop of the unit "
          f"within 5 km (a completed search): {', '.join(none_found)}")


EXCHANGE = {"AquiferToSurface", "SurfaceToAquifer", "ExchangeEquilibrium"}


def _river_rows(rinf):
    return [(r["driverCode"], local(r["responseSign"]), local(r["eligibility"]), r["associationType"], r["viaCode"])
            for r in rinf]


def _anchor_c2_1(assoc, rinf, cinf, st5, st6, st8):
    """MILLAS C2-1 (718BP02): 12.0 km of the Têt on its unit's outcrop (step note, 2026-11-06); the
    sources disagree on that stretch (FRDG351: losing from Vinça to the Comelade; BRGM, September 2017:
    gaining from Rodès to T6), so conflicting, while the sign stays eligible (the flux grows with the
    stage whatever its direction); the river edge comes from Rodès, the nearest pool gauge; stated
    canal returns into the recent alluvium make the canal edge eligible."""
    tet = {r["type"]: r for r in assoc if r["watercourseCode"] == "Y04-0400" and r["unitCode"] == "718BP02"}
    assert round(tet["OnOutcrop"]["lengthOnOutcropM"] / 1000, 1) == 12.0, tet
    assert st5["status"] == "conflicting", st5
    assert _river_rows(rinf) == [("Y046403001", "PositiveResponse", "EligibleConstraint", "OnOutcrop", "718BP02")], rinf
    assert [local(r["eligibility"]) for r in cinf] == ["EligibleConstraint"] and st6["stated"], (cinf, st6)


def _anchor_c2_2(assoc, rinf, cinf, st5, st6, st8):
    """MILLAS C2-2 (671AA00, beside C2-1): the same 12.0 km of the Têt, over the recent alluvium that
    covers the Pliocene: a river edge via the overlying unit, its sign unknown and never eligible; no
    canal return is documented into the Pliocene."""
    tet = {r["type"]: r for r in assoc if r["watercourseCode"] == "Y04-0400" and r["unitCode"] == "671AA00"}
    assert round(tet["OverCover"]["lengthOverCoverM"] / 1000, 1) == 12.0 and tet["OverCover"]["coverUnits"] == "718BP02", tet
    assert st5["status"] == "partial", st5
    assert _river_rows(rinf) == [("Y046403001", "UnknownResponse", "IneligibleConstraint", "OverCover", "671AA00")], rinf
    assert cinf == [] and st8["canal"] == "not_documented", st8


def _anchor_medalu(assoc, rinf, cinf, st5, st6, st8):
    """MEDALU at Terrats (671AA00): 7.5 km of the Réart on Pliocene outcrop; FRDG243 states that the
    Canterrane and the upper Réart are independent of the aquifer (supported); neither river has a pool
    gauge, so D gives it no river edge (a reported gap)."""
    reart = {r["type"]: r for r in assoc if r["watercourseCode"] == "Y03-0400" and r["unitCode"] == "671AA00"}
    assert round(reart["OnOutcrop"]["lengthOnOutcropM"] / 1000, 1) == 7.5, reart
    assert st5["status"] == "supported" and "independent" in st5["reason"], st5
    assert rinf == [] and st8["river"] == "no_pool_gauge", st8


RIVER_ANCHORS = {"10906X0039/C2-1": _anchor_c2_1, "10906X0038/C2-2": _anchor_c2_2,
                 "10963X0059/MEDALU": _anchor_medalu}


def test_data_rivers(store):
    """CQ5, CQ6 and CQ8 (rivers, canals) for every well, on the released graph. Against the GeoPandas
    oracle of tests.test_kg_rules (BD TOPO reaches x 5 km discs x BD LISA polygons, independent of
    src/kg/rivers.py): the on-outcrop and over-cover rows of cq05_associations for the well's recorded
    unit and their lengths, and the canal length on its outcrop in cq06_chain (pieces under 5 m
    tolerated, as in tests/test_kg_rules). Between the queries: cq05_status follows the statements
    that cq05_statements lists as applying (conflicting, supported, partial), cq06_status the canal
    rows, cq08_status the influences (derived, no_pool_gauge, not_documented, none_found), and
    cq05_gauges marks as used exactly the gauges of the well's river influences, all in arm C's pool.
    On a validated release no answer is "missing or stale". Anchors: RIVER_ANCHORS."""
    river, canal, _, pool = oracle_rivers(store)
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    pz = iris(store, "SELECT ?c ?w WHERE { ?w a lulcw:Piezometer ; lulcw:bssCode ?c }")
    unit = iris(store, "SELECT ?c ?u WHERE { ?u lulcw:bdlisaCode ?c }")
    rz = iris(store, "SELECT ?c ?z WHERE { ?z a lulcw:ReachSearchZone ; lulcw:zoneOf/lulcw:bssCode ?c }")
    described = {r[0].value for r in store.query(
        "PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#> "
        "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }")}
    assert set(rz) == set(wells["code_bss"]), "every well has its reach search zone"
    tally = {k: Counter() for k in ("cq05", "cq06", "river", "canal")}
    gaps, answers = [], {}
    for b, code in zip(wells["code_bss"], wells["code_bdlisa"]):
        st8 = one(store, "cq08_status", W=pz[b])
        assert "stale" not in st8["riverReason"] + st8["canalReason"], (b, st8)
        inf = ask(store, "cq08_influences", W=pz[b], policy=MAIN)
        rinf = [r for r in inf if local(r["mechanism"]) == "RiverExchange"]
        cinf = [r for r in inf if local(r["mechanism"]) == "CanalReturnFlow"]
        assoc = ask(store, "cq05_associations", S=rz[b])
        tally["river"][st8["river"]] += 1
        tally["canal"][st8["canal"]] += 1
        if not isinstance(code, str) or code not in described:
            assert (st8["river"], st8["canal"], rinf, cinf, assoc) == ("unknown", "unknown", [], [], []), (b, st8)
            if isinstance(code, str):
                for q in ("cq05_status", "cq06_status"):
                    st = one(store, q, U=unit[code], S=rz[b])
                    assert st["status"] == "unknown" and "BD LISA" in st["reason"], (b, q, st)
                    tally[q[:4]]["unknown"] += 1
            continue
        # CQ8: river and canal statuses from the influences and the associations
        canal_rows = [r for r in ask(store, "cq06_chain", S=rz[b], U=unit[code])]
        want_r = "derived" if rinf else ("no_pool_gauge" if assoc else "none_found")
        assert st8["river"] == want_r and all(r["driverCode"] in pool for r in rinf), (b, st8["river"], want_r)
        if want_r == "no_pool_gauge":
            gaps.append(b)
        used = {r["gaugeCode"] for r in ask(store, "cq05_gauges", S=rz[b]) if r["used"]}
        assert used == {r["driverCode"] for r in rinf}, (b, used)
        # CQ5: the associations of the recorded unit = the oracle
        mine = {(r["watercourseCode"], r["type"]): r["lengthOnOutcropM"] if r["type"] == "OnOutcrop" else r["lengthOverCoverM"]
                for r in assoc if r["unitCode"] == code and r["type"] != "DocumentedLateral"}
        want = {(wc, t): v for (bb, wc, uu, t), v in river.items() if bb == b and uu == code}
        assert {k for k, v in want.items() if v >= 5.0} <= set(mine) <= set(want), (b, sorted(set(mine) ^ set(want)))
        for k, v in mine.items():
            assert abs(v - want[k]) <= max(5.0, 0.002 * want[k]), (b, k, v, want[k])
        st5 = one(store, "cq05_status", U=unit[code], S=rz[b])
        app = {r["direction"] for r in ask(store, "cq05_statements", S=rz[b], U=unit[code]) if r["applies"]}
        found = any(r["unitCode"] == code for r in assoc)
        conflict = bool(app & EXCHANGE) and ("NoExchange" in app or {"AquiferToSurface", "SurfaceToAquifer"} <= app)
        if found:
            want5 = "conflicting" if conflict else ("supported" if app & (EXCHANGE | {"NoExchange"}) else "partial")
            assert st5["status"] == want5, (b, st5, app)
        else:
            assert st5["status"] == "supported" or (st5["status"] == "partial" and "off the geological map" in st5["reason"]), (b, st5)
        tally["cq05"][st5["status"]] += 1
        # CQ6: the canal rows of the recorded unit = the oracle; statuses and flags from the statements
        st6 = one(store, "cq06_status", U=unit[code], S=rz[b])
        ln = {r["lengthOnOutcropM"] for r in canal_rows}
        assert len(ln) <= 1, (b, ln)
        if (b, code) in canal and canal[(b, code)] >= 5.0:
            assert ln, (b, "canal on the outcrop without an association")
        if ln:
            assert (b, code) in canal and abs(ln.pop() - canal[(b, code)]) <= max(5.0, 0.002 * canal[(b, code)]), b
            assert st6["status"] == "partial", (b, st6)
        else:
            assert st6["status"] == "supported" or (st6["status"] == "partial" and "off the geological map" in st6["reason"]), (b, st6)
        ret = [r for r in canal_rows if r["direction"] == "SurfaceToAquifer"]
        assert st6["documented"] == bool(ret) and st6["stated"] == any(r["hedging"] == "StatedFinding" for r in ret), (b, st6)
        mine_c = [r for r in cinf if r["viaCode"] == code]
        assert bool(mine_c) == bool(ret), (b, "a canal influence exactly where a return is documented")
        assert all((local(r["eligibility"]) == "EligibleConstraint") ==
                   (st6["stated"] and not any(x["direction"] == "NoExchange" for x in canal_rows)) for r in mine_c), b
        tally["cq06"][st6["status"]] += 1
        answers[b] = (assoc, rinf, cinf, st5, st6, st8)
    for b, check in RIVER_ANCHORS.items():
        check(*answers[b])
    print(f"  17. data: CQ5/CQ6/CQ8 rivers and canals for {len(wells)} wells: river associations and canal "
          f"lengths of the recorded units = the GeoPandas oracle; cq05_status {dict(tally['cq05'])}, cq06_status "
          f"{dict(tally['cq06'])}; cq08 river {dict(tally['river'])}, canal {dict(tally['canal'])}; associated "
          f"rivers without a pool gauge (no river edge in D): {', '.join(gaps) or 'none'}; anchors: "
          f"{', '.join(RIVER_ANCHORS)}; no stale answer")


def main():
    s, u, g = fixture_store()
    test_cq1_fixture(s)
    test_cq3_fixture(s, u)
    test_cq11_fixture(s)
    test_cq2_fixture(s)
    test_cq12_fixture(s)
    test_cq7_fixture(s)
    test_cq8_fixture(s)
    test_cq4_fixture(s, u)
    test_cq5_fixture(s, u)
    test_cq6_fixture(s, u)
    test_cq8_rivers_fixture(s, g)
    facts, derived = KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"
    if facts.exists() and derived.exists():
        release.check()            # the files must form a validated release (src.kg.release)
        store = store_of(facts, derived)
        test_data(store)
        test_data_forcing(store, facts)
        test_data_recharge(store)
        test_data_rivers(store)
    else:
        print("  12-17. skipped: run src.kg.build_kg and src.kg.apply_rules first")
    print("test_cq: all checks passed")


if __name__ == "__main__":
    main()
