"""Spread of the Pastas reference over its starting values (dataset v4; step 12b note).

    PFE_DATASET=v4 python -m src.analysis.pastas_stability

Reads the runs of `src.models.pastas_baseline --starts` (pulled from Kaggle):
results/v4/pastas_seasonal_canal_start<k> and ..._trainobs_start<k>. Reports, for the 33
core wells and the drought phase:
1. the median NSE of each start, and its range over the starts;
2. per well, the range of NSE over the starts;
3. a best-start run: per well, the start with the lowest training noise (the solver's own
   criterion; the test period is not looked at), written as <prefix>_beststart and scored
   like any run;
4. start 0 against the run of record (same code, data and kind of machine: equal if the
   fit is deterministic there).
Nothing is fitted here.
"""
import numpy as np
import pandas as pd

from src.models.evaluate import RESULTS, evaluate_run

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


def best_start(prefix, runs):
    params = pd.concat([pd.read_csv(d / "params.csv") for d in runs], ignore_index=True)
    best = (params.dropna(subset=["train_sse_noise"]).sort_values("train_sse_noise")
            .drop_duplicates("code_bss"))
    preds = []
    for code, k in zip(best["code_bss"], best["start"].astype(int)):
        p = pd.read_parquet(RESULTS / f"{prefix}_start{k}" / "predictions.parquet")
        preds.append(p[p["code_bss"] == code])
    out = RESULTS / f"{prefix}_beststart"
    out.mkdir(exist_ok=True)
    pd.concat(preds, ignore_index=True).to_parquet(out / "predictions.parquet", index=False)
    best.to_csv(out / "params.csv", index=False)
    evaluate_run(out.name)
    return out.name, best["start"].astype(int).value_counts().sort_index()


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
        best, picked = best_start(prefix, runs)
        print(f"\n{prefix}: {len(runs)} starts")
        print("  drought median NSE per start: "
              + ", ".join(f"{k}: {v:.2f}" for k, v in med.items()))
        print(f"  range {med.min():.2f} .. {med.max():.2f} (sd {med.std():.2f}); "
              f"best start per well: {core_drought(best):.3f} ({best})")
        print(f"  per-well range of drought NSE over the starts: median {rng.median():.2f}, "
              f"{(rng > 0.1).sum()} of {len(rng)} wells above 0.1")
        print("  starts picked by the training criterion: "
              + ", ".join(f"{k}: {n}" for k, n in picked.items()))
        if prefix == BASE and 0 in med.index:
            d = (well_drought(f"{BASE}_start0") - well_drought(BASE)).abs()
            print(f"  start 0 vs the run of record: max |per-well difference| {np.nanmax(d):.2e}")


if __name__ == "__main__":
    main()
