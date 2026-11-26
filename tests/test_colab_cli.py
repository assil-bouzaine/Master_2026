"""Check the Colab CLI lifecycle with local fixtures and a fake Colab client.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_colab_cli
"""
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import tarfile
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts import colab_cli as cli

SCRATCH = cli.ROOT / "results" / "_agents" / "tmp" / "T37"
USAGE = b"Current balance: 200.00 compute units\nUsage rate: 3.09/hr\nActive assignments: 1\n"
MODEL = "AMD EPYC 7B13"
SECRET = "hf_fixture_secret"


class FakeColab:
    """Record commands and stand in for a VM, including a binary SSH transfer."""

    def __init__(self):
        self.calls = []
        self.sessions = set()
        self.uploads = {}
        self.pid = 12345
        self.remote_pids = b""
        self.archive = b""
        self.checksum_ok = True

    def __call__(self, args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, timeout=60):
        assert stdin == subprocess.DEVNULL
        self.calls.append(args)
        action = args[0]
        if action == "status":
            if args[2] in self.sessions:
                return b"Status: IDLE\n"
            return b"Session not found.\n"
        if action == "new":
            self.sessions.add(args[2])
            return b"[colab] Session READY.\n"
        if action == "stop":
            self.sessions.discard(args[2])
            return b"[colab] Session terminated.\n"
        if action == "usage":
            return USAGE
        if action == "upload":
            self.uploads[args[4]] = Path(args[3]).read_bytes()
            return b""
        if action == "exec":
            assert timeout is None
            stdout.write(b"old local line\nlast local line\n")
            return SimpleNamespace(pid=self.pid)
        assert action == "ssh" and args[3] == "--", args
        command = args[4]
        if command == cli.PROBE:
            return f"nproc=24\ncpu_model={MODEL}\nmem_gb=32.0\ngpu=NVIDIA L4\n".encode()
        if command == "mkdir -p /content/input":
            return b""
        if command.startswith("md5sum "):
            path = shlex.split(command)[1]
            digest = hashlib.md5(self.uploads[path]).hexdigest() if self.checksum_ok else "wrong"
            return f"{digest}  {path}\n".encode()
        if command.startswith("tar czf - "):
            stdout.write(self.archive)
            return None
        if command.startswith("pgrep"):
            return self.remote_pids
        if command == f"touch {cli.PULLED_FLAG}":
            self.pulled = True
            return b""
        if command.startswith("uptime"):
            return b"up 2 hours\nRemote runner PIDs\n" + self.remote_pids + b'{"exit": 0}\n'
        if command.startswith("if [ -f ") and "tail -n" in command:
            return f"last remote line {SECRET}\n".encode()
        raise AssertionError(f"Unexpected command: {args}")


def run(*args):
    with redirect_stdout(io.StringIO()) as stdout:
        cli.main(list(args))
    return stdout.getvalue()


def refuses(*args, contains=None):
    try:
        run(*args)
    except SystemExit as error:
        if contains is not None:
            assert contains in str(error), error
        return error.code
    raise AssertionError(f"Accepted {args}")


def test_up():
    expected = {"cpu": [], "highmem": ["--high-mem"], "v5e1": ["--tpu", "v5e1"],
                "l4": ["--gpu", "L4"], "a100": ["--gpu", "A100"], "t4": ["--gpu", "T4"]}
    fake = FakeColab()
    with patch.object(cli, "run_colab", fake):
        for runtime, flags in expected.items():
            fake.calls.clear()
            printed = run("up", runtime, "--runtime", runtime, "--require-cpu-model", MODEL)
            assert fake.calls == [["status", "-s", runtime], ["new", "-s", runtime, *flags],
                                  ["ssh", "-s", runtime, "--", cli.PROBE], ["usage"]]
            machine = json.loads((cli.STAGE / runtime / "machine.json").read_text())
            assert json.loads(printed) == machine
            assert machine == dict(runtime=runtime, nproc=24, cpu_model=MODEL, mem_gb=32.0,
                                   gpu="NVIDIA L4", rate_per_hour=3.09, balance=200.0,
                                   utc=machine["utc"])
            assert datetime.fromisoformat(machine["utc"]).utcoffset() == timedelta()
        fake.calls.clear()
        assert refuses("up", "mismatch", "--runtime", "v5e1", "--require-cpu-model", "different") == 1
        assert fake.calls[-1] == ["stop", "-s", "mismatch"] and ["usage"] not in fake.calls
        assert not (cli.STAGE / "mismatch" / "machine.json").exists()
        fake.calls.clear()
        refuses("up", "cpu", "--runtime", "cpu", contains="already exists")
        assert fake.calls == [["status", "-s", "cpu"]]
    print("  1. Six runtime flag sets, machine profiles and immediate stop on a CPU mismatch.")


def tiny_bundle(stage, slim):
    assert not slim
    dataset = stage / "dataset"
    dataset.mkdir()
    with zipfile.ZipFile(dataset / "cpu_bundle.zip", "w") as bundle:
        bundle.writestr("requirements.txt", "")
    return dataset


def check_heartbeat(launcher, vm, runner, log, env):
    for folder in ("pfe", "work"):
        (vm / folder).mkdir(parents=True, exist_ok=True)
    log = vm / log
    last_line = f"still working {SECRET}" if "HF_TOKEN" in env else "still working"
    with (patch("subprocess.run") as unzip, patch("subprocess.Popen") as popen,
          patch.object(os, "cpu_count", return_value=12), redirect_stdout(io.StringIO()) as stdout):
        def spawn(command, *, cwd, env, stdout, stderr):
            assert command == ["python3", str(vm / "pfe" / runner)]
            assert cwd == vm / "pfe"
            assert stderr == subprocess.STDOUT
            for key, value in expected.items():
                assert env[key] == value
            assert stdout.name == str(log)

            def wait(timeout):
                assert timeout == 15
                if not log.stat().st_size:
                    stdout.write(f"earlier line\n{last_line}\n")
                    stdout.flush()
                    raise subprocess.TimeoutExpired(command, timeout)
                return 7

            return SimpleNamespace(wait=wait)

        expected = {key: value.replace("/content", str(vm)) for key, value in env.items()}
        popen.side_effect = spawn
        source = launcher.read_text().replace("/content", str(vm))
        (vm / ".pulled").touch()       # a flag left by an earlier job: the launcher must remove it
        sleeps = []

        def sleep(seconds):            # the keep-alive waits for the final pull's flag
            sleeps.append(seconds)
            assert not (vm / ".pulled").exists() or len(sleeps) > 1
            (vm / ".pulled").touch()

        with patch("time.sleep", side_effect=sleep):
            exec(compile(source, str(launcher), "exec"), {})
        assert sleeps == [30], sleeps
        unzip.assert_called_once()
        assert unzip.call_args.args[0][:2] == ["unzip", "-oq"]
        popen.assert_called_once()
    heartbeat, exit_line, keepalive, done = stdout.getvalue().splitlines()
    assert keepalive.endswith("KEEPALIVE job ended, waiting for the final pull") and done == "keepalive done"
    timestamp, last = heartbeat.split(" ", 1)
    assert datetime.fromisoformat(timestamp).utcoffset() == timedelta()
    assert last == ("still working <redacted>" if "HF_TOKEN" in env else last_line)
    assert exit_line == f"{Path(runner).name} exit 7"


def test_push_cpu(root):
    fake = FakeColab()
    with (patch.object(cli, "run_colab", fake), patch.object(cli, "process_start", return_value=100),
          patch.object(cli.kaggle_cpu, "bundle", side_effect=tiny_bundle) as bundle):
        output = run("push-cpu", "cpu-job", "--steps", "p4_B1 p4_B2", "--budget", "3.5",
                     "--env", "P4_CONFIRMED=1", "P4_PARALLEL=$(nproc)", "--env", f"HF_TOKEN={SECRET}",
                     "--full")
        stage = cli.STAGE / "cpu-job"
        bundle.assert_called_once_with(stage=stage, slim=False)
        assert fake.calls[-1] == ["exec", "-s", "cpu-job", "-f", str(stage / "launch.py"),
                                  "--timeout", "3600"]
        assert "Started cpu job" in output and SECRET not in output
        with zipfile.ZipFile(io.BytesIO(fake.uploads["/content/input/cpu_bundle.zip"])) as code:
            assert code.read(cli.RUNNER.as_posix()) == (cli.ROOT / cli.RUNNER).read_bytes()
        with zipfile.ZipFile(io.BytesIO(fake.uploads["/content/input/state.zip"])) as state:
            assert not state.namelist()
        job = json.loads((stage / "job.json").read_text())
        assert job["kind"] == "cpu" and job["pid"] == fake.pid and job["pid_start_ticks"] == 100
        assert job["env"]["P4_PARALLEL"] == "$(nproc)"
        assert job["bundle_md5"] == hashlib.md5(fake.uploads["/content/input/cpu_bundle.zip"]).hexdigest()
        before = fake.calls.copy()
        refuses("push-cpu", "cpu-job", "--steps", "p4_B3", contains="still running")
        assert fake.calls == before
        output = run("log", "cpu-job", "-n", "1")
        assert "last remote line <redacted>" in output and "last local line" in output
        assert SECRET not in output and "old local line" not in output
    (root / "work").mkdir(parents=True)
    old_status = root / "work" / cli.STATUS_NAME
    old_status.touch()
    check_heartbeat(stage / "launch.py", root, cli.RUNNER.as_posix(), "work/launch.out",
                    dict(KAGGLE_INPUT="/content/input", KAGGLE_WORK="/content/work",
                         PFE_CODE="/content/pfe", PIN_TARGET="/content/pins", PFE_STATE="/content/pfe_state",
                         PIP_ONLINE="1", BUDGET_H="3.5", SYNC_S="300", STEPS="p4_B1 p4_B2",
                         P4_CONFIRMED="1", P4_PARALLEL="12", HF_TOKEN=SECRET))
    assert not old_status.exists()
    print("  2. CPU bundle, MD5 checks, private overrides, dispatcher heartbeat and duplicate push guard.")


def test_push_gpu(root):
    fake = FakeColab()
    (root / "src").mkdir(parents=True)
    newest = root / "src" / "latest.py"
    newest.touch()
    archive = root / "gpu_bundle.zip"
    with (patch.object(cli, "ROOT", root), patch.object(cli, "run_colab", fake),
          patch.object(cli, "process_start", return_value=None)):
        refuses("push-gpu", "gpu-job", "--steps", "chronos2", contains="is missing")
        archive.write_bytes(b"GPU bundle fixture")
        os.utime(archive, ns=(0, 0))
        refuses("push-gpu", "gpu-job", "--steps", "chronos2", contains="older than src/latest.py")
        assert not fake.calls
        os.utime(archive, ns=(newest.stat().st_mtime_ns, newest.stat().st_mtime_ns))
        fake.checksum_ok = False
        refuses("push-gpu", "gpu-job", "--steps", "chronos2", contains="MD5 check failed")
        assert not (cli.STAGE / "gpu-job" / "job.json").exists()
        fake.checksum_ok = True
        run("push-gpu", "gpu-job", "--steps", "chronos2")
        stage = cli.STAGE / "gpu-job"
        assert fake.calls[-3:] == [["upload", "-s", "gpu-job", str(archive), "/content/gpu_bundle.zip"],
                                   ["ssh", "-s", "gpu-job", "--", "md5sum /content/gpu_bundle.zip"],
                                   ["exec", "-s", "gpu-job", "-f", str(stage / "launch.py"),
                                    "--timeout", "3600"]]
        run("status", "gpu-job")
        assert "nvidia-smi --query-gpu=name,utilization.gpu" in fake.calls[-1][4]
    check_heartbeat(stage / "launch.py", root / "vm", cli.GPU_RUNNER.as_posix(), "launch.out",
                    dict(PFE_DATASET="v4", PFE_DRIVE="/content/persist", STEPS="chronos2"))
    print("  3. GPU rejects missing, stale and mismatched bundles and launches a verified bundle.")


def test_v5_cpu(root):
    """Carry the v5 choice from push to the launcher and back through CPU pull."""
    fake = FakeColab()

    def bundle_v5(stage, slim, dataset):
        assert dataset == "v5" and slim
        return tiny_bundle(stage, slim=False)

    with (patch.object(cli, "run_colab", fake), patch.object(cli, "process_start", return_value=None),
          patch.object(cli.kaggle_cpu, "bundle", side_effect=bundle_v5) as bundle):
        run("push-cpu", "v5-smoke", "--dataset", "v5", "--steps", "hgnn_smoke", "--budget", "1")
        stage = cli.STAGE / "v5-smoke"
        bundle.assert_called_once_with(stage=stage, slim=True, dataset="v5")
        launcher = (stage / "launch.py").read_text()
        assert "'PFE_DATASET': 'v5'" in launcher and "'STEPS': 'hgnn_smoke'" in launcher
        assert "'BUDGET_H': '1.0'" in launcher
        compile(launcher, "v5-launcher", "exec")
        job = json.loads((stage / "job.json").read_text())
        assert job["env"]["PFE_DATASET"] == "v5"
        fake.archive = make_tgz("work/run_kaggle_cpu.log")
        with patch.object(cli.kaggle_cpu, "pull") as shared_pull:
            run("pull", "v5-smoke")
            assert shared_pull.call_args.kwargs["dataset"] == "v5"
            assert shared_pull.call_args.kwargs["stage"] == stage
    # Only inspect the smoke launcher's text. Never execute the smoke step locally.
    pattern = cli.RUNNER_PATTERNS["cpu"]
    assert all(re.search(pattern, f"bash scripts/run_{ds}_cpu.sh") for ds in ("v4", "v5"))
    print("  6. v5 CPU push records dataset and steps; pull selects v5 and both dispatchers are recognised.")


def make_tgz(member=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        if member is not None:
            content = b"portable results\n"
            info = tarfile.TarInfo(member)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return stream.getvalue()


def test_pull_stop():
    fake = FakeColab()
    fake.sessions.add("cpu-job")
    cpu_stage = cli.STAGE / "cpu-job"
    fake.archive = make_tgz("work/run_kaggle_cpu.log")

    def cpu_import(*, stage, download):
        assert stage == cpu_stage
        destination = stage / "test_import"
        download(destination)
        assert (destination / cli.LOG_NAME).read_bytes() == b"portable results\n"

    with (patch.object(cli, "run_colab", fake), patch.object(cli, "process_start", return_value=None),
          patch.object(cli.kaggle_cpu, "pull", side_effect=cpu_import) as shared_pull):
        refuses("stop", "cpu-job", contains="Pull after the job ends")
        with patch.object(cli, "process_start", return_value=100):
            # The launcher cell lives on after the job (keep-alive until the final pull).
            refuses("stop", "cpu-job", contains="still alive")
        fake.remote_pids = b"555\n"         # the dispatcher still runs: a snapshot, not final
        run("pull", "cpu-job")
        assert fake.calls[-1][4].startswith("tar czf - ")   # no flag before the final pull
        refuses("stop", "cpu-job", contains="Pull after the job ends")

        status = run("status", "cpu-job")
        assert "Status: IDLE" in status
        assert "Local exec process ended" in status and "555" in status and '{"exit": 0}' in status
        assert "pgrep -f" in fake.calls[-1][4] and cli.STATUS_NAME in fake.calls[-1][4]
        refuses("push-cpu", "cpu-job", "--steps", "p4_B3", contains="still running")
        run("pull", "cpu-job")
        refuses("stop", "cpu-job", contains="Pull after the job ends")

        fake.remote_pids = b""
        run("pull", "cpu-job")
        assert fake.calls[-2][4] == "tar czf - -C /content work"
        assert fake.calls[-1][4] == f"touch {cli.PULLED_FLAG}"     # a final pull ends the keep-alive
        assert shared_pull.call_count == 3
        assert all(path.read_bytes() == fake.archive for path in cpu_stage.glob("pull_*.tgz"))
        job = json.loads((cpu_stage / "job.json").read_text())
        assert job["pull_after_exit"] and job["pull_utc"] > job["start_utc"]
        assert "Usage rate: 3.09/hr" in run("stop", "cpu-job")
        assert fake.calls[-2:] == [["stop", "-s", "cpu-job"], ["usage"]]

        with patch.object(cli.colab_pull, "main") as gpu_import:
            fake.archive = b"an invalid archive"
            refuses("pull", "gpu-job", contains="Could not read or extract")
            fake.archive = make_tgz()
            refuses("pull", "gpu-job", contains="No files")
            gpu_import.assert_not_called()
            fake.archive = make_tgz("results_gpu/v4/chronos2/predictions.parquet")
            run("pull", "gpu-job")
            assert fake.calls[-2][4] == "tar czf - -C /content/persist results_gpu"
            assert fake.calls[-1][4] == f"touch {cli.PULLED_FLAG}"
            arguments, = gpu_import.call_args.args
            assert arguments[0] == "--dir"
            folder = Path(arguments[1])
            assert folder.name == "results_gpu" and folder.parent.parent == cli.STAGE / "gpu-job"
            assert (folder / "v4/chronos2/predictions.parquet").read_bytes() == b"portable results\n"

        run("stop", "unrecorded", "--force")
        assert fake.calls[-2:] == [["stop", "-s", "unrecorded"], ["usage"]]
    print("  4. Tar snapshots reach both importers. Stop requires a final pull (after the remote exit); a final pull ends the keep-alive.")


def test_wrapper(root):
    with (patch.object(subprocess, "Popen") as spawn, patch.object(subprocess, "run") as foreground,
          (root / "fake_exec.log").open("wb") as output):
        foreground.return_value = SimpleNamespace(returncode=0, stdout=USAGE)
        assert cli.run_colab(["usage"]) == USAGE
        foreground.assert_called_once_with(["colab", "usage"], stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        args = ["exec", "-s", "name", "-f", "launch.py", "--timeout", "3600"]
        assert cli.run_colab(args, stdout=output, timeout=None) is spawn.return_value
        spawn.assert_called_once_with(["colab", *args], stdin=subprocess.DEVNULL, stdout=output,
                                      stderr=subprocess.STDOUT, start_new_session=True)
    print("  5. The subprocess wrapper detaches exec with no stdin and captures both output streams.")


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as folder, patch.object(cli, "STAGE", Path(folder) / "stage"):
        root = Path(folder)
        test_up()
        test_push_cpu(root / "cpu_vm")
        test_push_gpu(root / "gpu")
        test_pull_stop()
        test_wrapper(root)
        test_v5_cpu(root / "v5")
    print("test_colab_cli: all checks passed")


if __name__ == "__main__":
    main()
