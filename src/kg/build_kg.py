"""LULC-Water knowledge graph: the source facts and qualified assertions (task 12.5).

    PFE_DATASET=v4 python -m src.kg.build_kg

Instantiates the lulcw module (ontology/lulcw.ttl) from the source tables with rdflib, writes
data/processed/kg/lulcw_kg_<dataset>.ttl and a summary, and checks that pyoxigraph loads it.
Scope: the six MUST competency questions (docs/competency_questions.md), in their work order:

  CQ1, CQ3  piezometers, their monitoring stations and head series, WFD groundwater bodies,
            the BD LISA units (typed by the written rule of docs/ontology_design.md §4.4),
            unit groups, elementary polygons with their stacks, and the monitoring
            attribution of each piezometer (the unit recorded in ADES, or an explicit unknown)
  CQ2, CQ12 groundwater abstraction facilities and their intakes, the pump -> unit
            attributions of task 12.3 with their measured rule evaluations, the annual
            declared volumes (SOSA observations) and the export policies
  CQ7       land use (src/kg/landuse.py, task 12.6): RPG crop codes, crop classes with their
            FAO-56 parameters, a crop demand zone per piezometer, clipped crop areas per RPG
            edition and calendar-year potential irrigation demand
  CQ4       recharge-related forcing (src/kg/forcing.py): SAFRAN weather cells with their weekly
            forcing series, the forcing extent, an outcrop search zone per piezometer, and the
            area of every polygon of the graph inside each cell and reference extent
  CQ5, CQ6  rivers, gauges and canals (src/kg/rivers.py): watercourses and their main stems, the
            river and canal reaches near each piezometer cut by the polygons of the graph, the
            river sections that documents qualify, the gauges with their discharge series, the
            exchange statements of configs/exchange_evidence.csv, the plain's canal intakes

Only facts and assertions whose derivation already exists outside the graph enter here.
The links that the model's graph is made of (stratigraphic relations and `overlies`, well
links, influences, policy selections) are derived inside the graph by the SHACL-AF rules of
task 12.6, so that the equivalence test of task 12.8 (analysis plan §10) compares two
independent derivations: SPARQL on this graph, and pandas on the same tables.

Choices
- Geometry: GeoSPARQL WKT in Lambert-93 (EPSG:2154, metres), the CRS of every distance and
  area of the project; polygon areas as geo:hasMetricArea (m²). Points rounded to 0.1 m,
  polygon vertices to 0.01 m.
- Polygons: those intersecting the plain box, plus those containing a piezometer or a
  facility (a point on a shared edge keeps the first polygon, as in src.kg.pump_attribution),
  plus (CQ5, CQ6) those a river or canal reach of a search zone crosses, plus (CQ4) the polygons
  where a unit of these stacks is mapped at outcrop inside the weather cells or a search zone, to
  closure (the outcrops of units first met in an added stack are added too), so that every unit of
  the graph has its whole outcrop there.
- Monitoring attribution: the ADES record (Hub'Eau codes_bdlisa, in list order), confident if
  the recorded unit is under the point or within EDGE_M of it, else probable (the record rule
  of task 12.3). No record: an explicit unknown; map position alone does not establish what a
  borehole monitors (CQ1).
- Abstraction attribution (CQ2: resolution-aware). The table of task 12.3 has one confidence
  per candidate, measured at unit-group level. Where the exact unit is less certain than its
  group, the candidate becomes two assertions: the exact unit at the confidence its entity
  precision supports, and the group at the measured group confidence. flag_true: group
  precision 0.947, entity 0.632 (19 recorded boreholes), so the exact alluvial entity is
  "possible" and the group "alluvium" keeps "probable". Facilities absent from dataset v4
  (no attribution was computed) get an explicit unknown with the reason.
- Annual records: every groundwater row of the BNPE snapshot as declared (no imputation,
  no harmonisation: those are model inputs, kept in parquet), with its acquisition mode as
  sosa:usedProcedure (direct measurement, indirect measurement, flat-rate volume).
"""
import json
import math
import subprocess
from datetime import date, datetime
from urllib.parse import quote

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rdflib
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD
from rdflib.plugins.serializers.turtle import TurtleSerializer
from shapely import to_wkt
from shapely.geometry import box

from src.analysis.bdlisa_profile import GPKG, group_of
from src.analysis.bnpe_profile import load as load_bnpe
from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, PROCESSED, RAW, ROOT
from src.kg import forcing, landuse, rivers
from src.kg import pump_attribution as pa

L = Namespace("https://w3id.org/lulcw#")
D = "https://w3id.org/lulcw/data/"
SOSA = Namespace("http://www.w3.org/ns/sosa/")
PROV = Namespace("http://www.w3.org/ns/prov#")
TIME = Namespace("http://www.w3.org/2006/time#")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
DCT = Namespace("http://purl.org/dc/terms/")
EPSG2154 = "<http://www.opengis.net/def/crs/EPSG/0/2154> "
OUT = PROCESSED / "kg"
BNPE_SNAPSHOT = "2026-10-20"
PLAIN_MARGIN_DEG = 0.04          # the facility zone of src.dataset.build (~3 km)
EDGE_M = pa.EDGE_M
USE = {"AEP": L.DrinkingWaterUse, "IRR": L.IrrigationUse, "IND": L.IndustryUse,
       "CAN": L.CanalSupplyUse, "ENE": L.EnergyUse}
USE_OF_NAME = {"drinking water": L.DrinkingWaterUse, "irrigation": L.IrrigationUse,
               "industry": L.IndustryUse, "canals": L.CanalSupplyUse, "energy": L.EnergyUse}
CONF = {"confident": L.Confident, "probable": L.Probable, "possible": L.Possible}
RANK = {"possible": 0, "probable": 1, "confident": 2}
ALLUVIUM = "alluvium"            # recent or ancient: the group of the flag rules' evaluation
GROUP_LABELS = {                 # group -> (English, French)
    "recent alluvium": ("recent alluvium (Têt, Agly, Réart, Tech)", "alluvions récentes"),
    "ancient alluvium": ("ancient alluvium", "alluvions anciennes"),
    "Pliocene multilayer": ("Pliocene multilayer", "multicouche pliocène"),
    "Corbières karst": ("Corbières karst", "karst des Corbières"),
    ALLUVIUM: ("alluvium, recent or ancient", "alluvions récentes ou anciennes"),
}
# releases: key -> (label, retrieval or build date, where; dates from data/README.md)
RELEASES = {
    "hubeau-piezo-stations": ("Hub'Eau niveaux_nappes stations, département 66", "2026-10-05",
                              "https://hubeau.eaufrance.fr/api/v1/niveaux_nappes/stations"),
    "hubeau-qualite-stations": ("Hub'Eau qualite_nappes stations (ADES water points), "
                                "département 66", "2026-10-23",
                                "https://hubeau.eaufrance.fr/api/v1/qualite_nappes/stations"),
    f"bnpe-{BNPE_SNAPSHOT}": ("Hub'Eau prelevements (BNPE): withdrawal points and annual "
                              "volumes, département 66", BNPE_SNAPSHOT,
                              "https://hubeau.eaufrance.fr/api/v1/prelevements/"),
    "bdlisa-v3-occ": ("BD LISA V3, Occitanie extract (GeoPackage)", "2026-10-05",
                      "https://bdlisa.eaufrance.fr"),
}


def iri(*parts):
    return URIRef(D + "/".join(quote(str(p), safe="") for p in parts))


def dbl(x, nd=None):
    return Literal(float(round(x, nd) if nd is not None else x), datatype=XSD.double)


class ExactTurtle(TurtleSerializer):
    """Turtle that writes every xsd:double exactly. rdflib writes a double as f"{x:e}", 7
    significant digits (2786.8495 ha becomes 2786.850), so a stored class area no longer equals
    the sum of the stored code areas it cites, and the files fail shapes that the graph in memory
    passes (2,068 of 5,465 class areas on 2026-10-26). Here a double is the shortest decimal that
    reads back as the same number (Python's repr), with an exponent so that it stays a double."""

    def label(self, node, position):
        if isinstance(node, Literal) and node.datatype == XSD.double:
            try:
                v = float(node)
            except ValueError:
                v = math.nan
            if math.isfinite(v):
                s = repr(v)
                return s if "e" in s or "E" in s else s + "e0"
        return super().label(node, position)


def write_turtle(graph, path):
    with open(path, "wb") as f:
        ExactTurtle(graph).serialize(f, encoding="utf-8")


class KG:
    """An rdflib graph with the project's prefixes and a few helpers."""

    def __init__(self):
        self.g = rdflib.Graph()
        for p, ns in (("lulcw", str(L)), ("lulcwd", D), ("sosa", str(SOSA)), ("prov", str(PROV)),
                      ("time", str(TIME)), ("geo", str(GEO)), ("dcterms", str(DCT)),
                      ("skos", str(SKOS))):
            self.g.bind(p, ns)

    def add(self, s, p, o):
        if o is not None:
            self.g.add((s, p, o))

    def node(self, s, cls, label=None, lang=None, **props):
        self.g.add((s, RDF.type, cls))
        if label is not None:
            self.g.add((s, RDFS.label, Literal(label, lang=lang)))
        return s

    def point(self, owner, kind, key, x, y):
        geom = iri("geometry", kind, key)
        self.node(geom, GEO.Geometry)
        self.add(geom, GEO.asWKT, Literal(f"{EPSG2154}POINT({x:.1f} {y:.1f})", datatype=GEO.wktLiteral))
        self.add(owner, GEO.hasGeometry, geom)


def git_version(paths=("src/kg", "ontology")):
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=ROOT).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *paths], capture_output=True,
                           text=True, cwd=ROOT).stdout.strip()
    return head + ("+uncommitted" if dirty else "")


def file_date(path):
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


# ----------------------------------------------------------------------------- provenance
def provenance(kg, versions):
    rel = {}
    for key, (label, day, where) in RELEASES.items():
        r = kg.node(iri("release", key), L.DataRelease, label, "en")
        kg.add(r, L.retrievalDate, Literal(day, datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(f"Source: {where}", lang="en"))
        rel[key] = r
    for key, label, path in (
            (f"dataset-{DATASET}", f"model-ready dataset {DATASET}", DATASET_DIR / "meta.json"),
            ("pump-attribution", "pump-to-unit attribution tables (task 12.3)",
             INTERIM / "pump_unit_attribution.parquet")):
        r = kg.node(iri("release", key), L.DataRelease, label, "en")
        kg.add(r, L.releaseDate, Literal(file_date(path), datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(f"Stored in {path.relative_to(ROOT).parent}", lang="en"))
        rel[key] = r

    rules = {
        "piezometer-record": "Monitored unit of a piezometer: the BD LISA entity recorded for its "
            "station in ADES (Hub'Eau codes_bdlisa). Confident when that entity is in the BD LISA "
            f"stack under the point or within {EDGE_M:.0f} m of it, else probable.",
        "pump-attribution": "Pump-to-unit attribution of task 12.3 (src/kg/pump_attribution.py): "
            "the first applicable rule gives the main candidate; no applicable rule gives an "
            "explicit unknown.",
        "pump-record": "The BD LISA entity of the ADES quality station that has the facility's "
            f"BSS code: confident if under the point or within {EDGE_M:.0f} m, else probable.",
        "pump-record-depth": "A recent-alluvium record deeper than "
            f"{pa.ALLUVIUM_MAX_DEPTH_M:.0f} m (or named 'profond') above the Pliocene: Pliocene "
            "(probable); the recorded entity is kept as rank 2 (possible).",
        "pump-flag-true": "No record, BNPE nappe_accompagnement True: the alluvial entity under "
            f"the point, else the nearest within {EDGE_M:.0f} m. Confidence measured on the "
            "recorded boreholes, at unit-group and exact-unit resolution.",
        "pump-flag-false": "No record, BNPE nappe_accompagnement False, Pliocene in the stack "
            "under the point: Pliocene (671AA00). Confidence measured on the recorded boreholes.",
        "pump-dug-well": "No record, no flag, named PUITS, alluvium at the point: that alluvial "
            "entity (possible, not measured).",
        "pump-single-unit": "No record, no flag, one entity in the stack under the point: that "
            "entity (possible, not measured).",
        "unit-typing": "Typing of BD LISA entities (docs/ontology_design.md §4.4): 671AA00 "
            "multilayer aquifer system; theme alluvial or ancient alluvium (671AB) alluvial "
            "aquifer; medium karstic karst aquifer; nature 7 confining unit; otherwise "
            "hydrogeological unit. BD LISA's nature code alone never types a unit.",
        "point-in-polygon": "Location of a point in a BD LISA elementary polygon (Lambert-93, "
            "within; a point on a shared edge keeps the first polygon).",
    }
    rule = {k: kg.node(iri("rule", k), L.DerivationRule, k.replace("-", " "), "en")
            for k in rules}
    for k, text in rules.items():
        kg.add(rule[k], RDFS.comment, Literal(text, lang="en"))
        kg.add(rule[k], L.ruleVersion, Literal(versions["pump"] if k.startswith("pump")
                                               else versions["kg"]))
    ex_pump = kg.node(iri("execution", "pump-attribution"), L.RuleExecution,
                      "pump-to-unit attribution run (task 12.3)", "en")
    kg.add(ex_pump, L.codeVersion, Literal(versions["pump"]))
    for k in ("hubeau-qualite-stations", f"bnpe-{BNPE_SNAPSHOT}", "bdlisa-v3-occ",
              f"dataset-{DATASET}"):
        kg.add(ex_pump, PROV.used, rel[k])
    ex_kg = kg.node(iri("execution", f"kg-build-{DATASET}"), L.RuleExecution,
                    f"knowledge-graph build, dataset {DATASET} (task 12.5)", "en")
    kg.add(ex_kg, L.codeVersion, Literal(versions["kg"]))
    for r in rel.values():
        kg.add(ex_kg, PROV.used, r)
    kg.add(rel["pump-attribution"], PROV.wasGeneratedBy, ex_pump)
    return rel, rule, {"pump": ex_pump, "kg": ex_kg}


def record(kg, kind, ident, release):
    """A SourceRecord: one row of a release, by its original identifier."""
    r = iri("record", kind, ident)
    kg.node(r, L.SourceRecord)
    kg.add(r, L.sourceIdentifier, Literal(str(ident)))
    kg.add(r, L.inRelease, release)
    return r


def extents(kg):
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    m = PLAIN_MARGIN_DEG
    out = {}
    for key, bb, label in (
            ("plain-box", PLAIN_BBOX, "Roussillon plain box (lon 2.55-3.06, lat 42.50-42.88): "
             "the piezometer working set and the BD LISA polygons of the plain"),
            ("plain-box-margin", (lon0 - m, lat0 - m, lon1 + m, lat1 + m),
             "Roussillon plain box with a 0.04 degree margin (about 3 km): the abstraction "
             "facilities of the plain (zone 'plain' of the dataset)")):
        poly = gpd.GeoSeries([box(*bb)], crs=CRS_WGS84).to_crs(CRS_L93).iloc[0]
        f = kg.node(iri("extent", key), GEO.Feature, label, "en")
        geom = kg.node(iri("geometry", "extent", key), GEO.Geometry)
        kg.add(geom, GEO.asWKT, Literal(EPSG2154 + to_wkt(poly, rounding_precision=1),
                                        datatype=GEO.wktLiteral))
        kg.add(f, GEO.hasGeometry, geom)
        out[key] = (f, poly)
    return out


# ------------------------------------------------------------------- units and polygons
def unit_class(code, t):
    """The written typing rule (docs/ontology_design.md §4.4); t = BD LISA TME row or None."""
    hits = []
    if code == pa.PLIOCENE:
        hits.append(L.MultilayerAquiferSystem)
    if code.startswith("671AB") or (t is not None and t["themeeh"] == "1"):
        hits.append(L.AlluvialAquifer)
    if t is not None and t["milieueh"] == "3":
        hits.append(L.KarstAquifer)
    if t is not None and t["natureeh"] == "7":
        hits.append(L.ConfiningUnit)
    if len(hits) > 1 and hits[0] != L.MultilayerAquiferSystem:
        raise ValueError(f"{code}: the typing rule gives several disjoint types {hits}")
    return hits[0] if hits else L.HydrogeologicalUnit


def load_bdlisa(points_l93, aoi=None):
    """TME (level 3), stacks, and the polygons of the plain, under a point or meeting `aoi`."""
    tme = pyogrio.read_dataframe(GPKG, layer="TME", read_geometry=False)
    tme = tme[tme["niveaueh"].astype(str) == "3"].copy()
    for c in ("natureeh", "themeeh", "milieueh"):
        tme[c] = tme[c].astype(str).str.strip()
    tme = tme.set_index("codeeh")
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    plain_box = gpd.GeoSeries([box(*PLAIN_BBOX)], crs=CRS_WGS84).to_crs(CRS_L93).iloc[0]
    bounds = np.minimum(points_l93.total_bounds[:2], plain_box.bounds[:2]) - EDGE_M
    upper = np.maximum(points_l93.total_bounds[2:], plain_box.bounds[2:]) + EDGE_M
    if aoi is not None:
        bounds, upper = np.minimum(bounds, aoi.bounds[:2]), np.maximum(upper, aoi.bounds[2:])
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES",
                                  bbox=(*bounds, *upper))[["codepoly", "geometry"]]
    assert poly["codepoly"].is_unique
    return tme, pile, poly, plain_box


def locate(points, poly):
    """Point (GeoSeries, L93) -> codepoly of the containing polygon (first on shared edges)."""
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=points), poly, how="left", predicate="within")
    return j[~j.index.duplicated()]["codepoly"].reindex(points.index)


def units_and_polygons(kg, rel, tme, pile, poly, used_polys, plain_box, extent, extra_units):
    keep = poly[poly.intersects(plain_box) | poly["codepoly"].isin(used_polys)].copy()
    stacks = (pile[pile["CodePoly"].isin(set(keep["codepoly"]))].sort_values(["CodePoly", "OrdRelatif"])
              .groupby("CodePoly")[["CodeEH", "OrdRelatif"]].apply(lambda d: list(zip(d.CodeEH, d.OrdRelatif))))
    codes = sorted({c for s in stacks for c, _ in s} | set(extra_units))
    unit = {}
    for code in codes:
        t = tme.loc[code] if code in tme.index else None
        u = kg.node(iri("unit", code), unit_class(code, t),
                    t["libelleeh"] if t is not None else None, "fr")
        kg.add(u, L.bdlisaCode, Literal(code))
        if t is not None:
            for p, c in ((L.bdlisaNatureCode, "natureeh"), (L.bdlisaThemeCode, "themeeh"),
                         (L.bdlisaMediumCode, "milieueh")):
                if t[c].isdigit():
                    kg.add(u, p, Literal(int(t[c]), datatype=XSD.integer))
            kg.add(u, PROV.wasDerivedFrom, record(kg, "bdlisa-tme", code, rel["bdlisa-v3-occ"]))
        else:
            kg.add(u, RDFS.comment, Literal("Not in the BD LISA V3 Occitanie extract: typed "
                                            "only as a hydrogeological unit.", lang="en"))
        unit[code] = u
    groups = {}
    for name, (en, fr) in GROUP_LABELS.items():
        members = [c for c in codes if group_of(c) == name
                   or (name == ALLUVIUM and group_of(c) in pa.ALLUVIAL)]
        g = kg.node(iri("unit-group", name.lower().replace(" ", "-").replace("è", "e")),
                    L.HydrogeologicalUnitGroup, en, "en")
        kg.add(g, RDFS.label, Literal(fr, lang="fr"))
        for c in members:
            kg.add(g, L.hasMemberUnit, unit[c])
        groups[name] = g
    for _, p in keep.iterrows():
        cp = p["codepoly"]
        assert str(cp).isdigit(), f"polygon code {cp} is not an integer"
        pn = kg.node(iri("polygon", cp), L.ElementaryPolygon)
        kg.add(pn, L.polygonCode, Literal(int(cp), datatype=XSD.integer))
        kg.add(pn, L.inRelease, rel["bdlisa-v3-occ"])
        kg.add(pn, GEO.hasMetricArea, dbl(p.geometry.area, 1))
        geom = kg.node(iri("geometry", "polygon", cp), GEO.Geometry)
        kg.add(geom, GEO.asWKT, Literal(EPSG2154 + to_wkt(p.geometry, rounding_precision=2),
                                        datatype=GEO.wktLiteral))
        kg.add(pn, GEO.hasGeometry, geom)
        if p.geometry.intersects(plain_box):
            kg.add(pn, GEO.sfIntersects, extent)
        for code, order in stacks.get(cp, []):
            layer = kg.node(iri("polygon", cp, "layer", int(order)), L.StackLayer)
            kg.add(pn, L.hasStackLayer, layer)
            kg.add(layer, L.layerUnit, unit[code])
            kg.add(layer, L.layerOrder, Literal(int(order), datatype=XSD.integer))
    return unit, groups, {cp: [c for c, _ in s] for cp, s in stacks.items()}, keep


# -------------------------------------------------------------------------- piezometers
def recorded_codes(raw, code_bss):
    """The BD LISA codes recorded for a station, in Hub'Eau's order. The cached table keeps a
    single code as a string (no station of dept 66 lists several: raw JSON, 2026-10-24)."""
    v = raw["codes_bdlisa"].get(code_bss)
    if isinstance(v, str):
        return [v] if v else []
    return [c for c in v if c] if isinstance(v, (list, np.ndarray)) else []


def recorded_near(code, pt, poly, pile):
    """Is the recorded unit in a polygon under the point or within EDGE_M of it?"""
    cps = set(pile.loc[pile["CodeEH"] == code, "CodePoly"])
    cand = poly[poly["codepoly"].isin(cps)]
    return bool(len(cand)) and float(cand.distance(pt).min()) <= EDGE_M


def piezometers(kg, rel, rule, ex, unit, wells, pts, cps, stacks, poly, pile, extent):
    stations = pd.read_parquet(INTERIM / "piezo_stations.parquet").set_index("code_bss")
    raw = pd.read_parquet(RAW / "hubeau" / "stations_66.parquet").set_index("code_bss")
    heads = pd.read_parquet(DATASET_DIR / "heads_weekly.parquet", columns=["code_bss", "week", "head"])
    cover = heads.dropna(subset=["head"]).groupby("code_bss")["week"].agg(["min", "max"])
    bodies, n_unknown = {}, 0
    for i, w in wells.iterrows():
        key = w["bss_id"] if isinstance(w["bss_id"], str) and w["bss_id"] else w["code_bss"]
        pz = kg.node(iri("piezometer", key), L.Piezometer,
                     w["libelle_pe"] if isinstance(w["libelle_pe"], str) else w["code_bss"])
        kg.add(pz, L.bssCode, Literal(w["code_bss"]))
        if isinstance(w["bss_id"], str):
            kg.add(pz, L.bssId, Literal(w["bss_id"]))
        if pd.notna(w["profondeur_investigation"]):
            kg.add(pz, L.investigationDepthM, dbl(w["profondeur_investigation"]))
        kg.point(pz, "piezometer", key, pts.x[i], pts.y[i])
        src = record(kg, "hubeau-piezo-station", w["code_bss"], rel["hubeau-piezo-stations"])
        kg.add(pz, PROV.wasDerivedFrom, src)
        if pd.notna(cps[i]):
            kg.add(pz, L.locatedInPolygon, iri("polygon", cps[i]))
        lon0, lat0, lon1, lat1 = PLAIN_BBOX
        if lon0 <= w["x"] <= lon1 and lat0 <= w["y"] <= lat1:
            kg.add(pz, GEO.sfWithin, extent)
        st = stations.loc[w["code_bss"]]
        if isinstance(st["codes_masse_eau_edl"], str) and st["codes_masse_eau_edl"]:
            code = st["codes_masse_eau_edl"]
            if code not in bodies:
                bodies[code] = kg.node(iri("groundwater-body", code), L.GroundwaterBody,
                                       st["noms_masse_eau_edl"], "fr")
                kg.add(bodies[code], L.groundwaterBodyCode, Literal(code))
            kg.add(pz, L.inGroundwaterBody, bodies[code])

        sta = kg.node(iri("station", key), L.MonitoringStation)
        kg.add(sta, L.hostedBy, pz)
        kg.add(sta, PROV.wasDerivedFrom, src)
        alt = pd.to_numeric(w["altitude_station"], errors="coerce")
        if pd.notna(alt):
            kg.add(sta, L.groundElevationM, dbl(alt))
        se = kg.node(iri("series", f"head-weekly-{DATASET}", key), L.ObservationSeries)
        kg.add(sta, L.hasObservationSeries, se)
        kg.add(se, L.seriesVariable, L.GroundwaterHead)
        kg.add(se, L.verticalDatum, Literal("NGF-IGN69"))
        kg.add(se, L.temporalResolution, Literal("P7D"))
        if w["code_bss"] in cover.index:
            c0, c1 = cover.loc[w["code_bss"]]
            kg.add(se, L.coverageStart, Literal(c0.date().isoformat(), datatype=XSD.date))
            kg.add(se, L.coverageEnd, Literal(c1.date().isoformat(), datatype=XSD.date))
        kg.add(se, L.storedIn, Literal(f"{(DATASET_DIR / 'heads_weekly.parquet').relative_to(ROOT)}"
                                       f" [code_bss = {w['code_bss']}]"))
        kg.add(se, L.qualityPolicy, Literal(
            "weekly mean of the daily Hub'Eau values (week ending Sunday); values qualified "
            "'Incorrecte' or 'Qualification non définissable' dropped (dataset v4)"))
        kg.add(se, L.inRelease, rel[f"dataset-{DATASET}"])

        codes = recorded_codes(raw, w["code_bss"])
        assert codes[:1] == ([w["code_bdlisa"]] if isinstance(w["code_bdlisa"], str) else []), \
            f"{w['code_bss']}: recorded unit differs from the dataset's"
        stack = stacks.get(cps[i], []) if pd.notna(cps[i]) else []
        where = (f"BD LISA stack under the point: {' > '.join(stack)} (polygon {cps[i]})"
                 if stack else "no BD LISA polygon under the point in the Occitanie extract")
        if not codes:
            a = attribution(kg, ("piezometer", key, 1), pz, L.MonitoringRole, rule["piezometer-record"],
                            ex["kg"], None, None, None, L.DerivedAssertion, [src])
            kg.add(a, L.unknownReason, Literal(
                "no BD LISA entity recorded for the station in ADES; map position alone does not "
                "establish the monitored unit"))
            kg.add(a, RDFS.comment, Literal(where, lang="en"))
            n_unknown += 1
        for rank, code in enumerate(codes, start=1):
            near = recorded_near(code, pts[i], poly, pile)
            a = attribution(kg, ("piezometer", key, rank), pz, L.MonitoringRole,
                            rule["piezometer-record"], ex["kg"], unit[code], L.ExactUnitResolution,
                            "confident" if near else "probable", L.ReportedObservation, [src],
                            rank=rank)
            kg.add(a, RDFS.comment, Literal(
                f"recorded entity {code}; {where}; recorded entity "
                + ("under the point or within 1000 m" if near else "not within 1000 m of the point")
                + (f"; investigation depth {w['profondeur_investigation']:g} m"
                   if pd.notna(w["profondeur_investigation"]) else "; investigation depth unknown"),
                lang="en"))
    return len(bodies), n_unknown


def attribution(kg, key, entity, role, rule, execution, target, resolution, confidence, evidence,
                sources, rank=1, status=L.CandidateStatus):
    """A UnitAttribution node; target = a unit (exact) or a group, None for an unknown."""
    a = kg.node(iri("attribution", *key), L.UnitAttribution)
    kg.add(a, L.attributedEntity, entity)
    kg.add(a, L.role, role)
    kg.add(a, L.derivationRule, rule)
    kg.add(a, PROV.wasGeneratedBy, execution)
    kg.add(a, L.assessmentStatus, status)
    kg.add(a, L.evidenceKind, evidence)
    kg.add(a, L.rank, Literal(rank, datatype=XSD.integer))
    for s in sources:
        kg.add(a, PROV.wasDerivedFrom, s)
    if target is not None:
        kg.add(a, L.candidateGroup if resolution == L.UnitGroupResolution else L.candidateUnit, target)
        kg.add(a, L.resolution, resolution)
        kg.add(a, L.confidence, CONF[confidence])
    return a


# --------------------------------------------------------------------------- facilities
def measured(fired, precision, use_ok):
    """Confidence of a measured rule at one resolution (thresholds of task 12.3)."""
    ok = fired >= pa.MIN_EVAL and precision >= pa.PRECISION_PROBABLE and use_ok
    return "probable" if ok else "possible"


def evaluations(kg, rule, ex, ev):
    out = {}
    for name, r in ev["rules"].items():
        uses = [USE_OF_NAME[u] for u in r["by_use"]]
        for res, prec, note in (
                (L.UnitGroupResolution, r["precision_group"],
                 "unit group: alluvium (recent or ancient) or Pliocene multilayer"),
                (L.ExactUnitResolution, r["precision_entity"], "exact BD LISA entity")):
            e = kg.node(iri("evaluation", f"pump-{name.replace('_', '-')}",
                            "unit-group" if res == L.UnitGroupResolution else "exact-unit"),
                        L.RuleEvaluation)
            kg.add(e, L.evaluatedRule, rule[f"pump-{name.replace('_', '-')}"])
            kg.add(e, L.resolution, res)
            kg.add(e, L.precision, dbl(prec))
            kg.add(e, L.sampleSize, Literal(r["fires_on"], datatype=XSD.integer))
            for u in uses:
                kg.add(e, L.applicableUse, u)
            kg.add(e, PROV.wasGeneratedBy, ex["pump"])
            kg.add(e, RDFS.comment, Literal(
                f"Reference: the recorded boreholes (ADES quality stations, after the depth "
                f"check); resolution {note}; group precision against the raw record "
                f"{r['precision_group_raw_record']}; uses with at least {pa.MIN_USE_EVAL} cases: "
                f"{', '.join(r['by_use']) or 'none'}.", lang="en"))
            out[(name, res)] = (prec, r["fires_on"], set(r["by_use"]))
    return out


def facilities(kg, rel, rule, ex, unit, groups, fac, pts, cps, stacks, extent, ev_table):
    attr = pd.read_parquet(INTERIM / "pump_unit_attribution.parquet")
    evid = pd.read_parquet(INTERIM / "pump_unit_evidence.parquet").set_index("code_ouvrage")
    bnpe_pts = pd.read_parquet(RAW / "hubeau_bnpe" / BNPE_SNAPSHOT / "points_prelevement_66.parquet")
    bnpe_pts = bnpe_pts.set_index("code_ouvrage")
    release = rel[f"bnpe-{BNPE_SNAPSHOT}"]
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    m = PLAIN_MARGIN_DEG
    counts = {"group_split": 0, "absent": 0}
    for i, f in fac.iterrows():
        code = f["code_ouvrage"]
        fn = kg.node(iri("facility", code), L.AbstractionFacility, f["nom_ouvrage"], "fr")
        kg.add(fn, L.bnpeCode, Literal(code))
        kg.add(fn, L.waterSource, L.GroundwaterSource)
        if isinstance(f["uri_ouvrage"], str) and f["uri_ouvrage"].startswith("https://id.eaufrance.fr/"):
            kg.add(fn, RDFS.seeAlso, URIRef(f["uri_ouvrage"]))   # Sandre IRI, listed in the source
        kg.point(fn, "facility", code, pts.x[i], pts.y[i])
        if pd.notna(cps[i]):
            kg.add(fn, L.locatedInPolygon, iri("polygon", cps[i]))
        if lon0 - m <= f["longitude"] <= lon1 + m and lat0 - m <= f["latitude"] <= lat1 + m:
            kg.add(fn, GEO.sfWithin, extent)
        p = bnpe_pts.loc[code]
        src = record(kg, "bnpe-point", p["code_point_prelevement"], release)
        kg.add(fn, PROV.wasDerivedFrom, src)
        it = kg.node(iri("intake", p["code_point_prelevement"]), L.Intake,
                     p["nom_point_prelevement"], "fr")
        kg.add(fn, L.hasIntake, it)
        kg.add(it, PROV.wasDerivedFrom, src)
        if isinstance(p["code_bss_point_eau"], str) and p["code_bss_point_eau"]:
            kg.add(it, L.bssCode, Literal(p["code_bss_point_eau"]))

        rows = attr[attr["code_ouvrage"] == code]
        if rows.empty:
            a = attribution(kg, ("facility", code, 1), fn, L.AbstractionRole, rule["pump-attribution"],
                            ex["kg"], None, None, None, L.DerivedAssertion, [src])
            kg.add(a, L.unknownReason, Literal(
                f"not attributed by task 12.3: the facility is absent from dataset {DATASET} "
                "(its declared volumes are all zero or have no usage code)"))
            counts["absent"] += 1
            continue
        e = evid.loc[code]
        sources = [src]
        if isinstance(e["rec_unit"], str):
            sources.append(record(kg, "ades-quality-station", e["code_bss_point_eau"],
                                  rel["hubeau-qualite-stations"]))
        if pd.notna(cps[i]):
            sources.append(iri("polygon", cps[i]))
        note = (f"BNPE nappe_accompagnement: {e['flag']}; BD LISA stack under the point: "
                f"{e['stack'] or 'none'}"
                + (f"; ADES record {e['code_bss_point_eau']}: {e['rec_unit']}"
                   + (f" at {e['rec_depth_m']:g} m" if pd.notna(e["rec_depth_m"]) else "")
                   if isinstance(e["rec_unit"], str) else "")
                + f"; main use 2012-2024: {e['usage_main']}")
        use = USE_OF_NAME.get(e["usage_main"])
        for _, r in rows.iterrows():
            rname = r["rule"]
            key = ("facility", code, int(r["rank"]))
            if not isinstance(r["unit"], str):
                a = attribution(kg, key, fn, L.AbstractionRole,
                                rule.get(f"pump-{rname.replace('_', '-').removesuffix('-no-alluvium').removesuffix('-no-pliocene')}",
                                         rule["pump-attribution"]),
                                ex["pump"], None, None, None, L.DerivedAssertion, sources,
                                rank=int(r["rank"]))
                kg.add(a, L.unknownReason, Literal({
                    "flag_true_no_alluvium": "BNPE nappe_accompagnement True, but no alluvial "
                        f"unit under the point or within {EDGE_M:.0f} m",
                    "flag_false_no_pliocene": "BNPE nappe_accompagnement False, and the Pliocene "
                        "is not in the BD LISA stack under the point",
                }.get(rname, "no ADES record, no BNPE nappe_accompagnement flag, and no rule "
                             "applies to the stack under the point")))
                kg.add(a, RDFS.comment, Literal(note, lang="en"))
                continue
            conf, evk = r["confidence"], L.DerivedAssertion
            if rname == "record":
                evk = L.ReportedObservation
            group_conf = None
            if rname in ("flag_true", "flag_false"):
                prec_g, n, uses = ev_table[(rname, L.UnitGroupResolution)]
                prec_e, _, _ = ev_table[(rname, L.ExactUnitResolution)]
                use_ok = e["usage_main"] in uses
                assert conf == measured(n, prec_g, use_ok), f"{code}: table and evaluation differ"
                exact = measured(n, prec_e, use_ok)
                if RANK[exact] < RANK[conf]:
                    group_conf, conf = conf, exact
            a = attribution(kg, key, fn, L.AbstractionRole,
                            rule[f"pump-{rname.replace('_', '-')}"], ex["pump"], unit[r["unit"]],
                            L.ExactUnitResolution, conf, evk, sources, rank=int(r["rank"]))
            kg.add(a, RDFS.comment, Literal(note, lang="en"))
            if conf == "probable" and use is not None and rname in ("flag_true", "flag_false"):
                kg.add(a, L.applicableUse, use)
            if group_conf is not None:
                grp = ALLUVIUM if rname == "flag_true" else group_of(r["unit"])
                ga = attribution(kg, key + ("group",), fn, L.AbstractionRole,
                                 rule[f"pump-{rname.replace('_', '-')}"], ex["pump"], groups[grp],
                                 L.UnitGroupResolution, group_conf, evk, sources,
                                 rank=int(r["rank"]))
                kg.add(ga, RDFS.comment, Literal(note + f"; the exact entity {r['unit']} is a "
                                                 "member of this group", lang="en"))
                if group_conf == "probable" and use is not None:
                    kg.add(ga, L.applicableUse, use)
                counts["group_split"] += 1
    return counts


def annual_records(kg, rel, d):
    """Every groundwater row of the BNPE snapshot, as declared."""
    release = rel[f"bnpe-{BNPE_SNAPSHOT}"]
    years = {}
    for y in sorted(d["annee"].unique()):
        y = int(y)
        iv = kg.node(iri("interval", "year", y), TIME.ProperInterval)
        for p, day in ((TIME.hasBeginning, f"{y}-01-01"), (TIME.hasEnd, f"{y + 1}-01-01")):
            inst = kg.node(iri("instant", day), TIME.Instant)
            kg.add(inst, TIME.inXSDDate, Literal(day, datatype=XSD.date))
            kg.add(iv, p, inst)
        kg.add(iv, RDFS.comment, Literal(f"calendar year {y}, start inclusive, end exclusive",
                                         lang="en"))
        years[y] = iv
    proc = {}
    for code, label in d.groupby("code_mode_obtention_volume")["libelle_mode_obtention_volume"].first().items():
        proc[code] = kg.node(iri("procedure", f"bnpe-{code.lower()}"), SOSA.Procedure, label, "fr")
        kg.add(proc[code], RDFS.comment, Literal(
            f"BNPE volume acquisition mode {code} (code_mode_obtention_volume)", lang="en"))
    for r in d.itertuples(index=False):
        use = r.code_usage if isinstance(r.code_usage, str) else "none"
        o = kg.node(iri("abstraction", r.code_ouvrage, int(r.annee), use), L.AnnualAbstractionRecord)
        kg.add(o, SOSA.hasFeatureOfInterest, iri("facility", r.code_ouvrage))
        kg.add(o, SOSA.observedProperty, L.DeclaredAnnualVolume)
        kg.add(o, SOSA.hasSimpleResult, dbl(r.volume))
        kg.add(o, SOSA.phenomenonTime, years[int(r.annee)])
        kg.add(o, SOSA.usedProcedure, proc.get(r.code_mode_obtention_volume))
        kg.add(o, L.waterUse, USE.get(r.code_usage))
        kg.add(o, L.waterSource, L.GroundwaterSource)
        kg.add(o, L.recordKind, L.DeclaredRecord)
        kg.add(o, L.inRelease, release)
        if use == "none":
            kg.add(o, RDFS.comment, Literal("usage code missing in the source", lang="en"))
    return len(d)


def policies(kg):
    admits = {"main": (L.Confident, L.Probable), "confident-only": (L.Confident,),
              "all-links": (L.Confident, L.Probable, L.Possible)}
    for key, label, text in (
            ("main", "main runs: confident and probable links",
             "Selects the qualified attributions whose confidence is confident or probable, at the "
             "resolution they were assessed: a unit-group attribution links to its group, never "
             "to one exact unit. Decided by Assil on 2026-10-24 (72 % of the plain's declared "
             "groundwater volume against 27 % for confident links only)."),
            ("confident-only", "sensitivity: confident links only",
             "Selects the qualified attributions whose confidence is confident."),
            ("all-links", "sensitivity: all links",
             "Selects every attribution with a target (confident, probable, possible). Alternative "
             "candidates of one facility are never summed in volume accounting.")):
        p = kg.node(iri("policy", key), L.ExportPolicy, label, "en")
        kg.add(p, RDFS.comment, Literal(text, lang="en"))
        kg.add(p, L.ruleVersion, Literal("2026-10-24"))
        for c in admits[key]:   # read by the selection rule of task 12.6 (ontology/rules/)
            kg.add(p, L.admitsConfidence, c)


# --------------------------------------------------------------------------------- main
def producing_commit(output, code):
    """The commit of the code that wrote `output`: the first commit of `code` after the file
    was written (steps are committed once they have run), else the last one before it."""
    t = datetime.fromtimestamp(output.stat().st_mtime).isoformat(timespec="seconds")
    log = lambda *a: subprocess.run(["git", "log", *a, "--format=%h", "--", code],  # noqa: E731
                                    capture_output=True, text=True, cwd=ROOT).stdout.split()
    after, before = log("--reverse", f"--after={t}"), log("-1", f"--before={t}")
    return (after or before or ["unknown"])[0]


def main():
    versions = {"kg": git_version(),
                "pump": producing_commit(INTERIM / "pump_unit_attribution.parquet",
                                         "src/kg/pump_attribution.py"),
                "crop": producing_commit(landuse.DEMAND, "src/dataset/crop_demand.py")}
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    bnpe = load_bnpe(BNPE_SNAPSHOT)
    gw = bnpe[bnpe["source"] == "groundwater"]
    fac = (gw.groupby("code_ouvrage").agg(nom_ouvrage=("nom_ouvrage", "first"),
                                          longitude=("longitude", "first"),
                                          latitude=("latitude", "first"),
                                          uri_ouvrage=("uri_ouvrage", "first"))
           .reset_index())
    w_pts = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    f_pts = gpd.GeoSeries(gpd.points_from_xy(fac["longitude"], fac["latitude"]),
                          crs=CRS_WGS84).to_crs(CRS_L93)
    cells = forcing.grid()
    aoi = forcing.area_of_interest(cells, w_pts)
    tme, pile, poly, plain_box = load_bdlisa(pd.concat([w_pts, f_pts], ignore_index=True)
                                             .pipe(gpd.GeoSeries, crs=CRS_L93), aoi)
    w_cp, f_cp = locate(w_pts, poly), locate(f_pts, poly)

    attr = pd.read_parquet(INTERIM / "pump_unit_attribution.parquet")
    evid = pd.read_parquet(INTERIM / "pump_unit_evidence.parquet")
    ev = json.loads((INTERIM / "pump_unit_attribution_eval.json").read_text())
    stack_str = {cp: " > ".join(c for c in (pile[pile["CodePoly"] == cp]
                                             .sort_values("OrdRelatif")["CodeEH"]))
                 for cp in set(f_cp.dropna())}
    mine = f_cp.map(stack_str).fillna("").values
    check = evid.set_index("code_ouvrage")["stack"].reindex(fac["code_ouvrage"])
    same = (mine == check.fillna("").values) | check.isna().values
    assert same.all(), f"{(~same).sum()} facilities: stack differs from task 12.3's evidence"

    raw = pd.read_parquet(RAW / "hubeau" / "stations_66.parquet").set_index("code_bss")
    extra = set(attr["unit"].dropna()) | set(evid["rec_unit"].dropna()) | \
        {c for b in wells["code_bss"] for c in recorded_codes(raw, b)} | rivers.statement_units()
    riv = rivers.Context(wells, w_pts, poly)

    # polygons: the plain, those under a well or a facility, and (CQ4) the outcrop polygons of
    # the units of these stacks inside the cells or a search zone, each with its whole stack;
    # to closure, since an added stack can hold a unit not met before (2 passes on v4)
    used = set(w_cp.dropna()) | set(f_cp.dropna()) | riv.polygons
    base = poly[poly.intersects(plain_box) | poly["codepoly"].isin(used)]
    polys = set(base["codepoly"])
    units0 = set(pile.loc[pile["CodePoly"].isin(polys), "CodeEH"]) | extra
    units_all, passes = set(units0), 0
    while add := forcing.outcrop_polygons(pile, poly, units_all, aoi) - polys:
        polys |= add
        units_all |= set(pile.loc[pile["CodePoly"].isin(add), "CodeEH"])
        passes += 1
    outcrops = polys - set(base["codepoly"])

    kg = KG()
    rel, rule, ex = provenance(kg, versions)
    ext = extents(kg)
    unit, groups, stacks, keep = units_and_polygons(
        kg, rel, tme, pile, poly, used | outcrops, plain_box, ext["plain-box"][0], extra)
    new_units = sorted(set(unit) - units0)
    assert set(unit) == units_all, "units differ from the closure's"
    n_bodies, n_unknown_pz = piezometers(kg, rel, rule, ex, unit, wells, w_pts, w_cp, stacks,
                                         poly, pile, ext["plain-box"][0])
    ev_table = evaluations(kg, rule, ex, ev)
    counts = facilities(kg, rel, rule, ex, unit, groups, fac, f_pts, f_cp, stacks,
                        ext["plain-box-margin"][0], ev_table)
    n_rec = annual_records(kg, rel, gw)
    policies(kg)
    land = landuse.add(kg, rel, wells, versions)
    forc = forcing.add(kg, rel, wells, w_pts, keep, cells, versions, unit, pile, set(tme.index))
    forc |= {"outcrop_polygons_added": len(outcrops), "outcrop_passes": passes,
             "units_first_met_in_added_stacks": new_units}
    keys = [w["bss_id"] if isinstance(w["bss_id"], str) and w["bss_id"] else w["code_bss"]
            for _, w in wells.iterrows()]
    assert riv.polygons <= set(keep["codepoly"]), "a reach piece's polygon is not in the graph"
    river = rivers.add(kg, rel, riv, unit, {k: iri("piezometer", k) for k in keys}, versions,
                       pd.read_parquet(DATASET_DIR / "pumping_points.parquet"))

    head = URIRef(D + f"kg-{DATASET}")
    kg.node(head, OWL.Ontology)
    kg.add(head, OWL.imports, URIRef("https://w3id.org/lulcw/meta"))
    kg.add(head, DCT.title, Literal(f"LULC-Water knowledge graph, dataset {DATASET}", lang="en"))
    kg.add(head, DCT.description, Literal(
        "Source facts and qualified assertions for the competency questions CQ1-CQ8, CQ11 and "
        "CQ12 (tasks 12.5-12.7); derived links come from the SHACL-AF rules of task 12.6.",
        lang="en"))
    kg.add(head, DCT.created, Literal(date.today().isoformat(), datatype=XSD.date))
    kg.add(head, PROV.wasGeneratedBy, ex["kg"])
    kg.add(head, OWL.versionInfo, Literal(versions["kg"]))

    OUT.mkdir(parents=True, exist_ok=True)
    ttl = OUT / f"lulcw_kg_{DATASET}.ttl"
    write_turtle(kg.g, ttl)
    import pyoxigraph
    store = pyoxigraph.Store()
    store.bulk_load(path=str(ttl), format=pyoxigraph.RdfFormat.TURTLE)
    assert len(store) == len(kg.g), f"pyoxigraph loaded {len(store)} of {len(kg.g)} triples"

    g = kg.g
    by_class = pd.Series([str(o).split("#")[-1].split("/")[-1] for o in g.objects(None, RDF.type)]
                         ).value_counts()
    conf = pd.Series([str(o).split("#")[-1] for a in g.subjects(RDF.type, L.UnitAttribution)
                      for o in g.objects(a, L.confidence)]).value_counts()
    summary = {
        "dataset": DATASET, "built": date.today().isoformat(), "code_version": versions["kg"],
        "pump_attribution_code_version": versions["pump"], "triples": len(g),
        "file_mb": round(ttl.stat().st_size / 1e6, 1), "instances_by_class": by_class.to_dict(),
        "attribution_confidence": conf.to_dict(),
        "piezometers_without_recorded_unit": n_unknown_pz, "groundwater_bodies": n_bodies,
        "facilities_with_group_level_split": counts["group_split"],
        "facilities_absent_from_dataset": counts["absent"], "annual_records": n_rec,
        "polygons": len(keep), "polygons_in_plain_box": int(keep.intersects(plain_box).sum()),
        "piezometers_without_polygon": int(w_cp.isna().sum()),
        "facilities_without_polygon": int(f_cp.isna().sum()),
        "land_use": land, "crop_demand_code_version": versions["crop"], "forcing": forc,
        "rivers_and_canals": river,
    }
    (OUT / f"lulcw_kg_{DATASET}_summary.json").write_text(json.dumps(summary, indent=1,
                                                                     ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"-> {ttl.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
