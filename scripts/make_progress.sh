#!/bin/bash
# Progress bar for a make run whose output goes to a log file.
#   scripts/make_progress.sh LOGFILE TARGET...      e.g. scripts/make_progress.sh run.log rebuild
# Counts the pipeline commands make has started (uv run / caffeinate / quarto lines in the
# log) against the total that `make -n TARGET...` would run. Ctrl-C to stop watching; the
# make run itself is not affected.
LOG=$1
shift
cd "$(dirname "$0")/.." || exit 1
CMD='^(uv run|caffeinate|QUARTO_PYTHON)'
TOTAL=$(make -n "$@" 2>/dev/null | grep -cE "$CMD")
[ "$TOTAL" -gt 0 ] || { echo "no commands found for: make $*"; exit 1; }
W=40
START=$(date +%s)
while :; do
  DONE=$(grep -cE "$CMD" "$LOG" 2>/dev/null)
  CUR=$(grep -E "$CMD" "$LOG" 2>/dev/null | tail -1 | sed -E 's/.* -m ([^ ]+).*/\1/; s/^QUARTO_PYTHON.*/quarto render/')
  RUNNING=$(pgrep -x make >/dev/null && echo 1 || echo 0)
  FINISHED=$DONE
  [ "$RUNNING" = 1 ] && [ "$DONE" -gt 0 ] && FINISHED=$((DONE - 1))
  F=$((FINISHED * W / TOTAL))
  BAR=$(printf '%*s' "$F" '' | tr ' ' '#')$(printf '%*s' $((W - F)) '' | tr ' ' '.')
  MIN=$((($(date +%s) - START) / 60))
  printf '\r[%s] %3d%%  %2d/%d done  %3d min  now: %-38s' \
    "$BAR" $((FINISHED * 100 / TOTAL)) "$FINISHED" "$TOTAL" "$MIN" "${CUR:-starting}"
  if grep -qE 'make: \*\*\* .*Error' "$LOG"; then
    printf '\n\nFAILED:\n'; grep -E 'Error|Traceback' "$LOG" | tail -5; exit 1
  fi
  if [ "$RUNNING" = 0 ]; then printf '\n\nmake has finished.\n'; exit 0; fi
  sleep 5
done
