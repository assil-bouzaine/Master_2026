"""Tune the global LSTM with Optuna, then retrain the best configuration with 5 seeds.

    python -m src.models.tune_lstm --trials 24        # resumable (SQLite study)
    python -m src.models.tune_lstm --final-only       # skip the search, retrain best

Search space: look-back 104/156/208 weeks (the confined Pliocene has a long
memory), hidden size 64/128, dropout 0.1-0.4, learning rate 3e-4-3e-3.
Objective: the median validation NSE over core wells, from one seed per trial
with early stopping. **Selection uses validation only; the test period is
never looked at.** Akiba et al. 2019, Optuna, doi:10.1145/3292500.3330701.

Outputs: results/<version>/lstm_tuning/study.db and best.json; the final model
goes to results/<version>/lstm_tuned/ (5 seeds, scored by evaluate.py).
"""
import argparse
import json
import subprocess
import sys

import optuna

from src.models import lstm
from src.models.evaluate import RESULTS
from src.models.features import build_panel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--final-only", action="store_true")
    args = ap.parse_args()
    out = RESULTS / "lstm_tuning"
    out.mkdir(parents=True, exist_ok=True)
    study = optuna.create_study(study_name="lstm", direction="maximize",
                                storage=f"sqlite:///{out / 'study.db'}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=2026))
    if not args.final_only:
        P = build_panel()
        P = P[P["mu"].notna()]
        codes, weeks, X, Z, split, core, mu, sd, head = lstm.arrays(P)

        def objective(trial):
            lstm.set_lookback(trial.suggest_categorical("lookback", [104, 156, 208]))
            hidden = trial.suggest_categorical("hidden", [64, 128])
            dropout = trial.suggest_float("dropout", 0.1, 0.4)
            lr = trial.suggest_float("lr", 3e-4, 3e-3, log=True)
            _, best = lstm.train_seed(0, X, Z, split, core, mu, sd, head, args.epochs,
                                      patience=6, hidden=hidden, dropout=dropout, lr=lr)
            print(f"trial {trial.number}: {trial.params} -> validation median NSE {best:.3f}",
                  flush=True)
            return best

        done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
        study.optimize(objective, n_trials=max(0, args.trials - done))
    best = study.best_trial
    (out / "best.json").write_text(json.dumps({"params": best.params,
                                               "validation_median_nse": best.value,
                                               "n_trials": len(study.trials)}, indent=1))
    print(f"best trial {best.number}: {best.params} validation {best.value:.3f}", flush=True)
    p = best.params
    subprocess.run([sys.executable, "-m", "src.models.lstm", "--run", "lstm_tuned",
                    "--lookback", str(p["lookback"]), "--hidden", str(p["hidden"]),
                    "--dropout", str(p["dropout"]), "--lr", str(p["lr"])], check=True)


if __name__ == "__main__":
    main()
