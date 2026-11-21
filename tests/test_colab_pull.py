"""Check Colab result imports and scoring dispatch (analysis plan §5) offline.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_colab_pull
"""
import os
import shutil
import subprocess
import sys
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import colab_pull as pull


def make_zip(path, source):
    with zipfile.ZipFile(path, "w") as archive:
        for file in sorted(source.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(source))


def test_sources(root):
    fixture = root / "fixture"
    gpu = fixture / "results_gpu"
    version = gpu / "v4"
    expected = {"v4/finished/predictions.parquet": b"finished predictions",
                "v4/finished/seed_0.parquet": b"finished seed",
                "v4/model_tuning/best.json": b"{}"}
    skipped = {"v4/unfinished/seed_0.parquet": b"partial seed",
               "v4/_cache/panel.parquet": b"cache",
               "v4/unfinished/study.db-journal": b"journal",
               "v4/unfinished/study.db-wal": b"wal",
               "v4/unfinished/study.db-shm": b"shm"}
    log = "".join(f"line {n}\n" for n in range(20))
    for name, content in {**expected, **skipped, "run_colab.log": log.encode()}.items():
        file = gpu / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)

    wrapped_zip, versioned_zip, flat_zip = (root / f"{name}.zip" for name in ("wrapped", "versioned", "flat"))
    for archive, source in ((wrapped_zip, fixture), (versioned_zip, gpu), (flat_zip, version)):
        make_zip(archive, source)

    default_remote = "gdrive:pfe_colab/results_gpu"
    flat_remote = "gdrive:fixtures/v4"
    cases = [(["--drive"], default_remote, gpu),
             (["--drive", flat_remote, "--version", "v4"], flat_remote, version),
             (["--dir", str(fixture)], None, None),
             (["--dir", str(gpu)], None, None),
             (["--dir", str(version)], None, None),
             ([str(wrapped_zip)], None, None),
             ([str(versioned_zip)], None, None),
             ([str(flat_zip), "--version", "v4"], None, None)]
    flat = root / "extracted"
    shutil.copytree(version, flat)
    cases.append((["--dir", str(flat), "--version", "v4"], None, None))

    for index, (args, remote, source) in enumerate(cases):
        local = root / f"local_{index}"
        stage = local / "results" / "_colab" / "output"
        downloaded = []
        scored = []

        def run(command, **kwargs):
            if command[0] == "rclone":
                assert remote is not None
                destination = Path(command[3])
                assert command[:3] == ["rclone", "copy", remote]
                assert command[4:] == ["--exclude", "_cache/**", "--exclude", "*.db-journal",
                                       "--exclude", "*-wal", "--exclude", "*-shm",
                                       "--exclude", "ckpt/**"]
                assert kwargs == {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "check": True}
                shutil.copytree(source, destination, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("_cache", "*.db-journal", "*-wal", "*-shm"))
                downloaded.append(destination)
            else:
                assert command == [sys.executable, "-m", "src.models.evaluate", "finished"]
                assert kwargs["cwd"] == local and kwargs["env"]["PFE_DATASET"] == "v4" and kwargs["check"]
                scored.append(command[-1])

        stdout = StringIO()
        with (patch.multiple(pull, ROOT=local, OUTPUT=stage), patch.object(subprocess, "run", side_effect=run),
              patch.dict(os.environ, PFE_DATASET="v3"), redirect_stdout(stdout)):
            pull.main(args)
        copied = {file.relative_to(local / "results").as_posix(): file.read_bytes()
                  for file in (local / "results" / "v4").rglob("*") if file.is_file()}
        assert copied == expected, args
        assert scored == ["finished"], args
        assert len(downloaded) == int(remote is not None), args
        assert all(not folder.exists() for folder in downloaded), args
        if args in ([str(wrapped_zip)], [str(versioned_zip)]):
            assert stdout.getvalue().endswith("".join(log.splitlines(keepends=True)[-15:]) + "\n")
    print(f"  1. {len(cases)} inputs copied the same three files and dispatched scoring for the finished run.")


def test_drive_failures(root):
    cases = [(FileNotFoundError("private path"), "rclone executable not found on PATH"),
             (PermissionError("private path"), "could not start rclone"),
             (subprocess.CalledProcessError(7, ["rclone"], stderr="private diagnostic"),
              "rclone copy failed (exit 7)")]
    for failure, message in cases:
        with (patch.multiple(pull, ROOT=root, OUTPUT=root / "stage"),
              patch.object(subprocess, "run", side_effect=failure) as run):
            try:
                pull.main(["--drive"])
            except SystemExit as error:
                assert str(error) == message
            else:
                raise AssertionError("Drive pull continued after rclone failed")
        run.assert_called_once()
        assert run.call_args.kwargs["stderr"] == subprocess.DEVNULL
        assert not Path(run.call_args.args[0][3]).exists()
        assert not root.exists()
    print("  2. Three rclone failures stopped before copying or scoring and hid private diagnostics.")


def main():
    with TemporaryDirectory() as name:
        root = Path(name)
        test_sources(root)
        test_drive_failures(root / "failure")
    print("test_colab_pull: all checks passed")


if __name__ == "__main__":
    main()
