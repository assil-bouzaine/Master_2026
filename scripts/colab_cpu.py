"""Run the dataset v4 CPU steps on Colab using Drive (analysis plan §5 and §14).

    .venv/bin/python -m scripts.colab_cpu push [--steps "..."] [--env KEY=VALUE] [--budget H] [--full]
    .venv/bin/python -m scripts.colab_cpu log [-n N]
    .venv/bin/python -m scripts.colab_cpu status
    .venv/bin/python -m scripts.colab_cpu pull

Push stages the CPU bundle, resume state and launcher under results/_colab_cpu and
copies them to gdrive:pfe_colab_cpu/input. Run the printed cell in a Colab CPU session.
Use --full for steps that read daily SAFRAN or land-use panels.
The shared runner works on local disk and saves to Drive. Pull validates and merges
the saved results and rescores finished runs through the Kaggle CPU pull code.
"""
import argparse
import hashlib
import shlex
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from . import kaggle_cpu
else:
    import kaggle_cpu

STAGE = kaggle_cpu.ROOT / "results" / "_colab_cpu"
REMOTE = "gdrive:pfe_colab_cpu"
DRIVE = Path("/content/drive/MyDrive/pfe_colab_cpu")
INPUT, WORK = DRIVE / "input", DRIVE / "work"
CODE = Path("/content/pfe")
RUNNER = Path("scripts/kaggle_cpu_run.py")
LAUNCHER = "run_colab_cpu.sh"
LOG_NAME, STATUS_NAME = "run_kaggle_cpu.log", "run_status.json"


def rclone(action, *args, missing_ok=False):
    try:
        result = subprocess.run(["rclone", action, *args], capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit("rclone executable not found on PATH")
    if result.returncode:
        if missing_ok and result.returncode in (3, 4):  # directory or file not found
            return ""
        # Keep rclone diagnostics private. They may show details from its configuration.
        sys.exit(f"rclone {action} failed (exit {result.returncode}) for {' '.join(args)}")
    return result.stdout


def launcher_text(steps, budget, overrides, bundle_md5):
    env = dict(KAGGLE_INPUT=str(INPUT), KAGGLE_WORK=str(WORK), PFE_CODE=str(CODE),
               PIN_TARGET="/content/pins", PFE_STATE="/content/pfe_state", PIP_ONLINE="1",
               BUDGET_H=str(budget), SYNC_S="300", STEPS=steps, **overrides)
    assignments = []
    for key, value in env.items():
        if key == "P4_PARALLEL" and value == "$(nproc)":
            quoted = '"$(nproc)"'
        else:
            quoted = shlex.quote(value)
        assignments.append(f"{key}={quoted}")
    pushed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return "\n".join([
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"# Push {pushed} | steps {steps!r} | cpu_bundle.zip MD5 {bundle_md5}",
        shlex.join(["unzip", "-oq", str(INPUT / "cpu_bundle.zip"), "-d", str(CODE)]),
        # Clear the previous session's status. The runner writes a new one when done.
        shlex.join(["rm", "-f", str(WORK / STATUS_NAME)]),
        " ".join([*assignments, shlex.join(["python3", str(CODE / RUNNER)])]),
        "",
    ])


def push(steps, budget, assignments, full=False):
    overrides = kaggle_cpu.parse_env(assignments)
    if "PIP_ONLINE" in overrides:
        sys.exit("--env cannot override PIP_ONLINE: the runner controls it")
    dataset = kaggle_cpu.bundle(stage=STAGE, slim=not full)
    bundle, state = dataset / "cpu_bundle.zip", dataset / "state.zip"
    # Kaggle ships the runner as its kernel. Colab needs it inside the bundle.
    with zipfile.ZipFile(bundle, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.write(kaggle_cpu.ROOT / RUNNER, RUNNER)
    if not state.exists():
        # Upload an empty archive on the first push so an older Drive state cannot be used.
        with zipfile.ZipFile(state, "w"):
            pass
    with bundle.open("rb") as archive:
        bundle_md5 = hashlib.file_digest(archive, "md5").hexdigest()
    launcher = STAGE / LAUNCHER
    launcher.write_text(launcher_text(steps, budget, overrides, bundle_md5), encoding="utf-8")
    print(f"Colab upload {bundle.name}: {bundle.stat().st_size / 1e6:.1f} MB")
    for path in (bundle, state, launcher):
        rclone("copyto", str(path), f"{REMOTE}/input/{path.name}")
    cell = ("from google.colab import drive; drive.mount('/content/drive')\n"
            f"!bash {shlex.quote(str(INPUT / LAUNCHER))}\n")
    (STAGE / "colab_cell.txt").write_text(cell, encoding="utf-8")
    print(cell, end="")


def log(n):
    lines = rclone("cat", f"{REMOTE}/work/{LOG_NAME}").splitlines(keepends=True)
    if n:
        print("".join(lines[-n:]), end="")


def status():
    files = rclone("lsf", f"{REMOTE}/work", "--files-only", missing_ok=True).splitlines()
    if STATUS_NAME in files:
        print(rclone("cat", f"{REMOTE}/work/{STATUS_NAME}").rstrip())
    else:
        print("running")
        if LOG_NAME in files:
            log(5)


def download_output(destination):
    rclone("copy", f"{REMOTE}/work", str(destination))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    actions = parser.add_subparsers(dest="action", required=True)
    push_parser = actions.add_parser("push", help="Upload the CPU bundle and print the Colab cell")
    push_parser.add_argument("--steps", default=kaggle_cpu.DEFAULT_STEPS, help="steps of scripts/run_v4_cpu.sh")
    push_parser.add_argument("--budget", type=float, default=23, help="hours before a clean stop")
    push_parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                             help="override a dispatcher environment setting (repeatable)")
    push_parser.add_argument("--full", action="store_true", help="include daily SAFRAN and land-use panels")
    log_parser = actions.add_parser("log", help="Print the last lines of the Drive run log")
    log_parser.add_argument("-n", type=int, default=15, help="number of lines to print")
    actions.add_parser("status", help="Print the run status or the latest log lines")
    actions.add_parser("pull", help="Download, merge and rescore the finished runs")
    args = parser.parse_args(argv)
    if args.action == "push":
        push(args.steps, args.budget, args.env, full=args.full)
    elif args.action == "log":
        if args.n < 0:
            log_parser.error("-n must be zero or greater")
        log(args.n)
    elif args.action == "status":
        status()
    elif args.action == "pull":
        kaggle_cpu.pull(stage=STAGE, download=download_output)


if __name__ == "__main__":
    main()
