#!/usr/bin/env bash
# Prepare v5 inputs or time Hybrid-GNN v2 on Colab (analysis plan v3, section 3).
# The default only builds inputs. Run hgnn_smoke on remote compute, never the laptop.
set -u
cd "$(dirname "$0")/.."
export PFE_DATASET=v5 PYTHONIOENCODING=utf-8
# CPU fits only. A Colab TPU runtime ships the torch_tpu plugin; torch loads it on import and
# torch.manual_seed then seeds the TPU too, which one process at a time may hold. Disable
# the plugin so CPU fits can run together without trying to claim the TPU.
export TORCH_DEVICE_BACKEND_AUTOLOAD=0
PY=${PY:-.venv/bin/python}
mkdir -p results/v5
STEPS=${STEPS:-"prepare_check"}

hgnn_smoke() {
  local arm threads started rc=0
  local epochs=${HGNN_EPOCHS:-5} epochs_b=${HGNN_EPOCHS_B:-3}
  threads=${PFE_THREADS:-$(nproc)}
  nproc || return 1
  "$PY" -c 'import torch, torch_geometric; print("torch", torch.__version__, "torch_geometric", torch_geometric.__version__)' || return 1
  for arm in C D; do
    started=$(date +%s)
    PFE_ALLOW_TRAIN=1 PFE_NO_SCORE=1 PFE_THREADS=$threads "$PY" -m src.models.hybrid_gnn \
      --arm "$arm" --stage B --epochs "$epochs" --epochs-b "$epochs_b" --seeds 0 \
      --run "_smoke/hgnn_$arm" || rc=1
    echo "hgnn_smoke arm $arm: $(( $(date +%s) - started )) s for $((epochs + epochs_b)) epochs"
  done
  started=$(date +%s)
  PFE_ALLOW_TRAIN=1 PFE_NO_SCORE=1 PFE_THREADS=1 "$PY" -m src.models.hybrid_gnn \
    --arm D --stage B --epochs "$epochs" --epochs-b "$epochs_b" --seeds 0 \
    --run _smoke/hgnn_D_1thread || rc=1
  echo "hgnn_smoke arm D (1 thread): $(( $(date +%s) - started )) s for $((epochs + epochs_b)) epochs"
  return "$rc"
}

failed=()
if [[ -n ${STATUS_FILE:-} ]]; then
  : > "$STATUS_FILE" || exit 1
fi
for step in $STEPS; do
  echo "== $step"
  started=$(date +%s)
  case $step in
    prepare_check)
      "$PY" - <<'PY'
from src.models import hybrid_gnn

for arm in ("C", "D"):
    prep = hybrid_gnn.prepare(hybrid_gnn.build_parser().parse_args(["--arm", arm]))
    print(f"arm {arm}: pumping_record_start={prep['routed']['pumping_record_start']}", flush=True)
PY
      ;;
    hgnn_smoke) hgnn_smoke ;;
    *) echo "unknown step $step"; false ;;
  esac || {
    echo "!! step $step failed, continuing"
    failed+=("$step")
    if [[ -n ${STATUS_FILE:-} ]]; then
      printf '%s\n' "$step" >> "$STATUS_FILE" || exit 1
    fi
  }
  echo "== $step: $(( $(date +%s) - started )) s"
done
if (( ${#failed[@]} )); then
  echo "== failed steps: ${failed[*]}"
  exit 1
fi
exit 0
