"""Checks for the Phase 4 dependency-aware queue (scripts/p4_queue.py; no model fitting).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_p4_queue

1. Plan against the real dry run of the ten Phase 4 steps: 378 fits, 51 assemblies, 14 refits,
   269 dependencies; every planned command, re-quoted with bash ``printf %q``, equals its dry-run
   line; every refit depends on exactly its R1 fit, every assembly on exactly its five folds, and
   nothing else has a dependency; bash ``$'...'`` ANSI-C quoting is refused.
2. Execution with a stub script (in ``results/_agents/tmp/T38/``) substituted for ``PY``:
   - checks that no more than ``--jobs`` commands overlap in time (and that parallelism occurs);
   - checks that a failed R1 skips only its refit, a failed fold skips only its assembly,
     everything else runs, and the exit code is 1;
   - checks that with no failures every command runs once, dependencies start after their
     prerequisites finish, ``PFE_THREADS=1``, logs and heartbeats are written, and exit code is 0;
   - checks that the ``p4_queue`` step in ``scripts/run_v4_cpu.sh`` is locked unless
     ``P4_CONFIRMED=1``.
3. Sharding (2 and 3 shards): partitions all commands without overlap or omission, keeps every
   connected component whole, and balances fit counts within the size of the largest component.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from scripts import p4_queue as Q

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "results" / "_agents" / "tmp" / "T38"
TEN_STEPS = Q.DEFAULT_STEPS


def _clean_env(**overrides: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("P4_") and key != "STATUS_FILE"
    }
    env["PFE_DATASET"] = "v4"
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(overrides)
    return env


def _bash_requote_all(argvs: list[list[str]]) -> list[str]:
    """Re-quote every argv list with bash ``printf %q`` (same format as ``p4_command``)."""
    # Pack null-delimited commands so a single bash invocation re-quotes all 429 commands quickly.
    script = (
        'while IFS= read -r -d "" count; do '
        '  args=(); '
        '  for ((i=0; i<count; i++)); do IFS= read -r -d "" tok; args+=("$tok"); done; '
        '  printf "%q" "${args[0]}"; '
        '  for ((i=1; i<${#args[@]}; i++)); do printf " %q" "${args[i]}"; done; '
        '  printf "\\n"; '
        'done'
    )
    payload_parts: list[str] = []
    for argv in argvs:
        payload_parts.append(str(len(argv)))
        payload_parts.extend(argv)
    payload = "\0".join(payload_parts) + "\0"
    result = subprocess.run(
        ["bash", "-c", script],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.splitlines()


def _max_overlap(events: list[dict]) -> int:
    """Compute maximum number of commands running simultaneously from [start, end] intervals."""
    points: list[tuple[float, int]] = []
    for ev in events:
        # Process end (-1) before start (+1) at equal timestamps to avoid false overlap.
        points.append((ev["start"], 1))
        points.append((ev["end"], -1))
    points.sort(key=lambda item: (item[0], item[1]))
    active = 0
    peak = 0
    for _, delta in points:
        active += delta
        if active > peak:
            peak = active
    return peak


def _write_stub(path: Path) -> Path:
    """Write a fast Python stub executable that mimics PY for dry-run dates and task execution."""
    code = f"""#!{sys.executable}
import fcntl
import json
import os
from pathlib import Path
import sys
import time

argv = sys.argv[1:]
if len(argv) >= 2 and argv[0] == "-c" and "R3_STARTS" in argv[1]:
    print("2016-04-01 2012-07-01")
    sys.exit(0)

if len(argv) >= 2 and argv[0] == "-m" and argv[1] == "src.models.response":
    run_name = None
    fold = None
    for i, tok in enumerate(argv):
        if tok == "--run":
            run_name = argv[i + 1]
        elif tok == "--fold":
            fold = argv[i + 1]
    task_id = f"{{run_name}}_fold{{fold}}" if fold is not None else run_name
elif len(argv) >= 3 and argv[0] == "-c" and "assemble_lwo(sys.argv[1]" in argv[1]:
    run_name = argv[2]
    task_id = f"{{run_name}}_assemble"
else:
    print(f"Unexpected stub invocation: {{argv!r}}", file=sys.stderr)
    sys.exit(2)

delay = float(os.environ.get("STUB_SLEEP", "0.08"))
fail_set = {{x for x in os.environ.get("STUB_FAIL", "").split(",") if x}}
rc = 1 if (task_id in fail_set or run_name in fail_set) else 0

t0 = time.monotonic()
time.sleep(delay)
t1 = time.monotonic()

record = {{
    "task_id": task_id,
    "run": run_name,
    "start": t0,
    "end": t1,
    "pid": os.getpid(),
    "rc": rc,
    "pfe_threads": os.environ.get("PFE_THREADS"),
}}
trace_path = Path(os.environ["STUB_TRACE"])
trace_path.parent.mkdir(parents=True, exist_ok=True)
with trace_path.open("a", encoding="utf-8") as fh:
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    fh.write(json.dumps(record) + "\\n")
    fh.flush()
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

print(f"stub ran {{task_id}} rc={{rc}}")
sys.exit(rc)
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_real_dry_run_plan() -> Q.Plan:
    env = _clean_env(PY=sys.executable)
    plan = Q.build_plan(TEN_STEPS, env=env, cwd=ROOT)
    counts = plan.summary()
    assert counts["fits"] == 378, counts
    assert counts["assemblies"] == 51, counts
    assert counts["refits"] == 14, counts
    assert counts["dependencies"] == 14 + 51 * 5, counts
    assert counts["total"] == 429, counts

    # Every planned command, re-quoted with bash printf %q, must equal its dry-run line verbatim.
    requoted = _bash_requote_all([task.argv for task in plan.tasks])
    assert len(requoted) == len(plan.tasks)
    for task, line in zip(plan.tasks, requoted):
        assert line == task.raw_line, (task.id, line, task.raw_line)

    by_id = plan.by_id()
    for task in plan.tasks:
        if task.is_refit:
            assert task.deps == [task.refit_from], (task.id, task.deps, task.refit_from)
            parent = by_id[task.deps[0]]
            assert parent.kind == "fit" and parent.fold is None and parent.run == task.refit_from
        elif task.kind == "assembly":
            expected_folds = [f"{task.run}_fold{k}" for k in range(5)]
            assert task.deps == expected_folds, (task.id, task.deps, expected_folds)
            for dep_id in task.deps:
                assert by_id[dep_id].kind == "fit" and by_id[dep_id].run == task.run
        else:
            assert task.deps == [], (task.id, task.deps)

    # Confirm plan CLI + --json export work and refuse bash $'...' ANSI-C quoting.
    json_out = SCRATCH / "plan_10steps.json"
    if json_out.exists():
        json_out.unlink()
    cli = subprocess.run(
        [sys.executable, "-m", "scripts.p4_queue", "plan", "--steps", TEN_STEPS, "--json", str(json_out)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert cli.returncode == 0, (cli.stdout, cli.stderr)
    assert "378 fits, 51 assemblies, 14 refits, 269 dependencies" in cli.stdout, cli.stdout
    loaded = json.loads(json_out.read_text(encoding="utf-8"))
    assert loaded["counts"] == counts and len(loaded["tasks"]) == 429

    try:
        Q.parse_command_line("python -m src.models.response --run $'bad\\nname'", 0)
    except ValueError as error:
        assert "$'" in str(error)
    else:
        raise AssertionError("parse_command_line must refuse bash $'...' quoting")

    print(
        f"  1. Real dry-run plan: {counts['fits']} fits, {counts['assemblies']} assemblies, "
        f"{counts['refits']} refits, {counts['dependencies']} dependencies across "
        f"{counts['components']} components; all 429 re-quoted commands match dry-run lines."
    )
    return plan


def test_stub_execution() -> dict[str, int]:
    stub = _write_stub(SCRATCH / "stub_py.py")
    jobs = 4
    steps = "p4_B1c"  # 2 arms x (R1 + 5 folds + assembly + f25 + f50 + refit) = 20 commands

    # --- Case A: fail one R1 and one fold of the other arm ---
    trace_fail = SCRATCH / "trace_fail.jsonl"
    logs_fail = SCRATCH / "logs_fail"
    if trace_fail.exists():
        trace_fail.unlink()
    if logs_fail.exists():
        for f in logs_fail.iterdir():
            f.unlink()

    env_fail = _clean_env(
        PY=str(stub),
        STUB_TRACE=str(trace_fail),
        STUB_SLEEP="0.08",
        STUB_FAIL="p4_B1c_B_nametags_r1,p4_B1c_B_shuffled_r1_lwo_fold2",
    )
    res_fail = subprocess.run(
        [
            sys.executable, "-m", "scripts.p4_queue", "run",
            "--steps", steps,
            "--jobs", str(jobs),
            "--log-dir", str(logs_fail),
            "--heartbeat", "0.1",
        ],
        cwd=ROOT,
        env=env_fail,
        text=True,
        capture_output=True,
    )
    assert res_fail.returncode == 1, (res_fail.returncode, res_fail.stdout, res_fail.stderr)
    assert "HEARTBEAT" in res_fail.stdout, res_fail.stdout
    assert "SKIP p4_B1c_B_nametags_r1_refit" in res_fail.stdout, res_fail.stdout
    assert "SKIP p4_B1c_B_shuffled_r1_lwo_assemble" in res_fail.stdout, res_fail.stdout

    events_fail = [json.loads(line) for line in trace_fail.read_text(encoding="utf-8").splitlines()]
    ran_fail = [ev["task_id"] for ev in events_fail]
    assert len(ran_fail) == len(set(ran_fail)) == 18, (len(ran_fail), ran_fail)
    assert "p4_B1c_B_nametags_r1_refit" not in ran_fail
    assert "p4_B1c_B_shuffled_r1_lwo_assemble" not in ran_fail
    # The unaffected arm's refit and the first arm's assembly must both have run and succeeded.
    ev_map_fail = {ev["task_id"]: ev for ev in events_fail}
    assert ev_map_fail["p4_B1c_B_shuffled_r1_refit"]["rc"] == 0
    assert ev_map_fail["p4_B1c_B_nametags_r1_lwo_assemble"]["rc"] == 0
    assert ev_map_fail["p4_B1c_B_nametags_r1"]["rc"] == 1
    assert ev_map_fail["p4_B1c_B_shuffled_r1_lwo_fold2"]["rc"] == 1
    assert all(ev["pfe_threads"] == "1" for ev in events_fail)

    overlap_fail = _max_overlap(events_fail)
    assert 2 <= overlap_fail <= jobs, overlap_fail

    # --- Case B: no failures -> exit 0, every command runs once, deps respected ---
    trace_ok = SCRATCH / "trace_ok.jsonl"
    logs_ok = SCRATCH / "logs_ok"
    if trace_ok.exists():
        trace_ok.unlink()
    if logs_ok.exists():
        for f in logs_ok.iterdir():
            f.unlink()

    env_ok = _clean_env(
        PY=str(stub),
        STUB_TRACE=str(trace_ok),
        STUB_SLEEP="0.08",
    )
    res_ok = subprocess.run(
        [
            sys.executable, "-m", "scripts.p4_queue", "run",
            "--steps", steps,
            "--jobs", str(jobs),
            "--log-dir", str(logs_ok),
            "--heartbeat", "0.1",
        ],
        cwd=ROOT,
        env=env_ok,
        text=True,
        capture_output=True,
    )
    assert res_ok.returncode == 0, (res_ok.returncode, res_ok.stdout, res_ok.stderr)
    assert "HEARTBEAT" in res_ok.stdout, res_ok.stdout

    events_ok = [json.loads(line) for line in trace_ok.read_text(encoding="utf-8").splitlines()]
    ran_ok = [ev["task_id"] for ev in events_ok]
    assert len(ran_ok) == len(set(ran_ok)) == 20, (len(ran_ok), ran_ok)
    assert all(ev["rc"] == 0 and ev["pfe_threads"] == "1" for ev in events_ok)

    ev_map_ok = {ev["task_id"]: ev for ev in events_ok}
    plan_b1c = Q.build_plan(steps, env=env_ok, cwd=ROOT)
    for task in plan_b1c.tasks:
        # Check exact log file creation for fits, folds and assemblies.
        log_file = logs_ok / task.log_name
        assert log_file.is_file() and task.id in log_file.read_text(encoding="utf-8"), log_file
        for dep_id in task.deps:
            assert ev_map_ok[task.id]["start"] >= ev_map_ok[dep_id]["end"], (
                task.id, dep_id, ev_map_ok[task.id]["start"], ev_map_ok[dep_id]["end"]
            )

    overlap_ok = _max_overlap(events_ok)
    assert 2 <= overlap_ok <= jobs, overlap_ok

    # Verify default log directory resolves to results/$PFE_DATASET/_p4_logs.
    assert Q.default_log_dir("v4") == ROOT / "results" / "v4" / "_p4_logs"

    # Verify the p4_queue step in scripts/run_v4_cpu.sh respects the P4_CONFIRMED lock.
    locked = subprocess.run(
        ["bash", "scripts/run_v4_cpu.sh"],
        cwd=ROOT,
        env=_clean_env(STEPS="p4_queue", P4_CONFIRMED="0", PY=sys.executable),
        text=True,
        capture_output=True,
    )
    assert locked.returncode == 0, (locked.stdout, locked.stderr)
    assert "Phase 4 is locked until Gate 3 and the plan's tag" in locked.stdout, locked.stdout
    assert "START " not in locked.stdout

    print(
        f"  2. Stub execution (p4_B1c, --jobs {jobs}): failure run exited 1 (18 ran, 2 skipped, "
        f"peak overlap {overlap_fail}); clean run exited 0 (20 ran once, peak overlap {overlap_ok}); "
        f"heartbeat, PFE_THREADS=1, log files and p4_queue lock verified."
    )
    return {"overlap_fail": overlap_fail, "overlap_ok": overlap_ok, "jobs": jobs}


def test_sharding(plan: Q.Plan) -> None:
    components = Q.connected_components(plan.tasks)
    largest_component_fits = max(
        sum(1 for task in comp_tasks if task.kind == "fit")
        for _, comp_tasks in components
    )
    all_ids = {task.id for task in plan.tasks}

    summary_parts = []
    for total_shards in (2, 3):
        seen_ids: list[str] = []
        comp_to_shard: dict[str, int] = {}
        fit_counts: list[int] = []
        for idx in range(1, total_shards + 1):
            sub_plan = Q.select_shard(plan, idx, total_shards)
            sub_ids = {task.id for task in sub_plan.tasks}
            seen_ids.extend(sub_ids)
            fit_counts.append(sub_plan.summary()["fits"])
            for task in sub_plan.tasks:
                # Every dependency must remain in the same shard.
                for dep_id in task.deps:
                    assert dep_id in sub_ids, (total_shards, idx, task.id, dep_id)
                prev = comp_to_shard.get(task.component)
                assert prev is None or prev == idx, (task.component, prev, idx)
                comp_to_shard[task.component] = idx

        assert len(seen_ids) == len(all_ids) and set(seen_ids) == all_ids
        assert len(comp_to_shard) == len(components)
        spread = max(fit_counts) - min(fit_counts)
        assert spread <= largest_component_fits, (total_shards, fit_counts, largest_component_fits)
        summary_parts.append(f"{total_shards} shards -> fits {fit_counts} (spread {spread})")

    # Check invalid shard specs are refused.
    for bad in ("0/2", "3/2", "1/0", "1", "a/b"):
        try:
            Q.parse_shard(bad)
        except Exception:
            pass
        else:
            raise AssertionError(f"Invalid shard {bad!r} must be refused")

    print(
        f"  3. Shards (largest component = {largest_component_fits} fits): "
        + "; ".join(summary_parts) + "."
    )


def main() -> None:
    plan = test_real_dry_run_plan()
    test_stub_execution()
    test_sharding(plan)
    print("test_p4_queue: all checks passed")


if __name__ == "__main__":
    main()
