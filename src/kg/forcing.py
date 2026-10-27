"""Recharge-related forcing facts of the knowledge graph (CQ4), added by src.kg.build_kg.

  weather cells   the SAFRAN points of data/raw/safran/grid_cells_66.parquet, each taken as the 8 km
                  square centred on its point (Lambert II étendu, EPSG:27572; the SIM2 parameter list
                  calls LAMBX/LAMBY "the grid point's coordinate", the 8 km spacing is checked here),
                  densified every DENSIFY_M before reprojection to Lambert-93 so that neighbouring cells
                  keep their shared edges; with their weekly forcing series in
                  dataset_<v>/forcing_weekly.parquet (effective rainfall PE, soil drainage DRAINC)
  forcing extent  the union of the cells (extent "forcing-cells"): the unit-wide reference extent
  search zones    one outcrop search zone per piezometer: the area within ZONE_M of it (the radius of
                  the pumping influences, decided by Assil on 2026-10-26: analysis plan §14 item 14)
  intersections   for every reference extent, every elementary polygon of the graph and every cell:
                  the area of polygon ∩ cell ∩ extent, and the area of polygon ∩ extent outside every
                  cell, in m²; pieces under MIN_AREA_M2 are slivers of coincident edges and dropped
  mapped outcrop  per unit described by BD LISA, the area of all the elementary polygons of the
                  extract where it is at order 1, wherever they lie: the forcing extent clips a unit
                  whose outcrop reaches beyond the cells (681AF00: 15 %, 681AO00: 9 % outside), and
                  the CQ4 answer must say so (docs/competency_questions.md, CQ4: "state explicitly
                  whether S clips the unit")
Outcrop coverage and cell weights are derived from these by the SHACL-AF rules (order 60). The
outcrop polygons of the graph's units inside the cells are added to the polygons by build_kg
(outcrop_polygons), with their whole stacks.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from rdflib import Literal
from rdflib.namespace import RDFS, XSD
from shapely import segmentize, to_wkt
from shapely.geometry import Point, box

from src.analysis.bdlisa_profile import GPKG
from src.config import CRS_L93, DATASET, DATASET_DIR, RAW, ROOT
from src.ingest.safran import GRID_URL

GRID = RAW / "safran" / "grid_cells_66.parquet"
CRS_L2E = "EPSG:27572"          # Lambert II étendu, the SAFRAN grid's coordinates (hm)
SPACING_HM = 80                 # 8 km between grid points, in both directions
DENSIFY_M = 250.0
ZONE_M = 5000.0
MIN_AREA_M2 = 1.0
FORCING = {"PE": "EffectiveRainfall", "DRAINC": "SoilDrainage"}


def grid():
    """The weather cells as Lambert-93 polygons (cell_id, LAMBX, LAMBY, geometry)."""
    g = pd.read_parquet(GRID)
    for c in ("LAMBX", "LAMBY"):
        steps = set(np.diff(np.sort(g[c].unique())))
        assert steps == {SPACING_HM}, f"{c}: grid spacing {steps} hm, not {SPACING_HM}"
    half = SPACING_HM * 100 / 2
    squares = [segmentize(box(x * 100 - half, y * 100 - half, x * 100 + half, y * 100 + half), DENSIFY_M)
               for x, y in zip(g["LAMBX"], g["LAMBY"])]
    cells = gpd.GeoDataFrame(g[["cell_id", "LAMBX", "LAMBY"]], geometry=squares, crs=CRS_L2E).to_crs(CRS_L93)
    assert cells["cell_id"].is_unique
    return cells.reset_index(drop=True)


def zone(pt):
    """The outcrop search zone of a piezometer (a Lambert-93 point)."""
    return Point(pt.x, pt.y).buffer(ZONE_M, 256)


def area_of_interest(cells, points):
    """The cells and every search zone: where outcrop polygons are needed."""
    return cells.union_all().union(gpd.GeoSeries([zone(p) for p in points], crs=CRS_L93).union_all())


def outcrop_polygons(pile, poly, units, aoi):
    """Codes of the elementary polygons meeting `aoi` whose order-1 unit is one of `units`."""
    top = pile.loc[(pile["OrdRelatif"] == 1) & pile["CodeEH"].isin(units), "CodePoly"]
    cand = poly[poly["codepoly"].isin(set(top))]
    return set(cand.loc[cand.intersects(aoi), "codepoly"])


def mapped_outcrop(pile, codes):
    """{unit code: m²} of the elementary polygons of the whole extract where the unit is at order 1
    (0.0 for a unit never at outcrop there)."""
    top = pile.loc[(pile["OrdRelatif"] == 1) & pile["CodeEH"].isin(codes), ["CodePoly", "CodeEH"]]
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", columns=["codepoly"])
    area = pd.Series(poly.area.to_numpy(), index=poly["codepoly"].astype(str))
    assert area.index.is_unique
    m2 = top.assign(m2=top["CodePoly"].astype(str).map(area)).groupby("CodeEH")["m2"].sum(min_count=1)
    assert not m2.isna().any(), "an order-1 polygon of the stack table is missing from the layer"
    return {c: float(m2.get(c, 0.0)) for c in codes}


def pieces(geom, cells, sindex):
    """(cell_id or None, area) of geom inside each cell and outside every cell."""
    out, inside = [], 0.0
    for j in sindex.query(geom, predicate="intersects"):
        a = geom.intersection(cells.geometry.iloc[j]).area
        inside += a
        if a >= MIN_AREA_M2:
            out.append((cells["cell_id"].iloc[j], a))
    rest = geom.area - inside       # cells do not overlap, so the rest is outside every cell
    if rest >= MIN_AREA_M2:
        out.append((None, rest))
    return out


def add(kg, rel, wells, w_pts, keep, cells, versions, unit, pile, described):
    """Add the CQ4 facts; returns counts for build_kg's summary. `unit`: code -> node of the
    graph's units; `described`: the codes BD LISA describes (TME)."""
    from src.kg.build_kg import EPSG2154, GEO, L, PROV, dbl, file_date, iri

    codes = sorted(c for c in unit if c in described)
    outcrop = mapped_outcrop(pile, codes)
    for c in codes:
        kg.add(unit[c], L.mappedOutcropAreaM2, dbl(outcrop[c]))

    r = kg.node(iri("release", "sim2-grid"), L.DataRelease,
                "Météo-France SIM2 (SAFRAN-ISBA) grid points, Lambert II étendu", "en")
    kg.add(r, L.retrievalDate, Literal(file_date(GRID), datatype=XSD.date))
    kg.add(r, RDFS.comment, Literal(f"Source: {GRID_URL}; the points of the département extent are "
                                    f"kept in {GRID.relative_to(ROOT)}", lang="en"))
    rel["sim2-grid"] = r
    exe = kg.node(iri("execution", "polygon-cell-intersection"), L.RuleExecution,
                  "polygon-cell intersection areas (src/kg/forcing.py)", "en")
    kg.add(exe, L.codeVersion, Literal(versions["kg"]))
    kg.add(exe, RDFS.comment, Literal(
        f"Each SAFRAN grid point is taken as the 8 km square centred on it (EPSG:27572), densified every "
        f"{DENSIFY_M:g} m and reprojected to Lambert-93; elementary polygons are intersected with the "
        f"cells and with the reference extent (GeoPandas/Shapely); pieces under {MIN_AREA_M2:g} m² are "
        "dropped (src/kg/forcing.py).", lang="en"))
    kg.add(exe, PROV.used, rel["sim2-grid"])
    kg.add(exe, PROV.used, rel["bdlisa-v3-occ"])

    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["cell_id", "week"])
    span = forcing.groupby("cell_id")["week"].agg(["min", "max"])
    cell = {}
    for c in cells.itertuples():
        n = kg.node(iri("weather-cell", c.cell_id), L.WeatherCell, f"SAFRAN cell {c.cell_id}", "en")
        kg.add(n, L.safranGridXHm, Literal(int(c.LAMBX), datatype=XSD.integer))
        kg.add(n, L.safranGridYHm, Literal(int(c.LAMBY), datatype=XSD.integer))
        kg.add(n, GEO.hasMetricArea, dbl(c.geometry.area, 1))
        geom = kg.node(iri("geometry", "weather-cell", c.cell_id), GEO.Geometry)
        kg.add(geom, GEO.asWKT, Literal(EPSG2154 + to_wkt(c.geometry, rounding_precision=1),
                                        datatype=GEO.wktLiteral))
        kg.add(n, GEO.hasGeometry, geom)
        kg.add(n, L.inRelease, rel["sim2-grid"])
        for var, prop in FORCING.items():
            se = kg.node(iri("series", f"forcing-weekly-{DATASET}", c.cell_id, var), L.ObservationSeries)
            kg.add(n, L.hasForcingSeries, se)
            kg.add(se, L.seriesVariable, getattr(L, prop))
            kg.add(se, L.temporalResolution, Literal("P7D"))
            if c.cell_id in span.index:
                w0, w1 = span.loc[c.cell_id]
                kg.add(se, L.coverageStart, Literal(w0.date().isoformat(), datatype=XSD.date))
                kg.add(se, L.coverageEnd, Literal(w1.date().isoformat(), datatype=XSD.date))
            kg.add(se, L.storedIn, Literal(f"{(DATASET_DIR / 'forcing_weekly.parquet').relative_to(ROOT)}"
                                           f" [cell_id = {c.cell_id}, column {var}]"))
            kg.add(se, L.qualityPolicy, Literal("weekly sum of the daily SIM2 values (weeks ending Sunday)"))
            kg.add(se, L.inRelease, rel[f"dataset-{DATASET}"])
        cell[c.cell_id] = n

    union = cells.union_all()
    fx = kg.node(iri("extent", "forcing-cells"), GEO.Feature,
                 f"the {len(cells)} SAFRAN cells of the département extent: the unit-wide reference "
                 "extent of CQ4", "en")
    fg = kg.node(iri("geometry", "extent", "forcing-cells"), GEO.Geometry)
    kg.add(fg, GEO.asWKT, Literal(EPSG2154 + to_wkt(union, rounding_precision=1), datatype=GEO.wktLiteral))
    kg.add(fx, GEO.hasGeometry, fg)
    extents = [("forcing-cells", fx, union)]
    for i, (_, w) in enumerate(wells.iterrows()):
        key = w["bss_id"] if isinstance(w["bss_id"], str) and w["bss_id"] else w["code_bss"]
        z = kg.node(iri("outcrop-zone", key), L.OutcropSearchZone)
        kg.add(z, L.zoneOf, iri("piezometer", key))
        kg.add(z, L.zoneRadiusM, dbl(ZONE_M))
        kg.add(z, RDFS.comment, Literal(f"The area within {ZONE_M:g} m of the piezometer (Lambert-93)",
                                        lang="en"))
        extents.append((f"zone-{key}", z, zone(w_pts.iloc[i])))

    sindex = cells.sindex
    n_pieces = 0
    for ekey, ext_node, ext_geom in extents:
        inside = keep[keep.intersects(ext_geom)]
        for cp, g in zip(inside["codepoly"], inside.geometry):
            part = g.intersection(ext_geom)
            for cid, a in pieces(part, cells, sindex):
                x = kg.node(iri("polygon-cell", ekey, cp, cid or "outside"), L.PolygonCellIntersection)
                kg.add(x, L.intersectedPolygon, iri("polygon", cp))
                if cid is not None:
                    kg.add(x, L.intersectedCell, cell[cid])
                kg.add(x, L.withinExtent, ext_node)
                kg.add(x, L.intersectionAreaM2, dbl(a))
                kg.add(x, PROV.wasGeneratedBy, exe)
                n_pieces += 1
    return {"weather_cells": len(cells), "forcing_extent_km2": round(union.area / 1e6, 1),
            "outcrop_search_zones": len(wells), "polygon_cell_intersections": n_pieces,
            "units_with_mapped_outcrop": sum(v > 0 for v in outcrop.values())}
