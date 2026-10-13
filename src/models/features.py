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
    static      altitude, screen depth, x, y, aquifer group code, artesian share
For the forecast task, `lagged_panel(P, h)` shifts every input to the issue
week t-h and adds the observed head anomaly known at t-h (operational setup:
nothing after t-h is used except the calendar).
"""
import json

import numpy as np
import pandas as pd

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


def _split_labels(weeks, splits):
    lab = pd.Series("warmup", index=weeks)
    for name in ("train", "validation", "test"):
        a, b = splits[name]
        lab[(weeks >= a) & (weeks <= b)] = name
    return lab


def build_panel(refresh=False):
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    splits = json.loads((DS / "splits.json").read_text())
    wells = pd.read_parquet(DS / "wells.parquet")
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

    parts = []
    for _, w in wells.iterrows():
        g = cells[w["cell_id"]].copy()
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

    tr = P[P["split"] == "train"].groupby("code_bss")["head"].agg(["mean", "std"])
    P = P.merge(tr.rename(columns={"mean": "mu", "std": "sd"}), on="code_bss", how="left")
    P["z"] = (P["head"] - P["mu"]) / P["sd"]
    # keep the warm-up weeks (2005-2011): sequence models need them as input;
    # they are labelled "warmup", never trained on and never scored
    P = P.reset_index(drop=True)
    # training climatology of z per well and week of year (smoothed over 5 weeks);
    # calendar information, so it may be used at any time without leakage
    P["woy"] = P["week"].dt.isocalendar().week.clip(upper=52).astype(int)
    c = (P[P["split"] == "train"].groupby(["code_bss", "woy"])["z"].mean().unstack()
         .reindex(columns=range(1, 53)))
    c = c.T.interpolate(limit_direction="both").T
    c = pd.concat([c.iloc[:, -2:], c, c.iloc[:, :2]], axis=1).T.rolling(5, center=True).mean().T
    c = c.iloc[:, 2:-2].set_axis(range(1, 53), axis=1)
    clim = c.rename_axis(index="code_bss", columns="woy").stack().rename("clim_z").reset_index()
    P = P.merge(clim, on=["code_bss", "woy"], how="left").drop(columns="woy")
    P["anom"] = P["z"] - P["clim_z"]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    P.to_parquet(CACHE, index=False)
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
