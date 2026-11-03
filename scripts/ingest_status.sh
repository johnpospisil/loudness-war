#!/bin/bash
# Show AcousticBrainz ingest progress: finished parts, rows so far, and the latest bar per part.
d="$(dirname "$0")/../data/interim/ab_lowlevel"
done_n=$(ls "$d"/part=*.done.json 2>/dev/null | wc -l | tr -d ' ')
rows=$(cat "$d"/part=*.done.json 2>/dev/null | grep '"rows"' | tr -dc '0-9\n' | paste -sd+ - | bc)
echo "Parts finished: $done_n / 30   rows parsed: ${rows:-0}"
if pgrep -f "parse_lowlevel --parts" >/dev/null; then echo "Ingest: RUNNING"; else echo "Ingest: NOT running (rerun 'make ingest-ab' to resume)"; fi
tr '\r' '\n' < "$d/ingest.log" | grep -E "^part=" | awk -F: '{last[$1]=$0} END {for (k in last) print last[k]}' | sort | tail -4
grep -E "ERROR|failed" "$d/ingest.log" | tail -3
