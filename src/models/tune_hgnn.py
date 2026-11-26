"""Give each Hybrid-GNN arm its own validation-only tuning budget (plan v3 §3.7, §8.5).

    PFE_DATASET=v5 PFE_ALLOW_TRAIN=1 python -m src.models.tune_hgnn --arm D --workers 6

The journal is shared by CPU worker processes. The launcher reserves trials so the last
workers cannot exceed the budget. The top three seed-0 trials are checked with seeds
1 and 2 before choosing a winner. No predictions or test-period scores are produced.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import multiprocessing as mp
from multiprocessing.connection import wait

import optuna
from optuna.storages.journal import JournalFileBackend
from optuna.trial import TrialState

from src.config import DATASET, RESULTS_DIR
from src.models import hybrid_gnn as H
from src.models.manifest import code_version


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=["A", "B", "C", "D"], required=True)
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--policy", default="main")
    return ap


def model_args(args):
    """Use the model's defaults for every setting outside the six search dimensions."""
    return H.build_parser().parse_args(["--arm", args.arm, "--policy", args.policy])


def with_gain(params):
    return dict(params, lam_gain=params["r"] * params["lam_shape"])


def sample(trial):
    return {
        "epochs": trial.suggest_int("epochs", 300, 1500, log=True),
        "epochs_b": trial.suggest_int("epochs_b", 0, 400),
        "lr": trial.suggest_float("lr", 0.003, 0.03, log=True),
        "lam_shape": trial.suggest_float("lam_shape", 0.001, 1.0, log=True),
        "r": trial.suggest_float("r", 0.01, 0.5, log=True),
        "lam_delta": trial.suggest_float("lam_delta", 0.001, 1.0, log=True),
    }


def score_factory(args):
    """Prepare once in this process, on its first fit; return only validation median NSE."""
    defaults = model_args(args)
    prep = None

    def score(params, seed):
        nonlocal prep
        if prep is None:
            prep = H.prepare(defaults, verbose=False)
        values = vars(defaults) | with_gain(params)
        keys = ("epochs", "epochs_b", "lr", "weight_decay", "lam_shape", "lam_gain",
                "lam_delta", "lam_res", "kernel_weeks", "hidden", "heads", "dropout",
                "n_layers", "bucket_smooth")
        kwargs = {key: values[key] for key in keys}
        kwargs.update({key: prep[key] for key in
                       ("stage", "signs", "sign_ref", "soft", "soft_stresses", "residual",
                        "train_mask", "keep_wells")})
        result = H.train_seed(seed=seed, data=prep["data"], graph_data=prep["graph_data"],
                              well_graph_idx=prep["well_graph_idx"], device="cpu", **kwargs)
        value = float(result[1])
        if not math.isfinite(value):
            raise ValueError(f"Non-finite validation median NSE for seed {seed}: {value}")
        return value

    return score


def open_study(out, arm):
    storage = optuna.storages.JournalStorage(JournalFileBackend(str(out / "study.log")))
    return optuna.create_study(
        study_name=f"hgnn_{arm}", direction="maximize", storage=storage, load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=2026, constant_liar=True),
    )


@contextmanager
def run_lock(out):
    """A second launcher must not recover trials while the first launcher is fitting them."""
    with (out / ".tune.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Tuning is already running in {out}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def finish_trial(study, trial, score):
    """Record failed attempts too, so a broken fit never silently consumes extra budget."""
    try:
        value = score(trial.params, 0)
    except BaseException:
        study.tell(trial.number, state=TrialState.FAIL)
        raise
    study.tell(trial.number, value)
    print(f"trial {trial.number}: {with_gain(trial.params)} -> validation median NSE {value:.3f}",
          flush=True)


def reserve(study, trials):
    """Only the launcher asks for trials, keeping one TPE random stream seeded at 2026."""
    used = sum(t.state.is_finished() or t.state == TrialState.RUNNING
               for t in study.get_trials(deepcopy=False))
    if used >= trials:
        return None
    trial = study.ask()
    sample(trial)
    return trial


def search(study, score, trials):
    while True:
        trial = reserve(study, trials)
        if trial is None:
            return
        finish_trial(study, trial, score)


def worker(args, out, connection):
    H._require_train_guard()
    study = open_study(out, args.arm)
    score = score_factory(args)
    try:
        while True:
            number = connection.recv()
            if number is None:
                return
            trial = study.get_trials(deepcopy=False)[number]
            finish_trial(study, trial, score)
            connection.send(number)
    finally:
        connection.close()


def run_workers(args, out, study, context):
    """Feed one trial at a time to each worker, stopping exactly at the shared budget.

    Sampling in the launcher avoids cloned seed-2026 samplers suggesting duplicate
    startup points. Workers each open the journal and record their own finished trials.
    """
    pipes = [context.Pipe() for _ in range(args.workers)]
    processes = [context.Process(target=worker, args=(args, out, child)) for _, child in pipes]
    pending = {}

    def dispatch(connection, process):
        trial = reserve(study, args.trials)
        connection.send(None if trial is None else trial.number)
        if trial is not None:
            pending[connection] = (process, trial.number)

    try:
        for process in processes:
            process.start()
        for (connection, child), process in zip(pipes, processes):
            child.close()
            dispatch(connection, process)
        while pending:
            ready = wait([*pending, *(p.sentinel for p, _ in pending.values())])
            for connection in list(pending):
                process, number = pending[connection]
                if connection in ready:
                    try:
                        completed = connection.recv()
                    except EOFError as exc:
                        raise RuntimeError("Hybrid-GNN tuning workers failed: connection closed") from exc
                    if completed != number:
                        raise RuntimeError(f"Worker returned trial {completed}, expected {number}")
                    del pending[connection]
                    dispatch(connection, process)
                elif process.sentinel in ready:
                    raise RuntimeError(f"Hybrid-GNN tuning workers failed during trial {number}")
        for process in processes:
            process.join()
        failures = [process.exitcode for process in processes if process.exitcode != 0]
        if failures:
            raise RuntimeError(f"Hybrid-GNN tuning workers failed: exit codes {failures}")
    finally:
        # Keep the launcher lock until every child has stopped, also after Ctrl-C.
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            if process.pid is not None:
                process.join()
        for connection, child in pipes:
            connection.close()
            child.close()


def write_json(path, value):
    """Replace a complete JSON file, preserving the previous cache if the write is interrupted."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def reselect(study, score, out):
    """Cache seeds 1 and 2 of the top three trials; choose the highest three-seed mean."""
    path = out / "reselect.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    done = [t for t in study.trials if t.state == TrialState.COMPLETE]
    if not done:
        raise RuntimeError("No completed Hybrid-GNN tuning trials to reselect")
    candidates = sorted(done, key=lambda t: (-t.value, t.number))[:3]
    best = None
    for trial in candidates:
        params = with_gain(trial.params)
        entry = cache.setdefault(str(trial.number), {"params": params, "0": trial.value})
        if entry["params"] != params or entry["0"] != trial.value:
            raise ValueError(f"Re-selection cache disagrees with trial {trial.number}")
        for seed in (1, 2):
            if str(seed) not in entry:
                entry[str(seed)] = score(trial.params, seed)
                write_json(path, cache)
        entry["mean"] = sum(entry[str(seed)] for seed in (0, 1, 2)) / 3
        write_json(path, cache)
        print(f"reselect trial {trial.number}: validation mean {entry['mean']:.3f}", flush=True)
        if best is None or entry["mean"] > best[1]["mean"]:
            best = (trial, entry)
    return best


def run(args, *, context=None):
    """Run or resume a search. A supplied process context lets tests inherit their fake fits."""
    H._require_train_guard()
    if args.trials < 1 or args.workers < 1:
        raise ValueError("--trials and --workers must be >= 1")
    out = RESULTS_DIR / f"hgnn_{args.arm}_tuning"
    out.mkdir(parents=True, exist_ok=True)
    # Spawn avoids inheriting any Torch thread pools from the launcher on Colab.
    context = context or mp.get_context("spawn")
    with run_lock(out):
        study = open_study(out, args.arm)
        identity = {"arm": args.arm, "policy": args.policy, "dataset": DATASET,
                    "defaults": vars(model_args(args))}
        previous = study.user_attrs.get("identity")
        if previous is not None and previous != identity:
            raise ValueError(f"Study in {out} belongs to a different arm, policy, dataset or defaults")
        study.set_user_attr("identity", identity)
        score = score_factory(args)
        # The exclusive launcher lock proves these RUNNING trials have no live owner.
        # Reuse their numbers and sampled points rather than spending extra trials.
        for trial in study.trials:
            if trial.state == TrialState.RUNNING:
                trial = optuna.Trial(study, trial._trial_id)
                sample(trial)  # also completes suggestions if interrupted during reservation
                finish_trial(study, trial, score)
        finished = sum(t.state.is_finished() for t in study.trials)
        if finished < args.trials:
            if args.workers == 1:
                search(study, score, args.trials)
            else:
                run_workers(args, out, study, context)
        trial, entry = reselect(study, score, out)
        config = vars(model_args(args)) | {k: v for k, v in entry["params"].items() if k != "r"}
        config["seeds"] = [0, 1, 2]
        best = {
            "params": entry["params"], "config": config, "trial": trial.number,
            "scores": {str(seed): entry[str(seed)] for seed in (0, 1, 2)},
            "validation_median_nse_3seed": entry["mean"],
            "single_seed_best": study.best_value, "arm": args.arm, "policy": args.policy,
            "dataset": DATASET, "n_trials": sum(t.state.is_finished() for t in study.trials),
            "code_version": code_version(),
        }
        write_json(out / "best.json", best)
        return best


def main(argv=None):
    args = build_parser().parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
