"""Run GPU steps of a sweep in a Google Colab notebook (free T4); results kept on Drive.

Dataset: PFE_DATASET (default v3). For the dataset v4 re-runs (analysis plan v2 §5) set
%env PFE_DATASET=v4 before the run line: STEPS then defaults to V4_STEPS (the final seeds of
every neural baseline first, then their regimes, then Chronos-2; docs/gpu_howto.md). The
bundle must have been made with PFE_DATASET=v4.

Notebook cells (runtime type T4 GPU; docs/gpu_howto.md, Colab section):
    from google.colab import drive; drive.mount('/content/drive')       # Assil clicks Allow
    !unzip -oq /content/drive/MyDrive/pfe_colab/gpu_bundle.zip -d /content/pfe && python /content/pfe/scripts/colab_run.py

It:
1. stops at once if the session has no GPU (CPU runtime, or the free GPU quota is used up);
2. restores the results saved on Drive (DRIVE/results_gpu) to local disk, so that finished
   seeds, trials and folds are skipped;
3. installs the pinned packages (scripts/run_gpu.sh with PIN_TARGET: Colab keeps its CUDA
   torch) and runs tests/test_taccari.py as an import and equality check; when STEPS has
   EA-LSTM steps, also tests/test_ealstm.py (the fused cuDNN path against the explicit loop;
   the EA-LSTM steps are dropped if it fails);
4. runs STEPS through scripts/run_gpu.sh and copies the results to Drive every SYNC_S seconds
   and at the end. The runs work on local disk because SQLite (the Optuna studies) is not
   safe on the Drive mount; databases are copied with SQLite's backup API, so a copy is
   never caught in the middle of a write.
Free sessions stop without warning: mount Drive again and re-run the same line to resume
(only the run in progress and the last SYNC_S seconds are lost).

    python scripts/colab_run.py zip     # Drive copy -> /content/results_colab.zip (no _cache);
                                        # files.download it, then scripts/colab_pull.py
"""
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from contextlib import closing
from pathlib import Path

DATASET = os.environ.get("PFE_DATASET", "v3")
V4_STEPS = ("final:lstm final:stgnn final:taccari final:ealstm regimes:lstm regimes:stgnn "
            "regimes:taccari regimes:ealstm chronos2 chronos2_xl chronos2_ft")
STEPS = os.environ.get("STEPS", V4_STEPS if DATASET == "v4"
                       else "taccari tune:taccari regimes:taccari")
DRIVE = Path(os.environ.get("PFE_DRIVE", "/content/drive/MyDrive/pfe_colab"))
CODE = Path(__file__).resolve().parents[1]
LOCAL = CODE / "results_gpu"              # results_gpu/<v>/<run> and results_gpu/run_colab.log
SAVED = DRIVE / "results_gpu"
LOG = LOCAL / "run_colab.log"
PINS = os.environ.get("PIN_TARGET", "/content/pins")   # pinned packages (scripts/run_gpu.sh)
SYNC_S = int(os.environ.get("SYNC_S", 300))
ZIP = Path(os.environ.get("PFE_ZIP", "/content/results_colab.zip"))
EPOCH = re.compile(r" epoch +(\d+)")


def log(msg):
    line = f"== {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def copy_new(src, dst, live=False):
    """Copy the files of src that are missing or changed in dst; returns how many. live: src
    is being written (databases through the backup API; feature caches are not copied)."""
    n = 0
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if (not f.is_file() or f.name.endswith(("-journal", "-wal", "-shm"))
                or (live and "_cache" in rel.parts)):
            continue
        t = dst / rel
        s = f.stat()
        if t.exists() and t.stat().st_size == s.st_size and t.stat().st_mtime >= s.st_mtime:
            continue
        t.parent.mkdir(parents=True, exist_ok=True)
        if live and f.suffix == ".db":
            tmp = Path("/tmp") / f"{f.name}.{os.getpid()}.bak"
            with closing(sqlite3.connect(f)) as a, closing(sqlite3.connect(tmp)) as b:
                a.backup(b)
            shutil.copyfile(tmp, t)
            tmp.unlink()
        else:
            shutil.copy2(f, t)
        n += 1
    return n


def run(cmd, env):
    """Run cmd in its own process group. LOG gets the whole output, the notebook a short
    version: of the per-epoch lines only the first of each seed (it shows the epoch time)."""
    p = subprocess.Popen(cmd, cwd=CODE, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        with LOG.open("a") as f:
            for line in p.stdout:
                f.write(line)
                f.flush()
                m = EPOCH.search(line)
                if not m or m.group(1) == "1":
                    print(line, end="", flush=True)
        return p.wait()
    except KeyboardInterrupt:              # "interrupt execution" in Colab: stop the sweep too
        os.killpg(p.pid, signal.SIGTERM)
        p.wait()
        raise


def sync_loop(stop):
    while not stop.wait(SYNC_S):
        try:
            n = copy_new(LOCAL, SAVED, live=True)
            if n:
                print(f"   [{time.strftime('%H:%M', time.gmtime())} UTC: {n} files saved to "
                      f"Drive]", flush=True)
        except Exception as e:             # a Drive hiccup: try again at the next round
            print(f"   [copy to Drive failed: {e}]", flush=True)


def gpu():
    if not shutil.which("nvidia-smi"):
        return ""
    r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def make_zip():
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SAVED.rglob("*")):
            if (f.is_file() and "_cache" not in f.parts
                    and not f.name.endswith(("-journal", "-wal", "-shm"))):
                z.write(f, f.relative_to(SAVED.parent))
    print(f"{ZIP}: {ZIP.stat().st_size / 1e6:.1f} MB. Download it with: "
          f"from google.colab import files; files.download('{ZIP}')")


def main():
    if not DRIVE.parent.exists():
        sys.exit("Google Drive is not mounted: run drive.mount('/content/drive') first")
    if sys.argv[1:] == ["zip"]:
        return make_zip()
    name = gpu()
    if not name and os.environ.get("REQUIRE_GPU", "1") == "1":
        sys.exit("no GPU in this session: Runtime > Change runtime type > T4 GPU. If T4 is "
                 "already selected, the free GPU quota is used up for now: try again later")
    LOCAL.mkdir(parents=True, exist_ok=True)
    restored = copy_new(SAVED, LOCAL) if SAVED.exists() else 0
    env = dict(os.environ, PFE_DATASET=DATASET, PFE_RESULTS=str(LOCAL / DATASET),
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PIN_TARGET=PINS,
               PFE_THREADS=os.environ.get("PFE_THREADS", "2"))
    log(f"GPU {name or 'none'}; {restored} files restored from Drive; steps {STEPS}; "
        f"saved to {SAVED} every {SYNC_S} s")
    run(["bash", "scripts/run_gpu.sh"], dict(env, STEPS="setup"))         # pinned packages
    test_env = dict(env, PYTHONPATH=os.pathsep.join(filter(None, [PINS, env.get("PYTHONPATH")])))
    if run(["python3", "-m", "tests.test_taccari"], test_env) != 0:
        sys.exit("tests/test_taccari.py failed in this session (output above): stopping")
    steps = STEPS
    if "ealstm" in steps and run(["python3", "-m", "tests.test_ealstm"], test_env) != 0:
        # "none", not "": an empty STEPS would make run_gpu.sh run its default sweep
        steps = " ".join(s for s in steps.split() if "ealstm" not in s) or "none"
        log("tests/test_ealstm.py failed in this session (output above): EA-LSTM steps dropped")
    stop = threading.Event()
    threading.Thread(target=sync_loop, args=(stop,), daemon=True).start()
    try:
        run(["bash", "scripts/run_gpu.sh"], dict(env, STEPS=steps, SKIP_PIP="1"))
    finally:
        stop.set()
        log(f"{copy_new(LOCAL, SAVED, live=True)} files saved to {SAVED}")
        copy_new(LOCAL, SAVED, live=True)         # the log line above


if __name__ == "__main__":
    main()
