"""Single loader for the model-ready dataset (version in src.config.DATASET): aligned weekly arrays for every model.

    from src.dataset.load import load_arrays
    d = load_arrays()            # all wells
    d["Y"].shape                 # (T weeks, N wells) head in m NGF, NaN where missing
    d["M"]                       # (T, N) bool, True where a head was observed
    d["X"]                       # (T, N, F) dynamic inputs, names in d["x_names"]
    d["S"]                       # (N, K) static inputs, names in d["s_names"]
    d["split"]                   # (T,) "warmup" | "train" | "validation" | "test"

    python -m src.dataset.load   # prints shapes and draws reports/figures/dataset_v1_series.png

Dynamic inputs per well: weekly forcings of the nearest SAFRAN cell, plus
groundwater and surface-water abstraction within PUMP_RADIUS_KM, split by
use. The graph models will replace the radius features with explicit
abstraction nodes (Phase 3/4); the radius version is for the baselines.
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, FIGURES

DS = DATASET_DIR
FORCING_VARS = ["rain", "ETP", "EVAP", "PE", "DRAINC", "RUNC", "T", "SWI"]
PUMP_RADIUS_KM = 3.0
PUMP_USES = ["drinking water", "irrigation", "canals", "industry"]
STATIC_VARS = ["altitude_station", "profondeur_investigation", "x", "y"]


def _pumping_near_wells(wells, pw=None):
    """Weekly abstraction within PUMP_RADIUS_KM of each well, by source x use.

    `pw` overrides the dataset's pumping_weekly table (used by sensitivity runs)."""
    pts = pd.read_parquet(DS / "pumping_points.parquet")
    if pw is None:
        pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    gw = gpd.GeoDataFrame(wells[["code_bss"]], geometry=gpd.points_from_xy(wells["x"], wells["y"]),
                          crs=CRS_WGS84).to_crs(CRS_L93)
    gp = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts["longitude"], pts["latitude"]),
                          crs=CRS_WGS84).to_crs(CRS_L93)
    buf = gw.copy()
    buf["geometry"] = buf.buffer(PUMP_RADIUS_KM * 1000)
    near = gpd.sjoin(buf, gp[["code_ouvrage", "source", "geometry"]], predicate="contains")
    j = near[["code_bss", "code_ouvrage", "source"]].merge(pw, on="code_ouvrage")
    j["feature"] = "pump_" + j["source"].str[:2] + "_" + j["usage"].str.replace(" ", "_")
    return j.groupby(["code_bss", "week", "feature"])["volume_m3"].sum().unstack("feature")


def load_arrays(core_only=False):
    wells = pd.read_parquet(DS / "wells.parquet")
    if core_only:
        wells = wells[wells["core"]].reset_index(drop=True)
    splits = json.loads((DS / "splits.json").read_text())
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    forcing = pd.read_parquet(DS / "forcing_weekly.parquet")

    weeks = pd.date_range(forcing["week"].min(), heads["week"].max(), freq=splits["week_rule"])
    codes = list(wells["code_bss"])
    T, N = len(weeks), len(codes)

    hp = heads.pivot(index="week", columns="code_bss", values="head").reindex(index=weeks,
                                                                             columns=codes)
    Y = hp.to_numpy(dtype=float)
    sgi = heads.pivot(index="week", columns="code_bss", values="sgi").reindex(
        index=weeks, columns=codes).to_numpy(dtype=float)

    fx = forcing.set_index(["cell_id", "week"])[FORCING_VARS]
    X_f = np.stack([fx.loc[c].reindex(weeks).to_numpy(dtype=float)
                    for c in wells["cell_id"]], axis=1)              # (T, N, Ff)

    pump = _pumping_near_wells(wells)
    pump_names = sorted(pump.columns)
    X_p = np.zeros((T, N, len(pump_names)))
    for i, c in enumerate(codes):
        if c in pump.index.get_level_values(0):
            X_p[:, i, :] = pump.loc[c].reindex(index=weeks, columns=pump_names).fillna(0).to_numpy()
    X = np.concatenate([X_f, X_p], axis=2)

    split = np.full(T, "warmup", dtype=object)
    for name in ("train", "validation", "test"):
        a, b = splits[name]
        split[(weeks >= a) & (weeks <= b)] = name

    S = wells[STATIC_VARS].to_numpy(dtype=float)
    return {"weeks": weeks, "wells": wells, "Y": Y, "M": ~np.isnan(Y), "SGI": sgi,
            "X": X, "x_names": FORCING_VARS + pump_names, "S": S, "s_names": STATIC_VARS,
            "split": split, "fold": wells["fold"].to_numpy()}


def plot_series(d, path):
    """Top panel: weekly rain (mean over the wells' cells); then one core well per group."""
    import matplotlib.pyplot as plt

    wells = d["wells"]
    picks = [g.sort_values("n_weeks_model").index[-1]
             for _, g in wells[wells["core"]].groupby("group")]
    xi = {n: k for k, n in enumerate(d["x_names"])}
    fig, axes = plt.subplots(len(picks) + 1, 1, figsize=(10, 1.9 * (len(picks) + 1)),
                             sharex=True, facecolor="#fcfcfb",
                             gridspec_kw={"height_ratios": [0.7] + [1] * len(picks)})
    rain = np.nanmean(d["X"][:, :, xi["rain"]], axis=1)
    axes[0].bar(d["weeks"], rain, width=6, color="#2a78d6", linewidth=0)
    axes[0].set_ylabel("rain (mm/week)", fontsize=8, color="#52514e")
    axes[0].set_title("Weekly rain, mean over the wells' SAFRAN cells", fontsize=9, loc="left")
    for ax, i in zip(axes[1:], picks):
        w = wells.loc[i]
        ax.plot(d["weeks"], d["Y"][:, i], color="#2a78d6", linewidth=1.2)
        ax.set_ylabel("head (m NGF)", fontsize=8, color="#52514e")
        ax.set_title(f"{w['libelle_pe']} ({w['code_bdlisa']}, {w['group']}, "
                     f"{w['profondeur_investigation']:.0f} m deep)", fontsize=9, loc="left")
    for ax in axes:
        ax.set_facecolor("#fcfcfb")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for name, color in (("validation", "#eda100"), ("test", "#e34948")):
            on = d["weeks"][d["split"] == name]
            ax.axvspan(on.min(), on.max(), color=color, alpha=0.10, linewidth=0)
    axes[0].text(0.99, 1.05, "shaded: validation (yellow) and test (red) periods",
                 transform=axes[0].transAxes, ha="right", fontsize=7, color="#52514e")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    d = load_arrays()
    print("Y", d["Y"].shape, "X", d["X"].shape, "S", d["S"].shape)
    print("dynamic inputs:", d["x_names"])
    for name in ("warmup", "train", "validation", "test"):
        sel = d["split"] == name
        print(f"  {name:<10} {sel.sum():4d} weeks, observed well-weeks {int(d['M'][sel].sum()):,}")
    assert not np.isnan(d["X"][d["split"] != "warmup"][..., :len(FORCING_VARS)]).any(), \
        "missing forcing inside the model window"
    out = FIGURES / f"dataset_{DATASET}_series.png"
    plot_series(d, out)
    print("figure ->", out)


if __name__ == "__main__":
    main()
