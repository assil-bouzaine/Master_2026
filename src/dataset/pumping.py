"""Pumping helpers shared by all models.

seasonal_drinking_water: sensitivity variant of dataset_v1's flat drinking-water
profile. The Pastas baselines (docs/notes/step09_baselines.md) showed the flat
profile cannot explain the Pliocene's summer drawdown; 50 % flat + 50 %
following the April-October climatic deficit fits better. Annual totals are
unchanged. canal_series: plain-wide surface irrigation + canal intakes.
"""
import pandas as pd

from src.config import DATASET_DIR

DS = DATASET_DIR
SEASONAL_SHARE = 0.5


def seasonal_drinking_water(pw, pts):
    """Re-spread drinking-water volumes: SEASONAL_SHARE follows the Apr-Oct deficit."""
    f = pd.read_parquet(DS / "forcing_weekly.parquet", columns=["cell_id", "week", "ETP", "rain"])
    f["year"] = f["week"].dt.year
    f["deficit"] = (f["ETP"] - f["rain"]).clip(lower=0)
    f.loc[~f["week"].dt.month.between(4, 10), "deficit"] = 0.0
    tot = f.groupby(["cell_id", "year"])["deficit"].transform("sum")
    f["w"] = f["deficit"] / tot
    d = pw.merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage")
    dw = d["usage"] == "drinking water"
    d["year"] = d["week"].dt.year
    annual = d[dw].groupby(["code_ouvrage", "year"])["volume_m3"].transform("sum")
    d = d.merge(f[["cell_id", "week", "w"]], on=["cell_id", "week"], how="left")
    flat = d.loc[dw, "volume_m3"]
    d.loc[dw, "volume_m3"] = ((1 - SEASONAL_SHARE) * flat
                              + SEASONAL_SHARE * annual * d.loc[dw, "w"].fillna(0))
    return d[pw.columns]


def canal_series(pw=None, pts=None):
    """Weekly plain-wide surface-water irrigation + canal-intake volume (m3)."""
    if pw is None:
        pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    if pts is None:
        pts = pd.read_parquet(DS / "pumping_points.parquet")
    s = pw.merge(pts[["code_ouvrage", "source"]], on="code_ouvrage")
    s = s[(s["source"] == "surface") & s["usage"].isin(["irrigation", "canals"])]
    return s.groupby("week")["volume_m3"].sum()
