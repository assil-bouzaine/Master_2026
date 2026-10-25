"""Checks of the SHACL-AF rules and the SHACL shapes of the knowledge graph (task 12.6).

    PFE_DATASET=v4 python -m src.kg.build_kg && PFE_DATASET=v4 python -m src.kg.apply_rules
    PFE_DATASET=v4 python -m tests.test_kg_rules

1. Vocabulary: every lulcw:, prov: and geo: term that the rules and shapes use, in their RDF and
   inside their SPARQL text, is declared in the ontology network (catches typos).
2. Synthetic fixtures (the acceptance cases of docs/competency_questions.md), run through the
   same rules (src.kg.apply_rules.run_rules) and shapes:
   CQ3  a stack A > B > C gives direct A-B and B-C and indirect A-C via B; X > Y in one polygon
        and Y > Z in another give no X-Z relation and no "X overlies Z"
   CQ11 wells 4,999 m apart are linked, 5,001 m apart are not; no self-pair, one link per pair;
        a missing depth leaves the depth difference missing; other units are never linked
   CQ8  an exact-unit path gives a non-increasing, eligible influence; a group-level path an
        unknown sign, not eligible; an explicit unknown gives no influence; nor does a facility
        beyond the radius
   CQ2  each policy selects only the confidence levels it admits; group-level evidence never
        becomes lulcw:pumpsFrom; a path is selected only when every segment is; changing the
        policy changes the selection, never the evidence
   CQ7  a code override beats the crop group (AGR is citrus, not orchard); a code of no class
        stays in the totals as unmapped; class areas are the sums of their codes' clipped areas;
        the high-demand threshold is the upper tercile of the training years' estimates (800 m³
        here) and every zone-year gets a dated category
   The fixture graph, with the rule outputs, has no violation.
3. Negative controls, each inserted on purpose and reported as a violation: an ordering chained
   across two polygons, a self-paired well link, an eligible influence with an unknown sign,
   an influence resting on an explicit unknown, an attribution with both a target and a reason
   for unknown, `overlies` without a witness, a piezometer without an attribution, a selection
   of a confidence level the policy does not admit, a path selected without its segments, a
   class area that is not the sum of its codes, a category that disagrees with the threshold,
   an RPG edition used for another year, a crop code with two classes.
4. Data-backed regression (when the graph and the rule outputs exist), against pandas on the
   source tables: the stratigraphic relations equal the pairs of the BD LISA stack table for
   the graph's polygons, and the direct contacts of the plain's polygons equal the overlies
   edges of Step 6b (bdlisa_overlies_plain.csv, polygon counts included); the well links equal
   the same-unit pairs within 5 km of wells.parquet (distances, depth differences); the
   exact-unit influences equal the facility-well pairs of the attribution table of task 12.3
   and the BNPE coordinates; the policy selections equal the attribution counts; the crop class
   of every code equals src.dataset.crop_demand.code_to_class, the class areas equal the clipped
   areas summed with pandas, the demand estimates equal the weekly index spread over its days and
   summed by calendar year, and the threshold and categories follow; the validation report of
   src.kg.apply_rules is the one of the current files and has no violation.
"""
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pyoxigraph as ox
import rdflib
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD

from src.analysis.bdlisa_profile import GPKG
from src.analysis.bnpe_profile import load as load_bnpe
from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, PROCESSED
from src.dataset.crop_demand import AREA_OUT, code_to_class, load_classes
from src.kg.apply_rules import (RULES, SHAPES, check, ontology_network, rule_records,
                                run_rules)
from src.kg.build_kg import BNPE_SNAPSHOT

KG = PROCESSED / "kg"
L = rdflib.Namespace("https://w3id.org/lulcw#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
GEO = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
SOSA = rdflib.Namespace("http://www.w3.org/ns/sosa/")
TIME = rdflib.Namespace("http://www.w3.org/2006/time#")
D = "https://w3id.org/lulcw/data/"
PRE = """PREFIX lulcw: <https://w3id.org/lulcw#> PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/> PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
BASE <https://w3id.org/lulcw/data/>
"""
RADIUS = 5000.0
NS = {"lulcw": str(L), "prov": str(PROV), "geo": str(GEO)}


def d(path):
    return URIRef(D + path)


def violations(results, shape=None, text=None):
    return sum(n for k, n in results.items() if k.startswith("Violation")
               and (shape is None or f"| {shape}" in k) and (text is None or text in k))


# ------------------------------------------------------------------------------- 1. vocabulary
def test_vocabulary(net):
    declared = {str(s) for s in net.subjects(RDF.type, None)}
    used = set()
    for f in (RULES, SHAPES):
        g = rdflib.Graph().parse(f)
        used |= {str(x) for t in g for x in t if isinstance(x, URIRef)
                 and str(x).startswith(tuple(NS.values()))}
        for lit in (o for o in g.objects() if isinstance(o, Literal)):
            for p, local in re.findall(r"\b(lulcw|prov|geo):([A-Za-z][A-Za-z0-9]*)", str(lit)):
                used.add(NS[p] + local)
    missing = sorted(u for u in used if u not in declared)
    assert not missing, f"terms used by the rules or shapes but not declared: {missing}"
    print(f"  1. {len(used)} lulcw/prov/geo terms of the rules and shapes, all declared")


# ---------------------------------------------------------------------------- 2. the fixtures
class Fixture:
    """A small graph with every field the shapes require, built from the acceptance cases."""

    def __init__(self):
        self.g = rdflib.Graph()
        self.n = 0
        a = self.g.add
        rel = d("release/test")
        a((rel, RDF.type, L.DataRelease))
        self.rule = d("rule/test-record")
        a((self.rule, RDF.type, L.DerivationRule))
        a((self.rule, RDFS.comment, Literal("fixture rule", lang="en")))
        a((self.rule, L.ruleVersion, Literal("test")))
        self.ex = d("execution/test")
        a((self.ex, RDF.type, L.RuleExecution))
        self.rel = rel
        for key, levels in (("main", (L.Confident, L.Probable)), ("confident-only", (L.Confident,)),
                            ("all-links", (L.Confident, L.Probable, L.Possible))):
            p = d(f"policy/{key}")
            a((p, RDF.type, L.ExportPolicy))
            a((p, RDFS.comment, Literal(key, lang="en")))
            a((p, L.ruleVersion, Literal("test")))
            for c in levels:
                a((p, L.admitsConfidence, c))

    def unit(self, code):
        u = d(f"unit/{code}")
        self.g.add((u, RDF.type, L.HydrogeologicalUnit))
        self.g.add((u, L.bdlisaCode, Literal(code)))
        return u

    def geometry(self, owner, kind, key, wkt):
        geom = d(f"geometry/{kind}/{key}")
        self.g.add((geom, RDF.type, GEO.Geometry))
        self.g.add((geom, GEO.asWKT, Literal("<http://www.opengis.net/def/crs/EPSG/0/2154> " + wkt,
                                             datatype=GEO.wktLiteral)))
        self.g.add((owner, GEO.hasGeometry, geom))

    def polygon(self, code, stack):
        p = d(f"polygon/{code}")
        a = self.g.add
        a((p, RDF.type, L.ElementaryPolygon))
        a((p, L.polygonCode, Literal(code, datatype=XSD.integer)))
        a((p, GEO.hasMetricArea, Literal(1.0e6, datatype=XSD.double)))
        a((p, L.inRelease, self.rel))
        self.geometry(p, "polygon", code, "POLYGON((0 0, 1000 0, 1000 1000, 0 0))")
        for order, unit in enumerate(stack, start=1):
            layer = d(f"polygon/{code}/layer/{order}")
            a((layer, RDF.type, L.StackLayer))
            a((p, L.hasStackLayer, layer))
            a((layer, L.layerUnit, unit))
            a((layer, L.layerOrder, Literal(order, datatype=XSD.integer)))
        return p

    def attribution(self, key, entity, role, target=None, group=False, conf=None, rank=1):
        x = d(f"attribution/{key}/{rank}" + ("/group" if group else ""))
        a = self.g.add
        a((x, RDF.type, L.UnitAttribution))
        a((x, L.attributedEntity, entity))
        a((x, L.role, role))
        a((x, L.assessmentStatus, L.CandidateStatus))
        a((x, L.evidenceKind, L.DerivedAssertion))
        a((x, L.derivationRule, self.rule))
        a((x, PROV.wasDerivedFrom, self.rel))
        a((x, PROV.wasGeneratedBy, self.ex))
        a((x, L.rank, Literal(rank, datatype=XSD.integer)))
        if target is None:
            a((x, L.unknownReason, Literal("no evidence (fixture)")))
        else:
            a((x, L.candidateGroup if group else L.candidateUnit, target))
            a((x, L.resolution, L.UnitGroupResolution if group else L.ExactUnitResolution))
            a((x, L.confidence, conf))
        return x

    def well(self, key, x, y, unit, conf, depth=None):
        w = d(f"piezometer/{key}")
        a = self.g.add
        a((w, RDF.type, L.Piezometer))
        a((w, L.bssCode, Literal(key)))
        a((w, PROV.wasDerivedFrom, self.rel))
        st = d(f"station/{key}")
        a((st, RDF.type, L.MonitoringStation))
        a((st, L.hostedBy, w))
        if depth is not None:
            a((w, L.investigationDepthM, Literal(float(depth), datatype=XSD.double)))
        self.geometry(w, "piezometer", key, f"POINT({x:.1f} {y:.1f})")
        self.attribution(f"piezometer/{key}", w, L.MonitoringRole, unit, conf=conf)
        return w

    def facility(self, code, x, y, target, conf, group=False):
        f = d(f"facility/{code}")
        a = self.g.add
        a((f, RDF.type, L.AbstractionFacility))
        a((f, L.bnpeCode, Literal(code)))
        a((f, L.waterSource, L.GroundwaterSource))
        a((f, PROV.wasDerivedFrom, self.rel))
        it = d(f"intake/{code}")
        a((it, RDF.type, L.Intake))
        a((f, L.hasIntake, it))
        self.geometry(f, "facility", code, f"POINT({x:.1f} {y:.1f})")
        self.attribution(f"facility/{code}", f, L.AbstractionRole, target, group=group, conf=conf)
        return f


def build_fixture():
    fx = Fixture()
    A, B, C, X, Y, Z, U, V = (fx.unit(c) for c in "ABCXYZUV")
    fx.polygon(1, [A, B, C])
    fx.polygon(2, [X, Y])
    fx.polygon(3, [Y, Z])
    G = d("unit-group/g")
    fx.g.add((G, RDF.type, L.HydrogeologicalUnitGroup))
    fx.g.add((G, RDFS.label, Literal("group g", lang="en")))
    fx.g.add((G, L.hasMemberUnit, U))
    fx.well("W1", 0, 0, U, L.Confident, depth=50)
    fx.well("W2", 4999, 0, U, L.Probable)                # no depth
    fx.well("W3", 5001, 0, U, L.Confident, depth=80)     # 5,001 m from W1, 2 m from W2
    fx.well("W4", 0, 100, V, L.Confident, depth=40)      # another unit
    fx.facility("F1", 100, 0, U, L.Probable)             # exact unit
    fx.facility("F2", 200, 0, G, L.Probable, group=True)  # group containing U
    fx.facility("F3", 300, 0, None, None)                # explicit unknown
    fx.facility("F4", 400, 0, U, L.Possible)             # exact, possible
    fx.facility("F5", 0, 20000, U, L.Confident)          # beyond the radius of every well
    add_landuse(fx)
    return fx, {"A": A, "B": B, "C": C, "X": X, "Y": Y, "Z": Z, "U": U, "V": V, "G": G}


def add_landuse(fx):
    """CQ7 fixture: zone W1 in 2023 has 4 ha of PEC (group 20: orchard), 2 ha of AGR (group 20 but
    an override of citrus) and 1 ha of ZZZ (no class); main demand 1000 m³ in 2016, 400 m³ in 2017
    (the training years: upper tercile 800 m³) and 2000 m³ in 2023."""
    a = fx.g.add
    scheme, cscheme = d("crop-code-scheme/rpg"), d("crop-class-scheme/lulcw")
    a((scheme, RDF.type, SKOS.ConceptScheme))
    a((cscheme, RDF.type, SKOS.ConceptScheme))

    def cls(name, groups=(), overrides=(), assumption=None):
        c = d(f"crop-class/{name}")
        a((c, RDF.type, L.CropClass))
        a((c, SKOS.inScheme, cscheme))
        a((c, SKOS.notation, Literal(name)))
        for gnum in groups:
            a((c, L.rpgGroupCode, Literal(gnum, datatype=XSD.integer)))
        for o in overrides:
            a((c, L.overrideCode, Literal(o)))
        if assumption is not None:
            a((c, L.irrigationAssumption, assumption))
            for prop, v in ((L.kcInitial, 0.5), (L.kcMid, 0.9), (L.kcEnd, 0.6)):
                a((c, prop, Literal(v, datatype=XSD.double)))
            for prop, v in ((L.initialStageDays, 30), (L.developmentStageDays, 50),
                            (L.midSeasonStageDays, 130), (L.lateSeasonStageDays, 30), (L.plantingMonth, 3)):
                a((c, prop, Literal(v, datatype=XSD.integer)))

    cls("orchard", groups=(20,), assumption=L.UsuallyIrrigated)
    cls("citrus", overrides=("AGR",), assumption=L.UsuallyIrrigated)
    cls("unmapped")
    codes = {}
    for n, group in (("PEC", 20), ("AGR", 20), ("ZZZ", 99)):
        c = codes[n] = d(f"crop-code/{n}")
        for prop, v in ((RDF.type, L.CropCode), (SKOS.inScheme, scheme), (SKOS.notation, Literal(n)),
                        (SKOS.prefLabel, Literal(n, lang="fr")),
                        (L.rpgGroupCode, Literal(group, datatype=XSD.integer))):
            a((c, prop, v))
    zone, proc = d("zone/W1"), d("procedure/test")
    a((zone, RDF.type, L.CropDemandZone))
    a((zone, L.zoneOf, d("piezometer/W1")))
    a((zone, L.zoneRadiusM, Literal(3000.0, datatype=XSD.double)))
    a((proc, RDF.type, SOSA.Procedure))

    def year(y):
        iv, b = d(f"interval/year/{y}"), d(f"instant/{y}-01-01")
        a((iv, RDF.type, TIME.ProperInterval))
        a((iv, TIME.hasBeginning, b))
        a((b, TIME.inXSDDate, Literal(f"{y}-01-01", datatype=XSD.date)))
        return iv

    for n, ha in (("PEC", 4.0), ("AGR", 2.0), ("ZZZ", 1.0)):
        o = d(f"crop-area/W1/2023/{n}")
        for prop, v in ((RDF.type, L.CropAreaObservation), (SOSA.hasFeatureOfInterest, zone),
                        (SOSA.observedProperty, L.ClippedCropArea),
                        (SOSA.hasSimpleResult, Literal(ha, datatype=XSD.double)),
                        (SOSA.phenomenonTime, year(2023)), (SOSA.usedProcedure, proc),
                        (L.cropCode, codes[n]), (L.rpgEdition, Literal(2023, datatype=XSD.integer))):
            a((o, prop, v))
    year(2016)
    for y, main, wide in ((2016, 1000.0, 1500.0), (2017, 400.0, 900.0), (2023, 2000.0, 2500.0)):
        for name, prop_v, v in (("main", L.PotentialIrrigationDemandMain, main),
                                ("wide", L.PotentialIrrigationDemandWide, wide)):
            o = d(f"crop-demand/W1/{y}/{name}")
            for prop, val in ((RDF.type, L.CropDemandEstimate), (SOSA.hasFeatureOfInterest, zone),
                              (SOSA.observedProperty, prop_v),
                              (SOSA.hasSimpleResult, Literal(v, datatype=XSD.double)),
                              (SOSA.phenomenonTime, year(y)), (SOSA.usedProcedure, proc),
                              (L.rpgEdition, Literal(y, datatype=XSD.integer))):
                a((o, prop, val))


def select(g, q):
    return [tuple(None if v is None else (v.toPython() if isinstance(v, Literal) else str(v))
                  for v in r) for r in g.query(PRE + q)]


def test_fixtures(rules, shapes, net):
    fx, u = build_fixture()
    facts = fx.g
    records = rule_records(rules, "test", facts)
    added = run_rules(facts, rules, records)
    g = facts + records + added

    # CQ3
    rel = {(a.rsplit("/", 1)[-1], b.rsplit("/", 1)[-1], k.split("#")[-1]): m
           for a, b, k, m in select(g, """SELECT ?a ?b ?k (GROUP_CONCAT(STR(?m)) AS ?mid) WHERE {
               ?r a lulcw:StratigraphicRelation ; lulcw:upperUnit ?a ; lulcw:lowerUnit ?b ; lulcw:relationKind ?k .
               OPTIONAL { ?r lulcw:interveningUnit ?m } } GROUP BY ?a ?b ?k""")}
    assert set(rel) == {("A", "B", "DirectContact"), ("B", "C", "DirectContact"),
                        ("A", "C", "IndirectOrdering"), ("X", "Y", "DirectContact"),
                        ("Y", "Z", "DirectContact")}, rel
    assert rel[("A", "C", "IndirectOrdering")].endswith("unit/B")
    over = {(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1]) for s, o in g.subject_objects(L.overlies)}
    assert over == {("A", "B"), ("B", "C"), ("X", "Y"), ("Y", "Z")}, over

    # CQ11
    links = select(g, """SELECT ?a ?b ?d ?dz ?c WHERE { ?l a lulcw:WellLink ; lulcw:wellA/lulcw:bssCode ?a ;
        lulcw:wellB/lulcw:bssCode ?b ; lulcw:horizontalDistanceM ?d ; lulcw:confidence ?c .
        OPTIONAL { ?l lulcw:investigationDepthDifferenceM ?dz } }""")
    got = {(a, b): (dist, dz, c.split("#")[-1]) for a, b, dist, dz, c in links}
    assert set(got) == {("W1", "W2"), ("W2", "W3")}, got        # W1-W3 is 5,001 m; W4 is unit V
    assert abs(got[("W1", "W2")][0] - 4999.0) < 1e-6 and got[("W1", "W2")][1] is None
    assert got[("W1", "W2")][2] == "Probable" and abs(got[("W2", "W3")][0] - 2.0) < 1e-6

    # CQ8
    infl = {(f.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1]): (s.split("#")[-1], e.split("#")[-1], r.split("#")[-1])
            for f, w, s, e, r in select(g, """SELECT ?f ?w ?s ?e ?r WHERE { ?i a lulcw:Influence ;
                lulcw:driverEntity ?f ; lulcw:targetEntity ?w ; lulcw:responseSign ?s ;
                lulcw:constraintEligibility ?e ; lulcw:resolution ?r }""")}
    for w in ("W1", "W2", "W3"):
        assert infl[("F1", w)] == ("NegativeResponse", "EligibleConstraint", "ExactUnitResolution")
        assert infl[("F4", w)] == ("NegativeResponse", "EligibleConstraint", "ExactUnitResolution")
        assert infl[("F2", w)] == ("UnknownResponse", "IneligibleConstraint", "UnitGroupResolution")
    assert len(infl) == 9 and not any(f in ("F3", "F5") or w == "W4" for f, w in infl), infl

    # CQ2 and path selection
    sel = {(x.split("/attribution/")[-1], p.rsplit("/", 1)[-1]) for x, p in select(
        g, "SELECT ?x ?p WHERE { ?x a lulcw:UnitAttribution ; lulcw:selectedUnder ?p }")}
    assert ("facility/F4/1", "main") not in sel and ("facility/F4/1", "all-links") in sel
    assert ("piezometer/W2/1", "confident-only") not in sel and ("piezometer/W1/1", "confident-only") in sel
    assert not any(x.startswith("facility/F3") for x, _ in sel)
    pumps = {(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1]) for s, o in g.subject_objects(L.pumpsFrom)}
    assert pumps == {("F1", "U"), ("F5", "U")}, pumps            # F2 is group-level, F4 possible
    paths = {(f.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1], p.rsplit("/", 1)[-1]) for f, w, p in select(
        g, "SELECT ?f ?w ?p WHERE { ?i lulcw:driverEntity ?f ; lulcw:targetEntity ?w ; lulcw:selectedUnder ?p }")}
    assert ("F1", "W1", "main") in paths and ("F4", "W1", "main") not in paths
    assert ("F4", "W1", "all-links") in paths
    assert not any(p == "confident-only" for _, _, p in paths)    # F1, F2 probable; F4 possible
    assert ("F1", "W2", "main") in paths                          # W2 probable, F1 probable
    touched = {p for s, p, _ in added if (s, RDF.type, L.UnitAttribution) in facts}
    assert touched == {L.selectedUnder}, f"the rules changed the evidence: {touched}"

    # CQ7
    cc = {k.rsplit("/", 1)[-1]: c.rsplit("/", 1)[-1] for k, c in select(
        g, "SELECT ?k ?c WHERE { ?k a lulcw:CropCode ; lulcw:cropClass ?c }")}
    assert cc == {"PEC": "orchard", "AGR": "citrus"}, cc           # ZZZ has no class
    areas = {c.rsplit("/", 1)[-1]: ha for c, ha in select(
        g, "SELECT ?c ?ha WHERE { ?x a lulcw:CropClassArea ; lulcw:cropClass ?c ; sosa:hasSimpleResult ?ha }")}
    assert areas == {"orchard": 4.0, "citrus": 2.0, "unmapped": 1.0}, areas
    assert abs(float(g.value(d("rule/high-irrigation-demand"), L.demandThresholdM3)) - 800.0) < 1e-9
    cats = {int(y): c.split("#")[-1] for y, c in select(g, """SELECT ?y ?c WHERE {
        ?x a lulcw:IrrigationDemandAssessment ; lulcw:demandCategory ?c ;
           prov:wasDerivedFrom/lulcw:rpgEdition ?y }""")}
    assert cats == {2016: "HighIrrigationDemand", 2017: "BelowHighIrrigationDemand",
                    2023: "HighIrrigationDemand"}, cats

    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results
    infos = sum(n for k, n in results.items() if k.startswith("Info"))
    assert infos == 1, results                                    # W2's missing depth
    print(f"  2. fixtures: CQ3, CQ11, CQ8, CQ2 and CQ7 cases hold; {len(added)} derived triples; "
          f"no violation, 1 info (the missing depth)")
    return g


# ---------------------------------------------------------------------- 3. negative controls
def test_negative_controls(g, shapes, net):
    def bad(triples, remove=()):
        h = rdflib.Graph()
        for t in g:
            if t not in remove:
                h.add(t)
        for t in triples:
            h.add(t)
        return check(h, shapes, net)[2]

    r, xz = d("stratigraphic-relation/2/X/Z"), []
    xz += [(r, RDF.type, L.StratigraphicRelation), (r, L.upperUnit, d("unit/X")),
           (r, L.lowerUnit, d("unit/Z")), (r, L.relationKind, L.DirectContact),
           (r, L.witnessedBy, d("polygon/2"))]
    cases = {
        "an ordering chained across polygons": (
            xz, (), "StratigraphicRelationShape", "never chained across polygons"),
        "a self-paired well link": (
            [(d("well-link/x"), RDF.type, L.WellLink), (d("well-link/x"), L.wellA, d("piezometer/W1")),
             (d("well-link/x"), L.wellB, d("piezometer/W1"))], (), "WellLinkShape", "two different"),
        "an eligible influence with an unknown sign": (
            [(d("influence/pumping/F2/1/group/to/W1/1"), L.constraintEligibility, L.EligibleConstraint)],
            [(d("influence/pumping/F2/1/group/to/W1/1"), L.constraintEligibility, L.IneligibleConstraint)],
            "InfluenceShape", "supported sign"),
        "an influence resting on an explicit unknown": (
            [(d("influence/pumping/F1/1/to/W1/1"), PROV.wasDerivedFrom, d("attribution/facility/F3/1"))],
            (), "InfluenceShape", "missing targets never become model edges"),
        "an attribution with a target and a reason for unknown": (
            [(d("attribution/facility/F1/1"), L.unknownReason, Literal("contradiction"))], (),
            "UnitAttributionShape", None),
        "overlies without a witness": (
            [(d("unit/X"), L.overlies, d("unit/Z"))], (), "OverliesShape", None),
        "a piezometer without an attribution": (
            [(d("piezometer/W9"), RDF.type, L.Piezometer), (d("piezometer/W9"), L.bssCode, Literal("W9")),
             (d("piezometer/W9"), PROV.wasDerivedFrom, d("release/test")),
             (d("piezometer/W9"), GEO.hasGeometry, d("geometry/piezometer/W1")),
             (d("station/W9"), L.hostedBy, d("piezometer/W9"))], (),
            "PiezometerShape", "at least one monitoring attribution"),
        "a selection the policy does not admit": (
            [(d("attribution/facility/F4/1"), L.selectedUnder, d("policy/main"))], (),
            "UnitAttributionShape", "does not admit"),
        "a path selected without its segments": (
            [(d("influence/pumping/F1/1/to/W1/1"), L.selectedUnder, d("policy/confident-only"))], (),
            "PathSelectionShape", None),
        "a class area that is not the sum of its codes": (
            [(d("crop-class-area/W1/2023/orchard"), SOSA.hasSimpleResult, Literal(5.0, datatype=XSD.double))],
            [(d("crop-class-area/W1/2023/orchard"), SOSA.hasSimpleResult, Literal(4.0, datatype=XSD.double))],
            "CropClassAreaShape", "sum of the code areas"),
        "a category that disagrees with the threshold": (
            [(d("crop-demand/W1/2017/main/assessment"), L.demandCategory, L.HighIrrigationDemand)],
            [(d("crop-demand/W1/2017/main/assessment"), L.demandCategory, L.BelowHighIrrigationDemand)],
            "IrrigationDemandAssessmentShape", "disagrees with the estimate"),
        "an RPG edition used for another year": (
            [(d("crop-area/W1/2023/PEC"), SOSA.phenomenonTime, d("interval/year/2016"))],
            [(d("crop-area/W1/2023/PEC"), SOSA.phenomenonTime, d("interval/year/2023"))],
            "CropAreaObservationShape", "its own year"),
        "a crop code with two classes": (
            [(d("crop-code/AGR"), L.cropClass, d("crop-class/orchard"))], (),
            "CropCodeShape", "at most one crop class"),
    }

    for name, (add, remove, shape, text) in cases.items():
        res = bad(add, remove)
        assert violations(res, shape, text) > 0, f"{name}: not caught\n{res}"
    print(f"  3. negative controls: all {len(cases)} inserted errors are reported as violations")


# ---------------------------------------------------------------- 4. data-backed regression
def store_of(*files):
    s = ox.Store()
    for f in files:
        s.bulk_load(path=str(f), format=ox.RdfFormat.TURTLE)
    return s


def rows(store, q):
    out = []
    for r in store.query(PRE + q):
        vals = []
        for v in r:
            if v is None:
                vals.append(None)
            elif isinstance(v, ox.Literal):
                dt = v.datatype.value if v.datatype else ""
                vals.append(float(v.value) if dt.endswith(("double", "decimal", "integer")) else v.value)
            else:
                vals.append(v.value)
        out.append(vals)
    return out


def l93(lon, lat):
    p = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs=CRS_WGS84).to_crs(CRS_L93)
    return np.round(p.x.to_numpy(), 1), np.round(p.y.to_numpy(), 1)


def oracle_relations(codes):
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    pile = pile[pile["CodePoly"].astype(int).isin(codes)].sort_values(["CodePoly", "OrdRelatif"])  # codes are text
    out = set()
    for cp, s in pile.groupby("CodePoly"):
        units = list(s["CodeEH"])
        for i in range(len(units)):
            for j in range(i + 1, len(units)):
                out.add((int(cp), units[i], units[j], "DirectContact" if j == i + 1 else "IndirectOrdering",
                         tuple(sorted(units[i + 1:j]))))
    return out


def test_data(store):
    # stratigraphy
    polys = {int(c) for (c,) in rows(store, "SELECT ?c WHERE { ?p a lulcw:ElementaryPolygon ; lulcw:polygonCode ?c }")}
    got = {}
    for cp, a, b, k, m in rows(store, """SELECT ?cp ?a ?b ?k ?m WHERE { ?r a lulcw:StratigraphicRelation ;
            lulcw:witnessedBy/lulcw:polygonCode ?cp ; lulcw:upperUnit/lulcw:bdlisaCode ?a ;
            lulcw:lowerUnit/lulcw:bdlisaCode ?b ; lulcw:relationKind ?k .
            OPTIONAL { ?r lulcw:interveningUnit/lulcw:bdlisaCode ?m } }"""):
        key = (int(cp), a, b, k.split("#")[-1])
        got.setdefault(key, set())
        if m is not None:
            got[key].add(m)
    got = {k + (tuple(sorted(v)),) for k, v in got.items()}
    want = oracle_relations(polys)
    assert got == want, f"relations differ: {sorted(got ^ want)[:5]}"
    plain = rows(store, """SELECT ?a ?b (COUNT(DISTINCT ?p) AS ?n) WHERE { ?r lulcw:relationKind lulcw:DirectContact ;
            lulcw:upperUnit/lulcw:bdlisaCode ?a ; lulcw:lowerUnit/lulcw:bdlisaCode ?b ; lulcw:witnessedBy ?p .
            ?p geo:sfIntersects <extent/plain-box> } GROUP BY ?a ?b""")
    step6b = pd.read_csv(INTERIM / "bdlisa_overlies_plain.csv")
    assert {(a, b, int(n)) for a, b, n in plain} == set(zip(step6b["upper"], step6b["lower"], step6b["n_polygons"])), \
        "plain direct contacts differ from Step 6b's overlies edges"
    n_over = rows(store, "SELECT (COUNT(*) AS ?n) WHERE { ?a lulcw:overlies ?b }")[0][0]
    assert n_over == len({(a, b) for _, a, b, k, _ in want if k == "DirectContact"})

    # well links
    w = pd.read_parquet(DATASET_DIR / "wells.parquet")
    w["x93"], w["y93"] = l93(w["x"], w["y"])
    w = w[w["code_bdlisa"].notna()]
    pairs = {}
    for (i, a), (j, b) in ((p, q) for p in w.iterrows() for q in w.iterrows()):
        if a["code_bss"] < b["code_bss"] and a["code_bdlisa"] == b["code_bdlisa"]:
            dist = float(np.hypot(a["x93"] - b["x93"], a["y93"] - b["y93"]))
            if dist <= RADIUS:
                za, zb = a["profondeur_investigation"], b["profondeur_investigation"]
                pairs[(a["code_bss"], b["code_bss"])] = (dist, abs(za - zb) if pd.notna(za) and pd.notna(zb) else None)
    links = {(a, b): (dist, dz) for a, b, dist, dz in rows(store, """SELECT ?a ?b ?d ?dz WHERE { ?l a lulcw:WellLink ;
            lulcw:wellA/lulcw:bssCode ?a ; lulcw:wellB/lulcw:bssCode ?b ; lulcw:horizontalDistanceM ?d .
            OPTIONAL { ?l lulcw:investigationDepthDifferenceM ?dz } }""")}
    assert set(links) == set(pairs), f"well links differ: {sorted(set(links) ^ set(pairs))}"
    for k, (dist, dz) in pairs.items():
        assert abs(links[k][0] - dist) < 0.15, (k, links[k], dist)   # 0.1 m rounding of points
        assert (dz is None) == (links[k][1] is None) and (dz is None or abs(links[k][1] - dz) < 1e-6), k

    # exact-unit influences
    bnpe = load_bnpe(BNPE_SNAPSHOT)
    fac = bnpe[bnpe["source"] == "groundwater"].groupby("code_ouvrage")[["longitude", "latitude"]].first()
    fac["x93"], fac["y93"] = l93(fac["longitude"], fac["latitude"])
    attr = pd.read_parquet(INTERIM / "pump_unit_attribution.parquet").dropna(subset=["unit"])
    attr = attr[attr["code_ouvrage"].isin(fac.index)].join(fac[["x93", "y93"]], on="code_ouvrage")
    want = {}
    for _, b in w.iterrows():
        m = attr[attr["unit"] == b["code_bdlisa"]]
        dist = np.hypot(m["x93"] - b["x93"], m["y93"] - b["y93"])
        for (code, rank), dd in zip(zip(m["code_ouvrage"], m["rank"]), dist):
            if dd <= RADIUS:
                want[(code, int(rank), b["code_bss"])] = float(dd)
    got = {(f, int(r), wb): dd for f, r, wb, dd in rows(store, """SELECT ?f ?r ?w ?d WHERE { ?i a lulcw:Influence ;
            lulcw:resolution lulcw:ExactUnitResolution ; lulcw:horizontalDistanceM ?d ;
            lulcw:driverEntity/lulcw:bnpeCode ?f ; lulcw:targetEntity/lulcw:bssCode ?w ;
            prov:wasDerivedFrom ?a . ?a lulcw:role lulcw:AbstractionRole ; lulcw:rank ?r }""")}
    assert set(got) == set(want), f"exact influences differ: {sorted(set(got) ^ set(want))[:5]}"
    assert max(abs(got[k] - want[k]) for k in want) < 0.15
    elig = rows(store, """SELECT (COUNT(?i) AS ?n) WHERE { ?i a lulcw:Influence ;
            lulcw:constraintEligibility lulcw:EligibleConstraint ; lulcw:resolution ?r .
            FILTER (?r != lulcw:ExactUnitResolution) }""")[0][0]
    assert elig == 0, "a group-level influence is eligible"

    # policy selections
    sel = {p.rsplit("/", 1)[-1]: int(n) for p, n in rows(store, """SELECT ?p (COUNT(?a) AS ?n) WHERE {
            ?a a lulcw:UnitAttribution ; lulcw:selectedUnder ?p } GROUP BY ?p""")}
    conf = {c.split("#")[-1]: int(n) for c, n in rows(store, """SELECT ?c (COUNT(?a) AS ?n) WHERE {
            ?a a lulcw:UnitAttribution ; lulcw:confidence ?c } GROUP BY ?c""")}
    assert sel == {"main": conf["Confident"] + conf["Probable"], "confident-only": conf["Confident"],
                   "all-links": sum(conf.values())}, (sel, conf)

    # land use (CQ7)
    classes = load_classes()
    ar = pd.read_parquet(AREA_OUT)
    groups = ar.groupby("CODE_CULTU")["CODE_GROUP"].first()
    spec = dict(zip(groups.index, code_to_class(groups.index.to_numpy(), groups.to_numpy(), classes)))
    kg_cls = {n: (c.rsplit("/", 1)[-1] if c else "unmapped") for n, c in rows(store, """SELECT ?n ?c WHERE {
            ?k a lulcw:CropCode ; skos:notation ?n . OPTIONAL { ?k lulcw:cropClass ?c } }""")}
    assert kg_cls == spec, f"crop classes differ: {sorted(set(kg_cls.items()) ^ set(spec.items()))[:5]}"
    ar["cls"] = ar["CODE_CULTU"].map(spec)
    want_area = ar.groupby(["code_bss", "rpg_year", "cls"])["ha"].sum()
    got_area = {(b, int(ed), c.rsplit("/", 1)[-1]): ha for b, ed, c, ha in rows(store, """SELECT ?b ?ed ?c ?ha WHERE {
            ?x a lulcw:CropClassArea ; sosa:hasFeatureOfInterest/lulcw:zoneOf/lulcw:bssCode ?b ;
               lulcw:rpgEdition ?ed ; lulcw:cropClass ?c ; sosa:hasSimpleResult ?ha }""")}
    assert set(got_area) == set(want_area.index), "class areas: other zone-year-class keys"
    close = lambda a, b: abs(a - b) <= 2e-6 * max(1.0, abs(b)) + 1e-4  # noqa: E731  Turtle doubles: 7 digits
    assert all(close(got_area[k], v) for k, v in want_area.items()), "class areas differ"
    dem = pd.read_parquet(INTERIM / f"crop_demand_weekly_{DATASET}.parquet",
                          columns=["code_bss", "week", "demand_main_m3", "demand_wide_m3"])
    days = dem.loc[dem.index.repeat(7)].reset_index(drop=True)   # each week spread over its 7 days
    days["day"] = days["week"] - pd.to_timedelta(np.tile(np.arange(6, -1, -1), len(dem)), unit="D")
    tot = days.groupby(["code_bss", days["day"].dt.year])[["demand_main_m3", "demand_wide_m3"]].sum() / 7.0
    tot = tot[tot.index.get_level_values(1).isin(range(2015, 2026))]
    est = {(b, int(y), q.split("#")[-1]): v for b, y, q, v in rows(store, """SELECT ?b ?y ?q ?v WHERE {
            ?e a lulcw:CropDemandEstimate ; sosa:hasFeatureOfInterest/lulcw:zoneOf/lulcw:bssCode ?b ;
               lulcw:rpgEdition ?y ; sosa:observedProperty ?q ; sosa:hasSimpleResult ?v }""")}
    assert len(est) == 2 * len(tot), (len(est), len(tot))

    def close_m3(a, b, atol=0.051):   # estimates are stored to 0.1 m³ (the threshold too)
        return abs(a - b) <= 2e-6 * max(1.0, abs(b)) + atol
    for (b, y), r in tot.iterrows():
        assert close_m3(est[(b, y, "PotentialIrrigationDemandMain")], r["demand_main_m3"]), (b, y)
        assert close_m3(est[(b, y, "PotentialIrrigationDemandWide")], r["demand_wide_m3"]), (b, y)
    train = tot[tot.index.get_level_values(1) <= 2019]["demand_main_m3"]
    thr = rows(store, "SELECT ?t WHERE { <rule/high-irrigation-demand> lulcw:demandThresholdM3 ?t }")[0][0]
    assert close_m3(thr, float(np.quantile(train, 2 / 3)), 0.11), thr
    high = {(b, int(y)) for b, y in rows(store, """SELECT ?b ?y WHERE {
            ?a lulcw:demandCategory lulcw:HighIrrigationDemand ;
               sosa:hasFeatureOfInterest/lulcw:zoneOf/lulcw:bssCode ?b ; prov:wasDerivedFrom/lulcw:rpgEdition ?y }""")}
    # categories from the stored estimates (checked above against pandas): with 325 training
    # values the tercile falls on the 217th one, so one zone-year sits on the threshold (high)
    assert high == {(b, y) for (b, y, q), v in est.items() if q == "PotentialIrrigationDemandMain" and v >= thr}

    # the validation report belongs to these files and has no violation
    s = json.loads((KG / f"lulcw_kg_{DATASET}_rules_summary.json").read_text())
    n_rules = len(rdflib.Graph().parse(KG / f"lulcw_kg_{DATASET}_rules.ttl"))
    assert s["rules_file_triples"] == n_rules, "the summary is from another run of the rules"
    assert s["shacl_conforms_no_violation"] and not any(k.startswith("Violation") for k in s["shacl_results"])
    print(f"  4. data: {len(want)} exact influences, {len(pairs)} well links and the relations of "
          f"{len(polys)} polygons equal the pandas oracles; plain contacts = Step 6b's {len(step6b)} "
          f"edges; selections = attribution counts; crop classes of {len(spec)} codes, "
          f"{len(want_area)} class areas and {len(est)} demand estimates = pandas; threshold "
          f"{thr:,.0f} m³, {len(high)} high-demand zone-years; report: no violation")


def main():
    net = ontology_network()
    rules, shapes = rdflib.Graph().parse(RULES), rdflib.Graph().parse(SHAPES)
    test_vocabulary(net)
    g = test_fixtures(rules, shapes, net)
    test_negative_controls(g, shapes, net)
    facts, derived = KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"
    if facts.exists() and derived.exists():
        test_data(store_of(facts, derived))
    else:
        print("  4. skipped: run src.kg.build_kg and src.kg.apply_rules first")
    print("test_kg_rules: all checks passed")


if __name__ == "__main__":
    main()
