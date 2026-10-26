"""Bring Colab results back to the laptop (docs/gpu_howto.md, Colab section).

    .venv/bin/python scripts/colab_pull.py ~/Downloads/results_colab.zip
    .venv/bin/python scripts/colab_pull.py ~/Downloads/drive-download-....zip --version v4

The zip is made in Colab (`python scripts/colab_run.py zip`, then files.download) or
downloaded from Drive (folder pfe_colab/results_gpu > Download). A Drive download of run
folders selected inside results_gpu/v4 has no version folder: --version names it. It is unpacked into
results/_colab/output; for every dataset version in it (v3, v4), every finished run
(predictions.parquet present) and every tuning folder (<model>_tuning with a study or a
best.json) is copied to results/<v>/<run>, and the runs are rescored with
src.models.evaluate under that version.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "_colab" / "output"    # results/ is gitignored
VERSIONS = ("v3", "v4")


def main():
    args = sys.argv[1:]
    version = None
    if len(args) == 3 and args[1] == "--version" and args[2] in VERSIONS:
        args, version = args[:1], args[2]
    if len(args) != 1:
        sys.exit(__doc__)
    shutil.rmtree(OUTPUT, ignore_errors=True)
    target = OUTPUT / version if version else OUTPUT
    target.mkdir(parents=True)
    with zipfile.ZipFile(args[0]) as z:
        if version and any(n.split("/")[0] in VERSIONS for n in z.namelist()):
            sys.exit(f"{args[0]} already holds a version folder: run without --version")
        z.extractall(target)
    found = [d for v in VERSIONS for d in sorted(OUTPUT.rglob(v)) if d.is_dir()]
    if not found:
        sys.exit(f"no results folder of {VERSIONS} in {sys.argv[1]}")
    for vdir in found:
        v = vdir.name
        runs, studies = [], []
        for d in sorted(vdir.iterdir()):
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
        if runs:
            subprocess.run([sys.executable, "-m", "src.models.evaluate", *runs], cwd=ROOT,
                           env={**os.environ, "PFE_DATASET": v}, check=True)
    log = found[0].parent / "run_colab.log"
    if log.exists():
        print("".join(log.read_text().splitlines(keepends=True)[-15:]))


if __name__ == "__main__":
    main()
