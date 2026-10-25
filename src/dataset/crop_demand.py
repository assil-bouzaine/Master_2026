"""Weekly potential crop irrigation demand around each well (LU-3, the "crop thirst" index).

    PFE_DATASET=v4 python -m src.dataset.crop_demand

For well w and week t, with y(t) the RPG edition used for t:

    demand(w, t) = sum over crop classes c of
                   A(c, w, y(t)) [ha] x max(0, Kc(c, t) x ETP(t) - rain(t)) [mm/week] x 10

in m3/week (1 mm on 1 ha = 10 m3). A is the *clipped* parcel area inside the 3 km
buffer of the well (CQ7: a 10 ha parcel half inside counts 5 ha), not the
centroid-selected whole-parcel area of src/analysis/rpg_profile.py. ETP (SIM2, FAO-56
Penman-Monteith) and rain (liquid + solid) are weekly sums on the well's SAFRAN cell,
so the deficit is the project's weekly climatic deficit max(ETP - rain, 0) with ETP
scaled by the crop coefficient. SIM2's PE (water surplus after the soil fills) is not
used: it is near zero all summer by construction. Soil storage is ignored, so this is an
index of the timing and size of demand, not a field water balance.

Kc follows the FAO-56 four-stage curve (Allen et al. 1998, FAO Irrigation and Drainage
Paper 56, Tables 11-12; fao.org/4/X0490E/x0490e0b.htm, read 2026-10-25), on calendar
dates: each season starts on day 1 of plant_month every year; Kc is constant over the
initial stage, linear to Kc_mid over development, constant over mid-season, linear to
Kc_end over the late stage. Off season, perennial classes keep Kc_ini and annual classes
have no crop (Kc = 0). Weekly Kc = mean over the 7 days of the week (Monday-Sunday,
labelled by the Sunday, as the forcing). Parameters: configs/lu_crop_classes.csv.

This is a *potential requirement*: crop identity is observed; whether a parcel is
irrigated, and from which source, are not (CQ7, CQ15). The main index `demand_main_m3`
sums the classes whose irrigation assumption is "usually" (orchards, vegetables,
artichokes, maize, citrus); `demand_wide_m3` adds the "partly" classes (vines, olives,
nuts, fodder) as a sensitivity. Decided by Assil on 2026-10-25 before any land-use run
(analysis plan §14 item 13): in the 2020 census of dept 66 about 4-7 % of the vines are
irrigated, against most orchards and vegetables, so counting every vineyard would let
mostly unirrigated vines dominate the index.

RPG editions: each calendar year uses its own edition; a missing year uses the nearest
earlier edition, years before the first edition use the first one (`rpg_backfill`),
`rpg_lag_years` = year - edition used. Parcels come from the département-wide clips
(src/ingest/rpg.py --clip dept); every buffer must lie inside that extent. RPG covers
France only: `zone_partly_foreign` flags wells whose zone reaches Spain or Andorra
(src/ingest/borders.py), whose demand then covers the French part only (none at 3 km).

Placebo (analysis plan §14 item 13): `demand_main_placebo_m3` gives each well its own
weather with the main classes' areas of another well (`placebo_donor`, a seeded
derangement: no well keeps its own areas). A model that gains from the real index but not from the
placebo uses the crop information, not just a per-well signature.

Outputs: data/interim/crop_area_3km.parquet        clipped ha by well x edition x crop code
         data/interim/crop_area_3km_meta.json      what the area cache was built from
         data/interim/crop_demand_weekly_<dataset>.parquet  well x week demand (m3/week)
"""
import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, ROOT

CLASSES = ROOT / "configs" / "lu_crop_classes.csv"
BUFFER_M = 3000
MAIN = ("usually",)            # irrigation assumptions in the main index
WIDE = ("usually", "partly")    # the sensitivity row
AREA_OUT = INTERIM / "crop_area_3km.parquet"
AREA_META = INTERIM / "crop_area_3km_meta.json"
FOREIGN = INTERIM / "foreign_land_66.parquet"
PLACEBO_SEED = 0


def load_classes(path=CLASSES):
    return pd.read_csv(path, dtype=str, keep_default_na=False).set_index("class")


def code_to_class(codes, groups, classes):
    """Crop class of each parcel: code override first, then the RPG crop group."""
    by_group, by_code = {}, {}
    for k, r in classes.iterrows():
        for g in r["rpg_groups"].split():
            by_group[g] = k
        for c in r["code_overrides"].split():
            by_code[c] = k
    groups = pd.Series(groups).astype("string").str.strip()
    out = pd.Series(codes).map(by_code).fillna(groups.map(by_group))
    return out.fillna("unmapped")


def season_curve(r):
    """Kc for each day since planting (FAO-56 four stages); empty for 'no crop'."""
    if not r["kc_ini"]:
        return np.zeros(0)
    ini, mid, end = float(r["kc_ini"]), float(r["kc_mid"]), float(r["kc_end"])
    li, ld, lm, ll = (int(r[k]) for k in ("l_ini", "l_dev", "l_mid", "l_late"))
    return np.concatenate([np.full(li, ini), np.linspace(ini, mid, ld + 1)[1:],
                           np.full(lm, mid), np.linspace(mid, end, ll + 1)[1:]])


def kc_on_dates(dates, r):
    """Kc of one class row on each date; a season longer than a year is cut at one year."""
    dates = pd.DatetimeIndex(dates).normalize()
    curve = season_curve(r)
    if not len(curve):
        return np.zeros(len(dates))
    off = float(r["kc_ini"]) if r["perennial"] == "yes" else 0.0
    month = int(r["plant_month"])

    def planting(years):
        return pd.to_datetime(pd.DataFrame({"year": years, "month": month, "day": 1}))

    days = (dates - pd.DatetimeIndex(planting(dates.year))).days.to_numpy()
    before = days < 0  # still in the season planted the year before
    days[before] = (dates[before] - pd.DatetimeIndex(planting(dates.year[before] - 1))).days.to_numpy()
    return np.where(days < len(curve), curve[np.minimum(days, len(curve) - 1)], off)


def kc_weekly(weeks, classes):
    """Mean Kc over the 7 days ending on each week label: DataFrame week x class."""
    weeks = pd.DatetimeIndex(weeks)
    days = pd.date_range(weeks.min() - pd.Timedelta(days=6), weeks.max(), freq="D")
    daily = pd.DataFrame({k: kc_on_dates(days, r) for k, r in classes.iterrows()}, index=days)
    return daily.rolling(7).mean().reindex(weeks)


def rpg_years():
    return sorted(int(p.stem.rsplit("_", 1)[1]) for p in INTERIM.glob("rpg_dept_*.parquet"))


def year_map(years_needed, available):
    """Calendar year -> RPG edition used (nearest earlier, else the first)."""
    av = np.array(sorted(available))
    out = {}
    for y in years_needed:
        earlier = av[av <= y]
        out[y] = int(earlier[-1]) if len(earlier) else int(av[0])
    return out


def well_buffers(wells):
    pts = gpd.GeoSeries.from_xy(wells["x"], wells["y"], crs=CRS_WGS84).to_crs(CRS_L93)
    return gpd.GeoDataFrame({"code_bss": wells["code_bss"].to_numpy()},
                            geometry=pts.buffer(BUFFER_M).to_numpy(), crs=CRS_L93)


def foreign_share(buffers):
    """Share of each zone on Spanish or Andorran land (RPG has no data there)."""
    if not FOREIGN.exists():
        raise FileNotFoundError(f"{FOREIGN.name} missing: run python -m src.ingest.borders")
    land = gpd.read_parquet(FOREIGN).to_crs(CRS_L93).union_all()
    return pd.Series(buffers.intersection(land).area.to_numpy() / buffers.area.to_numpy(),
                     index=buffers["code_bss"].to_numpy())


def clipped_area(parcels, buffers):
    """Hectares of each crop code inside each buffer (intersection area, not centroids)."""
    p = parcels[["CODE_CULTU", "CODE_GROUP", "geometry"]].copy()
    p["geometry"] = p.geometry.make_valid()
    x = gpd.overlay(p, buffers, how="intersection", keep_geom_type=True)
    x["ha"] = x.area / 1e4
    return x.groupby(["code_bss", "CODE_CULTU", "CODE_GROUP"], as_index=False, dropna=False)["ha"].sum()


def build_areas(wells, rebuild=False):
    """Clipped area by well x edition x crop code, cached with what it was built from."""
    from src.ingest.rpg import extent_l93
    buffers = well_buffers(wells)
    outside = ~buffers.within(box(*extent_l93("dept")))
    if outside.any():
        raise RuntimeError(f"zones outside the RPG clip extent: {list(buffers.loc[outside, 'code_bss'])}")
    files = {y: INTERIM / f"rpg_dept_{y}.parquet" for y in rpg_years()}
    if not files:
        raise FileNotFoundError("no rpg_dept_<year>.parquet: run src.ingest.rpg --clip dept")
    meta = {"buffer_m": BUFFER_M, "wells": sorted(wells["code_bss"]),
            "inputs": {str(y): [p.stat().st_size, int(p.stat().st_mtime)] for y, p in files.items()}}
    if not rebuild and AREA_OUT.exists() and AREA_META.exists() and json.loads(AREA_META.read_text()) == meta:
        return pd.read_parquet(AREA_OUT)
    parts = []
    for y, path in files.items():
        g = gpd.read_parquet(path).set_crs(CRS_L93, allow_override=True)
        a = clipped_area(g, buffers).assign(rpg_year=y)
        print(f"  RPG {y}: {len(g):,} parcels, {a['ha'].sum():,.0f} ha inside the {len(buffers)} zones "
              f"(overlapping zones count twice)")
        parts.append(a)
    a = pd.concat(parts, ignore_index=True)
    a.to_parquet(AREA_OUT, index=False)
    AREA_META.write_text(json.dumps(meta, indent=1))
    return a


def derangement(codes, seed=PLACEBO_SEED):
    """{well: donor well}: a seeded random permutation in which no well keeps its own."""
    rng = np.random.default_rng(seed)
    codes = list(codes)
    while True:
        perm = rng.permutation(len(codes))
        if not (perm == np.arange(len(codes))).any():
            return {c: codes[p] for c, p in zip(codes, perm)}


def demand(wells, forcing, areas, classes, foreign):
    """Well x week demand (m3/week), per irrigation assumption, with the edition used.
    `demand_main_placebo_m3`: the well's own weather with the main classes' areas of
    another well (derangement), the placebo of the analysis plan §14 item 13."""
    weeks = pd.DatetimeIndex(sorted(forcing["week"].unique()))
    kc = kc_weekly(weeks, classes)
    f = forcing.set_index(["cell_id", "week"])[["ETP", "rain"]]
    areas = areas.assign(crop_class=code_to_class(areas["CODE_CULTU"].to_numpy(),
                                                  areas["CODE_GROUP"].to_numpy(), classes).to_numpy())
    avail = sorted(areas["rpg_year"].unique())
    ymap = year_map(sorted(set(weeks.year)), avail)
    wide = areas.pivot_table(index=["code_bss", "rpg_year"], columns="crop_class",
                             values="ha", aggfunc="sum", fill_value=0.0)
    assumption = classes["irrigation_assumption"]
    used = pd.Series(weeks.year.map(ymap), index=weeks)

    def areas_by_week(code):
        if code in wide.index.get_level_values(0):
            a = wide.loc[code].reindex(avail, fill_value=0.0)
        else:  # a well with no parcel within 3 km
            a = pd.DataFrame(0.0, index=avail, columns=wide.columns)
        return a.reindex(used.to_numpy()).set_axis(weeks)

    donor = derangement(wells["code_bss"])
    rows = []
    for _, w in wells.iterrows():
        fc = f.loc[w["cell_id"]].reindex(weeks)
        # mm/week of unmet crop requirement, per class
        need = (kc.mul(fc["ETP"], axis=0).sub(fc["rain"], axis=0)).clip(lower=0)
        a_t = areas_by_week(w["code_bss"])
        cols = [c for c in need.columns if c in a_t.columns]
        m3 = need[cols] * a_t[cols] * 10.0

        def part(kind, m=m3):
            return m[[c for c in cols if assumption[c] == kind]].sum(axis=1).to_numpy()

        main = [c for c in cols if assumption[c] in MAIN]
        wide_cls = [c for c in cols if assumption[c] in WIDE]
        placebo = (need[main] * areas_by_week(donor[w["code_bss"]])[main] * 10.0).sum(axis=1).to_numpy()
        rows.append(pd.DataFrame({
            "code_bss": w["code_bss"], "week": weeks,
            "demand_usually_m3": part("usually"), "demand_partly_m3": part("partly"),
            "demand_rainfed_m3": part("rainfed"),
            "demand_main_placebo_m3": placebo, "placebo_donor": donor[w["code_bss"]],
            "main_ha": a_t[main].sum(axis=1).to_numpy(), "wide_ha": a_t[wide_cls].sum(axis=1).to_numpy(),
            "rpg_year_used": used.to_numpy(),
            "zone_partly_foreign": bool(foreign[w["code_bss"]] > 0),
        }))
    d = pd.concat(rows, ignore_index=True)
    d["demand_main_m3"] = d["demand_usually_m3"]
    d["demand_wide_m3"] = d["demand_usually_m3"] + d["demand_partly_m3"]
    d["rpg_backfill"] = d["week"].dt.year < min(avail)
    d["rpg_lag_years"] = d["week"].dt.year - d["rpg_year_used"]
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rebuild", action="store_true", help="recompute the clipped areas")
    args = ap.parse_args()
    classes = load_classes()
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["cell_id", "week", "ETP", "rain"])
    print(f"dataset {DATASET}: {len(wells)} wells; RPG editions {rpg_years()}")
    areas = build_areas(wells, rebuild=args.rebuild)
    cls = code_to_class(areas["CODE_CULTU"].to_numpy(), areas["CODE_GROUP"].to_numpy(), classes)
    unm = areas.loc[(cls == "unmapped").to_numpy()]
    print(f"  unmapped area: {unm['ha'].sum():.1f} ha" +
          (f" (codes {sorted(unm['CODE_CULTU'].dropna().unique())})" if len(unm) else ""))
    foreign = foreign_share(well_buffers(wells))
    print(f"  zones reaching Spain or Andorra: {int((foreign > 0).sum())}")
    d = demand(wells, forcing, areas, classes, foreign)
    out = INTERIM / f"crop_demand_weekly_{DATASET}.parquet"
    d.to_parquet(out, index=False)
    print(f"-> {out.name}: {len(d):,} well-weeks")


if __name__ == "__main__":
    main()
