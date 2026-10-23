"""Shared feature panel for the machine-learning baselines (one row per well x week).

Every ML model reads the same panel, so differences come from the model, not
from the inputs. Built from dataset_v1 with the *seasonal* drinking-water
profile (the better assumption, see docs/notes/step09_baselines.md).

    from src.models.features import build_panel
    P = build_panel()          # cached in results/_cache/panel.parquet

Columns
    keys        code_bss, week, split, fold, core, group
    target      head (m NGF); z = per-well z-score with *training* mean/sd
    dynamic     weekly forcings + rolling means over ROLL_WEEKS (groundwater
                remembers: 1 month to 2 years), climatic deficit, local
                groundwater pumping (3 km), plain-wide canal volume, season
    static      altitude, investigation depth, x, y, aquifer group code, artesian share
    rivers      (dataset v3 on) log discharge of the Têt in the plain, the Agly, the Tech
                and of the main-stem gauge nearest to the well, plus 13/52-week means
For the forecast task, `lagged_panel(P, h)` shifts every input to the issue
week t-h and adds the observed head anomaly known at t-h. This is a hindcast,
not an operational forecast: the observed heads are causal, but the inputs are
the reconstructed series, and some use information from after t-h (weekly
pumping spreads an annual total with weights normalised over the whole year,
river gaps are interpolated between both ends, imputed years use later means).
See docs/analysis_plan.md (information availability).

Regime R3 (less data), from dataset v4: `build_panel(train_start=...)` computes
the per-well statistics (mu, sd, the climatology, the artesian share) from
[train_start, end of training] only, so a run trained on the last 25 % of the
period does not inherit them from the earlier years. v1-v3 runs only masked
the loss (kept as they were, for reproducibility).
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, DATASET, R3_STARTS
from src.dataset.load import FORCING_VARS, _pumping_near_wells
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models.evaluate import DS, RESULTS

ROLL_WEEKS = (4, 13, 26, 52, 104)
ROLL_VARS = ("rain", "ETP", "PE", "DRAINC", "deficit")
GROUP_CODE = {"recent alluvium": 0, "ancient alluvium": 1, "Pliocene multilayer": 2,
              "Corbières karst": 3, "other": 4}
STATIC = ["altitude_station", "profondeur_investigation", "x", "y", "group_code",
          "pct_days_artesian"]
CACHE = RESULTS / "_cache" / "panel.parquet"
# River inputs from dataset v3 (v1/v2 panels stay as they were). Main-stem gauges with a
# full 2005-2026 record (dataset gauges.parquet): the Têt in the plain at Perpignan
# Pont-Joffre, the Agly at Estagel, the Tech at Argelès Pont d'Elne; plus Têt at Rodès and
# Tech at Le Boulou as candidates for the nearest gauge.
WITH_RIVERS = DATASET >= "v3"
R3_WINDOW_STATS = DATASET >= "v4"
RIVERS = {"river_tet": "Y047403001", "river_agly": "Y066404001", "river_tech": "Y028406001"}
NEAR_CANDIDATES = ["Y047403001", "Y046403001", "Y066404001", "Y027401001", "Y028406001"]


def _split_labels(weeks, splits):
    lab = pd.Series("warmup", index=weeks)
    for name in ("train", "validation", "test"):
        a, b = splits[name]
        lab[(weeks >= a) & (weeks <= b)] = name
    return lab


def river_series(weeks, train_end):
    """log(1 + weekly mean discharge) per candidate gauge; gaps <= 8 weeks interpolated,
    longer ones filled with the gauge's training-period median for that week of year."""
    r = pd.read_parquet(DS / "rivers_weekly.parquet")
    out = {}
    for code in set(NEAR_CANDIDATES) | set(RIVERS.values()):
        s = np.log1p(r[r["code_station"] == code].set_index("week")["q_m3s"]).reindex(weeks)
        s = s.interpolate(limit=8, limit_area="inside")
        woy = pd.Series(weeks.isocalendar().week.clip(upper=52).to_numpy(), index=weeks)
        clim = s[weeks <= train_end].groupby(woy[weeks <= train_end]).median()
        out[code] = s.fillna(woy.map(clim))
    return pd.DataFrame(out, index=weeks)


def nearest_gauge(wells):
    g = pd.read_parquet(DS / "gauges.parquet").set_index("code_station").loc[NEAR_CANDIDATES]
    gx = gpd.GeoSeries(gpd.points_from_xy(g["longitude_station"], g["latitude_station"]),
                       crs=CRS_WGS84).to_crs(CRS_L93)
    wx = gpd.GeoSeries(gpd.points_from_xy(wells["x"], wells["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    d = np.hypot(wx.x.to_numpy()[:, None] - gx.x.to_numpy()[None],
                 wx.y.to_numpy()[:, None] - gx.y.to_numpy()[None])
    return dict(zip(wells["code_bss"], np.array(NEAR_CANDIDATES)[d.argmin(axis=1)]))


def build_panel(refresh=False, train_start=None):
    """The panel; with train_start (regime R3, dataset v4 on) the per-well statistics come
    from [train_start, end of training] only. Ignored before v4."""
    if not R3_WINDOW_STATS:
        train_start = None
    window = None
    if train_start:
        window = {v: k for k, v in R3_STARTS.items()}.get(train_start)
        if window is None:
            raise ValueError(f"train_start {train_start} is not an R3 window {R3_STARTS}")
    cache = CACHE.with_name(f"panel_{window}.parquet") if window else CACHE
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    splits = json.loads((DS / "splits.json").read_text())
    wells = pd.read_parquet(DS / "wells.parquet")
    if window:  # the artesian share of the window (src.dataset.build, v4)
        wells["pct_days_artesian"] = wells[f"pct_days_artesian_{window}"]
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    forcing = pd.read_parquet(DS / "forcing_weekly.parquet")
    pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    pts = pd.read_parquet(DS / "pumping_points.parquet")
    weeks = pd.date_range(forcing["week"].min(), heads["week"].max(), freq=splits["week_rule"])

    # forcings per cell, with rolling means
    f = forcing.set_index(["cell_id", "week"])[FORCING_VARS].copy()
    f["deficit"] = f["ETP"] - f["rain"]
    cells = {}
    for cell, g in f.groupby(level=0):
        g = g.droplevel(0).reindex(weeks)
        for v in ROLL_VARS:
            for w in ROLL_WEEKS:
                g[f"{v}_m{w}"] = g[v].rolling(w, min_periods=max(1, w // 2)).mean()
        cells[cell] = g

    # pumping: local groundwater (3 km, seasonal drinking water) + plain-wide canals
    near = _pumping_near_wells(wells, seasonal_drinking_water(pw, pts)).fillna(0.0)
    gcols = [c for c in near.columns if c.startswith("pump_gr_")]
    canal = canal_series(pw, pts).reindex(weeks).fillna(0.0) / 1e6  # Mm3/week

    if WITH_RIVERS:
        riv = river_series(weeks, splits["train"][1])
        near_of = nearest_gauge(wells)
    parts = []
    for _, w in wells.iterrows():
        g = cells[w["cell_id"]].copy()
        if WITH_RIVERS:
            for name, code in RIVERS.items():
                g[name] = riv[code]
            g["river_near"] = riv[near_of[w["code_bss"]]]
            for k in (13, 52):
                g[f"river_near_m{k}"] = g["river_near"].rolling(k, min_periods=1).mean()
        if w["code_bss"] in near.index.get_level_values(0):
            gw = near.loc[w["code_bss"]][gcols].sum(axis=1).reindex(weeks).fillna(0.0) / 1e3
        else:
            gw = pd.Series(0.0, index=weeks)
        g["pump_gw"] = gw                                       # thousand m3/week
        g["canal"] = canal
        for v in ("pump_gw", "canal"):
            for k in (4, 13, 52):
                g[f"{v}_m{k}"] = g[v].rolling(k, min_periods=1).mean()
        g["code_bss"] = w["code_bss"]
        parts.append(g)
    P = pd.concat(parts).rename_axis("week").reset_index()

    doy = P["week"].dt.dayofyear / 365.25 * 2 * np.pi
    P["season_sin"], P["season_cos"] = np.sin(doy), np.cos(doy)
    w = wells.copy()
    w["group_code"] = w["group"].map(GROUP_CODE).fillna(4)
    for c in STATIC:  # some come from the API as text (e.g. altitude_station)
        w[c] = pd.to_numeric(w[c], errors="coerce")
    P = P.merge(w[["code_bss", "core", "group", "fold"] + [c for c in STATIC if c != "group_code"]
                  + ["group_code"]], on="code_bss")
    P = P.merge(heads[["code_bss", "week", "head", "share_not_validated"]],
                on=["code_bss", "week"], how="left")
    P["split"] = _split_labels(pd.DatetimeIndex(P["week"]), splits).values

    def stats_rows(P):  # the weeks the per-well statistics may use
        rows = P["split"] == "train"
        return rows & (P["week"] >= pd.Timestamp(train_start)) if window else rows

    tr = P[stats_rows(P)].groupby("code_bss")["head"].agg(["mean", "std"])
    P = P.merge(tr.rename(columns={"mean": "mu", "std": "sd"}), on="code_bss", how="left")
    P["z"] = (P["head"] - P["mu"]) / P["sd"]
    # keep the warm-up weeks (2005-2011): sequence models need them as input;
    # they are labelled "warmup", never trained on and never scored
    P = P.reset_index(drop=True)
    # training climatology of z per well and week of year (smoothed over 5 weeks);
    # calendar information, so it may be used at any time without leakage
    P["woy"] = P["week"].dt.isocalendar().week.clip(upper=52).astype(int)
    c = (P[stats_rows(P)].groupby(["code_bss", "woy"])["z"].mean().unstack()
         .reindex(columns=range(1, 53)))
    c = c.T.interpolate(limit_direction="both").T
    c = pd.concat([c.iloc[:, -2:], c, c.iloc[:, :2]], axis=1).T.rolling(5, center=True).mean().T
    c = c.iloc[:, 2:-2].set_axis(range(1, 53), axis=1)
    clim = c.rename_axis(index="code_bss", columns="woy").stack().rename("clim_z").reset_index()
    P = P.merge(clim, on=["code_bss", "woy"], how="left").drop(columns="woy")
    P["anom"] = P["z"] - P["clim_z"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    P.to_parquet(cache, index=False)
    return P


def input_columns(P):
    skip = {"code_bss", "week", "core", "group", "fold", "head", "share_not_validated",
            "split", "mu", "sd", "z", "anom"}
    return [c for c in P.columns if c not in skip]


def lagged_panel(P, h):
    """Forecast setup: inputs taken at issue week t-h, target at week t."""
    cols = [c for c in input_columns(P) if c not in STATIC and not c.startswith("season_")
            and c != "clim_z"]
    out = []
    for code, g in P.groupby("code_bss", sort=False):
        g = g.sort_values("week").copy()
        lag = g[cols].shift(h)
        lag.columns = [f"{c}_issue" for c in cols]
        za = g["z"].ffill(limit=26)  # last observed level known at each week
        aa = g["anom"].ffill(limit=26)
        feats = pd.DataFrame({"z_issue": za.shift(h), "z_issue_m4": za.rolling(4, min_periods=1)
                              .mean().shift(h), "z_issue_d4": (za - za.shift(4)).shift(h),
                              "anom_issue": aa.shift(h),
                              "anom_issue_m4": aa.rolling(4, min_periods=1).mean().shift(h)})
        out.append(pd.concat([g[["code_bss", "week", "split", "fold", "core", "group", "head",
                                 "share_not_validated", "mu", "sd", "z", "anom", "clim_z",
                                 "season_sin", "season_cos"] + [c for c in STATIC]], lag, feats],
                             axis=1))
    return pd.concat(out, ignore_index=True)
