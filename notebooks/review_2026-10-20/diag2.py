import json
import numpy as np
import pandas as pd
from pathlib import Path
ROOT = Path("/home/mclovin/Projects/Master_2026")
DS = ROOT / "data/processed/dataset_v2"
pw = pd.read_parquet(DS / "pumping_weekly.parquet")
pts = pd.read_parquet(DS / "pumping_points.parquet")
print(pts.columns.tolist()); print(pw.columns.tolist())
lon0, lat0, lon1, lat1 = 2.55, 42.50, 3.06, 42.88
m = 0.04
plain = pts[pts["longitude"].between(lon0 - m, lon1 + m) & pts["latitude"].between(lat0 - m, lat1 + m)]
d = pw.merge(plain[["code_ouvrage", "source"]], on="code_ouvrage")
d["year"] = d["week"].dt.year
t = d.groupby(["year", "source", "usage"])["volume_m3"].sum().div(1e6).unstack(["source", "usage"]).round(1)
imp = d.groupby("year")["imputed"].mean().round(2).rename("share_imputed")
print(pd.concat([t, imp], axis=1).loc[2010:].to_string())

# collinearity: plain-average weekly deficit vs canal/irrigation input, within years
f = pd.read_parquet(DS / "forcing_weekly.parquet")
f["deficit"] = (f["ETP"] - f["rain"]).clip(lower=0)
fd = f.groupby("week")["deficit"].mean()
canal = d[(d["source"] == "surface") & d["usage"].isin(["irrigation", "canals"])].groupby("week")["volume_m3"].sum()
gw_irr = d[(d["source"] == "groundwater") & (d["usage"] == "irrigation")].groupby("week")["volume_m3"].sum()
j = pd.concat([fd.rename("deficit"), canal.rename("canal"), gw_irr.rename("gw_irr")], axis=1).dropna()
j = j[(j.index.year >= 2012) & (j.index.month.isin(range(4, 11)))]
print("\nApr-Oct weekly correlation with plain-mean climatic deficit:")
print(j.corr().round(3).to_string())
# within-year correlation after removing each year's mean
jw = j.groupby(j.index.year).transform(lambda s: s / s.sum())
print("within-year shape correlation (each year normalised):")
print(jw.corr().round(3).to_string())
