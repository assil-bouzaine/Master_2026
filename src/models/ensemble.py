"""Ensemble of simulation baselines: mean of the members chosen on validation.

    python -m src.models.ensemble

Candidates are the simulation runs that exist in results/<version>/ (Pastas,
LightGBM, LSTM, tuned LSTM, distance ST-GNN). Every subset of 2+ candidates is
scored by the median validation NSE over core wells; the best subset is kept
and written as run "ensemble_sim". The test period is never used to choose.
Averaging models with different errors is a standard way to reduce variance.
"""
import itertools

import numpy as np
import pandas as pd

from src.models.evaluate import RESULTS, evaluate_run, score

CANDIDATES = ["pastas_seasonal_canal", "lgbm_sim", "lstm", "lstm_tuned", "stgnn_distance"]


def load(run):
    p = pd.read_parquet(RESULTS / run / "predictions.parquet")
    p = p[p["task"] == "simulation"]
    return p.set_index(["code_bss", "week"])["pred"].rename(run)


def val_median(pred):
    m = score(pred)
    m = m[(m["split"] == "validation") & (m["variant"] == "all") & m["core"]]
    return m["NSE"].median()


def main():
    runs = [r for r in CANDIDATES if (RESULTS / r / "predictions.parquet").exists()]
    preds = pd.concat([load(r) for r in runs], axis=1)
    rows = []
    for k in range(2, len(runs) + 1):
        for combo in itertools.combinations(runs, k):
            mean = preds[list(combo)].mean(axis=1, skipna=False).dropna()
            p = mean.rename("pred").reset_index().assign(task="simulation", horizon=0)
            rows.append((val_median(p), combo))
            print(f"  {' + '.join(combo):<70} validation median NSE {rows[-1][0]:.3f}", flush=True)
    best_score, best = max(rows)
    print(f"selected: {' + '.join(best)} (validation {best_score:.3f})")
    out = RESULTS / "ensemble_sim"
    out.mkdir(parents=True, exist_ok=True)
    mean = preds[list(best)].mean(axis=1, skipna=False).dropna()
    mean.rename("pred").reset_index().assign(task="simulation", horizon=0).to_parquet(
        out / "predictions.parquet", index=False)
    (out / "members.txt").write_text("\n".join(best) + f"\nvalidation median NSE {best_score:.4f}\n")
    s = evaluate_run("ensemble_sim")
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(c[["split", "n_wells", "NSE", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
