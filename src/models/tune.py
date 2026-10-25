"""Tune a neural baseline with Optuna (equal budget for every model), then train 5 seeds.

    python -m src.models.tune --model lstm   --trials 24    # -> results/<v>/lstm_tuned/
    python -m src.models.tune --model ealstm --trials 24    # -> ealstm_tuned/
    python -m src.models.tune --model stgnn  --trials 24    # -> stgnn_tuned/
    python -m src.models.tune --model taccari --trials 24   # -> taccari_tuned/
    python -m src.models.tune --model lstm --final-only     # skip the search, retrain best

docs/analysis_plan.md section 5: Optuna TPE sampler (seed 2026), 24 trials, objective =
median validation NSE over the core wells, one seed per trial with early stopping
(patience 6, at most 40 epochs). Search spaces of the same size, 4 hyperparameters:
look-back, hidden size, dropout, learning rate. The test period is never looked at.
Selection: the 3 best trials are re-run with seeds 1 and 2 and the configuration with the
best 3-seed mean wins (reselect(); a single-seed maximum over 24 trials favours lucky seeds).
Akiba et al. 2019, Optuna, doi:10.1145/3292500.3330701. Resumable (SQLite study).

Outputs: results/<version>/<model>_tuning/study.db and best.json; the final model goes to
results/<version>/<model>_tuned/ (5 seeds, scored by evaluate.py).
"""
import argparse
import json
import subprocess
import sys

import optuna
import pandas as pd

from src.models.evaluate import DS, RESULTS
from src.models.features import build_panel

MODULE = {"lstm": "src.models.lstm", "ealstm": "src.models.lstm", "stgnn": "src.models.stgnn",
          "taccari": "src.models.taccari"}
SPACE = {  # (lookback choices, hidden choices)
    "lstm": ([104, 156, 208], [64, 128]),
    "ealstm": ([104, 156, 208], [64, 128]),
    "stgnn": ([104, 156], [32, 64, 128]),
    "taccari": ([52, 104, 156], [32, 64]),
}


def reselect(study, score, out, top=3, seeds=(1, 2)):
    """Re-evaluate the `top` best trials with extra `seeds` (validation only) and return
    (params, 3-seed mean) of the best mean. Scores are cached in reselect.json (resumable)."""
    f = out / "reselect.json"
    cache = json.loads(f.read_text()) if f.exists() else {}
    done = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    best = None
    for t in sorted(done, key=lambda t: t.value, reverse=True)[:top]:
        c = cache.setdefault(str(t.number), {"params": t.params, "0": t.value})
        for s in seeds:
            if str(s) not in c:
                c[str(s)] = score(t.params, s)
                f.write_text(json.dumps(cache, indent=1))
        mean = sum(c[str(s)] for s in (0, *seeds)) / (1 + len(seeds))
        c["mean"] = mean
        print(f"reselect trial {t.number}: seeds {[round(c[str(s)], 3) for s in (0, *seeds)]}"
              f" mean {mean:.3f}", flush=True)
        if best is None or mean > best[1]:
            best = (t.params, mean, t.number)
    f.write_text(json.dumps(cache, indent=1))
    return best


def score_factory(model, data, epochs):
    """score(params, seed) -> validation median NSE of one training run."""
    codes, weeks, X, Z, split, core, mu, sd, head = data

    def score(p, seed):
        lb, hidden, dropout, lr = p["lookback"], p["hidden"], p["dropout"], p["lr"]
        if model in ("lstm", "ealstm"):
            from src.models import lstm
            lstm.set_lookback(lb)
            _, best, _ = lstm.train_seed(seed, X, Z, split, core, mu, sd, head, epochs,
                                         patience=6, hidden=hidden, dropout=dropout, lr=lr,
                                         arch=model)
        else:
            from src.models import stgnn
            wells = pd.read_parquet(DS / "wells.parquet")
            if model == "stgnn":
                A = stgnn.distance_adjacency(codes, wells)
                make_net = lambda F: stgnn.Net(F, A, hidden, dropout)  # noqa: E731
            else:
                from src.models import taccari
                ns = argparse.Namespace(hidden=hidden, dropout=dropout)
                make_net = taccari.build(codes, wells, X.shape[2], ns)
            _, best, _ = stgnn.train_seed(seed, None, X, Z, split, core, mu, sd, head, epochs,
                                          patience=6, lr=lr, lookback=lb, make_net=make_net)
        return best

    return score


def objective_factory(model, score):
    lookbacks, hiddens = SPACE[model]

    def objective(trial):
        p = {"lookback": trial.suggest_categorical("lookback", lookbacks),
             "hidden": trial.suggest_categorical("hidden", hiddens),
             "dropout": trial.suggest_float("dropout", 0.1, 0.5),
             "lr": trial.suggest_float("lr", 3e-4, 3e-3, log=True)}
        best = score(p, 0)
        print(f"trial {trial.number}: {p} -> validation median NSE {best:.3f}", flush=True)
        return best

    return objective


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODULE), required=True)
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--final-only", action="store_true")
    ap.add_argument("--no-final", action="store_true", help="search only (smoke tests)")
    ap.add_argument("--land-use", choices=["on", "placebo", "wide", "frozen", "none"], default=None,
                    help="with --final-only: the tuned configuration with the crop-demand input, "
                         "main, placebo, wide or frozen -> <model>_tuned_lu_<variant> (analysis plan §14 item 13); "
                         "none: without it, re-trained in the land-use job (a control for the machine)")
    args = ap.parse_args()
    if args.land_use and not args.final_only:
        ap.error("--land-use reuses the tuned configuration: use it with --final-only")
    if args.land_use and args.model not in ("lstm", "ealstm"):
        ap.error("--land-use is implemented for the LSTM family (the pre-registered test)")
    out = RESULTS / f"{args.model}_tuning"
    out.mkdir(parents=True, exist_ok=True)
    study = optuna.create_study(study_name=args.model, direction="maximize",
                                storage=f"sqlite:///{out / 'study.db'}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=2026))
    if args.final_only and (out / "best.json").exists():
        p = json.loads((out / "best.json").read_text())["params"]
    else:
        from src.models.lstm import arrays
        P = build_panel()
        P = P[P["mu"].notna()]
        data = arrays(P)
        if args.model == "taccari":
            from src.models import taccari
            data = taccari.prepare(P, data)
        score = score_factory(args.model, data, args.epochs)
        done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
        if not args.final_only:
            study.optimize(objective_factory(args.model, score),
                           n_trials=max(0, args.trials - done))
        p, mean, number = reselect(study, score, out)
        (out / "best.json").write_text(json.dumps(
            {"params": p, "trial": number, "validation_median_nse_3seed": mean,
             "single_seed_best": study.best_value, "n_trials": len(study.trials)}, indent=1))
        print(f"selected trial {number}: {p} 3-seed validation {mean:.3f}", flush=True)
    if args.no_final:
        return
    run = f"{args.model}_tuned" + (f"_lu_{args.land_use}" if args.land_use else "")
    cmd = [sys.executable, "-m", MODULE[args.model], "--run", run,
           "--lookback", str(p["lookback"]), "--hidden", str(p["hidden"]),
           "--dropout", str(p["dropout"]), "--lr", str(p["lr"])]
    if args.land_use:
        cmd += ["--land-use", args.land_use]
    if args.model in ("lstm", "ealstm"):
        cmd += ["--arch", args.model]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
