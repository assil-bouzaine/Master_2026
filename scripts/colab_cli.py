"""Run the CPU and GPU steps on Colab from the terminal (analysis plan §5 and §14).

Keep the VM active with one blocking Colab cell per job. Save the machine profile
for the Phase 4 contrasts and pull the results before releasing the runtime.
CPU jobs can select v5 for the Hybrid-GNN smoke run (analysis plan v3 §3).
GPU jobs can select v5 and extraction settings for v5 plan R2.1.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import colab_pull, kaggle_cpu
from .colab_cpu import LOG_NAME, RUNNER, STATUS_NAME

ROOT = kaggle_cpu.ROOT
STAGE = ROOT / "results" / "_colab_cli"
RUNTIMES = {
    "cpu": [], "highmem": ["--high-mem"], "v5e1": ["--tpu", "v5e1"],
    "l4": ["--gpu", "L4"], "a100": ["--gpu", "A100"], "t4": ["--gpu", "T4"],
}
CPU, GPU = "/content/work", "/content/pfe/results_gpu"
PULLED_FLAG = "/content/.pulled"     # written by a final pull; ends the launcher's keep-alive
KEEPALIVE_S = 3 * 3600               # the most a finished job keeps its runtime busy
GPU_RUNNER = Path("scripts/colab_run.py")
LOGS = {"cpu": f"{CPU}/{LOG_NAME}", "gpu": f"{GPU}/run_colab.log"}
PULL = {"cpu": ("/content", "work"), "gpu": ("/content/persist", "results_gpu")}
# Bracket one letter so pgrep does not match the SSH shell carrying the pattern.
RUNNER_PATTERNS = {
    "cpu": ("unzip -oq /content/input/[c]pu_bundle.zip|/content/pfe/scripts/[k]aggle_cpu_run.py"
            "|bash scripts/[r]un_v[45]_cpu.sh"),
    "gpu": ("unzip -oq /content/[g]pu_bundle.zip|/content/pfe/scripts/[c]olab_run.py"
            "|bash scripts/[r]un_gpu.sh"),
}
PROBE = r"""export LC_ALL=C
printf 'nproc=%s\n' "$(nproc)"
lscpu | sed -n 's/^Model name:[[:space:]]*/cpu_model=/p'
awk '/^MemTotal:/ {printf "mem_gb=%.2f\n", $2 * 1024 / 1e9}' /proc/meminfo
if command -v nvidia-smi >/dev/null; then
    nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sed 's/^/gpu=/'
fi
"""
SECRET_KEYS = re.compile(r"TOKEN|PASS(WD|WORD|PHRASE)?|SECRET|CREDENTIAL|API_?KEY|ACCESS_?KEY|"
                         r"PRIVATE_?KEY|AUTH|COOKIE")
SECRET_VALUES = re.compile(r"://[^/\s]+:[^/\s]+@|\b(?:gh[pousr]_|github_pat_|hf_|sk-|xox[baprs]-)"
                           r"|-----BEGIN .*PRIVATE KEY-----|^eyJ")


def run_colab(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, timeout=60):
    """Return captured output, or the detached client for a long-running cell."""
    command = ["colab", *args]
    try:
        if args[0] == "exec":
            return subprocess.Popen(command, stdin=stdin, stdout=stdout, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        result = subprocess.run(command, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE,
                                timeout=timeout)
    except FileNotFoundError:
        sys.exit("colab executable not found on PATH")
    except subprocess.TimeoutExpired:
        sys.exit(f"colab {args[0]} timed out after {timeout} seconds")
    except OSError:
        sys.exit(f"Could not start colab {args[0]}")
    if result.returncode:
        sys.exit(f"colab {args[0]} failed (exit {result.returncode})")
    return result.stdout


def ssh(name, command, **kwargs):
    return run_colab(["ssh", "-s", name, "--", command], **kwargs)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def output_text(output):
    return output.decode("utf-8", errors="replace")


def write_private(path, content):
    """Replace local metadata atomically and keep environment values private."""
    with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as temporary:
        temporary.write(content)
    Path(temporary.name).replace(path)


def write_json(path, content):
    write_private(path, json.dumps(content, indent=2) + "\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def job_for(stage, required=False):
    job = read_json(stage / "job.json")
    if job and job["start_utc"] < read_json(stage / "machine.json").get("utc", ""):
        job = {}  # The name was reused after a stop. Keep its CPU resume state.
    if required and not job:
        sys.exit(f"No job recorded for {stage.name}.")
    return job


def process_start(pid):
    """Read the Linux process start tick, ignoring exited children awaiting reaping."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    fields = stat.rsplit(")", 1)[1].split()
    return int(fields[19]) if fields[0] not in ("Z", "X") else None


def exec_alive(job):
    if not job:
        return False
    ticks = process_start(job["pid"])
    return ticks is not None and ticks == job.get("pid_start_ticks", ticks)


def process_probe(kind):
    # pgrep returns 1 when there is no runner. SSH should still succeed.
    return f'pgrep -f {shlex.quote(RUNNER_PATTERNS[kind])}; rc=$?; [ "$rc" -le 1 ]'


def remote_running(name, kind):
    return bool(ssh(name, process_probe(kind)).strip())


def secret_values(env):
    secrets = set()
    for key, value in env.items():
        if SECRET_KEYS.search(key) or SECRET_VALUES.search(value):
            secrets.add(value)
            secrets.update(value.splitlines())
    secrets.discard("")
    return sorted(secrets, key=len, reverse=True)


def redact(text, secrets):
    if not secrets:
        return text
    return re.sub("|".join(map(re.escape, secrets)), "<redacted>", text)


def up(name, stage, runtime, required_model):
    # The CLI creates a new assignment even if it already tracks this name.
    if b"Status:" in run_colab(["status", "-s", name]):
        sys.exit(f"Colab session {name} already exists. Stop it before reusing its name.")
    ready = run_colab(["new", "-s", name, *RUNTIMES[runtime]], timeout=600)
    if b"[colab] Session READY." not in ready:
        sys.exit(f"Colab did not confirm that {name} was ready. Check its status.")
    try:
        fields = dict(line.split("=", 1) for line in output_text(ssh(name, PROBE)).splitlines()
                      if "=" in line)
        model = fields.get("cpu_model", "").strip()
        if not model:
            sys.exit("The Colab probe returned no CPU model.")
        if required_model is not None and model != required_model:
            print(f"CPU model {model!r} differs from the required model {required_model!r}.")
            raise SystemExit(1)
        usage = output_text(run_colab(["usage"]))
        balance = re.search(r"Current balance:\s*([\d.]+) compute units", usage)
        rate = re.search(r"Usage rate:\s*([\d.]+)/hr", usage)
        if not balance or not rate:
            sys.exit("Could not read the Colab compute balance and usage rate.")
        machine = dict(runtime=runtime, nproc=int(fields["nproc"]), cpu_model=model,
                       mem_gb=float(fields["mem_gb"]), gpu=fields.get("gpu"),
                       rate_per_hour=float(rate[1]), balance=float(balance[1]), utc=now())
        write_json(stage / "machine.json", machine)
    except (KeyError, ValueError, OSError, SystemExit) as error:
        print(output_text(run_colab(["stop", "-s", name])).rstrip())
        if isinstance(error, (KeyError, ValueError)):
            sys.exit("Could not read the Colab machine probe.")
        raise
    print(json.dumps(machine, indent=2))


def require_idle(name, stage):
    job = job_for(stage)
    if exec_alive(job) or (job and remote_running(name, job["kind"])):
        sys.exit(f"A job is still running for {name}. Check its status before pushing again.")


def upload(name, path, remote):
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "md5").hexdigest()
    run_colab(["upload", "-s", name, str(path), remote], timeout=1800)
    expected = ssh(name, f"md5sum {shlex.quote(remote)}").split()
    if not expected or expected[0] != digest.encode("ascii"):
        sys.exit(f"MD5 check failed for {path.name} on Colab.")
    return digest


def launcher_text(kind, steps, env):
    """Build one blocking cell that reports progress while the dispatcher runs."""
    parallel = ""
    if kind == "cpu":
        setup = """work = Path("/content/work")
work.mkdir(exist_ok=True)
(work / "run_status.json").unlink(missing_ok=True)
"""
        bundle, runner, log = "/content/input/cpu_bundle.zip", RUNNER, f"{CPU}/launch.out"
        if env.get("P4_PARALLEL") == "$(nproc)":
            parallel = 'env["P4_PARALLEL"] = str(os.cpu_count() or 1)\n'
    else:
        setup = 'Path("/content/persist").mkdir(exist_ok=True)\n'
        bundle, runner, log = "/content/gpu_bundle.zip", GPU_RUNNER, "/content/launch.out"
    return f"""# Colab keeps the kernel busy until the dispatcher finishes.
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

Path({PULLED_FLAG!r}).unlink(missing_ok=True)   # a new job waits for its own final pull
{setup}code = Path("/content/pfe")
subprocess.run(["unzip", "-oq", {bundle!r}, "-d", str(code)], check=True)
env = {{**os.environ, **{dict(env, STEPS=steps)!r}}}
{parallel}
log = Path({log!r})
secrets = {secret_values(env)!r}
with log.open("w") as out, log.open("rb") as reader:
    process = subprocess.Popen(["python3", str(code / {runner.as_posix()!r})], cwd=code, env=env,
                               stdout=out, stderr=subprocess.STDOUT)
    while True:
        try:
            exit_code = process.wait(timeout=15)
            break
        except subprocess.TimeoutExpired:
            size = reader.seek(0, os.SEEK_END)
            reader.seek(max(0, size - 4096))
            lines = reader.read().decode("utf-8", errors="replace").splitlines()
            last = lines[-1] if lines else "waiting for job output"
            if secrets:
                last = re.sub("|".join(map(re.escape, secrets)), "<redacted>", last)
            print(datetime.now(timezone.utc).isoformat(timespec="seconds"), last, flush=True)
print({runner.name!r}, "exit", exit_code, flush=True)
# Keep the kernel busy until a final pull has the results (colab_cli pull touches PULLED_FLAG):
# an idle runtime is reclaimed with its files (2026-11-24: shard 1 of Phase 4 was lost that way).
import time
flag, deadline = Path({PULLED_FLAG!r}), time.time() + {KEEPALIVE_S}
while not flag.exists() and time.time() < deadline:
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), "KEEPALIVE job ended, waiting for the final pull", flush=True)
    time.sleep(30)
print("keepalive done", flush=True)
"""


def start_job(name, stage, kind, steps, env, bundle_md5, export_metadata=None):
    launcher = stage / "launch.py"
    write_private(launcher, launcher_text(kind, steps, env))
    log = stage / "exec.log"
    log.touch(mode=0o600, exist_ok=True)
    started = now()
    with log.open("wb") as stream:
        process = run_colab(["exec", "-s", name, "-f", str(launcher), "--timeout", "3600"],
                            stdout=stream, timeout=None)
    job = dict(kind=kind, steps=steps, env=env, bundle_md5=bundle_md5, pid=process.pid,
               pid_start_ticks=process_start(process.pid), start_utc=started)
    if export_metadata:
        job["export_override"] = export_metadata
    write_json(stage / "job.json", job)
    print(f"Started {kind} job for {name} (local PID {process.pid}).")


def push_cpu(name, stage, steps, budget, assignments, full, export_override=None, dataset="v4"):
    """Stage CPU inputs and the dataset selection for v4 or the v5 smoke run (§3)."""
    if dataset == "v5" and export_override:
        sys.exit("Export overrides are not supported for dataset v5 yet.")
    require_idle(name, stage)
    overrides = kaggle_cpu.parse_env(assignments)
    if "PIP_ONLINE" in overrides:
        sys.exit("--env cannot override PIP_ONLINE: the runner controls it")
    bundle_options = {"export_override": export_override} if export_override else {}
    if dataset != "v4":
        bundle_options["dataset"] = dataset
    bundle_dir = kaggle_cpu.bundle(stage=stage, slim=not full, **bundle_options)
    bundle, state = bundle_dir / "cpu_bundle.zip", bundle_dir / "state.zip"
    export_metadata = {}
    with zipfile.ZipFile(bundle, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / RUNNER, RUNNER)
        for policy, folder in (export_override or {}).items():
            manifest = f"data/processed/kg/export_v4_{policy}/manifest.json"
            with archive.open(manifest) as source:
                manifest_md5 = hashlib.file_digest(source, "md5").hexdigest()
            export_metadata[policy] = {"path": str(folder), "manifest_md5": manifest_md5}
    if export_metadata:
        print(f"Export override metadata: {json.dumps(export_metadata)}")
    if not state.exists():
        with zipfile.ZipFile(state, "w"):
            pass
    ssh(name, "mkdir -p /content/input")
    digest = upload(name, bundle, "/content/input/cpu_bundle.zip")
    upload(name, state, "/content/input/state.zip")
    env = dict(KAGGLE_INPUT="/content/input", KAGGLE_WORK=CPU, PFE_CODE="/content/pfe",
               PIN_TARGET="/content/pins", PFE_STATE="/content/pfe_state", PIP_ONLINE="1",
               PFE_DATASET=dataset, BUDGET_H=str(budget), SYNC_S="300", **overrides)
    start_job(name, stage, "cpu", steps, env, digest, export_metadata=export_metadata)


def gpu_environment(dataset, assignments=()):
    """Validate GPU overrides before upload, including extraction settings (v5 plan R2.1)."""
    overrides = kaggle_cpu.parse_env(assignments)
    if "PIP_ONLINE" in overrides:
        sys.exit("--env cannot override PIP_ONLINE: the runner controls it")
    return {"PFE_DATASET": dataset, "PFE_DRIVE": "/content/persist", **overrides}


def push_gpu(name, stage, steps, dataset, assignments=()):
    env = gpu_environment(dataset, assignments)
    bundle = ROOT / "gpu_bundle.zip"
    rebuild = f"PFE_DATASET={dataset} .venv/bin/python scripts/make_gpu_bundle.py"
    if not bundle.is_file():
        sys.exit(f"gpu_bundle.zip is missing. Build it with {rebuild}")
    bundle_time = bundle.stat().st_mtime_ns
    newest = max((p for folder in ("src", "scripts") for p in (ROOT / folder).rglob("*.py")
                  if p.is_file()), key=lambda p: p.stat().st_mtime_ns, default=None)
    if newest and newest.stat().st_mtime_ns > bundle_time:
        sys.exit(f"gpu_bundle.zip is older than {newest.relative_to(ROOT)}. Rebuild it with {rebuild}")
    require_idle(name, stage)
    digest = upload(name, bundle, "/content/gpu_bundle.zip")
    start_job(name, stage, "gpu", steps, env, digest)


def log(name, stage, n):
    job = job_for(stage, required=True)
    if not n:
        return
    remote = LOGS[job["kind"]]
    secrets = secret_values(job["env"])
    command = f"if [ -f {remote} ]; then tail -n {n} {remote}; fi"
    print("Colab log")
    print(redact(output_text(ssh(name, command)).rstrip(), secrets))
    print("Local exec log")
    local = stage / "exec.log"
    if local.is_file():
        with local.open("rb") as stream:
            tail = subprocess.run(["tail", "-n", str(n)], stdin=stream, capture_output=True,
                                  check=True).stdout
        print(redact(output_text(tail).rstrip(), secrets))


def status(name, stage):
    print(output_text(run_colab(["status", "-s", name])).rstrip())
    job = job_for(stage)
    local = "unrecorded"
    if job:
        local = "alive" if exec_alive(job) else "ended"
    print(f"Local exec process {local}")
    machine = read_json(stage / "machine.json")
    kind = job.get("kind", "gpu" if machine.get("gpu") else "cpu")
    command = ("uptime\nprintf 'Remote runner PIDs (empty when stopped)\\n'\n"
               f"{process_probe(kind)} || exit $?\n")
    if kind == "gpu":
        command += ("if command -v nvidia-smi >/dev/null; then "
                    "nvidia-smi --query-gpu=name,utilization.gpu --format=csv; fi\n")
    else:
        remote = f"{CPU}/{STATUS_NAME}"
        command += f"if [ -f {remote} ]; then cat {remote}; fi\n"
    print(redact(output_text(ssh(name, command)).rstrip(), secret_values(job.get("env", {}))))


def pull(name, stage, exclude=()):
    job = job_for(stage, required=True)
    kind = job["kind"]
    # A snapshot qualifies for a normal stop only if both clients were done
    # before the download. Colab can show IDLE while the dispatcher is still running.
    # Final = the dispatcher has ended on Colab. The launcher cell stays alive afterwards on purpose
    # (keep-alive until this pull), so the local exec process is no longer part of the test.
    final = not remote_running(name, kind)
    root, folder = PULL[kind]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = stage / f"pull_{stamp}.tgz"
    extracted = stage / archive.stem
    with archive.open("xb") as destination:
        # A Phase 4 shard is about 4 GB (mostly per-start contributions), about 30 min at 2.4 MB/s:
        # 1800 s was too short (2026-11-24). Allow 4 hours.
        # --exclude leaves out files that can be rebuilt, e.g. the leave-wells-out folds'
        # per-start contributions (fold_*/contrib_seed_*.parquet, half of a Phase 4 shard): the
        # replay (src/models/response.py: replay) recomputes them exactly from the checkpoints.
        skip = "".join(f" --exclude={shlex.quote(pattern)}" for pattern in exclude)
        ssh(name, f"tar czf -{skip} -C {root} {folder}", stdout=destination, timeout=4 * 3600)
    try:
        with tarfile.open(archive, "r:gz") as source:
            members = source.getmembers()
            if not any(member.isfile() for member in members):
                sys.exit(f"No files in the Colab archive {archive.name}.")
            if any(Path(m.name).parts[:1] != (folder,) or ".." in Path(m.name).parts
                   for m in members):
                sys.exit(f"Unexpected paths in the Colab archive {archive.name}.")
            extracted.mkdir()
            source.extractall(extracted, members=members, filter="data")
    except (tarfile.TarError, EOFError, OSError):
        sys.exit(f"Could not read or extract the Colab archive {archive.name}.")
    result = extracted / folder
    failure = None
    if kind == "cpu":
        def download(destination):
            shutil.copytree(result, destination, dirs_exist_ok=True)

        captured = io.StringIO()
        try:
            with redirect_stdout(captured):
                # CPU imports do not use colab_pull.VERSIONS (the GPU importer is still v3/v4).
                dataset = job["env"].get("PFE_DATASET", "v4")
                options = {"dataset": dataset} if dataset != "v4" else {}
                kaggle_cpu.pull(stage=stage, download=download, **options)
        except SystemExit as error:
            if error.code != 1:
                raise
            # The shared CPU pull reports failed steps after it saves the results.
            failure = error
        finally:
            print(redact(captured.getvalue(), secret_values(job["env"])), end="")
    else:
        colab_pull.main(["--dir", str(result)])
    job["pull_utc"] = now()
    job["pull_after_exit"] = final
    if final:
        ssh(name, f"touch {PULLED_FLAG}")   # ends the launcher's keep-alive
    write_json(stage / "job.json", job)
    print(f"Pulled {archive}")
    if failure:
        raise failure


def stop(name, stage, force):
    if not force:
        job = job_for(stage)
        if exec_alive(job) and not job.get("pull_after_exit"):
            sys.exit("The local exec process is still alive. Wait for it to end or use --force.")
        if not job.get("pull_after_exit"):
            sys.exit("Pull after the job ends before stopping, or use --force.")
        if remote_running(name, job["kind"]):
            sys.exit("The Colab runner is still active. Wait, then pull again, or use --force.")
    print(output_text(run_colab(["stop", "-s", name])).rstrip())
    print(output_text(run_colab(["usage"])).rstrip())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("up", "push-cpu", "push-gpu", "log", "status", "pull", "stop"):
        commands = actions.add_parser(action)
        commands.add_argument("name")
        if action == "up":
            commands.add_argument("--runtime", choices=RUNTIMES, required=True)
            commands.add_argument("--require-cpu-model")
        elif action in ("push-cpu", "push-gpu"):
            commands.add_argument("--steps", required=True)
            commands.add_argument("--dataset", choices=("v4", "v5"), default="v4")
            commands.add_argument("--env", metavar="KEY=VALUE", nargs="+", action="extend", default=[])
            if action == "push-cpu":
                commands.add_argument("--export-override", action="append", default=[], metavar="POLICY=PATH",
                                      help="bundle a chosen graph export folder (repeatable)")
                commands.add_argument("--budget", type=float, default=23)
                commands.add_argument("--full", action="store_true")
        elif action == "log":
            commands.add_argument("-n", type=int, default=20)
        elif action == "stop":
            commands.add_argument("--force", action="store_true")
        elif action == "pull":
            commands.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                                  help="tar pattern of files to leave on Colab (repeatable)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.name):
        parser.error("NAME must start with a letter or digit and use only letters, digits, dots, underscores or hyphens")
    stage = STAGE / args.name
    if args.action == "log":
        if args.n < 0:
            parser.error("-n must be zero or greater")
        return log(args.name, stage, args.n)
    if args.action == "status":
        return status(args.name, stage)
    stage.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (stage / ".lock").open("a") as lock:
        # Serialize bundle staging, pulling and stopping for each named session.
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == "up":
            up(args.name, stage, args.runtime, args.require_cpu_model)
        elif args.action == "push-cpu":
            push_cpu(args.name, stage, args.steps, args.budget, args.env, args.full,
                     export_override=kaggle_cpu.parse_export_overrides(args.export_override), dataset=args.dataset)
        elif args.action == "push-gpu":
            push_gpu(args.name, stage, args.steps, args.dataset, args.env)
        elif args.action == "pull":
            pull(args.name, stage, exclude=args.exclude)
        else:
            stop(args.name, stage, args.force)


if __name__ == "__main__":
    main()
