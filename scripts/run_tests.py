"""Run every tests/test_*.py module in its own Python process.

This records the checks needed before tagging the analysis plan (docs/analysis_plan.md,
section 14). Results go to results/_tests/<UTC timestamp>_<git short hash>.json,
with a full .log for each module beside it. Some modules contain small synthetic
test fits. These are allowed on the laptop; no module may train a project model.

    PYTHONIOENCODING=utf-8 .venv/bin/python scripts/run_tests.py --jobs 1
    PYTHONIOENCODING=utf-8 .venv/bin/python scripts/run_tests.py --only routing response

Names may be short (routing), file stems (test_routing), full module names
(tests.test_routing), or paths (tests/test_routing.py). --skip takes the same names.
--quick skips SLOW even when a slow module is named by --only. Unknown names and
an empty selection are errors, so a typo cannot silently give a passing run.
"""
import argparse
import json
import math
import os
import platform
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

# Measured on 2026-11-20, full suite with --jobs 1. Quick mode skips times > 60 s.
SLOW = {
    "test_cq",         # 435.733 s
    "test_kg_rules",   # 335.363 s
    "test_routing",    # 72.684 s
    "test_twin",       # 107.040 s
}

ROOT = Path(__file__).resolve().parents[1]


def positive_seconds(value):
    """Reject unusable deadlines before starting any test processes."""
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and greater than zero")
    return seconds


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="MODULE", help="run only these modules")
    parser.add_argument("--skip", nargs="+", default=[], metavar="MODULE", help="skip these modules")
    parser.add_argument("--quick", action="store_true", help="skip the measured SLOW modules")
    parser.add_argument("--timeout", type=positive_seconds, default=1800.0, metavar="SECONDS",
                        help="deadline for each module (default: 1800 seconds)")
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=1,
                        help="simultaneous modules (default: 1; maximum: 2)")
    args = parser.parse_args(argv)
    discovered = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py") if p.is_file())

    def names(values):
        result = set()
        for value in values:
            name = Path(value).name.removesuffix(".py").removeprefix("tests.")
            if not name.startswith("test_"):
                name = "test_" + name
            if name not in discovered:
                parser.error(f"unknown test module: {value}")
            result.add(name)
        return result

    only = names(args.only) if args.only is not None else set(discovered)
    skip = names(args.skip)
    skipped = {}
    for name in discovered:
        if name not in only:
            skipped[name] = "not selected by --only"
        elif name in skip:
            skipped[name] = "--skip"
        elif args.quick and name in SLOW:
            skipped[name] = "--quick (measured over 60 seconds)"
    selected = [name for name in discovered if name not in skipped]
    if not selected:
        parser.error("no test modules selected")
    return args, discovered, selected, skipped


def git_metadata():
    """Keep the commit and working-tree state with the evidence they qualify."""
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=10,
                                check=True)
        return result.stdout.rstrip("\n")

    status = git("status", "--porcelain")
    return {"git_commit": git("rev-parse", "HEAD"),
            "git_short_hash": git("rev-parse", "--short", "HEAD"),
            "git_dirty": bool(status), "git_status_porcelain": status}


def utc_now():
    return datetime.now(timezone.utc)


def output_tail(path):
    """Read the last twenty lines without keeping a large test log in memory."""
    with path.open(encoding="utf-8", errors="replace") as stream:
        return [line.rstrip("\r\n") for line in deque(stream, maxlen=20)]


@dataclass
class Running:
    module: str
    process: subprocess.Popen
    started: float
    log_path: Path
    log: BinaryIO


def kill_module(process):
    """Also stop child tools such as Java when a module exceeds its deadline."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def module_result(module, started, log_path, status, exit_code):
    return {"module": module, "command": [sys.executable, "-m", f"tests.{module}"],
            "status": status, "exit_code": exit_code,
            "seconds": round(time.perf_counter() - started, 3),
            "tail": output_tail(log_path), "log": str(log_path.relative_to(ROOT))}


def run_modules(selected, run_id, args, record):
    """Poll at most two independent processes; keep output in separate files."""
    pending, active = deque(selected), []
    env = {**os.environ, "PFE_DATASET": "v4", "PYTHONIOENCODING": "utf-8",
           "PYTHONUNBUFFERED": "1"}
    try:
        while pending or active:
            while pending and len(active) < args.jobs:
                name = pending.popleft()
                log_path = ROOT / "results" / "_tests" / f"{run_id}_{name}.log"
                log = log_path.open("xb")
                started = time.perf_counter()
                print(f"Starting {name} -> {log_path.relative_to(ROOT)}", flush=True)
                try:
                    process = subprocess.Popen([sys.executable, "-m", f"tests.{name}"],
                                               cwd=ROOT, env=env, stdout=log,
                                               stderr=subprocess.STDOUT,
                                               start_new_session=(os.name == "posix"))
                except OSError as error:
                    log.write(f"Could not start module: {error}\n".encode("utf-8"))
                    log.close()
                    record(module_result(name, started, log_path, "fail", None))
                    continue
                active.append(Running(name, process, started, log_path, log))
            for item in active[:]:
                code = item.process.poll()
                timed_out = code is None and time.perf_counter() - item.started >= args.timeout
                if timed_out:
                    kill_module(item.process)
                    code = item.process.returncode
                if code is not None:
                    item.log.close()
                    active.remove(item)
                    status = "timeout" if timed_out else ("pass" if code == 0 else "fail")
                    record(module_result(item.module, item.started, item.log_path, status, code))
            if active:
                time.sleep(0.05)
    finally:
        # An interrupted runner must not leave a Java process or a test fit running.
        for item in active:
            kill_module(item.process)
            item.log.close()


def save_results(path, report):
    """Replace a complete JSON file so an interrupted write leaves the last checkpoint."""
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def print_summary(report, path):
    results = report["results"]
    width = max([len("module"), *(len(row["module"]) for row in results)])
    print(f"\n{'module':<{width}}  {'status':<7}  {'exit':>5}  {'seconds':>10}")
    for row in results:
        print(f"{row['module']:<{width}}  {row['status']:<7}  "
              f"{str(row['exit_code']):>5}  {row['seconds']:>10.3f}")
    print(f"\n{report['counts']['pass']} passed; {report['counts']['fail']} failed; "
          f"{report['counts']['timeout']} timed out; {len(report['skipped'])} skipped; "
          f"{len(report['not_run'])} not run. Total: {report['seconds']:.3f} s")
    print(f"Results: {path.relative_to(ROOT)}", flush=True)
    if report["git_state_changed"]:
        print("Git commit or working-tree status changed during this run; "
              "see git_at_finish in the JSON.", flush=True)


def main(argv=None):
    args, discovered, selected, skipped = arguments(argv)
    started, clock_start = utc_now(), time.perf_counter()
    metadata = git_metadata()
    run_id = f"{started:%Y%m%dT%H%M%S%fZ}_{metadata['git_short_hash']}"
    path = ROOT / "results" / "_tests" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "started_at": started.isoformat(), "finished_at": None,
              **metadata, "python_version": platform.python_version(),
              "python_executable": sys.executable, "argv": sys.argv if argv is None else argv,
              "environment": {"PFE_DATASET": "v4", "PYTHONIOENCODING": "utf-8",
                              "PYTHONUNBUFFERED": "1"},
              "jobs": args.jobs, "timeout_seconds": args.timeout, "quick": args.quick,
              "slow_modules": sorted(SLOW), "discovered": discovered, "selected": selected,
              "skipped": skipped, "results": [], "completed": False, "interrupted": False,
              "git_at_finish": None, "git_state_changed": None}

    def checkpoint():
        report["results"].sort(key=lambda row: row["module"])
        report["seconds"] = round(time.perf_counter() - clock_start, 3)
        done = {row["module"] for row in report["results"]}
        report["not_run"] = [name for name in selected if name not in done]
        report["counts"] = {status: sum(row["status"] == status for row in report["results"])
                            for status in ("pass", "fail", "timeout")}
        save_results(path, report)

    def record(row):
        report["results"].append(row)
        checkpoint()
        print(f"[{len(report['results'])}/{len(selected)}] {row['module']}: "
              f"{row['status']} ({row['seconds']:.3f} s)", flush=True)

    checkpoint()
    print(f"Running {len(selected)} of {len(discovered)} modules; jobs={args.jobs}; "
          f"timeout={args.timeout:g} s; commit={metadata['git_commit']}; "
          f"dirty={metadata['git_dirty']}", flush=True)
    try:
        run_modules(selected, run_id, args, record)
        report["completed"] = True
    except KeyboardInterrupt:
        report["interrupted"] = True
        print("\nInterrupted; active modules stopped. Completed results are preserved.", flush=True)
    finally:
        report["finished_at"] = utc_now().isoformat()
        report["git_at_finish"] = git_metadata()
        report["git_state_changed"] = report["git_at_finish"] != metadata
        checkpoint()
    print_summary(report, path)
    if report["interrupted"]:
        return 130
    return int(bool(report["counts"]["fail"] or report["counts"]["timeout"]))


if __name__ == "__main__":
    sys.exit(main())
