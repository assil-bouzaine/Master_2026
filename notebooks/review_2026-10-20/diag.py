"""Diagnostics for the critical review (read-only on results/v2)."""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path("/home/mclovin/Projects/Master_2026")
DS = ROOT / "data/processed/dataset_v2"
RES = ROOT / "results/v2"
heads = pd.read_parquet(DS / "heads_weekly.parquet")
wells = pd.read_parquet(DS / "wells.parquet")
splits = json.loads((DS / "splits.json").read_text())
core = wells.loc[wells["core"], ["code_bss", "group"]]
runs = ["naive_climatology", "pastas_seasonal_canal", "lgbm_sim", "lstm_tuned", "stgnn_distance", "ensemble_sim"]

def nse(o, s): return 1 - ((s - o) ** 2).sum() / ((o - o.mean()) ** 2).sum()

# training stats per well (head) for z
tr = heads[(heads["week"] >= splits["train"][0]) & (heads["week"] <= splits["train"][1])]
st = tr.groupby("code_bss")["head"].agg(mu="mean", sd="std", hmin="min", hmax="max")

periods = {"test_all": ("2022-05-01", "2026-12-31"), "drought_2022-05_2024-12": ("2022-05-01", "2024-12-31"),
           "recovery_2025-2026": ("2025-01-01", "2026-12-31"), "validation": tuple(splits["validation"])}
rows = []
for r in runs:
    p = pd.read_parquet(RES / r / "predictions.parquet")
    p = p[p["task"] == "simulation"]
    d = p.merge(heads[["code_bss", "week", "head"]], on=["code_bss", "week"]).dropna(subset=["pred", "head"])
    d = d.merge(core, on="code_bss")
    for pn, (a, b) in periods.items():
        dd = d[(d["week"] >= a) & (d["week"] <= b)]
        sc = []
        for code, g in dd.groupby("code_bss"):
            if len(g) < 26: continue
            o, s = g["head"].to_numpy(), g["pred"].to_numpy()
            sdw = st.loc[code, "sd"]
            sc.append({"code": code, "NSE": nse(o, s), "RMSE": np.sqrt(((s - o) ** 2).mean()),
                       "bias_sd": (s.mean() - o.mean()) / sdw,           # mean error in training sd units
                       "alpha": s.std() / o.std(), "r": np.corrcoef(o, s)[0, 1],
                       "bias_share": (s.mean() - o.mean()) ** 2 / ((s - o) ** 2).mean()})
        sc = pd.DataFrame(sc)
        rows.append({"run": r, "period": pn, "n": len(sc), **sc.drop(columns="code").median().round(2).to_dict()})
out = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print(out.to_string(index=False))

# ---- out-of-range / saturation check on the ensemble and lstm_tuned
print("\n--- out-of-range check (core wells, test) ---")
te = heads[(heads["week"] >= splits["test"][0])].merge(core, on="code_bss")
te = te.merge(st, left_on="code_bss", right_index=True)
te["below_train_min"] = te["head"] < te["hmin"]
frac = te.groupby("code_bss")["below_train_min"].mean()
print("share of test well-weeks below the well's training minimum: median %.2f, mean %.2f, wells with >10%%: %d/%d"
      % (frac.median(), frac.mean(), (frac > 0.10).sum(), len(frac)))
for r in ["lstm_tuned", "ensemble_sim", "stgnn_distance"]:
    p = pd.read_parquet(RES / r / "predictions.parquet")
    p = p[(p["task"] == "simulation") & (p["week"] >= splits["test"][0])].merge(core, on="code_bss")
    p = p.merge(st, left_on="code_bss", right_index=True)
    pf = (p["pred"] < p["hmin"]).groupby(p["code_bss"]).mean()
    print(f"{r}: share of test predictions below training min: median {pf.median():.2f}, mean {pf.mean():.2f}")
# per-well: NSE vs out-of-range share
m = pd.read_csv(RES / "ensemble_sim/metrics_per_well.csv")
m = m[(m["split"] == "test") & (m["variant"] == "all") & m["core"]].set_index("code_bss")
j = pd.concat([m["NSE"], frac.rename("oor")], axis=1).dropna()
print("Spearman(test NSE ensemble, out-of-range share) = %.2f (n=%d)" % (j.corr(method="spearman").iloc[0, 1], len(j)))

# ---- KGE datum dependence
print("\n--- head means of core wells (m NGF) ---")
mh = heads.merge(core, on="code_bss").groupby("code_bss")["head"].mean()
print(mh.describe().round(2).to_string())
print("core wells with |mean head| < 5 m NGF:", (mh.abs() < 5).sum())
km = m[["KGE", "NSE"]].join(mh.rename("mean_head"))
print(km.sort_values("mean_head").head(8).round(2).to_string())
