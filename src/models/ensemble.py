"""Ensemble of simulation baselines: mean of the members chosen on validation.

    python -m src.models.ensemble

Rule (docs/analysis_plan.md section 5, fixed on 2026-10-20 before the v3 ensemble was
built):
1. one candidate per model family (FAMILIES): the family's run with the best median
   validation NSE over the core wells;
2. every subset of 2+ family winners is scored by the same validation median; the best
   subset is kept and written as run "ensemble_sim".
Searching all runs instead (11 on v3, 2,036 subsets) would reward runs that happen to do
well on validation, the winner's curse already seen in the tuning. The test period is
never used. Averaging models with different errors is a standard way to reduce variance.
From v4 the Pastas candidate is the reference built from training heads only (decided
2026-10-24): the full-series fits set their initial constant from test-period heads too.
"""
import itertools

import pandas as pd

from src.config import DATASET
from src.models.evaluate import RESULTS, evaluate_run, score

FAMILIES = {"Pastas": (["pastas_seasonal_canal_trainobs_beststart"] if DATASET >= "v4"
                       else ["pastas_seasonal_canal", "pastas_wellmodel"]),
            # without its own-climatology input, like the networks (decision 2026-10-20)
            "LightGBM": ["lgbm_noclim_tuned"],
            "recurrent": ["lstm", "lstm_tuned", "ealstm_tuned"],
            "graph": ["stgnn_distance", "stgnn_tuned", "taccari", "taccari_tuned"]}


def load(run):
    p = pd.read_parquet(RESULTS / run / "predictions.parquet")
    p = p[p["task"] == "simulation"]
    return p.set_index(["code_bss", "week"])["pred"].rename(run)


def as_frame(pred):
    return pred.rename("pred").reset_index().assign(task="simulation", horizon=0)


def val_median(pred):
    m = score(pred)
    m = m[(m["split"] == "validation") & (m["variant"] == "all") & m["core"]]
    return m["NSE"].median()


def main():
    preds, winners, log = {}, [], []
    for fam, runs in FAMILIES.items():
        best = None
        for r in runs:
            if not (RESULTS / r / "predictions.parquet").exists():
                continue
            preds[r] = load(r)
            v = val_median(as_frame(preds[r]))
            log.append(f"{fam}: {r} validation median NSE {v:.4f}")
            print(f"  {log[-1]}", flush=True)
            if best is None or v > best[0]:
                best = (v, r)
        if best:
            winners.append(best[1])
    rows = []
    for k in range(2, len(winners) + 1):
        for combo in itertools.combinations(winners, k):
            mean = pd.concat([preds[r] for r in combo], axis=1).mean(axis=1, skipna=False).dropna()
            rows.append((val_median(as_frame(mean)), combo))
            print(f"  {' + '.join(combo):<70} validation median NSE {rows[-1][0]:.3f}", flush=True)
    best_score, best = max(rows)
    print(f"selected: {' + '.join(best)} (validation {best_score:.3f}; {len(rows)} subsets "
          f"of {len(winners)} family winners)")
    out = RESULTS / "ensemble_sim"
    out.mkdir(parents=True, exist_ok=True)
    mean = pd.concat([preds[r] for r in best], axis=1).mean(axis=1, skipna=False).dropna()
    as_frame(mean).to_parquet(out / "predictions.parquet", index=False)
    (out / "members.txt").write_text("\n".join(best) + f"\nvalidation median NSE {best_score:.4f}"
                                     f"\n{len(rows)} candidate subsets of the family winners\n"
                                     + "\n".join(log) + "\n")
    s = evaluate_run("ensemble_sim")
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(c[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
