"""Offline checks of the Kaggle CPU runner for analysis plan v2, sections 5 and 14.

Run with PFE_DATASET=v4 python -m tests.test_kaggle_runner. Use temporary folders
and stand-ins for Kaggle and for the shell's model commands.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import kaggle_cpu as local
from scripts import kaggle_cpu_run as remote


def test_dispatcher(root):
    script = Path("scripts/run_v4_cpu.sh")
    (root / script).parent.mkdir()
    shutil.copy2(local.ROOT / script, root / script)
    status = root / "failed.txt"
    worker = root / "worker"
    worker.write_text('#!/bin/bash\n[[ "$*" != *"--run twin_slices"* ]]\n')
    worker.chmod(0o755)
    cases = [
        ("/bin/false", "twin_grid", ["twin_grid"]),
        ("/bin/false", "naive", ["naive"]),
        ("/bin/true", "twin_grid naive", []),
        ("/bin/true", "naive nosuchstep", ["nosuchstep"]),
        ("/bin/false", "ladder ladder2 twin_pilot twin_slices", ["ladder", "ladder2", "twin_pilot", "twin_slices"]),
        (str(worker), "twin_slices naive", ["twin_slices"]),
    ]
    for python, steps, failed in cases:
        result = subprocess.run(["bash", str(script)], cwd=root, capture_output=True, text=True,
                                env=dict(os.environ, PY=python, STEPS=steps, STATUS_FILE=str(status)))
        assert result.returncode == int(bool(failed)), result.stdout + result.stderr
        assert status.read_text().splitlines() == failed
        if failed:
            assert f"== failed steps: {' '.join(failed)}" in result.stdout
            assert "done" in result.stdout
    print("  1. dispatcher: all worker groups, foreground failures, unknown steps, and continuation")


def test_status(root):
    failed_file = root / "dispatcher.txt"
    status_file = root / "run_status.json"
    steps = "naive twin_grid"
    for rc, budget, failed in [(0, False, []), (1, False, ["twin_grid"]), (-signal.SIGTERM, True, [])]:
        failed_file.write_text("".join(f"{step}\n" for step in failed))
        remote.write_run_status(status_file, failed_file, rc, budget, steps)
        status = json.loads(status_file.read_text())
        assert status["exit"] == rc and status["budget_stop"] is budget
        assert status["failed_steps"] == failed and status["steps"] == steps
        assert datetime.fromisoformat(status["finished_utc"]).utcoffset() == timedelta(0)

    worker = root / "worker"
    worker.write_text("#!/bin/bash\nexec /bin/sleep 30\n")
    with (patch.object(remote, "CODE", root), patch.object(remote, "LOG", root / "runner.log"),
          patch.object(remote, "DEADLINE", time.time() + 1)):
        worker.chmod(0o755)
        rc, budget = remote.run("nosuchstep naive",
                                dict(os.environ, PY=str(worker), STATUS_FILE=str(failed_file)))
    assert rc == -signal.SIGTERM and budget
    assert failed_file.read_text().splitlines() == ["nosuchstep"]
    print("  2. run status: clean, failed, budget stop, and a failure before the deadline")


def fixture_output(folder, run, seed):
    path = folder / local.CPU_RESULTS / run / "seed_0.json"
    path.parent.mkdir(parents=True)
    path.write_text(seed)
    (folder / "run_kaggle_cpu.log").write_text(f"session for {run}\n")
    return path.relative_to(folder)


def snapshot(folder):
    return {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def test_pull_merge(root):
    stage = root / "stage"
    results = root / "local_results"
    output = stage / "output"
    previous = stage / "output_prev"
    state = stage / "state"
    incoming = stage / "output_incoming"
    legacy = fixture_output(output, "legacy", "legacy seed")
    archive = root / "state.zip"
    assert local.bundle_state(stage, archive)
    with zipfile.ZipFile(archive) as z:
        assert z.read(legacy.as_posix()) == b"legacy seed"

    first, second = root / "first", root / "second"
    seed_a = fixture_output(first, "runA", "seed A")
    seed_b = fixture_output(second, "runB", "seed B")
    incoming.mkdir()
    (incoming / "leftover").touch()
    for fixture in (first, second):
        with patch.object(local, "download_output", side_effect=lambda dst: shutil.copytree(
                fixture, dst, dirs_exist_ok=True)):
            local.pull(stage, results)
        assert snapshot(output) == snapshot(fixture)
        assert (state / seed_a).read_text() == "seed A"
        assert (state / legacy).read_text() == "legacy seed"
    assert snapshot(previous) == snapshot(first)
    assert not results.exists()
    assert local.bundle_state(stage, archive)
    with zipfile.ZipFile(archive) as z:
        assert z.read(seed_a.as_posix()) == b"seed A"
        assert z.read(seed_b.as_posix()) == b"seed B"

    folders = (output, previous, state)
    before = [snapshot(folder) for folder in folders]

    def interrupted_download(destination):
        (destination / "partial_download").touch()
        raise OSError("mock download failed")

    with patch.object(local, "download_output", side_effect=interrupted_download):
        try:
            local.pull(stage, results)
        except OSError as error:
            assert str(error) == "mock download failed"
        else:
            raise AssertionError("The interrupted download should fail")
    assert [snapshot(folder) for folder in folders] == before
    with patch.object(local, "download_output"):  # download returns without a log
        try:
            local.pull(stage, results)
        except SystemExit as error:
            assert "run_kaggle_cpu.log" in str(error)
        else:
            raise AssertionError("The download without a log should fail")
    assert [snapshot(folder) for folder in folders] == before
    print("  3. pull merge: remembered both partial runs and the older download after failed pulls")


def test_pull_status(root):
    stage, results, fixture = root / "stage", root / "local_results", root / "fixture"
    seed = fixture_output(fixture, "finished", "")
    prediction = fixture / seed.with_name("predictions.parquet")
    prediction.touch()
    world = fixture / local.CPU_RESULTS / "twin" / "cell" / "world_0.json"
    world.parent.mkdir(parents=True)
    world.write_text("{}")
    cases = [(0, False, [], 0), (1, False, ["naive"], 1), (2, False, [], 1),
             (-signal.SIGTERM, True, [], 0), (-signal.SIGTERM, True, ["naive"], 1)]
    for count, (rc, budget, failed, expected) in enumerate(cases):
        (fixture / seed).write_text(str(count))
        (fixture / "run_status.json").write_text(json.dumps(
            {"exit": rc, "budget_stop": budget, "failed_steps": failed}))
        with (patch.object(local, "download_output", side_effect=lambda dst: shutil.copytree(
                  fixture, dst, dirs_exist_ok=True)),
              patch.object(local.subprocess, "run") as evaluate):
            exit_code = 0
            try:
                local.pull(stage, results)
            except SystemExit as error:
                exit_code = error.code
            assert exit_code == expected
            evaluate.assert_called_once()
            assert evaluate.call_args.args[0][1:] == ["-m", "src.models.evaluate", "finished"]
            assert evaluate.call_args.kwargs["env"]["PFE_RESULTS"] == str(results)
        assert (results / "finished" / prediction.name).is_file()
        assert (results / "twin" / "cell" / world.name).is_file()
        assert (stage / "state" / seed).read_text() == str(count)
    print("  4. pull status: new files replace old copies, predictions and twins survive failures")


def test_bundle(root):
    started = time.perf_counter()
    archive = local.bundle(root / "stage") / "cpu_bundle.zip"
    print(f"     archive: {archive.stat().st_size} bytes in {time.perf_counter() - started:.2f}s")
    extracted = root / "extracted"
    with zipfile.ZipFile(archive) as z:
        z.extractall(extracted)
    code = textwrap.dedent("""
        from pathlib import Path

        from src.config import ROOT
        from src.models import message, routing, statics, twin

        assert ROOT == Path.cwd()
        for arm, reconstruction in (("baseline", 1), ("C", 3), ("D", 3), ("E_degree:0", 3)):
            data = routing.routed_inputs(arm, reconstruction=reconstruction)
            assert data["reconstruction"] == reconstruction and data["codes"] and len(data["weeks"])
            print(f"     {arm} R{reconstruction}: {len(data['codes'])} wells x {len(data['weeks'])} weeks")
        facts = statics.static_table("B")
        assert not facts.empty
        print(f"     rung 3: {facts.shape[0]} wells x {facts.shape[1]} facts")
        links, record = message.regime_links("E_degree:0")
        assert record["threshold"]["regime"] == "R1" and record["edges"] == len(links) > 0
        print(f"     regime R1: {len(links)} control well links")
        base = twin.load_base()
        assert len(base["P"]) == len(base["codes"]) * len(base["weeks"]) > 0
        print(f"     twin base: {len(base['codes'])} wells x {len(base['weeks'])} weeks")
    """)
    env = dict(os.environ, PYTHONPATH=str(extracted), PYTHONNOUSERSITE="1", PFE_DATASET="v4")
    env.pop("PFE_RESULTS", None)
    subprocess.run([sys.executable, "-c", code], cwd=extracted, env=env, check=True)
    print("  5. bundle: routed inputs, facts, regime links and twin base loaded from the archive")


if __name__ == "__main__":
    with TemporaryDirectory() as folder:
        root = Path(folder)
        dispatcher = root / "dispatcher"
        dispatcher.mkdir()
        test_dispatcher(dispatcher)
        test_status(dispatcher)
        test_pull_merge(root / "merge")
        test_pull_status(root / "status")
        test_bundle(root / "bundle")
    print("test_kaggle_runner: all checks passed")
