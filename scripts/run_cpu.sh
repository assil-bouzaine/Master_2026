#!/usr/bin/env bash
# Laptop baselines for one dataset version (sequential, every step resumable).
#   nohup bash scripts/run_cpu.sh > results/v3/cpu_runs.log 2>&1 &
#   STEPS="pastas wellmodel" bash scripts/run_cpu.sh      # only some steps
# Pastas uses JOBS worker processes (default 2: the laptop lost power once with every core
# busy, and its battery holds 12 % of its design charge; per-well fits do not depend on the
# worker count). LightGBM keeps 4 threads (its runs are short).
# Neural models and Chronos-2 run on the GPU (scripts/run_gpu.sh, docs/gpu_howto.md).
set -u
cd "$(dirname "$0")/.."
export PFE_DATASET=${PFE_DATASET:-v3} PYTHONIOENCODING=utf-8
PY=.venv/bin/python
STEPS=${STEPS:-"naive lgbm lgbm_tuned pastas wellmodel"}
JOBS=${JOBS:-2}
for s in $STEPS; do
  echo "== $(date) $s"
  case $s in
    naive)      $PY -m src.models.naive ;;
    lgbm)       $PY -m src.models.lgbm ;;
    lgbm_tuned) $PY -m src.models.lgbm --tune 24 ;;          # Optuna study is resumable
    lgbm_noclim)  $PY -m src.models.lgbm --tune 24 --no-clim ;;   # networks' inputs (no clim_z)
    lgbm_regimes) $PY -m src.models.lgbm --no-clim --regimes lwo f25 f50 ;;   # RQ1, resumable
    pastas)     $PY -m src.models.pastas_baseline --variant pastas pastas_seasonal_canal --workers $JOBS ;;
    wellmodel)  $PY -m src.models.pastas_baseline --variant pastas_wellmodel --workers $JOBS ;;   # ~2-6 min/well
    *)          echo "unknown step $s" ;;
  esac || echo "!! step $s failed, continuing"
done
echo "== $(date) done"
