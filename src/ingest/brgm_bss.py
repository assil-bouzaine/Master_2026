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
spatial pulls. Pages of PAGE features (STARTINDEX paging works past the server's 1000-feature cap),
one second apart. Every attribute is kept as the service gives it (strings); conversions happen
downstream. Output: data/raw/brgm_bss/<YYYY-MM-DD>/<layer>.parquet (GeoParquet, EPSG:4326) and
release.json (endpoint, parameters, counts, retrieval time). A layer already saved for that day is
skipped.
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
PAGE = 1000
GEOJSON = "application/json; subtype=geojson; charset=utf-8"
OUT = RAW / "brgm_bss"


def params(layer, start):
    lon0, lat0, lon1, lat1 = DEPT_BBOX
    # WFS 2.0.0 with the EPSG URN: axis order latitude, longitude.
    return {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": f"ms:{layer}", "COUNT": PAGE, "STARTINDEX": start,
            "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
            "BBOX": f"{lat0},{lon0},{lat1},{lon1},urn:ogc:def:crs:EPSG::4326",
            "OUTPUTFORMAT": GEOJSON}


def fetch_layer(session, layer):
    """All features of one layer inside the extent, page by page."""
    rows, start = [], 0
    while True:
        r = session.get(ENDPOINT, params=params(layer, start), timeout=TIMEOUT)
        r.raise_for_status()
        feats = r.json().get("features", [])
        for f in feats:
            props = dict(f.get("properties") or {})
            geom = f.get("geometry") or {}
            if geom.get("type") == "Point":
                # GeoJSON output is longitude, latitude whatever the request's axis order.
                props["lon_wfs"], props["lat_wfs"] = geom["coordinates"][:2]
            rows.append(props)
        print(f"  {layer}: {start + len(feats)} features")
        if len(feats) < PAGE:
            break
        start += PAGE
        time.sleep(1.0)
    df = pd.DataFrame(rows)
    if df.empty:
        return gpd.GeoDataFrame(df)
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon_wfs"], df["lat_wfs"]), crs="EPSG:4326")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layers", nargs="+", default=list(LAYERS), choices=LAYERS)
    ap.add_argument("--day", default=dt.date.today().isoformat(), help="snapshot folder (default today)")
    args = ap.parse_args()
    out = OUT / args.day
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "release.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {
        "endpoint": ENDPOINT, "bbox_wgs84": list(DEPT_BBOX), "page_size": PAGE, "layers": {}}
    session = make_session()
    for layer in args.layers:
        path = out / f"{layer.lower()}.parquet"
        if path.exists() and path.stat().st_size > 0:
            print(f"{layer}: already saved ({path}), skipped")
            continue
        gdf = fetch_layer(session, layer)
        if gdf.empty:
            raise SystemExit(f"{layer}: the service returned no feature for the extent")
        gdf.to_parquet(path, index=False)
        meta["layers"][layer] = {"rows": int(len(gdf)), "columns": list(gdf.columns),
                                 "bytes": path.stat().st_size,
                                 "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        print(f"{layer}: {len(gdf)} rows, {len(gdf.columns)} columns -> {path}")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
