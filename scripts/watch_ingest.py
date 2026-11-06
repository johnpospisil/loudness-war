#!/usr/bin/env python3
"""Live terminal progress for the AcousticBrainz ingest (stdlib only; Ctrl-C to quit).

python3 scripts/watch_ingest.py               # low-level dump, refresh every 5 s
python3 scripts/watch_ingest.py --highlevel   # high-level dump (P06)
python3 scripts/watch_ingest.py --once        # print once and exit
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

HIGH = "--highlevel" in sys.argv
D = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "interim"
    / ("ab_highlevel" if HIGH else "ab_lowlevel")
)
# sum of Content-Length over all 30 parts (low-level: P01; high-level: P06)
TOTAL_BYTES = 41_780_535_425 if HIGH else 631_788_161_107
PROC = "parse_highlevel --parts" if HIGH else "parse_lowlevel --parts"
TITLE = "AcousticBrainz HIGH-level ingest" if HIGH else "AcousticBrainz ingest"
RESUME = "make ingest-ab-hl" if HIGH else "make ingest-ab"
N_PARTS = 30
WIDTH = 40
LINE = re.compile(
    r"(part=\d\d):\s+(\d+)%\|[^|]*\|\s*([\d.]+)([kMGT]?)/([\d.]+)([kMGT]?)"
    r"(?: \[[^<]*<([^,]*),\s*([\d.]+)([kMGT]?)B/s)?"
)
SCALE = {"": 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}


def bar(frac: float, width: int = WIDTH) -> str:
    full = int(frac * width)
    return (
        "█" * full
        + ("▌" if frac * width - full >= 0.5 else "")
        + "░" * (width - full - (1 if frac * width - full >= 0.5 else 0))
    )


def hms(s: float) -> str:
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def snapshot() -> str:
    done = {}
    for f in D.glob("part=*.done.json"):
        done[f.name[:7]] = json.loads(f.read_text())
    bytes_done = sum(s["bytes"] for s in done.values())
    rows_done = sum(s["rows"] for s in done.values())

    active = {}
    log = D / "ingest.log"
    if log.exists():
        for chunk in log.read_text(errors="replace").replace("\r", "\n").splitlines():
            m = LINE.search(chunk)
            if m and m.group(1) not in done:
                active[m.group(1)] = m
    running = subprocess.run(["pgrep", "-f", PROC],
                             capture_output=True).returncode == 0  # fmt: skip

    lines = []
    bytes_active, rate = 0.0, 0.0
    for name, m in sorted(active.items()):
        cur = float(m.group(3)) * SCALE[m.group(4)]
        tot = float(m.group(5)) * SCALE[m.group(6)]
        r = float(m.group(8)) * SCALE[m.group(9)] if m.group(8) else 0.0
        bytes_active += cur
        rate += r
        lines.append(f"  {name}  {bar(cur / tot, 30)} {100 * cur / tot:5.1f}%  "
                     f"{cur / 1e9:5.1f}/{tot / 1e9:.1f} GB  {r / 1e6:4.1f} MB/s")  # fmt: skip

    got = bytes_done + bytes_active
    frac = min(got / TOTAL_BYTES, 1.0)
    eta = (TOTAL_BYTES - got) / rate if rate > 0 else None
    head = [
        f"{TITLE} — {'RUNNING' if running else f'NOT RUNNING ({RESUME} resumes)'}"
        f"   {time.strftime('%H:%M:%S')}",
        f"  ALL      {bar(frac)} {100 * frac:5.1f}%  {got / 1e9:6.1f}/{TOTAL_BYTES / 1e9:.0f} GB",
        f"  parts {len(done):2d}/{N_PARTS} done · {rows_done:,} rows · {rate / 1e6:.1f} MB/s · "
        f"ETA {hms(eta) if eta else '—'}",
        "",
    ]
    errs = (
        [ln for ln in log.read_text(errors="replace").splitlines() if "ERROR" in ln][-3:]
        if log.exists()
        else []
    )  # noqa: E501
    return "\n".join(head + lines + ([""] + errs if errs else []))


def main() -> None:
    if "--once" in sys.argv:
        print(snapshot())
        return
    try:
        while True:
            out = snapshot()
            sys.stdout.write(
                "\033[H\033[J" + out + "\n\n  (bars update about once a minute · Ctrl-C to quit)\n"
            )
            sys.stdout.flush()
            time.sleep(5)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
