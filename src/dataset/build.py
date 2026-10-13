"""Build the model-ready weekly dataset (dataset_v1) that every model reads.

    python -m src.dataset.build

Inputs (all produced by src.ingest.* and src.analysis.*):
    piezometer series, station table, BD LISA station stacks, SAFRAN/SIM2,
    Hub'Eau hydrometry, BNPE abstraction.

Design (CLAUDE.md section 3, docs/roadmap.md Phase 1)
- Weekly step, weeks ending on Sunday (pandas "W-SUN").
- Model window from MODEL_START (BNPE starts in 2012); forcings from
  FORCING_START so that baselines like Pastas have a warm-up period.
- Splits by time: train <= 2019, validation 2020-01 .. 2022-04,
  test 2022-05 .. latest (record drought, then recovery); plus 5
  leave-wells-out folds, stratified by aquifer group.
- Wells: every plain station with >= MIN_WEEKS weekly values in the model
  window (masked loss for gaps); `core` = the 33-station working set, on
  which results are reported.
- Drought concept: monthly SGI (Bloomfield & Marchant 2013,
  doi:10.5194/hess-17-4769-2013), normal scores per calendar month with the
  *training period only* as reference (no leakage), mapped to the 7 BRGM IPS
  classes. The class bounds are the standard-normal quantiles of the
  return periods in the BRGM/DREAL Rhône-Méditerranée bulletin table
  (10/20/40/60/80/90 %).
- Pumping: BNPE annual volumes spread over weeks. Irrigation and canal
  intakes follow the weekly climatic water deficit max(ETP - rain, 0) from
  April to October. Drinking water and industry are uniform. Hydropower is
  dropped (water is returned at once). Years after the last BNPE year are
  filled with the mean of the three last complete years and flagged.
  These are assumptions; the flag lets Phase 2 test their sensitivity.

Outputs (data/processed/dataset_v1/)
    wells.parquet            static well attributes
    heads_weekly.parquet     well x week: head, n_days, share not validated, SGI, class
    forcing_weekly.parquet   SAFRAN cell x week
    rivers_weekly.parquet    gauge x week (m3/s); gauges.parquet
    pumping_weekly.parquet   ouvrage x usage x week (m3); pumping_points.parquet
    splits.json              time splits + leave-wells-out folds
    meta.json                build date, parameters, row counts
"""
import json
from datetime import date
from statistics import NormalDist

import geopandas as gpd
import numpy as np
import pandas as pd

from src.analysis.bdlisa_profile import group_of
from src.analysis.bnpe_profile import load as load_bnpe
from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, INTERIM, PROCESSED, RAW
from src.ingest.hubeau_piezo import CHRON, safe_name

OUT = PROCESSED / "dataset_v1"
WEEK = "W-SUN"
FORCING_START = "2005-01-01"
MODEL_START = "2012-01-01"
TRAIN_END = "2019-12-31"
VAL_END = "2022-04-30"
MIN_WEEKS = 104          # at least two years of weekly values in the model window
SGI_MIN_REF_YEARS = 5    # per calendar month, in the training period
N_FOLDS = 5
SEED = 2026
PLAIN_MARGIN_DEG = 0.04  # ~3 km around the plain box for abstraction points

# BRGM IPS classes: (upper bound of z, label); bounds = Phi^-1(0.1, 0.2, 0.4, 0.6, 0.8, 0.9)
_q = NormalDist().inv_cdf
IPS_CLASSES = [(_q(0.1), "très bas"), (_q(0.2), "bas"), (_q(0.4), "modérément bas"),
               (_q(0.6), "autour de la moyenne"), (_q(0.8), "modérément haut"),
               (_q(0.9), "haut"), (np.inf, "très haut")]

SUM_VARS = ["PRELIQ", "PRENEI", "ETP", "EVAP", "PE", "DRAINC", "RUNC"]
MEAN_VARS = ["T", "SWI"]


# --------------------------------------------------------------------- wells
def build_wells():
    t = pd.read_parquet(INTERIM / "piezo_stations.parquet")
    t = t[t["ok_plain"] & (t["n_obs"] > 0)].copy()  # 5 plain stations have no data at all
    stacks = pd.read_csv(INTERIM / "bdlisa_station_stacks.csv")
    # stacks were computed for the core wells; the group comes from the code for all
    t = t.merge(stacks[["code_bss", "stack_str", "pos_in_stack", "pct_days_artesian"]],
                on="code_bss", how="left")
    t["group"] = t["code_bdlisa"].map(group_of)
    t["core"] = t["working_set"]
    return t


def weekly_heads(code):
    df = pd.read_parquet(CHRON / f"{safe_name(code)}.parquet",
                         columns=["date_mesure", "niveau_nappe_eau", "qualification"])
    df["date_mesure"] = pd.to_datetime(df["date_mesure"])
    df = df[df["date_mesure"] >= FORCING_START].set_index("date_mesure")
    df["not_validated"] = (df["qualification"] == "Non qualifié").astype(float)
    r = df.resample(WEEK)
    w = pd.DataFrame({"head": r["niveau_nappe_eau"].mean(),
                      "n_days": r["niveau_nappe_eau"].count(),
                      "share_not_validated": r["not_validated"].mean()})
    w = w[w["n_days"] > 0]
    w.index.name = "week"
    return w.reset_index().assign(code_bss=code)


def sgi(heads):
    """Monthly SGI per well, reference = training period; returns week-level values."""
    h = heads.set_index("week")["head"]
    monthly = h.resample("MS").mean().dropna()
    ref = monthly[monthly.index <= TRAIN_END]
    z = pd.Series(np.nan, index=monthly.index)
    for m in range(1, 13):
        r = np.sort(ref[ref.index.month == m].values)
        if len(r) < SGI_MIN_REF_YEARS:
            continue
        n = len(r)
        vals = monthly[monthly.index.month == m]
        # Weibull plotting position, clipped half a step beyond the reference range
        p = (np.searchsorted(r, vals.values, side="right")) / (n + 1)
        p = np.clip(p, 0.5 / (n + 1), 1 - 0.5 / (n + 1))
        z[vals.index] = [NormalDist().inv_cdf(x) for x in p]
    month_of_week = heads["week"].dt.to_period("M").dt.to_timestamp()
    return month_of_week.map(z).values


def ips_class(z):
    if np.isnan(z):
        return None
    for bound, label in IPS_CLASSES:
        if z < bound:
            return label
    return IPS_CLASSES[-1][1]


# ------------------------------------------------------------------ forcing
def build_forcing():
    files = sorted((RAW / "safran").glob("sim2_66_[0-9]*.parquet"))
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    d = d[d["date"] >= FORCING_START]
    d["cell_id"] = d["LAMBX"].astype(str) + "_" + d["LAMBY"].astype(str)
    d = d.set_index("date")
    g = d.groupby("cell_id")
    w = pd.concat([g[SUM_VARS].resample(WEEK).sum(min_count=7),
                   g[MEAN_VARS].resample(WEEK).mean()], axis=1)
    w = w.dropna(subset=["PRELIQ"]).reset_index().rename(columns={"date": "week"})
    w["rain"] = w["PRELIQ"] + w["PRENEI"]
    return w


def nearest_cell(points_gdf):
    cells = pd.read_parquet(RAW / "safran" / "grid_cells_66.parquet")
    cg = gpd.GeoDataFrame(cells, geometry=gpd.points_from_xy(cells["lon"], cells["lat"]),
                          crs=CRS_WGS84).to_crs(CRS_L93)
    j = gpd.sjoin_nearest(points_gdf.to_crs(CRS_L93), cg[["cell_id", "geometry"]],
                          distance_col="cell_dist_m")
    return j[~j.index.duplicated()]


# ------------------------------------------------------------------- rivers
def build_rivers():
    gauges = pd.read_parquet(RAW / "hubeau_hydro" / "stations_66.parquet")
    parts = []
    for f in sorted((RAW / "hubeau_hydro" / "qmnj").glob("*.parquet")):
        df = pd.read_parquet(f)
        if df.empty:
            continue
        s = df.set_index("date_obs_elab")["resultat_obs_elab"] / 1000.0  # L/s -> m3/s
        w = s.resample(WEEK).agg(["mean", "count"]).rename(
            columns={"mean": "q_m3s", "count": "n_days"})
        parts.append(w[w["n_days"] > 0].reset_index().rename(
            columns={"date_obs_elab": "week"}).assign(code_station=f.stem))
    rivers = pd.concat(parts, ignore_index=True)
    rivers = rivers[rivers["week"] >= FORCING_START]
    stats = rivers.groupby("code_station").agg(n_weeks=("week", "size"),
                                               first_week=("week", "min"),
                                               last_week=("week", "max"))
    gauges = gauges.merge(stats, left_on="code_station", right_index=True, how="inner")
    return gauges, rivers


# ------------------------------------------------------------------ pumping
def build_pumping(forcing):
    d = load_bnpe()
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    m = PLAIN_MARGIN_DEG
    d = d[d["longitude"].between(lon0 - m, lon1 + m) & d["latitude"].between(lat0 - m, lat1 + m)]
    d = d[~d["usage"].str.startswith("hydropower")]
    pts = (d.groupby("code_ouvrage")
             .agg(nom_ouvrage=("nom_ouvrage", "first"), longitude=("longitude", "first"),
                  latitude=("latitude", "first"), source=("source", "first"))
             .reset_index())
    bnpe_pts = pd.read_parquet(RAW / "hubeau_bnpe" / "points_prelevement_66.parquet")
    pts = pts.merge(bnpe_pts.groupby("code_ouvrage")["code_bss_point_eau"].first(),
                    on="code_ouvrage", how="left")
    gp = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["longitude"], pts["latitude"]),
                          crs=CRS_WGS84)
    pts["cell_id"] = nearest_cell(gp)["cell_id"].values

    annual = d.groupby(["code_ouvrage", "usage", "annee"])["volume"].sum().reset_index()
    last = int(annual["annee"].max())
    end_year = date.today().year
    # mean of the 3 years before the last (the last one is under-reported); a year
    # without a declaration counts as zero, otherwise one-off declarers inflate the fill
    fill = (annual[annual["annee"].between(last - 3, last - 1)]
            .groupby(["code_ouvrage", "usage"])["volume"].sum().div(3).reset_index())
    filled = [fill.assign(annee=y) for y in range(last + 1, end_year + 1)]
    annual["imputed"] = False
    annual = pd.concat([annual] + [f.assign(imputed=True) for f in filled], ignore_index=True)

    # weekly weights per cell and year
    f = forcing[["cell_id", "week", "ETP", "rain"]].copy()
    f["year"] = f["week"].dt.year
    f["deficit"] = (f["ETP"] - f["rain"]).clip(lower=0)
    f.loc[~f["week"].dt.month.between(4, 10), "deficit"] = 0.0
    # Reported years keep their declared annual total: irrigation weights sum to 1
    # over the year. Imputed years (after the last BNPE year, incl. the partial
    # current year) are divided by the mean annual deficit of the reported years,
    # so their irrigation scales with that year's climatic demand, and a partial
    # year is not squeezed into fewer weeks. Flat weights are 7/365.25 per week.
    reported = f["year"] <= last
    annual_def = f.groupby(["cell_id", "year"])["deficit"].transform("sum")
    clim_def = (f[reported & (f["year"] >= int(annual["annee"].min()))]
                .groupby(["cell_id", "year"])["deficit"].sum().groupby("cell_id").mean())
    denom = annual_def.where(reported, f["cell_id"].map(clim_def))
    f["w_irr"] = f["deficit"] / denom
    f["w_flat"] = 7 / 365.25

    a = annual.merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage")
    out = a.merge(f[["cell_id", "year", "week", "w_irr", "w_flat"]],
                  left_on=["cell_id", "annee"], right_on=["cell_id", "year"])
    seasonal = out["usage"].isin(["irrigation", "canals"])
    out["volume_m3"] = out["volume"] * np.where(seasonal, out["w_irr"], out["w_flat"])
    out = out[["code_ouvrage", "usage", "week", "volume_m3", "imputed"]]
    return pts, out, last


# --------------------------------------------------------------------- main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    wells = build_wells()
    heads = pd.concat([weekly_heads(c) for c in wells["code_bss"]], ignore_index=True)
    in_window = heads[heads["week"] >= MODEL_START].groupby("code_bss").size()
    wells["n_weeks_model"] = wells["code_bss"].map(in_window).fillna(0).astype(int)
    wells = wells[wells["n_weeks_model"] >= MIN_WEEKS].reset_index(drop=True)
    heads = heads[heads["code_bss"].isin(wells["code_bss"])]
    heads["sgi"] = np.concatenate([sgi(g) for _, g in heads.groupby("code_bss", sort=False)])
    heads["ips_class"] = heads["sgi"].map(ips_class)

    gw = gpd.GeoDataFrame(wells, geometry=gpd.points_from_xy(wells["x"], wells["y"]),
                          crs=CRS_WGS84)
    nc = nearest_cell(gw)
    wells["cell_id"] = nc["cell_id"].values
    wells["cell_dist_m"] = nc["cell_dist_m"].round(0).values

    forcing = build_forcing()
    gauges, rivers = build_rivers()
    pts, pumping, last_bnpe = build_pumping(forcing)

    # leave-wells-out folds, stratified by aquifer group
    rng = np.random.default_rng(SEED)
    folds = {}
    for _, g in wells.groupby(wells["group"].fillna("unknown")):
        codes = list(g["code_bss"])
        rng.shuffle(codes)
        for i, c in enumerate(codes):
            folds[c] = i % N_FOLDS
    wells["fold"] = wells["code_bss"].map(folds)

    end = heads["week"].max()
    splits = {"week_rule": WEEK, "model_start": MODEL_START, "forcing_start": FORCING_START,
              "train": [MODEL_START, TRAIN_END],
              "validation": ["2020-01-01", VAL_END],
              "test": ["2022-05-01", str(end.date())],
              "leave_wells_out": {"n_folds": N_FOLDS, "seed": SEED,
                                  "stratified_by": "BD LISA group",
                                  "fold_of_well": folds}}

    keep_w = ["code_bss", "bss_id", "libelle_pe", "nom_commune", "x", "y", "altitude_station",
              "profondeur_investigation", "code_bdlisa", "layer", "group", "stack_str",
              "pos_in_stack", "pct_days_artesian", "record_years", "core", "n_weeks_model",
              "cell_id", "cell_dist_m", "fold"]
    wells[keep_w].to_parquet(OUT / "wells.parquet", index=False)
    heads.to_parquet(OUT / "heads_weekly.parquet", index=False)
    forcing.to_parquet(OUT / "forcing_weekly.parquet", index=False)
    gauges.to_parquet(OUT / "gauges.parquet", index=False)
    rivers.to_parquet(OUT / "rivers_weekly.parquet", index=False)
    pts.to_parquet(OUT / "pumping_points.parquet", index=False)
    pumping.to_parquet(OUT / "pumping_weekly.parquet", index=False)
    (OUT / "splits.json").write_text(json.dumps(splits, indent=1))
    meta = {"version": "v1", "built": date.today().isoformat(),
            "rows": {"wells": len(wells), "core_wells": int(wells["core"].sum()),
                     "heads_weekly": len(heads), "forcing_weekly": len(forcing),
                     "gauges": len(gauges), "rivers_weekly": len(rivers),
                     "pumping_points": len(pts), "pumping_weekly": len(pumping)},
            "last_week": str(end.date()), "last_bnpe_year": last_bnpe,
            "ips_bounds": [round(b, 3) for b, _ in IPS_CLASSES[:-1]]}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))

    # ------------------------------------------------------------ report
    print(f"wells: {len(wells)} (core {int(wells['core'].sum())}), by group:")
    print(wells.groupby(["group", "core"], dropna=False).size().unstack(fill_value=0).to_string())
    print(f"\nweekly heads: {len(heads):,} rows, {heads['week'].min().date()} .. {end.date()}")
    hm = heads[heads["week"] >= MODEL_START]
    for name, (a, b) in (("train", (MODEL_START, TRAIN_END)), ("validation", ("2020-01-01", VAL_END)),
                         ("test", ("2022-05-01", str(end.date())))):
        s = hm[hm["week"].between(a, b)]
        core = s[s["code_bss"].isin(wells.loc[wells["core"], "code_bss"])]
        print(f"  {name:<10} {a} .. {b}: {len(s):,} well-weeks ({len(core):,} core), "
              f"not validated {100 * s['share_not_validated'].mean():.1f}%")
    print(f"  SGI defined for {100 * heads['sgi'].notna().mean():.0f}% of well-weeks")
    test = hm[hm["week"] >= "2022-05-01"]
    print("  IPS classes in the test period (% of well-weeks):")
    print((100 * test["ips_class"].value_counts(normalize=True)).round(1)
          .reindex([l for _, l in IPS_CLASSES]).to_string())
    print(f"\nforcing: {forcing['cell_id'].nunique()} cells, {len(forcing):,} cell-weeks; "
          f"wells' nearest cell within {wells['cell_dist_m'].max():.0f} m")
    print(f"rivers: {len(gauges)} gauges with data ({int(gauges['is_canal'].sum())} canals), "
          f"{len(rivers):,} gauge-weeks")
    print(f"pumping: {len(pts)} ouvrages near the plain, last BNPE year {last_bnpe} "
          f"(later years imputed), {len(pumping):,} rows")
    yearly = (pumping.assign(y=pumping["week"].dt.year)
              .merge(pts[["code_ouvrage", "source"]], on="code_ouvrage")
              .groupby(["y", "source"])["volume_m3"].sum().div(1e6).unstack().round(1))
    print(yearly.loc[2012:].to_string())
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
