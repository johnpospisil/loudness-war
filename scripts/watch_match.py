#!/usr/bin/env python3
"""Live terminal view of the P08 release match (stdlib only; Ctrl-C to quit).

python3 scripts/watch_match.py          # refresh every 5 s
python3 scripts/watch_match.py --once   # print once and exit

DuckDB reports no progress for a single big query, so there is no honest percentage. Instead:
a stage bar (the match runs 6 steps; the last one writes ab_matched.parquet.tmp, which is the
only step visible from outside), the output size and its write rate, DuckDB's spill folder,
free disk, and the process's memory and CPU.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "interim" / "ab_matched.parquet"
TMP = OUT.with_name(OUT.name + ".tmp")
SPILL = ROOT / "data" / "interim" / "duckdb_tmp"
SUMMARY = ROOT / "data" / "interim" / "ab_matched_summary.json"
STAGES = ["keys", "redirects", "releases", "tiers A/B/C", "join to submissions", "write"]
WIDTH = 30


def _proc():
    """(pid, elapsed, rss_gb, cpu%) of the running matcher, or None."""
    try:
        pid = subprocess.run(
            ["pgrep", "-f", "lw.build.release_match"], capture_output=True, text=True
        ).stdout.split()
    except OSError:
        return None
    if not pid:
        return None
    rows = []  # `uv run` is a parent process too: report the one doing the work (largest RSS)
    for p in pid:
        out = subprocess.run(
            ["ps", "-o", "etime=,rss=,pcpu=", "-p", p], capture_output=True, text=True
        ).stdout.split()
        if len(out) >= 3:
            rows.append((p, out[0], int(out[1]) / 2**20, float(out[2])))
    return max(rows, key=lambda r: r[2]) if rows else None


def _du(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _gb(b: float) -> str:
    return f"{b / 1e9:6.2f} GB"


def snapshot(prev):
    pr = _proc()
    now = time.time()
    tmp = TMP.stat().st_size if TMP.exists() else 0
    done = OUT.exists() and not TMP.exists() and (pr is None)
    if done:
        stage = len(STAGES)
    elif tmp:
        stage = len(STAGES) - 1
    else:
        stage = None  # steps 1-5 are invisible from outside; we only know it's before "write"
    lines = [f"P08 release match — {'DONE' if done else 'RUNNING' if pr else 'NOT RUNNING'}"
             f"   {time.strftime('%H:%M:%S')}"]  # fmt: skip
    if stage is None:
        bar = "▒" * (WIDTH * 5 // 6) + "░" * (WIDTH - WIDTH * 5 // 6)
        lines.append(f"  stages   {bar}  steps 1-5 (keys → join), not visible separately")
    else:
        k = WIDTH * (stage + (0 if done else 0.5)) // len(STAGES)
        bar = "█" * int(k) + "░" * (WIDTH - int(k))
        lab = "all 6 done" if done else f"step 6/6: {STAGES[-1]}"
        lines.append(f"  stages   {bar}  {lab}")
    rate = ""
    if prev and tmp and now > prev[0]:
        r = (tmp - prev[1]) / (now - prev[0])
        rate = f"  +{r / 1e6:5.1f} MB/s" if r > 0 else "  (not growing: finishing row groups)"
    size = OUT.stat().st_size if done else tmp
    lines.append(
        f"  output   {_gb(size)}{rate}   (part-0 trial scaled ≈ 5.9 GB; actual runs larger)"
    )
    free = shutil.disk_usage(ROOT).free
    lines.append(f"  spill    {_gb(_du(SPILL))}  DuckDB temp   ·   free disk {_gb(free)}")
    if pr:
        lines.append(
            f"  process  pid {pr[0]} · elapsed {pr[1]} · RAM {pr[2]:.1f} GB · CPU {pr[3]:.0f}%"
        )
    if done and SUMMARY.exists():
        lines.append(f"  summary  {SUMMARY.relative_to(ROOT)} written")
    if not pr and not done:
        lines.append("  ⚠ no matcher process and no finished output — rerun `make match`")
    return "\n".join(lines), (now, tmp)


def main():
    if "--once" in sys.argv:
        print(snapshot(None)[0])
        return
    prev = None
    try:
        while True:
            text, prev = snapshot(prev)
            sys.stdout.write("\033[H\033[J" + text + "\n\n  (refresh 5 s · Ctrl-C to quit)\n")
            sys.stdout.flush()
            if "DONE" in text.splitlines()[0]:
                break
            time.sleep(5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
