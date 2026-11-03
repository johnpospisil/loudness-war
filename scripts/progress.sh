#!/bin/bash
# Usage: bash progress.sh <file> <total_bytes>
f="$1"; total="$2"
t0=$(date +%s); s0=$(stat -f %z "$f" 2>/dev/null || echo 0)
while :; do
  cur=$(stat -f %z "$f" 2>/dev/null || echo 0)
  pct=$(( cur * 100 / total )); fill=$(( pct / 2 ))
  el=$(( $(date +%s) - t0 ))
  rate=0; eta=0
  if [ "$el" -gt 0 ]; then rate=$(( (cur - s0) / el )); fi
  if [ "$rate" -gt 0 ]; then eta=$(( (total - cur) / rate )); fi
  bar=$(printf '%*s' "$fill" '' | tr ' ' '#')$(printf '%*s' $((50 - fill)) '' | tr ' ' '-')
  printf "\r[%s] %3d%%  %5.2f/%.2f GB  %5.1f MB/s  ETA %dm%02ds " "$bar" "$pct" \
    "$(bc -l <<<"$cur/1000000000")" "$(bc -l <<<"$total/1000000000")" \
    "$(bc -l <<<"$rate/1000000")" $((eta / 60)) $((eta % 60))
  if [ "$cur" -ge "$total" ]; then echo; echo "Done."; break; fi
  sleep 2
done
