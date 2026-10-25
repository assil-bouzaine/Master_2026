#!/usr/bin/env bash
# Dataset v4 re-runs of the laptop baselines (analysis plan v2, section 5). Start it only
# when the v3 sweep has finished (pgrep -af src.models shows nothing):
#   setsid nohup bash scripts/run_v4_cpu.sh > results/v4/cpu_runs.log 2>&1 < /dev/null &
# Sequential and resumable like scripts/run_cpu.sh; the neural models run on Colab
# (docs/gpu_howto.md, "Dataset v4 re-runs"), except EA-LSTM, which also runs on a CPU
# (final:ealstm, regimes:ealstm). STEPS selects a subset. On Kaggle
# (scripts/kaggle_cpu_run.py) PY is the image's python with the pinned wheels.
set -u
cd "$(dirname "$0")/.."
export PFE_DATASET=v4 PYTHONIOENCODING=utf-8
PY=${PY:-.venv/bin/python}
JOBS=${JOBS:-2}
mkdir -p results/v4
STEPS=${STEPS:-"select naive lgbm lgbm_final lgbm_regimes pastas wellmodel"}
for s in $STEPS; do
  echo "== $(date) $s"
  case $s in
    select)       $PY scripts/v4_from_v3.py ;;                       # v3 selections -> v4
    naive)        $PY -m src.models.naive ;;                         # the skill benchmarks first
    lgbm)         $PY -m src.models.lgbm ;;                          # sensitivity rows + forecast
    lgbm_final)   $PY -m src.models.lgbm --no-clim --final-only ;;   # baseline of record
    lgbm_regimes) $PY -m src.models.lgbm --no-clim --regimes lwo f25 f50 ;;
    pastas)       $PY -m src.models.pastas_baseline --variant pastas pastas_seasonal_canal --workers $JOBS ;;
    wellmodel)    $PY -m src.models.pastas_baseline --variant pastas_wellmodel --workers $JOBS ;;
    pastas_starts)   $PY -m src.models.pastas_baseline --variant pastas_seasonal_canal \
                       --starts 0 1 2 3 4 5 6 7 8 9 --workers $JOBS ;;          # stability check
    pastas_trainobs) $PY -m src.models.pastas_baseline --variant pastas_seasonal_canal \
                       --starts 0 1 2 3 4 5 6 7 8 9 --train-obs --workers $JOBS ;;
    lu:lgbm)      $PY -m src.models.lgbm --no-clim --final-only --land-use on &&   # land-use test
                  $PY -m src.models.lgbm --no-clim --final-only --land-use none &&     # same-machine control
                  $PY -m src.models.lgbm --no-clim --final-only --land-use placebo &&  # (plan §14.13)
                  $PY -m src.models.lgbm --no-clim --final-only --land-use wide &&
                  $PY -m src.models.lgbm --no-clim --final-only --land-use frozen ;;
    lu:lstm)      $PY -m src.models.tune --model lstm --final-only --land-use on &&
                  $PY -m src.models.tune --model lstm --final-only --land-use none &&
                  $PY -m src.models.tune --model lstm --final-only --land-use placebo &&
                  $PY -m src.models.tune --model lstm --final-only --land-use wide &&
                  $PY -m src.models.tune --model lstm --final-only --land-use frozen ;;
    final:*)      $PY -m src.models.tune --model "${s#final:}" --final-only ;;   # v3 choice
    regimes:*)    $PY -m src.models.regimes --model "${s#regimes:}" ;;
    *)            echo "unknown step $s" ;;
  esac || echo "!! step $s failed, continuing"
done
echo "== $(date) done"
