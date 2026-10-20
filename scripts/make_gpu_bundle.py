"""Pack code + model-ready data into one zip to run the neural baselines on a GPU.

    python scripts/make_gpu_bundle.py      # -> gpu_bundle.zip (~10 MB)

Contains src/, scripts/run_gpu.sh, requirements.txt, the current dataset
(PFE_DATASET), its cached feature panel and the SAFRAN grid table (Taccari weather
nodes). Raw data is otherwise not needed. See docs/gpu_howto.md.
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DATASET_DIR, RAW, RESULTS_DIR  # noqa: E402
OUT = ROOT / "gpu_bundle.zip"
INCLUDE = [ROOT / "src", ROOT / "scripts" / "run_gpu.sh", ROOT / "requirements.txt",
           DATASET_DIR, RESULTS_DIR / "_cache" / "panel.parquet",
           RAW / "safran" / "grid_cells_66.parquet"]

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for item in INCLUDE:
        if not item.exists():
            continue
        files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" not in f.parts:
                z.write(f, f.relative_to(ROOT))
print(f"{OUT.name}: {OUT.stat().st_size / 1e6:.1f} MB")
