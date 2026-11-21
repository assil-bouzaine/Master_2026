"""Check the Colab CPU path for analysis plan §5 and §14 without Drive or model fits.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_colab_cpu
"""
import ast
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import colab_cpu as colab, kaggle_cpu as local, kaggle_cpu_run as remote


def shell_from_cell(cell):
    assert cell.splitlines()[0] == "from google.colab import drive; drive.mount('/content/drive')"
    assert len(cell.splitlines()) == 2
    call = ast.parse(cell).body[-1].value
    assert ast.unparse(call.func) == "subprocess.run"
    assert {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords} == {"shell": True, "check": True}
    return ast.literal_eval(call.args[0])


def test_cell_and_push(root):
    stage, dataset = root / "stage", root / "stage" / "dataset"
    dataset.mkdir(parents=True)
    seed = "results_cpu/v4/saved/seed_0.json"
    for resumed in (False, True):
        with zipfile.ZipFile(dataset / "cpu_bundle.zip", "w") as archive:
            archive.writestr("requirements.txt", "")
        state = dataset / "state.zip"
        if resumed:
            with zipfile.ZipFile(state, "w") as archive:
                archive.writestr(seed, "{}")
        stdout = io.StringIO()
        with (patch.object(colab, "STAGE", stage), patch.object(local, "bundle", return_value=dataset) as bundle,
              patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run,
              redirect_stdout(stdout)):
            colab.main(["push", "--steps", "p4_B1 p4_B2conv", "--env", "P4_CONFIRMED=1"])
        bundle.assert_called_once_with(stage=stage)
        assert [call.args[0] for call in run.call_args_list] == [
            ["rclone", "copyto", str(dataset / name), f"gdrive:pfe_colab_cpu/input/{name}"]
            for name in ("cpu_bundle.zip", "state.zip")]
        with zipfile.ZipFile(dataset / "cpu_bundle.zip") as archive:
            assert archive.read(colab.RUNNER.as_posix()) == (local.ROOT / colab.RUNNER).read_bytes()
        with zipfile.ZipFile(state) as archive:
            assert archive.namelist() == ([seed] if resumed else [])

    cell = (stage / "colab_cell.txt").read_text()
    assert cell == stdout.getvalue()
    command = shlex.split(shell_from_cell(cell))
    assert command[:6] == ["unzip", "-oq", "/content/drive/MyDrive/pfe_colab_cpu/input/cpu_bundle.zip",
                           "-d", "/content/pfe", "&&"]
    assert command[-2:] == ["python3", "/content/pfe/scripts/kaggle_cpu_run.py"]
    assert set(command[command.index("&&", 6) + 1:-2]) == {
        "KAGGLE_INPUT=/content/drive/MyDrive/pfe_colab_cpu/input",
        "KAGGLE_WORK=/content/drive/MyDrive/pfe_colab_cpu/work", "PFE_CODE=/content/pfe",
        "PIN_TARGET=/content/pins", "PFE_STATE=/content/pfe_state", "PIP_ONLINE=1", "BUDGET_H=23",
        "SYNC_S=300", "STEPS=p4_B1 p4_B2conv", "P4_CONFIRMED=1"}
    with patch.object(local, "bundle") as bundle, patch.object(subprocess, "run") as run:
        for assignment, message in (("KAGGLE_WORK=/x", "cannot override KAGGLE_WORK"),
                                    ("PIP_ONLINE=0", "cannot override PIP_ONLINE"),
                                    ("broken", "expects KEY=VALUE")):
            try:
                colab.main(["push", "--env", assignment])
            except SystemExit as error:
                assert message in str(error)
            else:
                raise AssertionError(f"push accepted {assignment}")
        bundle.assert_not_called()
        run.assert_not_called()
    print("  1. Both archives go to the Colab input folder and the cell has the declared defaults.")


def test_shell_quoting(root):
    root.mkdir()
    code, inputs, work, bin_dir = (root / name for name in ("pfe code", "drive input", "drive work", "bin"))
    for folder in (inputs, work, bin_dir):
        folder.mkdir()
    status = work / colab.STATUS_NAME
    status.write_text("old status")
    stub = "import json, os; print(json.dumps({k: os.environ[k] for k in ('LABEL', 'EMPTY', 'STEPS', 'P4_PARALLEL')}))"
    with zipfile.ZipFile(inputs / "cpu_bundle.zip", "w") as archive:
        archive.writestr(colab.RUNNER.as_posix(), stub)
    (bin_dir / "python3").symlink_to(sys.executable)
    nproc = bin_dir / "nproc"
    nproc.write_text("#!/bin/sh\necho 7\n")
    nproc.chmod(0o755)
    label = "é='quoted' \"double\" \\ {brace} $USER $(echo expanded)\nnew line"
    overrides = {"LABEL": label, "EMPTY": "", "P4_PARALLEL": "$(nproc)"}
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    with patch.multiple(colab, CODE=code, INPUT=inputs, WORK=work):
        shell = shell_from_cell(colab.colab_cell("p4_B1 p4_B2", 3.5, overrides))
    result = subprocess.run(shell, shell=True, env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {"LABEL": label, "EMPTY": "", "STEPS": "p4_B1 p4_B2", "P4_PARALLEL": "7"}
    assert not status.exists() and (code / colab.RUNNER).is_file()
    print("  2. The shell preserves literal overrides and expands only the requested CPU count.")


def test_status_and_log():
    log = "".join(f"line {i}\n" for i in range(1, 8))
    complete = '{"failed_steps": [], "exit": 0, "budget_stop": false}\n'
    listing = ["rclone", "lsf", "gdrive:pfe_colab_cpu/work", "--files-only"]

    def result(text, code=0, stderr=""):
        return subprocess.CompletedProcess([], code, text, stderr)

    cases = [(["log", "-n", "2"], [result(log)], "line 6\nline 7\n"),
             (["status"], [result("run_kaggle_cpu.log\n"), result(log)], "running\n" + "".join(log.splitlines(True)[-5:])),
             (["status"], [result("run_status.json\nrun_kaggle_cpu.log\n"), result(complete)], complete),
             (["status"], [result("", code=3)], "running\n")]
    for args, responses, expected in cases:
        stdout = io.StringIO()
        with patch.object(subprocess, "run", side_effect=responses) as run, redirect_stdout(stdout):
            colab.main(args)
        assert stdout.getvalue() == expected
        if args == ["status"]:
            assert run.call_args_list[0].args[0] == listing
        if args[0] == "log" or len(responses) > 1:
            name = "run_status.json" if expected == complete else "run_kaggle_cpu.log"
            assert run.call_args.args[0] == ["rclone", "cat", f"gdrive:pfe_colab_cpu/work/{name}"]
    with patch.object(subprocess, "run", return_value=result("", code=7, stderr="private diagnostic")):
        try:
            colab.main(["status"])
        except SystemExit as error:
            assert "rclone lsf failed (exit 7)" in str(error) and "private diagnostic" not in str(error)
        else:
            raise AssertionError("status accepted a failed rclone request")
    print("  3. Status shows finished JSON or the last five lines, and rclone failures stop the command.")


def test_pull(root):
    fixture, stage, results = root / "fixture", root / "stage", root / "results"
    paths = {local.CPU_RESULTS / "finished" / "predictions.parquet": b"prediction fixture",
             local.CPU_RESULTS / "twin" / "slice" / "world_0.json": b"{}",
             local.CPU_RESULTS / "unfinished" / "seed_0.json": b"{}",
             Path(colab.LOG_NAME): b"session log\n",
             Path(colab.STATUS_NAME): b'{"failed_steps": [], "exit": 0, "budget_stop": false}'}
    for name, content in paths.items():
        path = fixture / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def download(destination):
        shutil.copytree(fixture, destination, dirs_exist_ok=True)

    def fake_run(cmd, **kwargs):
        if cmd[0] == "rclone":
            assert cmd == ["rclone", "copy", "gdrive:pfe_colab_cpu/work", str(stage / "output_incoming")]
            download(cmd[-1])
        else:
            assert cmd == [sys.executable, "-m", "src.models.evaluate", "finished"]
            assert kwargs["env"]["PFE_DATASET"] == "v4"
            assert kwargs["env"]["PFE_RESULTS"] == str(results.resolve())
        return subprocess.CompletedProcess(cmd, 0, "", "")

    pull = local.pull
    with (patch.object(colab, "STAGE", stage),
          patch.object(local, "pull", side_effect=lambda **kw: pull(results=results, **kw)) as shared_pull,
          patch.object(local, "download_output") as kaggle_download, patch.object(subprocess, "run", side_effect=fake_run) as run,
          redirect_stdout(io.StringIO()) as stdout):
        colab.main(["pull"])
        shared_pull.assert_called_once_with(stage=stage, download=colab.download_output)
        kaggle_download.assert_not_called()
        assert run.call_count == 2
    for name, content in paths.items():
        assert (stage / "output" / name).read_bytes() == content
        if name.is_relative_to(local.CPU_RESULTS):
            assert (stage / "state" / name).read_bytes() == content
    assert (results / "finished" / "predictions.parquet").read_bytes() == b"prediction fixture"
    assert (results / "twin" / "slice" / "world_0.json").read_bytes() == b"{}"
    assert not (results / "unfinished").exists()
    assert "twin (1 worlds)" in stdout.getvalue() and "session log" in stdout.getvalue()

    kaggle_stage = root / "kaggle"
    with (patch.object(local, "download_output", side_effect=download) as kaggle_download,
          patch.object(subprocess, "run", side_effect=fake_run) as run, redirect_stdout(io.StringIO())):
        pull(stage=kaggle_stage, results=results)
        kaggle_download.assert_called_once_with(kaggle_stage / "output_incoming")
        run.assert_called_once()
    print("  4. The shared pull merges state and copies a finished run and a twin, rescoring only the model run.")


def test_restore(root):
    inputs, state, work, results = (root / name for name in ("inputs", "state", "work", "results"))
    inputs.mkdir(parents=True)
    archived = local.CPU_RESULTS / "fixture"
    with zipfile.ZipFile(inputs / "state.zip", "w") as archive:
        for name in ("zip_only", "zip_then_input", "all_three"):
            archive.writestr((archived / name).as_posix(), "state.zip")
    for base, names, text in ((inputs / "extracted", ["zip_then_input", "all_three"], "input"),
                              (work, ["all_three", "work_only"], "work")):
        (base / archived).mkdir(parents=True)
        for name in names:
            (base / archived / name).write_text(text)
    with patch.multiple(remote, INPUT=inputs, STATE=state, WORK=work, RESULTS=results), patch.object(remote, "log"):
        remote.restore()
    restored = {p.name: p.read_text() for p in (results / "fixture").iterdir()}
    assert restored == {"zip_only": "state.zip", "zip_then_input": "input", "all_three": "work", "work_only": "work"}
    print("  5. Restore loads state.zip, then extracted inputs, then the newest Drive copy.")


def test_pins(root):
    inputs, code, pins = (root / name for name in ("inputs", "code", "pins"))
    inputs.mkdir(parents=True)
    code.mkdir()
    (code / "requirements.txt").write_text("numpy==1.0\npandas==2.0  # pin\nunrelated==3.0\n")
    wheel = inputs / "fixture.whl"
    wheel.touch()
    assert remote.PINNED == local.PINNED
    output = [subprocess.CompletedProcess([], 0, "", ""),
              subprocess.CompletedProcess([], 0, "numpy==1.0\npandas==2.0\n", "")]

    def install_command(online):
        with (patch.dict(os.environ, {"PIP_ONLINE": online}), patch.multiple(
                remote, INPUT=inputs, CODE=code, PINS=pins, CHECKED=["numpy", "pandas"]),
              patch.object(remote, "log"), patch.object(subprocess, "run", side_effect=output) as run):
            remote.install()
            pip, check = run.call_args_list
            assert check.args[0][:2] == [sys.executable, "-c"]
            assert check.kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(pins)
            assert "src.models.pastas_baseline" in check.args[0][2]
            return pip.args[0]

    command = [sys.executable, "-m", "pip", "install"]
    assert install_command("1") == [*command, "--target", str(pins), "--upgrade", "numpy==1.0", "pandas==2.0"]
    assert install_command("0") == [*command, "-q", "--no-index", "--no-deps", "--upgrade", "--target", str(pins), str(wheel)]
    print("  6. Online pip gets the two matching pins and Kaggle keeps its offline wheel command.")


def test_parallel_batches():
    script = (local.ROOT / "scripts" / "run_v4_cpu.sh").read_text()
    enqueue = script[script.index("p4_enqueue() {"):].split("\n}\n", 1)[0] + "\n}\n"
    stand_ins = """
set -u
p4_regimes() { :; }
p4_wait() {
    echo "${#p4_pids[@]}"
    wait "${p4_pids[@]}"
    p4_pids=()
}
p4_pids=()
for _ in 1 2 3 4 5; do p4_enqueue || exit 1; done
p4_wait
"""
    env = {key: value for key, value in os.environ.items() if not key.startswith("P4_")}
    for settings, expected in (({}, ["4", "1"]), ({"P4_PARALLEL": "2"}, ["2", "2", "1"])):
        run = subprocess.run(["bash", "-c", enqueue + stand_ins], env={**env, **settings},
                             capture_output=True, text=True, check=True)
        assert run.stdout.splitlines() == expected
    invalid = subprocess.run(["bash", "-c", enqueue + stand_ins], env={**env, "P4_PARALLEL": "0"},
                             capture_output=True, text=True)
    assert invalid.returncode == 1 and "P4_PARALLEL must be a positive integer" in invalid.stderr
    assert not invalid.stdout
    print("  7. Phase 4 waits after four jobs by default and after two with a size-two batch.")


def main():
    with TemporaryDirectory() as folder:
        root = Path(folder)
        test_cell_and_push(root / "push")
        test_shell_quoting(root / "shell quoting")
        test_status_and_log()
        test_pull(root / "pull")
        test_restore(root / "restore")
        test_pins(root / "pins")
        test_parallel_batches()
    print("test_colab_cpu: all checks passed")


if __name__ == "__main__":
    main()
