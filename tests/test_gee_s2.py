"""Offline checks of the Sentinel-2 parcel pull (src/ingest/gee_s2.py, v5 plan R1.4).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_gee_s2

No request is sent to Earth Engine: the checks cover what the module decides on the laptop.
1. Zone selection: a parcel touching a zone is kept whole, one outside is dropped, ids stay unique.
2. Batches are deterministic (the same order whatever the input order), compact (sorted by 2 km grid
   cell) and cover every parcel exactly once.
3. GeoJSON features are in EPSG:4326, one per parcel, in batch order.
4. The tidy step turns an Earth Engine table into one row per parcel: band means where Earth Engine
   returned them, n_px = 0 and NaN values for a parcel it returned without pixels or not at all
   (insufficient data, never a value), with the parcel's crop and areas attached.
5. The real 2023 edition: the zone parcels equal an independent overlay of the RPG with the 65 wells'
   3 km circles.
"""
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from src.config import CRS_L93, DATASET_DIR, INTERIM
from src.ingest import gee_s2 as G


def _toy_parcels():
    geoms = [box(0, 0, 100, 100), box(4950, 0, 5050, 100), box(9000, 9000, 9100, 9100),
             box(150, 0, 250, 80), box(2100, 2100, 2150, 2150)]
    return gpd.GeoDataFrame({"ID_PARCEL": ["a", "b", "c", "d", "e"], "SURF_PARC": [1.0, 1.0, 1.0, 0.8, 0.25],
                             "CODE_CULTU": ["VRC", "PFR", "BTH", "LEF", "PRL"],
                             "CODE_GROUP": [21, 20, 1, 22, 18]}, geometry=geoms, crs=CRS_L93)


def test_zone_selection(tmp):
    parcels = _toy_parcels()
    parcels.to_parquet(tmp)
    buffers = gpd.GeoDataFrame({"code_bss": ["w"]}, geometry=[Point(0, 0).buffer(3000)], crs=CRS_L93)
    orig = G.INTERIM
    try:
        G.INTERIM = tmp.parent
        tmp.rename(tmp.parent / "rpg_dept_1999.parquet")
        got = G.zone_parcels(1999, buffers)
    finally:
        G.INTERIM = orig
    assert sorted(got["ID_PARCEL"]) == ["a", "d", "e"], got["ID_PARCEL"].tolist()
    assert np.allclose(got.set_index("ID_PARCEL").loc["a", "area_m2"], 1e4)
    print("  1. zone selection keeps touching parcels whole and drops the far ones")


def test_batches():
    parcels = _toy_parcels()
    one = [b["ID_PARCEL"].tolist() for b in G.batches(parcels, size=2)]
    two = [b["ID_PARCEL"].tolist() for b in G.batches(parcels.sample(frac=1, random_state=3), size=2)]
    assert one == two, (one, two)
    flat = [pid for b in one for pid in b]
    assert sorted(flat) == sorted(parcels["ID_PARCEL"]) and len(flat) == len(set(flat))
    assert one[0][:2] == ["a", "d"], one          # the same 2 km cell first
    print(f"  2. batches deterministic and complete: {one}")


def test_geojson():
    parcels = _toy_parcels().iloc[:2]
    feats = G.geojson_features(parcels)
    assert [pid for pid, _ in feats] == ["a", "b"]
    lon, lat = np.array(feats[0][1]["coordinates"][0]).T
    assert (np.abs(lon) <= 180).all() and (np.abs(lat) <= 90).all()
    print("  3. GeoJSON features in EPSG:4326, one per parcel, in batch order")


def test_tidy():
    batch = _toy_parcels().iloc[:3].assign(area_m2=[1e4, 1e4, 1e4])
    ee_table = pd.DataFrame({"id": ["a", "b"], "ndvi_spring_mean": [0.5, np.nan], "ndvi_spring_count": [100, 0],
                             "ndmi_spring_mean": [0.1, np.nan], "nobs_spring_mean": [12.0, np.nan],
                             "ndvi_summer_mean": [0.7, np.nan], "ndvi_summer_count": [98, 0],
                             "ndmi_summer_mean": [0.2, np.nan], "nobs_summer_mean": [15.0, np.nan]})
    out = G.tidy(ee_table, 2023, batch).set_index("ID_PARCEL")
    assert list(out.index) == ["a", "b", "c"]
    assert out.loc["a", "ndvi_summer"] == 0.7 and out.loc["a", "n_px_summer"] == 98
    for pid in ("b", "c"):        # no pixels / not returned: insufficient data, never a value
        assert out.loc[pid, "n_px_summer"] == 0 and np.isnan(out.loc[pid, "ndvi_summer"])
    assert out.loc["c", "CODE_CULTU"] == "BTH" and (out["year"] == 2023).all()
    assert set(G.BANDS) <= set(out.columns)
    print("  4. tidy: one row per parcel; missing or pixel-less parcels get n_px 0 and no value")


def test_real_2023():
    from src.dataset.crop_demand import well_buffers
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    buffers = well_buffers(wells)
    got = set(G.zone_parcels(2023, buffers)["ID_PARCEL"])
    rpg = gpd.read_parquet(INTERIM / "rpg_dept_2023.parquet").to_crs(CRS_L93)
    rpg["geometry"] = rpg.geometry.make_valid()
    zone = buffers.union_all()
    want = set(rpg.loc[rpg.intersects(zone), "ID_PARCEL"].astype(str))
    assert got == want, (len(got ^ want), sorted(got ^ want)[:5])
    print(f"  5. real 2023 edition: {len(got)} zone parcels = an independent intersection with the union "
          f"of the {len(buffers)} wells' 3 km circles")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as d:
        test_zone_selection(Path(d) / "toy.parquet")
    test_batches()
    test_geojson()
    test_tidy()
    test_real_2023()
    print(f"test_gee_s2: all checks passed ({time.perf_counter() - started:.1f}s)")
