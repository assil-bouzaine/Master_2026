"""Pack code + model-ready data into one zip to run the neural baselines on a GPU.

    python scripts/make_gpu_bundle.py      # -> gpu_bundle.zip (~10 MB)

Contains src/, requirements.txt, data/processed/dataset_v1/ and the cached
feature panel. Raw data is not needed. See docs/gpu_howto.md.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "gpu_bundle.zip"
INCLUDE = [ROOT / "src", ROOT / "requirements.txt", ROOT / "data" / "processed" / "dataset_v1",
           ROOT / "results" / "_cache" / "panel.parquet"]

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for item in INCLUDE:
        files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" not in f.parts:
                z.write(f, f.relative_to(ROOT))
print(f"{OUT.name}: {OUT.stat().st_size / 1e6:.1f} MB")
