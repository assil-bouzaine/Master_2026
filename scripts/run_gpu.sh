#!/usr/bin/env bash
# Run the slow baselines on a GPU machine (Camber JupyterLab node, Colab, Kaggle).
# Resumable: finished seeds / wells are saved, re-running continues where it stopped.
#   cd <bundle folder> && nohup bash scripts/run_gpu.sh > results/gpu_run.log 2>&1 &
#
# Keeps the machine's own CUDA PyTorch: a venv with --system-site-packages sees it,
# and our exact pins (everything except torch) are installed into the venv with
# --no-deps, so pip never replaces torch (a ~2 GB download).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
echo "== $(date -u) start on $(hostname)"
python3 -c "import torch; print('system torch', torch.__version__, '| CUDA available:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
if [ ! -x .venv_gpu/bin/python ]; then
  python3 -m venv --system-site-packages .venv_gpu
  EXCL='^(torch|nvidia-|triton)'
  # if the system torch was built for numpy 1.x, keep the system numpy
  if python3 -c "import numpy, sys; sys.exit(0 if numpy.__version__.startswith('1.') else 1)"; then
    EXCL='^(torch|nvidia-|triton|numpy==)'
    echo "system numpy is 1.x: keeping it"
  fi
  grep -v -E "$EXCL" requirements.txt > .venv_gpu/req_gpu.txt
  .venv_gpu/bin/python -m pip install -q --upgrade pip
  .venv_gpu/bin/python -m pip install -q --no-deps -r .venv_gpu/req_gpu.txt
fi
PY=.venv_gpu/bin/python
$PY -c "import torch, pandas, numpy; print('venv: torch', torch.__version__, 'cuda', torch.cuda.is_available(), '| pandas', pandas.__version__, '| numpy', numpy.__version__)"
export PYTHONIOENCODING=utf-8
$PY -m src.models.stgnn          # distance-graph ST-GNN, 5 seeds
$PY -m src.models.chronos2       # Chronos-2 zero-shot, remaining wells
echo "== $(date -u) done"
