"""Check the equal-budget Hybrid-GNN tuner without fitting (analysis plan v3 §3.7, §8.5).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m tests.test_tune_hgnn

Preparation returns tiny stand-ins, and every training call returns a deterministic fake
network and validation score. Forked test workers inherit these replacements; production
workers use spawn. All study files and runner probes live in temporary directories.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
import io
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import optuna
from optuna.trial import TrialState

from src.config import ROOT
from src.models import hybrid_gnn as H
from src.models import tune_hgnn as T


def fake_prepare(args, *, verbose, event_dir):
    assert verbose is False
    assert (args.stage, args.signs, args.hidden, args.heads, args.n_layers, args.dropout,
            args.regime, args.pumping_reconstruction, args.residual) == (
                "B", "gate3", 32, 2, 2, 0.1, "R1", 1, "none")
    with (event_dir / f"prepare_{os.getpid()}.txt").open("a") as handle:
        handle.write("prepare\n")
    return {
        "data": {"event_dir": event_dir}, "graph_data": "fake graph", "well_graph_idx": [0],
        "stage": "B", "signs": "gate3", "sign_ref": "gate3", "soft": None,
        "soft_stresses": None, "residual": "none", "train_mask": [[True]], "keep_wells": [True],
    }


def hand_score(params, seed):
    base = params["epochs"] / 1500 + params["lr"] - 0.1 * params["lam_shape"]
    # A lucky seed-0 maximum must lose to the lower-variance candidate in re-selection.
    return base if seed == 0 else 1 - base


def fake_train(seed, data, graph_data, well_graph_idx, **kwargs):
    assert graph_data == "fake graph" and well_graph_idx == [0]
    assert seed in (0, 1, 2)
    assert kwargs["device"] == "cpu"
    assert (kwargs["stage"], kwargs["signs"], kwargs["sign_ref"], kwargs["hidden"],
            kwargs["heads"], kwargs["n_layers"], kwargs["dropout"], kwargs["residual"],
            kwargs["weight_decay"], kwargs["kernel_weeks"], kwargs["bucket_smooth"]) == (
                "B", "gate3", "gate3", 32, 2, 2, 0.1, "none", 1e-4, 416, 0.0)
    assert kwargs["soft"] is None and kwargs["soft_stresses"] is None
    assert kwargs["lam_res"] is None
    assert kwargs["train_mask"] == [[True]] and kwargs["keep_wells"] == [True]
    assert kwargs["lam_gain"] < kwargs["lam_shape"]
    with (data["event_dir"] / f"fit_{os.getpid()}.jsonl").open("a") as handle:
        handle.write(json.dumps({"seed": seed, "kwargs": kwargs}) + "\n")
    time.sleep(0.01)  # Let all three workers reserve trials before the small fake fits finish.
    return object(), hand_score(kwargs, seed), kwargs["epochs"] + kwargs["epochs_b"], []


def records(folder):
    return [json.loads(line) for path in folder.glob("fit_*.jsonl")
            for line in path.read_text().splitlines()]


def no_test_score(*args, **kwargs):
    raise AssertionError("Tuning must never produce predictions or score the test period")


def test_guards():
    with (TemporaryDirectory() as directory,
          patch.object(T, "RESULTS_DIR", Path(directory)),
          patch.object(H, "prepare", side_effect=no_test_score),
          patch.object(H, "train_seed", side_effect=no_test_score)):
        for value in (None, "0", "true"):
            with patch.dict(os.environ):
                if value is None:
                    os.environ.pop(H.ALLOW_TRAIN_ENV, None)
                else:
                    os.environ[H.ALLOW_TRAIN_ENV] = value
                try:
                    T.main(["--arm", "D"])
                except SystemExit as exc:
                    assert "Refusing to train HybridGNN without PFE_ALLOW_TRAIN=1" in str(exc)
                else:
                    raise AssertionError("Missing training guard accepted")
        with patch.dict(os.environ, {H.ALLOW_TRAIN_ENV: "1"}):
            for arm in ("A", "B", "C", "D"):
                args = T.build_parser().parse_args(["--arm", arm])
                assert T.model_args(args).arm == arm
            for flag in ("--trials", "--workers"):
                try:
                    T.main(["--arm", "C", flag, "0"])
                except ValueError as exc:
                    assert "must be >= 1" in str(exc)
                else:
                    raise AssertionError(f"Invalid {flag} accepted")
        assert not list(Path(directory).iterdir())


def check_space(study):
    for trial in study.trials:
        p = trial.params
        assert set(p) == {"epochs", "epochs_b", "lr", "lam_shape", "r", "lam_delta"}
        assert isinstance(p["epochs"], int) and 300 <= p["epochs"] <= 1500
        assert isinstance(p["epochs_b"], int) and 0 <= p["epochs_b"] <= 400
        assert 0.003 <= p["lr"] <= 0.03
        assert 0.001 <= p["lam_shape"] <= 1
        assert 0.01 <= p["r"] <= 0.5
        assert 0.001 <= p["lam_delta"] <= 1
        assert 0 < T.with_gain(p)["lam_gain"] < p["lam_shape"]
        for name, distribution in trial.distributions.items():
            assert distribution.log == (name != "epochs_b")


def test_budget(workers, arm):
    with (TemporaryDirectory() as directory,
          patch.dict(os.environ, {H.ALLOW_TRAIN_ENV: "1", H.NO_SCORE_ENV: "1"}),
          patch.object(T, "RESULTS_DIR", Path(directory)),
          patch.object(H, "prepare", side_effect=partial(fake_prepare, event_dir=Path(directory))),
          patch.object(H, "train_seed", side_effect=fake_train),
          patch.object(H, "evaluate_run", side_effect=no_test_score),
          patch.object(H, "seed_outputs", side_effect=no_test_score),
          redirect_stdout(io.StringIO())):
        args = T.build_parser().parse_args(["--arm", arm, "--workers", str(workers)])
        best = T.run(args, context=mp.get_context("fork"))
        out = Path(directory) / f"hgnn_{arm}_tuning"
        study = T.open_study(out, arm)
        assert len(study.trials) == 24
        assert all(t.state == TrialState.COMPLETE for t in study.trials)
        check_space(study)
        assert len({tuple(sorted(t.params.items())) for t in study.trials}) == 24
        top = sorted(study.trials, key=lambda t: (-t.value, t.number))[:3]
        expected = min(top, key=lambda t: (hand_score(t.params, 0), t.number))
        assert best["trial"] == expected.number
        scores = {str(s): hand_score(expected.params, s) for s in (0, 1, 2)}
        assert best["scores"] == scores
        assert best["validation_median_nse_3seed"] == sum(scores.values()) / 3
        assert best["params"] == T.with_gain(expected.params)
        assert best["arm"] == arm and best["policy"] == "main" and best["dataset"] == "v5"
        assert best["n_trials"] == 24 and best["single_seed_best"] == study.best_value
        assert len(best["code_version"]["src_sha256"]) == 64
        assert "git_commit" in best["code_version"]
        assert best["config"]["seeds"] == [0, 1, 2]
        assert best["config"]["lam_gain"] == best["params"]["lam_gain"]
        assert json.loads((out / "best.json").read_text()) == best
        cache = json.loads((out / "reselect.json").read_text())
        assert set(cache) == {str(t.number) for t in top}
        calls = records(Path(directory))
        assert len(calls) == 30
        assert sum(c["seed"] == 0 for c in calls) == 24
        assert sum(c["seed"] == 1 for c in calls) == sum(c["seed"] == 2 for c in calls) == 3
        prepared = list(Path(directory).glob("prepare_*.txt"))
        assert len(prepared) == (1 if workers == 1 else workers + 1)
        assert all(p.read_text() == "prepare\n" for p in prepared)
        before = {p.name: p.read_bytes() for p in Path(directory).glob("*.jsonl")}
        resumed = T.run(args, context=mp.get_context("fork"))
        assert resumed == best
        assert len(T.open_study(out, arm).trials) == 24
        assert {p.name: p.read_bytes() for p in Path(directory).glob("*.jsonl")} == before
        assert all(p.read_text() == "prepare\n" for p in prepared)
        # The output path is per arm; refuse accidental reuse with a different policy.
        args.policy = "confident"
        try:
            T.run(args)
        except ValueError as exc:
            assert "different arm, policy, dataset or defaults" in str(exc)
        else:
            raise AssertionError("A different policy reused the old study")


def test_reselect_hand_computation():
    with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
        out = Path(directory)
        study = optuna.create_study(direction="maximize")
        for epochs in (1500, 1200, 900, 300):
            p = {"epochs": epochs, "epochs_b": 50, "lr": 0.01,
                 "lam_shape": 0.1, "r": 0.1, "lam_delta": 0.01}
            distributions = {
                "epochs": optuna.distributions.IntDistribution(300, 1500, log=True),
                "epochs_b": optuna.distributions.IntDistribution(0, 400),
                "lr": optuna.distributions.FloatDistribution(0.003, 0.03, log=True),
                "lam_shape": optuna.distributions.FloatDistribution(0.001, 1, log=True),
                "r": optuna.distributions.FloatDistribution(0.01, 0.5, log=True),
                "lam_delta": optuna.distributions.FloatDistribution(0.001, 1, log=True),
            }
            study.add_trial(optuna.trial.create_trial(
                params=p, distributions=distributions, value=hand_score(p, 0)))
        score = []

        def evaluate(p, seed):
            score.append((p["epochs"], seed))
            return hand_score(p, seed)

        trial, entry = T.reselect(study, evaluate, out)
        # Seed-0 values: 1, .8, .6, .2. Top-three means: 1/3, 1.2/3, 1.4/3.
        assert trial.number == 2 and abs(entry["mean"] - 1.4 / 3) < 1e-12
        assert score == [(1500, 1), (1500, 2), (1200, 1), (1200, 2), (900, 1), (900, 2)]
        T.reselect(study, evaluate, out)
        assert len(score) == 6
        cache = json.loads((out / "reselect.json").read_text())
        del cache["1"]["2"]
        T.write_json(out / "reselect.json", cache)
        T.reselect(study, evaluate, out)
        assert score[6:] == [(1200, 2)]


def test_interrupted_trial():
    with (TemporaryDirectory() as directory,
          patch.dict(os.environ, {H.ALLOW_TRAIN_ENV: "1"}),
          patch.object(T, "RESULTS_DIR", Path(directory)),
          patch.object(H, "prepare", side_effect=partial(fake_prepare, event_dir=Path(directory))),
          patch.object(H, "train_seed", side_effect=fake_train),
          redirect_stdout(io.StringIO())):
        out = Path(directory) / "hgnn_D_tuning"
        out.mkdir()
        study = T.open_study(out, "D")
        trial = study.ask()
        epochs = trial.suggest_int("epochs", 300, 1500, log=True)
        args = T.build_parser().parse_args(["--arm", "D", "--trials", "3", "--workers", "1"])
        T.run(args)
        resumed = T.open_study(out, "D")
        assert len(resumed.trials) == 3
        assert all(t.state == TrialState.COMPLETE for t in resumed.trials)
        assert resumed.trials[0].params["epochs"] == epochs
        assert len(records(Path(directory))) == 9


def failed_fit(*args, **kwargs):
    raise RuntimeError("fake fit failed")


def test_worker_failure():
    with (TemporaryDirectory() as directory,
          patch.dict(os.environ, {H.ALLOW_TRAIN_ENV: "1"}),
          patch.object(T, "RESULTS_DIR", Path(directory)),
          patch.object(H, "prepare", side_effect=partial(fake_prepare, event_dir=Path(directory))),
          patch.object(H, "train_seed", side_effect=failed_fit),
          redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())):
        args = T.build_parser().parse_args(["--arm", "D", "--trials", "3", "--workers", "3"])
        try:
            T.run(args, context=mp.get_context("fork"))
        except RuntimeError as exc:
            assert "tuning workers failed" in str(exc)
        else:
            raise AssertionError("Worker failure was hidden")
        assert not (Path(directory) / "hgnn_D_tuning" / "best.json").exists()


def spawn_fake_worker(args, out, connection):
    """Install fake preparation and fits inside a freshly spawned interpreter too."""
    optuna.logging.set_verbosity(optuna.logging.ERROR)
    with (patch.object(H, "prepare", side_effect=partial(fake_prepare, event_dir=out.parent)),
          patch.object(H, "train_seed", side_effect=fake_train),
          patch.object(H, "evaluate_run", side_effect=no_test_score),
          patch.object(H, "seed_outputs", side_effect=no_test_score),
          redirect_stdout(io.StringIO())):
        T.worker(args, out, connection)


def test_spawn_workers():
    """Exercise the production process start method without inheriting parent mocks."""
    with (TemporaryDirectory() as directory,
          patch.dict(os.environ, {H.ALLOW_TRAIN_ENV: "1"}),
          patch.object(T, "RESULTS_DIR", Path(directory)),
          patch.object(H, "prepare", side_effect=partial(fake_prepare, event_dir=Path(directory))),
          patch.object(H, "train_seed", side_effect=fake_train),
          patch.object(T, "worker", new=spawn_fake_worker),
          redirect_stdout(io.StringIO())):
        args = T.build_parser().parse_args(["--arm", "D", "--trials", "3", "--workers", "3"])
        best = T.run(args)
        assert best["n_trials"] == 3
        assert len(records(Path(directory))) == 9
        assert all(p.read_text() == "prepare\n" for p in Path(directory).glob("prepare_*.txt"))


def test_runner():
    subprocess.run(["bash", "-n", "scripts/run_v5_cpu.sh"], cwd=ROOT, check=True)
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        fake = folder / "fake_python"
        fake.write_text(f"#!{sys.executable}\n" + '''import json, os, sys, time
from pathlib import Path
folder = Path(os.environ["FAKE_EVENTS"])
if sys.argv[1:] == ["-"]:
    (folder / "prepare_check.py").write_text(sys.stdin.read())
    sys.exit(0)
arm = sys.argv[sys.argv.index("--arm") + 1]
record = {"argv": sys.argv[1:], "threads": os.environ.get("PFE_THREADS"),
          "allow": os.environ.get("PFE_ALLOW_TRAIN"), "dataset": os.environ.get("PFE_DATASET")}
(folder / (arm + ".json")).write_text(json.dumps(record))
deadline = time.monotonic() + 5
while len(list(folder.glob("*.json"))) < int(os.environ["FAKE_ARM_COUNT"]):
    if time.monotonic() > deadline:
        sys.exit(8)
    time.sleep(.01)
sys.exit(7 if arm == "D" else 0)
''')
        fake.chmod(0o755)
        env = os.environ | {"PY": str(fake), "STEPS": "hgnn_tune", "FAKE_EVENTS": directory,
                            "FAKE_ARM_COUNT": "4", "STATUS_FILE": str(folder / "status")}
        env.pop("HGNN_TUNE_ARMS", None)
        env.pop("HGNN_TUNE_WORKERS", None)
        result = subprocess.run(["bash", "scripts/run_v5_cpu.sh"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 1, result.stdout + result.stderr
        for arm in ("A", "B", "C"):
            assert f"hgnn_tune arm {arm}: passed" in result.stdout
        assert "hgnn_tune arm D: failed" in result.stdout
        assert (folder / "status").read_text() == "hgnn_tune\n"
        for arm in ("A", "B", "C", "D"):
            record = json.loads((folder / f"{arm}.json").read_text())
            assert record == {"argv": ["-m", "src.models.tune_hgnn", "--arm", arm, "--workers", "6"],
                              "threads": "1", "allow": "1", "dataset": "v5"}
        env.update(HGNN_TUNE_ARMS="C", HGNN_TUNE_WORKERS="3", FAKE_ARM_COUNT="1")
        result = subprocess.run(["bash", "scripts/run_v5_cpu.sh"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (folder / "status").read_text() == ""
        assert json.loads((folder / "C.json").read_text())["argv"][-1] == "3"
        env["STEPS"] = "prepare_check"
        result = subprocess.run(["bash", "scripts/run_v5_cpu.sh"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        prepared = []

        def prepare_arm(args):
            prepared.append(args.arm)
            return {"routed": {"pumping_record_start": "fake start"}}

        with patch.object(H, "prepare", side_effect=prepare_arm), redirect_stdout(io.StringIO()):
            exec(compile((folder / "prepare_check.py").read_text(), "prepare_check", "exec"), {})
        assert prepared == ["A", "B", "C", "D"]


if __name__ == "__main__":
    optuna.logging.set_verbosity(optuna.logging.ERROR)
    tests = [test_guards, partial(test_budget, 1, "A"), partial(test_budget, 3, "B"),
             partial(test_budget, 1, "C"), partial(test_budget, 3, "D"),
             test_reselect_hand_computation, test_interrupted_trial, test_worker_failure,
             test_spawn_workers, test_runner]
    for test in tests:
        started = time.perf_counter()
        test()
        name = test.func.__name__ + str(test.args) if isinstance(test, partial) else test.__name__
        print(f"  {name}: passed ({time.perf_counter() - started:.2f}s)")
    print("test_tune_hgnn: all checks passed; no model fitting")
