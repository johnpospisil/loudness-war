"""P03: reproduce EBU R128 and measure audio with the AcousticBrainz-era Essentia extractor.

Three meters run on the same audio:

* **pyloudnorm** (ITU-R BS.1770-4 integrated loudness, EBU Tech 3342 loudness range): reference.
* **ffmpeg ``ebur128``**: an independent R128 implementation, used as a cross-check.
* **Essentia ``streaming_extractor_music`` v2.1_beta2** (the AcousticBrainz ``music 1.0``
  extractor, run under Rosetta): gives ``replay_gain``, ``dynamic_complexity`` and
  ``average_loudness`` exactly as they appear in the AcousticBrainz dumps.

The signals are the EBU Tech 3341 / 3342 conformance cases, a grid of synthetic
pink-noise programmes with controlled loudness, level variation and crest factor, and a
sample of the user's own library. Results go to ``data/interim/p03_calibration/``; the
calibration fit lives in :mod:`lw.measure.calibrate`.

CLI::

    python -m lw.measure.pyloudnorm_check conformance
    python -m lw.measure.pyloudnorm_check synthetic
    python -m lw.measure.pyloudnorm_check library --root "<music folder>" [--n 1200] [--jobs 5]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

ROOT = Path(__file__).resolve().parents[3]
EXTRACTOR = ROOT / "data/raw/essentia_extractor/streaming_extractor_music"
OUT_DIR = ROOT / "data/interim/p03_calibration"
AUDIO_EXT = {".m4a", ".mp3", ".flac", ".wav", ".aif", ".aiff", ".ogg"}
RATE = 48_000

# Memory guards (added after the 2026-11-04 freeze: three audiobooks of 1-11 h were each
# decoded whole into RAM by 5 parallel workers, ~64 GB on a 16 GB machine).
MAX_DURATION_S = 20 * 60  # longer files are not songs (audiobooks, DJ mixes): skip
# Measured peak for decode + pyloudnorm integrated_loudness + loudness_range: ~28 B per
# sample per channel (pyloudnorm upcasts to float64 and copies); 32 adds headroom.
BYTES_PER_SAMPLE = 32
MAX_FILE_BYTES = 3 * 2**30  # per-file decode budget (~16 min at 48 kHz stereo)
WORKER_OVERHEAD_BYTES = 512 * 2**20  # interpreter + Essentia extractor subprocess
SKIP_DIRS = {"ebooks", "audiobooks", "books", "podcasts", "voice memos"}


class SkipFile(Exception):
    """A file deliberately not measured (too long, too big to decode, not music)."""


def max_jobs_for_ram(ram_fraction: float = 0.7) -> int:
    """Workers that fit in ``ram_fraction`` of physical RAM at the worst-case file size."""
    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return max(1, int(ram * ram_fraction // (MAX_FILE_BYTES + WORKER_OVERHEAD_BYTES)))


# --------------------------------------------------------------------------------------
# Meters
# --------------------------------------------------------------------------------------
def probe(path: str | Path) -> tuple[int, int, float]:
    """(sample_rate, channels, duration_s) of the first audio stream, without decoding."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    d = json.loads(out)
    st = d["streams"][0]
    return int(st["sample_rate"]), int(st["channels"]), float(d["format"].get("duration", "nan"))


def check_size(
    sr: int,
    ch: int,
    duration_s: float,
    max_duration_s: float = MAX_DURATION_S,
    max_bytes: int = MAX_FILE_BYTES,
) -> None:
    """Raise SkipFile if the file is too long, or would need too much RAM, to measure."""
    if not np.isfinite(duration_s):
        raise SkipFile("unknown duration")
    if duration_s > max_duration_s:
        raise SkipFile(f"duration {duration_s / 60:.0f} min > {max_duration_s / 60:.0f} min")
    need = duration_s * sr * ch * BYTES_PER_SAMPLE
    if need > max_bytes:
        raise SkipFile(f"needs ~{need / 2**30:.1f} GB > {max_bytes / 2**30:.1f} GB budget")


def decode(path: str | Path, rate: int | None = None, guard: bool = True) -> tuple[np.ndarray, int]:
    """Decode any file to float32 (samples, channels) with ffmpeg, no clipping.

    With ``guard`` (default) it probes first and raises SkipFile rather than decode a
    file that is too long or would exceed the per-file memory budget.
    """
    sr, ch, dur = probe(path)
    sr = rate or sr
    if guard:
        check_size(sr, ch, dur)
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-ar",
            str(sr),
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    # float32 view of ffmpeg's buffer: no float64 copy (pyloudnorm upcasts internally)
    x = np.frombuffer(raw, dtype="<f4").reshape(-1, ch)
    return x, sr


def pyloudnorm_measure(x: np.ndarray, rate: int) -> dict:
    """Integrated loudness (LUFS), loudness range (LU), sample peak (dBFS) and PLR (LU)."""
    m = pyln.Meter(rate)
    lufs = float(m.integrated_loudness(x))
    lra = float(m.loudness_range(x))
    peak = float(20 * np.log10(float(np.max(np.abs(x))) + 1e-12))
    return {"lufs": lufs, "lra": lra, "peak_dbfs": peak, "plr": peak - lufs}


_FF_I = re.compile(r"I:\s+(-?[\d.]+|-inf) LUFS")
_FF_LRA = re.compile(r"LRA:\s+(-?[\d.]+) LU")


def ffmpeg_ebur128(path: str | Path) -> dict:
    """ffmpeg's EBU R128 meter: integrated loudness and LRA from the summary block."""
    err = subprocess.run(
        [
            "ffmpeg",
            "-nostats",
            "-hide_banner",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "ebur128=framelog=quiet",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    summary = err[err.rfind("Summary:") :]
    i, lra = _FF_I.search(summary), _FF_LRA.search(summary)
    return {
        "ff_lufs": float(i.group(1)) if i and i.group(1) != "-inf" else float("nan"),
        "ff_lra": float(lra.group(1)) if lra else float("nan"),
    }


def extractor_available() -> bool:
    if not EXTRACTOR.exists():
        return False
    try:
        return subprocess.run([str(EXTRACTOR)], capture_output=True, timeout=30).returncode in (
            0,
            1,
            2,
        )
    except OSError:  # Bad CPU type: Rosetta missing
        return False


def essentia_measure(path: str | Path, timeout: int = 900) -> dict:
    """Run the AcousticBrainz extractor; return the fields the dumps carry."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.json"
        r = subprocess.run(
            [str(EXTRACTOR), str(path), str(out)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"extractor failed ({r.returncode}): {r.stderr[-300:]}")
        d = json.loads(out.read_text())
    ap, ll = d["metadata"]["audio_properties"], d["lowlevel"]
    return {
        "replay_gain": float(ap["replay_gain"]),
        "dynamic_complexity": float(ll["dynamic_complexity"]),
        "average_loudness": float(ll["average_loudness"]),
        "codec": ap.get("codec"),
        "lossless": bool(ap.get("lossless")),
        "bit_rate": int(ap.get("bit_rate") or 0),
        "length_s": float(ap.get("length") or 0),
        "essentia_version": d["metadata"]["version"]["essentia_git_sha"],
    }


def measure_file(path: str | Path, with_essentia: bool = True) -> dict:
    """All three meters on one file."""
    x, sr = decode(path)
    row = {
        "path": str(path),
        "sample_rate": sr,
        "channels": x.shape[1],
        "duration_s": x.shape[0] / sr,
    }
    row |= pyloudnorm_measure(x, sr)
    row |= ffmpeg_ebur128(path)
    if with_essentia:
        row |= essentia_measure(path)
    return row


# --------------------------------------------------------------------------------------
# EBU Tech 3341 / 3342 conformance signals (stereo 1 kHz sine, levels in dBFS per channel)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Case:
    name: str
    standard: str  # "Tech 3341" (integrated) or "Tech 3342" (LRA)
    segments: tuple[tuple[float, float], ...]  # (dBFS, seconds)
    expected: float
    tol: float
    metric: str  # "lufs" or "lra"


CASES: tuple[Case, ...] = (
    Case("3341-1", "Tech 3341", ((-23, 20),), -23.0, 0.1, "lufs"),
    Case("3341-2", "Tech 3341", ((-33, 20),), -33.0, 0.1, "lufs"),
    Case("3341-3", "Tech 3341", ((-36, 10), (-23, 60), (-36, 10)), -23.0, 0.1, "lufs"),
    Case(
        "3341-4",
        "Tech 3341",
        ((-72, 10), (-36, 10), (-23, 60), (-36, 10), (-72, 10)),
        -23.0,
        0.1,
        "lufs",
    ),
    Case("3341-5", "Tech 3341", ((-26, 20), (-20, 20.1), (-26, 20)), -23.0, 0.1, "lufs"),
    Case("3342-1", "Tech 3342", ((-20, 20), (-30, 20)), 10.0, 1.0, "lra"),
    Case("3342-2", "Tech 3342", ((-20, 20), (-15, 20)), 5.0, 1.0, "lra"),
    Case("3342-3", "Tech 3342", ((-40, 20), (-20, 20)), 20.0, 1.0, "lra"),
    Case(
        "3342-4",
        "Tech 3342",
        ((-50, 20), (-35, 20), (-20, 20), (-35, 20), (-50, 20)),
        15.0,
        1.0,
        "lra",
    ),
)


def case_signal(case: Case, rate: int = RATE) -> np.ndarray:
    """Stereo 1 kHz sine; phase-continuous across level steps."""
    parts, t0 = [], 0
    for dbfs, secs in case.segments:
        n = int(round(secs * rate))
        t = (np.arange(n) + t0) / rate
        parts.append(10 ** (dbfs / 20) * np.sin(2 * np.pi * 1000 * t))
        t0 += n
    mono = np.concatenate(parts)
    return np.column_stack([mono, mono])


# --------------------------------------------------------------------------------------
# Synthetic programmes: pink noise with controlled loudness, level variation and crest
# --------------------------------------------------------------------------------------
def pink_noise(n: int, rng: np.random.Generator, channels: int = 2) -> np.ndarray:
    """1/f noise by spectral shaping, partially correlated stereo (like a real mix)."""

    def one() -> np.ndarray:
        spec = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n)
        f[0] = f[1]
        return np.fft.irfft(spec / np.sqrt(f), n)

    common = one()
    chans = [0.8 * common + 0.6 * one() for _ in range(channels)]
    x = np.column_stack(chans)
    return x / np.max(np.abs(x))


def synthetic_programme(
    target_lufs: float,
    env_sd_db: float,
    drive: float,
    seed: int,
    seconds: float = 60.0,
    rate: int = 44_100,
) -> np.ndarray:
    """Pink noise with a slow log-normal envelope (sets LRA), tanh drive (sets crest).

    The programme is scaled to ``target_lufs``; if that would exceed −0.1 dBFS it is
    soft-limited, so the loudest targets also end up with less crest, as in real masters.
    """
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    x = pink_noise(n, rng)
    # envelope: random walk in dB, smoothed over ~2 s, with the requested SD
    knots = rng.standard_normal(int(seconds / 2) + 2)
    env_db = np.interp(np.linspace(0, len(knots) - 1, n), np.arange(len(knots)), knots)
    env_db = (env_db - env_db.mean()) / (env_db.std() + 1e-12) * env_sd_db
    x = x * 10 ** (env_db / 20)[:, None]
    if drive > 0:
        x = np.tanh(drive * x / np.max(np.abs(x))) / np.tanh(drive)
    meter = pyln.Meter(rate)
    for _ in range(6):
        gain = target_lufs - meter.integrated_loudness(x)
        x = x * 10 ** (gain / 20)
        peak = np.max(np.abs(x))
        if peak <= 0.989 and abs(gain) < 0.05:
            break
        if peak > 0.989:  # soft limiter
            x = 0.989 * np.tanh(x / 0.989)
    return x


SYNTH_GRID = {
    "target_lufs": (-30.0, -24.0, -18.0, -14.0, -11.0, -8.0),
    "env_sd_db": (0.0, 2.0, 4.0, 7.0),
    "drive": (0.0, 2.0, 6.0),
}


# --------------------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------------------
def run_conformance(out_dir: Path = OUT_DIR) -> Path:
    import polars as pl

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for c in CASES:
            x = case_signal(c)
            wav = Path(td) / f"{c.name}.wav"
            sf.write(wav, x, RATE, subtype="FLOAT")
            m = pyloudnorm_measure(x, RATE) | ffmpeg_ebur128(wav)
            rows.append(
                {
                    "case": c.name,
                    "standard": c.standard,
                    "metric": c.metric,
                    "expected": c.expected,
                    "tol": c.tol,
                    "pyloudnorm": m[c.metric],
                    "ffmpeg": m[f"ff_{c.metric}"],
                }
            )
    df = pl.DataFrame(rows)
    path = out_dir / "conformance.parquet"
    df.write_parquet(path)
    print(df)
    return path


def _synth_one(args: tuple) -> dict:
    tl, sd, drive, seed = args
    x = synthetic_programme(tl, sd, drive, seed)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "s.wav"
        sf.write(wav, x, 44_100, subtype="PCM_24")
        row = measure_file(wav)
    row |= {"target_lufs": tl, "env_sd_db": sd, "drive": drive, "seed": seed, "path": None}
    return row


def run_synthetic(out_dir: Path = OUT_DIR, jobs: int = 4) -> Path:
    import itertools

    import polars as pl

    out_dir.mkdir(parents=True, exist_ok=True)
    grid = [(*g, i) for i, g in enumerate(itertools.product(*SYNTH_GRID.values()))]
    with ProcessPoolExecutor(jobs) as ex:
        rows = list(ex.map(_synth_one, grid))
    df = pl.DataFrame(rows).drop("path")
    path = out_dir / "synthetic.parquet"
    df.write_parquet(path)
    print(f"{len(df)} synthetic programmes -> {path}")
    return path


def sample_library(roots: list[Path], n: int, per_album: int, seed: int = 0) -> list[Path]:
    """Spread the sample over albums: up to ``per_album`` random tracks from each folder."""
    by_album: dict[Path, list[Path]] = {}
    for root in roots:
        for p in root.rglob("*"):
            if any(part.lower() in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
                continue  # audiobooks, podcasts etc. are not music
            if p.suffix.lower() in AUDIO_EXT and p.is_file() and not p.name.startswith("."):
                by_album.setdefault(p.parent, []).append(p)
    rng = random.Random(seed)
    picks: list[Path] = []
    for album in sorted(by_album):
        tracks = sorted(by_album[album])
        picks += rng.sample(tracks, min(per_album, len(tracks)))
    rng.shuffle(picks)
    return sorted(picks[:n])


def _library_one(path: str) -> dict:
    try:
        return measure_file(path) | {"error": None}
    except SkipFile as e:  # recorded so a resumed run does not retry it
        return {"path": path, "error": f"skipped: {e}"}
    except Exception as e:  # logged, never fatal
        return {"path": path, "error": f"{type(e).__name__}: {e}"[:400]}


def run_library(
    roots: list[Path], n: int, per_album: int, jobs: int, out_dir: Path = OUT_DIR
) -> Path:
    """Measure a sample of the user's files. Resumable: already-measured paths are skipped."""
    import polars as pl

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "library.parquet"
    done = pl.read_parquet(path) if path.exists() else None
    seen = set(done["path"]) if done is not None else set()
    cap = max_jobs_for_ram()
    if jobs > cap:
        print(f"library: --jobs {jobs} capped to {cap} to fit physical RAM", flush=True)
        jobs = cap
    todo = [str(p) for p in sample_library(roots, n, per_album) if str(p) not in seen]
    print(f"library: {len(seen)} done, {len(todo)} to measure with {jobs} workers", flush=True)
    rows, t0 = [], time.time()

    def flush() -> None:
        nonlocal done
        if rows:
            new = pl.DataFrame(rows, infer_schema_length=None)
            done = pl.concat([done, new], how="diagonal_relaxed") if done is not None else new
            done.write_parquet(path)
            rows.clear()

    with ProcessPoolExecutor(jobs) as ex:
        futs = [ex.submit(_library_one, p) for p in todo]
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if (rows[-1].get("error") or "").startswith("skipped"):
                print(f"  skip {Path(rows[-1]['path']).name}: {rows[-1]['error']}", flush=True)
            if i % 25 == 0 or i == len(futs):
                flush()
                rate = i / (time.time() - t0)
                print(
                    f"  {i}/{len(futs)}  {rate:.2f} files/s  "
                    f"ETA {(len(futs) - i) / rate / 60:.0f} min",
                    flush=True,
                )
    flush()
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("conformance")
    s = sub.add_parser("synthetic")
    s.add_argument("--jobs", type=int, default=4)
    lib = sub.add_parser("library")
    lib.add_argument("--root", action="append", required=True, type=Path)
    lib.add_argument("--n", type=int, default=1200)
    lib.add_argument("--per-album", type=int, default=4)
    lib.add_argument(
        "--jobs", type=int, default=min(max(1, (os.cpu_count() or 4) - 3), max_jobs_for_ram())
    )
    a = ap.parse_args(argv)
    if a.cmd != "conformance" and not extractor_available():
        sys.exit(f"Essentia extractor not runnable at {EXTRACTOR} (Rosetta installed?)")
    if a.cmd == "conformance":
        run_conformance()
    elif a.cmd == "synthetic":
        run_synthetic(jobs=a.jobs)
    else:
        run_library(a.root, a.n, a.per_album, a.jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
