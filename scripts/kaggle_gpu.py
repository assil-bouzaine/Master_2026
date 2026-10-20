"""Run GPU steps of the v3 sweep on Kaggle from the laptop (docs/gpu_howto.md, Kaggle section).

    .venv/bin/kaggle auth login                                  # once, by Assil (browser)
    .venv/bin/python scripts/kaggle_gpu.py push [--steps "tune:ealstm regimes:ealstm"]
    .venv/bin/python scripts/kaggle_gpu.py status | log | quota
    .venv/bin/python scripts/kaggle_gpu.py pull                  # -> results/v3/<run>, rescored

push: rebuilds gpu_bundle.zip and uploads it as the private dataset <user>/pfe-v3-bundle (a new
version if it exists), with the last pulled kernel output as state.zip so that the kernel
resumes; waits until Kaggle has processed it; then pushes scripts/kaggle_run.py as the
private kernel <user>/pfe-v3-gpu (T4, internet on for the pinned packages). Kaggle starts it
at once and it runs without the laptop.
pull: downloads the kernel output to results/v3/_kaggle/output, copies every finished run
(predictions.parquet present) to results/v3/<run> and rescores it with src.models.evaluate.
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
STAGE = ROOT / "results" / "v3" / "_kaggle"          # results/ is gitignored
OUTPUT = STAGE / "output"
DATASET, KERNEL = "pfe-v3-bundle", "pfe-v3-gpu"


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


def push(steps, budget):
    u = user()
    subprocess.run([sys.executable, "scripts/make_gpu_bundle.py"], cwd=ROOT, check=True,
                   env={**os.environ, "PFE_DATASET": "v3"})
    ds = STAGE / "dataset"
    shutil.rmtree(ds, ignore_errors=True)
    ds.mkdir(parents=True)
    shutil.copy(ROOT / "gpu_bundle.zip", ds)
    prev = OUTPUT / "results_gpu" / "v3"
    if prev.exists():                                  # earlier Kaggle results -> resume
        with zipfile.ZipFile(ds / "state.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(prev.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(OUTPUT))
    (ds / "dataset-metadata.json").write_text(json.dumps(
        {"title": DATASET, "id": f"{u}/{DATASET}", "licenses": [{"name": "other"}]}, indent=1))
    exists = "ready" in kg("datasets", "status", f"{u}/{DATASET}", check=False)
    if exists:
        kg("datasets", "version", "-p", str(ds), "-m", time.strftime("%Y-%m-%d %H:%M"), "-t")
    else:
        kg("datasets", "create", "-p", str(ds), "-t")
    for _ in range(60):                                # Kaggle processes the upload first
        time.sleep(10)
        if "ready" in kg("datasets", "status", f"{u}/{DATASET}", check=False):
            break
    else:
        sys.exit("dataset not ready after 10 min; push again later")
    kd = STAGE / "kernel"
    shutil.rmtree(kd, ignore_errors=True)
    kd.mkdir(parents=True)
    code = (ROOT / "scripts" / "kaggle_run.py").read_text()
    code = re.sub(r'^DEFAULT_STEPS = ".*"$', f'DEFAULT_STEPS = "{steps}"', code, flags=re.M)
    code = re.sub(r'"BUDGET_H", [\d.]+', f'"BUDGET_H", {budget}', code)
    (kd / "kaggle_run.py").write_text(code)
    (kd / "kernel-metadata.json").write_text(json.dumps(
        {"id": f"{u}/{KERNEL}", "title": KERNEL, "code_file": "kaggle_run.py",
         "language": "python", "kernel_type": "script", "is_private": True,
         "enable_gpu": True, "enable_tpu": False, "enable_internet": True,
         "machine_shape": "NvidiaTeslaT4", "dataset_sources": [f"{u}/{DATASET}"],
         "competition_sources": [], "kernel_sources": [], "model_sources": []}, indent=1))
    print(kg("kernels", "push", "-p", str(kd)))


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
    for d in sorted((OUTPUT / "results_gpu" / "v3").glob("*")):
        if (d / "predictions.parquet").exists():
            shutil.copytree(d, ROOT / "results" / "v3" / d.name, dirs_exist_ok=True)
            runs.append(d.name)
    print("finished runs copied:", " ".join(runs) or "none")
    if runs:
        subprocess.run([sys.executable, "-m", "src.models.evaluate", *runs], cwd=ROOT,
                       env={**os.environ, "PFE_DATASET": "v3"}, check=True)
    log = OUTPUT / "run_kaggle.log"
    if log.exists():
        print("".join(log.read_text().splitlines(keepends=True)[-15:]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["push", "status", "log", "quota", "pull"])
    ap.add_argument("--steps", default="tune:ealstm regimes:ealstm taccari | tune:taccari "
                                       "regimes:taccari", help='chains separated by "|"')
    ap.add_argument("--budget", type=float, default=11.0, help="hours before a clean stop")
    a = ap.parse_args()
    if a.action == "push":
        push(a.steps, a.budget)
    elif a.action == "pull":
        pull()
    elif a.action == "quota":
        print(kg("quota"))
    else:
        print(kg("kernels", "status" if a.action == "status" else "logs", f"{user()}/{KERNEL}"))


if __name__ == "__main__":
    main()
