"""Run dataset-selected CPU steps on Kaggle or Colab (analysis plans v2 §5 and v3 §3).

PFE_DATASET selects the dispatcher, results and resume paths; unset means v4.
The v5 path installs and checks PyG on Colab for the Hybrid-GNN smoke run.

Pushed by scripts/kaggle_cpu.py (docs/gpu_howto.md, "Kaggle CPU"). On Kaggle it:
1. unpacks the code + data bundle (dataset <user>/pfe-v4-cpu-bundle, cpu_bundle.zip) into
   /tmp/pfe and restores the results of earlier pushes (state.zip), so that finished seeds
   and wells are skipped;
2. installs the pinned wheels (dataset <user>/pfe-wheels-cp313) offline into PIN_TARGET,
   placed first on PYTHONPATH, and stops if a version differs from requirements.txt or a
   baseline module does not import;
3. runs STEPS through scripts/run_v4_cpu.sh with any staged environment overrides and one
   Pastas worker per CPU. The results are
   copied to /kaggle/working/results_cpu/v4 (= the kernel's output) every SYNC_S seconds and
   at the end. A step that would run past BUDGET_H is stopped, so the output is saved before
   Kaggle's 12 h session limit. Push again to continue.

On Colab, scripts/colab_cpu.py points the runner at Drive and sets PIP_ONLINE=1. The
runner installs from PyPI and restores the last files saved to Drive before it starts.

After dispatch, the kernel exits successfully even if steps failed. Kaggle may only keep the
results of a successful kernel, and its output is the only copy of the session's work. The
local pull reads run_status.json and reports step failures after retrieving that work.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

KERNEL_ENV = {}
DATASET = os.environ.get("PFE_DATASET", "v4")
DISPATCHER = f"scripts/run_{DATASET}_cpu.sh"
STEPS = os.environ.get("STEPS", "naive lgbm lgbm_final lgbm_regimes pastas wellmodel")
BUDGET_H = float(os.environ.get("BUDGET_H", 11.0))
SYNC_S = int(os.environ.get("SYNC_S", 600))
INPUT = Path(os.environ.get("KAGGLE_INPUT", "/kaggle/input"))
WORK = Path(os.environ.get("KAGGLE_WORK", "/kaggle/working"))
CODE = Path(os.environ.get("PFE_CODE", "/tmp/pfe"))
PINS = Path(os.environ.get("PIN_TARGET", "/tmp/pins"))
RESULTS = CODE / "results" / DATASET
OUT = WORK / "results_cpu" / DATASET
LOG = WORK / "run_kaggle_cpu.log"
STATE = Path(os.environ.get("PFE_STATE", "/tmp/pfe_state"))   # earlier results, kept out of the output
T0 = time.time()                                             # reset after restore(): see save()
DEADLINE = time.time() + BUDGET_H * 3600
CHECKED = ["numpy", "pandas", "pyarrow", "scipy", "lightgbm", "pastas", "numba", "llvmlite",
           "matplotlib", "geopandas", "shapely", "pyproj", "rdflib", "pyoxigraph",
           "requests"]    # import names = pin names
# Same list as scripts/kaggle_cpu.py. Kaggle runs this file on its own.
PINNED = ["numpy", "pandas", "pyarrow", "scipy", "lightgbm", "narwhals", "pastas", "numba",
          "llvmlite", "matplotlib", "contourpy", "cycler", "fonttools", "kiwisolver", "pillow",
          "pyparsing", "packaging", "python-dateutil", "six", "pytz", "tzdata", "geopandas",
          "pyogrio", "shapely", "pyproj", "certifi", "charset-normalizer", "tqdm",
          "rdflib", "pyoxigraph", "requests", "idna", "urllib3"]


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
        trees = [p.parents[1] for p in INPUT.rglob(DISPATCHER)]
        if not trees:
            sys.exit(f"no bundle under {INPUT}")
        shutil.copytree(trees[0], CODE, dirs_exist_ok=True)
    log(f"code and data in {CODE}")


def restore():
    """Restore state.zip, then extracted inputs, then newer results saved to the work folder."""
    for z in INPUT.rglob("state.zip"):
        with zipfile.ZipFile(z) as f:
            f.extractall(STATE)
    for d in [STATE / "results_cpu" / DATASET, *INPUT.rglob(f"results_cpu/{DATASET}"),
              WORK / "results_cpu" / DATASET]:
        if d.is_dir() and any(d.iterdir()):
            shutil.copytree(d, RESULTS, dirs_exist_ok=True)
            log(f"restored earlier results from {d}")


def pythonpath():
    return os.pathsep.join(filter(None, [str(PINS), os.environ.get("PYTHONPATH")]))


def shell_env(status_file):
    """Apply the staged overrides to the dispatcher and set its runner-controlled values."""
    env = {**os.environ, **KERNEL_ENV}
    return dict(env, PFE_DATASET=DATASET, PY=sys.executable, PYTHONPATH=pythonpath(), PYTHONIOENCODING="utf-8",
                PYTHONUNBUFFERED="1", JOBS=str(len(os.sched_getaffinity(0))), STATUS_FILE=str(status_file))


def read_pins():
    return dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", (CODE / "requirements.txt")
                           .read_text(), flags=re.M))


def install():
    """Install into PINS from the attached wheels or from PyPI and check the versions."""
    online = os.environ.get("PIP_ONLINE") == "1"
    if online:
        pins = read_pins()
        packages = [f"{name}=={pins[name]}" for name in PINNED if name in pins]
        if DATASET == "v5":
            # Colab supplies torch. Install PyG and its dependencies for the v3 parameter encoder.
            packages.append(f"torch_geometric=={pins['torch_geometric']}")
        options = ["--target", str(PINS), "--upgrade", *packages]
        installed = f"{len(packages)} PyPI packages"
    else:
        wheels = sorted({w.name: w for w in INPUT.rglob("*.whl")}.values())
        if not wheels:
            sys.exit(f"no wheels under {INPUT}: attach the dataset made by kaggle_cpu.py wheels")
        options = ["-q", "--no-index", "--no-deps", "--upgrade", "--target", str(PINS), *map(str, wheels)]
        installed = f"{len(wheels)} wheels"
    r = subprocess.run([sys.executable, "-m", "pip", "install", *options], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"pip install failed:\n{r.stdout}{r.stderr}")
    if not online:
        pins = read_pins()
    code = "import importlib; " + "; ".join(
        f"print('{m}==' + importlib.import_module('{m}').__version__)" for m in CHECKED)
    code += "; import src.models.naive, src.models.lgbm, src.models.pastas_baseline"
    if DATASET == "v5":
        code += "; import torch, torch_geometric, src.models.hybrid_gnn; print('torch_geometric==' + torch_geometric.__version__)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=CODE,
                       env=dict(os.environ, PYTHONPATH=pythonpath(), PFE_DATASET=DATASET))
    got = dict(re.findall(r"^(\w+)==(\S+)$", r.stdout, flags=re.M))
    bad = [f"{m} {got.get(m, 'missing')} (pin {pins.get(m)})" for m in CHECKED
           if got.get(m) != pins.get(m)]
    if DATASET == "v5" and got.get("torch_geometric") != pins["torch_geometric"]:
        bad.append(f"torch_geometric {got.get('torch_geometric', 'missing')} (pin {pins['torch_geometric']})")
    if r.returncode or bad:
        sys.exit(f"pinned versions not in use: {', '.join(bad)}\n{r.stderr}")
    log(f"{installed} installed; versions = requirements.txt for {', '.join(CHECKED)}")


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
    """Run the dataset's dispatcher in its own process group; stop at DEADLINE."""
    p = subprocess.Popen(["bash", DISPATCHER], cwd=CODE, env=dict(env, STEPS=steps),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    budget_stop = threading.Event()

    def end_session():
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:  # the process group already finished
            return
        budget_stop.set()

    timer = threading.Timer(max(DEADLINE - time.time(), 0), end_session)
    timer.start()
    try:
        with LOG.open("a") as f, p.stdout:
            for line in p.stdout:
                print(line, end="", flush=True)
                f.write(line)
        rc = p.wait()
    finally:
        timer.cancel()
        timer.join()
    return rc, budget_stop.is_set()


def write_run_status(path, status_file, rc, budget_stop, steps, skipped=()):
    """Save the dispatcher result so pull can report it after copying the session's work."""
    failed_steps = status_file.read_text().splitlines() if status_file.is_file() else []
    status = {"exit": rc, "budget_stop": budget_stop, "failed_steps": [*failed_steps, *skipped],
              "steps": steps, "env": KERNEL_ENV,
              "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(status, indent=2) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    global T0
    if KERNEL_ENV:
        log(f"kernel environment overrides: {json.dumps(KERNEL_ENV)}")
    unpack()
    restore()
    T0 = time.time()
    install()
    status_file = (CODE / "failed_steps.txt").resolve()
    status_file.unlink(missing_ok=True)
    env = shell_env(status_file)
    steps = STEPS
    skipped = []
    if "ealstm" in steps and not ealstm_ok(env):
        skipped = [s for s in steps.split() if "ealstm" in s]
        steps = " ".join(s for s in steps.split() if s not in skipped)
    log(f"{env['JOBS']} CPUs; steps {steps}; budget {BUDGET_H} h")
    stop = threading.Event()
    sync = threading.Thread(target=sync_loop, args=(stop,), daemon=True)
    sync.start()
    try:
        if skipped and not steps:
            rc, budget_stop = 0, False
        else:
            rc, budget_stop = run(steps, env)
        log("time budget used: push again to continue" if budget_stop
            else f"steps ended (exit {rc})")
    finally:
        stop.set()
        sync.join()
        save()
        log(f"results saved to {OUT}")
    write_run_status(WORK / "run_status.json", status_file, rc, budget_stop, STEPS, skipped)


if __name__ == "__main__":
    main()
