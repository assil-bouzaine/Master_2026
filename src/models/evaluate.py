"""Shared evaluation: every model writes predictions in one format, scored here.

Prediction format (results/<run_id>/predictions.parquet), one row per
well x week x task:
    code_bss, week, pred, task, horizon
    task    = "simulation" (inputs: weather + pumping only, no observed heads)
              or "forecast" (observed heads known up to week - horizon)
    horizon = 0 for simulation, h weeks for forecasts

    python -m src.models.evaluate <run_id> [<run_id> ...]   # (re)score runs
    python -m src.models.evaluate --all                      # rescore every run
    python -m src.models.evaluate --compare                  # table of all runs

Periods scored per well (docs/analysis_plan.md):
    train, validation, test            the time splits of the dataset
    test_drought, test_recovery        sub-periods of test (src.config.TEST_PERIODS),
                                       fixed from observed SGI before any new run
Variants (test periods only for the last two): "all" weeks; "validated", weeks with less
than half "Non qualifié" days (the v1-v3 definition, kept for comparison); "strict" (added
2026-10-23, analysis plan v2), weeks whose every value is qualified "Correcte". Values
qualified "Incorrecte" are dropped before the weekly mean from dataset v4 on; none fall in
the test period of v3. n_weeks gives the coverage of each variant.
Suspect placeholders (dataset v4 on, decided 2026-10-24; src.dataset.placeholders): the weeks
of a run of >= 28 days with a depth of exactly 0.00 m (CORNEILLA PD5, Dec 2022 - Jan 2024,
60 weeks) leave every variant; "all_unmasked" (test periods only) keeps them, to show the
scores before this rule, which was written after the test period was seen.

Metrics, per well and period:
    NSE    Nash & Sutcliffe 1970, doi:10.1016/0022-1694(70)90255-6
    KGE    the KGE'' of Tang, Clark & Papalexiou 2021 (doi:10.1175/JCLI-D-21-0067.1):
           bias term (mean_sim - mean_obs) / sd_obs instead of mean_sim / mean_obs
           (Gupta et al. 2009, doi:10.1016/j.jhydrol.2009.08.003). Heads are in m NGF,
           so the original ratio depended on the vertical datum: 12 of the 33 core
           wells have a mean head below 5 m NGF.
    r, alpha, beta_n   the three KGE'' components (correlation, sd ratio, bias / sd_obs)
    RMSE (m), bias (m)
    skill  1 - MSE / MSE_benchmark on the same weeks. Benchmark = the training
           climatology for simulation (run naive_climatology), anomaly persistence
           at the same horizon for forecasts (run naive_anomaly_persist). NSE uses
           the mean of the scored period itself as benchmark, which in a sub-period
           "knows" how low the levels went (Schaefli & Gupta 2007,
           doi:10.1002/hyp.6825).
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR, RESULTS_DIR, TEST_PERIODS
from src.dataset.placeholders import load_mask

DS = DATASET_DIR
RESULTS = RESULTS_DIR
MIN_WEEKS = 26  # a well needs half a year of weeks in a period to be scored
BENCHMARK = {"simulation": "naive_climatology", "forecast": "naive_anomaly_persist"}
PLAIN_GROUPS = ("recent alluvium", "ancient alluvium", "Pliocene multilayer")
METRICS = ["NSE", "KGE", "RMSE", "bias", "r", "alpha", "beta_n", "skill"]


def nse(obs, sim):
    return 1 - np.sum((sim - obs) ** 2) / np.sum((obs - obs.mean()) ** 2)


def kge_parts(obs, sim):
    """KGE'' (datum-free) and its components r, alpha, beta_n."""
    so, ss = obs.std(), sim.std()
    r = np.corrcoef(obs, sim)[0, 1] if so > 0 and ss > 0 else np.nan
    alpha = ss / so if so > 0 else np.nan
    beta_n = (sim.mean() - obs.mean()) / so if so > 0 else np.nan
    return 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + beta_n ** 2), r, alpha, beta_n


def kge(obs, sim):
    return kge_parts(obs, sim)[0]


def split_of(weeks, splits):
    out = pd.Series("warmup", index=weeks.index, dtype=object)
    for name in ("train", "validation", "test"):
        a, b = splits[name]
        out[(weeks >= a) & (weeks <= b)] = name
    return out


def with_periods(d, splits):
    """Label rows with their split and duplicate test rows into the test sub-periods."""
    d = d.assign(split=split_of(d["week"], splits))
    d = d[d["split"] != "warmup"]
    extra = []
    for name, (a, b) in TEST_PERIODS.items():
        m = (d["split"] == "test") & (d["week"] >= a)
        if b is not None:
            m &= d["week"] <= b
        extra.append(d[m].assign(split=name))
    return pd.concat([d] + extra, ignore_index=True)


def benchmark_predictions(tasks):
    """Benchmark predictions (code_bss, week, task, horizon, bench) for the tasks present."""
    parts = []
    for task in tasks:
        f = RESULTS / BENCHMARK[task] / "predictions.parquet"
        if f.exists():
            b = pd.read_parquet(f, columns=["code_bss", "week", "pred", "task", "horizon"])
            parts.append(b[b["task"] == task].rename(columns={"pred": "bench"}))
    return pd.concat(parts, ignore_index=True) if parts else None


def score(pred):
    """Per well x task x horizon x period x variant metrics."""
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    wells = pd.read_parquet(DS / "wells.parquet")
    splits = json.loads((DS / "splits.json").read_text())
    d = pred.merge(heads[["code_bss", "week", "head", "share_not_validated"]],
                   on=["code_bss", "week"], how="inner").dropna(subset=["pred", "head"])
    bench = benchmark_predictions(d["task"].unique())
    if bench is not None:
        d = d.merge(bench, on=["code_bss", "week", "task", "horizon"], how="left")
    else:
        d["bench"] = np.nan
    d = with_periods(d, splits)
    test_like = d["split"].str.startswith("test")
    mask = load_mask() if DATASET >= "v4" else None
    if DATASET >= "v4" and mask is None:
        raise FileNotFoundError("placeholder_weeks.parquet missing from the dataset: run "
                                "python -m src.dataset.placeholders (src.dataset.build does)")
    unmasked = None
    if mask is not None:
        flagged = pd.MultiIndex.from_frame(d[["code_bss", "week"]]).isin(
            pd.MultiIndex.from_frame(mask[["code_bss", "week"]]))
        unmasked = d[test_like]
        d, test_like = d[~flagged], test_like[~flagged]
    variants = [("all", d), ("validated", d[test_like & (d["share_not_validated"] < 0.5)]),
                ("strict", d[test_like & (d["share_not_validated"] == 0)])]
    if unmasked is not None:
        variants.append(("all_unmasked", unmasked))
    rows = []
    for variant, dd in variants:
        for (code, task, h, split), g in dd.groupby(["code_bss", "task", "horizon", "split"]):
            if len(g) < MIN_WEEKS:
                continue
            o, s = g["head"].to_numpy(), g["pred"].to_numpy()
            k, r, alpha, beta_n = kge_parts(o, s)
            gb = g.dropna(subset=["bench"])
            skill = np.nan
            if len(gb) >= MIN_WEEKS:
                ob = gb["head"].to_numpy()
                den = np.sum((gb["bench"].to_numpy() - ob) ** 2)
                if den > 0:
                    skill = 1 - np.sum((gb["pred"].to_numpy() - ob) ** 2) / den
            rows.append({"code_bss": code, "task": task, "horizon": h, "split": split,
                         "variant": variant, "n_weeks": len(g), "NSE": nse(o, s), "KGE": k,
                         "RMSE": float(np.sqrt(np.mean((s - o) ** 2))),
                         "bias": float(np.mean(s - o)), "r": r, "alpha": alpha,
                         "beta_n": beta_n, "skill": skill})
    m = pd.DataFrame(rows)
    return m.merge(wells[["code_bss", "group", "core", "libelle_pe"]], on="code_bss", how="left")


def summarise(m):
    """Median over core wells, per task x horizon x period x variant: all core, plain
    core (alluvium + Pliocene) and each aquifer group."""
    core = m[m["core"]]
    keys = ["task", "horizon", "split", "variant"]
    agg = ({"n_wells": ("code_bss", "nunique"), "n_weeks": ("n_weeks", "sum")}
           | {k: (k, "median") for k in METRICS})
    parts = [core.groupby(keys).agg(**agg).reset_index().assign(group="all core"),
             core[core["group"].isin(PLAIN_GROUPS)].groupby(keys).agg(**agg).reset_index()
             .assign(group="plain core"),
             core.groupby(keys + ["group"]).agg(**agg).reset_index()]
    return pd.concat(parts, ignore_index=True)


def evaluate_run(run_id):
    run = RESULTS / run_id
    pred = pd.read_parquet(run / "predictions.parquet")
    m = score(pred)
    m.to_csv(run / "metrics_per_well.csv", index=False)
    s = summarise(m)
    s.to_csv(run / "metrics_summary.csv", index=False)
    return s


def all_runs():
    return sorted(p.parent.name for p in RESULTS.glob("*/predictions.parquet"))


def compare():
    rows = []
    for f in sorted(RESULTS.glob("*/metrics_summary.csv")):
        s = pd.read_csv(f)
        rows.append(s[s["group"] == "all core"].assign(run=f.parent.name))
    t = pd.concat(rows)
    t = t[t["variant"] == "all"]
    return t.pivot_table(index=["task", "horizon", "run"], columns="split",
                         values=["NSE", "skill"]).round(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--all", action="store_true", help="rescore every run of this dataset version")
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()
    pd.set_option("display.width", 220, "display.max_rows", 300, "display.max_columns", 30)
    runs = all_runs() if args.all else args.runs
    cols = ["task", "horizon", "split", "n_wells", "NSE", "skill", "KGE", "RMSE"]
    for r in runs:
        s = evaluate_run(r)
        c = s[(s["group"] == "all core") & (s["variant"] == "all")]
        print(f"== {r}\n" + c[cols].round(3).to_string(index=False), flush=True)
    if args.compare or not runs:
        print(compare().to_string())


if __name__ == "__main__":
    main()
