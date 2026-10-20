"""Run GPU steps of the v3 sweep as a Kaggle kernel (runs in the background, laptop may be off).

Pushed by scripts/kaggle_gpu.py (docs/gpu_howto.md, Kaggle section). On Kaggle it:
1. unpacks the code + data bundle (dataset <user>/pfe-v3-bundle, made by make_gpu_bundle.py)
   into /tmp/pfe, and restores earlier Kaggle results shipped with it (state.zip), so that
   finished seeds, trials and folds are skipped;
2. checks the EA-LSTM cuDNN path against the explicit loop (tests/test_ealstm.py); if the
   check fails, the EA-LSTM steps are dropped;
3. runs the step chains (STEPS, chains separated by "|") through scripts/run_gpu.sh, one GPU
   per chain when there are enough GPUs (Kaggle "T4 x2"), else one after the other; results
   go to /kaggle/working/results_gpu/v3 (= the kernel's output). A step that would run past
   BUDGET_H is stopped, so the outputs are saved before Kaggle's 12 h session limit. Push
   again to continue.
"""
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

DEFAULT_STEPS = "tune:ealstm regimes:ealstm taccari | tune:taccari regimes:taccari"
CHAINS = [c.split() for c in os.environ.get("STEPS", DEFAULT_STEPS).split("|") if c.split()]
BUDGET_H = float(os.environ.get("BUDGET_H", 11.0))
INPUT = Path(os.environ.get("KAGGLE_INPUT", "/kaggle/input"))
WORK = Path(os.environ.get("KAGGLE_WORK", "/kaggle/working"))
CODE = Path(os.environ.get("PFE_CODE", "/tmp/pfe"))
PINS = os.environ.get("PIN_TARGET", "/tmp/pins")   # pinned packages (scripts/run_gpu.sh)
OUT = WORK / "results_gpu" / "v3"
LOG = WORK / "run_kaggle.log"
DEADLINE = time.time() + BUDGET_H * 3600


def log(msg):
    line = f"== {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def unpack():
    """The bundle as uploaded (gpu_bundle.zip) or as extracted by Kaggle -> CODE."""
    zips = sorted(INPUT.rglob("gpu_bundle.zip"))
    if zips:
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(CODE)
    else:
        trees = [p.parents[1] for p in INPUT.rglob("scripts/run_gpu.sh")]
        if not trees:
            sys.exit(f"no bundle under {INPUT}")
        shutil.copytree(trees[0], CODE, dirs_exist_ok=True)
    log(f"code and data in {CODE}")


def restore():
    """Earlier Kaggle results (state.zip, or its extracted results_gpu/v3) -> OUT."""
    for z in INPUT.rglob("state.zip"):
        with zipfile.ZipFile(z) as f:
            f.extractall(WORK)
        log(f"restored earlier results from {z}")
    for d in INPUT.rglob("results_gpu/v3"):
        if d.is_dir():
            shutil.copytree(d, OUT, dirs_exist_ok=True)
            log(f"restored earlier results from {d}")


def run(cmd, env, budget_s, tag=""):
    """Run cmd in its own process group, output to stdout and LOG; stop it after budget_s."""
    p = subprocess.Popen(cmd, cwd=CODE, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    timer = threading.Timer(budget_s, os.killpg, (p.pid, signal.SIGTERM))
    timer.start()
    with LOG.open("a") as f:
        for line in p.stdout:
            print(tag + line, end="", flush=True)
            f.write(tag + line)
    timer.cancel()
    return p.wait()


def chain(steps, env, tag):
    for s in steps:
        left = DEADLINE - time.time()
        if left < 600:
            log(f"{tag}time budget used: stopping before {s} (push again to continue)")
            return
        log(f"{tag}step {s} ({left / 3600:.1f} h left)")
        run(["bash", "scripts/run_gpu.sh"], dict(env, STEPS=s), left, tag)


def gpus():
    if not shutil.which("nvidia-smi"):
        return 0
    return subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.count("GPU ")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n_gpu = gpus()
    if n_gpu == 0 and os.environ.get("REQUIRE_GPU", "1") == "1":
        log("no GPU in this session (Kaggle gives none to accounts without phone "
            "verification): stopping")
        return
    unpack()
    restore()
    env = dict(os.environ, PFE_DATASET="v3", PFE_RESULTS=str(OUT), PYTHONIOENCODING="utf-8",
               PYTHONUNBUFFERED="1", PIN_TARGET=PINS)
    log(f"{n_gpu} GPU(s); steps {' | '.join(' '.join(c) for c in CHAINS)}; budget {BUDGET_H} h")
    run(["bash", "scripts/run_gpu.sh"], dict(env, STEPS="setup"), 1800)   # pinned packages
    chains = CHAINS
    test_env = dict(env, PYTHONPATH=os.pathsep.join(filter(None, [PINS, env.get("PYTHONPATH")])))
    if run(["python3", "-m", "tests.test_ealstm"], test_env, 900) != 0:
        chains = [[s for s in c if "ealstm" not in s] for c in chains]
        log("EA-LSTM GPU check failed: EA-LSTM steps dropped")
    env["SKIP_PIP"] = "1"
    if n_gpu >= len(chains) > 1:
        log(f"{len(chains)} chains in parallel, one GPU each")
        threads = [threading.Thread(target=chain, args=(c, dict(env, CUDA_VISIBLE_DEVICES=str(i)),
                                                        f"[gpu{i}] "))
                   for i, c in enumerate(chains)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        chain([s for c in chains for s in c], env, "")
    log("end")


if __name__ == "__main__":
    main()
