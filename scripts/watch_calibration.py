#!/usr/bin/env python3
"""Live terminal progress for the P03 library measurement (stdlib only; Ctrl-C to quit).

    python3 scripts/watch_calibration.py          # refresh every 5 s
    python3 scripts/watch_calibration.py --once   # print once and exit

Reads data/interim/p03_calibration/library.log (a line every 25 files) and counts the
Essentia extractor processes currently running.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "data/interim/p03_calibration/library.log"
HEAD = re.compile(r"library: (\d+) done, (\d+) to measure with (\d+) workers")
PROG = re.compile(r"^\s*(\d+)/(\d+)\s+([\d.]+) files/s")
WIDTH = 40


def bar(frac: float) -> str:
    full = int(frac * WIDTH)
    return "█" * full + "░" * (WIDTH - full)


def hms(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def running() -> int:
    out = subprocess.run(
        ["pgrep", "-f", "streaming_extractor_music"], capture_output=True, text=True
    ).stdout
    return len(out.split())


def snapshot() -> str:
    if not LOG.exists():
        return "No calibration run found (library.log missing)."
    text = LOG.read_text()
    head = HEAD.search(text)
    prog = [PROG.match(line) for line in text.splitlines()]
    prog = [m for m in prog if m]
    prior, todo, workers = (int(g) for g in head.groups()) if head else (0, 0, 0)
    done, rate = (int(prog[-1][1]), float(prog[-1][3])) if prog else (0, 0.0)
    total = todo or 1
    # files finished since the last log line are invisible; extrapolate from the rate
    since = time.time() - LOG.stat().st_mtime
    live = running()
    finished = done >= total or (live == 0 and since > 30)
    est = done if finished else min(total, done + int(rate * since))
    frac = est / total
    eta = (total - est) / rate if rate else float("nan")
    elapsed = done / rate if rate else 0
    state = "FINISHED" if finished else "RUNNING"
    lines = [
        f"P03 library calibration — {state}   {time.strftime('%H:%M:%S')}",
        f"  {bar(frac)}  {frac:6.1%}   {est:,}/{total:,} files",
        f"  {rate:.2f} files/s · {live} extractors running ({workers} workers)"
        f" · elapsed {hms(elapsed + since)} · ETA {'—' if finished else hms(eta)}",
    ]
    if prior:
        lines.append(f"  ({prior:,} files already measured in an earlier run)")
    if "Traceback" in text:
        lines.append("  ⚠ Traceback in library.log — check it")
    lines.append(
        "\n  (log line every 25 files; between them the count is estimated · Ctrl-C to quit)"
    )
    return "\n".join(lines)


def main() -> None:
    if "--once" in sys.argv:
        print(snapshot())
        return
    try:
        while True:
            sys.stdout.write("\033[H\033[J" + snapshot() + "\n")
            sys.stdout.flush()
            time.sleep(5)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
