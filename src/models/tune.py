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


def objective_factory(model, data, epochs):
    codes, weeks, X, Z, split, core, mu, sd, head = data
    lookbacks, hiddens = SPACE[model]

    def objective(trial):
        lb = trial.suggest_categorical("lookback", lookbacks)
        hidden = trial.suggest_categorical("hidden", hiddens)
        dropout = trial.suggest_float("dropout", 0.1, 0.5)
        lr = trial.suggest_float("lr", 3e-4, 3e-3, log=True)
        if model in ("lstm", "ealstm"):
            from src.models import lstm
            lstm.set_lookback(lb)
            _, best, _ = lstm.train_seed(0, X, Z, split, core, mu, sd, head, epochs, patience=6,
                                         hidden=hidden, dropout=dropout, lr=lr, arch=model)
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
            _, best, _ = stgnn.train_seed(0, None, X, Z, split, core, mu, sd, head, epochs,
                                          patience=6, lr=lr, lookback=lb, make_net=make_net)
        print(f"trial {trial.number}: {trial.params} -> validation median NSE {best:.3f}",
              flush=True)
        return best

    return objective


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODULE), required=True)
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--final-only", action="store_true")
    ap.add_argument("--no-final", action="store_true", help="search only (smoke tests)")
    args = ap.parse_args()
    out = RESULTS / f"{args.model}_tuning"
    out.mkdir(parents=True, exist_ok=True)
    study = optuna.create_study(study_name=args.model, direction="maximize",
                                storage=f"sqlite:///{out / 'study.db'}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=2026))
    if not args.final_only:
        from src.models.lstm import arrays
        P = build_panel()
        P = P[P["mu"].notna()]
        data = arrays(P)
        if args.model == "taccari":
            from src.models import taccari
            data = taccari.prepare(P, data)
        done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
        study.optimize(objective_factory(args.model, data, args.epochs),
                       n_trials=max(0, args.trials - done))
    best = study.best_trial
    (out / "best.json").write_text(json.dumps({"params": best.params,
                                               "validation_median_nse": best.value,
                                               "n_trials": len(study.trials)}, indent=1))
    print(f"best trial {best.number}: {best.params} validation {best.value:.3f}", flush=True)
    if args.no_final:
        return
    p = best.params
    cmd = [sys.executable, "-m", MODULE[args.model], "--run", f"{args.model}_tuned",
           "--lookback", str(p["lookback"]), "--hidden", str(p["hidden"]),
           "--dropout", str(p["dropout"]), "--lr", str(p["lr"])]
    if args.model in ("lstm", "ealstm"):
        cmd += ["--arch", args.model]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
