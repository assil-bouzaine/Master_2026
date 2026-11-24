#!/usr/bin/env bash
# Fetch the per-start contribution files of chosen Phase 4 runs from a Colab session (step 14).
# The main pull leaves contrib_seed_*.parquet on Colab (scripts/colab_cli.py pull --exclude), since the
# replay rebuilds them exactly; the runs that explanations and shortcut test 2 read (B2, B2conv, B4 at
# R1) are fetched here, both to use them directly and to check the replay against them.
#   bash scripts/fetch_contribs.sh SESSION [PATTERN ...]
# Default patterns: p4_B2_*_r1 p4_B2conv_* p4_B4_D_*_r1. Files land in results/v4/<run>/.
set -euo pipefail
cd "$(dirname "$0")/.."
session=$1; shift
patterns=("$@")
if (( ${#patterns[@]} == 0 )); then patterns=(p4_B2_*_r1 p4_B2conv_* p4_B4_D_*_r1); fi
stage=results/_colab_cli/$session
mkdir -p "$stage"
archive=$stage/contribs_$(date -u +%Y%m%dT%H%M%SZ).tgz
remote="cd /content/work/results_cpu/v4 && files=\$(ls -d ${patterns[*]} 2>/dev/null | while read d; do ls \$d/contrib_seed_*.parquet 2>/dev/null; done) && [ -n \"\$files\" ] && tar czf - \$files"
timeout 7200 colab ssh -s "$session" -- "$remote" < /dev/null > "$archive"
tar tzf "$archive" > /dev/null                      # a truncated archive fails here
n=$(tar tzf "$archive" | wc -l)
tar xzf "$archive" -C results/v4
echo "$session: $n contribution files from $(tar tzf "$archive" | cut -d/ -f1 | sort -u | wc -l) runs -> results/v4 ($archive)"
