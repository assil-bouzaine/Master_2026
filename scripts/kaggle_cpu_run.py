"""Run the CPU baselines of dataset v4 as a Kaggle kernel (CPU only, no internet).

Pushed by scripts/kaggle_cpu.py (docs/gpu_howto.md, "Kaggle CPU"). On Kaggle it:
1. unpacks the code + data bundle (dataset <user>/pfe-v4-cpu-bundle, cpu_bundle.zip) into
   /tmp/pfe and restores the results of earlier pushes (state.zip), so that finished seeds
   and wells are skipped;
2. installs the pinned wheels (dataset <user>/pfe-wheels-cp313) offline into PIN_TARGET,
   placed first on PYTHONPATH, and stops if a version differs from requirements.txt or a
   baseline module does not import;
3. runs STEPS through scripts/run_v4_cpu.sh, one Pastas worker per CPU. The results are
   copied to /kaggle/working/results_cpu/v4 (= the kernel's output) every SYNC_S seconds and
   at the end. A step that would run past BUDGET_H is stopped, so the output is saved before
   Kaggle's 12 h session limit. Push again to continue.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

STEPS = os.environ.get("STEPS", "naive lgbm lgbm_final lgbm_regimes pastas wellmodel")
BUDGET_H = float(os.environ.get("BUDGET_H", 11.0))
SYNC_S = int(os.environ.get("SYNC_S", 600))
INPUT = Path(os.environ.get("KAGGLE_INPUT", "/kaggle/input"))
WORK = Path(os.environ.get("KAGGLE_WORK", "/kaggle/working"))
CODE = Path(os.environ.get("PFE_CODE", "/tmp/pfe"))
PINS = Path(os.environ.get("PIN_TARGET", "/tmp/pins"))
RESULTS = CODE / "results" / "v4"
OUT = WORK / "results_cpu" / "v4"
LOG = WORK / "run_kaggle_cpu.log"
STATE = Path(os.environ.get("PFE_STATE", "/tmp/pfe_state"))   # earlier results, kept out of the output
T0 = time.time()                                             # reset after restore(): see save()
DEADLINE = time.time() + BUDGET_H * 3600
CHECKED = ["numpy", "pandas", "pyarrow", "scipy", "lightgbm", "pastas", "numba", "llvmlite",
           "matplotlib", "geopandas", "shapely", "pyproj"]    # import names = pin names


def log(msg):
    line = f"== {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def unpack():
    """The bundle as uploaded (cpu_bundle.zip) or as extracted by Kaggle -> CODE."""
    zips = sorted(INPUT.rglob("cpu_bundle.zip"))
    if zips:
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(CODE)
    else:
        trees = [p.parents[1] for p in INPUT.rglob("scripts/run_v4_cpu.sh")]
        if not trees:
            sys.exit(f"no bundle under {INPUT}")
        shutil.copytree(trees[0], CODE, dirs_exist_ok=True)
    log(f"code and data in {CODE}")


def restore():
    """Results of earlier pushes (state.zip, or its extracted results_cpu/v4) -> RESULTS. They are
    unpacked outside the output folder (since 2026-11-10): a session's output holds only the runs it
    touched (save()), so a pull no longer downloads every earlier run again (1,400 files, 90 min)."""
    for z in INPUT.rglob("state.zip"):
        with zipfile.ZipFile(z) as f:
            f.extractall(STATE)
    for d in [STATE / "results_cpu" / "v4", *INPUT.rglob("results_cpu/v4")]:
        if d.is_dir() and any(d.iterdir()):
            shutil.copytree(d, RESULTS, dirs_exist_ok=True)
            log(f"restored earlier results from {d}")


def pythonpath():
    return os.pathsep.join(filter(None, [str(PINS), os.environ.get("PYTHONPATH")]))


def install():
    """Pinned wheels -> PINS (no index: the session has no internet); versions checked."""
    wheels = sorted({w.name: w for w in INPUT.rglob("*.whl")}.values())
    if not wheels:
        sys.exit(f"no wheels under {INPUT}: attach the dataset made by kaggle_cpu.py wheels")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-index", "--no-deps",
                        "--upgrade", "--target", str(PINS), *map(str, wheels)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"pip install failed:\n{r.stdout}{r.stderr}")
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", (CODE / "requirements.txt")
                           .read_text(), flags=re.M))
    code = "import importlib; " + "; ".join(
        f"print('{m}==' + importlib.import_module('{m}').__version__)" for m in CHECKED)
    code += "; import src.models.naive, src.models.lgbm, src.models.pastas_baseline"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=CODE,
                       env=dict(os.environ, PYTHONPATH=pythonpath(), PFE_DATASET="v4"))
    got = dict(re.findall(r"^(\w+)==(\S+)$", r.stdout, flags=re.M))
    bad = [f"{m} {got.get(m, 'missing')} (pin {pins.get(m)})" for m in CHECKED
           if got.get(m) != pins.get(m)]
    if r.returncode or bad:
        sys.exit(f"pinned versions not in use: {', '.join(bad)}\n{r.stderr}")
    log(f"{len(wheels)} wheels installed; versions = requirements.txt for {', '.join(CHECKED)}")


def ealstm_ok(env):
    """EA-LSTM steps need torch (the image's: it is not among the pinned wheels) and the
    fused-kernel check tests/test_ealstm.py, as on Colab."""
    r = subprocess.run([sys.executable, "-c", "import torch; print(torch.__version__)"],
                       capture_output=True, text=True, cwd=CODE, env=env)
    if r.returncode:
        log(f"no torch in this image: EA-LSTM steps dropped\n{r.stderr[-500:]}")
        return False
    t = subprocess.run([sys.executable, "-m", "tests.test_ealstm"], capture_output=True,
                       text=True, cwd=CODE, env=env)
    print(t.stdout + t.stderr, flush=True)
    log(f"torch {r.stdout.strip()}; tests/test_ealstm.py "
        + ("passed" if t.returncode == 0 else "FAILED: EA-LSTM steps dropped"))
    return t.returncode == 0


def save():
    """The runs of RESULTS with a file written since the session started -> OUT (not the feature
    caches, which are in the bundle, nor the restored runs this session did not touch)."""
    for d in sorted(p for p in RESULTS.iterdir() if p.is_dir() and p.name != "_cache"):
        if any(f.stat().st_mtime > T0 for f in d.rglob("*") if f.is_file()):
            shutil.copytree(d, OUT / d.name, dirs_exist_ok=True)
    for f in RESULTS.glob("*.*"):
        if f.is_file() and f.stat().st_mtime > T0:
            shutil.copy2(f, OUT / f.name)


def sync_loop(stop):
    while not stop.wait(SYNC_S):
        try:
            save()
        except Exception as e:           # a file being written: try again at the next round
            print(f"   [copy to the output failed: {e}]", flush=True)


def run(steps, env):
    """run_v4_cpu.sh in its own process group, output to stdout and LOG; stopped at DEADLINE."""
    p = subprocess.Popen(["bash", "scripts/run_v4_cpu.sh"], cwd=CODE, env=dict(env, STEPS=steps),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    timer = threading.Timer(max(DEADLINE - time.time(), 0), os.killpg, (p.pid, signal.SIGTERM))
    timer.start()
    with LOG.open("a") as f:
        for line in p.stdout:
            print(line, end="", flush=True)
            f.write(line)
    timer.cancel()
    return p.wait()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    global T0
    unpack()
    restore()
    T0 = time.time()
    install()
    env = dict(os.environ, PY=sys.executable, PYTHONPATH=pythonpath(), PYTHONIOENCODING="utf-8",
               PYTHONUNBUFFERED="1", JOBS=str(len(os.sched_getaffinity(0))))
    steps = STEPS
    if "ealstm" in steps and not ealstm_ok(env):
        # "none", not "": an empty STEPS would make run_v4_cpu.sh run its default steps
        steps = " ".join(s for s in steps.split() if "ealstm" not in s) or "none"
    log(f"{env['JOBS']} CPUs; steps {steps}; budget {BUDGET_H} h")
    stop = threading.Event()
    threading.Thread(target=sync_loop, args=(stop,), daemon=True).start()
    try:
        rc = run(steps, env)
        log(f"steps ended (exit {rc})" if time.time() < DEADLINE
            else "time budget used: push again to continue")
    finally:
        stop.set()
        save()
        log(f"results saved to {OUT}")


if __name__ == "__main__":
    main()
