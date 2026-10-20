#!/usr/bin/env bash
# Run the slow baselines on a GPU machine (Camber JupyterLab node, Colab, Kaggle).
# Resumable: finished seeds / wells are saved, re-running continues where it stopped.
#   cd <bundle folder> && nohup bash scripts/run_gpu.sh > results/gpu_run.log 2>&1 &
#
# Keeps the machine's own CUDA PyTorch: a venv with --system-site-packages sees it,
# and our exact pins (everything except torch) are installed into the venv with
# --no-deps, so pip never replaces torch (a ~2 GB download).
# The venv lives on local disk (/tmp), not in the project folder: on Camber the
# project folder is the synced Stash and must not receive hundreds of MB of packages.
set -uo pipefail   # no -e: one failed step must not stop the sweep
VENV=${VENV:-/tmp/venv_gpu}
cd "$(dirname "$0")/.."
mkdir -p results
echo "== $(date -u) start on $(hostname)"
python3 -c "import torch; print('system torch', torch.__version__, '| CUDA available:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv --system-site-packages "$VENV"
fi
# (re)install the pins every start: fast when already satisfied, repairs a broken venv
{
  EXCL='^(torch|nvidia-|triton)'
  # if the system torch was built for numpy 1.x, keep the system numpy
  if python3 -c "import numpy, sys; sys.exit(0 if numpy.__version__.startswith('1.') else 1)"; then
    EXCL='^(torch|nvidia-|triton|numpy==)'
    echo "system numpy is 1.x: keeping it"
  fi
  grep -v -E "$EXCL" requirements.txt > "$VENV/req_gpu.txt"
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -q --no-deps -r "$VENV/req_gpu.txt"
}
PY="$VENV/bin/python"
# Some images ship torchaudio/torchvision built for another torch; transformers
# imports them if present and crashes. Shadow them with versions matching the
# system torch (installed --no-deps into the venv; torch itself is untouched).
TV=$(python3 -c "import torch; print(torch.__version__.split('+')[0])")
TMINOR=$(echo "$TV" | cut -d. -f2)
if ! $PY -c "import torchaudio" 2>/dev/null; then
  echo "torchaudio broken or missing: installing torchaudio==$TV in the venv"
  $PY -m pip install -q --no-deps "torchaudio==$TV" || true
fi
if ! $PY -c "import torchvision" 2>/dev/null; then
  echo "torchvision broken or missing: installing torchvision==0.$((TMINOR + 15)).0 in the venv"
  $PY -m pip install -q --no-deps "torchvision==0.$((TMINOR + 15)).0" || true
fi
$PY -c "import torch, pandas, numpy; print('venv: torch', torch.__version__, 'cuda', torch.cuda.is_available(), '| pandas', pandas.__version__, '| numpy', numpy.__version__)"
export PYTHONIOENCODING=utf-8
export PFE_DATASET=${PFE_DATASET:-v3}
echo "dataset: $PFE_DATASET"
# Uploaded folders are read-only for Camber jobs: write to a fresh results folder and copy
# the cached feature panel into it (docs/gpu_howto.md).
if [ -n "${PFE_RESULTS:-}" ] && [ ! -f "$PFE_RESULTS/_cache/panel.parquet" ]; then
  mkdir -p "$PFE_RESULTS/_cache"
  cp "results/$PFE_DATASET/_cache/panel.parquet" "$PFE_RESULTS/_cache/"
fi
# v3 default sweep (docs/analysis_plan.md): default models for comparability, equal-budget
# tuning (24 Optuna trials) of every neural model, the RQ1 regimes of the tuned models, and
# the three Chronos-2 variants. Every step is resumable.
STEPS=${STEPS:-"lstm stgnn taccari chronos2 chronos2_xl chronos2_ft tune:lstm tune:stgnn tune:taccari regimes:lstm regimes:stgnn regimes:taccari tune:ealstm regimes:ealstm"}
for s in $STEPS; do
  echo "== $(date -u) step $s"
  case $s in
    stgnn)       $PY -m src.models.stgnn ;;                   # distance-graph ST-GNN, 5 seeds
    taccari)     $PY -m src.models.taccari ;;                 # Taccari-graph ST-GNN, 5 seeds
    lstm)        $PY -m src.models.lstm ;;                    # default LSTM, 5 seeds
    ealstm)      $PY -m src.models.lstm --arch ealstm --run ealstm ;;
    chronos2)    $PY -m src.models.chronos2 ;;                # zero-shot
    chronos2_xl) $PY -m src.models.chronos2 --mode xl ;;      # zero-shot, cross-learning
    chronos2_ft) $PY -m src.models.chronos2 --mode ft ;;      # fine-tuned on train
    tune_lstm)   $PY -m src.models.tune_lstm --trials 24 ;;   # v2 tuner (kept for v2 reruns)
    tune:*)      $PY -m src.models.tune --model "${s#tune:}" --trials 24 ;;
    regimes:*)   $PY -m src.models.regimes --model "${s#regimes:}" ;;
    *)           echo "unknown step $s" ;;
  esac || echo "!! step $s failed, continuing"
done
echo "== $(date -u) done"
