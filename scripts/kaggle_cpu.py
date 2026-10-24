"""Run the CPU baselines of dataset v4 on Kaggle from the laptop (docs/gpu_howto.md, Kaggle CPU).

    .venv/bin/python scripts/kaggle_cpu.py wheels     # once: pinned wheels -> private dataset
    .venv/bin/python scripts/kaggle_cpu.py push [--steps "lgbm_final pastas"]
    .venv/bin/python scripts/kaggle_cpu.py kernel     # push the staged kernel again, same bundle
    .venv/bin/python scripts/kaggle_cpu.py status | log
    .venv/bin/python scripts/kaggle_cpu.py pull       # -> results/v4/<run>, rescored

Kaggle without phone verification (Assil's account) runs kernels on CPU only and without
internet. Checked on 2026-10-24 with a probe kernel: Python 3.13, 4 CPUs, 32 GB RAM, no GPU,
no name resolution, pastas not installed and the other packages at other versions than
requirements.txt. Hence:
wheels: downloads the wheels of the pinned packages that the CPU baselines import (cp313,
  manylinux x86_64; `uvx pip download`, the venv has no pip) into results/_kaggle_cpu/wheels
  and uploads them as the private dataset <user>/pfe-wheels-cp313.
push: packs code, dataset v4, the daily SAFRAN files (Pastas), the cached feature panels and
  the configurations selected on v3 (scripts/v4_from_v3.py) into cpu_bundle.zip, with the
  last pulled output as state.zip (resume), as the private dataset <user>/pfe-v4-cpu-bundle;
  waits until Kaggle has processed it; then pushes scripts/kaggle_cpu_run.py as the private
  kernel <user>/pfe-v4-cpu (CPU, internet off). Kaggle starts it at once and it runs
  without the laptop. The push then watches the start: on 2026-10-24 kernel version 3, pushed
  16 s after a new bundle version, ended in ERROR with an empty log and no output (it never
  ran; the same kernel pushed again 2 h later ran). `datasets status` answers "ready" for
  the dataset while its new version may still be processed, so a new version now gets
  VERSION_GRACE_S before the kernel is pushed, and a kernel that fails in its first minutes
  with an empty log is pushed once more.
kernel: pushes the kernel staged by the last push (results/_kaggle_cpu/kernel) again, when
  the bundle on Kaggle is still current; same start watch.
pull: downloads the kernel output to results/_kaggle_cpu/output, copies every finished run
  (predictions.parquet present) to results/v4/<run> and rescores it with src.models.evaluate.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KAGGLE = str(Path(sys.executable).parent / "kaggle")
STAGE = ROOT / "results" / "_kaggle_cpu"              # results/ is gitignored
OUTPUT = STAGE / "output"
V4 = ROOT / "results" / "v4"
BUNDLE, WHEELS, KERNEL = "pfe-v4-cpu-bundle", "pfe-wheels-cp313", "pfe-v4-cpu"
VERSION_GRACE_S = 120      # after "ready": time for Kaggle to unpack a new dataset version
WATCH_S, WATCH_STEP_S = 360, 30   # how long the start of a pushed kernel is watched
DEFAULT_STEPS = "naive lgbm lgbm_final lgbm_regimes pastas wellmodel"
# pinned distributions imported by naive, LightGBM, Pastas and the evaluation (checked with an
# import trace), with their runtime dependencies; versions come from requirements.txt
PINNED = ["numpy", "pandas", "pyarrow", "scipy", "lightgbm", "narwhals", "pastas", "numba",
          "llvmlite", "matplotlib", "contourpy", "cycler", "fonttools", "kiwisolver", "pillow",
          "pyparsing", "packaging", "python-dateutil", "six", "pytz", "tzdata", "geopandas",
          "pyogrio", "shapely", "pyproj", "certifi", "charset-normalizer", "tqdm"]
PLATFORMS = ["manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_27_x86_64",
             "manylinux_2_28_x86_64", "manylinux_2_34_x86_64"]


def kg(*args, check=True):
    r = subprocess.run([KAGGLE, "-W", *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"kaggle {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def user():
    m = re.search(r"username:\s*(\S+)", kg("config", "view", check=False))
    if not m:
        sys.exit("no Kaggle username: log in first with .venv/bin/kaggle auth login")
    return m.group(1)


def upload(folder, slug):
    """folder -> private dataset <user>/<slug> (a new version if it exists); waits until ready."""
    u = user()
    (folder / "dataset-metadata.json").write_text(json.dumps(
        {"title": slug, "id": f"{u}/{slug}", "licenses": [{"name": "other"}]}, indent=1))
    new_version = "ready" in kg("datasets", "status", f"{u}/{slug}", check=False)
    if new_version:
        kg("datasets", "version", "-p", str(folder), "-m", time.strftime("%Y-%m-%d %H:%M"), "-t")
    else:
        kg("datasets", "create", "-p", str(folder), "-t")
    for _ in range(90):                                # Kaggle processes the upload first
        time.sleep(10)
        if "ready" in kg("datasets", "status", f"{u}/{slug}", check=False):
            if new_version:              # "ready" may still describe the previous version
                time.sleep(VERSION_GRACE_S)
            print(f"dataset {u}/{slug} ready")
            return
    sys.exit(f"dataset {slug} not ready after 15 min; run the command again later")


def download_wheels():
    """The PINNED wheels for Kaggle's Python -> results/_kaggle_cpu/wheels (kept if complete)."""
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", (ROOT / "requirements.txt")
                           .read_text(), flags=re.M))
    wd = STAGE / "wheels"
    if len(list(wd.glob("*.whl"))) != len(PINNED):
        shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True)
        plat = [a for p in PLATFORMS for a in ("--platform", p)]
        subprocess.run(["uvx", "pip", "download", "-q", "--no-deps", "--only-binary=:all:",
                        "--python-version", "3.13", "--implementation", "cp", "--abi", "cp313",
                        *plat, "-d", str(wd), *[f"{d}=={pins[d]}" for d in PINNED]], check=True)
    got = sorted(p.name for p in wd.glob("*.whl"))
    print(f"{len(got)} wheels, {sum(p.stat().st_size for p in wd.glob('*.whl')) / 1e6:.0f} MB")
    if len(got) != len(PINNED):
        sys.exit(f"expected {len(PINNED)} wheels: {got}")
    return wd


def wheels():
    upload(download_wheels(), WHEELS)


def bundle():
    """Code + data of the CPU baselines -> dataset folder/cpu_bundle.zip."""
    sys.path.insert(0, str(ROOT))
    os.environ["PFE_DATASET"] = "v4"
    from src.config import DATASET_DIR, RAW   # noqa: E402
    include = [ROOT / "src", ROOT / "scripts" / "run_v4_cpu.sh", ROOT / "requirements.txt",
               ROOT / "tests" / "__init__.py", ROOT / "tests" / "test_ealstm.py",
               DATASET_DIR, *sorted((RAW / "safran").glob("sim2_66_[0-9]*.parquet")),
               *sorted((V4 / "_cache").glob("panel*.parquet")),
               *sorted(V4.glob("*_tuning/best.json")), *sorted(V4.glob("*_tuned/best.json"))]
    ds = STAGE / "dataset"
    shutil.rmtree(ds, ignore_errors=True)
    ds.mkdir(parents=True)
    with zipfile.ZipFile(ds / "cpu_bundle.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for item in include:
            files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
            for f in files:
                if "__pycache__" not in f.parts:
                    z.write(f, f.relative_to(ROOT))
    prev = OUTPUT / "results_cpu" / "v4"
    if prev.exists():                                  # earlier Kaggle results -> resume
        with zipfile.ZipFile(ds / "state.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(prev.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(OUTPUT))
    print(f"cpu_bundle.zip: {(ds / 'cpu_bundle.zip').stat().st_size / 1e6:.1f} MB"
          + (", with state.zip" if prev.exists() else ""))
    return ds


def push(steps, budget):
    u = user()
    if "ready" not in kg("datasets", "status", f"{u}/{WHEELS}", check=False):
        sys.exit(f"dataset {u}/{WHEELS} missing: run `scripts/kaggle_cpu.py wheels` first")
    upload(bundle(), BUNDLE)
    kd = STAGE / "kernel"
    shutil.rmtree(kd, ignore_errors=True)
    kd.mkdir(parents=True)
    code = (ROOT / "scripts" / "kaggle_cpu_run.py").read_text()
    code = re.sub(r'"STEPS", ".*?"', f'"STEPS", "{steps}"', code, count=1)
    code = re.sub(r'"BUDGET_H", [\d.]+', f'"BUDGET_H", {budget}', code, count=1)
    (kd / "kaggle_cpu_run.py").write_text(code)
    (kd / "kernel-metadata.json").write_text(json.dumps(
        {"id": f"{u}/{KERNEL}", "title": KERNEL, "code_file": "kaggle_cpu_run.py",
         "language": "python", "kernel_type": "script", "is_private": True,
         "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
         "dataset_sources": [f"{u}/{BUNDLE}", f"{u}/{WHEELS}"],
         "competition_sources": [], "kernel_sources": [], "model_sources": []}, indent=1))
    push_kernel()


def push_kernel(retry=True):
    """Push the staged kernel and watch its start; one more push if it dies at once, silently."""
    kd = STAGE / "kernel"
    if not (kd / "kernel-metadata.json").exists():
        sys.exit("no staged kernel: run `scripts/kaggle_cpu.py push` first")
    print(kg("kernels", "push", "-p", str(kd)).strip())
    ref = f"{user()}/{KERNEL}"
    for waited in range(0, WATCH_S, WATCH_STEP_S):
        time.sleep(WATCH_STEP_S)
        status = kg("kernels", "status", ref, check=False).lower()
        if "error" in status or "cancel" in status:
            log = kg("kernels", "logs", ref, check=False).strip()
            if len(log) > 10:            # it ran and stopped: show why, do not retry blindly
                sys.exit(f"kernel failed after {waited + WATCH_STEP_S} s; log tail:\n{log[-2000:]}")
            if retry:
                print(f"kernel ended in ERROR with an empty log after {waited + WATCH_STEP_S} s "
                      "(it did not start): pushing it once more")
                return push_kernel(retry=False)
            sys.exit("the kernel did not start twice: check https://www.kaggle.com/code/" + ref)
        if "complete" in status:
            print("kernel already complete: `scripts/kaggle_cpu.py pull`")
            return
    print(f"kernel running after {WATCH_S} s: it continues without the laptop "
          "(`scripts/kaggle_cpu.py status`, then `pull`)")


def pull():
    u = user()
    status = kg("kernels", "status", f"{u}/{KERNEL}")
    print(status.strip())
    if "running" in status.lower() or "queued" in status.lower():
        sys.exit("still running: pull when it has finished")
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)
    kg("kernels", "output", f"{u}/{KERNEL}", "-p", str(OUTPUT), "-o")
    runs = []
    for d in sorted((OUTPUT / "results_cpu" / "v4").glob("*")):
        if (d / "predictions.parquet").exists():
            shutil.copytree(d, V4 / d.name, dirs_exist_ok=True)
            runs.append(d.name)
    print("finished runs copied:", " ".join(runs) or "none")
    if runs:
        subprocess.run([sys.executable, "-m", "src.models.evaluate", *runs], cwd=ROOT,
                       env={**os.environ, "PFE_DATASET": "v4"}, check=True)
    log = OUTPUT / "run_kaggle_cpu.log"
    if log.exists():
        print("".join(log.read_text().splitlines(keepends=True)[-15:]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["wheels", "push", "kernel", "status", "log", "pull"])
    ap.add_argument("--steps", default=DEFAULT_STEPS, help="steps of scripts/run_v4_cpu.sh")
    ap.add_argument("--budget", type=float, default=11.0, help="hours before a clean stop")
    a = ap.parse_args()
    if a.action == "wheels":
        wheels()
    elif a.action == "push":
        push(a.steps, a.budget)
    elif a.action == "kernel":
        push_kernel()
    elif a.action == "pull":
        pull()
    else:
        print(kg("kernels", "status" if a.action == "status" else "logs", f"{user()}/{KERNEL}"))


if __name__ == "__main__":
    main()
