"""Bring Colab results back to the laptop for scoring (analysis plan §5).

    .venv/bin/python scripts/colab_pull.py ~/Downloads/results_colab.zip
    .venv/bin/python scripts/colab_pull.py ~/Downloads/drive-download-....zip --version v4
    .venv/bin/python scripts/colab_pull.py --drive [REMOTE_PATH] [--version v4]
    .venv/bin/python scripts/colab_pull.py --dir PATH [--version v4]

The zip is made in Colab (`python scripts/colab_run.py zip`, then files.download) or
downloaded from Drive and is unpacked into results/_colab/output. --drive uses rclone (without
the Chronos-2 checkpoints)
to copy from gdrive:pfe_colab/results_gpu by default. --dir reads a local folder.
The layouts are results_gpu/<version>/<run>/... and <version>/<run>/.... Use
--version for a source containing run folders directly without a version name.
For each dataset version (v3, v4, v5), copy finished runs (with predictions.parquet)
and tuning folders (with study.db or best.json) to results/<version>/<run>.
Rescore the finished runs with src.models.evaluate under their dataset version.
Copy extraction runs with run.json or predictions_*.json under extraction/ without
model scoring; these use the separate extraction scorer (v5 plan R2.1).
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "_colab" / "output"    # results/ is gitignored
VERSIONS = ("v3", "v4", "v5")
REMOTE = "gdrive:pfe_colab/results_gpu"


def extract_zip(path, version):
    shutil.rmtree(OUTPUT, ignore_errors=True)
    target = OUTPUT / version if version else OUTPUT
    target.mkdir(parents=True)
    with zipfile.ZipFile(path) as z:
        if version and any(n.split("/")[0] in VERSIONS for n in z.namelist()):
            sys.exit(f"{path} already holds a version folder: run without --version")
        z.extractall(target)
    return OUTPUT


def download_drive(remote, folder):
    try:
        subprocess.run(["rclone", "copy", remote, str(folder),
                        "--exclude", "_cache/**", "--exclude", "*.db-journal",
                        "--exclude", "*-wal", "--exclude", "*-shm",
                        # Chronos-2 fine-tuning checkpoints (hundreds of MB, not needed to score)
                        "--exclude", "ckpt/**"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except FileNotFoundError:
        sys.exit("rclone executable not found on PATH")
    except OSError:
        sys.exit("could not start rclone")
    except subprocess.CalledProcessError as error:
        # rclone diagnostics can contain details from its configuration.
        sys.exit(f"rclone copy failed (exit {error.returncode})")


def process_folder(folder, source, version=None):
    if not folder.is_dir():
        sys.exit(f"results folder does not exist: {folder}")
    found = []
    for v in VERSIONS:
        if folder.name == v:
            found.append((v, folder))
        found.extend((v, d) for d in sorted(folder.rglob(v)) if d.is_dir())
    if not found and version:
        found.append((version, folder))
    if not found:
        sys.exit(f"no results folder of {VERSIONS} in {source}")
    for v, vdir in found:
        runs, studies, extractions = [], [], []
        for d in sorted(vdir.iterdir()):
            if d.name == "extraction" and d.is_dir():
                for extraction in sorted(d.iterdir()):
                    if extraction.is_dir() and ((extraction / "run.json").is_file()
                                                or any(p.is_file() for p in
                                                       extraction.glob("predictions_*.json"))):
                        shutil.copytree(extraction, ROOT / "results" / v / "extraction" / extraction.name,
                                        dirs_exist_ok=True)
                        extractions.append(extraction.name)
                continue
            if (d / "predictions.parquet").exists():
                runs.append(d.name)
            elif d.name.endswith("_tuning") and any((d / f).exists()
                                                    for f in ("study.db", "best.json")):
                studies.append(d.name)
            else:
                continue
            shutil.copytree(d, ROOT / "results" / v / d.name, dirs_exist_ok=True)
        print(f"[{v}] finished runs copied:", " ".join(runs) or "none")
        print(f"[{v}] tuning folders copied:", " ".join(studies) or "none")
        print(f"[{v}] extraction runs copied:", " ".join(extractions) or "none")
        if runs:
            subprocess.run([sys.executable, "-m", "src.models.evaluate", *runs], cwd=ROOT,
                           env={**os.environ, "PFE_DATASET": v}, check=True)
    vdir = found[0][1]
    log = (folder if vdir == folder else vdir.parent) / "run_colab.log"
    if log.exists():
        print("".join(log.read_text().splitlines(keepends=True)[-15:]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("zip", nargs="?", help="Colab or Drive results download")
    sources.add_argument("--drive", nargs="?", const=REMOTE, metavar="REMOTE_PATH",
                         help=f"copy from Drive (default: {REMOTE})")
    sources.add_argument("--dir", type=Path, metavar="PATH", help="read an extracted results folder")
    parser.add_argument("--version", choices=VERSIONS, help="dataset for unversioned run folders")
    args = parser.parse_args(argv)
    if args.drive is not None:
        with TemporaryDirectory(prefix="colab_pull_") as temporary:
            folder = Path(temporary)
            download_drive(args.drive, folder)
            process_folder(folder, args.drive, args.version)
    elif args.dir is not None:
        process_folder(args.dir, args.dir, args.version)
    else:
        process_folder(extract_zip(args.zip, args.version), args.zip)


if __name__ == "__main__":
    main()
