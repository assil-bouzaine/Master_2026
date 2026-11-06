"""River, gauge and canal facts of the knowledge graph (CQ5, CQ6), added by src.kg.build_kg.

  watercourses  the watercourses of the dataset's gauges and those a statement names (BD Carthage
                code), each with its main stem: the longest path of its BD TOPO flow network, reaches
                oriented in flow direction, main-network reaches weighing 1 per metre, its other
                reaches 0.5, and reaches of another code 0.01, admitted only between two nodes of the
                watercourse (BD TOPO codes the Têt's reach at the Bolès confluence as the Bolès)
  reaches       the BD TOPO reaches of those watercourses, and the canal reaches (nature Canal),
                that meet a reach search zone (ZONE_M around a piezometer)
  pieces        reach ∩ zone ∩ elementary polygon, with its length in metres; a piece outside every
                polygon of the release is kept without a polygon; pieces under MIN_LENGTH_M dropped.
                The polygons the pieces meet join the graph's polygons (build_kg's closure).
  sections      the WFD river water bodies the statements name (Sandre, 2022 reporting) and the
                stretches between two points a source locates, projected on the main stem; a piece of
                one of a section's watercourses is in the section when at least SECTION_SHARE of its
                length lies within SECTION_TOL_M of the section's line, a gauge when its point does
  gauges        every gauge of the dataset: watercourse, chainage on its main stem (off it beyond
                STEM_SNAP_M), local influence as recorded, weekly discharge series with its observed
                training weeks; arm C's gauge pool (src/models/features.py); one gauge-zone relation
                per gauge and zone where the gauge's watercourse has pieces
  statements    configs/exchange_evidence.csv (checked against the documents by
                tests/test_exchange_evidence.py): documents, passages, exchange statements. A
                statement is about a unit itself (lulcw:aboutUnit) or about an aggregate of units
                (lulcw:aggregateMemberUnit; lulcw:aboutGroundwaterBody when the source states a WFD
                body): membership of an aggregate is never written as evidence about each member
                (Codex review of 2026-11-06, R1); each states its method (lulcw:evidenceMethod)
  overlaps      two sections of one watercourse overlap when at least SECTION_OVERLAP_M of one's
                line lies within SECTION_TOL_M of the other's (lulcw:overlapsSection): only
                statements about overlapping or identical sections can contradict each other
  canals        the plain's surface-water intakes behind the canal input of the models
                (src/dataset/pumping.py canal_series), each with its candidate watercourse (nearest
                reach within INTAKE_SNAP_M), and their group with its weekly series
Associations, statement applicability, gauge selection and the influences are derived from these by
the SHACL-AF rules (orders 62-64), so that the export's equivalence test meets two derivations.
"""
import csv
import json
from collections import defaultdict
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
from rdflib import Literal
from rdflib.namespace import RDF, RDFS, XSD
from shapely import to_wkt
from shapely.geometry import Point
from shapely.ops import linemerge, substring

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, RAW, ROOT

ZONE_M = 5000.0
MIN_LENGTH_M = 1.0
SECTION_TOL_M = 100.0
SECTION_SHARE = 0.5
SECTION_OVERLAP_M = 500.0
STEM_SNAP_M = 200.0
INTAKE_SNAP_M = 500.0
EVIDENCE = ROOT / "configs" / "exchange_evidence.csv"
DOCS = RAW / "documents"
# arm C's gauge candidates (src/models/features.py, RIVERS and NEAR_CANDIDATES); tests/test_kg_rules.py
# checks that the graph's pool equals them, so that D draws from the same gauges (analysis plan §14 item 16)
POOL = ("Y046403001", "Y047403001", "Y066404001", "Y027401001", "Y028406001")
MECH = {"RiverExchange": "RiverExchange", "CanalReturnFlow": "CanalReturnFlow"}
DIRECTION = {"aquifer_to_surface": "AquiferToSurface", "surface_to_aquifer": "SurfaceToAquifer",
             "equilibrium": "ExchangeEquilibrium", "no_exchange": "NoExchange",
             "not_qualified": "NotQualified"}
HEDGING = {"stated": "StatedFinding", "hedged": "HedgedFinding"}
MAPPING = {"listed_by_source": "UnitListedBySource", "by_name": "UnitMappedByName"}
METHOD = {"differential_gauging": "DifferentialGauging", "geochemical_tracing": "GeochemicalTracing",
          "water_balance": "WaterBalanceEstimate", "synthesis": "SynthesisStatement"}
SNAPSHOTS = ROOT / "configs" / "snapshots.json"


def snapshot(name):
    """The pinned snapshot of data/raw/<name> (configs/snapshots.json); a newer one is reported and
    ignored until its date is pinned, so a download never changes a build silently."""
    day = json.loads(SNAPSHOTS.read_text())[name]
    d = RAW / name / day
    assert (d / "release.json").exists(), f"pinned snapshot {d} missing: run its ingest script or pin another date"
    newer = sorted(x.name for x in (RAW / name).glob("????-??-??") if x.name > day and (x / "release.json").exists())
    if newer:
        print(f"note: data/raw/{name} has newer snapshots {newer}, not used (pinned {day} in {SNAPSHOTS.name})")
    return d


def statements():
    with open(EVIDENCE, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def statement_units():
    """BD LISA codes the statements name (the graph describes them, build_kg's `extra`)."""
    return {u for r in statements() for u in r["units"].split(";") if u}


def section_overlaps(sections):
    """{(a, b)} of different sections sharing a watercourse whose lines run together over at least
    SECTION_OVERLAP_M (within SECTION_TOL_M), both orders."""
    out = set()
    keys = sorted(sections)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            (_, ga, ca, *_), (_, gb, cb, *_) = sections[a], sections[b]
            if not set(ca) & set(cb):
                continue
            run = min(ga.intersection(gb.buffer(SECTION_TOL_M)).length, gb.intersection(ga.buffer(SECTION_TOL_M)).length)
            if run >= SECTION_OVERLAP_M:
                out |= {(a, b), (b, a)}
    return out


def main_stem(reaches, code):
    """(LineString in flow direction, [reach index]) of a watercourse's main stem."""
    own = reaches[reaches["code_du_cours_d_eau_bdcarthage"] == code]
    nodes = set(own["lien_vers_noeud_hydrographique_ini"]) | set(own["lien_vers_noeud_hydrographique_fin"])
    bridge = reaches[(reaches["code_du_cours_d_eau_bdcarthage"] != code)
                     & reaches["lien_vers_noeud_hydrographique_ini"].isin(nodes)
                     & reaches["lien_vers_noeud_hydrographique_fin"].isin(nodes)]
    net = pd.concat([own, bridge])
    out, indeg = defaultdict(list), defaultdict(int)
    for i, r in zip(net.index, net.itertuples()):
        mine = r.code_du_cours_d_eau_bdcarthage == code
        w = r.geometry.length * ((1.0 if r.reseau_principal_coulant == 1 else 0.5) if mine else 0.01)
        out[r.lien_vers_noeud_hydrographique_ini].append((r.lien_vers_noeud_hydrographique_fin, w, i))
        indeg[r.lien_vers_noeud_hydrographique_fin] += 1
    every = set(out) | set(indeg)
    left = {n: indeg.get(n, 0) for n in every}
    order, todo = [], sorted(n for n in every if left[n] == 0)
    while todo:
        n = todo.pop()
        order.append(n)
        for b, _, _ in out[n]:
            left[b] -= 1
            if left[b] == 0:
                todo.append(b)
    assert len(order) == len(every), f"{code}: the flow network has a cycle"
    best, prev = dict.fromkeys(every, 0.0), {}
    for n in order:
        for b, w, i in out[n]:
            if best[n] + w > best[b]:
                best[b], prev[b] = best[n] + w, (n, i)
    n = max((m for m in every if not out[m]), key=lambda m: best[m])
    path = []
    while n in prev:
        n, i = prev[n][0], prev[n][1]
        path.append(i)
    path = path[::-1]
    line = linemerge([net.loc[i, "geometry"] for i in path])
    assert line.geom_type == "LineString", f"{code}: the main stem does not merge into one line"
    return line, path


class Context:
    """What build_kg needs before the graph exists (the polygons the pieces meet), and the
    geometry add() writes."""

    def __init__(self, wells, w_pts, poly):
        self.t = gpd.read_parquet(snapshot("bdtopo_hydro") / "troncon_hydrographique.parquet")
        self.wb = gpd.read_parquet(snapshot("sandre_water_bodies") / "masses_eau_riviere_vrap2022.parquet")
        self.wb["code"] = self.wb["CdEuMasseDEau"].str.upper()
        self.gauges = pd.read_parquet(DATASET_DIR / "gauges.parquet")
        gp = gpd.GeoSeries(gpd.points_from_xy(self.gauges["longitude_station"],
                                              self.gauges["latitude_station"]), crs=CRS_WGS84).to_crs(CRS_L93)
        self.gauges["geometry"] = list(gp)
        self.st = statements()
        codes = {c for c in self.gauges["code_cours_eau"] if c != "00000000"}
        codes |= {c for r in self.st for c in r["watercourses"].split(";") if c}
        self.codes = sorted(codes)
        self.stem = {}
        for c in self.codes:
            self.stem[c] = main_stem(self.t, c)
        self.wells = wells.reset_index(drop=True)
        self.keys = [w["bss_id"] if isinstance(w["bss_id"], str) and w["bss_id"] else w["code_bss"]
                     for _, w in self.wells.iterrows()]
        self.zones = [Point(p.x, p.y).buffer(ZONE_M, 256) for p in w_pts]
        river = self.t["code_du_cours_d_eau_bdcarthage"].isin(self.codes)
        canal = self.t["nature"] == "Canal"
        sel = self.t[river | canal]
        union = gpd.GeoSeries(self.zones, crs=CRS_L93).union_all()
        self.reaches = sel[sel.intersects(union)].copy()
        self.reaches["kind"] = np.where(self.reaches["nature"] == "Canal", "canal", "river")
        # a canal reach that carries a watercourse code counts as a canal (its nature), never as a
        # river reach
        self.pieces = self._pieces(poly)
        self.polygons = set(self.pieces["codepoly"].dropna())

    def _pieces(self, poly):
        rows = []
        sidx = poly.sindex
        for key, z in zip(self.keys, self.zones):
            near = self.reaches[self.reaches.intersects(z)]
            for r in near.itertuples():
                g = r.geometry.intersection(z)
                if g.is_empty or g.length < MIN_LENGTH_M:
                    continue
                inside = 0.0
                for j in sidx.query(g, predicate="intersects"):
                    part = g.intersection(poly.geometry.iloc[j])
                    inside += part.length
                    if part.length >= MIN_LENGTH_M:
                        rows.append((key, r.cleabs, poly["codepoly"].iloc[j], part.length, part))
                rest = g.length - inside
                if rest >= MIN_LENGTH_M:            # polygons do not overlap: the rest is off the map
                    rows.append((key, r.cleabs, None, rest, None))
        return pd.DataFrame(rows, columns=["zone", "cleabs", "codepoly", "length", "geometry"])

    # ------------------------------------------------------------------------------- sections
    def sections(self):
        """{section id: (kind, geometry, [watercourse codes], label, extra)}."""
        out = {}
        for r in self.st:
            codes = [c for c in r["watercourses"].split(";") if c]
            if r["section_kind"] == "water_body":
                row = self.wb[self.wb["code"] == r["section"].upper()]
                assert len(row) == 1, r["section"]
                out[r["section"].upper()] = ("water_body", row.geometry.iloc[0], codes,
                                             row["NomMasseDEau"].iloc[0], {})
            elif r["section_kind"] == "between_points":
                line = self.stem[codes[0]][0]
                a = line.project(Point(float(r["from_x"]), float(r["from_y"])))
                b = line.project(Point(float(r["to_x"]), float(r["to_y"])))
                for end in ("from", "to"):
                    d = line.distance(Point(float(r[end + "_x"]), float(r[end + "_y"])))
                    assert d <= STEM_SNAP_M, f"{r['id']}: {end} point {d:.0f} m from the main stem"
                lo, hi = sorted((a, b))
                out[r["section"]] = ("between_points", substring(line, lo, hi), codes,
                                     f"{r['from_name']} to {r['to_name']}",
                                     {"from": lo, "to": hi, "doc": r["document"], "page": r["points_page"]})
        return out

    def piece_sections(self, sections):
        """{(zone, cleabs, codepoly): [section ids]} for river pieces."""
        river = set(self.reaches.loc[self.reaches["kind"] == "river", "cleabs"])
        code_of = dict(zip(self.reaches["cleabs"], self.reaches["code_du_cours_d_eau_bdcarthage"]))
        corridors = {s: (g.buffer(SECTION_TOL_M), set(c)) for s, (_, g, c, _, _) in sections.items()}
        out = defaultdict(list)
        for p in self.pieces.itertuples():
            if p.cleabs not in river or p.geometry is None:
                continue
            for s, (corr, codes) in corridors.items():
                if code_of[p.cleabs] in codes and p.geometry.intersection(corr).length >= SECTION_SHARE * p.length:
                    out[(p.zone, p.cleabs, p.codepoly)].append(s)
        return out


def add(kg, rel, ctx, unit, wells_iri, versions, plain_points):
    """Add the CQ5/CQ6 facts; returns counts for build_kg's summary. `unit`: code -> node;
    `wells_iri`: well key -> piezometer node; `plain_points`: the dataset's pumping points."""
    from src.kg.build_kg import EPSG2154, GEO, L, PROV, dbl, iri, record

    def release(key, label, day, where):
        r = kg.node(iri("release", key), L.DataRelease, label, "en")
        kg.add(r, L.retrievalDate, Literal(day, datatype=XSD.date))
        kg.add(r, RDFS.comment, Literal(f"Source: {where}", lang="en"))
        rel[key] = r
        return r

    def wkt(g, nd=1):
        return Literal(EPSG2154 + to_wkt(g, rounding_precision=nd), datatype=GEO.wktLiteral)

    def geom(node, kind, key, g):
        n = kg.node(iri("geometry", kind, key), GEO.Geometry)
        kg.add(n, GEO.asWKT, wkt(g))
        kg.add(node, GEO.hasGeometry, n)

    topo = json.loads((snapshot("bdtopo_hydro") / "release.json").read_text())
    sandre = json.loads((snapshot("sandre_water_bodies") / "release.json").read_text())
    r_topo = release(f"bdtopo-hydro-{topo['retrieved']}", "IGN BD TOPO V3 hydrography (reaches, "
                     "watercourses), département box", topo["retrieved"], topo["url"])
    r_sandre = release("sandre-water-bodies-vrap2022", "Sandre, WFD river water bodies, 2022 "
                       "reporting", sandre["retrieved"], sandre["url"])
    r_hydro = release("hubeau-hydrometrie", "Hub'Eau hydrometry: stations and daily mean flows, "
                      "département 66", "2026-10-13", "https://hubeau.eaufrance.fr/api/v2/hydrometrie")
    exe = kg.node(iri("execution", "river-geometry"), L.RuleExecution,
                  "river and canal geometry (src/kg/rivers.py)", "en")
    kg.add(exe, L.codeVersion, Literal(versions["kg"]))
    kg.add(exe, RDFS.comment, Literal(
        f"Main stems: the longest path of each watercourse's BD TOPO flow network (reaches of the code; "
        f"reaches of another code only between two of its nodes). Reach pieces: reach ∩ {ZONE_M:g} m "
        f"zone ∩ elementary polygon (GeoPandas/Shapely, Lambert-93), pieces under {MIN_LENGTH_M:g} m "
        f"dropped. Sections: a piece is in a section when {SECTION_SHARE:g} of its length lies within "
        f"{SECTION_TOL_M:g} m of the section's line and its reach carries one of the section's "
        f"watercourse codes; gauges off the main stem beyond {STEM_SNAP_M:g} m (src/kg/rivers.py).",
        lang="en"))
    for r in (r_topo, r_sandre, r_hydro, rel["bdlisa-v3-occ"]):
        kg.add(exe, PROV.used, r)

    # watercourses and their main stems
    wc = {}
    name = {}
    for c in ctx.codes:
        own = ctx.t[ctx.t["code_du_cours_d_eau_bdcarthage"] == c]
        nm = own["cpx_toponyme_de_cours_d_eau"].dropna()
        name[c] = nm.mode().iloc[0] if len(nm) else c
        n = kg.node(iri("watercourse", c), L.Watercourse, name[c], "fr")
        kg.add(n, L.bdCarthageCode, Literal(c))
        kg.add(n, L.mainStemLengthM, dbl(ctx.stem[c][0].length))
        kg.add(n, L.inRelease, r_topo)
        wc[c] = n

    # reaches (river and canal) that meet a zone
    stem_reach = {}
    for c in ctx.codes:
        line, path = ctx.stem[c]
        for i in path:
            r = ctx.t.loc[i]
            if r["code_du_cours_d_eau_bdcarthage"] == c:
                a, b = line.project(Point(r.geometry.coords[0])), line.project(Point(r.geometry.coords[-1]))
                stem_reach[r["cleabs"]] = (min(a, b), max(a, b))
    reach = {}
    for r in ctx.reaches.itertuples():
        cls = L.CanalReach if r.kind == "canal" else L.RiverReach
        label = r.cpx_toponyme_de_cours_d_eau if isinstance(r.cpx_toponyme_de_cours_d_eau, str) else \
            ("canal" if r.kind == "canal" else name.get(r.code_du_cours_d_eau_bdcarthage, "reach"))
        n = kg.node(iri("reach", r.cleabs), cls, label, "fr")
        kg.add(n, L.bdtopoId, Literal(r.cleabs))
        kg.add(n, L.reachNature, Literal(r.nature))
        if not pd.isna(r.reseau_principal_coulant):
            kg.add(n, L.onMainNetwork, Literal(bool(r.reseau_principal_coulant == 1)))
        if isinstance(r.persistance, str):
            kg.add(n, L.persistence, Literal(r.persistance))
        if r.kind == "river":
            kg.add(n, L.reachOf, wc[r.code_du_cours_d_eau_bdcarthage])
            kg.add(n, L.onMainStem, Literal(r.cleabs in stem_reach))
            if r.cleabs in stem_reach:
                kg.add(n, L.chainageFromM, dbl(stem_reach[r.cleabs][0], 1))
                kg.add(n, L.chainageToM, dbl(stem_reach[r.cleabs][1], 1))
        geom(n, "reach", r.cleabs, r.geometry)
        kg.add(n, L.inRelease, r_topo)
        reach[r.cleabs] = n

    # sections
    secs = ctx.sections()
    sec = {}
    for s, (kind, g, codes, label, extra) in secs.items():
        if kind == "water_body":
            n = kg.node(iri("water-body", s), L.SurfaceWaterBody, label, "fr")
            kg.add(n, L.wfdCode, Literal(s))
            kg.add(n, L.inRelease, r_sandre)
        else:
            n = kg.node(iri("river-section", s), L.RiverSection, label, "en")
            kg.add(n, L.chainageFromM, dbl(extra["from"], 1))
            kg.add(n, L.chainageToM, dbl(extra["to"], 1))
            kg.add(n, RDFS.comment, Literal(
                f"Between two points located by {extra['doc']} (page {extra['page']}), projected on the "
                "main stem of BD TOPO (src/kg/rivers.py).", lang="en"))
            kg.add(n, PROV.wasGeneratedBy, exe)
        for c in codes:
            kg.add(n, L.sectionOf, wc[c])
        geom(n, "section", s, g)
        sec[s] = n
    overlaps = section_overlaps(secs)
    for a, b in overlaps:
        kg.add(sec[a], L.overlapsSection, sec[b])

    # zones and pieces
    zone = {}
    for key in ctx.keys:
        z = kg.node(iri("reach-zone", key), L.ReachSearchZone)
        kg.add(z, L.zoneOf, wells_iri[key])
        kg.add(z, L.zoneRadiusM, dbl(ZONE_M))
        kg.add(z, RDFS.comment, Literal(f"The area within {ZONE_M:g} m of the piezometer (Lambert-93), "
                                        "where river and canal reaches are cut by elementary polygons",
                                        lang="en"))
        zone[key] = z
    in_sec = ctx.piece_sections(secs)
    n_pieces = 0
    for p in ctx.pieces.itertuples():
        n = kg.node(iri("reach-piece", p.zone, p.cleabs, p.codepoly or "off-map"), L.ReachPiece)
        kg.add(n, L.pieceOfReach, reach[p.cleabs])
        if p.codepoly is not None:
            kg.add(n, L.piecePolygon, iri("polygon", p.codepoly))
        kg.add(n, L.withinExtent, zone[p.zone])
        kg.add(n, L.pieceLengthM, dbl(p.length))
        for s in in_sec.get((p.zone, p.cleabs, p.codepoly), []):
            kg.add(n, L.inSection, sec[s])
        kg.add(n, PROV.wasGeneratedBy, exe)
        n_pieces += 1

    # gauges, their series, the pool and the gauge-zone relations
    splits = json.loads((DATASET_DIR / "splits.json").read_text())
    t0, t1 = splits["train"]
    rw = pd.read_parquet(DATASET_DIR / "rivers_weekly.parquet")
    weeks = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["week"])["week"].drop_duplicates()
    n_train = int(((weeks >= t0) & (weeks <= t1)).sum())
    obs = rw[(rw["week"] >= t0) & (rw["week"] <= t1) & rw["q_m3s"].notna()].groupby("code_station").size()
    gauge, g_chain = {}, {}
    for g in ctx.gauges.itertuples():
        n = kg.node(iri("gauge", g.code_station), L.RiverGauge, g.libelle_station, "fr")
        kg.add(n, L.gaugeCode, Literal(g.code_station))
        # POINT(x y), the form of every point of the graph (the CQ2 distance queries parse it)
        kg.point(n, "gauge", g.code_station, g.geometry.x, g.geometry.y)
        if g.code_cours_eau in wc:
            kg.add(n, L.onWatercourse, wc[g.code_cours_eau])
            line = ctx.stem[g.code_cours_eau][0]
            ch, off = line.project(g.geometry), line.distance(g.geometry)
            kg.add(n, L.chainageM, dbl(ch, 1))
            kg.add(n, L.offsetFromStemM, dbl(off, 1))
            g_chain[g.code_station] = (ch, off)
            for s, (kind, sg, codes, _, _) in secs.items():
                if g.code_cours_eau in codes and sg.distance(g.geometry) <= SECTION_TOL_M:
                    kg.add(n, L.inSection, sec[s])
        if not pd.isna(g.influence_locale_station):
            kg.add(n, L.localInfluenceCode, Literal(int(g.influence_locale_station), datatype=XSD.integer))
        if isinstance(g.commentaire_influence_locale_station, str):
            kg.add(n, L.localInfluenceComment, Literal(g.commentaire_influence_locale_station, lang="fr"))
        se = kg.node(iri("series", f"rivers-weekly-{DATASET}", g.code_station), L.ObservationSeries)
        kg.add(n, L.hasDischargeSeries, se)
        kg.add(se, L.seriesVariable, L.RiverDischarge)
        kg.add(se, L.temporalResolution, Literal("P7D"))
        kg.add(se, L.coverageStart, Literal(pd.Timestamp(g.first_week).date().isoformat(), datatype=XSD.date))
        kg.add(se, L.coverageEnd, Literal(pd.Timestamp(g.last_week).date().isoformat(), datatype=XSD.date))
        kg.add(se, L.observedTrainingWeeks, Literal(int(obs.get(g.code_station, 0)), datatype=XSD.integer))
        kg.add(se, L.trainingWeeks, Literal(n_train, datatype=XSD.integer))
        kg.add(se, L.storedIn, Literal(f"{(DATASET_DIR / 'rivers_weekly.parquet').relative_to(ROOT)}"
                                       f" [code_station = {g.code_station}, column q_m3s]"))
        kg.add(se, L.qualityPolicy, Literal("weekly mean of Hub'Eau's daily mean discharge (QmnJ), m3/s, "
                                            "weeks ending Sunday with at least one day"))
        kg.add(se, L.inRelease, rel[f"dataset-{DATASET}"])
        kg.add(n, L.inRelease, r_hydro)
        gauge[g.code_station] = n
    pool = kg.node(iri("gauge-pool", "arm-c"), L.GaugePool,
                   "the five full-record gauges of arm C's distance rule (src/models/features.py)", "en")
    for code in POOL:
        kg.add(pool, L.poolMember, gauge[code])
    code_of = dict(zip(ctx.reaches["cleabs"], ctx.reaches["code_du_cours_d_eau_bdcarthage"]))
    kind_of = dict(zip(ctx.reaches["cleabs"], ctx.reaches["kind"]))
    pc = ctx.pieces.assign(code=ctx.pieces["cleabs"].map(code_of), kind=ctx.pieces["cleabs"].map(kind_of))
    pc = pc[(pc["kind"] == "river") & pc["geometry"].notna()]
    n_rel = 0
    for (key, code), sub in pc.groupby(["zone", "code"]):
        line = ctx.stem[code][0]
        on = [g for g in sub["geometry"] if line.distance(g) <= STEM_SNAP_M / 4]
        span = None
        if on:
            ch = [line.project(Point(xy)) for g in on for part in getattr(g, "geoms", [g]) for xy in part.coords]
            span = (min(ch), max(ch))
        union = gpd.GeoSeries(list(sub["geometry"])).union_all()
        for g in ctx.gauges[ctx.gauges["code_cours_eau"] == code].itertuples():
            x = kg.node(iri("gauge-zone", key, g.code_station), L.GaugeZoneRelation)
            kg.add(x, L.relatedGauge, gauge[g.code_station])
            kg.add(x, L.withinExtent, zone[key])
            kg.add(x, L.horizontalDistanceM, dbl(union.distance(g.geometry), 1))
            ch, off = g_chain[g.code_station]
            if span is None or off > STEM_SNAP_M:
                pos, d = L.OffMainStem, None
            elif ch < span[0]:
                pos, d = L.UpstreamOfZone, span[0] - ch
            elif ch > span[1]:
                pos, d = L.DownstreamOfZone, ch - span[1]
            else:
                pos, d = L.AlongZoneStretch, 0.0
            kg.add(x, L.alongRiverPosition, pos)
            if d is not None:
                kg.add(x, L.alongRiverDistanceM, dbl(d, 1))
            kg.add(x, PROV.wasGeneratedBy, exe)
            n_rel += 1

    # documents, passages, statements
    index = json.loads((DOCS / "documents.json").read_text())
    doc = {}
    for key, d in index.items():
        n = kg.node(iri("document", key), L.Document, d["title"], "fr")
        kg.add(n, L.sourceUrl, Literal(d["url"], datatype=XSD.anyURI))
        kg.add(n, L.retrievalDate, Literal(d["retrieved"], datatype=XSD.date))
        kg.add(n, L.md5, Literal(d["md5"]))
        kg.add(n, L.storedIn, Literal(f"{(DOCS / d['file']).relative_to(ROOT)}"))
        doc[key] = n
    for r in ctx.st:
        pa = kg.node(iri("passage", r["id"]), L.DocumentPassage)
        kg.add(pa, L.inDocument, doc[r["document"]])
        kg.add(pa, L.pageLabel, Literal(r["page"]))
        kg.add(pa, L.quote, Literal(r["quote"], lang="fr"))
        s = kg.node(iri("exchange-statement", r["id"]), L.ExchangeStatement)
        kg.add(s, L.statedMechanism, getattr(L, MECH[r["mechanism"]]))
        if r["section_kind"] in ("water_body", "between_points"):
            kg.add(s, L.aboutSection, sec[r["section"].upper() if r["section_kind"] == "water_body" else r["section"]])
        for c in [c for c in r["watercourses"].split(";") if c]:
            kg.add(s, L.aboutWatercourse, wc[c])
        units = [u for u in r["units"].split(";") if u]
        assert r["subject"] in ("unit", "aggregate") and (r["subject"] == "unit" or len(units) > 1), r["id"]
        for u in units:
            kg.add(s, L.aboutUnit if r["subject"] == "unit" else L.aggregateMemberUnit, unit[u])
        if r["groundwater_body"]:
            body = iri("groundwater-body", r["groundwater_body"].removeprefix("FR"))
            assert (body, RDF.type, L.GroundwaterBody) in kg.g, f"{r['id']}: no groundwater body {body}"
            kg.add(s, L.aboutGroundwaterBody, body)
        kg.add(s, L.evidenceMethod, getattr(L, METHOD[r["method"]]))
        kg.add(s, L.unitAsNamed, Literal(r["unit_as_named"], lang="fr"))
        kg.add(s, L.unitMapping, getattr(L, MAPPING[r["unit_mapping"]]))
        kg.add(s, L.exchangeDirection, getattr(L, DIRECTION[r["direction"]]))
        kg.add(s, L.hedging, getattr(L, HEDGING[r["hedging"]]))
        kg.add(s, L.stateDescription, Literal(r["state"], lang="en"))
        for k, p in (("period_start", L.periodStart), ("period_end", L.periodEnd)):
            if r[k]:
                kg.add(s, p, Literal(r[k], datatype=XSD.date))
        if r["flux_m3s"]:
            kg.add(s, L.fluxM3s, dbl(float(r["flux_m3s"])))
        if r["flux_unc_m3s"]:
            kg.add(s, L.fluxUncertaintyM3s, dbl(float(r["flux_unc_m3s"])))
        if r["measured_at"]:
            assert r["subject"] == "unit", f"{r['id']}: a measurement at a site is about a unit"
            hit = [k for k, w in zip(ctx.keys, ctx.wells["code_bss"]) if w == r["measured_at"]]
            assert hit, f"{r['id']}: measured_at {r['measured_at']} is not a well of the dataset"
            kg.add(s, L.measuredAt, wells_iri[hit[0]])
        if r["note"]:
            kg.add(s, RDFS.comment, Literal(r["note"], lang="en"))
        kg.add(s, L.evidenceKind, L.ExpertHypothesis)
        kg.add(s, PROV.wasDerivedFrom, pa)

    # canals: the plain's surface intakes behind the canal input, and their group
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet", columns=["code_ouvrage", "usage"]).drop_duplicates()
    pts = plain_points[(plain_points["zone"] == "plain") & (plain_points["source"] == "surface")]
    members = pts[pts["code_ouvrage"].isin(pw.loc[pw["usage"].isin(["irrigation", "canals"]), "code_ouvrage"])]
    members = members.drop_duplicates("code_ouvrage")
    ip = gpd.GeoSeries(gpd.points_from_xy(members["longitude"], members["latitude"]), crs=CRS_WGS84).to_crs(CRS_L93)
    rivers_only = ctx.t[ctx.t["code_du_cours_d_eau_bdcarthage"].isin(ctx.codes) & (ctx.t["nature"] != "Canal")]
    rsidx = rivers_only.sindex
    group = kg.node(iri("canal-intakes", "plain"), L.CanalIntakeGroup,
                    "surface-water irrigation and canal intakes of the plain (the canal input of the models)", "en")
    gs = kg.node(iri("series", f"canal-intakes-weekly-{DATASET}", "plain"), L.ObservationSeries)
    kg.add(group, L.hasVolumeSeries, gs)
    kg.add(gs, L.seriesVariable, L.CanalDiversionVolume)
    kg.add(gs, L.temporalResolution, Literal("P7D"))
    kg.add(gs, L.storedIn, Literal(f"{(DATASET_DIR / 'pumping_weekly.parquet').relative_to(ROOT)} [the members' "
                                   "rows with usage irrigation or canals, summed by week: src/dataset/pumping.py canal_series]"))
    kg.add(gs, L.inRelease, rel[f"dataset-{DATASET}"])
    n_cand = 0
    for (_, m), p in zip(members.iterrows(), ip):
        n = kg.node(iri("surface-intake", m["code_ouvrage"]), L.SurfaceWaterIntake, m["nom_ouvrage"], "fr")
        kg.add(n, L.bnpeCode, Literal(m["code_ouvrage"]))
        kg.add(n, L.waterSource, L.SurfaceWaterSource)
        kg.point(n, "surface-intake", m["code_ouvrage"], p.x, p.y)
        kg.add(n, PROV.wasDerivedFrom, record(kg, "bnpe-ouvrage", m["code_ouvrage"], rel["bnpe-2026-10-20"]))
        near = list(rsidx.query(p.buffer(INTAKE_SNAP_M), predicate="intersects"))
        if near:
            d = [rivers_only.geometry.iloc[j].distance(p) for j in near]
            c = rivers_only["code_du_cours_d_eau_bdcarthage"].iloc[near[int(np.argmin(d))]]
            kg.add(n, L.candidateWatercourse, wc[c])
            n_cand += 1
        kg.add(group, L.intakeMember, n)

    return {"watercourses": len(wc), "reaches": len(reach),
            "canal_reaches": int((ctx.reaches["kind"] == "canal").sum()),
            "reach_pieces": n_pieces, "pieces_off_map": int(ctx.pieces["codepoly"].isna().sum()),
            "sections": {"water_bodies": sum(k == "water_body" for k, *_ in secs.values()),
                         "between_points": sum(k == "between_points" for k, *_ in secs.values())},
            "section_overlaps": len(overlaps) // 2,
            "gauges": len(gauge), "gauge_zone_relations": n_rel, "statements": len(ctx.st),
            "aggregate_statements": sum(r["subject"] == "aggregate" for r in ctx.st),
            "surface_intakes": len(members), "intakes_with_candidate_watercourse": n_cand,
            "polygons_met_by_pieces": len(ctx.polygons)}
