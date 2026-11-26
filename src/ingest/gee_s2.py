"""Sentinel-2 spring and summer vegetation and moisture per farm parcel, from Google Earth Engine.

    PFE_DATASET=v5 python -m src.ingest.gee_s2 --plan                 # parcels and batches, no request
    PFE_DATASET=v5 python -m src.ingest.gee_s2                        # 2017-2025, resumable
    PFE_DATASET=v5 python -m src.ingest.gee_s2 --years 2023 --workers 2

Why (docs/v5_plan.md R1.4; docs/analysis_plan_v3.md §1 and §8 item 4, decided by Assil on 2026-11-26;
docs/competency_questions.md CQ15): the subject's objective SO2 asks for a satellite-derived concept,
`lulcw:ProbablyIrrigatedParcel`: a parcel whose vegetation stays active in the dry summer while the soil
of its weather cell is dry is a candidate for irrigation. This module pulls only the **observations**
the rule needs, per RPG parcel and season, with their quality: it classifies nothing (the rule, its
thresholds frozen on training years, and its validation come later, CQ15).

What is pulled (one row per parcel, edition year and season):
- parcels: the RPG edition of the year (data/interim/rpg_dept_<year>.parquet, built by src.ingest.rpg)
  that intersect at least one well's 3 km zone, the zones of the crop-demand index
  (src.dataset.crop_demand.well_buffers), so CQ15 and the demand index describe the same land. Whole
  parcels are sent (the observation belongs to the parcel; the share inside each zone is computed
  downstream), simplified to SIMPLIFY_M in Lambert-93.
- images: COPERNICUS/S2_SR_HARMONIZED (Sentinel-2 level-2A surface reflectance, harmonised across the
  2022 processing-baseline change), seasons SEASONS (spring: April-May, summer: July-August), every
  acquisition over the zones.
- cloud mask: the scene classification band SCL; a pixel counts only when it is vegetation (4), bare
  soil (5) or water (6): clouds, shadows, cirrus, snow, saturated and unclassified pixels are dropped.
- per pixel: the median over the season's valid acquisitions of NDVI = (B8 - B4) / (B8 + B4) and
  NDMI = (B8 - B11) / (B8 + B11) (B11 is 20 m, resampled by Earth Engine), and the number of valid
  acquisitions (nobs);
- per parcel (reduceRegions at 10 m, a pixel counts when its centre is inside): the mean of those
  per-pixel values, and the number of valid pixels (n_px). A parcel smaller than a pixel, or covered by
  clouds every time, gets n_px = 0: "insufficient data" for the rule, never a value.

Earth Engine runs under Assil's Cloud project (EE_PROJECT; .agents/RESOURCES.md); the laptop's sign-in
is his. Requests: batches of BATCH parcels, a few in parallel, retried with backoff on quota errors.
Output: data/raw/gee_s2/<folder>/s2_<year>_<batch>.parquet (one file per request, skipped if present:
the pull resumes), then s2_parcels_<year>.parquet per year and release.json (collection, seasons,
mask, scale, retrieval date, counts). Log each pull in data/README.md.
"""
import argparse
import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, DATASET_DIR, INTERIM, RAW

EE_PROJECT = "bright-proxy-486018-s9"
COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
SEASONS = {"spring": (4, 5), "summer": (7, 8)}         # months, inclusive
SCL_KEEP = (4, 5, 6)                                  # vegetation, not vegetated, water
SCALE_M = 10
SIMPLIFY_M = 2.0
BATCH = 800
YEARS = tuple(range(2017, 2026))                       # S2 level-2A over France from 2017-03-28
OUT = RAW / "gee_s2"
BANDS = [f"{v}_{s}" for s in SEASONS for v in ("ndvi", "ndmi", "nobs")]


def zone_parcels(year, buffers):
    """The edition's parcels that intersect at least one zone: id, crop, declared and mapped area."""
    p = gpd.read_parquet(INTERIM / f"rpg_dept_{year}.parquet")
    p = p.to_crs(CRS_L93)
    p["geometry"] = p.geometry.make_valid()
    hit = gpd.sjoin(p[["ID_PARCEL", "geometry"]], buffers[["geometry"]], how="inner",
                    predicate="intersects")["ID_PARCEL"].unique()
    p = p[p["ID_PARCEL"].isin(hit)].copy()
    p["area_m2"] = p.area
    p["ID_PARCEL"] = p["ID_PARCEL"].astype(str)
    if p["ID_PARCEL"].duplicated().any():
        raise ValueError(f"RPG {year}: duplicated ID_PARCEL")
    return p[["ID_PARCEL", "CODE_CULTU", "CODE_GROUP", "SURF_PARC", "area_m2", "geometry"]]


def batches(parcels, size=BATCH):
    """Spatially compact, deterministic batches: parcels sorted by a 2 km grid cell, then by id."""
    c = parcels.geometry.centroid
    key = pd.DataFrame({"gx": (c.x // 2000).astype(int), "gy": (c.y // 2000).astype(int),
                        "id": parcels["ID_PARCEL"].to_numpy()}, index=parcels.index)
    order = key.sort_values(["gy", "gx", "id"]).index
    p = parcels.loc[order]
    return [p.iloc[i:i + size] for i in range(0, len(p), size)]


def geojson_features(batch):
    """GeoJSON geometries (EPSG:4326) of a batch, simplified in metres first, with the parcel id."""
    geom = batch.geometry.simplify(SIMPLIFY_M, preserve_topology=True).to_crs(CRS_WGS84)
    feats = json.loads(gpd.GeoSeries(geom.to_numpy(), crs=CRS_WGS84).to_json())["features"]
    return [(pid, f["geometry"]) for pid, f in zip(batch["ID_PARCEL"], feats)]


def season_image(ee, year, region):
    """Per-pixel seasonal medians of NDVI and NDMI and valid-acquisition counts, both seasons."""
    keep = SCL_KEEP

    def indices(img):
        scl = img.select("SCL")
        ok = scl.eq(keep[0])
        for k in keep[1:]:
            ok = ok.Or(scl.eq(k))
        return (img.normalizedDifference(["B8", "B4"]).rename("ndvi")
                .addBands(img.normalizedDifference(["B8", "B11"]).rename("ndmi"))
                .updateMask(ok))

    parts = []
    for tag, (m0, m1) in SEASONS.items():
        end = f"{year + 1}-01-01" if m1 == 12 else f"{year}-{m1 + 1:02d}-01"
        col = (ee.ImageCollection(COLLECTION).filterBounds(region)
               .filterDate(f"{year}-{m0:02d}-01", end).map(indices))
        parts.append(col.median().rename([f"ndvi_{tag}", f"ndmi_{tag}"]))
        parts.append(col.select("ndvi").count().rename(f"nobs_{tag}"))
    img = parts[0]
    for part in parts[1:]:
        img = img.addBands(part)
    return img.select(BANDS)


def tidy(df, year, batch):
    """computeFeatures output -> one row per parcel: band means and the valid-pixel count."""
    out = pd.DataFrame({"ID_PARCEL": batch["ID_PARCEL"].to_numpy()})
    got = df.set_index("id") if len(df) else pd.DataFrame(index=pd.Index([], name="id"))
    for band in BANDS:
        col = f"{band}_mean"
        out[band] = out["ID_PARCEL"].map(got[col]) if col in got else np.nan
    for tag in SEASONS:
        col = f"ndvi_{tag}_count"
        out[f"n_px_{tag}"] = (out["ID_PARCEL"].map(got[col]) if col in got else 0)
        out[f"n_px_{tag}"] = out[f"n_px_{tag}"].fillna(0).astype(int)
    out.insert(0, "year", year)
    meta = batch.set_index("ID_PARCEL")[["CODE_CULTU", "CODE_GROUP", "SURF_PARC", "area_m2"]]
    return out.join(meta, on="ID_PARCEL")


def fetch_batch(ee, image, year, batch, retries=6):
    feats = [ee.Feature(ee.Geometry(g), {"id": pid}) for pid, g in geojson_features(batch)]
    fc = ee.FeatureCollection(feats)
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    expr = image.reduceRegions(collection=fc, reducer=reducer, scale=SCALE_M, tileScale=4)
    for attempt in range(retries):
        try:
            df = ee.data.computeFeatures({"expression": expr, "fileFormat": "PANDAS_DATAFRAME"})
            return tidy(pd.DataFrame(df).drop(columns=["geo"], errors="ignore"), year, batch)
        except Exception as err:                              # quota, timeout, transient server error
            if attempt == retries - 1:
                raise
            wait = 10 * 2 ** attempt
            print(f"  {year}: retry in {wait} s after {type(err).__name__}: {str(err)[:120]}", flush=True)
            time.sleep(wait)


def run_year(ee, year, buffers, folder, workers):
    parcels = zone_parcels(year, buffers)
    parts = batches(parcels)
    region = ee.Geometry.Rectangle(list(buffers.to_crs(CRS_WGS84).total_bounds), None, False)
    image = season_image(ee, year, region)
    todo = [(i, b) for i, b in enumerate(parts) if not (folder / f"s2_{year}_{i:03d}.parquet").exists()]
    print(f"{year}: {len(parcels)} parcels, {len(parts)} batches, {len(todo)} to fetch", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_batch, ee, image, year, b): i for i, b in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            i = futures[fut]
            fut.result().to_parquet(folder / f"s2_{year}_{i:03d}.parquet", index=False)
            if n % 5 == 0 or n == len(todo):
                print(f"  {year}: {n}/{len(todo)} batches ({time.time() - t0:.0f} s)", flush=True)
    table = pd.concat([pd.read_parquet(folder / f"s2_{year}_{i:03d}.parquet") for i in range(len(parts))],
                      ignore_index=True)
    if len(table) != len(parcels) or table["ID_PARCEL"].duplicated().any():
        raise ValueError(f"{year}: {len(table)} rows for {len(parcels)} parcels")
    table.to_parquet(folder / f"s2_parcels_{year}.parquet", index=False)
    return {"parcels": int(len(parcels)), "batches": len(parts),
            **{f"with_pixels_{s}": int((table[f"n_px_{s}"] > 0).sum()) for s in SEASONS}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    ap.add_argument("--folder", default=dt.date.today().isoformat())
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--plan", action="store_true", help="count parcels and batches; send no request")
    args = ap.parse_args()
    from src.dataset.crop_demand import well_buffers
    buffers = well_buffers(pd.read_parquet(DATASET_DIR / "wells.parquet"))
    if args.plan:
        for y in args.years:
            p = zone_parcels(y, buffers)
            print(f"{y}: {len(p)} parcels in the zones, {len(batches(p))} batches of {BATCH}")
        return
    import ee
    ee.Initialize(project=EE_PROJECT)
    folder = OUT / args.folder
    folder.mkdir(parents=True, exist_ok=True)
    release = folder / "release.json"
    meta = json.loads(release.read_text()) if release.exists() else {
        "collection": COLLECTION, "seasons_months": SEASONS, "scl_keep": SCL_KEEP, "scale_m": SCALE_M,
        "simplify_m": SIMPLIFY_M, "batch": BATCH, "zones": "3 km around each well of the dataset "
        "(src.dataset.crop_demand.well_buffers)", "ee_project": EE_PROJECT, "years": {}}
    for y in args.years:
        meta["years"][str(y)] = run_year(ee, y, buffers, folder, args.workers) | {
            "retrieved": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        release.write_text(json.dumps(meta, indent=1))
    print(f"-> {folder}")


if __name__ == "__main__":
    main()
