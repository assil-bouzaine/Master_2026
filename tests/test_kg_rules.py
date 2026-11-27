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
   CQ4  0.6 + 0.4 km² of a unit's outcrop in two cells give weights 0.6 / 0.4 and a covered
        fraction 1; 0.8 of 1 km² inside cells gives a fraction 0.8 and weights renormalised over
        the covered part (0.625 / 0.375); a unit only below order 1 gets no coverage; every piece
        of the outcrop, the one outside the cells too, is cited
   CQ8  recharge proxies: W7 (unit X at outcrop in its zone) gets one influence per cell, weights
        0.625 / 0.375, effective rainfall standing in for groundwater recharge, non-decreasing,
        eligible, the four omitted pathways named, the covered fraction in its conditions; W8 (no
        outcrop of its unit Y in its zone) gets none locally and one unit-wide (c2, weight 1, the
        extent holding 0.8 of Y's outcrop said in its conditions); W1, whose zone holds outcrop of
        other units only, gets none; a policy selects a proxy exactly when it selects the well's
        attribution (W8's is probable)
   CQ5  rivers: R1's watercourse on its unit's outcrop, in a water body where a statement documents
        drainage, gets an eligible, non-decreasing influence from the nearest gauge of the pool (a
        nearer gauge outside the pool is not used); R2's river over the unit covering its own gets a
        conditional, ineligible influence with the cover unit named; R3's unit is not under the
        reaches, but a statement documents its exchange with the zone's section: documented lateral,
        eligible; R4 (no documented section, 50 m off the map) non-decreasing but ineligible; R5,
        where one statement states independence and another an exchange, ineligible; R6's
        watercourse has no pool gauge: an association and no influence; a statement that does not
        delimit its stretch applies to no zone
   CQ6  canals: R1's canal on its unit's outcrop with measured/traced return statements gives an
        eligible canal influence of the intake group; R6's (hedged synthesis + aggregate statement)
        and R13's (stated synthesis only) give ineligible ones; R14's (hedged differential gauging)
        gives an eligible one; the river and canal influences are selected exactly with the wells'
        attributions
   The fixture graph, with the rule outputs, has no violation.
3. Negative controls, each inserted on purpose and reported as a violation: an ordering chained
   across two polygons, a self-paired well link, an eligible influence with an unknown sign,
   an influence resting on an explicit unknown, an attribution with both a target and a reason
   for unknown, `overlies` without a witness, a piezometer without an attribution, a selection
   of a confidence level the policy does not admit, a path selected without its segments, a
   class area that is not the sum of its codes, a category that disagrees with the threshold,
   an RPG edition used for another year, a crop code with two classes, a code area that no class
   area counts, a code area counted by two class areas, two class areas for one zone, year and
   class; (CQ4) cell weights that do not sum to one, pieces of a polygon larger than the polygon,
   two pieces with one polygon, extent and cell, a piece under 1 m², a coverage citing a piece of
   another extent, a covered fraction that is not covered / outcrop, a cell weight outside any
   coverage, a coverage larger than the unit's whole mapped outcrop, two coverages for one extent
   and unit; (CQ8 recharge proxies) a proxy that does not name the pathways it omits, a second
   proxy of the same surplus on one path (soil drainage beside effective rainfall), a missing
   proxy in a well's zone and in the unit-wide extent (a derivation not run, or stale), a proxy
   resting on another well's attribution, a driver that is not a water-surplus proxy, a proxy in
   another well's search zone; (CQ5, CQ6) a missing on-outcrop association, an eligible river
   influence over cover, an eligible river influence without a documented exchange, a river
   influence from a gauge outside the pool, two river influences on one path, a missing river
   influence, a river piece in a section of another watercourse, a statement without its passage,
   an eligible canal influence on a synthesis statement, a canal statement about a river section, a
   distance along the river off the main stem, a canal reach typed as a river reach, a documented
   lateral association without its statement, an association whose unit is not the well's, a
   missing canal influence.
4. Data-backed regression (when the graph and the rule outputs exist), against pandas on the
   source tables: the stratigraphic relations equal the pairs of the BD LISA stack table for
   the graph's polygons, and the direct contacts of the plain's polygons equal the overlies
   edges of Step 6b (bdlisa_overlies_plain.csv, polygon counts included); the well links equal
   the same-unit pairs within 5 km of wells.parquet (distances, depth differences); the
   exact-unit influences equal the facility-well pairs of the attribution table of task 12.3
   and the BNPE coordinates; the policy selections equal the attribution counts; the crop class
   of every code equals src.dataset.crop_demand.code_to_class, the class areas equal the clipped
   areas summed with pandas, and in the stored files each class area equals the sum of the stored
   code areas it cites (doubles are written exactly), the demand estimates equal the weekly index
   spread over its days and
   summed by calendar year, and the threshold and categories follow; the validation report of
   src.kg.apply_rules is the one of the current files and has no violation.
5. Data, CQ4: the outcrop coverages and cell weights equal oracle_coverage (GeoPandas on BD LISA
   and the raw SAFRAN grid, written apart from src.kg.forcing), and each unit's mapped outcrop equals
   the order-1 polygons of the whole extract.
6. Data, CQ8 recharge proxies: for every well with a recorded unit described by BD LISA, the cells
   and weights of its influences equal the oracle's for that unit in its zone and in the forcing
   extent; none for the other wells; signs, proxy, omitted pathways and policy selections as
   specified. Sections 4-6 run only on a validated release (src.kg.release.check): facts, rule
   outputs, rules, shapes and ontology unchanged since src.kg.apply_rules validated them.
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
from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, PROCESSED, RAW, ROOT
from src.dataset.crop_demand import AREA_OUT, code_to_class, load_classes
from src.kg.apply_rules import (RULES, SHAPES, check, ontology_network, rule_records,
                                run_rules)
from src.kg import release
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
# the export policies' constraint decisions (configs/constraint_decisions.csv in the real graph)
FIXTURE_DECISIONS = {"PumpingDrawdown": (L.AcceptedStatus, L.AcceptedStatus),
                     "DiffuseRecharge": (L.CandidateStatus, L.CandidateStatus),
                     "VerticalLeakage": (L.CandidateStatus, L.CandidateStatus),
                     "RiverExchange": (L.CandidateStatus, L.CandidateStatus),
                     "CanalReturnFlow": (L.CandidateStatus, L.CandidateStatus)}


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
            for mech in FIXTURE_DECISIONS:
                a((p, L.constraintDecision, d(f"constraint-decision/{mech}")))
        for mech, (proxy, approval) in FIXTURE_DECISIONS.items():
            n = d(f"constraint-decision/{mech}")
            a((n, RDF.type, L.ConstraintDecision))
            a((n, L.decisionMechanism, L[mech]))
            a((n, L.proxyReview, proxy))
            a((n, L.constraintApproval, approval))
            a((n, L.decisionBasis, Literal(f"fixture decision for {mech}", lang="en")))

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
    A, B, C, X, Y, Z, U, V, M = (fx.unit(c) for c in "ABCXYZUVM")
    fx.polygon(1, [A, B, C])
    fx.polygon(2, [X, Y])
    fx.polygon(3, [Y, Z])
    fx.polygon(4, [M])                                   # single-layer: no stratigraphic pair, canal method tests
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
    fx.well("W7", -30000, 0, X, L.Confident, depth=60)   # recharge: X at outcrop in its zone
    fx.well("W8", -30000, -30000, Y, L.Probable, depth=70)   # no Y outcrop in its zone; unit-wide only
    add_landuse(fx)
    add_forcing(fx, (A, B, C, X, Y, Z))
    add_rivers(fx, {"A": A, "B": B, "X": X, "Z": Z, "M": M})
    return fx, {"A": A, "B": B, "C": C, "X": X, "Y": Y, "Z": Z, "U": U, "V": V, "M": M, "G": G}


def add_forcing(fx, described):
    """CQ4 fixture, on the three polygons of the stacks (1 km² each): the search zone of W1 holds
    polygon 1 (A at outcrop) as 0.6 km² in cell c1 and 0.4 km² in c2, and polygon 2 (X at outcrop)
    as 0.5 km² in c1, 0.3 km² in c2 and 0.2 km² outside every cell; the forcing extent holds
    polygon 3 (Y at outcrop) in c2. Units A-Z are described by BD LISA (a source record), U and V
    are not; mapped outcrop over the whole release: A 1 km² (all in the zone), X 2 km² (half),
    Y 1.25 km² (the forcing extent clips it to 0.8), B, C, Z never at outcrop.
    Recharge proxies (CQ8): W7 (unit X) has polygon 2 in its zone as W1 has; W8 (unit Y) has
    polygon 1 (A at outcrop, no Y) in its zone, so a completed search finds no outcrop of its unit,
    and only the forcing extent (the unit-wide sensitivity) connects it to c2. W1's zone holds
    outcrop of A and X, but W1 monitors U, which is not at outcrop anywhere."""
    a = fx.g.add
    for u in described:
        a((u, PROV.wasDerivedFrom, fx.rel))
        m2 = FIXTURE_MAPPED_OUTCROP.get(str(u).rsplit("/", 1)[-1], 0.0)
        a((u, L.mappedOutcropAreaM2, Literal(m2, datatype=XSD.double)))
    for k, (x, y) in {"c1": (100, 200), "c2": (180, 200)}.items():
        c = d(f"weather-cell/{k}")
        a((c, RDF.type, L.WeatherCell))
        a((c, L.safranGridXHm, Literal(x, datatype=XSD.integer)))
        a((c, L.safranGridYHm, Literal(y, datatype=XSD.integer)))
        a((c, L.inRelease, fx.rel))
        fx.geometry(c, "weather-cell", k, "POLYGON((0 0, 8000 0, 8000 8000, 0 8000, 0 0))")
        se = d(f"series/forcing-test/{k}/PE")
        a((se, RDF.type, L.ObservationSeries))
        a((se, L.seriesVariable, L.EffectiveRainfall))
        a((se, L.storedIn, Literal(f"forcing_weekly.parquet [cell_id = {k}, column PE]")))
        a((c, L.hasForcingSeries, se))
    zones, forcing = {}, d("extent/forcing-cells")
    for w in ("W1", "W7", "W8"):
        zones[w] = d(f"outcrop-zone/{w}")
        a((zones[w], RDF.type, L.OutcropSearchZone))
        a((zones[w], L.zoneOf, d(f"piezometer/{w}")))
        a((zones[w], L.zoneRadiusM, Literal(RADIUS, datatype=XSD.double)))
    a((forcing, RDF.type, GEO.Feature))
    for ext, poly, cell, m2 in FIXTURE_PIECES:
        x = d(f"polygon-cell/{ext}/{poly}/{cell or 'outside'}")
        a((x, RDF.type, L.PolygonCellIntersection))
        a((x, L.intersectedPolygon, d(f"polygon/{poly}")))
        a((x, L.withinExtent, zones["W1"] if ext == "zone" else zones.get(ext, forcing)))
        if cell:
            a((x, L.intersectedCell, d(f"weather-cell/{cell}")))
        a((x, L.intersectionAreaM2, Literal(m2, datatype=XSD.double)))
        a((x, PROV.wasGeneratedBy, d("execution/polygon-cell-intersection")))


# CQ5, CQ6: wells R1-R14 (far from the others: no well link, no pumping or recharge path), each with
# its reach search zone; (zone, reach, watercourse or None for a canal, polygon or None off the map,
# length m, section(s) or None)
RIVER_WELLS = (("R1", "X"), ("R2", "Z"), ("R3", "B"), ("R4", "X"), ("R5", "X"), ("R6", "A"),
               ("R7", "X"), ("R8", "B"), ("R9", "B"), ("R10", "X"), ("R11", "X"), ("R12", "X"),
               ("R13", "M"), ("R14", "M"))
RIVER_PIECES = (("R1", "r1", "WC1", 2, 1500.0, "FRDRT1"), ("R1", "k1", None, 2, 800.0, None),
                ("R2", "r2", "WC2", 3, 1200.0, None),
                ("R3", "r3", "WC1", 2, 700.0, "t-sec2"),
                ("R4", "r4", "WC1", 2, 900.0, None), ("R4", "r4b", "WC1", None, 50.0, None),
                ("R5", "r5", "WC1", 2, 600.0, "FRDRT3"),
                ("R6", "r6", "WC3", 1, 1000.0, None), ("R6", "k6", None, 1, 400.0, None),
                ("R7", "r7", "WC1", 2, 500.0, "FRDRT1"), ("R7", "r7b", "WC1", None, 40.0, None),
                ("R7", "k7", None, 2, 300.0, None),
                ("R8", "r8", "WC2", None, 60.0, None), ("R8", "k8", None, None, 70.0, None),
                ("R9", "r9", "WC1", 2, 400.0, "FRDRT1"),
                ("R10", "r10a", "WC4", 2, 600.0, "t-up"), ("R10", "r10b", "WC4", 2, 600.0, "t-down"),
                ("R11", "r11", "WC4", 2, 700.0, ("t-up", "FRDRT4")),
                ("R12", "r12", "WC4", 2, 700.0, ("t-up", "FRDRT5")),
                ("R13", "k13", None, 4, 350.0, None),
                ("R14", "k14", None, 4, 450.0, None))
# sections: id -> watercourse; overlapping pairs (both orders are written, as src/kg/rivers.py does)
RIVER_SECTIONS = {"FRDRT1": "WC1", "FRDRT3": "WC1", "t-sec2": "WC1",
                  "t-up": "WC4", "t-down": "WC4", "FRDRT4": "WC4", "FRDRT5": "WC4"}
SECTION_OVERLAPS = (("t-up", "FRDRT4"), ("t-up", "FRDRT5"), ("FRDRT4", "FRDRT5"))
# gauge, watercourse, pool member; per zone: (distance m, position, distance along the river m or None)
RIVER_GAUGES = {"G1": ("WC1", True), "G2": ("WC1", True), "G3": ("WC1", False), "G4": ("WC2", True),
                "G5": ("WC3", False)}
RIVER_RELATIONS = {("R1", "G1"): (1000.0, "UpstreamOfZone", 2000.0), ("R1", "G2"): (3000.0, "DownstreamOfZone", 5000.0),
                   ("R1", "G3"): (500.0, "AlongZoneStretch", 0.0),
                   ("R3", "G1"): (4000.0, "UpstreamOfZone", 6000.0), ("R3", "G2"): (2500.0, "DownstreamOfZone", 3000.0),
                   ("R3", "G3"): (100.0, "OffMainStem", None),
                   ("R4", "G1"): (1200.0, "UpstreamOfZone", 1500.0), ("R4", "G2"): (2000.0, "DownstreamOfZone", 2500.0),
                   ("R4", "G3"): (300.0, "AlongZoneStretch", 0.0),
                   ("R5", "G1"): (800.0, "AlongZoneStretch", 0.0), ("R5", "G2"): (900.0, "DownstreamOfZone", 1000.0),
                   ("R5", "G3"): (700.0, "AlongZoneStretch", 0.0),
                   ("R2", "G4"): (600.0, "DownstreamOfZone", 700.0), ("R6", "G5"): (400.0, "AlongZoneStretch", 0.0),
                   ("R7", "G1"): (900.0, "UpstreamOfZone", 1000.0), ("R7", "G2"): (2500.0, "DownstreamOfZone", 3000.0),
                   ("R8", "G4"): (300.0, "AlongZoneStretch", 0.0),
                   ("R9", "G1"): (1500.0, "UpstreamOfZone", 1800.0), ("R9", "G2"): (2600.0, "DownstreamOfZone", 2900.0)}
# statement, mechanism, section (or None), watercourse (or None), unit (a tuple: an aggregate of
# those units), direction, hedging, method, period (or None), measured at (a fixture well, or None)
SUMMER_2020, SEPT_2017, YEAR_2011 = ("2020-06-01", "2020-08-31"), ("2017-09-11", "2017-09-13"), ("2011-01-01", "2011-12-31")
RIVER_STATEMENTS = (("S1", "RiverExchange", "FRDRT1", "WC1", "X", "AquiferToSurface", "StatedFinding", "SynthesisStatement", None, None),
                    ("S2", "RiverExchange", "t-sec2", "WC1", "B", "ExchangeEquilibrium", "StatedFinding", "SynthesisStatement", None, None),
                    ("S3", "RiverExchange", "FRDRT3", "WC1", "X", "NoExchange", "StatedFinding", "DifferentialGauging", SUMMER_2020, None),
                    ("S4", "RiverExchange", "FRDRT3", "WC1", "X", "SurfaceToAquifer", "StatedFinding", "DifferentialGauging", SUMMER_2020, None),
                    ("S5", "RiverExchange", None, "WC1", "X", "SurfaceToAquifer", "StatedFinding", "SynthesisStatement", None, None),
                    ("S7", "RiverExchange", "FRDRT1", "WC1", ("X", "B"), "AquiferToSurface", "StatedFinding", "SynthesisStatement", None, None),
                    ("S8", "RiverExchange", "t-up", "WC4", "X", "AquiferToSurface", "StatedFinding", "DifferentialGauging", SEPT_2017, None),
                    ("S9", "RiverExchange", "t-down", "WC4", "X", "SurfaceToAquifer", "StatedFinding", "DifferentialGauging", SEPT_2017, None),
                    ("S10", "RiverExchange", "FRDRT4", "WC4", "X", "SurfaceToAquifer", "StatedFinding", "DifferentialGauging", YEAR_2011, None),
                    ("S11", "RiverExchange", "FRDRT5", "WC4", "X", "SurfaceToAquifer", "StatedFinding", "SynthesisStatement", None, None),
                    ("C1", "CanalReturnFlow", None, None, "X", "SurfaceToAquifer", "StatedFinding", "DifferentialGauging", None, None),
                    ("C2", "CanalReturnFlow", None, None, "A", "SurfaceToAquifer", "HedgedFinding", "SynthesisStatement", None, None),
                    ("C3", "CanalReturnFlow", None, None, ("A", "X"), "SurfaceToAquifer", "StatedFinding", "WaterBalanceEstimate", None, None),
                    ("C4", "CanalReturnFlow", None, None, "X", "SurfaceToAquifer", "StatedFinding", "GeochemicalTracing", None, "R1"),
                    ("C5", "CanalReturnFlow", None, None, "M", "SurfaceToAquifer", "StatedFinding", "SynthesisStatement", None, "R13"),
                    ("C6", "CanalReturnFlow", None, None, "M", "SurfaceToAquifer", "HedgedFinding", "DifferentialGauging", None, "R14"))


def add_rivers(fx, u):
    """CQ5, CQ6 fixture on the polygons of the stacks: R1 (unit X) has watercourse WC1 on X's outcrop
    (polygon 2) inside water body FRDRT1, where S1 documents drainage of X, and a canal on that
    outcrop with a stated return statement (C1); R2 (unit Z) has WC2 over Y, which covers Z
    (polygon 3); R3 (unit B) has WC1 on polygon 2, which does not hold B, inside section t-sec2 where
    S2 documents an exchange with B (documented lateral); R4 (unit X) has WC1 on X's outcrop in no
    documented section, and 50 m of it off the map; R5 (unit X) has WC1 in water body FRDRT3, where
    S3 states independence and S4 an exchange for the same summer (a contradiction); R6 (unit A) has
    WC3 (no pool gauge) on A's outcrop (polygon 1) and a canal there with a hedged return statement
    (C2). S5 is about WC1 without a delimited stretch: listed, never applied. Gauges G1, G2 (pool) and
    G3 (not pool) are on WC1, G4 (pool) on WC2, G5 (not pool) on WC3; G3 is the nearest in R1's zone
    but not in the pool.
    Codex review of 2026-11-06: S7 is about an aggregate of X and B (a groundwater body) in FRDRT1:
    localised to R1's and R7's on-outcrop associations of X, it never makes R9 (unit B, WC1 on polygon
    2 in FRDRT1, which does not hold B) a documented lateral association (R1); C3, a stated return
    into an aggregate of A and X, is localised to the canal associations and makes R6 no sign; C4, a
    return measured at R1, applies to R1 only, not to R7 (unit X, canal on X's outcrop) (Q3); R7 is
    documented by S1 but 40 m of its WC1 lie off the map (CQ5 partial, Q2); R8 (unit B) has only
    pieces off the map, of WC2 (a pool gauge) and of a canal (CQ8 unknown, never none_found, Q1);
    on WC4 (no gauge), R10 has opposite dated states for the adjacent stretches t-up and t-down
    (variation), R11 opposite states for t-up (2017) and the overlapping water body FRDRT4 (2011:
    disjoint periods, variation), R12 for t-up and the overlapping FRDRT5, undated (unresolved, a
    conflict) (R4)."""
    a = fx.g.add
    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    exe = d("execution/river-geometry")
    a((exe, RDF.type, L.RuleExecution))
    for key, unit in RIVER_WELLS:
        k = int(key[1:])
        fx.well(key, 100000 + 20000 * k, 100000, u[unit], L.Confident, depth=30)
        z = d(f"reach-zone/{key}")
        a((z, RDF.type, L.ReachSearchZone))
        a((z, L.zoneOf, d(f"piezometer/{key}")))
        a((z, L.zoneRadiusM, dbl(RADIUS)))
    for wc in ("WC1", "WC2", "WC3", "WC4"):
        n = d(f"watercourse/{wc}")
        a((n, RDF.type, L.Watercourse))
        a((n, RDFS.label, Literal(f"river {wc}", lang="fr")))
        a((n, L.bdCarthageCode, Literal(wc)))
        a((n, L.mainStemLengthM, dbl(50000)))
        a((n, L.inRelease, fx.rel))
    def sec(s):
        return d(f"water-body/{s}" if s.startswith("FRDR") else f"river-section/{s}")
    for s, wc in RIVER_SECTIONS.items():
        n = sec(s)
        a((n, RDF.type, L.SurfaceWaterBody if s.startswith("FRDR") else L.RiverSection))
        a((n, RDFS.label, Literal(f"section {s}", lang="fr")))
        a((n, L.sectionOf, d(f"watercourse/{wc}")))
        if s.startswith("FRDR"):
            a((n, L.wfdCode, Literal(s)))
            a((n, L.inRelease, fx.rel))
        else:
            a((n, L.chainageFromM, dbl(1000)))
            a((n, L.chainageToM, dbl(4000)))
        fx.geometry(n, "section", s, "LINESTRING(0 0, 1000 0)")
    for x1, x2 in SECTION_OVERLAPS:
        a((sec(x1), L.overlapsSection, sec(x2)))
        a((sec(x2), L.overlapsSection, sec(x1)))
    reaches = {}
    for zone, r, wc, poly, length, secs in RIVER_PIECES:
        if r not in reaches:
            n = d(f"reach/{r}")
            a((n, RDF.type, L.RiverReach if wc else L.CanalReach))
            a((n, RDFS.label, Literal(f"reach {r}", lang="fr")))
            a((n, L.bdtopoId, Literal(r)))
            a((n, L.reachNature, Literal("Ecoulement naturel" if wc else "Canal")))
            if wc:
                a((n, L.reachOf, d(f"watercourse/{wc}")))
                a((n, L.onMainStem, Literal(False)))
            a((n, L.inRelease, fx.rel))
            fx.geometry(n, "reach", r, "LINESTRING(0 0, 100 0)")
            reaches[r] = n
        x = d(f"reach-piece/{zone}/{r}/{poly or 'off-map'}")
        a((x, RDF.type, L.ReachPiece))
        a((x, L.pieceOfReach, reaches[r]))
        if poly:
            a((x, L.piecePolygon, d(f"polygon/{poly}")))
        a((x, L.withinExtent, d(f"reach-zone/{zone}")))
        a((x, L.pieceLengthM, dbl(length)))
        for one in (secs if isinstance(secs, tuple) else (secs,) if secs else ()):
            a((x, L.inSection, sec(one)))
        a((x, PROV.wasGeneratedBy, exe))
    pool = d("gauge-pool/arm-c")
    a((pool, RDF.type, L.GaugePool))
    for g, (wc, in_pool) in RIVER_GAUGES.items():
        n = d(f"gauge/{g}")
        a((n, RDF.type, L.RiverGauge))
        a((n, RDFS.label, Literal(f"gauge {g}", lang="fr")))
        a((n, L.gaugeCode, Literal(g)))
        a((n, L.onWatercourse, d(f"watercourse/{wc}")))
        a((n, L.chainageM, dbl(1000)))
        a((n, L.offsetFromStemM, dbl(5)))
        a((n, L.inRelease, fx.rel))
        fx.geometry(n, "gauge", g, "POINT(0 0)")
        se = d(f"series/rivers-test/{g}")
        a((se, RDF.type, L.ObservationSeries))
        a((se, L.seriesVariable, L.RiverDischarge))
        a((se, L.observedTrainingWeeks, Literal(700, datatype=XSD.integer)))
        a((se, L.trainingWeeks, Literal(783, datatype=XSD.integer)))
        a((n, L.hasDischargeSeries, se))
        if in_pool:
            a((pool, L.poolMember, n))
    for (zone, g), (dist, pos, along) in RIVER_RELATIONS.items():
        x = d(f"gauge-zone/{zone}/{g}")
        a((x, RDF.type, L.GaugeZoneRelation))
        a((x, L.relatedGauge, d(f"gauge/{g}")))
        a((x, L.withinExtent, d(f"reach-zone/{zone}")))
        a((x, L.horizontalDistanceM, dbl(dist)))
        a((x, L.alongRiverPosition, getattr(L, pos)))
        if along is not None:
            a((x, L.alongRiverDistanceM, dbl(along)))
        a((x, PROV.wasGeneratedBy, exe))
    doc = d("document/test")
    a((doc, RDF.type, L.Document))
    a((doc, RDFS.label, Literal("test report", lang="fr")))
    a((doc, L.sourceUrl, Literal("https://example.org/report.pdf", datatype=XSD.anyURI)))
    a((doc, L.md5, Literal("0" * 32)))
    a((doc, L.retrievalDate, Literal("2026-11-06", datatype=XSD.date)))
    for sid, mech, secn, wc, units, direction, hedging, method, period, site in RIVER_STATEMENTS:
        pa = d(f"passage/{sid}")
        a((pa, RDF.type, L.DocumentPassage))
        a((pa, L.inDocument, doc))
        a((pa, L.pageLabel, Literal("1")))
        a((pa, L.quote, Literal(f"a verbatim quote of statement {sid}", lang="fr")))
        s = d(f"exchange-statement/{sid}")
        a((s, RDF.type, L.ExchangeStatement))
        a((s, L.statedMechanism, getattr(L, mech)))
        if secn:
            a((s, L.aboutSection, sec(secn)))
        if wc:
            a((s, L.aboutWatercourse, d(f"watercourse/{wc}")))
        for unit in (units if isinstance(units, tuple) else (units,)):
            a((s, L.aggregateMemberUnit if isinstance(units, tuple) else L.aboutUnit, u[unit]))
        a((s, L.unitAsNamed, Literal(f"unit {units}", lang="fr")))
        a((s, L.unitMapping, L.UnitListedBySource))
        a((s, L.exchangeDirection, getattr(L, direction)))
        a((s, L.hedging, getattr(L, hedging)))
        a((s, L.evidenceMethod, getattr(L, method)))
        if period:
            a((s, L.periodStart, Literal(period[0], datatype=XSD.date)))
            a((s, L.periodEnd, Literal(period[1], datatype=XSD.date)))
        if site:
            a((s, L.measuredAt, d(f"piezometer/{site}")))
        a((s, L.stateDescription, Literal("low flow (fixture)", lang="en")))
        a((s, L.evidenceKind, L.ExpertHypothesis))
        a((s, PROV.wasDerivedFrom, pa))
    grp, it = d("canal-intakes/plain"), d("surface-intake/I1")
    a((grp, RDF.type, L.CanalIntakeGroup))
    a((it, RDF.type, L.SurfaceWaterIntake))
    a((it, L.bnpeCode, Literal("I1")))
    a((it, L.waterSource, L.SurfaceWaterSource))
    fx.geometry(it, "surface-intake", "I1", "POINT(0 0)")
    a((grp, L.intakeMember, it))
    vs = d("series/canal-test/plain")
    a((vs, RDF.type, L.ObservationSeries))
    a((vs, L.seriesVariable, L.CanalDiversionVolume))
    a((grp, L.hasVolumeSeries, vs))


FIXTURE_MAPPED_OUTCROP = {"A": 1.0e6, "X": 2.0e6, "Y": 1.25e6}
# extent ("zone" = W1's search zone, W7 / W8 = theirs), polygon, cell (None = outside every cell), m²
FIXTURE_PIECES = (("zone", 1, "c1", 6.0e5), ("zone", 1, "c2", 4.0e5),
                  ("zone", 2, "c1", 5.0e5), ("zone", 2, "c2", 3.0e5), ("zone", 2, None, 2.0e5),
                  ("forcing", 3, "c2", 1.0e6),
                  ("W7", 2, "c1", 5.0e5), ("W7", 2, "c2", 3.0e5), ("W7", 2, None, 2.0e5),
                  ("W8", 1, "c1", 6.0e5), ("W8", 1, "c2", 4.0e5))


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

    # CQ8: pumping drawdown
    infl = {(f.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1]): (s.split("#")[-1], e.split("#")[-1], r.split("#")[-1])
            for f, w, s, e, r in select(g, """SELECT ?f ?w ?s ?e ?r WHERE { ?i a lulcw:Influence ;
                lulcw:mechanism lulcw:PumpingDrawdown ;
                lulcw:driverEntity ?f ; lulcw:targetEntity ?w ; lulcw:responseSign ?s ;
                lulcw:constraintEligibility ?e ; lulcw:resolution ?r }""")}
    for w in ("W1", "W2", "W3"):
        assert infl[("F1", w)] == ("NegativeResponse", "EligibleConstraint", "ExactUnitResolution")
        assert infl[("F4", w)] == ("NegativeResponse", "EligibleConstraint", "ExactUnitResolution")
        assert infl[("F2", w)] == ("UnknownResponse", "IneligibleConstraint", "UnitGroupResolution")
    assert len(infl) == 9 and not any(f in ("F3", "F5") or w == "W4" for f, w in infl), infl

    # CQ4, CQ8: recharge proxies. W7 gets c1 and c2 from X's outcrop in its zone, with X's weights
    # renormalised over the covered 0.8; W8 gets c2 only from the unit-wide extent, where Y is
    # clipped to 0.8 of its outcrop; nothing reaches W1 (its unit U is at outcrop nowhere, and A
    # and X in its zone are not its unit) nor any well without a zone
    rech = {}
    for c, w, s, wt, sign, elig, var, q, conf, grp, res, n_om, cond in select(g, """
            SELECT ?c ?w ?s ?wt ?sign ?elig ?var ?q ?conf ?grp ?res (COUNT(DISTINCT ?om) AS ?n) ?cond WHERE {
            ?i a lulcw:Influence ; lulcw:mechanism lulcw:DiffuseRecharge ; lulcw:driverEntity ?c ;
               lulcw:targetEntity ?w ; lulcw:withinExtent ?s ; lulcw:responseSign ?sign ;
               lulcw:constraintEligibility ?elig ; lulcw:driverVariable ?var ; lulcw:proxyFor ?q ;
               lulcw:confidence ?conf ; lulcw:driverGroup ?grp ; lulcw:resolution ?res ;
               lulcw:omitsPathway ?om ; lulcw:conditions ?cond ; prov:wasDerivedFrom ?cw .
            ?cw lulcw:cellWeight ?wt . }
            GROUP BY ?c ?w ?s ?wt ?sign ?elig ?var ?q ?conf ?grp ?res ?cond"""):
        rech[(c.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1], s.rsplit("/", 1)[-1])] = (
            wt, *(x.split("#")[-1] for x in (sign, elig, var, q, conf, grp, res)), n_om, cond)
    same = ("PositiveResponse", "EligibleConstraint", "EffectiveRainfall", "GroundwaterRecharge")
    assert {k: v[:5] for k, v in rech.items()} == {
        ("c1", "W7", "W7"): (0.625, *same), ("c2", "W7", "W7"): (0.375, *same),
        ("c2", "W8", "forcing-cells"): (1.0, *same)}, rech
    assert all(v[5:9] == (("Confident" if k[1] == "W7" else "Probable"), "RechargeProxies",
                          "ExactUnitResolution", 4) for k, v in rech.items()), rech
    assert "within 5000 m" in rech[("c1", "W7", "W7")][9] and "covered fraction 0.8" in rech[("c1", "W7", "W7")][9]
    assert "share 0.8 of the unit's mapped outcrop" in rech[("c2", "W8", "forcing-cells")][9], rech
    rsel = {(w.rsplit("/", 1)[-1], p.rsplit("/", 1)[-1]) for w, p in select(g, """SELECT ?w ?p WHERE {
        ?i lulcw:mechanism lulcw:DiffuseRecharge ; lulcw:targetEntity ?w ; lulcw:selectedUnder ?p }""")}
    assert rsel == {("W7", "main"), ("W7", "confident-only"), ("W7", "all-links"),
                    ("W8", "main"), ("W8", "all-links")}, rsel     # W8's attribution is probable

    # CQ2 and path selection
    sel = {(x.split("/attribution/")[-1], p.rsplit("/", 1)[-1]) for x, p in select(
        g, "SELECT ?x ?p WHERE { ?x a lulcw:UnitAttribution ; lulcw:selectedUnder ?p }")}
    assert ("facility/F4/1", "main") not in sel and ("facility/F4/1", "all-links") in sel
    assert ("piezometer/W2/1", "confident-only") not in sel and ("piezometer/W1/1", "confident-only") in sel
    assert not any(x.startswith("facility/F3") for x, _ in sel)
    pumps = {(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1]) for s, o in g.subject_objects(L.pumpsFrom)}
    assert pumps == {("F1", "U"), ("F5", "U")}, pumps            # F2 is group-level, F4 possible
    paths = {(f.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1], p.rsplit("/", 1)[-1]) for f, w, p in select(
        g, "SELECT ?f ?w ?p WHERE { ?i lulcw:mechanism lulcw:PumpingDrawdown ; lulcw:driverEntity ?f ; lulcw:targetEntity ?w ; lulcw:selectedUnder ?p }")}
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

    # CQ4: coverage per (extent, unit at outcrop), weights renormalised over the covered part
    cov = {(s.rsplit("/", 1)[-1], u.rsplit("/", 1)[-1]): (o, c, f) for s, u, o, c, f in select(g, """
        SELECT ?s ?u ?o ?c ?f WHERE { ?v a lulcw:OutcropCoverage ; lulcw:withinExtent ?s ; lulcw:coverageUnit ?u ;
            lulcw:outcropAreaM2 ?o ; lulcw:coveredAreaM2 ?c ; lulcw:coveredFraction ?f }""")}
    assert cov == {("W1", "A"): (1.0e6, 1.0e6, 1.0), ("W1", "X"): (1.0e6, 8.0e5, 0.8),
                   ("W7", "X"): (1.0e6, 8.0e5, 0.8), ("W8", "A"): (1.0e6, 1.0e6, 1.0),
                   ("forcing-cells", "Y"): (1.0e6, 1.0e6, 1.0)}, cov   # B, C: not at outcrop
    wts = {(s.rsplit("/", 1)[-1], u.rsplit("/", 1)[-1], c.rsplit("/", 1)[-1]): (w, a) for s, u, c, w, a in select(g, """
        SELECT ?s ?u ?c ?w ?a WHERE { ?v lulcw:withinExtent ?s ; lulcw:coverageUnit ?u ; lulcw:hasCellWeight ?x .
            ?x lulcw:weightCell ?c ; lulcw:cellWeight ?w ; lulcw:coveredAreaM2 ?a }""")}
    want = {(s, "A", "c1"): (0.6, 6.0e5) for s in ("W1", "W8")} | {(s, "A", "c2"): (0.4, 4.0e5) for s in ("W1", "W8")} | \
           {(s, "X", "c1"): (0.625, 5.0e5) for s in ("W1", "W7")} | {(s, "X", "c2"): (0.375, 3.0e5) for s in ("W1", "W7")} | \
           {("forcing-cells", "Y", "c2"): (1.0, 1.0e6)}
    assert wts.keys() == want.keys() and all(abs(wts[k][0] - w) < 1e-12 and wts[k][1] == a
                                             for k, (w, a) in want.items()), wts
    cited = {(s.rsplit("/", 1)[-1], u.rsplit("/", 1)[-1]): int(n) for s, u, n in select(g, """SELECT ?s ?u (COUNT(?x) AS ?n) WHERE {
        ?v a lulcw:OutcropCoverage ; lulcw:withinExtent ?s ; lulcw:coverageUnit ?u ; prov:wasDerivedFrom ?x } GROUP BY ?s ?u""")}
    assert cited == {("W1", "A"): 2, ("W1", "X"): 3, ("W7", "X"): 3, ("W8", "A"): 2,
                     ("forcing-cells", "Y"): 1}, cited             # every piece, the outside one too

    # CQ5: river-unit associations, the statements that apply, the river influences
    assoc = {(z.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1], u_.rsplit("/", 1)[-1], t_.split("#")[-1]): (lo, lc, cv)
             for z, w, u_, t_, lo, lc, cv in select(g, """SELECT ?z ?wc ?u ?t ?lo ?lc (GROUP_CONCAT(STR(?c)) AS ?cv) WHERE {
                 ?a a lulcw:RiverUnitAssociation ; lulcw:withinExtent ?z ; lulcw:associationWatercourse ?wc ;
                    lulcw:associationUnit ?u ; lulcw:associationType ?t .
                 OPTIONAL { ?a lulcw:lengthOnOutcropM ?lo } OPTIONAL { ?a lulcw:lengthOverCoverM ?lc }
                 OPTIONAL { ?a lulcw:coverUnit ?c } } GROUP BY ?z ?wc ?u ?t ?lo ?lc""")}
    assert set(assoc) == {("R1", "WC1", "X", "OnOutcrop"), ("R2", "WC2", "Z", "OverCover"),
                          ("R3", "WC1", "B", "DocumentedLateral"), ("R4", "WC1", "X", "OnOutcrop"),
                          ("R5", "WC1", "X", "OnOutcrop"), ("R6", "WC3", "A", "OnOutcrop"),
                          ("R7", "WC1", "X", "OnOutcrop"), ("R10", "WC4", "X", "OnOutcrop"),
                          ("R11", "WC4", "X", "OnOutcrop"), ("R12", "WC4", "X", "OnOutcrop")}, assoc
    # R9: S7 is about an aggregate holding B, which locates nothing (no documented lateral); R8: only
    # off-map pieces
    assert assoc[("R1", "WC1", "X", "OnOutcrop")][0] == 1500.0          # the canal piece is not a river
    assert assoc[("R4", "WC1", "X", "OnOutcrop")][0] == 900.0           # the off-map piece is not counted
    assert assoc[("R7", "WC1", "X", "OnOutcrop")][0] == 500.0
    assert assoc[("R2", "WC2", "Z", "OverCover")][1:] == (1200.0, str(u["Y"])), assoc
    applies = {(a_.split("/reach-zone/")[1].split("/")[0], s.rsplit("/", 1)[-1]) for a_, s in select(
        g, "SELECT ?a ?s WHERE { ?a a lulcw:RiverUnitAssociation ; lulcw:applicableStatement ?s }")}
    assert applies == {("R1", "S1"), ("R3", "S2"), ("R5", "S3"), ("R5", "S4"), ("R7", "S1"),
                       ("R10", "S8"), ("R10", "S9"), ("R11", "S8"), ("R11", "S10"),
                       ("R12", "S8"), ("R12", "S11")}, applies   # S5: not delimited; S7: an aggregate
    localised = {(a_.split("/reach-zone/")[1].split("/")[0], s_.rsplit("/", 1)[-1], k.split("#")[-1]) for a_, s_, k in select(
        g, "SELECT ?a ?s ?k WHERE { ?a lulcw:localizedStatement ?s ; a ?k }")}
    assert localised == {("R1", "S7", "RiverUnitAssociation"), ("R7", "S7", "RiverUnitAssociation"),
                         ("R1", "C3", "CanalUnitAssociation"), ("R6", "C3", "CanalUnitAssociation"),
                         ("R7", "C3", "CanalUnitAssociation")}, localised
    rivers = {(w.rsplit("/", 1)[-1], gg.rsplit("/", 1)[-1]): (sg.split("#")[-1], e.split("#")[-1]) for w, gg, sg, e in select(
        g, """SELECT ?w ?g ?s ?e WHERE { ?i lulcw:mechanism lulcw:RiverExchange ; lulcw:targetEntity ?w ;
              lulcw:driverEntity ?g ; lulcw:responseSign ?s ; lulcw:constraintEligibility ?e }""")}
    assert rivers == {("R1", "G1"): ("PositiveResponse", "EligibleConstraint"),       # G3 nearer, not in the pool
                      ("R2", "G4"): ("UnknownResponse", "IneligibleConstraint"),      # over cover
                      ("R3", "G2"): ("PositiveResponse", "EligibleConstraint"),       # documented lateral
                      ("R4", "G1"): ("PositiveResponse", "IneligibleConstraint"),     # geometric only
                      ("R5", "G1"): ("PositiveResponse", "IneligibleConstraint"),     # independence stated
                      ("R7", "G1"): ("PositiveResponse", "EligibleConstraint")}, rivers   # S1, about X itself
    # (R6, R10-R12: WC3 and WC4 have no pool gauge, so no influence)
    # CQ6: canal-unit associations and canal influences
    canal = {(z.rsplit("/", 1)[-1], u_.rsplit("/", 1)[-1]): ln for z, u_, ln in select(
        g, "SELECT ?z ?u ?l WHERE { ?c a lulcw:CanalUnitAssociation ; lulcw:withinExtent ?z ; lulcw:associationUnit ?u ; lulcw:lengthOnOutcropM ?l }")}
    assert canal == {("R1", "X"): 800.0, ("R6", "A"): 400.0, ("R7", "X"): 300.0,
                     ("R13", "M"): 350.0, ("R14", "M"): 450.0}, canal   # R8's canal is off the map
    capp = {(a_.split("/reach-zone/")[1].split("/")[0], s_.rsplit("/", 1)[-1]) for a_, s_ in select(
        g, "SELECT ?a ?s WHERE { ?a a lulcw:CanalUnitAssociation ; lulcw:applicableStatement ?s }")}
    assert capp == {("R1", "C1"), ("R1", "C4"), ("R6", "C2"), ("R7", "C1"),
                    ("R13", "C5"), ("R14", "C6")}, capp   # C4 measured at R1, C5 at R13, C6 at R14
    cinf = {w.rsplit("/", 1)[-1]: e.split("#")[-1] for w, e in select(
        g, "SELECT ?w ?e WHERE { ?i lulcw:mechanism lulcw:CanalReturnFlow ; lulcw:targetEntity ?w ; lulcw:constraintEligibility ?e }")}
    assert cinf == {"R1": "EligibleConstraint", "R6": "IneligibleConstraint",       # C2 synthesis; C3 aggregate
                    "R7": "EligibleConstraint",                                     # C1 differential gauging
                    "R13": "IneligibleConstraint",                                  # C5 stated synthesis only
                    "R14": "EligibleConstraint"}, cinf                              # C6 hedged differential gauging
    rsel = {(w.rsplit("/", 1)[-1], p.rsplit("/", 1)[-1]) for w, p in select(
        g, "SELECT ?w ?p WHERE { ?i lulcw:mechanism lulcw:RiverExchange ; lulcw:targetEntity ?w ; lulcw:selectedUnder ?p }")}
    assert rsel == {(w, p) for w in ("R1", "R2", "R3", "R4", "R5", "R7") for p in ("main", "confident-only", "all-links")}, rsel

    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results
    infos = sum(n for k, n in results.items() if k.startswith("Info"))
    assert infos == 1, results                                    # W2's missing depth
    print(f"  2. fixtures: CQ3, CQ11, CQ8 (pumping, recharge proxies, rivers, canals), CQ2, CQ7, CQ4, CQ5 and CQ6 cases hold; "
          f"{len(added)} derived triples; no violation, 1 info (the missing depth)")
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
        "a code area that no class area counts": (
            [], [(d("crop-class-area/W1/2023/orchard"), PROV.wasDerivedFrom, d("crop-area/W1/2023/PEC"))],
            "CropAreaObservationShape", "exactly one class area"),
        "a code area counted by two class areas": (
            [(d("crop-class-area/W1/2023/citrus"), PROV.wasDerivedFrom, d("crop-area/W1/2023/PEC"))], (),
            "CropAreaObservationShape", "exactly one class area"),
        "two class areas for one zone, year and class": (
            [(d("crop-class-area/W1/2023/orchard-bis"), RDF.type, L.CropClassArea),
             (d("crop-class-area/W1/2023/orchard-bis"), SOSA.hasFeatureOfInterest, d("zone/W1")),
             (d("crop-class-area/W1/2023/orchard-bis"), L.rpgEdition, Literal(2023, datatype=XSD.integer)),
             (d("crop-class-area/W1/2023/orchard-bis"), L.cropClass, d("crop-class/orchard"))], (),
            "CropClassAreaKeyShape", "share a zone"),
    }
    # CQ4: coverages and weights of the fixture (A, X in the search zone of W1; Y in the forcing extent)
    zone, cov_a = d("outcrop-zone/W1"), d("outcrop-zone/W1/outcrop-coverage/A")
    cov_x, cov_y = d("outcrop-zone/W1/outcrop-coverage/X"), d("extent/forcing-cells/outcrop-coverage/Y")
    dbl = lambda v: Literal(v, datatype=XSD.double)  # noqa: E731

    def now(s, p):
        return list(g.triples((s, p, None)))

    def piece(key, poly, cell, m2):
        x = d(f"polygon-cell/zone/{poly}/{key}")
        return [(x, RDF.type, L.PolygonCellIntersection), (x, L.intersectedPolygon, d(f"polygon/{poly}")),
                (x, L.withinExtent, zone), (x, L.intersectionAreaM2, dbl(m2)),
                (x, PROV.wasGeneratedBy, d("execution/polygon-cell-intersection"))] + \
               ([(x, L.intersectedCell, d(f"weather-cell/{cell}"))] if cell else [])
    cases |= {
        "cell weights that do not sum to one": (
            [(d("outcrop-zone/W1/outcrop-coverage/A/c1"), L.cellWeight, dbl(0.7))],
            now(d("outcrop-zone/W1/outcrop-coverage/A/c1"), L.cellWeight),
            "OutcropCoverageShape", "do not sum to one"),
        "pieces of a polygon larger than the polygon": (
            piece("outside", 1, None, 1.0e4), (), "PolygonCellIntersectionKeyShape", "exceed the polygon's area"),
        "two pieces for one polygon, extent and cell": (
            piece("c1-bis", 1, "c1", 1.0), (), "PolygonCellIntersectionKeyShape", "share a polygon"),
        "a piece under 1 m²": (
            [(d("polygon-cell/zone/2/outside"), L.intersectionAreaM2, dbl(0.5))],
            now(d("polygon-cell/zone/2/outside"), L.intersectionAreaM2),
            "PolygonCellIntersectionShape", "sliver"),
        "a coverage citing a piece of another extent": (
            [(cov_y, PROV.wasDerivedFrom, d("polygon-cell/zone/1/c1"))], (),
            "OutcropCoverageShape", "from another extent"),
        "a covered fraction that is not covered / outcrop": (
            [(cov_x, L.coveredFraction, dbl(0.9))], now(cov_x, L.coveredFraction),
            "OutcropCoverageShape", "covered fraction is not"),
        "a cell weight outside any coverage": (
            [(d("cell-weight/orphan"), RDF.type, L.CellWeight), (d("cell-weight/orphan"), L.weightCell, d("weather-cell/c1")),
             (d("cell-weight/orphan"), L.cellWeight, dbl(0.5)), (d("cell-weight/orphan"), L.coveredAreaM2, dbl(1.0))], (),
            "CellWeightShape", "exactly one outcrop coverage"),
        "a coverage larger than the unit's whole mapped outcrop": (
            [(d("unit/Y"), L.mappedOutcropAreaM2, dbl(5.0e5))], now(d("unit/Y"), L.mappedOutcropAreaM2),
            "MappedOutcropShape", "exceeds the unit's whole mapped outcrop"),
        "two coverages for one extent and unit": (
            [(d(str(cov_a)[len(D):] + "-bis"), RDF.type, L.OutcropCoverage),
             (d(str(cov_a)[len(D):] + "-bis"), L.withinExtent, zone),
             (d(str(cov_a)[len(D):] + "-bis"), L.coverageUnit, d("unit/A"))], (),
            "OutcropCoverageKeyShape", "share an extent and a unit"),
    }
    # CQ4, CQ8: the recharge proxies of W7 (local, c1 and c2) and W8 (unit-wide, c2)
    r7 = d("influence/recharge/local/c1/to/W7/1")
    r8 = d("influence/recharge/unit-wide/c2/to/W8/1")
    twin = d("influence/recharge/local/c1/to/W7/1/drainage")
    cases |= {
        "a recharge proxy that does not name the pathways it omits": (
            [], now(r7, L.omitsPathway), "InfluenceShape", "the pathways it omits"),
        "a second proxy of the same surplus on one path": (
            [(twin, p, o) for _, p, o in g.triples((r7, None, None)) if p != L.driverVariable]
            + [(twin, L.driverVariable, L.SoilDrainage)], (),
            "RechargeInfluenceKeyShape", "one water surplus counted twice"),
        "a missing recharge proxy (a derivation not run or stale)": (
            [], list(g.triples((r7, None, None))), "RechargeInfluenceKeyShape", "in the well's search zone has no"),
        "a missing unit-wide recharge proxy": (
            [], list(g.triples((r8, None, None))), "RechargeInfluenceKeyShape", "in a fixed extent of the rule has no"),
        "a recharge proxy resting on another well's attribution": (
            [(r7, PROV.wasDerivedFrom, d("attribution/piezometer/W1/1"))],
            [(r7, PROV.wasDerivedFrom, d("attribution/piezometer/W7/1"))],
            "InfluenceShape", "does not join the weather cell"),
        "a recharge proxy whose driver is not a water-surplus proxy": (
            [(r7, L.driverVariable, L.ReconstructedWeeklyVolume)], now(r7, L.driverVariable),
            "InfluenceShape", "not effective rainfall or soil drainage"),
        "a recharge proxy in another well's search zone": (
            [(r7, L.withinExtent, zone)], now(r7, L.withinExtent),
            "InfluenceShape", "neither the target well's search zone"),
        "a diffuse-recharge influence carrying viaUnit": (
            [(r7, L.viaUnit, d("unit/A"))], (),
            "InfluenceShape", "must not carry viaUnit"),
    }

    # CQ5, CQ6: the river and canal fixture (wells R1-R6)
    a1 = d("reach-zone/R1/river/WC1/X/on-outcrop")
    a3 = d("reach-zone/R3/river/WC1/B/documented-lateral")
    i1, i2 = d("influence/river/on-outcrop/G1/to/R1/1"), d("influence/river/over-cover/G4/to/R2/1")
    i4 = d("influence/river/on-outcrop/G1/to/R4/1")
    c1, c6, c13 = (d("influence/canal/plain/to/R1/1"), d("influence/canal/plain/to/R6/1"),
                   d("influence/canal/plain/to/R13/1"))
    twin_r = d("influence/river/on-outcrop/G2/to/R1/1")
    elig = lambda i: ([(i, L.constraintEligibility, L.EligibleConstraint)], now(i, L.constraintEligibility))  # noqa: E731
    cases |= {
        "a missing on-outcrop river association (a derivation not run or stale)": (
            [], list(g.triples((a1, None, None))), "RiverAssociationKeyShape", "no on-outcrop association exists"),
        "an eligible river influence over cover": (
            *elig(i2), "RiverCanalInfluenceShape", "over cover carries a supported sign or is eligible"),
        "an eligible river influence without a documented exchange": (
            *elig(i4), "RiverCanalInfluenceShape", "no applicable statement documenting the exchange"),
        "a river influence from a gauge outside the pool": (
            [(i1, L.driverEntity, d("gauge/G3"))], now(i1, L.driverEntity),
            "RiverCanalInfluenceShape", "does not join the gauge to the well"),
        "two river influences for one association and attribution": (
            [(twin_r, p_, o) for _, p_, o in g.triples((i1, None, None)) if p_ != L.driverEntity]
            + [(twin_r, L.driverEntity, d("gauge/G2"))], (),
            "RiverInfluenceKeyShape", "share an association and a well attribution"),
        "a missing river influence": (
            [], list(g.triples((i1, None, None))), "RiverInfluenceKeyShape", "has no influence for an attribution"),
        "a river piece in a section of another watercourse": (
            [(d("reach-piece/R2/r2/3"), L.inSection, d("water-body/FRDRT1"))], (),
            "ReachPieceKeyShape", "not a stretch of its watercourse"),
        "a statement without its passage": (
            [], [(d("exchange-statement/S1"), PROV.wasDerivedFrom, d("passage/S1"))],
            "ExchangeStatementShape", None),
        "an eligible canal influence on a synthesis statement": (
            *elig(c13), "RiverCanalInfluenceShape", "rests on no measured or traced canal-return statement about its unit"),
        "a canal-return statement about a river section": (
            [(d("exchange-statement/C1"), L.aboutSection, d("water-body/FRDRT1"))], (),
            "ExchangeStatementShape", "names a river section"),
        "a distance along the river off the main stem": (
            [(d("gauge-zone/R3/G3"), L.alongRiverDistanceM, Literal(10.0, datatype=XSD.double))], (),
            "GaugeZoneRelationShape", "along the river is given off the main stem"),
        "a canal reach typed as a river reach": (
            [(d("reach/k1"), RDF.type, L.RiverReach)], (), "RiverReachShape", None),
        "a documented lateral association without its statement": (
            [], [(a3, L.applicableStatement, d("exchange-statement/S2"))],
            "RiverUnitAssociationShape", "documented lateral association has no applicable statement"),
        "a river association whose unit is not the well's": (
            [(a1, L.associationUnit, d("unit/Z"))], now(a1, L.associationUnit),
            "RiverUnitAssociationShape", "not the candidate unit of a monitoring attribution"),
        "a missing canal influence": (
            [], list(g.triples((c1, None, None))), "CanalInfluenceKeyShape", "has no influence for an attribution"),
        # Codex review of 2026-11-06: aggregates, measurements at a site, constraint decisions
        "a statement about a unit both itself and as an aggregate member": (
            [(d("exchange-statement/S7"), L.aboutUnit, d("unit/X"))], (), "ExchangeStatementShape", "both itself and as an aggregate"),
        "an aggregate of one unit": (
            [], [(d("exchange-statement/S7"), L.aggregateMemberUnit, d("unit/B"))], "ExchangeStatementShape",
            "an aggregate of fewer than two units"),
        "a statement without its method": (
            [], [(d("exchange-statement/S1"), L.evidenceMethod, L.SynthesisStatement)], "ExchangeStatementShape", None),
        "a measurement at a site that is not about a unit itself": (
            [(d("exchange-statement/C3"), L.measuredAt, d("piezometer/R6"))], (), "ExchangeStatementShape",
            "measured at a site is not about a unit itself"),
        "an aggregate statement applied as evidence about the unit itself": (
            [(a1, L.applicableStatement, d("exchange-statement/S7"))], (), "ApplicableStatementShape",
            "not about the association's unit itself"),
        "a measurement at R1 applied to another well's canal association": (
            [(d("reach-zone/R7/canal/X"), L.applicableStatement, d("exchange-statement/C4"))], (),
            "ApplicableStatementShape", "measured at a site outside the association's zone"),
        "an aggregate statement localised to a documented lateral association": (
            [(a3, L.localizedStatement, d("exchange-statement/S7"))], (), "LocalizedStatementShape", "not on outcrop"),
        "a missing localisation of an aggregate statement": (
            [], [(a1, L.localizedStatement, d("exchange-statement/S7"))], "RiverAssociationKeyShape",
            "is not localised to that on-outcrop association"),
        "a missing localisation of an aggregate canal statement": (
            [], [(d("reach-zone/R6/canal/A"), L.localizedStatement, d("exchange-statement/C3"))], "CanalInfluenceKeyShape",
            "is not localised to it"),
        "a canal influence made eligible by an aggregate statement alone": (
            *elig(c6), "RiverCanalInfluenceShape", "rests on no measured or traced canal-return statement about its unit"),
        "a constraint approved while its proxy is pending": (
            [(d("constraint-decision/RiverExchange"), L.constraintApproval, L.AcceptedStatus)],
            now(d("constraint-decision/RiverExchange"), L.constraintApproval), "ConstraintDecisionShape",
            "approved although its driver is not accepted as a proxy"),
        "a policy without a decision for a mechanism of its influences": (
            [], [(d("policy/main"), L.constraintDecision, d("constraint-decision/CanalReturnFlow"))],
            "ExportPolicyDecisionShape", "no constraint decision for a mechanism"),
    }

    for name, (add, remove, shape, text) in cases.items():
        res = bad(add, remove)
        assert violations(res, shape, text) > 0, f"{name}: not caught\n{res}"
    print(f"  3. negative controls: all {len(cases)} inserted errors are reported as violations")


def build_leakage_fixture():
    """Overlying-leakage recharge fixture (T65):
      (a) WL1 in polygon P1 [A > U], attributed to U (Confident), A's outcrop in its zone over two
          cells (0.7 / 0.3) -> 2 VerticalLeakage influences via A with weights 0.7 and 0.3;
      (b) WL2 in polygon P1 [A > U], attributed to A (Probable, top of stack) -> 0 leakage influences
          (only local DiffuseRecharge);
      (c) WL3 in polygon P2 [A > B > U], attributed to U (Probable), both A and B at outcrop in its
          zone -> 2 leakage influences via B only (direct contact), never via A;
      (d) WL4 attributed to U (Confident), without locatedInPolygon, A at outcrop in its zone -> 0.
    """
    fx = Fixture()
    a = fx.g.add
    A, B, U = (fx.unit(c) for c in ("LA", "LB", "LU"))
    for u, m2 in ((A, 1.0e6), (B, 1.0e6), (U, 0.0)):
        a((u, PROV.wasDerivedFrom, fx.rel))
        a((u, L.mappedOutcropAreaM2, Literal(m2, datatype=XSD.double)))
    p1 = fx.polygon(101, [A, U])
    p2 = fx.polygon(102, [A, B, U])
    p3 = fx.polygon(103, [B])
    p4 = fx.polygon(104, [A])
    for k, (gx, gy) in {"c1": (100, 200), "c2": (180, 200)}.items():
        c = d(f"weather-cell/{k}")
        a((c, RDF.type, L.WeatherCell))
        a((c, L.safranGridXHm, Literal(gx, datatype=XSD.integer)))
        a((c, L.safranGridYHm, Literal(gy, datatype=XSD.integer)))
        a((c, L.inRelease, fx.rel))
        fx.geometry(c, "weather-cell", k, "POLYGON((0 0, 8000 0, 8000 8000, 0 8000, 0 0))")
        se = d(f"series/forcing-leak/{k}/PE")
        a((se, RDF.type, L.ObservationSeries))
        a((se, L.seriesVariable, L.EffectiveRainfall))
        a((se, L.storedIn, Literal(f"forcing_weekly.parquet [cell_id = {k}, column PE]")))
        a((c, L.hasForcingSeries, se))
    wl1 = fx.well("WL1", 0, 0, U, L.Confident, depth=50)
    wl2 = fx.well("WL2", 20000, 0, A, L.Probable, depth=15)
    wl3 = fx.well("WL3", 40000, 0, U, L.Probable, depth=80)
    wl4 = fx.well("WL4", 60000, 0, U, L.Confident, depth=60)
    a((d("extent/forcing-cells"), RDF.type, GEO.Feature))
    a((wl1, L.locatedInPolygon, p1))
    a((wl2, L.locatedInPolygon, p1))
    a((wl3, L.locatedInPolygon, p2))
    # WL4 deliberately has no locatedInPolygon
    zones = {}
    for key, w in (("WL1", wl1), ("WL2", wl2), ("WL3", wl3), ("WL4", wl4)):
        z = zones[key] = d(f"outcrop-zone/{key}")
        a((z, RDF.type, L.OutcropSearchZone))
        a((z, L.zoneOf, w))
        a((z, L.zoneRadiusM, Literal(RADIUS, datatype=XSD.double)))
    pieces = (("WL1", 104, "c1", 7.0e5), ("WL1", 104, "c2", 3.0e5),
              ("WL2", 104, "c1", 6.0e5), ("WL2", 104, "c2", 4.0e5),
              ("WL3", 104, "c1", 6.0e5), ("WL3", 104, "c2", 4.0e5),
              ("WL3", 103, "c1", 2.5e5), ("WL3", 103, "c2", 7.5e5),
              ("WL4", 104, "c1", 5.0e5), ("WL4", 104, "c2", 5.0e5))
    for key, poly, cell, m2 in pieces:
        x = d(f"polygon-cell/{key}/{poly}/{cell}")
        a((x, RDF.type, L.PolygonCellIntersection))
        a((x, L.intersectedPolygon, d(f"polygon/{poly}")))
        a((x, L.withinExtent, zones[key]))
        a((x, L.intersectedCell, d(f"weather-cell/{cell}")))
        a((x, L.intersectionAreaM2, Literal(m2, datatype=XSD.double)))
        a((x, PROV.wasGeneratedBy, d("execution/polygon-cell-intersection")))
    return fx


def test_leakage_fixture(rules, shapes, net):
    fx = build_leakage_fixture()
    facts = fx.g
    records = rule_records(rules, "test", facts)
    added = run_rules(facts, rules, records)
    g = facts + records + added

    leak = {}
    for c, w, v, wt, sign, elig, var, q, conf, grp, res, n_om, cond in select(g, """
            SELECT ?c ?w ?v ?wt ?sign ?elig ?var ?q ?conf ?grp ?res (COUNT(DISTINCT ?om) AS ?n) ?cond WHERE {
            ?i a lulcw:Influence ; lulcw:mechanism lulcw:VerticalLeakage ; lulcw:driverEntity ?c ;
               lulcw:targetEntity ?w ; lulcw:viaUnit ?v ; lulcw:responseSign ?sign ;
               lulcw:constraintEligibility ?elig ; lulcw:driverVariable ?var ; lulcw:proxyFor ?q ;
               lulcw:confidence ?conf ; lulcw:driverGroup ?grp ; lulcw:resolution ?res ;
               lulcw:omitsPathway ?om ; lulcw:conditions ?cond ; prov:wasDerivedFrom ?cw .
            ?cw lulcw:cellWeight ?wt . }
            GROUP BY ?c ?w ?v ?wt ?sign ?elig ?var ?q ?conf ?grp ?res ?cond"""):
        leak[(c.rsplit("/", 1)[-1], w.rsplit("/", 1)[-1], v.rsplit("/", 1)[-1])] = (
            round(wt, 6), *(x.split("#")[-1] for x in (sign, elig, var, q, conf, grp, res)), n_om, cond)
    same = ("PositiveResponse", "EligibleConstraint", "EffectiveRainfall", "GroundwaterRecharge")
    assert {k: v[:5] for k, v in leak.items()} == {
        ("c1", "WL1", "LA"): (0.7, *same), ("c2", "WL1", "LA"): (0.3, *same),
        ("c1", "WL3", "LB"): (0.25, *same), ("c2", "WL3", "LB"): (0.75, *same),
    }, leak
    assert all(v[5:9] == (("Confident" if k[1] == "WL1" else "Probable"), "RechargeProxies",
                          "ExactUnitResolution", 3) for k, v in leak.items()), leak
    # WL2 (top of stack) and WL4 (no locatedInPolygon) get no leakage; WL3 never via LA
    assert not any(w in ("WL2", "WL4") or (w == "WL3" and v == "LA") for _, w, v in leak), leak
    # Policy selection (order 90): WL1 confident (all 3), WL3 probable (main and all-links only)
    lsel = {(w.rsplit("/", 1)[-1], p.rsplit("/", 1)[-1]) for w, p in select(g, """SELECT ?w ?p WHERE {
        ?i lulcw:mechanism lulcw:VerticalLeakage ; lulcw:targetEntity ?w ; lulcw:selectedUnder ?p }""")}
    assert lsel == {("WL1", "main"), ("WL1", "confident-only"), ("WL1", "all-links"),
                    ("WL3", "main"), ("WL3", "all-links")}, lsel
    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results

    # Negative controls for the new leakage / viaUnit shapes
    def bad(triples, remove=()):
        h = rdflib.Graph()
        for t in g:
            if t not in remove:
                h.add(t)
        for t in triples:
            h.add(t)
        return check(h, shapes, net)[2]

    def now(s, p):
        return list(g.triples((s, p, None)))

    i1 = d("influence/recharge/leakage/c1/via/LA/to/WL1/1")
    i3 = d("influence/recharge/leakage/c1/via/LB/to/WL3/1")
    r2 = d("influence/recharge/local/c1/to/WL2/1")
    twin = d("influence/recharge/leakage/c1/via/LA/to/WL1/1/drainage")
    neg = {
        "vertical leakage without viaUnit": (
            [], now(i1, L.viaUnit), "InfluenceShape", "distinct from its attributed unit"),
        "vertical leakage with viaUnit equal to its attributed unit": (
            [(i1, L.viaUnit, d("unit/LU"))], now(i1, L.viaUnit),
            "InfluenceShape", "distinct from its attributed unit"),
        "vertical leakage with two viaUnits": (
            [(i1, L.viaUnit, d("unit/LB"))], (), "InfluenceShape", None),
        "diffuse recharge with viaUnit": (
            [(r2, L.viaUnit, d("unit/LA"))], (), "InfluenceShape", "must not carry viaUnit"),
        "vertical leakage via an indirect (non-direct-contact) upper unit": (
            [(i3, L.viaUnit, d("unit/LA"))], now(i3, L.viaUnit), "InfluenceShape", "direct contact above"),
        "vertical leakage without omitted pathways": (
            [], now(i1, L.omitsPathway), "InfluenceShape", "the pathways it omits"),
        "second vertical-leakage proxy of the same surplus on one path": (
            [(twin, p, o) for _, p, o in g.triples((i1, None, None)) if p != L.driverVariable]
            + [(twin, L.driverVariable, L.SoilDrainage)], (),
            "RechargeInfluenceKeyShape", "one water surplus counted twice"),
        "missing vertical-leakage influence": (
            [], list(g.triples((i1, None, None))),
            "RechargeInfluenceKeyShape", "has no vertical-leakage recharge influence"),
    }
    for name, (add, remove, shape, text) in neg.items():
        res = bad(add, remove)
        assert violations(res, shape, text) > 0, f"{name}: not caught\n{res}"
    print(f"  3b. leakage fixture: cases (a)-(d) and policy selection hold, 0 violations; "
          f"all {len(neg)} leakage/viaUnit negative controls caught")
    return g


def build_cq15_fixture(ndvi_threshold=0.50, validity=L.HeuristicRule):
    """CQ15 synthetic fixture covering every outcome and acceptance case:
      - P_POS:        NDVI 0.65, 10 px, 5.0 obs, dry cell c1 (SWI 0.30) -> ProbablyIrrigated
      - P_NEG:        NDVI 0.35, 10 px, 5.0 obs, dry cell c1 (SWI 0.30) -> NotProbablyIrrigated
      - P_LOW_PX:     NDVI 0.80,  3 px (< 4), 5.0 obs, dry c1 -> InsufficientSatelliteData
      - P_LOW_OBS:    NDVI 0.80, 10 px, 2.5 obs (< 3), dry c1 -> InsufficientSatelliteData
      - P_ZERO_PX:    0 px, no NDVI, no obs, dry c1           -> InsufficientSatelliteData
      - P_WET:        NDVI 0.80, 10 px, 5.0 obs, wet cell c2 (SWI 0.65) -> WetSeason
      - P_WET_LOW_PX: NDVI 0.80,  2 px (< 4), 5.0 obs, wet c2 -> InsufficientSatelliteData (quality first)
      - P_NO_SWI:     NDVI 0.80, 10 px, 5.0 obs, cell c3 (no SWI obs)   -> InsufficientSatelliteData
      - zone/W1 has an irrigation facility F_IRR nearby (500 m) and a canal association (never a parcel link)
      - zone/W2 has P_NOSUP (high NDVI, dry, sufficient quality) and NO supply context at all, plus a
        zero-classified-area share observation in 2021 (unbound result, never 0)
    """
    fx = Fixture()
    a = fx.g.add
    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    U = fx.unit("U1")
    a((U, PROV.wasDerivedFrom, fx.rel))
    a((U, L.mappedOutcropAreaM2, dbl(1.0e6)))
    p1 = fx.polygon(201, [U])
    w1 = fx.well("W1", 0, 0, U, L.Confident, depth=20)
    w2 = fx.well("W2", 50000, 0, U, L.Confident, depth=25)
    a((d("extent/forcing-cells"), RDF.type, GEO.Feature))
    a((w1, L.locatedInPolygon, p1))
    a((w2, L.locatedInPolygon, p1))
    # Nearby irrigation pump for W1 (500 m away; supply context only, never linked to any parcel)
    f_irr = fx.facility("F_IRR", 500, 0, U, L.Confident)
    iv2020 = d("interval/year/2020")
    a((iv2020, RDF.type, TIME.ProperInterval))
    b2020 = d("instant/2020-01-01")
    a((b2020, RDF.type, TIME.Instant))
    a((b2020, TIME.inXSDDate, Literal("2020-01-01", datatype=XSD.date)))
    a((iv2020, TIME.hasBeginning, b2020))
    rec = d("abstraction/F_IRR/2020/IRR")
    for p, v in ((RDF.type, L.AnnualAbstractionRecord), (SOSA.hasFeatureOfInterest, f_irr),
                 (SOSA.observedProperty, L.DeclaredAnnualVolume), (SOSA.hasSimpleResult, dbl(50000.0)),
                 (SOSA.phenomenonTime, iv2020), (L.waterUse, L.IrrigationUse),
                 (L.waterSource, L.GroundwaterSource), (L.recordKind, L.DeclaredRecord),
                 (L.inRelease, fx.rel)):
        a((rec, p, v))
    # Zones and crop code
    scheme = d("crop-code-scheme/rpg")
    a((scheme, RDF.type, SKOS.ConceptScheme))
    cc = d("crop-code/PEC")
    for p, v in ((RDF.type, L.CropCode), (SKOS.inScheme, scheme), (SKOS.notation, Literal("PEC")),
                 (SKOS.prefLabel, Literal("Pêchers", lang="fr")),
                 (L.rpgGroupCode, Literal(20, datatype=XSD.integer))):
        a((cc, p, v))
    z1, z2 = d("zone/W1"), d("zone/W2")
    for z, w in ((z1, w1), (z2, w2)):
        a((z, RDF.type, L.CropDemandZone))
        a((z, L.zoneOf, w))
        a((z, L.zoneRadiusM, dbl(3000.0)))
    # Weather cells and summer SWI observations
    for k, gx in (("c1", 100), ("c2", 180), ("c3", 260)):
        c = d(f"weather-cell/{k}")
        a((c, RDF.type, L.WeatherCell))
        a((c, L.safranGridXHm, Literal(gx, datatype=XSD.integer)))
        a((c, L.safranGridYHm, Literal(200, datatype=XSD.integer)))
        a((c, L.inRelease, fx.rel))
        fx.geometry(c, "weather-cell", k, "POLYGON((0 0, 8000 0, 8000 8000, 0 8000, 0 0))")
        se = d(f"series/forcing-cq15/{k}/PE")
        a((se, RDF.type, L.ObservationSeries))
        a((se, L.seriesVariable, L.EffectiveRainfall))
        a((c, L.hasForcingSeries, se))
    iv_s = d("interval/summer/2020")
    a((iv_s, RDF.type, TIME.ProperInterval))
    for k, swi in (("c1", 0.30), ("c2", 0.65)):
        so = d(f"summer-swi/{k}/2020")
        for p, v in ((RDF.type, SOSA.Observation), (SOSA.hasFeatureOfInterest, d(f"weather-cell/{k}")),
                     (SOSA.observedProperty, L.SummerSoilWetness), (SOSA.phenomenonTime, iv_s),
                     (L.seasonYear, Literal(2020, datatype=XSD.integer)),
                     (SOSA.hasSimpleResult, dbl(swi))):
            a((so, p, v))
    # Rule individual (thresholds read from the graph, never hard-coded in SPARQL)
    rule = d("rule/probable-irrigation")
    for p, v in ((RDF.type, L.DerivationRule), (RDFS.comment, Literal("CQ15 fixture rule", lang="en")),
                 (L.ruleVersion, Literal("fixture-v1")), (L.ndviThreshold, dbl(ndvi_threshold)),
                 (L.minValidPixels, Literal(4, datatype=XSD.integer)),
                 (L.minMeanClearAcquisitions, dbl(3.0)), (L.maxSoilWetness, dbl(0.50)),
                 (L.trainingEdition, Literal(2017, datatype=XSD.integer)),
                 (L.trainingEdition, Literal(2018, datatype=XSD.integer)),
                 (L.ruleValidity, validity)):
        a((rule, p, v))
    # Parcels, overlaps, and summer NDVI observations
    # (pid, zone, cell, ndvi, npx, nobs, area_m2)
    parcel_specs = (
        ("P_POS", z1, "c1", 0.65, 10, 5.0, 20000.0),
        ("P_NEG", z1, "c1", 0.35, 10, 5.0, 20000.0),
        ("P_LOW_PX", z1, "c1", 0.80, 3, 5.0, 10000.0),
        ("P_LOW_OBS", z1, "c1", 0.80, 10, 2.5, 10000.0),
        ("P_ZERO_PX", z1, "c1", None, 0, None, 10000.0),
        ("P_WET", z1, "c2", 0.80, 10, 5.0, 10000.0),
        ("P_WET_LOW_PX", z1, "c2", 0.80, 2, 5.0, 10000.0),
        ("P_NO_SWI", z1, "c3", 0.80, 10, 5.0, 10000.0),
        ("P_NOSUP", z2, "c1", 0.75, 12, 6.0, 30000.0),
    )
    for pid, z, cid, ndvi, npx, nobs, area in parcel_specs:
        pn = d(f"parcel/2020/{pid}")
        for p, v in ((RDF.type, L.RegisteredParcel), (L.sourceIdentifier, Literal(pid)),
                     (L.rpgEdition, Literal(2020, datatype=XSD.integer)), (L.cropCode, cc),
                     (L.parcelAreaM2, dbl(area)), (L.matchedWeatherCell, d(f"weather-cell/{cid}"))):
            a((pn, p, v))
        ov = d(f"parcel-zone-overlap/{str(z).rsplit('/', 1)[-1]}/2020/{pid}")
        for p, v in ((RDF.type, L.ParcelZoneOverlap), (L.overlapParcel, pn),
                     (L.overlapZone, z), (L.overlapAreaM2, dbl(area))):
            a((ov, p, v))
        obs = d(f"ndvi/2020/{pid}")
        for p, v in ((RDF.type, L.SatelliteIndexObservation), (SOSA.hasFeatureOfInterest, pn),
                     (SOSA.observedProperty, L.SummerNDVI), (SOSA.phenomenonTime, iv_s),
                     (L.seasonYear, Literal(2020, datatype=XSD.integer)),
                     (L.validPixelCount, Literal(npx, datatype=XSD.integer))):
            a((obs, p, v))
        if ndvi is not None:
            a((obs, SOSA.hasSimpleResult, dbl(ndvi)))
        if nobs is not None:
            a((obs, L.meanClearAcquisitions, dbl(nobs)))
    # Zone-level share observations (z1 partial coverage 0.4, z2 full coverage 1.0 in 2020 and 0 classified in 2021)
    sh1 = d("irrigation-share/W1/2020")
    for p, v in ((RDF.type, SOSA.Observation), (SOSA.hasFeatureOfInterest, z1),
                 (SOSA.observedProperty, L.ProbablyIrrigatedShare), (SOSA.phenomenonTime, iv_s),
                 (L.seasonYear, Literal(2020, datatype=XSD.integer)),
                 (SOSA.hasSimpleResult, dbl(0.5)), (L.classifiedAreaM2, dbl(40000.0)),
                 (L.classifiedFraction, dbl(0.4)), (L.derivationRule, rule)):
        a((sh1, p, v))
    sh2 = d("irrigation-share/W2/2020")
    for p, v in ((RDF.type, SOSA.Observation), (SOSA.hasFeatureOfInterest, z2),
                 (SOSA.observedProperty, L.ProbablyIrrigatedShare), (SOSA.phenomenonTime, iv_s),
                 (L.seasonYear, Literal(2020, datatype=XSD.integer)),
                 (SOSA.hasSimpleResult, dbl(1.0)), (L.classifiedAreaM2, dbl(30000.0)),
                 (L.classifiedFraction, dbl(1.0)), (L.derivationRule, rule)):
        a((sh2, p, v))
    iv_s21 = d("interval/summer/2021")
    a((iv_s21, RDF.type, TIME.ProperInterval))
    sh2_21 = d("irrigation-share/W2/2021")
    for p, v in ((RDF.type, SOSA.Observation), (SOSA.hasFeatureOfInterest, z2),
                 (SOSA.observedProperty, L.ProbablyIrrigatedShare), (SOSA.phenomenonTime, iv_s21),
                 (L.seasonYear, Literal(2021, datatype=XSD.integer)),
                 (L.classifiedAreaM2, dbl(0.0)), (L.classifiedFraction, dbl(0.0)),
                 (L.derivationRule, rule)):
        a((sh2_21, p, v))
    return fx


def test_cq15_fixture(rules, shapes, net):
    """CQ15 SHACL-AF rule fixture, threshold sensitivity and negative controls for every CQ15 shape."""
    fx = build_cq15_fixture(ndvi_threshold=0.50)
    facts = fx.g
    records = rule_records(rules, "test", facts)
    added = run_rules(facts, rules, records)
    g = facts + records + added

    got = {
        pid: out.split("#")[-1]
        for pid, out in select(g, """SELECT ?pid ?out WHERE {
            ?c a lulcw:IrrigationClassification ; lulcw:classifiedParcel/lulcw:sourceIdentifier ?pid ;
               lulcw:irrigationOutcome ?out ; lulcw:derivationRule <rule/probable-irrigation> }""")
    }
    want = {
        "P_POS": "ProbablyIrrigated",
        "P_NEG": "NotProbablyIrrigated",
        "P_LOW_PX": "InsufficientSatelliteData",
        "P_LOW_OBS": "InsufficientSatelliteData",
        "P_ZERO_PX": "InsufficientSatelliteData",
        "P_WET": "WetSeason",
        "P_WET_LOW_PX": "InsufficientSatelliteData",
        "P_NO_SWI": "InsufficientSatelliteData",
        "P_NOSUP": "ProbablyIrrigated",
    }
    assert got == want, (got, want)
    # Every classification cites its NDVI observation (and SWI observation when present)
    derived = {
        pid: set(srcs.split())
        for pid, srcs in select(g, """SELECT ?pid (GROUP_CONCAT(STR(?s)) AS ?srcs) WHERE {
            ?c a lulcw:IrrigationClassification ; lulcw:classifiedParcel/lulcw:sourceIdentifier ?pid ;
               prov:wasDerivedFrom ?s } GROUP BY ?pid""")
    }
    assert str(d("ndvi/2020/P_POS")) in derived["P_POS"] and str(d("summer-swi/c1/2020")) in derived["P_POS"]
    assert derived["P_NO_SWI"] == {str(d("ndvi/2020/P_NO_SWI"))}
    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results

    # Threshold read from the graph, not hard-coded: raising ndviThreshold to 0.70 flips P_POS (0.65)
    fx2 = build_cq15_fixture(ndvi_threshold=0.70)
    g2 = fx2.g + rule_records(rules, "test", fx2.g) + run_rules(fx2.g, rules, rule_records(rules, "test", fx2.g))
    got2 = {
        pid: out.split("#")[-1]
        for pid, out in select(g2, """SELECT ?pid ?out WHERE {
            ?c a lulcw:IrrigationClassification ; lulcw:classifiedParcel/lulcw:sourceIdentifier ?pid ;
               lulcw:irrigationOutcome ?out }""")
    }
    assert got2["P_POS"] == "NotProbablyIrrigated" and got2["P_NOSUP"] == "ProbablyIrrigated", got2

    # Negative controls: at least one per new CQ15 shape
    def bad(triples, remove=()):
        h = rdflib.Graph()
        for t in g:
            if t not in remove:
                h.add(t)
        for t in triples:
            h.add(t)
        return check(h, shapes, net)[2]

    def now(s, p):
        return list(g.triples((s, p, None)))

    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    c_pos = d("irrigation-classification/2020/P_POS")
    c_dup = d("irrigation-classification/2020/P_POS-dup")
    neg = {
        "parcel with non-positive area": (
            [(d("parcel/2020/P_POS"), L.parcelAreaM2, dbl(0.0))],
            now(d("parcel/2020/P_POS"), L.parcelAreaM2),
            "RegisteredParcelShape", None),
        "parcel-zone overlap with non-positive area": (
            [(d("parcel-zone-overlap/W1/2020/P_POS"), L.overlapAreaM2, dbl(-5.0))],
            now(d("parcel-zone-overlap/W1/2020/P_POS"), L.overlapAreaM2),
            "ParcelZoneOverlapShape", None),
        "NDVI observation outside [-1, 1]": (
            [(d("ndvi/2020/P_POS"), SOSA.hasSimpleResult, dbl(1.5))],
            now(d("ndvi/2020/P_POS"), SOSA.hasSimpleResult),
            "SatelliteIndexObservationShape", None),
        "NDVI observation with negative valid pixel count": (
            [(d("ndvi/2020/P_POS"), L.validPixelCount, Literal(-1, datatype=XSD.integer))],
            now(d("ndvi/2020/P_POS"), L.validPixelCount),
            "SatelliteIndexObservationShape", None),
        "classification missing its irrigation outcome": (
            [], now(c_pos, L.irrigationOutcome),
            "IrrigationClassificationShape", None),
        "zone share result outside [0, 1]": (
            [(d("irrigation-share/W1/2020"), SOSA.hasSimpleResult, dbl(1.2))],
            now(d("irrigation-share/W1/2020"), SOSA.hasSimpleResult),
            "ProbablyIrrigatedShareShape", None),
        "zone share with zero classified area carrying a result": (
            [(d("irrigation-share/W2/2021"), SOSA.hasSimpleResult, dbl(0.0))], (),
            "ProbablyIrrigatedShareShape", "classified area is positive"),
        "missing classification for a parcel-season with NDVI observation": (
            [], list(g.triples((c_pos, None, None))),
            "IrrigationClassificationKeyShape", "has no irrigation classification"),
        "duplicate classification for one parcel-season and rule": (
            [(c_dup, p, o) for _, p, o in g.triples((c_pos, None, None))], (),
            "IrrigationClassificationKeyShape", "share a parcel, a season year and a rule"),
        "satellite observation with valid pixels missing its NDVI result": (
            [], now(d("ndvi/2020/P_POS"), SOSA.hasSimpleResult),
            "IrrigationClassificationKeyShape", "lacks its NDVI result"),
    }
    for name, (add, remove, shape, text) in neg.items():
        res = bad(add, remove)
        assert violations(res, shape, text) > 0, f"{name}: not caught\n{res}"
    print(f"  3c. CQ15 fixture: all 9 parcel-season cases and threshold sensitivity hold, 0 violations; "
          f"all {len(neg)} CQ15 shape negative controls caught")
    return g


def build_cq10_fixture(rules):
    """CQ10 synthetic fixture (step 15 note + v5 channels):
      - W1 monitors unit U (Confident); F1 (100 m, Probable) is selected by policy/main, while
        F4 (400 m, Possible) is excluded by policy/main; W2 monitors U 4,999 m away; weather cell
        c1 covers U's outcrop in W1's search zone (derived DiffuseRecharge influence, selected by main).
      - run/test-v5-r1 uses policy/main over 2005-01-02 .. 2026-10-18.
      - sim-head/W1/summer-2024 (sgi -1.50 -> VeryLowLevel):
          * AttributedPumpingStress: +0.35 m (less pumping than usual RAISED head -> RaisedHead,
            AcceptedStatement, cites main-selected F1->W1 pumping influence)
          * LocalRechargeStress: -0.80 m (LoweredHead, AcceptedStatement, cites c1->W1 influence)
          * UnattributedPumpingStress: +0.12 m, ReferenceWindow, 5% imputed -> QualifiedStatement
      - sim-head/W1/summer-2009 (sgi -1.2815515655446008 -> LowLevel, exact < boundary):
          * AttributedPumpingStress: -0.25 m, 100% imputed -> WithheldStatement
      - sim-head/W1/summer-2023 (all accepted, sgi -0.50 -> ModeratelyLowLevel):
          * LocalRechargeStress: -0.40 m -> AcceptedStatement
    Returns (full_graph, refs_dict) after running SHACL-AF rules to derive real Influence nodes.
    """
    fx = Fixture()
    a = fx.g.add
    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    dt = lambda s: Literal(s, datatype=XSD.date)  # noqa: E731
    U = fx.unit("U1")
    a((U, PROV.wasDerivedFrom, fx.rel))
    a((U, L.mappedOutcropAreaM2, dbl(1.0e6)))
    p1 = fx.polygon(301, [U])
    w1 = fx.well("W1", 0, 0, U, L.Confident, depth=50)
    w2 = fx.well("W2", 4999, 0, U, L.Confident, depth=55)
    a((w1, L.locatedInPolygon, p1))
    a((w2, L.locatedInPolygon, p1))
    fx.facility("F1", 100, 0, U, L.Probable)    # selected under policy/main
    fx.facility("F4", 400, 0, U, L.Possible)    # excluded under policy/main
    # Weather cell & outcrop coverage in W1's zone (for a real RechargeProxies influence)
    c1 = d("weather-cell/c1")
    a((c1, RDF.type, L.WeatherCell))
    a((c1, L.safranGridXHm, Literal(100, datatype=XSD.integer)))
    a((c1, L.safranGridYHm, Literal(200, datatype=XSD.integer)))
    a((c1, L.inRelease, fx.rel))
    fx.geometry(c1, "weather-cell", "c1", "POLYGON((0 0, 8000 0, 8000 8000, 0 8000, 0 0))")
    se = d("series/forcing-cq10/c1/PE")
    a((se, RDF.type, L.ObservationSeries))
    a((se, L.seriesVariable, L.EffectiveRainfall))
    a((c1, L.hasForcingSeries, se))
    oz = d("outcrop-zone/W1")
    a((oz, RDF.type, L.OutcropSearchZone))
    a((oz, L.zoneOf, w1))
    a((oz, L.zoneRadiusM, dbl(RADIUS)))
    a((d("extent/forcing-cells"), RDF.type, GEO.Feature))
    pci = d("polygon-cell/W1/301/c1")
    for p, v in ((RDF.type, L.PolygonCellIntersection), (L.intersectedPolygon, p1),
                 (L.withinExtent, oz), (L.intersectedCell, c1),
                 (L.intersectionAreaM2, dbl(1.0e6)),
                 (PROV.wasGeneratedBy, d("execution/polygon-cell-intersection"))):
        a((pci, p, v))
    a((d("execution/polygon-cell-intersection"), RDF.type, L.RuleExecution))

    records = rule_records(rules, "test", fx.g)
    g = fx.g + records + run_rules(fx.g, rules, records)
    ga = g.add

    # Locate derived influences by (mechanism, driver, target)
    inf_f1_w1 = next(i for i in g.subjects(RDF.type, L.Influence)
                     if (i, L.mechanism, L.PumpingDrawdown) in g
                     and (i, L.driverEntity, d("facility/F1")) in g
                     and (i, L.targetEntity, w1) in g)
    inf_f4_w1 = next(i for i in g.subjects(RDF.type, L.Influence)
                     if (i, L.mechanism, L.PumpingDrawdown) in g
                     and (i, L.driverEntity, d("facility/F4")) in g
                     and (i, L.targetEntity, w1) in g)
    inf_f1_w2 = next(i for i in g.subjects(RDF.type, L.Influence)
                     if (i, L.mechanism, L.PumpingDrawdown) in g
                     and (i, L.driverEntity, d("facility/F1")) in g
                     and (i, L.targetEntity, w2) in g)
    inf_c1_w1 = next(i for i in g.subjects(RDF.type, L.Influence)
                     if (i, L.mechanism, L.DiffuseRecharge) in g
                     and (i, L.driverEntity, c1) in g
                     and (i, L.targetEntity, w1) in g)

    # ModelRun
    run = d("run/test-v5-r1")
    for p, v in ((RDF.type, L.ModelRun), (L.runIdentifier, Literal("test_hgnn_D_r1")),
                 (L.usesExportPolicy, d("policy/main")), (PROV.used, fx.rel),
                 (L.regime, Literal("R1")), (L.pumpingReconstruction, Literal(1, datatype=XSD.integer)),
                 (L.fittingProtocol, Literal("stageB_gate3_converged")),
                 (L.startCount, Literal(10, datatype=XSD.integer)),
                 (L.periodStart, dt("2005-01-02")), (L.periodEnd, dt("2026-10-18"))):
        ga((run, p, v))

    # SimulatedHead 1: summer 2024 (VeryLowLevel, less pumping raises head + local recharge lowers head + qualified)
    sh24 = d("sim-head/W1/summer-2024")
    for p, v in ((RDF.type, L.SimulatedHead), (PROV.wasGeneratedBy, run), (L.simulatedAt, w1),
                 (L.periodStart, dt("2024-06-02")), (L.periodEnd, dt("2024-08-25")),
                 (L.simulatedHeadM, dbl(12.40)), (L.sgiValue, dbl(-1.50)),
                 (L.sgiClass, L.VeryLowLevel), (L.sgiReferenceEnd, dt("2019-12-31"))):
        ga((sh24, p, v))

    c_pump24 = d("contrib/W1/2024/pumping")
    for p, v in ((RDF.type, L.DriverContribution), (L.contributionTo, sh24),
                 (L.contributionStress, L.AttributedPumpingStress), (L.referenceCondition, L.TrainingMean),
                 (L.contributionM, dbl(0.35)), (L.startSdM, dbl(0.04)),
                 (L.startSignAgreement, dbl(0.9)), (L.imputedPumpingShare, dbl(0.0))):
        ga((c_pump24, p, v))
    st_pump24 = d("stmt/W1/2024/pumping")
    for p, v in ((RDF.type, L.ExplanationStatement), (L.explains, sh24),
                 (L.citesContribution, c_pump24), (L.citesInfluence, inf_f1_w1),
                 (L.statedDirection, L.RaisedHead), (L.statementStatus, L.AcceptedStatement),
                 (L.statementText, Literal("The model attributes +0.35 m (raised the head) to lower groundwater pumping on the graph's links.", lang="en")),
                 (L.statementText, Literal("Le modèle attribue +0,35 m (a relevé le niveau) à la baisse des prélèvements reliés par le graphe.", lang="fr"))):
        ga((st_pump24, p, v))

    c_rech24 = d("contrib/W1/2024/recharge-local")
    for p, v in ((RDF.type, L.DriverContribution), (L.contributionTo, sh24),
                 (L.contributionStress, L.LocalRechargeStress), (L.referenceCondition, L.TrainingMean),
                 (L.contributionM, dbl(-0.80)), (L.startSdM, dbl(0.08)),
                 (L.startSignAgreement, dbl(1.0))):
        ga((c_rech24, p, v))
    st_rech24 = d("stmt/W1/2024/recharge-local")
    for p, v in ((RDF.type, L.ExplanationStatement), (L.explains, sh24),
                 (L.citesContribution, c_rech24), (L.citesInfluence, inf_c1_w1),
                 (L.statedDirection, L.LoweredHead), (L.statementStatus, L.AcceptedStatement),
                 (L.statementText, Literal("The model attributes -0.80 m (lowered the head) to the local recharge proxy.", lang="en")),
                 (L.statementText, Literal("Le modèle attribue -0,80 m (a abaissé le niveau) à l'indicateur de recharge locale.", lang="fr"))):
        ga((st_rech24, p, v))

    c_qual24 = d("contrib/W1/2024/pumping-unattributed")
    for p, v in ((RDF.type, L.DriverContribution), (L.contributionTo, sh24),
                 (L.contributionStress, L.UnattributedPumpingStress),
                 (L.referenceCondition, L.ReferenceWindow),
                 (L.referenceStart, dt("2023-06-04")), (L.referenceEnd, dt("2023-08-27")),
                 (L.contributionM, dbl(0.12)), (L.startSdM, dbl(0.03)),
                 (L.startSignAgreement, dbl(0.9)), (L.imputedPumpingShare, dbl(0.05))):
        ga((c_qual24, p, v))
    st_qual24 = d("stmt/W1/2024/pumping-unattributed")
    for p, v in ((RDF.type, L.ExplanationStatement), (L.explains, sh24),
                 (L.citesContribution, c_qual24),
                 (L.statedDirection, L.RaisedHead), (L.statementStatus, L.QualifiedStatement),
                 (L.statementReason, Literal("5% of routed pumping volume is imputed (0-10% qualified)")),
                 (L.statementText, Literal("The model attributes +0.12 m (raised the head) to unattributed nearby pumping (5% imputed).", lang="en")),
                 (L.statementText, Literal("Le modèle attribue +0,12 m (a relevé le niveau) aux prélèvements voisins non attribués (5 % imputés).", lang="fr"))):
        ga((st_qual24, p, v))

    # SimulatedHead 2: summer 2009 (exact IPS boundary -> LowLevel; 100% imputed pumping -> Withheld)
    sh09 = d("sim-head/W1/summer-2009")
    for p, v in ((RDF.type, L.SimulatedHead), (PROV.wasGeneratedBy, run), (L.simulatedAt, w1),
                 (L.periodStart, dt("2009-06-07")), (L.periodEnd, dt("2009-08-30")),
                 (L.simulatedHeadM, dbl(14.10)), (L.sgiValue, dbl(-1.2815515655446008)),
                 (L.sgiClass, L.LowLevel), (L.sgiReferenceEnd, dt("2019-12-31"))):
        ga((sh09, p, v))
    c_pump09 = d("contrib/W1/2009/pumping")
    for p, v in ((RDF.type, L.DriverContribution), (L.contributionTo, sh09),
                 (L.contributionStress, L.AttributedPumpingStress), (L.referenceCondition, L.TrainingMean),
                 (L.contributionM, dbl(-0.25)), (L.startSdM, dbl(0.05)),
                 (L.startSignAgreement, dbl(0.9)), (L.imputedPumpingShare, dbl(1.0))):
        ga((c_pump09, p, v))
    st_pump09 = d("stmt/W1/2009/pumping")
    for p, v in ((RDF.type, L.ExplanationStatement), (L.explains, sh09),
                 (L.citesContribution, c_pump09), (L.citesInfluence, inf_f1_w1),
                 (L.statedDirection, L.LoweredHead), (L.statementStatus, L.WithheldStatement),
                 (L.statementReason, Literal("pumping over 2009 is 100% imputed (> 10%)")),
                 (L.statementText, Literal("Withheld: pumping over 2009 is 100% imputed.", lang="en")),
                 (L.statementText, Literal("Non retenu : les prélèvements de 2009 sont imputés à 100 %.", lang="fr"))):
        ga((st_pump09, p, v))

    # SimulatedHead 3: summer 2023 (clean all-accepted window -> cq10_status supported)
    sh23 = d("sim-head/W1/summer-2023")
    for p, v in ((RDF.type, L.SimulatedHead), (PROV.wasGeneratedBy, run), (L.simulatedAt, w1),
                 (L.periodStart, dt("2023-06-04")), (L.periodEnd, dt("2023-08-27")),
                 (L.simulatedHeadM, dbl(13.10)), (L.sgiValue, dbl(-0.50)),
                 (L.sgiClass, L.ModeratelyLowLevel), (L.sgiReferenceEnd, dt("2019-12-31"))):
        ga((sh23, p, v))
    c_rech23 = d("contrib/W1/2023/recharge-local")
    for p, v in ((RDF.type, L.DriverContribution), (L.contributionTo, sh23),
                 (L.contributionStress, L.LocalRechargeStress), (L.referenceCondition, L.TrainingMean),
                 (L.contributionM, dbl(-0.40)), (L.startSdM, dbl(0.05)),
                 (L.startSignAgreement, dbl(1.0))):
        ga((c_rech23, p, v))
    st_rech23 = d("stmt/W1/2023/recharge-local")
    for p, v in ((RDF.type, L.ExplanationStatement), (L.explains, sh23),
                 (L.citesContribution, c_rech23), (L.citesInfluence, inf_c1_w1),
                 (L.statedDirection, L.LoweredHead), (L.statementStatus, L.AcceptedStatement),
                 (L.statementText, Literal("The model attributes -0.40 m (lowered the head) to the local recharge proxy.", lang="en")),
                 (L.statementText, Literal("Le modèle attribue -0,40 m (a abaissé le niveau) à l'indicateur de recharge locale.", lang="fr"))):
        ga((st_rech23, p, v))

    refs = {
        "run": run, "w1": w1, "w2": w2,
        "sh24": sh24, "sh09": sh09, "sh23": sh23,
        "c_pump24": c_pump24, "st_pump24": st_pump24,
        "c_rech24": c_rech24, "st_rech24": st_rech24,
        "c_qual24": c_qual24, "st_qual24": st_qual24,
        "c_pump09": c_pump09, "st_pump09": st_pump09,
        "inf_f1_w1": inf_f1_w1, "inf_f4_w1": inf_f4_w1,
        "inf_f1_w2": inf_f1_w2, "inf_c1_w1": inf_c1_w1,
    }
    return g, refs


def test_cq10_fixture(rules, shapes, net):
    """CQ10 positive fixture (0 violations) and negative controls for all 6 step-15 shapes."""
    g, r = build_cq10_fixture(rules)
    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results

    def bad(triples, remove=()):
        h = rdflib.Graph()
        for t in g:
            if t not in remove:
                h.add(t)
        for t in triples:
            h.add(t)
        return check(h, shapes, net)[2]

    def now(s, p):
        return list(g.triples((s, p, None)))

    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    dt = lambda s: Literal(s, datatype=XSD.date)  # noqa: E731

    neg = {
        "1a. cited influence excluded by the run's export policy (Possible under main)": (
            [(r["st_pump24"], L.citesInfluence, r["inf_f4_w1"])], (),
            "ExplanationStatementShape", "not selected under the run's export policy"),
        "1b. cited non-existent entity as influence": (
            [(r["st_pump24"], L.citesInfluence, d("influence/non-existent"))], (),
            "ExplanationStatementShape", "must exist as a lulcw:Influence"),
        "1c. cited influence targeting another well (W2 instead of W1)": (
            [(r["st_pump24"], L.citesInfluence, r["inf_f1_w2"])], (),
            "ExplanationStatementShape", "does not target the statement's well"),
        "2. cited influence driver group disagrees with contribution driver group": (
            [(r["st_pump24"], L.citesInfluence, r["inf_c1_w1"])], (),
            "ExplanationStatementShape", "driver group disagrees"),
        "3a. stated direction confuses response polarity with positive pumping contribution": (
            [(r["st_pump24"], L.statedDirection, L.LoweredHead)],
            now(r["st_pump24"], L.statedDirection),
            "ExplanationStatementShape", "stated direction disagrees"),
        "3b. NoNetChange stated on a -0.80 m contribution": (
            [(r["st_rech24"], L.statedDirection, L.NoNetChange)],
            now(r["st_rech24"], L.statedDirection),
            "ExplanationStatementShape", "stated direction disagrees"),
        "4a. pumping statement over 100% imputed weeks marked Accepted instead of Withheld": (
            [(r["st_pump09"], L.statementStatus, L.AcceptedStatement)],
            now(r["st_pump09"], L.statementStatus),
            "ExplanationStatementShape", "must be withheld"),
        "4b. pumping statement with 5% imputed volume marked Accepted unqualified": (
            [(r["st_qual24"], L.statementStatus, L.AcceptedStatement)],
            now(r["st_qual24"], L.statementStatus),
            "ExplanationStatementShape", "cannot be accepted unqualified"),
        "5a. wrong SGI class for sgiValue -1.50 (LowLevel instead of VeryLowLevel)": (
            [(r["sh24"], L.sgiClass, L.LowLevel)],
            now(r["sh24"], L.sgiClass),
            "SimulatedHeadShape", "BRGM IPS bounds"),
        "5b. wrong SGI boundary class (sgiValue == -1.28155... assigned VeryLowLevel)": (
            [(r["sh09"], L.sgiClass, L.VeryLowLevel)],
            now(r["sh09"], L.sgiClass),
            "SimulatedHeadShape", "BRGM IPS bounds"),
        "5c. simulated head period outside the model run's period": (
            [(r["sh24"], L.periodEnd, dt("2027-01-01"))],
            now(r["sh24"], L.periodEnd),
            "SimulatedHeadShape", "outside its model run's period"),
        "6. accepted statement with start sign agreement < 0.8": (
            [(r["c_pump24"], L.startSignAgreement, dbl(0.6))],
            now(r["c_pump24"], L.startSignAgreement),
            "ExplanationStatementShape", "start sign agreement at least 0.8"),
        "7. statement citing a contribution of another simulated head": (
            [(r["st_pump24"], L.citesContribution, r["c_pump09"])],
            now(r["st_pump24"], L.citesContribution),
            "ExplanationStatementShape", "does not belong to the simulated head"),
    }
    for name, (add, remove, shape, text) in neg.items():
        res = bad(add, remove)
        assert violations(res, shape, text) > 0, f"{name}: not caught\n{res}"
    print(f"  3d. CQ10 fixture: v5 stresses, positive pumping contribution (RaisedHead), exact IPS "
          f"boundary, withheld imputed pumping pass with 0 violations; all {len(neg)} CQ10 negative controls caught")
    return g


def build_cq16_fixture(rules):
    """CQ16 synthetic fixture (schema & acceptance cases; no real-data numbers yet):
      - scenario/opposing-pathways (zone/W1, eligible, TotalHeadChange, rank 1): orchard -> cereal,
        demand -100,000 m³, gw share 0.60, return-flow fraction 0.25 -> less abstraction (-60,000 m³)
        AND less return flow (-25,000 m³), uncertainty range [-0.15, +0.25] spanning 0.
      - scenario/surface-supplied (zone/W1, eligible, TotalHeadChange, rank 2): gw share 0.0,
        demand -40,000 m³, return-flow fraction 0.20 -> zero pumping change, -8,000 m³ return flow.
      - scenario/per-hectare (zone/W1, eligible, HeadChangePerHectare, rank 1): separate ranking
        metric, never ranked against TotalHeadChange.
      - scenario/no-change (zone/W1, eligible, HeadChangeAtWell, rank 1): 0 m² / 0 demand change ->
        zero forcing changes and 0.0 m head change.
      - scenario/missing-assumptions (zone/W2, eligible, TotalHeadChange, no result): missing both
        WaterSourceShare and ReturnFlowFraction -> SHACL Warning (0 violations), reported by CQ16.
      - scenario/ineligible-zone (zone/W3, scenarioEligible false: heuristic only + no supply evidence,
        no result): 0 violations; any attached result is rejected by SHACL.
    """
    fx = Fixture()
    a = fx.g.add
    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    dt = lambda s: Literal(s, datatype=XSD.date)  # noqa: E731
    U = fx.unit("U1")
    a((d("extent/forcing-cells"), RDF.type, GEO.Feature))
    w1 = fx.well("W1", 0, 0, U, L.Confident, depth=30)
    w2 = fx.well("W2", 20000, 0, U, L.Confident, depth=30)
    w3 = fx.well("W3", 40000, 0, U, L.Confident, depth=30)
    zones = {}
    for k, w in (("W1", w1), ("W2", w2), ("W3", w3)):
        z = zones[k] = d(f"zone/{k}")
        a((z, RDF.type, L.CropDemandZone))
        a((z, L.zoneOf, w))
        a((z, L.zoneRadiusM, dbl(3000.0)))

    cscheme = d("crop-class-scheme/lulcw")
    a((cscheme, RDF.type, SKOS.ConceptScheme))
    cls_map = {}
    for name, assump in (("orchard", L.UsuallyIrrigated), ("vineyard", L.PartlyIrrigated),
                         ("cereal", L.Rainfed)):
        c = cls_map[name] = d(f"crop-class/{name}")
        a((c, RDF.type, L.CropClass))
        a((c, SKOS.inScheme, cscheme))
        a((c, SKOS.notation, Literal(name)))
        a((c, L.irrigationAssumption, assump))
        for prop, v in ((L.kcInitial, 0.5), (L.kcMid, 0.9), (L.kcEnd, 0.6)):
            a((c, prop, dbl(v)))
        for prop, v in ((L.initialStageDays, 30), (L.developmentStageDays, 50),
                        (L.midSeasonStageDays, 130), (L.lateSeasonStageDays, 30), (L.plantingMonth, 3)):
            a((c, prop, Literal(v, datatype=XSD.integer)))

    run = d("run/test-v5-r1")
    for p, v in ((RDF.type, L.ModelRun), (L.runIdentifier, Literal("test_hgnn_D_r1")),
                 (L.usesExportPolicy, d("policy/main")), (PROV.used, fx.rel),
                 (L.regime, Literal("R1")), (L.pumpingReconstruction, Literal(1, datatype=XSD.integer)),
                 (L.fittingProtocol, Literal("stageB_gate3_converged")),
                 (L.startCount, Literal(10, datatype=XSD.integer)),
                 (L.periodStart, dt("2005-01-02")), (L.periodEnd, dt("2026-10-18"))):
        a((run, p, v))

    # Zone eligibilities
    for k, ok, why in (
        ("W1", True, "zone has declared groundwater supply and crop-demand data (fixture)"),
        ("W2", True, "zone has supply context; scenario assumptions incomplete (fixture)"),
        ("W3", False, "irrigation status heuristic only (CQ15) and no supply evidence"),
    ):
        el = d(f"scenario-eligibility/{k}")
        for p, v in ((RDF.type, L.ScenarioEligibility), (L.scenarioZone, zones[k]),
                     (L.scenarioEligible, Literal(ok, datatype=XSD.boolean)),
                     (L.eligibilityReason, Literal(why))):
            a((el, p, v))

    def add_assumption(sc_key, suffix, kind, val, unit, derived=False):
        n = d(f"scenario-assumption/{sc_key}/{suffix}")
        for p, v in ((RDF.type, L.ScenarioAssumption), (L.assumptionKind, kind),
                     (L.assumptionValue, dbl(val)), (L.assumptionUnit, Literal(unit))):
            a((n, p, v))
        if derived:
            a((n, PROV.wasDerivedFrom, fx.rel))
        else:
            a((n, L.evidenceKind, L.ExpertHypothesis))
        return n

    def add_scenario(key, base, alt, area_m2, z_key, metric, assumptions):
        sc = d(f"scenario/{key}")
        for p, v in ((RDF.type, L.CropChangeScenario), (L.baselineCropClass, cls_map[base]),
                     (L.alternativeCropClass, cls_map[alt]), (L.substitutedAreaM2, dbl(area_m2)),
                     (L.scenarioZone, zones[z_key]), (L.periodStart, dt("2023-01-01")),
                     (L.periodEnd, dt("2023-12-31")), (L.rankingMetric, metric)):
            a((sc, p, v))
        for suffix, kind, val, unit, derived in assumptions:
            a((sc, L.hasAssumption, add_assumption(key, suffix, kind, val, unit, derived)))
        return sc

    def add_result(key, sc, well, val, lo, hi, rank=None):
        res = d(f"scenario-result/{key}")
        for p, v in ((RDF.type, L.ScenarioResult), (L.scenarioOf, sc), (PROV.wasGeneratedBy, run),
                     (L.simulatedAt, well), (L.periodStart, dt("2023-01-01")),
                     (L.periodEnd, dt("2023-12-31")), (L.headChangeM, dbl(val)),
                     (L.headChangeLowM, dbl(lo)), (L.headChangeHighM, dbl(hi))):
            a((res, p, v))
        if rank is not None:
            a((res, L.rank, Literal(rank, datatype=XSD.integer)))
        return res

    sc_opp = add_scenario("opposing-pathways", "orchard", "cereal", 100000.0, "W1", L.TotalHeadChange, (
        ("ws", L.WaterSourceShare, 0.60, "dimensionless", False),
        ("rf", L.ReturnFlowFraction, 0.25, "dimensionless", False),
        ("id", L.IrrigationDemandChange, -100000.0, "m3/yr", True),
        ("cl", L.ClimateCase, 2023.0, "year", True),
    ))
    r_opp = add_result("opposing/W1", sc_opp, w1, 0.05, -0.15, 0.25, rank=1)

    sc_surf = add_scenario("surface-supplied", "orchard", "vineyard", 50000.0, "W1", L.TotalHeadChange, (
        ("ws", L.WaterSourceShare, 0.0, "dimensionless", False),
        ("rf", L.ReturnFlowFraction, 0.20, "dimensionless", False),
        ("id", L.IrrigationDemandChange, -40000.0, "m3/yr", True),
    ))
    r_surf = add_result("surface/W1", sc_surf, w1, -0.08, -0.14, -0.02, rank=2)

    sc_ha = add_scenario("per-hectare", "orchard", "cereal", 100000.0, "W1", L.HeadChangePerHectare, (
        ("ws", L.WaterSourceShare, 0.60, "dimensionless", False),
        ("rf", L.ReturnFlowFraction, 0.25, "dimensionless", False),
        ("id", L.IrrigationDemandChange, -100000.0, "m3/yr", True),
    ))
    r_ha = add_result("per-ha/W1", sc_ha, w1, 0.005, 0.001, 0.010, rank=1)

    sc_zero = add_scenario("no-change", "orchard", "vineyard", 0.0, "W1", L.HeadChangeAtWell, (
        ("ws", L.WaterSourceShare, 0.50, "dimensionless", False),
        ("rf", L.ReturnFlowFraction, 0.20, "dimensionless", False),
        ("id", L.IrrigationDemandChange, 0.0, "m3/yr", True),
    ))
    r_zero = add_result("no-change/W1", sc_zero, w1, 0.0, 0.0, 0.0, rank=1)

    sc_miss = add_scenario("missing-assumptions", "orchard", "cereal", 50000.0, "W2", L.TotalHeadChange, (
        ("id", L.IrrigationDemandChange, -50000.0, "m3/yr", True),
    ))

    sc_inel = add_scenario("ineligible-zone", "orchard", "cereal", 50000.0, "W3", L.TotalHeadChange, (
        ("ws", L.WaterSourceShare, 0.50, "dimensionless", False),
        ("rf", L.ReturnFlowFraction, 0.20, "dimensionless", False),
        ("id", L.IrrigationDemandChange, -50000.0, "m3/yr", True),
    ))

    refs = {
        "run": run, "w1": w1, "w2": w2, "w3": w3, "zones": zones, "cls": cls_map,
        "sc_opp": sc_opp, "r_opp": r_opp, "sc_surf": sc_surf, "r_surf": r_surf,
        "sc_ha": sc_ha, "r_ha": r_ha, "sc_zero": sc_zero, "r_zero": r_zero,
        "sc_miss": sc_miss, "sc_inel": sc_inel,
        "a_ws": d("scenario-assumption/opposing-pathways/ws"),
    }
    records = rule_records(rules, "test", fx.g)
    g = fx.g + records + run_rules(fx.g, rules, records)
    return g, refs


def test_cq16_fixture(rules, shapes, net):
    """CQ16 positive fixture (0 violations, 1 expected Warning on missing-assumptions) and negative
    controls covering every CQ16 shape."""
    g, r = build_cq16_fixture(rules)
    conforms, _, results = check(g, shapes, net)
    assert conforms and violations(results) == 0, results
    assert any(k.startswith("Warning") and "CropChangeScenarioAssumptionsShape" in k for k in results), results

    def bad(triples, remove=()):
        h = rdflib.Graph()
        for t in g:
            if t not in remove:
                h.add(t)
        for t in triples:
            h.add(t)
        return check(h, shapes, net)[2]

    def now(s, p):
        return list(g.triples((s, p, None)))

    dbl = lambda v: Literal(float(v), datatype=XSD.double)  # noqa: E731
    dt = lambda s: Literal(s, datatype=XSD.date)  # noqa: E731

    bad_inel_res = d("scenario-result/bad-ineligible")
    bad_miss_res = d("scenario-result/bad-missing")
    base_res = lambda node, sc, w: [  # noqa: E731
        (node, RDF.type, L.ScenarioResult), (node, L.scenarioOf, sc),
        (node, PROV.wasGeneratedBy, r["run"]), (node, L.simulatedAt, w),
        (node, L.periodStart, dt("2023-01-01")), (node, L.periodEnd, dt("2023-12-31")),
        (node, L.headChangeM, dbl(0.1)), (node, L.headChangeLowM, dbl(0.0)),
        (node, L.headChangeHighM, dbl(0.2)),
    ]

    neg = {
        "scenario with identical baseline and alternative crop classes": (
            [(r["sc_opp"], L.alternativeCropClass, r["cls"]["orchard"])],
            now(r["sc_opp"], L.alternativeCropClass),
            "CropChangeScenarioShape", "two different crop classes"),
        "scenario missing scenarioZone": (
            [], now(r["sc_opp"], L.scenarioZone),
            "CropChangeScenarioShape", None),
        "scenario period ending before it starts": (
            [(r["sc_opp"], L.periodEnd, dt("2022-01-01"))],
            now(r["sc_opp"], L.periodEnd),
            "CropChangeScenarioShape", "ends before it starts"),
        "assumption missing provenance (neither wasDerivedFrom nor ExpertHypothesis)": (
            [], now(r["a_ws"], L.evidenceKind),
            "ScenarioAssumptionShape", "cite its source"),
        "scenario result for a scenario missing WaterSourceShare/ReturnFlowFraction": (
            base_res(bad_miss_res, r["sc_miss"], r["w2"]), (),
            "ScenarioResultShape", "missing a WaterSourceShare or ReturnFlowFraction"),
        "scenario result missing simulatedAt well": (
            [], now(r["r_opp"], L.simulatedAt),
            "ScenarioResultShape", None),
        "scenario result with headChangeLowM > headChangeM": (
            [(r["r_opp"], L.headChangeLowM, dbl(0.20))],
            now(r["r_opp"], L.headChangeLowM),
            "ScenarioResultShape", "outside [headChangeLowM, headChangeHighM]"),
        "scenario result with headChangeM > headChangeHighM": (
            [(r["r_opp"], L.headChangeHighM, dbl(0.01))],
            now(r["r_opp"], L.headChangeHighM),
            "ScenarioResultShape", "outside [headChangeLowM, headChangeHighM]"),
        "scenario result for a zone whose eligibility is false": (
            base_res(bad_inel_res, r["sc_inel"], r["w3"]), (),
            "ScenarioResultShape", "eligibility is false"),
        "cross-metric ranking (rank 2 under HeadChangePerHectare without rank 1 under that metric)": (
            [(r["r_ha"], L.rank, Literal(2, datatype=XSD.integer))],
            now(r["r_ha"], L.rank),
            "ScenarioResultShape", "same ranking metric"),
        "scenario result declaring a different ranking metric from its scenario": (
            [(r["r_ha"], L.rankingMetric, L.TotalHeadChange)], (),
            "ScenarioResultShape", "disagrees with its scenario's ranking metric"),
    }
    for name, (add, remove, shape, text) in neg.items():
        res = bad(add, remove)
        assert violations(res, shape, text) > 0, f"{name}: not caught\n{res}"
    print(f"  3e. CQ16 fixture: opposing pathways, surface-supplied, no-change, missing assumptions "
          f"(Warning, 0 violations) and ineligible zone pass; all {len(neg)} CQ16 negative controls caught")
    return g


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


def oracle_coverage(units, wells):
    """CQ4 with GeoPandas on the raw sources, written apart from src.kg.forcing: the SAFRAN cells
    as 8 km squares around the grid points (EPSG:27572, edges densified every 250 m, then
    Lambert-93), a 5 km disc around each well (Lambert-93), and the BD LISA polygons whose order-1
    unit is one of `units`, cut by each extent and overlaid with the cells. Returns
    {(extent, unit): (outcrop m², covered m², {cell_id: covered m² in it})}, extent = "forcing-cells"
    or the well's code_bss; parts under 1 m² are slivers of shared edges, kept here."""
    from shapely import segmentize
    from shapely.geometry import Point, box
    from src.config import RAW
    grid = pd.read_parquet(RAW / "safran" / "grid_cells_66.parquet")
    cells = gpd.GeoDataFrame(
        {"cell_id": grid["cell_id"]}, crs="EPSG:27572",
        geometry=[segmentize(box(x * 100 - 4000, y * 100 - 4000, x * 100 + 4000, y * 100 + 4000), 250.0)
                  for x, y in zip(grid["LAMBX"], grid["LAMBY"])]).to_crs(CRS_L93)
    pts = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    extents = {"forcing-cells": cells.union_all()} | {   # unrounded centres, as the graph's zones
        c: Point(pt.x, pt.y).buffer(RADIUS, 256) for c, pt in zip(wells["code_bss"], pts)}
    bounds = gpd.GeoSeries(list(extents.values()), crs=CRS_L93).total_bounds
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", bbox=tuple(bounds))[["codepoly", "geometry"]]
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    first = pile[pile["OrdRelatif"].astype(int) == 1]
    top = first.set_index(first["CodePoly"].astype(int))["CodeEH"]
    assert top.index.is_unique, "a polygon with two units at order 1"
    poly["unit"] = poly["codepoly"].astype(int).map(top)
    poly = poly[poly["unit"].isin(units)]
    out = {}
    for key, ext in extents.items():
        part = poly[poly.intersects(ext)].copy()
        part["geometry"] = part.geometry.intersection(ext)
        part = part[part.area > 0]
        if part.empty:
            continue
        pieces = gpd.overlay(part[["unit", "geometry"]], cells, how="intersection", keep_geom_type=True)
        per_cell = pieces.assign(a=pieces.area).groupby(["unit", "cell_id"])["a"].sum()
        for unit, total in part.assign(a=part.area).groupby("unit")["a"].sum().items():
            by_cell = per_cell.loc[unit].to_dict() if unit in per_cell.index.get_level_values(0) else {}
            out[(key, unit)] = (total, sum(by_cell.values()), by_cell)
    return out


def oracle_mapped_outcrop(units):
    """{unit: m²} of the order-1 polygons of the whole BD LISA extract (pyogrio, apart from
    src.kg.forcing.mapped_outcrop)."""
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES")[["codepoly", "geometry"]]
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    first = pile[pile["OrdRelatif"].astype(int) == 1]
    unit = poly["codepoly"].astype(int).map(first.set_index(first["CodePoly"].astype(int))["CodeEH"])
    m2 = pd.Series(poly.area.to_numpy()).groupby(unit.to_numpy()).sum()
    return {u: float(m2.get(u, 0.0)) for u in units}


def test_data_forcing(store):
    """CQ4 rule outputs against oracle_coverage: the same (extent, unit) keys, outcrop and covered
    areas, covered fractions and cell weights; slivers under 1 m² are dropped by the graph, so
    areas agree within 1 m² per dropped piece (50 m² allowed) and weights within 1e-5."""
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    units = {c for (c,) in rows(store, "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }")}
    got = {}
    for s, b, u, o, c, f in rows(store, """SELECT ?s ?b ?u ?o ?c ?f WHERE {
            ?v a lulcw:OutcropCoverage ; lulcw:withinExtent ?s ; lulcw:coverageUnit/lulcw:bdlisaCode ?u ;
               lulcw:outcropAreaM2 ?o ; lulcw:coveredAreaM2 ?c ; lulcw:coveredFraction ?f .
            OPTIONAL { ?s lulcw:zoneOf/lulcw:bssCode ?b } }"""):
        got[("forcing-cells" if b is None else b, u)] = (o, c, f)
    wts = {}
    for s, b, u, cell, w in rows(store, """SELECT ?s ?b ?u ?cell ?w WHERE {
            ?v a lulcw:OutcropCoverage ; lulcw:withinExtent ?s ; lulcw:coverageUnit/lulcw:bdlisaCode ?u ;
               lulcw:hasCellWeight ?x . ?x lulcw:weightCell ?wc ; lulcw:cellWeight ?w .
            ?wc lulcw:safranGridXHm ?gx ; lulcw:safranGridYHm ?gy .
            BIND (CONCAT(STR(?gx), "_", STR(?gy)) AS ?cell)
            OPTIONAL { ?s lulcw:zoneOf/lulcw:bssCode ?b } }"""):
        wts.setdefault(("forcing-cells" if b is None else b, u), {})[cell] = w
    want = {k: v for k, v in oracle_coverage(units, wells).items() if v[0] >= 50.0}
    got = {k: v for k, v in got.items() if v[0] >= 50.0}
    assert set(got) == set(want), f"coverage keys: {sorted(set(got) ^ set(want))[:6]}"
    for k, (o, c, by_cell) in want.items():
        go, gc, gf = got[k]
        assert abs(go - o) <= 50.0 and abs(gc - c) <= 50.0, (k, go, o, gc, c)
        assert abs(gf - (c / o)) <= 1e-5, (k, gf, c / o)
        w_want = {cell: a / c for cell, a in by_cell.items() if a >= 1.0} if c > 0 else {}
        w_got = wts.get(k, {})
        big = {cell for cell, w in w_want.items() if w > 1e-5}
        assert big <= set(w_got) and all(abs(w_got.get(cell, 0.0) - w) <= 1e-5 for cell, w in w_want.items()), k
    mapped = {c: m for c, m in rows(store, "SELECT ?c ?m WHERE { ?u lulcw:bdlisaCode ?c ; lulcw:mappedOutcropAreaM2 ?m }")}
    assert set(mapped) == units, "units described by BD LISA without a mapped outcrop, or the reverse"
    want_m = oracle_mapped_outcrop(units)
    assert all(abs(mapped[u] - want_m[u]) <= 1e-6 * want_m[u] + 1e-3 for u in units), "mapped outcrop areas"
    assert all(o <= mapped[u] * (1 + 1e-6) + 1 for (_, u), (o, _, _) in got.items())
    partial = sorted(k for k, (o, c, f) in got.items() if f < 1 - 1e-9)
    assert all(f == 1.0 for (s, _), (_, _, f) in got.items() if s == "forcing-cells")   # the cells are the extent
    clipped = sorted(u for (s, u), (o, _, _) in got.items() if s == "forcing-cells" and o < mapped[u] * (1 - 1e-6) - 10)
    return got, partial, clipped, want


def test_data_recharge(store, oracle):
    """CQ4/CQ8 recharge proxies against the GeoPandas oracle of test_data_forcing and the dataset's
    recorded units: each well with a recorded unit described by BD LISA gets, in its search zone, one
    influence per cell that holds that unit's outcrop there, with the oracle's renormalised weight,
    and in the forcing extent the unit-wide cells; a well without a recorded unit, or whose unit BD
    LISA does not describe, gets none. Every influence: effective rainfall standing in for
    groundwater recharge, non-decreasing, eligible, exact unit, the four omitted pathways; a policy
    selects it exactly when it admits the well's attribution."""
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    described = {c for (c,) in rows(store, "SELECT ?c WHERE { ?u lulcw:bdlisaCode ?c ; prov:wasDerivedFrom ?r }")}
    got, n = {}, 0
    for b, kind, cell, w, sign, elig, var, q, res, grp, n_om in rows(store, """
            SELECT ?b ?kind ?cell ?w ?sign ?elig ?var ?q ?res ?grp (COUNT(DISTINCT ?om) AS ?n) WHERE {
            ?i a lulcw:Influence ; lulcw:mechanism lulcw:DiffuseRecharge ; lulcw:targetEntity/lulcw:bssCode ?b ;
               lulcw:driverEntity ?c ; lulcw:withinExtent ?s ; lulcw:responseSign ?sign ;
               lulcw:constraintEligibility ?elig ; lulcw:driverVariable ?var ; lulcw:proxyFor ?q ;
               lulcw:resolution ?res ; lulcw:driverGroup ?grp ; lulcw:omitsPathway ?om ; prov:wasDerivedFrom ?cw .
            ?cw lulcw:cellWeight ?w .
            ?c lulcw:safranGridXHm ?gx ; lulcw:safranGridYHm ?gy .
            BIND (CONCAT(STR(?gx), "_", STR(?gy)) AS ?cell)
            BIND (IF(STRSTARTS(STR(?s), STR(<outcrop-zone/>)), "local", "unit-wide") AS ?kind) }
            GROUP BY ?b ?kind ?cell ?w ?sign ?elig ?var ?q ?res ?grp"""):
        assert (sign, elig, var, q, res, grp, n_om) == tuple(str(x) for x in (
            L.PositiveResponse, L.EligibleConstraint, L.EffectiveRainfall, L.GroundwaterRecharge,
            L.ExactUnitResolution, L.RechargeProxies)) + (4,), (b, cell, sign, elig, var, q, res, grp, n_om)
        got.setdefault((b, kind), {})[cell] = w
        n += 1
    want, sliver = {}, set()
    for b, u in zip(wells["code_bss"], wells["code_bdlisa"]):
        if not isinstance(u, str) or u not in described:
            continue
        for kind, key in (("local", b), ("unit-wide", "forcing-cells")):
            o, c, by_cell = oracle.get((key, u), (0.0, 0.0, {}))
            if o >= 50.0 and c > 0:
                want[(b, kind)] = {cell: a / c for cell, a in by_cell.items() if a >= 1.0}
            elif o > 0:
                sliver.add((b, kind))     # under 50 m²: the graph may or may not keep it (1 m² pieces)
    assert set(got) - sliver == set(want), f"recharge wells differ: {sorted((set(got) - sliver) ^ set(want))[:6]}"
    for k, cells in want.items():
        big = {cell for cell, w in cells.items() if w > 1e-5}
        assert big <= set(got[k]) and all(abs(got[k].get(cell, 0.0) - w) <= 1e-5 for cell, w in cells.items()), k
    assert all(abs(sum(v.values()) - 1) <= 1e-9 for v in got.values())
    # selection: exactly the policies that admit the well's attribution
    bad = rows(store, """SELECT ?i ?p WHERE { ?i a lulcw:Influence ; lulcw:mechanism lulcw:DiffuseRecharge ;
            prov:wasDerivedFrom ?a . ?a a lulcw:UnitAttribution ; lulcw:confidence ?c . ?p a lulcw:ExportPolicy .
            BIND (EXISTS { ?p lulcw:admitsConfidence ?c } AS ?admits)
            BIND (EXISTS { ?i lulcw:selectedUnder ?p } AS ?selected)
            FILTER (?admits != ?selected) }""")
    assert not bad, f"recharge proxies selected against their attribution's confidence: {bad[:3]}"
    local = {b for b, kind in got if kind == "local"}
    with_unit = {b for b, u in zip(wells["code_bss"], wells["code_bdlisa"]) if isinstance(u, str)}
    # overlying-leakage recharge influences (VerticalLeakage)
    leak_got, n_leak = {}, 0
    for b, via, cell, w, sign, elig, var, q, res, grp, n_om in rows(store, """
            SELECT ?b ?via ?cell ?w ?sign ?elig ?var ?q ?res ?grp (COUNT(DISTINCT ?om) AS ?n) WHERE {
            ?i a lulcw:Influence ; lulcw:mechanism lulcw:VerticalLeakage ; lulcw:targetEntity/lulcw:bssCode ?b ;
               lulcw:viaUnit/lulcw:bdlisaCode ?via ; lulcw:driverEntity ?c ; lulcw:responseSign ?sign ;
               lulcw:constraintEligibility ?elig ; lulcw:driverVariable ?var ; lulcw:proxyFor ?q ;
               lulcw:resolution ?res ; lulcw:driverGroup ?grp ; lulcw:omitsPathway ?om ; prov:wasDerivedFrom ?cw .
            ?cw lulcw:cellWeight ?w .
            ?c lulcw:safranGridXHm ?gx ; lulcw:safranGridYHm ?gy .
            BIND (CONCAT(STR(?gx), "_", STR(?gy)) AS ?cell) }
            GROUP BY ?b ?via ?cell ?w ?sign ?elig ?var ?q ?res ?grp"""):
        assert (sign, elig, var, q, res, grp, n_om) == tuple(str(x) for x in (
            L.PositiveResponse, L.EligibleConstraint, L.EffectiveRainfall, L.GroundwaterRecharge,
            L.ExactUnitResolution, L.RechargeProxies)) + (3,), (b, via, cell, sign, elig, var, q, res, grp, n_om)
        leak_got.setdefault((b, via), {})[cell] = w
        n_leak += 1
    bad_leak = rows(store, """SELECT ?i ?p WHERE { ?i a lulcw:Influence ; lulcw:mechanism lulcw:VerticalLeakage ;
            prov:wasDerivedFrom ?a . ?a a lulcw:UnitAttribution ; lulcw:confidence ?c . ?p a lulcw:ExportPolicy .
            BIND (EXISTS { ?p lulcw:admitsConfidence ?c } AS ?admits)
            BIND (EXISTS { ?i lulcw:selectedUnder ?p } AS ?selected)
            FILTER (?admits != ?selected) }""")
    assert not bad_leak, f"leakage influences selected against their attribution's confidence: {bad_leak[:3]}"
    # oracle from the well's polygon stack in BD LISA
    pts = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", columns=["codepoly"]).to_crs(CRS_L93)
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=pts), poly, how="left", predicate="within")
    w_cp = j[~j.index.duplicated()]["codepoly"].reindex(wells.index)
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    pile = pile.assign(cp=pile["CodePoly"].astype(int)).sort_values(["cp", "OrdRelatif"])
    stack_of = pile.groupby("cp")["CodeEH"].agg(list).to_dict()
    leak_want, leak_sliver = {}, set()
    for i, b in enumerate(wells["code_bss"]):
        u = wells.iloc[i]["code_bdlisa"]
        cp = w_cp.iloc[i]
        if not isinstance(u, str) or pd.isna(cp):
            continue
        st = stack_of.get(int(cp), [])
        if u not in st:
            continue
        idx = st.index(u)
        if idx == 0:
            continue
        v = st[idx - 1]
        if v not in described:
            continue
        o, c, by_cell = oracle.get((b, v), (0.0, 0.0, {}))
        if o >= 50.0 and c > 0:
            leak_want[(b, v)] = {cell: a / c for cell, a in by_cell.items() if a >= 1.0}
        elif o > 0:
            leak_sliver.add((b, v))
    assert set(leak_got) - leak_sliver == set(leak_want), (
        f"leakage wells differ: {sorted((set(leak_got) - leak_sliver) ^ set(leak_want))[:6]}")
    for k, cells in leak_want.items():
        big = {cell for cell, w in cells.items() if w > 1e-5}
        assert big <= set(leak_got[k]) and all(abs(leak_got[k].get(cell, 0.0) - w) <= 1e-5 for cell, w in cells.items()), k
    assert all(abs(sum(v.values()) - 1) <= 1e-9 for v in leak_got.values())
    return n, len(local), len({b for b, kind in got if kind == "unit-wide"}), sorted(with_unit - local), n_leak, len(leak_got)


def oracle_rivers(store):
    """Independent of src/kg/rivers.py (GeoPandas clip and spatial join instead of its loops): the BD
    TOPO reaches of the searched watercourses (the dataset's gauged ones and those the statements
    name) and the canal reaches, clipped to each well's 5 km disc and cut by the BD LISA polygons;
    per (well, watercourse, unit) the length on the unit's outcrop and over its cover, per (well,
    unit) the canal length on its outcrop, for the units the graph attributes to the well; and per
    (well, watercourse) the distance of each gauge to the zone's pieces of that watercourse."""
    import ast
    import csv
    from src.kg.rivers import snapshot
    snap = snapshot("bdtopo_hydro")      # the pinned snapshot the graph was built from
    t = gpd.read_parquet(snap / "troncon_hydrographique.parquet")
    gauges = pd.read_parquet(DATASET_DIR / "gauges.parquet")
    with open(ROOT / "configs" / "exchange_evidence.csv", encoding="utf-8") as f:
        named = {c for r in csv.DictReader(f) for c in r["watercourses"].split(";") if c}
    codes = (set(gauges["code_cours_eau"]) - {"00000000"}) | named
    lines = t[t["code_du_cours_d_eau_bdcarthage"].isin(codes) | (t["nature"] == "Canal")].copy()
    lines["kind"] = np.where(lines["nature"] == "Canal", "canal", "river")
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    wx, wy = l93(wells["x"], wells["y"])
    zones = gpd.GeoDataFrame({"code_bss": wells["code_bss"]},
                             geometry=gpd.points_from_xy(wx, wy).buffer(5000.0, 256), crs=CRS_L93)
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", columns=["codepoly"],
                                  bbox=tuple(zones.total_bounds))
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    stack = pile.sort_values("OrdRelatif").groupby("CodePoly")["CodeEH"].apply(list)
    units = {}
    for b, c in rows(store, """SELECT ?b ?c WHERE { ?a lulcw:attributedEntity ?w ; lulcw:role lulcw:MonitoringRole ;
            lulcw:candidateUnit ?u . ?u lulcw:bdlisaCode ?c . ?w lulcw:bssCode ?b }"""):
        units.setdefault(b, set()).add(c)
    river, canal, dist = {}, {}, {}
    gp = gpd.GeoSeries(gpd.points_from_xy(gauges["longitude_station"], gauges["latitude_station"]),
                       crs=CRS_WGS84).to_crs(CRS_L93)
    for z in zones.itertuples():
        cut = gpd.clip(lines, z.geometry)
        cut = cut[cut.length > 0]
        if cut.empty:
            continue
        j = gpd.sjoin(cut[["cleabs", "code_du_cours_d_eau_bdcarthage", "kind", "geometry"]], poly,
                      predicate="intersects")
        j["part"] = [g.intersection(poly.geometry.loc[k]) for g, k in zip(j.geometry, j["index_right"])]
        j["len"] = [g.length for g in j["part"]]
        j["stack"] = j["codepoly"].astype(str).map(stack)
        for u in units.get(z.code_bss, ()):
            for r in j[j["len"] >= 1.0].itertuples():
                s = r.stack if isinstance(r.stack, list) else []
                if u not in s:
                    continue
                if r.kind == "river":
                    k = (z.code_bss, r.code_du_cours_d_eau_bdcarthage, u, "OnOutcrop" if s[0] == u else "OverCover")
                    river[k] = river.get(k, 0.0) + r.len
                elif s[0] == u:
                    canal[(z.code_bss, u)] = canal.get((z.code_bss, u), 0.0) + r.len
        rv = j[j["kind"] == "river"]
        for code, sub in rv.groupby("code_du_cours_d_eau_bdcarthage"):
            union = gpd.GeoSeries(list(sub["part"])).union_all()
            for i in gauges.index[gauges["code_cours_eau"] == code]:
                dist[(z.code_bss, code, gauges.loc[i, "code_station"])] = union.distance(gp.iloc[i])
    src = (ROOT / "src" / "models" / "features.py").read_text(encoding="utf-8")
    consts = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(src).body
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
              and n.targets[0].id in ("RIVERS", "NEAR_CANDIDATES")}
    pool = set(consts["RIVERS"].values()) | set(consts["NEAR_CANDIDATES"])
    return river, canal, dist, pool


def test_data_rivers(store):
    """CQ5, CQ6, CQ8 against the oracle: every on-outcrop and over-cover association equals the
    oracle's (well, watercourse, unit) lengths (1 m pieces dropped by the graph: 0.2 % or 5 m),
    every canal association the oracle's canal length on the unit's outcrop; the pool equals arm C's
    gauge candidates (src/models/features.py); each river influence comes from the pool gauge on the
    association's watercourse nearest to the zone's pieces (the oracle's distances, ties by code);
    the 45 gauges and their observed training weeks equal the dataset's; every statement of
    configs/exchange_evidence.csv is in the graph with its direction, hedging, method, subject (the
    unit itself or an aggregate's members), units and groundwater body."""
    import csv
    river, canal, dist, pool = oracle_rivers(store)
    got = {}
    for b, code, u, typ, lo, lc in rows(store, """SELECT ?b ?code ?u ?t ?lo ?lc WHERE {
            ?a a lulcw:RiverUnitAssociation ; lulcw:withinExtent ?z ; lulcw:associationWatercourse ?wc ;
               lulcw:associationUnit ?uu ; lulcw:associationType ?tt .
            ?z lulcw:zoneOf ?w . ?w lulcw:bssCode ?b . ?wc lulcw:bdCarthageCode ?code . ?uu lulcw:bdlisaCode ?u .
            OPTIONAL { ?a lulcw:lengthOnOutcropM ?lo } OPTIONAL { ?a lulcw:lengthOverCoverM ?lc }
            BIND (STRAFTER(STR(?tt), "#") AS ?t) }"""):
        if typ != "DocumentedLateral":
            got[(b, code, u, typ)] = lo if typ == "OnOutcrop" else lc
    big = {k: v for k, v in river.items() if v >= 5.0}
    assert set(big) <= set(got) <= set(river), f"associations differ: {sorted(set(big) ^ set(got))[:6]}"
    for k, v in got.items():
        assert abs(v - river[k]) <= max(5.0, 0.002 * river[k]), (k, v, river[k])
    cgot = {(b, u): ln for b, u, ln in rows(store, """SELECT ?b ?u ?l WHERE { ?c a lulcw:CanalUnitAssociation ;
            lulcw:withinExtent ?z ; lulcw:associationUnit ?uu ; lulcw:lengthOnOutcropM ?l .
            ?z lulcw:zoneOf ?w . ?w lulcw:bssCode ?b . ?uu lulcw:bdlisaCode ?u }""")}
    cbig = {k for k, v in canal.items() if v >= 5.0}
    assert cbig <= set(cgot) <= set(canal), f"canal associations differ: {sorted(cbig ^ set(cgot))[:6]}"
    assert all(abs(v - canal[k]) <= max(5.0, 0.002 * canal[k]) for k, v in cgot.items())
    members = {c for (c,) in rows(store, "SELECT ?c WHERE { ?p a lulcw:GaugePool ; lulcw:poolMember ?g . ?g lulcw:gaugeCode ?c }")}
    assert members == pool, (members, pool)
    n_inf = 0
    for b, code, g, typ in rows(store, """SELECT ?b ?code ?g ?t WHERE {
            ?i a lulcw:Influence ; lulcw:mechanism lulcw:RiverExchange ; lulcw:driverEntity ?gg ;
               lulcw:targetEntity ?w ; prov:wasDerivedFrom ?a .
            ?a lulcw:associationWatercourse ?wc ; lulcw:associationType ?tt .
            ?w lulcw:bssCode ?b . ?wc lulcw:bdCarthageCode ?code . ?gg lulcw:gaugeCode ?g
            BIND (STRAFTER(STR(?tt), "#") AS ?t) }"""):
        cand = sorted((round(dist[(b, code, p)]), p) for p in pool if (b, code, p) in dist)
        assert cand and g == cand[0][1], (b, code, g, cand)
        n_inf += 1
    # every association of a watercourse with a pool gauge has its influences
    pool_rivers = {c for c, in rows(store, "SELECT ?c WHERE { ?p lulcw:poolMember ?g . ?g lulcw:onWatercourse/lulcw:bdCarthageCode ?c }")}
    no_inf = rows(store, """SELECT ?a WHERE { ?a a lulcw:RiverUnitAssociation ; lulcw:associationWatercourse ?wc .
            ?wc lulcw:bdCarthageCode ?c . FILTER NOT EXISTS { ?i prov:wasDerivedFrom ?a ; lulcw:mechanism lulcw:RiverExchange } }""")
    assert not [a for (a,) in no_inf if any(f"/river/{c}/" in a for c in pool_rivers)], no_inf[:3]
    gauges = pd.read_parquet(DATASET_DIR / "gauges.parquet")
    split = json.loads((DATASET_DIR / "splits.json").read_text())["train"]
    rw = pd.read_parquet(DATASET_DIR / "rivers_weekly.parquet")
    obs = rw[(rw["week"] >= split[0]) & (rw["week"] <= split[1]) & rw["q_m3s"].notna()].groupby("code_station").size()
    kg_obs = {c: int(n) for c, n in rows(store, """SELECT ?c ?n WHERE { ?g a lulcw:RiverGauge ; lulcw:gaugeCode ?c ;
            lulcw:hasDischargeSeries/lulcw:observedTrainingWeeks ?n }""")}
    assert kg_obs == {c: int(obs.get(c, 0)) for c in gauges["code_station"]}, "gauge coverage differs"
    with open(ROOT / "configs" / "exchange_evidence.csv", encoding="utf-8") as f:
        want = {r["id"]: r for r in csv.DictReader(f)}
    kg = {}
    for sid, m, dr, h, me, kind, u in rows(store, """SELECT ?s ?m ?d ?h ?me ?kind ?u WHERE { ?x a lulcw:ExchangeStatement ;
            lulcw:statedMechanism ?mm ; lulcw:exchangeDirection ?dd ; lulcw:hedging ?hh ; lulcw:evidenceMethod ?ee ;
            lulcw:aboutUnit|lulcw:aggregateMemberUnit ?uu .
            ?uu lulcw:bdlisaCode ?u . OPTIONAL { ?x lulcw:aboutUnit ?su . FILTER (?su = ?uu) }
            BIND (IF(BOUND(?su), "unit", "aggregate") AS ?kind)
            BIND (STRAFTER(STR(?x), "/exchange-statement/") AS ?s) BIND (STRAFTER(STR(?ee), "#") AS ?me)
            BIND (STRAFTER(STR(?mm), "#") AS ?m) BIND (STRAFTER(STR(?dd), "#") AS ?d) BIND (STRAFTER(STR(?hh), "#") AS ?h) }"""):
        kg.setdefault(sid, [m, dr, h, me, set(), set()])
        kg[sid][4].add(kind)
        kg[sid][5].add(u)
    from src.kg.rivers import DIRECTION, HEDGING, METHOD
    assert set(kg) == set(want), set(kg) ^ set(want)
    for sid, r in want.items():
        assert kg[sid] == [r["mechanism"], DIRECTION[r["direction"]], HEDGING[r["hedging"]], METHOD[r["method"]],
                           {r["subject"]}, set(r["units"].split(";"))], (sid, kg[sid])
    bodies = {sid: b for sid, b in rows(store, """SELECT ?s ?b WHERE { ?x lulcw:aboutGroundwaterBody ?gb .
            ?gb lulcw:groundwaterBodyCode ?b . BIND (STRAFTER(STR(?x), "/exchange-statement/") AS ?s) }""")}
    assert bodies == {sid: r["groundwater_body"].removeprefix("FR") for sid, r in want.items() if r["groundwater_body"]}, bodies
    return len(got), len(cgot), n_inf, len(kg)


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
    close = lambda a, b: abs(a - b) <= 1e-4  # noqa: E731  code areas are stored to 1e-6 ha
    assert all(close(got_area[k], v) for k, v in want_area.items()), "class areas differ"
    # the files keep every double exactly (build_kg.ExactTurtle): each stored class area equals the
    # sum of the stored code areas it cites, within the shape's own 1e-6 ha
    sums = rows(store, """SELECT ?ca ?v (SUM(?a) AS ?s) WHERE { ?ca a lulcw:CropClassArea ;
            sosa:hasSimpleResult ?v ; prov:wasDerivedFrom ?o . ?o sosa:hasSimpleResult ?a } GROUP BY ?ca ?v""")
    off = [r[0] for r in sums if abs(r[1] - r[2]) > 1e-6]
    assert len(sums) == len(want_area) and not off, f"stored class areas differ from their codes: {off[:3]}"
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
        return abs(a - b) <= atol
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


def test_data_cq15(store):
    """CQ15 derived parcel-season outcomes on v5 equal T76's Python statuses in irrigation_s2_parcels_v5.parquet."""
    status_map = {
        "ProbablyIrrigated": "positive",
        "NotProbablyIrrigated": "negative",
        "InsufficientSatelliteData": "insufficient_data",
        "WetSeason": "not_applicable",
    }
    p_df = pd.read_parquet(INTERIM / f"irrigation_s2_parcels_{DATASET}.parquet",
                           columns=["year", "ID_PARCEL", "status"])
    p_df["ID_PARCEL"] = p_df["ID_PARCEL"].astype(str)
    want = p_df.set_index(["year", "ID_PARCEL"])["status"].to_dict()

    got = {}
    by_out = {}
    for y, pid, out in rows(store, """SELECT ?y ?pid ?out WHERE {
            ?c a lulcw:IrrigationClassification ; lulcw:seasonYear ?y ;
               lulcw:classifiedParcel/lulcw:sourceIdentifier ?pid ;
               lulcw:irrigationOutcome ?out ; lulcw:derivationRule <rule/probable-irrigation> }"""):
        name = out.split("#")[-1]
        got[(int(y), pid)] = status_map[name]
        by_out[name] = by_out.get(name, 0) + 1
    assert len(got) > 0, "no IrrigationClassification derived in v5"
    mismatches = [(k, v, want.get(k)) for k, v in got.items() if want.get(k) != v]
    assert not mismatches, f"CQ15 outcomes differ from T76 Python statuses: {mismatches[:5]}"
    return len(got), by_out


def main():
    net = ontology_network()
    rules, shapes = rdflib.Graph().parse(RULES), rdflib.Graph().parse(SHAPES)
    test_vocabulary(net)
    g = test_fixtures(rules, shapes, net)
    test_negative_controls(g, shapes, net)
    test_leakage_fixture(rules, shapes, net)
    test_cq15_fixture(rules, shapes, net)
    test_cq10_fixture(rules, shapes, net)
    test_cq16_fixture(rules, shapes, net)
    facts, derived = KG / f"lulcw_kg_{DATASET}.ttl", KG / f"lulcw_kg_{DATASET}_rules.ttl"
    if facts.exists() and derived.exists():
        m = release.check()        # the files must form a validated release (src.kg.release)
        store = store_of(facts, derived)
        test_data(store)
        got, partial, clipped, oracle = test_data_forcing(store)
        print(f"  5. data: CQ4 {len(got)} outcrop coverages (65 search zones + the forcing extent) = the "
              f"GeoPandas oracle on BD LISA and the SAFRAN grid (areas, fractions, weights), mapped outcrop "
              f"of every unit = the whole extract; {len(partial)} search-zone outcrops partly outside the "
              f"cells; the forcing cells clip {', '.join(clipped) or 'no unit'}; release of {m['released']}")
        n, n_local, n_wide, without, n_leak, n_leak_w = test_data_recharge(store, oracle)
        print(f"  6. data: CQ8 {n} diffuse-recharge proxies and {n_leak} overlying-leakage proxies ({n_leak_w} wells) "
              f"= the oracle's cells and weights for the recorded units: "
              f"{n_local} wells local, {n_wide} unit-wide; no local diffuse proxy for "
              f"{', '.join(without)}; signs, proxy, omitted pathways and policy selections as specified")
        n_assoc, n_canal, n_riv, n_st = test_data_rivers(store)
        print(f"  7. data: CQ5/CQ6 {n_assoc} on-outcrop and over-cover river associations and {n_canal} canal "
              f"associations = the GeoPandas oracle (BD TOPO reaches x 5 km discs x BD LISA polygons); "
              f"{n_riv} river influences from the nearest pool gauge (arm C's 5 gauges); gauge training "
              f"coverage = the dataset; {n_st} statements = configs/exchange_evidence.csv")
        if DATASET == "v5":
            n_cls, by_out = test_data_cq15(store)
            print(f"  8. data: CQ15 {n_cls} derived LU-6 parcel-season classifications = irrigation_s2_parcels_v5.parquet "
                  f"({by_out})")
    else:
        print("  4. skipped: run src.kg.build_kg and src.kg.apply_rules first")
    print("test_kg_rules: all checks passed")


if __name__ == "__main__":
    main()
