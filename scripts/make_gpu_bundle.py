"""Pack code + model-ready data into one zip to run the neural baselines on a GPU.

    python scripts/make_gpu_bundle.py                    # -> gpu_bundle.zip (~20 MB, v3)
    PFE_DATASET=v4 python scripts/make_gpu_bundle.py     # v4 re-runs: run v4_from_v3 first

Contains src/, scripts/run_gpu.sh and scripts/colab_run.py, requirements.txt, the GPU-path
tests, the current dataset (PFE_DATASET), its cached feature panels (full and R3 windows),
and the selected configurations and refit epoch records (analysis plan sections 4 and 5).
The SAFRAN grid table supplies Taccari's weather nodes. The arm D edge table and its export
manifest supply the black-box comparison (Gate 3 point 21). See docs/gpu_howto.md.
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DATASET, DATASET_DIR, PROCESSED, RAW  # noqa: E402

OUT = ROOT / "gpu_bundle.zip"


def bundle_files():
    """Yield files to archive under their original repository paths."""
    results = ROOT / "results" / DATASET
    export = PROCESSED / "kg" / f"export_{DATASET}_main"
    include = [ROOT / "src", ROOT / "scripts" / "run_gpu.sh", ROOT / "scripts" / "colab_run.py",
               ROOT / "requirements.txt", ROOT / "tests" / "__init__.py",
               ROOT / "tests" / "test_ealstm.py", ROOT / "tests" / "test_taccari.py",
               DATASET_DIR, RAW / "safran" / "grid_cells_66.parquet",
               export / "edges_D.parquet", export / "manifest.json"]
    include += sorted(p for p in (results / "_cache").glob("panel*.parquet")
                      if not p.match("panel_lu_*"))
    for pattern in ("*_tuning/best.json", "*_tuned/best.json", "*_tuned/seed_*.json"):
        include += sorted(results.glob(pattern))
    for item in include:
        files = sorted(item.rglob("*")) if item.is_dir() else [item]
        for f in files:
            if f.is_file() and "__pycache__" not in f.parts:
                yield f


def main():
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in bundle_files():
            z.write(f, f.relative_to(ROOT))
    print(f"{OUT.name}: {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
