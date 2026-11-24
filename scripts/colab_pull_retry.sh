#!/usr/bin/env bash
# Pull a Colab session's results with scripts/colab_cli.py, retrying a download that stalls.
#   bash scripts/colab_pull_retry.sh SESSION [colab_cli pull options, e.g. --exclude PATTERN]
# A dropped Wi-Fi leaves the `colab ssh` tar stream hanging without an error (2026-11-24: stuck for
# 12 min at 813 MB). The watchdog kills the transfer when the archive has not grown for STALL_S
# seconds while the ssh client is still running, and starts the pull again (up to TRIES times).
# After the download ends, extraction and rescoring do not grow the archive: the ssh client has
# exited by then, so the watchdog leaves them alone.
set -uo pipefail
cd "$(dirname "$0")/.."
session=$1; shift
STALL_S=${STALL_S:-120}
TRIES=${TRIES:-5}
stage=results/_colab_cli/$session
for attempt in $(seq 1 "$TRIES"); do
  rm -f "$stage"/pull_*.tgz
  .venv/bin/python -m scripts.colab_cli pull "$session" "$@" &
  pid=$!
  last=-1; still=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15
    f=$(ls "$stage"/pull_*.tgz 2>/dev/null | tail -1)
    size=$([ -n "$f" ] && stat -c %s "$f" || echo 0)
    ssh_pids=$(pgrep -f "colab ssh -s $session --|proxy-mode -s $session" || true)
    # Count a stall only while the download runs: once the archive is extracted (its folder exists)
    # the pull rescores locally and ends with a short ssh (the keep-alive flag); without an ssh client
    # nothing is downloading. (2026-11-24: the counter grew during rescoring and killed that last ssh.)
    if [ -n "$f" ] && [ -d "${f%.tgz}" ] || [ -z "$ssh_pids" ]; then still=0; last=$size; continue; fi
    if [ "$size" = "$last" ]; then still=$((still + 15)); else still=0; last=$size; fi
    if [ "$still" -ge "$STALL_S" ] && [ -n "$ssh_pids" ]; then
      echo "== attempt $attempt: no data for ${still}s at $((size / 1048576)) MB, restarting the transfer"
      kill $ssh_pids 2>/dev/null
      break
    fi
  done
  if wait "$pid"; then
    echo "== pull of $session done on attempt $attempt"
    exit 0
  fi
  echo "== attempt $attempt failed"
done
echo "== pull of $session failed after $TRIES attempts"
exit 1
