"""Equal-budget validation-only Optuna tuner for Hetero-STGNN (analysis plan v3 §3.7 and §6).

    PFE_DATASET=v5 PFE_ALLOW_TRAIN=1 python -m src.models.tune_hstgnn --arm D

Why this module exists
----------------------
Analysis plan v3 §6 requires the black-box Hetero-STGNN competitor to be tuned under the exact
same validation-only budget as Hybrid-GNN v2 (§3.7): 24 Optuna TPE trials (seed 2026) scored on
the median validation NSE of the core wells (seed 0), followed by re-evaluation of the top 3
trials on seeds 1 and 2, selecting the configuration with the highest 3-seed validation mean.
Each primary arm (C and D) receives its own independent 24-trial budget; E/F controls reuse arm
D's tuned settings. No predictions or test-period scores are produced here.

Search space (6 dimensions):
- ``hidden`` in ``{16, 32, 64}``
- ``receptive_field`` in ``{52, 104, 156}`` weeks
- ``lr`` in ``[1e-3, 1e-2]`` (log)
- ``weight_decay`` in ``[1e-5, 1e-2]`` (log)
- ``dropout`` in ``[0.0, 0.3]``
- ``epochs`` in ``[100, 800]``

Outputs: ``results/<dataset>/hstgnn_<arm>_tuning/{study.log, reselect.json, best.json}``.
Uses Optuna's file journal storage (resumable, safe on Colab without SQLite lock issues).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path

import optuna
from optuna.storages.journal import JournalFileBackend
from optuna.trial import TrialState

from src.config import DATASET, RESULTS_DIR
from src.models import hetero_stgnn as S
from src.models.manifest import code_version

HIDDEN_CHOICES = list(S.HIDDEN_CHOICES)
RECEPTIVE_FIELD_CHOICES = list(S.RECEPTIVE_FIELD_CHOICES)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Equal-budget Optuna tuner for Hetero-STGNN (plan v3 §3.7, §6)")
    ap.add_argument("--arm", choices=["C", "D"], required=True)
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--policy", default="main")
    ap.add_argument("--device", default=None, help="override torch device (default: cuda if available else cpu)")
    return ap


def model_args(args) -> argparse.Namespace:
    """Use HeteroSTGNN's defaults for every setting outside the six search dimensions."""
    return S.build_parser().parse_args(["--arm", args.arm, "--policy", args.policy])


def sample(trial: optuna.Trial) -> dict:
    """Sample one trial from the six-dimensional Hetero-STGNN search space."""
    return {
        "hidden": trial.suggest_categorical("hidden", HIDDEN_CHOICES),
        "receptive_field": trial.suggest_categorical("receptive_field", RECEPTIVE_FIELD_CHOICES),
        "lr": trial.suggest_float("lr", 1e-3, 1e-2, log=True),
        "weight_decay": trial.suggest_float("weight_decay", 1e-5, 1e-2, log=True),
        "dropout": trial.suggest_float("dropout", 0.0, 0.3),
        "epochs": trial.suggest_int("epochs", 100, 800),
    }


def parameter_count_for(prep: dict, hidden: int, receptive_field: int, dropout: float = 0.0) -> int:
    """Count trainable parameters of ``HeteroSTGNN`` on ``prep``'s graph for ``(hidden, receptive_field)``."""
    kw = dict(prep["model_kwargs"])
    kw.update(hidden=int(hidden), receptive_field=int(receptive_field), dropout=float(dropout))
    net = S.HeteroSTGNN.from_heterodata(prep["graph_data"], **kw)
    return S.count_parameters(net)


def score_factory(args):
    """Prepare once and return ``(score, cached_prep)`` where ``score(params, seed)`` returns val NSE."""
    defaults = model_args(args)
    state = {"prep": None}

    def score(params: dict, seed: int) -> float:
        if state["prep"] is None:
            state["prep"] = S.prepare(defaults, verbose=False)
        p = state["prep"]
        values = vars(defaults) | dict(params)
        _, val_nse, _, _ = S.train_seed(
            seed=seed,
            data=p["data"],
            graph_data=p["graph_data"],
            well_graph_idx=p["well_graph_idx"],
            epochs=int(values["epochs"]),
            lr=float(values["lr"]),
            weight_decay=float(values["weight_decay"]),
            hidden=int(values["hidden"]),
            receptive_field=int(values["receptive_field"]),
            dropout=float(values["dropout"]),
            n_spatial_layers=int(values["n_spatial_layers"]),
            train_mask=p["train_mask"],
            keep_wells=p["keep_wells"],
            device=args.device,
            verbose=False,
        )
        value = float(val_nse)
        if not math.isfinite(value):
            raise ValueError(f"Non-finite validation median NSE for seed {seed}: {value}")
        return value

    return score, state


def open_study(out: Path, arm: str) -> optuna.Study:
    storage = optuna.storages.JournalStorage(JournalFileBackend(str(out / "study.log")))
    return optuna.create_study(
        study_name=f"hstgnn_{arm}",
        direction="maximize",
        storage=storage,
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=2026),
    )


@contextmanager
def run_lock(out: Path):
    """Prevent two concurrent tuners from racing on the same arm's journal."""
    with (out / ".tune.lock").open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Tuning is already running in {out}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_json(path: Path, value: dict):
    """Atomically write JSON so an interrupted session keeps the last complete cache."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def finish_trial(study: optuna.Study, trial: optuna.Trial, score):
    """Evaluate seed 0 and record COMPLETE or FAIL so broken fits never spend extra budget."""
    try:
        value = score(trial.params, 0)
    except BaseException:
        study.tell(trial.number, state=TrialState.FAIL)
        raise
    study.tell(trial.number, value)
    print(f"trial {trial.number}: {trial.params} -> validation median NSE {value:.3f}", flush=True)


def reselect(study: optuna.Study, score, out: Path):
    """Re-evaluate the top 3 completed trials with seeds 1 and 2; choose highest 3-seed mean."""
    path = out / "reselect.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    done = [t for t in study.trials if t.state == TrialState.COMPLETE]
    if not done:
        raise RuntimeError("No completed Hetero-STGNN tuning trials to reselect")
    candidates = sorted(done, key=lambda t: (-t.value, t.number))[:3]
    best = None
    for trial in candidates:
        params = dict(trial.params)
        entry = cache.setdefault(str(trial.number), {"params": params, "0": trial.value})
        if entry["params"] != params or entry["0"] != trial.value:
            raise ValueError(f"Re-selection cache disagrees with trial {trial.number}")
        for seed in (1, 2):
            if str(seed) not in entry:
                entry[str(seed)] = score(params, seed)
                write_json(path, cache)
        entry["mean"] = sum(entry[str(seed)] for seed in (0, 1, 2)) / 3.0
        write_json(path, cache)
        print(f"reselect trial {trial.number}: validation mean {entry['mean']:.3f}", flush=True)
        if best is None or entry["mean"] > best[1]["mean"]:
            best = (trial, entry)
    return best


def run(args) -> dict:
    """Run or resume the 24-trial Optuna search and 3-seed re-selection for one arm."""
    S._require_train_guard()
    if args.trials < 1:
        raise ValueError("--trials must be >= 1")
    out = RESULTS_DIR / f"hstgnn_{args.arm}_tuning"
    out.mkdir(parents=True, exist_ok=True)
    with run_lock(out):
        study = open_study(out, args.arm)
        identity = {
            "arm": args.arm,
            "policy": args.policy,
            "dataset": DATASET,
            "defaults": vars(model_args(args)),
        }
        previous = study.user_attrs.get("identity")
        if previous is not None and previous != identity:
            raise ValueError(f"Study in {out} belongs to a different arm, policy, dataset or defaults")
        study.set_user_attr("identity", identity)

        score, prep_state = score_factory(args)

        # Resume any interrupted RUNNING trials without consuming extra budget.
        for t in study.trials:
            if t.state == TrialState.RUNNING:
                trial = optuna.Trial(study, t._trial_id)
                sample(trial)
                finish_trial(study, trial, score)

        while sum(t.state.is_finished() for t in study.trials) < args.trials:
            trial = study.ask()
            sample(trial)
            finish_trial(study, trial, score)

        trial, entry = reselect(study, score, out)
        config = vars(model_args(args)) | dict(entry["params"])
        config["seeds"] = [0, 1, 2]
        n_params = None
        prev_best = out / "best.json"
        if prep_state["prep"] is not None:
            p = prep_state["prep"]
            if isinstance(p, dict) and "graph_data" in p and "model_kwargs" in p:
                try:
                    n_params = parameter_count_for(
                        p, entry["params"]["hidden"], entry["params"]["receptive_field"]
                    )
                except Exception:
                    n_params = None
        elif prev_best.exists():
            n_params = json.loads(prev_best.read_text(encoding="utf-8")).get("n_parameters")

        best = {
            "params": entry["params"],
            "config": config,
            "trial": trial.number,
            "scores": {str(seed): entry[str(seed)] for seed in (0, 1, 2)},
            "validation_median_nse_3seed": entry["mean"],
            "single_seed_best": study.best_value,
            "arm": args.arm,
            "policy": args.policy,
            "dataset": DATASET,
            "n_trials": sum(t.state.is_finished() for t in study.trials),
            "n_parameters": n_params,
            "code_version": code_version(),
        }
        write_json(out / "best.json", best)
        return best


def main(argv=None):
    args = build_parser().parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
