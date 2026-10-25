"""Pumping reconstruction (3): irrigation spread by a fixed crop calendar (analysis plan §8).

    PFE_DATASET=v4 python -m src.dataset.pumping_cropcal

Reconstruction (1), the dataset's weekly table, spreads each facility's annual irrigation
volume with the April-October climatic deficit of that year, so within a year pumping and
weather move together (r = 0.92-0.97, docs/feedback.md §3.1). Reconstruction (3) keeps
every annual volume and changes only the weekly weights of irrigation: they follow the
potential crop demand of the SAFRAN cell's dated crop mix under the cell's *mean* weekly
climate of the training years (to 2019), so they do not depend on the year's weather.
Other uses keep the weights of (1); canals too, as the plan names irrigation only.

Steps
  1. annual volume of each facility x use x year = weekly volume / weight of (1)
     (src.dataset.build.spread_weights), the same for every week with a positive weight
     (checked); this also recovers the current, unfinished year
  2. crop mix by cell and RPG edition: parcels of the département clips assigned whole to
     their nearest SAFRAN cell (parcels are about 1 ha, cells 64 km2)
  3. profile(cell, week) = sum over the classes assumed usually or partly irrigated of
     area x max(0, Kc(class, week) x ETP_clim - rain_clim), the climate being the cell's
     mean for that week of the year; weights = profile / its sum over all the weeks of the
     calendar year, so an unfinished year keeps the share of the weeks it has. A cell
     without irrigable crops takes the département-wide mix (`cropcal_fallback`).

Output: data/interim/pumping_weekly_cropcal_<dataset>.parquet with the columns of
pumping_weekly.parquet; pass it as `pw` to src.dataset.load._pumping_near_wells.
"""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, DATASET, DATASET_DIR, INTERIM
from src.dataset.build import nearest_cell, spread_weights
from src.dataset.crop_demand import IRRIGABLE, code_to_class, kc_weekly, load_classes, rpg_years, year_map

SEASONAL = ("irrigation", "canals")  # the uses spread by w_irr in reconstruction (1)
RESPREAD = ("irrigation",)           # the uses re-spread here (analysis plan §8)
CLIM_END = 2019                      # last training year (analysis plan §2)
OUT = INTERIM / f"pumping_weekly_cropcal_{DATASET}.parquet"


def week_of_year(weeks):
    """0..51: the 7-day block of the year a week label falls in (53rd folded into the 52nd)."""
    return np.minimum((pd.DatetimeIndex(weeks).dayofyear.to_numpy() - 1) // 7, 51)


def annual_volumes(pw, pts, forcing):
    """Annual volume of each facility x use x year, from the weekly table and the weights
    of reconstruction (1); returns it and the largest relative spread within a year."""
    w1 = spread_weights(forcing)
    j = pw.merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage").merge(w1, on=["cell_id", "week"])
    w = np.where(j["usage"].isin(SEASONAL), j["w_irr"], j["w_flat"])
    j = j.assign(annual=np.where(w > 0, j["volume_m3"] / np.where(w > 0, w, 1), np.nan))
    g = j.dropna(subset=["annual"]).groupby(["code_ouvrage", "usage", "year"])["annual"]
    a = g.median()
    spread = ((g.max() - g.min()) / a.where(a > 0)).max()
    return a.rename("annual_m3").reset_index(), float(0 if np.isnan(spread) else spread)


def crop_mix_by_cell(classes):
    """Hectares of each class by SAFRAN cell and RPG edition (département clips)."""
    rows = []
    for y in rpg_years():
        g = gpd.read_parquet(INTERIM / f"rpg_dept_{y}.parquet").set_crs(CRS_L93, allow_override=True)
        g["crop_class"] = code_to_class(g["CODE_CULTU"].to_numpy(), g["CODE_GROUP"].to_numpy(), classes).to_numpy()
        pts = gpd.GeoDataFrame({"crop_class": g["crop_class"].to_numpy(), "ha": g.area.to_numpy() / 1e4},
                               geometry=g.representative_point().to_numpy(), crs=CRS_L93)
        j = nearest_cell(pts)
        rows.append(j.groupby(["cell_id", "crop_class"])["ha"].sum().rename(y))
    return pd.concat(rows, axis=1).fillna(0.0)  # index (cell, class), columns = editions


def climatology(forcing):
    """Mean weekly ETP and rain by cell and week of year over the training years."""
    f = forcing[forcing["week"].dt.year <= CLIM_END].copy()
    f["woy"] = week_of_year(f["week"])
    return f.groupby(["cell_id", "woy"])[["ETP", "rain"]].mean()


def cropcal_weights(cells, years, mix, clim, classes):
    """Weights by cell x week for every week (W-SUN) of the given calendar years."""
    irrigable = [c for c in classes.index if classes.loc[c, "irrigation_assumption"] in IRRIGABLE]
    weeks = pd.date_range(f"{min(years)}-01-01", f"{max(years)}-12-31", freq="W-SUN")
    kc = kc_weekly(weeks, classes)[irrigable]
    woy = week_of_year(weeks)
    ed = pd.Series(weeks.year).map(year_map(sorted(set(weeks.year)), list(mix.columns))).to_numpy()
    dept = mix.groupby(level="crop_class").sum()
    out = []
    for cell in cells:
        c = clim.loc[cell].reindex(range(52))
        need = (kc.to_numpy() * c["ETP"].to_numpy()[woy, None] - c["rain"].to_numpy()[woy, None]).clip(min=0)
        area = mix.loc[cell] if cell in mix.index.get_level_values(0) else dept.iloc[:0]
        area = area.reindex(index=irrigable, columns=mix.columns).fillna(0.0)
        fallback = area.sum(axis=0) == 0  # per edition
        for e in fallback[fallback].index:
            area[e] = dept[e].reindex(irrigable).fillna(0.0)
        a_t = area[ed].to_numpy().T  # week x class
        prof = (need * a_t).sum(axis=1)
        d = pd.DataFrame({"cell_id": cell, "week": weeks, "year": weeks.year, "profile": prof,
                          "cropcal_fallback": fallback.reindex(ed).to_numpy()})
        d["w_crop"] = d["profile"] / d.groupby("year")["profile"].transform("sum")
        out.append(d)
    return pd.concat(out, ignore_index=True)


def build(pw, pts, forcing, classes):
    annual, spread = annual_volumes(pw, pts, forcing)
    print(f"  annual volumes recovered: {len(annual):,} facility x use x years; "
          f"largest relative spread within a year {spread:.1e}")
    mix = crop_mix_by_cell(classes)
    clim = climatology(forcing)
    years = sorted(pw["week"].dt.year.unique())
    w3 = cropcal_weights(sorted(pts["cell_id"].unique()), years, mix, clim, classes)
    print(f"  cells on the département-wide mix (no irrigable crop): "
          f"{w3.loc[w3['cropcal_fallback'], 'cell_id'].nunique()} of {w3['cell_id'].nunique()}")
    out = pw.copy()
    re = out["usage"].isin(RESPREAD)
    r = (out.loc[re].merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage", how="left")
         .assign(year=lambda t: t["week"].dt.year)
         .merge(annual, on=["code_ouvrage", "usage", "year"], how="left")
         .merge(w3[["cell_id", "week", "w_crop"]], on=["cell_id", "week"], how="left"))
    if r[["annual_m3", "w_crop"]].isna().any().any():
        raise RuntimeError("irrigation rows without an annual volume or a crop-calendar weight")
    out.loc[re, "volume_m3"] = (r["annual_m3"] * r["w_crop"]).to_numpy()
    return out, w3


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args()
    classes = load_classes()
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["cell_id", "week", "ETP", "rain"])
    print(f"dataset {DATASET}: {pw['code_ouvrage'].nunique():,} facilities; RPG editions {rpg_years()}")
    out, _ = build(pw, pts, forcing, classes)
    out.to_parquet(OUT, index=False)
    irr = out["usage"] == "irrigation"
    print(f"-> {OUT.name}: {len(out):,} rows; irrigation total {out.loc[irr, 'volume_m3'].sum() / 1e6:,.1f} "
          f"Mm3 (reconstruction 1: {pw.loc[irr, 'volume_m3'].sum() / 1e6:,.1f})")


if __name__ == "__main__":
    main()
