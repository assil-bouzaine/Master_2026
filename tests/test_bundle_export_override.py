"""Check the CPU export replacement for analysis plan §14 item 23 without a remote run.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_bundle_export_override
"""
import hashlib
import io
import json
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts import colab_cli, colab_cpu, kaggle_cpu
from src import config

SCRATCH = kaggle_cpu.ROOT / "results" / "_agents" / "tmp" / "T42"
EXPORT_ROOT = Path("data/processed/kg")
POLICIES = ("main", "confident-only", "all-links")
FROZEN = {
    "manifest.json": b'{"release": "12:41"}\n',
    "edges_D.parquet": b"\x00frozen D\xff",
    "edges_C.parquet": b"\x00frozen C\xff",
    "nodes.parquet": b"\x00frozen nodes\xff",
    "metadata/note.txt": b"kept at its relative path\n",
}


def write_files(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def archive_files(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "duplicate ZIP member"
        return {name: archive.read(name) for name in names}


def export_entries(policy, files):
    folder = EXPORT_ROOT / f"export_v4_{policy}"
    return {(folder / name).as_posix(): content for name, content in files.items()}


def test_bundle(root, frozen, real_exports):
    stage = root / "stage"
    baseline = archive_files(kaggle_cpu.bundle(stage, slim=True) / "cpu_bundle.zip")
    for entries in real_exports.values():
        assert {name: baseline[name] for name in entries} == entries
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = kaggle_cpu.bundle(stage, slim=True, export_override={"main": str(frozen)})
    replaced = archive_files(result / "cpu_bundle.zip")
    expected = {name: content for name, content in baseline.items() if name not in real_exports["main"]}
    assert replaced == {**expected, **export_entries("main", FROZEN)}
    assert not any(name.startswith("data/processed/kg/export_v4_main/controls/") for name in replaced)
    assert str(frozen) in stdout.getvalue() and "Warning" in stdout.getvalue()
    assert "no controls/ files" in stdout.getvalue()
    for entries in real_exports.values():
        for name, content in entries.items():
            assert (kaggle_cpu.ROOT / name).read_bytes() == content
    print(f"  1. Replaced main with {len(FROZEN)} exact ZIP entries and kept {len(expected)} other entries.")


def refuses(call, *messages):
    try:
        call()
    except SystemExit as error:
        assert all(message in str(error) for message in messages), error
    else:
        raise AssertionError(f"Expected refusal with {messages}")


def test_refusals(root, frozen):
    stage = root / "refused-stage"
    refuses(lambda: kaggle_cpu.bundle(stage, slim=True, export_override={"unknown": frozen}),
            "Unknown export policy", "unknown")
    for missing in ("manifest.json", "edges_D.parquet", "nodes.parquet"):
        incomplete = root / f"missing-{missing}"
        write_files(incomplete, {name: content for name, content in FROZEN.items() if name != missing})
        (incomplete / missing).mkdir()   # A directory cannot stand in for the required file.
        refuses(lambda: kaggle_cpu.bundle(stage, slim=True, export_override={"main": incomplete}),
                "main", str(incomplete), f"missing {missing}")
    assert not stage.exists()
    inside_stage = stage / "dataset" / "frozen"
    write_files(inside_stage, FROZEN)
    refuses(lambda: kaggle_cpu.bundle(stage, slim=True, export_override={"main": inside_stage}),
            "overlaps the bundle staging folder")
    assert (inside_stage / "manifest.json").read_bytes() == FROZEN["manifest.json"]
    print("  2. Refused an unknown policy, each missing required file, and an input inside staging.")


def test_push_commands(root, frozen):
    other = root / "all-links export"
    other_files = {**FROZEN, "manifest.json": b'{"release": "other"}\n', "controls/draw": b"control"}
    write_files(other, other_files)
    args = ["--export-override", f"main={frozen}", "--export-override", f"all-links={other}"]
    invalid = ["--export-override", "main"]
    steps = ["--steps", "twin_shortcut_pilot"]
    kaggle_stage, cli_stage, drive_stage = (root / name for name in ("kaggle", "cli", "drive"))
    with (patch.object(kaggle_cpu, "STAGE", kaggle_stage), patch.object(kaggle_cpu, "user") as user,
          patch.object(kaggle_cpu, "kg", return_value="ready"), patch.object(kaggle_cpu, "upload") as upload,
          patch.object(kaggle_cpu, "push_kernel") as push_kernel, redirect_stdout(io.StringIO())):
        refuses(lambda: kaggle_cpu.main(["push", *invalid]), "expects POLICY=PATH")
        user.assert_not_called()
        user.return_value = "fixture"
        kaggle_cpu.main(["push", *steps, *args])
        upload.assert_called_once_with(kaggle_stage / "dataset", kaggle_cpu.BUNDLE)
        push_kernel.assert_called_once()
    with (patch.object(colab_cpu, "STAGE", drive_stage), patch.object(colab_cpu, "rclone") as rclone,
          redirect_stdout(io.StringIO())):
        refuses(lambda: colab_cpu.main(["push", *invalid]), "expects POLICY=PATH")
        rclone.assert_not_called()
        colab_cpu.main(["push", *steps, *args])
        assert rclone.call_count == 3
    stdout = io.StringIO()
    with (patch.object(colab_cli, "STAGE", cli_stage), patch.object(colab_cli, "ROOT", kaggle_cpu.ROOT),
          patch.object(colab_cli, "ssh") as ssh, patch.object(colab_cli, "upload", return_value="fixture-md5"),
          patch.object(colab_cli, "run_colab", return_value=SimpleNamespace(pid=12345)) as run_colab,
          patch.object(colab_cli, "process_start", return_value=100), redirect_stdout(stdout)):
        refuses(lambda: colab_cli.main(["push-cpu", "slice-f", *steps, *invalid]), "expects POLICY=PATH")
        ssh.assert_not_called()
        run_colab.assert_not_called()
        colab_cli.main(["push-cpu", "slice-f", *steps, *args])
    cli_job = cli_stage / "slice-f"
    expected = {**export_entries("main", FROZEN), **export_entries("all-links", other_files)}
    overridden_prefixes = tuple(f"data/processed/kg/export_v4_{policy}/" for policy in ("main", "all-links"))
    for stage in (kaggle_stage, drive_stage, cli_job):
        files = archive_files(stage / "dataset" / "cpu_bundle.zip")
        assert {name: content for name, content in files.items() if name.startswith(overridden_prefixes)} == expected
    job = json.loads((cli_job / "job.json").read_text(encoding="utf-8"))
    metadata = {
        policy: {"path": str(folder), "manifest_md5": hashlib.md5(files["manifest.json"]).hexdigest()}
        for policy, folder, files in (("main", frozen, FROZEN), ("all-links", other, other_files))
    }
    assert job["export_override"] == metadata
    assert f"Export override metadata: {json.dumps(metadata)}" in stdout.getvalue()
    print("  3. All three push commands accept two overrides. Colab CLI records and prints both manifest MD5s.")


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as folder:
        root = Path(folder)
        repo = root / "repo"
        raw, interim, processed = (repo / "data" / name for name in ("raw", "interim", "processed"))
        write_files(repo, {"data/raw/safran/grid_cells_66.parquet": b"grid",
                           "data/interim/pumping_weekly_cropcal_v4.parquet": b"pumping",
                           "scripts/kaggle_cpu_run.py": b"# runner fixture\n"})
        real_exports = {}
        for policy in POLICIES:
            files = {"manifest.json": policy.encode(), "edges_D.parquet": b"live D",
                     "nodes.parquet": b"live nodes", "controls/draw": b"live control", "live-only.txt": b"live note"}
            real_exports[policy] = export_entries(policy, files)
            write_files(repo, real_exports[policy])
        frozen = root / "frozen = 12 41"
        write_files(frozen, FROZEN)
        with (patch.object(kaggle_cpu, "ROOT", repo), patch.object(kaggle_cpu, "V4", repo / "results" / "v4"),
              patch.multiple(config, RAW=raw, INTERIM=interim, PROCESSED=processed),
              patch.object(sys, "path", sys.path.copy())):
            test_bundle(root, frozen, real_exports)
            test_refusals(root, frozen)
            test_push_commands(root, frozen)
    print("test_bundle_export_override: all checks passed")


if __name__ == "__main__":
    main()
