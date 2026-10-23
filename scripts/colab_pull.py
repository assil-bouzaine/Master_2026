"""Bring Colab results back to the laptop (docs/gpu_howto.md, Colab section).

    .venv/bin/python scripts/colab_pull.py ~/Downloads/results_colab.zip

The zip is made in Colab (`python scripts/colab_run.py zip`, then files.download) or
downloaded from Drive (folder pfe_colab/results_gpu > Download). It is unpacked into
results/v3/_colab/output; every finished run (predictions.parquet present) and every tuning
study (<model>_tuning) is copied to results/v3/<run>, and the runs are rescored with
src.models.evaluate.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "v3" / "_colab" / "output"    # results/ is gitignored


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)
    with zipfile.ZipFile(sys.argv[1]) as z:
        z.extractall(OUTPUT)
    v3 = sorted(d for d in OUTPUT.rglob("v3") if d.is_dir())
    if not v3:
        sys.exit(f"no v3 results folder in {sys.argv[1]}")
    runs, studies = [], []
    for d in sorted(v3[0].iterdir()):
        if (d / "predictions.parquet").exists():
            runs.append(d.name)
        elif d.name.endswith("_tuning") and (d / "study.db").exists():
            studies.append(d.name)
        else:
            continue
        shutil.copytree(d, ROOT / "results" / "v3" / d.name, dirs_exist_ok=True)
    print("finished runs copied:", " ".join(runs) or "none")
    print("tuning studies copied:", " ".join(studies) or "none")
    if runs:
        subprocess.run([sys.executable, "-m", "src.models.evaluate", *runs], cwd=ROOT,
                       env={**os.environ, "PFE_DATASET": "v3"}, check=True)
    log = v3[0].parent / "run_colab.log"
    if log.exists():
        print("".join(log.read_text().splitlines(keepends=True)[-15:]))


if __name__ == "__main__":
    main()
