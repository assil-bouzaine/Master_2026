"""One-off check (scratchpad): BNPE 2024 volumes vs 2020-2023, plain, by source x usage."""
import sys
from pathlib import Path
import pandas as pd
import requests
sys.path.insert(0, "/home/mclovin/Projects/Master_2026")
from src.analysis.bnpe_profile import SOURCE, USAGE

SP = Path("/tmp/claude-1000/-home-mclovin-Projects-Master-2026/5c1502e3-ccf7-4ed4-a349-57f50e9eeb3f/scratchpad")
f = SP / "bnpe_2024.parquet"
if not f.exists():
    r = requests.get("https://hubeau.eaufrance.fr/api/v1/prelevements/chroniques",
                     params={"code_departement": "66", "annee": 2024, "size": 2000}, timeout=120)
    js = r.json()
    print("HTTP", r.status_code, "count", js["count"], "rows", len(js["data"]), "next", js.get("next"))
    pd.DataFrame(js["data"]).to_parquet(f, index=False)
new = pd.read_parquet(f)
old = pd.read_parquet("/home/mclovin/Projects/Master_2026/data/raw/hubeau_bnpe/chroniques_66.parquet")
pts = pd.read_parquet("/home/mclovin/Projects/Master_2026/data/raw/hubeau_bnpe/points_prelevement_66.parquet")
d = pd.concat([old[old["annee"] >= 2019], new[old.columns.intersection(new.columns)]], ignore_index=True)
d = d.merge(pts[["code_ouvrage", "code_type_milieu"]].drop_duplicates(), on="code_ouvrage", how="left")
d["source"] = d["code_type_milieu"].map(SOURCE)
d["usage"] = d["code_usage"].map(USAGE).fillna(d["code_usage"])
lon0, lat0, lon1, lat1, m = 2.55, 42.50, 3.06, 42.88, 0.04
d = d[d["longitude"].between(lon0 - m, lon1 + m) & d["latitude"].between(lat0 - m, lat1 + m)]
d = d[~d["usage"].astype(str).str.startswith("hydropower")]
t = d.groupby(["annee", "source", "usage"])["volume"].sum().div(1e6).round(1).unstack(["source", "usage"])
print(t.to_string())
n = d.groupby("annee")["code_ouvrage"].nunique().rename("n_ouvrages")
print(n.to_string())
# drinking-water groundwater: ouvrages present in both 2022 and 2024
gw = d[(d["source"] == "groundwater") & (d["usage"] == "drinking water")]
p = gw.pivot_table(index="code_ouvrage", columns="annee", values="volume", aggfunc="sum")
both = p.dropna(subset=[2022, 2023, 2024])
print(f"\ngroundwater drinking water, ouvrages declared in 2022, 2023 and 2024: {len(both)}")
print((both[[2021, 2022, 2023, 2024]].sum() / 1e6).round(2).to_string())
