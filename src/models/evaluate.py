"""Shared evaluation: every model writes predictions in one format, scored here.

Prediction format (results/<run_id>/predictions.parquet), one row per
well x week x task:
    code_bss, week, pred, task, horizon
    task    = "simulation" (inputs: weather + pumping only, no observed heads)
              or "forecast" (observed heads known up to week - horizon)
    horizon = 0 for simulation, h weeks for forecasts

    python -m src.models.evaluate <run_id> [<run_id> ...]   # (re)score runs
    python -m src.models.evaluate --compare                  # table of all runs

Metrics, per well and split (train / validation / test):
    NSE  Nash & Sutcliffe 1970, doi:10.1016/0022-1694(70)90255-6
    KGE  Gupta et al. 2009, doi:10.1016/j.jhydrol.2009.08.003
    RMSE (m), bias (m)
Test scores are given on all weeks and on validated weeks only ("Non
qualifié" weeks removed), as decided in CLAUDE.md section 3.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROCESSED, ROOT

DS = PROCESSED / "dataset_v1"
RESULTS = ROOT / "results"
MIN_WEEKS = 26  # a well needs half a year of weeks in a split to be scored


def nse(obs, sim):
    return 1 - np.sum((sim - obs) ** 2) / np.sum((obs - obs.mean()) ** 2)


def kge(obs, sim):
    r = np.corrcoef(obs, sim)[0, 1]
    alpha = sim.std() / obs.std()
    beta = sim.mean() / obs.mean()
    return 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)


def split_of(weeks, splits):
    out = pd.Series("warmup", index=weeks.index, dtype=object)
    for name in ("train", "validation", "test"):
        a, b = splits[name]
        out[(weeks >= a) & (weeks <= b)] = name
    return out


def score(pred):
    """Per well x task x horizon x split metrics."""
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    wells = pd.read_parquet(DS / "wells.parquet")
    splits = json.loads((DS / "splits.json").read_text())
    d = pred.merge(heads[["code_bss", "week", "head", "share_not_validated"]],
                   on=["code_bss", "week"], how="inner").dropna(subset=["pred", "head"])
    d["split"] = split_of(d["week"], splits)
    d = d[d["split"] != "warmup"]
    variants = [("all", d)]
    variants.append(("validated", d[(d["split"] == "test") & (d["share_not_validated"] < 0.5)]))
    rows = []
    for variant, dd in variants:
        for (code, task, h, split), g in dd.groupby(["code_bss", "task", "horizon", "split"]):
            if len(g) < MIN_WEEKS:
                continue
            o, s = g["head"].to_numpy(), g["pred"].to_numpy()
            rows.append({"code_bss": code, "task": task, "horizon": h, "split": split,
                         "variant": variant, "n_weeks": len(g), "NSE": nse(o, s),
                         "KGE": kge(o, s), "RMSE": float(np.sqrt(np.mean((s - o) ** 2))),
                         "bias": float(np.mean(s - o))})
    m = pd.DataFrame(rows)
    return m.merge(wells[["code_bss", "group", "core", "libelle_pe"]], on="code_bss", how="left")


def summarise(m):
    """Median over core wells, per task x horizon x split x variant (and per group)."""
    core = m[m["core"]]
    overall = (core.groupby(["task", "horizon", "split", "variant"])
               .agg(n_wells=("code_bss", "nunique"), NSE=("NSE", "median"),
                    KGE=("KGE", "median"), RMSE=("RMSE", "median"))
               .reset_index().assign(group="all core"))
    by_group = (core.groupby(["task", "horizon", "split", "variant", "group"])
                .agg(n_wells=("code_bss", "nunique"), NSE=("NSE", "median"),
                     KGE=("KGE", "median"), RMSE=("RMSE", "median")).reset_index())
    return pd.concat([overall, by_group], ignore_index=True)


def evaluate_run(run_id):
    run = RESULTS / run_id
    pred = pd.read_parquet(run / "predictions.parquet")
    m = score(pred)
    m.to_csv(run / "metrics_per_well.csv", index=False)
    s = summarise(m)
    s.to_csv(run / "metrics_summary.csv", index=False)
    return s


def compare():
    rows = []
    for f in sorted(RESULTS.glob("*/metrics_summary.csv")):
        s = pd.read_csv(f)
        rows.append(s[s["group"] == "all core"].assign(run=f.parent.name))
    t = pd.concat(rows)
    t = t[t["variant"] == "all"]
    return t.pivot_table(index=["task", "horizon", "run"], columns="split",
                         values=["NSE", "RMSE"]).round(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()
    pd.set_option("display.width", 200, "display.max_rows", 200)
    for r in args.runs:
        s = evaluate_run(r)
        print(f"== {r}\n{s[s['group'] == 'all core'].round(3).to_string(index=False)}")
    if args.compare or not args.runs:
        print(compare().to_string())


if __name__ == "__main__":
    main()
