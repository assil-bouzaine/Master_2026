"""Dependency-aware queue for Phase 4 response-model fits (analysis plan §14, items 18 and 20).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m scripts.p4_queue plan --steps "p4_B1 ..."
    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m scripts.p4_queue run --steps "p4_B1 ..." --jobs auto

Why this exists
---------------
``scripts/run_v4_cpu.sh`` runs Phase 4 blocks one after another and, inside each arm, runs every
regime sequentially (R1, five folds, assembly, f25, f50, refit). On a many-core machine (such as
a 24-vCPU Colab TPU runtime), most cores sit idle while the last arm of a block finishes.

This queue asks ``scripts/run_v4_cpu.sh`` for its dry-run commands (``P4_DRYRUN=1``), parses those
exact command lines without re-coding any block definitions, builds the small dependency graph
(a refit waits for its R1 fit; an ``assemble_lwo`` call waits for its five folds), and runs
independent commands in parallel across up to ``--jobs`` worker processes with ``PFE_THREADS=1``.
Longest chains start first (R1 fits that unlock a refit) so refits are not left for the tail.

Resumability
------------
Re-running the queue after a timeout or interruption is safe: the response model caches every
finished start on disk (``cached_seed`` in ``src/models/response.py`` and ``src/models/lstm.py``),
so a re-run skips completed starts and computes only what is missing.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import heapq
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STEPS = "p4_B1 p4_B1c p4_B2 p4_B2conv p4_B3 p4_B4 p4_B5 p4_B6 p4_B7 p4_B8"
DEFAULT_HEARTBEAT_S = 20.0


@dataclass
class Task:
    """One command emitted by ``scripts/run_v4_cpu.sh`` during a Phase 4 dry run."""

    id: str
    kind: str  # "fit" or "assembly"
    run: str
    fold: int | None
    refit_from: str | None
    argv: list[str]
    deps: list[str]
    log_name: str
    order: int
    raw_line: str
    component: str = ""

    @property
    def is_refit(self) -> bool:
        return self.kind == "fit" and self.refit_from is not None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "run": self.run,
            "fold": self.fold,
            "refit_from": self.refit_from,
            "deps": list(self.deps),
            "log_name": self.log_name,
            "component": self.component,
            "order": self.order,
            "argv": list(self.argv),
        }


@dataclass
class Plan:
    """Parsed Phase 4 commands and their dependency graph."""

    steps: str
    tasks: list[Task]

    def by_id(self) -> dict[str, Task]:
        return {task.id: task for task in self.tasks}

    def summary(self) -> dict[str, int]:
        fits = sum(1 for task in self.tasks if task.kind == "fit")
        assemblies = sum(1 for task in self.tasks if task.kind == "assembly")
        refits = sum(1 for task in self.tasks if task.is_refit)
        dependencies = sum(len(task.deps) for task in self.tasks)
        components = len({task.component for task in self.tasks})
        return {
            "total": len(self.tasks),
            "fits": fits,
            "assemblies": assemblies,
            "refits": refits,
            "dependencies": dependencies,
            "components": components,
        }

    def to_dict(self) -> dict:
        return {
            "steps": self.steps,
            "counts": self.summary(),
            "tasks": [task.to_dict() for task in self.tasks],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _flag_value(argv: list[str], name: str, *, required: bool = False) -> str | None:
    """Return the last value passed after ``name`` (matching argparse's last-flag-wins rule)."""
    values = []
    for idx, arg in enumerate(argv):
        if arg == name:
            if idx + 1 >= len(argv):
                raise ValueError(f"Flag {name} has no value in command: {argv!r}")
            values.append(argv[idx + 1])
    if not values:
        if required:
            raise ValueError(f"Missing required flag {name} in command: {argv!r}")
        return None
    return values[-1]


def parse_jobs(spec: str) -> int:
    """Parse ``--jobs``: either ``auto`` (``os.cpu_count()``) or a positive integer."""
    if spec == "auto":
        return os.cpu_count() or 1
    try:
        value = int(spec)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"--jobs must be a positive integer or 'auto', got {spec!r}"
        ) from error
    if value < 1:
        raise argparse.ArgumentTypeError(f"--jobs must be >= 1, got {value}")
    return value


def parse_shard(spec: str) -> tuple[int, int]:
    """Parse 1-based ``--shard I/K`` (with ``1 <= I <= K``)."""
    parts = spec.split("/")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"--shard must have the form I/K (1-based, e.g. 1/2), got {spec!r}"
        )
    try:
        index, total = int(parts[0]), int(parts[1])
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"--shard must contain integers I/K, got {spec!r}"
        ) from error
    if total < 1 or index < 1 or index > total:
        raise argparse.ArgumentTypeError(
            f"--shard must satisfy 1 <= I <= K (1-based), got {spec!r}"
        )
    return index, total


def default_log_dir(dataset: str | None = None, root: Path = ROOT) -> Path:
    """Return ``results/$PFE_DATASET/_p4_logs`` (defaulting to ``v4`` when unset)."""
    version = dataset or os.environ.get("PFE_DATASET") or "v4"
    return root / "results" / version / "_p4_logs"


def dry_run(steps: str | Iterable[str], env: dict[str, str] | None = None,
            cwd: Path = ROOT) -> list[str]:
    """Run ``scripts/run_v4_cpu.sh`` in dry-run mode and return its stdout lines."""
    step_str = steps if isinstance(steps, str) else " ".join(steps)
    if not step_str.strip():
        raise ValueError("steps must not be empty")
    run_env = dict(os.environ if env is None else env)
    # Do not let the dry run truncate an outer run_v4_cpu.sh STATUS_FILE.
    run_env.pop("STATUS_FILE", None)
    run_env["P4_DRYRUN"] = "1"
    run_env["P4_CONFIRMED"] = "1"
    run_env["STEPS"] = step_str

    result = subprocess.run(
        ["bash", "scripts/run_v4_cpu.sh"],
        cwd=cwd,
        env=run_env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"Dry run of scripts/run_v4_cpu.sh failed (exit {result.returncode}): {detail}"
        )
    return result.stdout.splitlines()


def parse_command_line(line: str, order: int) -> Task:
    """Parse one bash ``printf %q`` command line from the Phase 4 dry run."""
    if "$'" in line:
        raise ValueError(
            f"Refusing dry-run line with bash $'...' ANSI-C quoting: {line!r}"
        )
    argv = shlex.split(line, posix=True)
    if len(argv) >= 3 and argv[1:3] == ["-m", "src.models.response"]:
        run_name = _flag_value(argv, "--run", required=True)
        assert run_name is not None
        fold_raw = _flag_value(argv, "--fold", required=False)
        fold = int(fold_raw) if fold_raw is not None else None
        refit_from = _flag_value(argv, "--refit-from", required=False)
        task_id = f"{run_name}_fold{fold}" if fold is not None else run_name
        log_name = f"{task_id}.log"
        return Task(
            id=task_id,
            kind="fit",
            run=run_name,
            fold=fold,
            refit_from=refit_from,
            argv=argv,
            deps=[],
            log_name=log_name,
            order=order,
            raw_line=line,
        )
    if len(argv) >= 4 and argv[1] == "-c" and "assemble_lwo(sys.argv[1]" in argv[2]:
        run_name = argv[3]
        task_id = f"{run_name}_assemble"
        log_name = f"{run_name}_assemble.log"
        return Task(
            id=task_id,
            kind="assembly",
            run=run_name,
            fold=None,
            refit_from=None,
            argv=argv,
            deps=[],
            log_name=log_name,
            order=order,
            raw_line=line,
        )
    raise ValueError(f"Unrecognized Phase 4 dry-run command: {line!r}")


def connected_components(tasks: list[Task]) -> list[tuple[str, list[Task]]]:
    """Return weakly connected components of the dependency graph, sorted by component name."""
    by_id = {task.id: task for task in tasks}
    neighbors: dict[str, set[str]] = {task.id: set() for task in tasks}
    for task in tasks:
        for dep in task.deps:
            if dep not in neighbors:
                raise ValueError(f"Task {task.id!r} depends on unknown task {dep!r}")
            neighbors[task.id].add(dep)
            neighbors[dep].add(task.id)

    seen: set[str] = set()
    components: list[tuple[str, list[Task]]] = []
    for task in tasks:
        if task.id in seen:
            continue
        group: list[Task] = []
        queue = deque([task.id])
        seen.add(task.id)
        while queue:
            current = queue.popleft()
            group.append(by_id[current])
            for nxt in neighbors[current]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        group.sort(key=lambda item: item.order)
        name = min(item.id for item in group)
        for item in group:
            item.component = name
        components.append((name, group))

    components.sort(key=lambda item: item[0])
    return components


def _validate_acyclic(tasks: list[Task]) -> None:
    """Raise ``ValueError`` if the dependency graph contains a cycle."""
    by_id = {task.id: task for task in tasks}
    in_degree = {task.id: len(task.deps) for task in tasks}
    children: dict[str, list[str]] = {task.id: [] for task in tasks}
    for task in tasks:
        for dep in task.deps:
            children[dep].append(task.id)
    ready = deque([tid for tid, deg in in_degree.items() if deg == 0])
    visited = 0
    while ready:
        tid = ready.popleft()
        visited += 1
        for child in children[tid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                ready.append(child)
    if visited != len(by_id):
        raise ValueError("Dependency graph contains a cycle")


def build_plan_from_lines(steps: str, lines: Iterable[str]) -> Plan:
    """Parse dry-run stdout lines into a validated ``Plan`` with dependencies and components."""
    tasks: list[Task] = []
    seen_ids: set[str] = set()
    order = 0
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("== "):
            continue
        if line.startswith("p4_B6: missing "):
            print(f"warning: {line}", file=sys.stderr, flush=True)
            continue
        task = parse_command_line(line, order)
        if task.id in seen_ids:
            raise ValueError(f"Duplicate task id in plan: {task.id!r}")
        seen_ids.add(task.id)
        tasks.append(task)
        order += 1

    r1_by_run: dict[str, str] = {}
    folds_by_run: dict[str, dict[int, str]] = {}
    for task in tasks:
        if task.kind != "fit":
            continue
        if task.fold is None:
            r1_by_run[task.run] = task.id
        else:
            folds_by_run.setdefault(task.run, {})[task.fold] = task.id

    for task in tasks:
        if task.kind == "fit" and task.refit_from is not None:
            dep = r1_by_run.get(task.refit_from)
            if dep is None:
                raise ValueError(
                    f"Refit {task.id!r} requires --run {task.refit_from!r}, which is missing"
                )
            task.deps = [dep]
        elif task.kind == "assembly":
            folds = folds_by_run.get(task.run, {})
            missing = [k for k in range(5) if k not in folds]
            if missing:
                raise ValueError(
                    f"Assembly {task.id!r} is missing fold fits {missing} for {task.run!r}"
                )
            task.deps = [folds[k] for k in range(5)]
        else:
            task.deps = []

    _validate_acyclic(tasks)
    connected_components(tasks)
    return Plan(steps=steps, tasks=tasks)


def build_plan(steps: str | Iterable[str], env: dict[str, str] | None = None,
               cwd: Path = ROOT) -> Plan:
    """Run ``scripts/run_v4_cpu.sh`` with ``P4_DRYRUN=1`` and build the dependency plan."""
    step_str = steps if isinstance(steps, str) else " ".join(steps)
    lines = dry_run(step_str, env=env, cwd=cwd)
    return build_plan_from_lines(step_str, lines)


def assign_shards(tasks: list[Task], total_shards: int) -> list[list[Task]]:
    """Partition ``tasks`` into ``total_shards`` balanced buckets without splitting components.

    Components are sorted by name and placed greedily into the shard with the fewest fits so far
    (tie-breaking by the lowest shard index). Every connected component stays whole, so no
    dependency ever crosses a shard boundary.
    """
    if total_shards < 1:
        raise ValueError(f"total_shards must be >= 1, got {total_shards}")
    components = connected_components(tasks)
    buckets: list[list[Task]] = [[] for _ in range(total_shards)]
    fit_loads = [0] * total_shards
    for _, comp_tasks in components:
        fit_count = sum(1 for task in comp_tasks if task.kind == "fit")
        target = min(range(total_shards), key=lambda idx: (fit_loads[idx], idx))
        buckets[target].extend(comp_tasks)
        fit_loads[target] += fit_count
    for bucket in buckets:
        bucket.sort(key=lambda task: task.order)
    return buckets


def select_shard(plan: Plan, shard_index: int, total_shards: int) -> Plan:
    """Return a sub-plan containing only the components assigned to 1-based ``shard_index``."""
    if total_shards < 1 or shard_index < 1 or shard_index > total_shards:
        raise ValueError(f"Invalid shard {shard_index}/{total_shards} (expected 1 <= I <= K)")
    buckets = assign_shards(plan.tasks, total_shards)
    return Plan(steps=plan.steps, tasks=buckets[shard_index - 1])


def _priorities(tasks: list[Task]) -> dict[str, tuple[int, int, int]]:
    """Compute scheduling priorities: longest chain of fits first, then chain length, then order.

    R1 fits that unlock a refit have fit-chain depth 2 and start before standalone fits (depth 1),
    so refits are unlocked early and do not sit at the tail of the run.
    """
    by_id = {task.id: task for task in tasks}
    children: dict[str, list[str]] = {task.id: [] for task in tasks}
    for task in tasks:
        for dep in task.deps:
            children[dep].append(task.id)

    fit_depth: dict[str, int] = {}
    node_depth: dict[str, int] = {}

    def compute(tid: str) -> tuple[int, int]:
        if tid in fit_depth:
            return fit_depth[tid], node_depth[tid]
        task = by_id[tid]
        own_fit = 1 if task.kind == "fit" else 0
        if not children[tid]:
            fit_depth[tid] = own_fit
            node_depth[tid] = 1
        else:
            child_scores = [compute(child) for child in children[tid]]
            fit_depth[tid] = own_fit + max(score[0] for score in child_scores)
            node_depth[tid] = 1 + max(score[1] for score in child_scores)
        return fit_depth[tid], node_depth[tid]

    priorities: dict[str, tuple[int, int, int]] = {}
    for task in tasks:
        f_depth, n_depth = compute(task.id)
        priorities[task.id] = (-f_depth, -n_depth, task.order)
    return priorities


def run_plan(plan: Plan, jobs: int, *, cwd: Path = ROOT, env: dict[str, str] | None = None,
             log_dir: Path | None = None, heartbeat_s: float = DEFAULT_HEARTBEAT_S) -> dict:
    """Execute ``plan`` with up to ``jobs`` concurrent processes and dependency tracking."""
    if jobs < 1:
        raise ValueError(f"jobs must be >= 1, got {jobs}")
    if heartbeat_s <= 0:
        raise ValueError(f"heartbeat_s must be > 0, got {heartbeat_s}")

    child_env = dict(os.environ if env is None else env)
    child_env["PFE_THREADS"] = "1"
    resolved_log_dir = Path(log_dir) if log_dir is not None else default_log_dir(
        child_env.get("PFE_DATASET"), root=cwd
    )
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    by_id = plan.by_id()
    dependents: dict[str, list[str]] = {task.id: [] for task in plan.tasks}
    remaining_deps: dict[str, set[str]] = {task.id: set(task.deps) for task in plan.tasks}
    for task in plan.tasks:
        for dep in task.deps:
            dependents[dep].append(task.id)

    priorities = _priorities(plan.tasks)
    state: dict[str, str] = {task.id: "waiting" for task in plan.tasks}
    ready: list[tuple[tuple[int, int, int], str]] = []
    for task in plan.tasks:
        if not task.deps:
            heapq.heappush(ready, (priorities[task.id], task.id))

    running: dict[str, tuple[subprocess.Popen, float]] = {}
    done_ids: list[str] = []
    failed_ids: list[str] = []
    skipped_ids: list[str] = []

    started_all = time.monotonic()
    last_heartbeat = started_all
    poll_sleep = min(0.05, heartbeat_s / 4.0)

    def skip_dependents(root_tid: str, root_status: str) -> None:
        queue = deque([(child, root_tid, root_status) for child in dependents[root_tid]])
        while queue:
            child, cause, cause_status = queue.popleft()
            if state[child] != "waiting":
                continue
            state[child] = "skipped"
            skipped_ids.append(child)
            print(
                f"{_utc_now()} SKIP {child} (dependency {cause} {cause_status})",
                flush=True,
            )
            for grand in dependents[child]:
                queue.append((grand, child, "skipped"))

    try:
        while running or ready:
            while len(running) < jobs and ready:
                _, tid = heapq.heappop(ready)
                if state[tid] != "waiting":
                    continue
                task = by_id[tid]
                log_path = resolved_log_dir / task.log_name
                try:
                    with log_path.open("w", encoding="utf-8") as log_fh:
                        proc = subprocess.Popen(
                            task.argv,
                            cwd=cwd,
                            env=child_env,
                            stdin=subprocess.DEVNULL,
                            stdout=log_fh,
                            stderr=subprocess.STDOUT,
                        )
                except OSError as error:
                    log_path.write_text(f"Failed to launch command: {error}\n", encoding="utf-8")
                    state[tid] = "failed"
                    failed_ids.append(tid)
                    print(
                        f"{_utc_now()} END {tid} rc=127 0.00m (launch error: {error})",
                        flush=True,
                    )
                    skip_dependents(tid, "failed")
                    continue

                state[tid] = "running"
                running[tid] = (proc, time.monotonic())
                print(
                    f"{_utc_now()} START {tid} [running={len(running)}/{jobs}]",
                    flush=True,
                )

            if not running:
                continue

            finished: list[tuple[str, int, float]] = []
            for tid, (proc, t0) in list(running.items()):
                rc = proc.poll()
                if rc is not None:
                    finished.append((tid, rc, time.monotonic() - t0))

            if finished:
                for tid, rc, elapsed_s in finished:
                    running.pop(tid, None)
                    elapsed_min = elapsed_s / 60.0
                    print(
                        f"{_utc_now()} END {tid} rc={rc} {elapsed_min:.2f}m",
                        flush=True,
                    )
                    if rc == 0:
                        state[tid] = "done"
                        done_ids.append(tid)
                        for child in dependents[tid]:
                            if state[child] != "waiting":
                                continue
                            remaining_deps[child].discard(tid)
                            if not remaining_deps[child]:
                                heapq.heappush(ready, (priorities[child], child))
                    else:
                        state[tid] = "failed"
                        failed_ids.append(tid)
                        skip_dependents(tid, "failed")
            else:
                time.sleep(poll_sleep)

            now = time.monotonic()
            if running and (now - last_heartbeat) >= heartbeat_s:
                waiting_count = sum(1 for st in state.values() if st == "waiting")
                print(
                    f"{_utc_now()} HEARTBEAT running={len(running)} done={len(done_ids)} "
                    f"failed={len(failed_ids)} skipped={len(skipped_ids)} waiting={waiting_count}",
                    flush=True,
                )
                last_heartbeat = now
    finally:
        # Clean up any child processes if interrupted (e.g., Ctrl-C or runtime signal).
        for proc, _ in running.values():
            if proc.poll() is None:
                proc.terminate()
        for proc, _ in running.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    stranded = [tid for tid, st in state.items() if st == "waiting"]
    if stranded:
        raise RuntimeError(f"Queue stopped with tasks still waiting: {stranded}")

    total_min = (time.monotonic() - started_all) / 60.0
    print(
        f"{_utc_now()} SUMMARY total={len(plan.tasks)} done={len(done_ids)} "
        f"failed={len(failed_ids)} skipped={len(skipped_ids)} elapsed={total_min:.2f}m",
        flush=True,
    )
    if failed_ids:
        print(f"Failed tasks ({len(failed_ids)}): {', '.join(failed_ids)}", flush=True)
    if skipped_ids:
        print(f"Skipped tasks ({len(skipped_ids)}): {', '.join(skipped_ids)}", flush=True)

    return {
        "total": len(plan.tasks),
        "done": done_ids,
        "failed": failed_ids,
        "skipped": skipped_ids,
        "elapsed_min": total_min,
        "log_dir": str(resolved_log_dir),
        "returncode": 1 if (failed_ids or skipped_ids) else 0,
    }


def _print_plan_summary(plan: Plan, shard: tuple[int, int] | None = None) -> None:
    counts = plan.summary()
    prefix = f"Shard {shard[0]}/{shard[1]} plan" if shard else "Plan"
    print(
        f"{prefix} ({plan.steps}): {counts['fits']} fits, {counts['assemblies']} assemblies, "
        f"{counts['refits']} refits, {counts['dependencies']} dependencies "
        f"({counts['components']} components, {counts['total']} commands total)",
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dependency-aware queue for Phase 4 response-model fits."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Parse dry-run commands and print dependency counts.")
    p_plan.add_argument("--steps", default=DEFAULT_STEPS,
                        help="Space-separated Phase 4 steps for scripts/run_v4_cpu.sh.")
    p_plan.add_argument("--shard", type=parse_shard, default=None,
                        help="Optional 1-based shard I/K to inspect.")
    p_plan.add_argument("--json", dest="json_path", type=Path, default=None,
                        help="Write the full plan to this JSON file.")

    p_run = sub.add_parser("run", help="Run the Phase 4 dependency plan in parallel.")
    p_run.add_argument("--steps", default=DEFAULT_STEPS,
                       help="Space-separated Phase 4 steps for scripts/run_v4_cpu.sh.")
    p_run.add_argument("--jobs", type=parse_jobs, default="auto",
                       help="Max concurrent commands (positive integer or 'auto').")
    p_run.add_argument("--shard", type=parse_shard, default=None,
                       help="Optional 1-based shard I/K (keeps connected components whole).")
    p_run.add_argument("--log-dir", type=Path, default=None,
                       help="Override log directory (default: results/$PFE_DATASET/_p4_logs).")
    p_run.add_argument("--heartbeat", type=float, default=DEFAULT_HEARTBEAT_S,
                       help="Heartbeat interval in seconds while commands run (default: 20).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = build_plan(args.steps)
    if args.shard is not None:
        plan = select_shard(plan, args.shard[0], args.shard[1])

    if args.command == "plan":
        _print_plan_summary(plan, shard=args.shard)
        if args.json_path is not None:
            args.json_path.parent.mkdir(parents=True, exist_ok=True)
            args.json_path.write_text(json.dumps(plan.to_dict(), indent=2) + "\n", encoding="utf-8")
        return 0

    _print_plan_summary(plan, shard=args.shard)
    outcome = run_plan(
        plan,
        args.jobs,
        log_dir=args.log_dir,
        heartbeat_s=args.heartbeat,
    )
    return outcome["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
