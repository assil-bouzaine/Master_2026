#!/usr/bin/env bash
# Run the slow baselines on a GPU machine (Camber, Colab, Kaggle). Resumable:
# every finished seed / well is saved, so re-running continues where it stopped.
#   bash scripts/run_gpu.sh            # from the unzipped bundle folder
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=results/gpu_run.log
mkdir -p results
{
  echo "== $(date -u) start on $(hostname)"
  # everything except our CPU-only torch pin; then the CUDA build from PyPI
  grep -v '^torch==' requirements.txt > /tmp/req_gpu.txt
  python -m pip install -q -r /tmp/req_gpu.txt
  python -m pip install -q "torch==2.14.1"
  python -c "import torch; print('CUDA available:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
  export PYTHONIOENCODING=utf-8
  python -m src.models.stgnn        # distance-graph ST-GNN, 5 seeds
  python -m src.models.chronos2     # Chronos-2 zero-shot, remaining wells
  echo "== $(date -u) done"
} 2>&1 | tee -a "$LOG"
