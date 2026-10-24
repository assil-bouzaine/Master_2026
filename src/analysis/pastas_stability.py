"""Spread of the Pastas reference over its starting values (dataset v4; step 12b note).

    PFE_DATASET=v4 python -m src.analysis.pastas_stability

Reads the runs of `src.models.pastas_baseline --starts` (pulled from Kaggle):
results/v4/pastas_seasonal_canal_start<k> and ..._trainobs_start<k>. Reports, for the 33
core wells and the drought phase:
1. the median NSE of each start, and its range over the starts;
2. per well, the range of NSE over the starts;
3. a best-start run: per well, the start whose deterministic simulation has the lowest RMSE
   on the observed training weeks (model_start to the end of training: 2005-2019). The
   criterion was fixed on 2026-10-25, before any multistart result was seen (third review,
   docs/review_codex_2026-10-24.md §3.3): it uses training heads only, it scores what the
   baseline is used for (the simulation, not the noise model), and it exists for every run.
   The solver's own objective (sum of squares of the weighted noise, `train_objective`) is
   only stored by runs pushed after 2026-10-25; where present, its agreement with the chosen
   start is reported. Ties go to the lower start number. Written as <prefix>_beststart and
   scored like any run;
4. start 0 against the run of record (same code, data and kind of machine: equal if the
   fit is deterministic there), and the simplified-response fallbacks and failures per start.
Nothing is fitted here.
"""
import json

import numpy as np
import pandas as pd

from src.models.evaluate import DS, RESULTS, evaluate_run

BASE = "pastas_seasonal_canal"


def start_runs(prefix):
    runs = [d for d in RESULTS.glob(f"{prefix}_start*") if (d / "predictions.parquet").exists()]
    return sorted(runs, key=lambda d: int(d.name.rsplit("start", 1)[1]))


def core_drought(run):
    s = pd.read_csv(RESULTS / run / "metrics_summary.csv")
    q = s[(s["group"] == "all core") & (s["variant"] == "all") & (s["split"] == "test_drought")]
    return float(q["NSE"].iloc[0])


def well_drought(run):
    m = pd.read_csv(RESULTS / run / "metrics_per_well.csv")
    return m[(m["split"] == "test_drought") & (m["variant"] == "all")].set_index("code_bss")["NSE"]


def train_rmse(pred, heads, splits):
    """Per well: RMSE of the simulated head on the observed training weeks."""
    t0, t1 = pd.Timestamp(splits["model_start"]), pd.Timestamp(splits["train"][1])
    h = heads[heads["week"].between(t0, t1)].dropna(subset=["head"])
    m = h.merge(pred[["code_bss", "week", "pred"]], on=["code_bss", "week"]).dropna(subset=["pred"])
    return m.assign(e2=(m["pred"] - m["head"]) ** 2).groupby("code_bss")["e2"].mean() ** 0.5


def pick(scores):
    """scores: DataFrame (code_bss, start, rmse) -> the chosen start per well (ties: lower)."""
    return (scores.dropna(subset=["rmse"]).sort_values(["code_bss", "rmse", "start"])
            .drop_duplicates("code_bss").set_index("code_bss")["start"].astype(int))


def best_start(prefix, runs):
    splits = json.loads((DS / "splits.json").read_text())
    heads = pd.read_parquet(DS / "heads_weekly.parquet", columns=["code_bss", "week", "head"])
    preds, scores, params = {}, [], []
    for d in runs:
        k = int(d.name.rsplit("start", 1)[1])
        preds[k] = pd.read_parquet(d / "predictions.parquet")
        scores.append(train_rmse(preds[k], heads, splits).rename("rmse").reset_index().assign(start=k))
        params.append(pd.read_csv(d / "params.csv").assign(start=k))
    scores, params = pd.concat(scores, ignore_index=True), pd.concat(params, ignore_index=True)
    chosen = pick(scores)
    out = RESULTS / f"{prefix}_beststart"
    out.mkdir(exist_ok=True)
    pd.concat([preds[k][preds[k]["code_bss"] == c] for c, k in chosen.items()],
              ignore_index=True).to_parquet(out / "predictions.parquet", index=False)
    rows = params.merge(chosen.rename("chosen").reset_index(), on="code_bss")
    rows = rows[rows["start"] == rows["chosen"]].drop(columns="chosen")
    rows = rows.merge(scores, on=["code_bss", "start"], how="left").rename(columns={"rmse": "train_rmse"})
    rows.assign(criterion="training-period simulation RMSE").to_csv(out / "params.csv", index=False)
    evaluate_run(out.name)
    agree = None
    if "train_objective" in params and params["train_objective"].notna().any():
        obj = (params.dropna(subset=["train_objective"])
               .rename(columns={"train_objective": "rmse"})[["code_bss", "start", "rmse"]])
        by_obj = pick(obj)
        common = chosen.index.intersection(by_obj.index)
        agree = (int((chosen[common] == by_obj[common]).sum()), len(common))
    fallbacks = params.groupby("start").agg(
        simple=("simple_rfuncs", lambda s: int(s.fillna(False).astype(bool).sum())),
        failed=("error", lambda s: int(s.fillna("").astype(str).str.len().gt(0).sum())))
    return out.name, chosen.value_counts().sort_index(), agree, fallbacks


def main():
    record = core_drought(BASE)
    print(f"run of record {BASE}: drought median NSE {record:.3f}")
    for prefix in (BASE, f"{BASE}_trainobs"):
        runs = start_runs(prefix)
        if not runs:
            print(f"\n{prefix}: no start runs yet (pull the Kaggle output first)")
            continue
        med = pd.Series({int(d.name.rsplit("start", 1)[1]): core_drought(d.name) for d in runs})
        wells = pd.concat({d.name: well_drought(d.name) for d in runs}, axis=1)
        rng = wells.max(axis=1) - wells.min(axis=1)
        best, picked, agree, fallbacks = best_start(prefix, runs)
        print(f"\n{prefix}: {len(runs)} starts")
        print("  drought median NSE per start: "
              + ", ".join(f"{k}: {v:.2f}" for k, v in med.items()))
        print(f"  range {med.min():.2f} .. {med.max():.2f} (sd {med.std():.2f}); "
              f"best start per well (training-period simulation RMSE): {core_drought(best):.3f} ({best})")
        print(f"  per-well range of drought NSE over the starts: median {rng.median():.2f}, "
              f"{(rng > 0.1).sum()} of {len(rng)} wells above 0.1")
        print("  starts picked: " + ", ".join(f"{k}: {n}" for k, n in picked.items()))
        print("  " + (f"same start as the solver's objective for {agree[0]} of {agree[1]} wells"
                      if agree else "solver objective not stored by these runs (pushed before "
                                    "2026-10-25)"))
        print("  simplified-response fallbacks / failed wells per start: "
              + ", ".join(f"{k}: {r.simple}/{r.failed}" for k, r in fallbacks.iterrows()))
        if prefix == BASE and 0 in med.index:
            d = (well_drought(f"{BASE}_start0") - well_drought(BASE)).abs()
            print(f"  start 0 vs the run of record: max |per-well difference| {np.nanmax(d):.2e}")


if __name__ == "__main__":
    main()
