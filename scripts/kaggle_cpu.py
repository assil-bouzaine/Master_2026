"""Run the CPU baselines of dataset v4 on Kaggle from the laptop (docs/gpu_howto.md, Kaggle CPU).

    .venv/bin/python scripts/kaggle_cpu.py wheels     # once: pinned wheels -> private dataset
    .venv/bin/python scripts/kaggle_cpu.py push [--steps "lgbm_final pastas"] [--env KEY=VALUE]
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
  cumulative pulled results as state.zip (resume), as the private dataset <user>/pfe-v4-cpu-bundle;
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
pull: validates the download before merging it into cumulative state and rotating the output.
  Copies finished runs (predictions.parquet present) to results/v4/<run> and rescores them with
  src.models.evaluate. Twin runs (world_*.json, src/models/twin.py) are copied as they are.
  Reports any failed steps after copying the results.
The bundle also carries the export tables of arms C and D (data/processed/kg/export_v4_*), which
the routed models and the twin read.
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
V4 = ROOT / "results" / "v4"
CPU_RESULTS = Path("results_cpu") / "v4"
BUNDLE, WHEELS, KERNEL = "pfe-v4-cpu-bundle", "pfe-wheels-cp313", "pfe-v4-cpu"
VERSION_GRACE_S = 120      # after "ready": time for Kaggle to unpack a new dataset version
WATCH_S, WATCH_STEP_S = 360, 30   # how long the start of a pushed kernel is watched
DEFAULT_STEPS = "naive lgbm lgbm_final lgbm_regimes pastas wellmodel"
EXPORT_POLICIES = ("main", "confident-only", "all-links")
EXPORT_REQUIRED_FILES = ("manifest.json", "edges_D.parquet", "nodes.parquet")
# The kernel and dispatcher control the interpreter, session, and result paths.
RUNNER_ENV = {"PY", "PYTHONPATH", "PYTHONIOENCODING", "PYTHONUNBUFFERED", "STEPS", "JOBS",
              "STATUS_FILE", "PFE_DATASET", "PFE_THREADS", "PFE_RESULTS", "BUDGET_H", "SYNC_S",
              "KAGGLE_INPUT", "KAGGLE_WORK", "PFE_CODE", "PIN_TARGET", "PFE_STATE"}
# The CPU baselines and routing imports, with their required dependencies.
# Versions come from requirements.txt.
PINNED = ["numpy", "pandas", "pyarrow", "scipy", "lightgbm", "narwhals", "pastas", "numba",
          "llvmlite", "matplotlib", "contourpy", "cycler", "fonttools", "kiwisolver", "pillow",
          "pyparsing", "packaging", "python-dateutil", "six", "pytz", "tzdata", "geopandas",
          "pyogrio", "shapely", "pyproj", "certifi", "charset-normalizer", "tqdm",
          "rdflib", "pyoxigraph", "requests", "idna", "urllib3"]
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


def bundle_state(stage, archive):
    """Pack the cumulative pulled results for resume, or the latest output before the first merge."""
    source = stage / "state"
    if not source.exists():
        source = stage / "output"
    runs = source / CPU_RESULTS
    if not runs.is_dir():
        return False
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(runs.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(source))
    return True


def validate_export_overrides(overrides):
    """Check that each chosen folder has the export files needed for analysis plan §14 item 23."""
    folders = {}
    for policy, path in (overrides or {}).items():
        if policy not in EXPORT_POLICIES:
            sys.exit(f"Unknown export policy {policy!r}. Choose from {', '.join(EXPORT_POLICIES)}.")
        folder = Path(path).expanduser().resolve()
        missing = [name for name in EXPORT_REQUIRED_FILES if not (folder / name).is_file()]
        if missing:
            sys.exit(f"Export override for {policy} at {folder} is missing {', '.join(missing)}.")
        folders[policy] = folder
    return folders


def parse_export_overrides(assignments):
    """Turn repeatable POLICY=PATH options into the mapping used by the bundler."""
    overrides = {}
    for assignment in assignments:
        policy, separator, path = assignment.partition("=")
        if not separator or not policy or not path:
            sys.exit("--export-override expects POLICY=PATH")
        overrides[policy] = path
    return validate_export_overrides(overrides)


def bundle(stage=STAGE, slim=False, export_override=None):
    """Build the CPU archive, with optional export replacements for the Phase 4 twin."""
    overrides = validate_export_overrides(export_override)
    ds = stage / "dataset"
    target = ds.resolve()
    for policy, folder in overrides.items():
        if folder.is_relative_to(target) or target.is_relative_to(folder):
            sys.exit(f"Export override for {policy} at {folder} overlaps the bundle staging folder {target}.")
    sys.path.insert(0, str(ROOT))
    from src.config import INTERIM, PROCESSED, RAW
    dataset = "v4"
    export_root = PROCESSED / "kg"
    export_prefix = f"export_{dataset}_"
    exports = sorted(path for path in export_root.glob(f"{export_prefix}*")
                     if path.name.removeprefix(export_prefix) not in overrides)
    routing_inputs = [RAW / "safran" / "grid_cells_66.parquet",
                      INTERIM / f"pumping_weekly_cropcal_{dataset}.parquet"]
    for path in routing_inputs:
        if not path.is_file():
            raise FileNotFoundError(f"required routing input is missing: {path}")
    daily = [] if slim else sorted((RAW / "safran").glob("sim2_66_[0-9]*.parquet"))
    panels = sorted(p for p in (V4 / "_cache").glob("panel*.parquet")
                    if not slim or not p.match("panel_lu_*.parquet"))
    # scripts/p4_queue.py: the Phase 4 queue that the p4_queue step of run_v4_cpu.sh calls
    include = [ROOT / "src", ROOT / "scripts" / "run_v4_cpu.sh", ROOT / "scripts" / "p4_queue.py",
               ROOT / "requirements.txt",
               ROOT / "tests" / "__init__.py", ROOT / "tests" / "test_ealstm.py",
               PROCESSED / f"dataset_{dataset}", *daily,
               *routing_inputs, *exports,
               *panels,
               *sorted((V4 / "_cache").glob("panel*.json")),  # land-use identity records
               *sorted(V4.glob("*_tuning/best.json")), *sorted(V4.glob("*_tuned/best.json"))]
    shutil.rmtree(ds, ignore_errors=True)
    ds.mkdir(parents=True)
    with zipfile.ZipFile(ds / "cpu_bundle.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for item in include:
            files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
            for f in files:
                if "__pycache__" not in f.parts:
                    z.write(f, f.relative_to(ROOT))
        for policy, folder in overrides.items():
            print(f"Export override for {policy}: {folder}")
            files = sorted(path.relative_to(folder) for path in folder.rglob("*") if path.is_file())
            if not any(len(path.parts) > 1 and path.parts[0] == "controls" for path in files):
                print(f"Warning: export override for {policy} has no controls/ files.")
            destination = export_root.relative_to(ROOT) / f"{export_prefix}{policy}"
            for path in files:
                z.write(folder / path, destination / path)
    with_state = bundle_state(stage, ds / "state.zip")
    print(f"cpu_bundle.zip: {(ds / 'cpu_bundle.zip').stat().st_size / 1e6:.1f} MB"
          + (", with state.zip" if with_state else ""))
    return ds


def parse_env(assignments):
    """Validate shell environment overrides before contacting Kaggle."""
    env = {}
    for assignment in assignments:
        key, separator, value = assignment.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            sys.exit("--env expects KEY=VALUE with a name matching [A-Z][A-Z0-9_]*")
        if key in RUNNER_ENV:
            sys.exit(f"--env cannot override {key}: the runner controls it")
        env[key] = value
    return env


def push(steps, budget, env_assignments=(), export_override=None):
    env = parse_env(env_assignments)
    if env:
        print(f"kernel environment overrides: {json.dumps(env)}")
    u = user()
    if "ready" not in kg("datasets", "status", f"{u}/{WHEELS}", check=False):
        sys.exit(f"dataset {u}/{WHEELS} missing: run `scripts/kaggle_cpu.py wheels` first")
    upload(bundle(stage=STAGE, export_override=export_override), BUNDLE)
    kd = STAGE / "kernel"
    shutil.rmtree(kd, ignore_errors=True)
    kd.mkdir(parents=True)
    code = (ROOT / "scripts" / "kaggle_cpu_run.py").read_text()
    code = re.sub(r'"STEPS", ".*?"', f'"STEPS", "{steps}"', code, count=1)
    code = re.sub(r'"BUDGET_H", [\d.]+', f'"BUDGET_H", {budget}', code, count=1)
    code = code.replace("\nKERNEL_ENV = {}\n", f"\nKERNEL_ENV = {env!r}\n", 1)
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


def download_output(destination):
    u = user()
    status = kg("kernels", "status", f"{u}/{KERNEL}")
    print(status.strip())
    if "running" in status.lower() or "queued" in status.lower():
        sys.exit("still running: pull when it has finished")
    kg("kernels", "output", f"{u}/{KERNEL}", "-p", str(destination), "-o")


def pull(stage=STAGE, results=V4, download=None):
    incoming = stage / "output_incoming"
    output = stage / "output"
    previous = stage / "output_prev"
    state = stage / "state" / CPU_RESULTS
    if incoming.exists():
        shutil.rmtree(incoming)
    incoming.mkdir(parents=True)
    if download is None:
        download = download_output
    download(incoming)
    if not (incoming / "run_kaggle_cpu.log").is_file():
        sys.exit(f"download is missing {incoming / 'run_kaggle_cpu.log'}")

    if not state.exists() and (output / CPU_RESULTS).is_dir():
        shutil.copytree(output / CPU_RESULTS, state)
    if (incoming / CPU_RESULTS).is_dir():
        shutil.copytree(incoming / CPU_RESULTS, state, dirs_exist_ok=True)
    if previous.exists():
        shutil.rmtree(previous)
    if output.exists():
        output.rename(previous)
    incoming.rename(output)

    runs, twins = [], []
    for d in sorted((output / CPU_RESULTS).glob("*")):
        if (d / "predictions.parquet").exists():
            shutil.copytree(d, results / d.name, dirs_exist_ok=True)
            runs.append(d.name)
        elif any(d.glob("*/world_*.json")):          # twin runs (src/models/twin.py): no rescoring
            shutil.copytree(d, results / d.name, dirs_exist_ok=True)
            twins.append(f"{d.name} ({len(list(d.glob('*/world_*.json')))} worlds)")
    print("finished runs copied:", " ".join(runs) or "none")
    if twins:
        print("twin runs copied:", ", ".join(twins))
    if runs:
        subprocess.run([sys.executable, "-m", "src.models.evaluate", *runs], cwd=ROOT,
                       env={**os.environ, "PFE_DATASET": "v4", "PFE_RESULTS": str(results.resolve())},
                       check=True)
    log = output / "run_kaggle_cpu.log"
    print("".join(log.read_text().splitlines(keepends=True)[-15:]))
    status_file = output / "run_status.json"
    if status_file.is_file():
        status = json.loads(status_file.read_text())
        print(json.dumps(status, indent=2))
        if status["failed_steps"] or (status["exit"] != 0 and not status["budget_stop"]):
            sys.exit(1)
        if status["budget_stop"]:
            print("time budget used: push again to continue")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["wheels", "push", "kernel", "status", "log", "pull"])
    ap.add_argument("--steps", default=DEFAULT_STEPS, help="steps of scripts/run_v4_cpu.sh")
    ap.add_argument("--budget", type=float, default=11.0, help="hours before a clean stop")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="override a dispatcher environment setting on push (repeatable)")
    ap.add_argument("--export-override", action="append", default=[], metavar="POLICY=PATH",
                    help="bundle a chosen graph export folder on push (repeatable)")
    a = ap.parse_args(argv)
    if a.env and a.action != "push":
        ap.error("--env is only supported by push")
    if a.export_override and a.action != "push":
        ap.error("--export-override is only supported by push")
    if a.action == "wheels":
        wheels()
    elif a.action == "push":
        push(a.steps, a.budget, a.env, parse_export_overrides(a.export_override))
    elif a.action == "kernel":
        push_kernel()
    elif a.action == "pull":
        pull()
    else:
        print(kg("kernels", "status" if a.action == "status" else "logs", f"{user()}/{KERNEL}"))


if __name__ == "__main__":
    main()
