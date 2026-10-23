"""Pack code + model-ready data into one zip to run the neural baselines on a GPU.

    python scripts/make_gpu_bundle.py                    # -> gpu_bundle.zip (~20 MB, v3)
    PFE_DATASET=v4 python scripts/make_gpu_bundle.py     # v4 re-runs: run v4_from_v3 first

Contains src/, scripts/run_gpu.sh and scripts/colab_run.py, requirements.txt, the GPU-path
tests, the current dataset (PFE_DATASET), its cached feature panels (full and R3 windows),
the selected configurations (best.json of every tuning) and the SAFRAN grid table (Taccari
weather nodes). Raw data is otherwise not needed. See docs/gpu_howto.md.
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DATASET_DIR, RAW, RESULTS_DIR  # noqa: E402
OUT = ROOT / "gpu_bundle.zip"
INCLUDE = [ROOT / "src", ROOT / "scripts" / "run_gpu.sh", ROOT / "scripts" / "colab_run.py",
           ROOT / "requirements.txt", ROOT / "tests" / "__init__.py",
           ROOT / "tests" / "test_ealstm.py", ROOT / "tests" / "test_taccari.py",
           DATASET_DIR, RAW / "safran" / "grid_cells_66.parquet"]
INCLUDE += sorted((RESULTS_DIR / "_cache").glob("panel*.parquet"))
INCLUDE += sorted(RESULTS_DIR.glob("*_tuning/best.json"))

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for item in INCLUDE:
        if not item.exists():
            continue
        files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" not in f.parts:
                z.write(f, f.relative_to(ROOT))
print(f"{OUT.name}: {OUT.stat().st_size / 1e6:.1f} MB")
