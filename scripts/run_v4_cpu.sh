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
waitall() {
  local pid rc=0
  for pid in "$@"; do
    wait "$pid" || rc=1
  done
  return "$rc"
}

failed=()
if [[ -n ${STATUS_FILE:-} ]]; then
  : > "$STATUS_FILE" || exit 1
fi
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
    ladder)       # rungs 1-2 of the model ladder (analysis plan §14 item 18): 10 starts each,
                  # four runs at a time, one thread per run
                  ( export PFE_THREADS=1; R="$PY -m src.models.response"; pids=(); rc=0
                    $R --mode free --run resp_free &
                    pids+=("$!")
                    $R --mode shared --run resp_shared &
                    pids+=("$!")
                    $R --mode pooled --lam 0.01 --run resp_pooled_l001 &
                    pids+=("$!")
                    $R --mode pooled --lam 0.1 --run resp_pooled_l01 &
                    pids+=("$!")
                    waitall "${pids[@]}" || rc=1
                    pids=()
                    $R --mode pooled --lam 1 --run resp_pooled_l1 &
                    pids+=("$!")
                    $R --mode pooled --lam 10 --run resp_pooled_l10 &
                    pids+=("$!")
                    $R --mode free --amax 104 --kernel-weeks 520 --run resp_free_a104 &   # sensitivity
                    pids+=("$!")
                    $R --mode free --recharge pe --run resp_free_pe &                     # sensitivity
                    pids+=("$!")
                    waitall "${pids[@]}" || rc=1
                    exit "$rc" ) ;;
    ladder2)      # follow-ups of the first ladder results (analysis plan §14 item 18, 2026-11-10)
                  ( export PFE_THREADS=1; R="$PY -m src.models.response"; pids=(); rc=0
                    $R --mode free --fixed-steps 3000 --run resp_free_conv &                 # diagnostic
                    pids+=("$!")
                    $R --mode pooled --lam 0.1 --fixed-steps 3000 --run resp_pooled_l01_conv &
                    pids+=("$!")
                    $R --mode free --pumping split --run resp_free_split &                   # sensitivity
                    pids+=("$!")
                    $R --mode pooled --lam 0.01 --pumping split --run resp_pooled_split &
                    pids+=("$!")
                    waitall "${pids[@]}" || rc=1
                    pids=()
                    $R --mode pooled --lam 0.01 --gain-units sd --run resp_pooled_sd_l001 &
                    pids+=("$!")
                    $R --mode pooled --lam 0.1 --gain-units sd --run resp_pooled_sd_l01 &
                    pids+=("$!")
                    $R --mode pooled --lam 1 --gain-units sd --run resp_pooled_sd_l1 &
                    pids+=("$!")
                    $R --mode shared --gain-units sd --run resp_shared_sd &
                    pids+=("$!")
                    waitall "${pids[@]}" || rc=1
                    exit "$rc" ) ;;
    twin_pilot)   # the twin's pilot (analysis plan §14 item 19 and its amendment of 2026-11-16):
                  # base cell, worlds 0-2, arms C, D, T; one process per world and learner setting;
                  # the RQ2 settings (none, soft) on arms D and T, beside the hard ones of twin_pilot
                  ( export PFE_THREADS=1; T="$PY -m src.models.twin"; pids=()
                    for w in 0 1 2; do
                      $T --run twin_pilot --worlds $w --fits free pooled:0.01 &
                      pids+=("$!")
                      $T --run twin_pilot_conv --worlds $w --fits pooled:0.1:3000 &
                      pids+=("$!")
                      $T --run twin_pilot_rq2 --worlds $w --fits free+none free+soft1 --arms D T &
                      pids+=("$!")
                    done
                    waitall "${pids[@]}" ) ;;
    twin_grid)    # the knowledge-value map (item 19): 12 cells (eps x u) x 20 worlds, both protocols
                  # (rule of 2026-11-16); four processes, a quarter of the worlds each, resumable
                  ( export PFE_THREADS=1; T="$PY -m src.models.twin"; pids=()
                    for part in 0-4 5-9 10-14 15-19; do
                      $T --run twin_map --grid --worlds $part --fits free pooled:0.1:3000 &
                      pids+=("$!")
                    done
                    waitall "${pids[@]}" ) ;;
    twin_slices)  # the slices of item 19 (pi, nu, timing, variants I, O, S, G) from the base cell,
                  # both protocols; then RQ2 on arms D and T: hard ("free"), none and soft on the same
                  # worlds (hard added 2026-11-20, so that RQ2's reading has score 5 per well for all
                  # three settings: astra review point 1)
                  ( export PFE_THREADS=1; T="$PY -m src.models.twin"; pids=(); rc=0
                    for part in 0-4 5-9 10-14 15-19; do
                      $T --run twin_slices --slices --worlds $part --fits free pooled:0.1:3000 &
                      pids+=("$!")
                    done
                    waitall "${pids[@]}" || rc=1
                    pids=()
                    for part in 0-9 10-19; do
                      $T --run twin_rq2 --worlds $part --fits free free+none free+soft1 --arms D T &
                      pids+=("$!")
                      $T --run twin_rq2 --slices --worlds $part --fits free free+none free+soft1 --arms D T &
                      pids+=("$!")
                    done
                    waitall "${pids[@]}" || rc=1
                    exit "$rc" ) ;;
    final:*)      $PY -m src.models.tune --model "${s#final:}" --final-only ;;   # v3 choice
    regimes:*)    $PY -m src.models.regimes --model "${s#regimes:}" ;;
    *)            echo "unknown step $s"; false ;;
  esac || {
    echo "!! step $s failed, continuing"
    failed+=("$s")
    # Keep failures already seen if the time budget stops a later step.
    if [[ -n ${STATUS_FILE:-} ]]; then
      printf '%s\n' "$s" >> "$STATUS_FILE" || exit 1
    fi
  }
done
echo "== $(date) done"
if (( ${#failed[@]} )); then
  echo "== failed steps: ${failed[*]}"
  exit 1
fi
exit 0
