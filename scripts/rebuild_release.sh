#!/usr/bin/env bash
# Rebuild a knowledge-graph release and everything bound to it, in order (step 12 / v5 plan R2):
# facts -> rules + validation (the release) -> persisted store -> inventory, export and control graphs of the
# three pump-link policies -> CQ timing (last, as it exits 1 when a query is slow). Laptop only (no model fitting). Each step's log goes to LOGDIR.
#     bash scripts/rebuild_release.sh v5 results/logs/rebuild_<date>
# Never edit ontology/, rules or shapes while it runs: the release refuses inputs that changed during the
# derivation (src/kg/release.py). The test suites are run separately afterwards.
set -euo pipefail
DATASET=${1:?dataset, e.g. v5}
LOGDIR=${2:?log directory}
mkdir -p "$LOGDIR"
export PFE_DATASET=$DATASET PYTHONIOENCODING=utf-8
PY=.venv/bin/python
step() {                       # step NAME CMD...: run, log, time
  local name=$1; shift
  local t0=$SECONDS
  echo "== $(date -u +%FT%TZ) $name: $*" | tee -a "$LOGDIR/rebuild.log"
  if "$@" > "$LOGDIR/$name.log" 2>&1; then
    echo "   ok in $((SECONDS - t0)) s" | tee -a "$LOGDIR/rebuild.log"
  else
    echo "   FAILED after $((SECONDS - t0)) s (see $LOGDIR/$name.log)" | tee -a "$LOGDIR/rebuild.log"
    exit 1
  fi
}
step build_kg     $PY -m src.kg.build_kg
step apply_rules  $PY -m src.kg.apply_rules
step store        $PY -m src.kg.store
for p in main confident-only all-links; do
  step "inventory_$p" $PY -m src.kg.inventory --policy "$p"
  step "export_$p"    $PY -m src.kg.export --policy "$p"
  step "controls_$p"  $PY -m src.kg.controls --policy "$p"
done
step cq_timing    $PY -m src.kg.cq_timing     # last: exits 1 when a query reaches 1 s (Gate R2)
echo "== $(date -u +%FT%TZ) done" | tee -a "$LOGDIR/rebuild.log"
