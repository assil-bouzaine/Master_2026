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

# Phase 4 of the analysis plan (§14, items 18 and 20). Keep the helpers here so
# they travel with the dispatcher in the CPU bundle.
p4_command() {
  if [[ ${P4_DRYRUN:-0} == 1 ]]; then
    printf '%q' "$1"
    shift
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

p4_regimes() {
  local name=$1 regimes=$2 reconstruction=$3
  shift 3
  local -a fit=("$PY" -m src.models.response "${p4_flags[@]}" --pumping-reconstruction "$reconstruction" "$@")
  local failed=0 r1_failed=0 folds_failed=0 fold
  p4_command "${fit[@]}" --run "$name" || r1_failed=1
  if [[ $regimes != r1 ]]; then
    for fold in 0 1 2 3 4; do
      p4_command "${fit[@]}" --run "${name}_lwo" --fold "$fold" || folds_failed=1
    done
    if (( ! folds_failed )); then
      p4_command "$PY" -c 'import sys; from src.models.regimes import assemble_lwo; assemble_lwo(sys.argv[1], seeds=list(map(int, sys.argv[2:])))' \
        "${name}_lwo" "${p4_seeds[@]}" || failed=1
    fi
  fi
  if [[ $regimes == all ]]; then
    p4_command "${fit[@]}" --run "${name}_f25" --train-start "$f25" || failed=1
    p4_command "${fit[@]}" --run "${name}_f50" --train-start "$f50" || failed=1
    if (( ! r1_failed )); then
      p4_command "${fit[@]}" --run "${name}_refit" --refit-from "$name" || failed=1
    fi
  fi
  return "$((r1_failed || folds_failed || failed))"
}

p4_wait() {
  waitall "${p4_pids[@]}" || p4_failed=1
  p4_pids=()
}

p4_enqueue() {
  if [[ ${P4_DRYRUN:-0} == 1 ]]; then
    p4_regimes "$@" || p4_failed=1
  else
    # An arm and reconstruction run their regimes in order. Up to four
    # independent jobs share the CPUs, with one fit active per job.
    p4_regimes "$@" &
    p4_pids+=("$!")
    if (( ${#p4_pids[@]} == 4 )); then
      p4_wait
    fi
  fi
}

p4_controls() {
  local block=$1 regimes=$2 draw
  shift 2
  for draw in 0 1 2 3 4; do
    p4_enqueue "p4_${block}_Edeg${draw}_r1" "$regimes" 1 --arm "E_degree:$draw" "$@"
    p4_enqueue "p4_${block}_Edist${draw}_r1" "$regimes" 1 --arm "E_distance:$draw" "$@"
    p4_enqueue "p4_${block}_Frand${draw}_r1" "$regimes" 1 --arm "F_random:$draw" "$@"
  done
  p4_enqueue "p4_${block}_Fcomp_r1" "$regimes" 1 --arm F_complete "$@"
}

p4_step() (
  if [[ ${P4_CONFIRMED:-0} != 1 ]]; then
    echo "Phase 4 is locked until Gate 3 and the plan's tag (docs/phase4_runs.md)"
    return 0
  fi

  local mode=${P4_MODE:-pooled} lam=${P4_LAM:-0.1} fixed=${P4_FIXED:-}
  local recharge=${P4_RECHARGE:-linear}   # the main recharge stress (Gate 3 point 7: linear or pe)
  local statics=${P4_RUNG4_STATICS:-} p4_failed=0
  local -a p4_seeds reconstructions soft_grid rung4=() p4_pids=()
  read -r -a p4_seeds <<< "${P4_SEEDS:-0 1 2 3 4 5 6 7 8 9}"
  read -r -a reconstructions <<< "${P4_RECONS:-1 2 3}"
  read -r -a soft_grid <<< "${P4_SOFT_GRID:-1 10 100}"
  local -a p4_flags=(--mode "$mode" --lam "$lam" --recharge "$recharge" --conv fft --seeds "${p4_seeds[@]}")
  if [[ -n $fixed ]]; then p4_flags+=(--fixed-steps "$fixed"); fi
  if [[ -n $statics ]]; then rung4=(--statics "$statics"); fi
  export PFE_THREADS=1

  local reconstruction arm facts control soft policy f25 f50 starts
  if [[ $1 == p4_B1 || $1 == p4_B1c || $1 == p4_B2 ]]; then
    # The dry run reads these dates too, so it prints the actual fit arguments.
    starts=$("$PY" -c 'from src.config import R3_STARTS; print(R3_STARTS["f25"], R3_STARTS["f50"])') || return 1
    read -r f25 f50 <<< "$starts"
  fi

  case $1 in
    p4_B1)
      for reconstruction in "${reconstructions[@]}"; do
        for facts in A B; do
          p4_enqueue "p4_B1_${facts}_r${reconstruction}" all "$reconstruction" --arm baseline --statics "$facts"
        done
      done ;;
    p4_B1c)
      for control in nametags shuffled; do
        p4_enqueue "p4_B1c_B_${control}_r1" all 1 --arm baseline --statics B --static-control "$control"
      done ;;
    p4_B2)
      for reconstruction in "${reconstructions[@]}"; do
        for arm in C D; do
          p4_enqueue "p4_B2_${arm}_r${reconstruction}" all "$reconstruction" --arm "$arm" "${rung4[@]}"
        done
      done ;;
    p4_B3)
      p4_controls B3 r1-r2 "${rung4[@]}" ;;
    p4_B4)
      for reconstruction in "${reconstructions[@]}"; do
        p4_enqueue "p4_B4_D_hard_r${reconstruction}" r1-r2 "$reconstruction" --arm D "${rung4[@]}"
        p4_enqueue "p4_B4_D_none_r${reconstruction}" r1-r2 "$reconstruction" --arm D "${rung4[@]}" --signs none
        for soft in "${soft_grid[@]}"; do
          p4_enqueue "p4_B4_D_soft${soft}_r${reconstruction}" r1-r2 "$reconstruction" \
            --arm D "${rung4[@]}" --signs none --soft "$soft"
        done
      done ;;
    p4_B5)
      for arm in C D; do
        p4_enqueue "p4_B5_${arm}_r1" r1-r2 1 --arm "$arm" --statics B --message 1
      done
      p4_controls B5 r1 --statics B --message 1 ;;
    p4_B6)
      for policy in confident-only all-links; do
        if [[ ! -d data/processed/kg/export_v4_${policy} ]]; then
          echo "p4_B6: missing data/processed/kg/export_v4_${policy}; skipping $policy"
          continue
        fi
        for arm in C D; do
          p4_enqueue "p4_B6_${arm}_${policy}_r1" r1-r2 1 --arm "$arm" --policy "$policy" "${rung4[@]}"
        done
      done ;;
    p4_B7)
      # recharge sensitivities of arm D (options added 2026-11-20, worker task T14): the unit-wide
      # recharge cells, and soil drainage instead of the main recharge stress (the later
      # --recharge overrides P4_RECHARGE's: argparse keeps the last value)
      p4_enqueue p4_B7_D_unitwide_r1 r1 1 --arm D "${rung4[@]}" --recharge-relation recharge_unitwide
      p4_enqueue p4_B7_D_drainage_r1 r1 1 --arm D "${rung4[@]}" --recharge drainc ;;
  esac
  p4_wait
  return "$p4_failed"
)

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
    p4_B[1-7]|p4_B1c) p4_step "$s" ;;
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
