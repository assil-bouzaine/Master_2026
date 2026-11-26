"""Check the Colab CPU path for analysis plan §5 and §14 without Drive or model fits.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_colab_cpu
"""
import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import colab_cpu as colab, kaggle_cpu as local, kaggle_cpu_run as remote


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
            full = ["--full"] if resumed else []
            colab.main(["push", "--steps", "p4_B1 p4_B2conv", "--env", "P4_CONFIRMED=1", *full])
        bundle.assert_called_once_with(stage=stage, slim=not resumed)
        assert [call.args[0] for call in run.call_args_list] == [
            ["rclone", "copyto", str(path), f"gdrive:pfe_colab_cpu/input/{path.name}"]
            for path in (dataset / "cpu_bundle.zip", state, stage / "run_colab_cpu.sh")]
        with zipfile.ZipFile(dataset / "cpu_bundle.zip") as archive:
            assert archive.read(colab.RUNNER.as_posix()) == (local.ROOT / colab.RUNNER).read_bytes()
        with zipfile.ZipFile(state) as archive:
            assert archive.namelist() == ([seed] if resumed else [])

    cell = (stage / "colab_cell.txt").read_text()
    assert cell == ("from google.colab import drive; drive.mount('/content/drive')\n"
                    "!bash /content/drive/MyDrive/pfe_colab_cpu/input/run_colab_cpu.sh\n")
    assert stdout.getvalue() == f"Colab upload cpu_bundle.zip: {(dataset / 'cpu_bundle.zip').stat().st_size / 1e6:.1f} MB\n{cell}"
    launcher = (stage / "run_colab_cpu.sh").read_text().splitlines()
    assert launcher[:2] == ["#!/usr/bin/env bash", "set -euo pipefail"]
    timestamp, steps, digest = launcher[2].split(" | ")
    assert timestamp.startswith("# Push ")
    assert datetime.fromisoformat(timestamp.removeprefix("# Push ")).utcoffset() == timedelta(0)
    assert steps == "steps 'p4_B1 p4_B2conv'"
    expected_md5 = hashlib.md5((dataset / "cpu_bundle.zip").read_bytes()).hexdigest()
    assert digest == f"cpu_bundle.zip MD5 {expected_md5}"
    assert shlex.split(launcher[3]) == ["unzip", "-oq", "/content/drive/MyDrive/pfe_colab_cpu/input/cpu_bundle.zip",
                                       "-d", "/content/pfe"]
    command = shlex.split(launcher[-1])
    assert command[-2:] == ["python3", "/content/pfe/scripts/kaggle_cpu_run.py"]
    assert set(command[:-2]) == {
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
    print("  1. Colab pushes both archives and the launcher, records the bundle MD5, and prints the two-line cell.")


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
    archive = inputs / "cpu_bundle.zip"
    launcher = inputs / "run_colab_cpu.sh"
    with patch.multiple(colab, CODE=code, INPUT=inputs, WORK=work):
        launcher.write_text(colab.launcher_text("p4_B1 p4_B2", 3.5, overrides,
                                                hashlib.md5(archive.read_bytes()).hexdigest()))
    assert 'P4_PARALLEL="$(nproc)"' in launcher.read_text()
    result = subprocess.run(["bash", str(launcher)], env=env, capture_output=True, text=True, check=True)
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


def test_v5_pins(root):
    """Install the v5 encoder dependency on Colab and fail before dispatch if it cannot import."""
    code = root / "code"
    code.mkdir(parents=True)
    (code / "requirements.txt").write_text("numpy==1.0\ntorch_geometric==2.8.1\n")
    output = [subprocess.CompletedProcess([], 0, "", ""),
              subprocess.CompletedProcess([], 0, "numpy==1.0\ntorch_geometric==2.8.1\n", "")]
    with (patch.dict(os.environ, {"PIP_ONLINE": "1"}),
          patch.multiple(remote, CODE=code, PINS=root / "pins", DATASET="v5", CHECKED=["numpy"]),
          patch.object(remote, "log"), patch.object(subprocess, "run", side_effect=output) as run):
        remote.install()
        install, check = run.call_args_list
        assert install.args[0][-2:] == ["numpy==1.0", "torch_geometric==2.8.1"]
        assert "import torch, torch_geometric, src.models.hybrid_gnn" in check.args[0][2]
        assert check.kwargs["env"]["PFE_DATASET"] == "v5"
    output[1] = subprocess.CompletedProcess([], 1, "numpy==1.0\n", "no torch_geometric")
    with (patch.dict(os.environ, {"PIP_ONLINE": "1"}),
          patch.multiple(remote, CODE=code, PINS=root / "pins", DATASET="v5", CHECKED=["numpy"]),
          patch.object(remote, "log"), patch.object(subprocess, "run", side_effect=output)):
        try:
            remote.install()
        except SystemExit as error:
            assert "torch_geometric missing" in str(error) and "no torch_geometric" in str(error)
        else:
            raise AssertionError("v5 must fail before dispatch when PyG is missing")
    print(" 10. v5 Colab installs the PyG pin and checks torch, PyG and Hybrid-GNN before dispatch.")


def test_slim_bundle(root):
    full = local.bundle(root / "full") / "cpu_bundle.zip"
    slim = local.bundle(root / "slim", slim=True) / "cpu_bundle.zip"
    extracted = root / "extracted"
    with zipfile.ZipFile(full) as archive:
        full_names = set(archive.namelist())
    with zipfile.ZipFile(slim) as archive:
        slim_names = set(archive.namelist())
        archive.extractall(extracted)
    daily = {name for name in full_names if Path(name).match("data/raw/safran/sim2_66_[0-9]*.parquet")}
    land_use = {name for name in full_names if Path(name).match("results/v4/_cache/panel_lu_*.parquet")}
    assert daily and land_use and slim_names == full_names - daily - land_use
    assert slim.stat().st_size < full.stat().st_size
    print(f"  8. CPU full {full.stat().st_size:,} bytes, slim {slim.stat().st_size:,} bytes. "
          f"Slim omits {len(daily)} daily files and {len(land_use)} land-use panels.", flush=True)

    env = {key: value for key, value in os.environ.items()
           if not key.startswith("P4_") and key not in ("PFE_RESULTS", "STATUS_FILE")}
    env.update(PYTHONPATH=str(extracted), PYTHONNOUSERSITE="1", PFE_DATASET="v4")
    blocks = "B1 B1c B2 B2conv B3 B4 B5 B6 B7".split()
    dry_env = dict(env, STEPS=" ".join(f"p4_{block}" for block in blocks), PY=sys.executable,
                   P4_CONFIRMED="1", P4_DRYRUN="1")
    dry = subprocess.run(["bash", "scripts/run_v4_cpu.sh"], env=dry_env, cwd=extracted,
                         capture_output=True, text=True, check=True)
    fits = [line for line in dry.stdout.splitlines() if " -m src.models.response " in line]
    assemblies = [line for line in dry.stdout.splitlines() if "assemble_lwo" in line]
    assert all(any(f"--run p4_{block}_" in line for line in fits) for block in blocks)
    assert "skipping" not in dry.stdout and "locked" not in dry.stdout
    print(f"     Extracted Phase 4 dry run: {len(fits)} fits and {len(assemblies)} fold assemblies.", flush=True)

    check = textwrap.dedent("""
        from pathlib import Path

        from src.config import ROOT, R3_STARTS
        from src.models import features, message, response, routing, statics, twin

        assert ROOT == Path.cwd()
        panel = features.build_panel()
        panel = panel[panel["mu"].notna()]
        for start in R3_STARTS.values():
            assert not features.build_panel(train_start=start).empty
            assert not statics.static_table("B", train_start=start).empty
        cases = [("baseline", 1, "main"), ("C", 2, "main"), ("D", 3, "main"),
                 ("D", 1, "confident-only"), ("C", 1, "all-links"),
                 ("E_degree:0", 1, "main"), ("E_distance:0", 1, "main"),
                 ("F_random:0", 1, "main"), ("F_complete", 1, "main")]
        for arm, recon, policy in cases:
            data = routing.routed_inputs(arm, policy, reconstruction=recon)
            assert data["reconstruction"] == recon and data["codes"] and len(data["weeks"])
            assert isinstance(response.gate3_river_wells(policy), set)
            print(f"     {arm} {policy} reconstruction {recon}: {len(data['codes'])} wells x {len(data['weeks'])} weeks")
        recharge_cases = [("linear", "recharge_unitwide", "rain"), ("drainc", "recharge", "DRAINC"),
                          ("pe", "recharge", "PE")]
        for recharge, relation, column in recharge_cases:
            data = routing.routed_inputs("D", recharge=relation, include_drainc=recharge == "drainc")
            arrays = response.panel_arrays(panel, response.KERNEL_WEEKS, data, recharge=recharge)
            assert arrays["codes"] and arrays["X"][column].size
        facts = statics.static_table("B")
        assert not facts.empty and not statics.static_table("A").empty
        links, record = message.regime_links("E_degree:0")
        assert record["threshold"]["regime"] == "R1" and record["edges"] == len(links) > 0
        base = twin.load_base()
        assert len(base["P"]) == len(base["codes"]) * len(base["weeks"]) > 0
        print(f"     Facts {facts.shape}, {len(links)} regime links, twin {len(base['codes'])} wells x {len(base['weeks'])} weeks")
    """)
    subprocess.run([sys.executable, "-c", check], env=env, cwd=extracted, check=True)


def test_gpu_bundle(root):
    dirs = (root / "scripts", root / "src", root / "results" / "v4" / "_cache")
    for folder in dirs:
        folder.mkdir(parents=True)
    scripts, src, cache = dirs
    script = scripts / "make_gpu_bundle.py"
    shutil.copyfile(local.ROOT / "scripts" / script.name, script)
    (src / "config.py").write_text("from pathlib import Path\n"
                                   "ROOT = Path(__file__).resolve().parents[1]\n"
                                   "DATASET = 'v4'\nPROCESSED = ROOT / 'data' / 'processed'\n"
                                   "DATASET_DIR = ROOT / 'data' / 'processed' / 'dataset_v4'\n"
                                   "RAW = ROOT / 'data' / 'raw'\nRESULTS_DIR = ROOT / 'results' / 'v4'\n")
    ordinary = ("panel.parquet", "panel_f25.parquet", "panel_f50.parquet")
    for name in (*ordinary, "panel_lu_on.parquet"):
        (cache / name).touch()
    env = dict(os.environ, PFE_DATASET="v4", PYTHONPATH=str(root))
    subprocess.run([sys.executable, str(script)], env=env, cwd=root, capture_output=True, text=True, check=True)
    with zipfile.ZipFile(root / "gpu_bundle.zip") as archive:
        panels = {Path(name).name for name in archive.namelist() if Path(name).parent == cache.relative_to(root)}
    assert panels == set(ordinary)
    print("  9. The GPU bundle keeps the ordinary full and R3 panels and omits the land-use panel.")


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
        test_slim_bundle(root / "bundles")
        test_gpu_bundle(root / "gpu")
        test_v5_pins(root / "v5_pins")
    print("test_colab_cpu: all checks passed")


if __name__ == "__main__":
    main()
