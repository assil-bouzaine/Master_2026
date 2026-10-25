"""The pre-registered land-use test (analysis plan §14 item 13), scored as written.

    PFE_DATASET=v4 python -m src.analysis.land_use_test

Written on 2026-10-25, before any land-use run. For each model, the tuned LightGBM without
its own climatology and the tuned LSTM, the run with the main crop-demand input
(`<run>_lu_on`) is compared with the same model without it (`<run>`, same settings and
seeds), well by well on the core wells, in the drought phase:

  main contrast   on vs without: median paired difference of NSE and of skill, cluster-
                  bootstrap 95 % interval, cluster sign-flip p (src.analysis.stats.paired,
                  strict paired support), Holm over the two models, per metric
  placebo         placebo vs without, and on vs placebo: a gain that the placebo also shows
                  is not evidence that the crop information is used
  wide            wide (vines, olives, nuts, fodder added) vs without
  aquifer groups  the main contrast per group (secondary)

Placebo, wide and group rows are reported with the same endpoint, outside the Holm family.
Runs not yet available are listed as missing; nothing is computed for them.

Output: results/<dataset>/land_use_test.csv (printed)
"""
import pandas as pd

from src.analysis.stats import holm, paired
from src.models.evaluate import DS, RESULTS

MODELS = {"LightGBM (no own climatology)": "lgbm_noclim_tuned", "LSTM": "lstm_tuned"}
METRICS = ("NSE", "skill")
SPLIT = "test_drought"
OUT = RESULTS / "land_use_test.csv"


def metrics(run):
    f = RESULTS / run / "metrics_per_well.csv"
    return pd.read_csv(f) if f.exists() else None


def contrasts():
    wells = pd.read_parquet(DS / "wells.parquet")
    rows, missing = [], []
    for label, base in MODELS.items():
        runs = {v: metrics(base + s) for v, s in
                (("without", ""), ("on", "_lu_on"), ("placebo", "_lu_placebo"), ("wide", "_lu_wide"))}
        missing += [base + s for v, s in (("without", ""), ("on", "_lu_on"), ("placebo", "_lu_placebo"),
                                          ("wide", "_lu_wide")) if runs[v] is None]
        pairs = [("main", "on", "without"), ("placebo", "placebo", "without"),
                 ("placebo", "on", "placebo"), ("wide", "wide", "without")]
        for kind, a, b in pairs:
            if runs[a] is None or runs[b] is None:
                continue
            for metric in METRICS:
                r = paired(runs[a], runs[b], wells, split=SPLIT, metric=metric, strict=kind == "main")
                rows.append({"model": label, "kind": kind, "contrast": f"{a} vs {b}",
                             "group": "all core", "metric": metric} | r)
        if runs["on"] is not None and runs["without"] is not None:
            for grp in sorted(runs["without"]["group"].dropna().unique()):
                sel = {k: m[m["group"] == grp] for k, m in (("on", runs["on"]), ("without", runs["without"]))}
                for metric in METRICS:
                    r = paired(sel["on"], sel["without"], wells, split=SPLIT, metric=metric)
                    rows.append({"model": label, "kind": "group", "contrast": "on vs without",
                                 "group": grp, "metric": metric} | r)
    t = pd.DataFrame(rows)
    if len(t):
        t["p_holm"] = float("nan")
        for metric in METRICS:
            idx = t.index[(t["kind"] == "main") & (t["metric"] == metric)]
            if len(idx):
                t.loc[idx, "p_holm"] = holm(t.loc[idx, "p_cluster"].to_numpy())
    return t, missing


def main():
    t, missing = contrasts()
    if missing:
        print("not yet run: " + ", ".join(missing))
    if not len(t):
        print("no contrast can be computed yet")
        return
    t.to_csv(OUT, index=False)
    cols = ["model", "kind", "contrast", "group", "metric", "n_wells", "median_diff", "ci_lo", "ci_hi",
            "p_cluster", "p_holm", "support_mismatch"]
    print(t[[c for c in cols if c in t.columns]].round(3).to_string(index=False))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
