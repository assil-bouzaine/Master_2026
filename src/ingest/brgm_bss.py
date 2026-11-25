"""Download BRGM's borehole database (BSS) points over the département extent, from the open WFS.

    python -m src.ingest.brgm_bss            # both layers, today's snapshot, resumable
    python -m src.ingest.brgm_bss --layers BSS_EAU_POINT

Why (docs/v5_plan.md, step R1.3; gemini_neon_review.md §2.1.3): the pump -> aquifer attribution
(src/kg/pump_attribution.py, task 12.3) gives no unit to the BNPE irrigation boreholes, because the
BNPE records carry neither a BSS code nor a depth for most of them. BRGM publishes the BSS points as
an open WFS on its geology geoservice (checked 2026-11-25 with GetCapabilities and
DescribeFeatureType; Etalab Open Licence 2.0):
    https://geoservices.brgm.fr/geologie   (MapServer WFS 2.0.0)
Two layers are kept:
- ms:BSS_EAU_POINT: the water points (wells, boreholes, springs) with the investigation depth
  (`prof_invest`), the BD LISA entities BRGM associates with the point (`liste_bdlisa`), the
  aquifer condition (`mode_gisement`) and the point's nature (`nature_pe`). How BRGM fills
  `liste_bdlisa` (recorded aquifer or location) is not documented on the service: its precision
  must be measured against the boreholes whose unit we know before it is used (CLAUDE.md §3:
  confidence levels are measured, not assumed).
- ms:BSS_TOTAL_SANS_LABEL: every BSS borehole, with the depth reached (`prof_atteinte`), its use
  (`utilisation`, `exploitation`, `ouvrage_eau`) and whether a geological log exists.

The extent is DEPT_BBOX (src.ingest.safran: lon 1.65-3.25, lat 42.30-43.00), as for the other
spatial pulls, cut into tiles of TILE_DEG degrees; a tile that returns the server's cap of CAP
features is split in four, recursively, so every request is complete without paging. (The first
pull of 2026-11-25 paged with STARTINDEX and no sort order: MapServer's order is not stable between
requests, so pages overlapped (1,556 duplicate water points, 2,658 duplicate boreholes, found by
worker neon in T62) and may have skipped features; it is kept in data/raw/brgm_bss/2026-11-25/ and
superseded by the tiled pull in 2026-11-25-tiled/.) A feature on a tile edge can come twice: rows are
deduplicated on the layer's id (`gid` or `gis`) and the count of removed duplicates is recorded.
Requests are one second apart. Every attribute is kept as the service gives it (strings);
conversions happen downstream. Output: data/raw/brgm_bss/<folder>/<layer>.parquet (GeoParquet,
EPSG:4326) and release.json (endpoint, parameters, counts, retrieval time). A layer already saved
in that folder is skipped.
"""
import argparse
import datetime as dt
import json
import time

import geopandas as gpd
import pandas as pd

from src.config import RAW
from src.ingest.safran import DEPT_BBOX
from src.web import TIMEOUT, make_session

ENDPOINT = "https://geoservices.brgm.fr/geologie"
LAYERS = ("BSS_EAU_POINT", "BSS_TOTAL_SANS_LABEL")
ID = {"BSS_EAU_POINT": "gid", "BSS_TOTAL_SANS_LABEL": "gis"}
CAP = 1000          # the server returns at most this many features per request
TILE_DEG = 0.2
GEOJSON = "application/json; subtype=geojson; charset=utf-8"
OUT = RAW / "brgm_bss"


def params(layer, box):
    lon0, lat0, lon1, lat1 = box
    # WFS 2.0.0 with the EPSG URN: axis order latitude, longitude.
    return {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": f"ms:{layer}", "COUNT": CAP,
            "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
            "BBOX": f"{lat0},{lon0},{lat1},{lon1},urn:ogc:def:crs:EPSG::4326",
            "OUTPUTFORMAT": GEOJSON}


def tiles(box, step=TILE_DEG):
    lon0, lat0, lon1, lat1 = box
    xs = [lon0 + i * step for i in range(int((lon1 - lon0) / step + 1 - 1e-9))] + [lon1]
    ys = [lat0 + j * step for j in range(int((lat1 - lat0) / step + 1 - 1e-9))] + [lat1]
    xs, ys = sorted(set(round(x, 6) for x in xs)), sorted(set(round(y, 6) for y in ys))
    return [(a, b, c, d) for a, c in zip(xs[:-1], xs[1:]) for b, d in zip(ys[:-1], ys[1:])]


def fetch_box(session, layer, box, depth=0):
    """All features of one box: split in four while the server's cap is reached."""
    r = session.get(ENDPOINT, params=params(layer, box), timeout=TIMEOUT)
    r.raise_for_status()
    time.sleep(1.0)
    if not r.content.strip():   # MapServer answers an empty tile with HTTP 200 and an empty body
        return []
    try:
        feats = r.json().get("features", [])
    except ValueError:
        raise SystemExit(f"{layer}: {box}: not GeoJSON: {r.text[:300]!r}")
    if len(feats) < CAP:
        return feats
    if depth > 8:
        raise SystemExit(f"{layer}: {box} still returns {CAP} features after 8 splits")
    lon0, lat0, lon1, lat1 = box
    xm, ym = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    out = []
    for sub in ((lon0, lat0, xm, ym), (xm, lat0, lon1, ym), (lon0, ym, xm, lat1), (xm, ym, lon1, lat1)):
        out += fetch_box(session, layer, sub, depth + 1)
    return out


def fetch_layer(session, layer):
    """All features of one layer inside the extent, tile by tile; duplicates removed on the id."""
    rows = []
    for i, box in enumerate(tiles(DEPT_BBOX), 1):
        for f in fetch_box(session, layer, box):
            props = dict(f.get("properties") or {})
            geom = f.get("geometry") or {}
            if geom.get("type") == "Point":
                # GeoJSON output is longitude, latitude whatever the request's axis order.
                props["lon_wfs"], props["lat_wfs"] = geom["coordinates"][:2]
            rows.append(props)
        print(f"  {layer}: tile {i}, {len(rows)} features so far")
    df = pd.DataFrame(rows)
    if df.empty:
        return gpd.GeoDataFrame(df), 0
    n = len(df)
    df = df.drop_duplicates(subset=[ID[layer]]).reset_index(drop=True)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon_wfs"], df["lat_wfs"]), crs="EPSG:4326")
    return gdf, n - len(gdf)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layers", nargs="+", default=list(LAYERS), choices=LAYERS)
    ap.add_argument("--folder", default=dt.date.today().isoformat() + "-tiled",
                    help="snapshot folder under data/raw/brgm_bss (default: today-tiled)")
    args = ap.parse_args()
    out = OUT / args.folder
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "release.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {
        "endpoint": ENDPOINT, "bbox_wgs84": list(DEPT_BBOX), "tile_deg": TILE_DEG, "cap": CAP,
        "method": "tiles split while the cap is reached; deduplicated on the layer id", "layers": {}}
    session = make_session()
    for layer in args.layers:
        path = out / f"{layer.lower()}.parquet"
        if path.exists() and path.stat().st_size > 0:
            print(f"{layer}: already saved ({path}), skipped")
            continue
        gdf, dups = fetch_layer(session, layer)
        if gdf.empty:
            raise SystemExit(f"{layer}: the service returned no feature for the extent")
        gdf.to_parquet(path, index=False)
        meta["layers"][layer] = {"rows": int(len(gdf)), "edge_duplicates_removed": int(dups),
                                 "columns": list(gdf.columns),
                                 "bytes": path.stat().st_size,
                                 "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        print(f"{layer}: {len(gdf)} rows ({dups} tile-edge duplicates removed), {len(gdf.columns)} columns -> {path}")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
