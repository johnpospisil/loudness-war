"""Stream-parse AcousticBrainz low-level dumps (tar.zst of JSON) into Parquet.

Each dump part is read once, from a local file or straight from HTTP, and never stored:
bytes -> sha256 + zstd -> tar stream -> orjson -> ~55 selected fields -> Parquet row groups.

The HTTP reader resumes with a Range request if the connection drops, so a part survives
network blips without restarting. Work is resumable per part: a finished part leaves
`part=NN.done.json` and is skipped on the next run.

    uv run python -m lw.build.parse_lowlevel --parts 0-29 --jobs 3
    uv run python -m lw.build.parse_lowlevel --sample            # 100k sample dump (tests/fixtures)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import tarfile
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
import requests
import zstandard
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "interim" / "ab_lowlevel"
BASE_URL = "https://data.metabrainz.org/pub/musicbrainz/acousticbrainz/dumps"
DUMP = "acousticbrainz-lowlevel-json-20220623"
SAMPLE_PATH = (
    ROOT
    / "data"
    / "raw"
    / "acousticbrainz"
    / "acousticbrainz-lowlevel-sample-json-20220623-0.tar.zst"
)
BATCH_ROWS = 50_000
MAX_STR = 500

log = logging.getLogger("parse_lowlevel")

# --- field selection -------------------------------------------------------------------------
# (output column, path into the JSON, arrow type). A path ending in "mean"/"median"/... reads
# one statistic of an Essentia stats dict.
_LL = ("lowlevel",)
_AP = ("metadata", "audio_properties")
_VER = ("metadata", "version")

NUMERIC_FIELDS: list[tuple[str, tuple[str, ...], pa.DataType]] = [
    # loudness / dynamics (headline metrics; see notes/p01_access_check.md)
    ("replay_gain", (*_AP, "replay_gain"), pa.float32()),
    ("dynamic_complexity", (*_LL, "dynamic_complexity"), pa.float32()),
    ("average_loudness", (*_LL, "average_loudness"), pa.float32()),
    ("spectral_rms_mean", (*_LL, "spectral_rms", "mean"), pa.float32()),
    ("spectral_rms_median", (*_LL, "spectral_rms", "median"), pa.float32()),
    ("spectral_rms_max", (*_LL, "spectral_rms", "max"), pa.float32()),
    ("spectral_rms_var", (*_LL, "spectral_rms", "var"), pa.float32()),
    ("silence_rate_20db", (*_LL, "silence_rate_20dB", "mean"), pa.float32()),
    ("silence_rate_30db", (*_LL, "silence_rate_30dB", "mean"), pa.float32()),
    ("silence_rate_60db", (*_LL, "silence_rate_60dB", "mean"), pa.float32()),
    # density / spectral balance (P17, S02)
    ("spectral_centroid", (*_LL, "spectral_centroid", "mean"), pa.float32()),
    ("spectral_flux", (*_LL, "spectral_flux", "mean"), pa.float32()),
    ("spectral_complexity", (*_LL, "spectral_complexity", "mean"), pa.float32()),
    ("spectral_energy", (*_LL, "spectral_energy", "mean"), pa.float32()),
    ("energyband_low", (*_LL, "spectral_energyband_low", "mean"), pa.float32()),
    ("energyband_mid_low", (*_LL, "spectral_energyband_middle_low", "mean"), pa.float32()),
    ("energyband_mid_high", (*_LL, "spectral_energyband_middle_high", "mean"), pa.float32()),
    ("energyband_high", (*_LL, "spectral_energyband_high", "mean"), pa.float32()),
    ("barkbands_flatness_db", (*_LL, "barkbands_flatness_db", "mean"), pa.float32()),
    ("rhythm_bpm", ("rhythm", "bpm"), pa.float32()),
    ("rhythm_onset_rate", ("rhythm", "onset_rate"), pa.float32()),
    # file / codec
    ("length_s", (*_AP, "length"), pa.float32()),
    ("bit_rate", (*_AP, "bit_rate"), pa.int32()),
    ("sample_rate", (*_AP, "sample_rate"), pa.int32()),
    ("analysis_sample_rate", (*_AP, "analysis_sample_rate"), pa.int32()),
    ("equal_loudness", (*_AP, "equal_loudness"), pa.int8()),
    ("lossless", (*_AP, "lossless"), pa.bool_()),
]

STRING_FIELDS: list[tuple[str, tuple[str, ...]]] = [
    ("codec", (*_AP, "codec")),
    ("downmix", (*_AP, "downmix")),
    ("md5_encoded", (*_AP, "md5_encoded")),
    ("essentia_version", (*_VER, "essentia")),
    ("extractor_version", (*_VER, "extractor")),
    ("essentia_git_sha", (*_VER, "essentia_git_sha")),
]

# File tags (lists of strings in the JSON; we keep the first value).
TAG_FIELDS = [
    "musicbrainz_albumid", "musicbrainz_releasegroupid", "musicbrainz_releasetrackid",
    "musicbrainz_recordingid", "musicbrainz_albumartistid", "date", "originaldate", "year",
    "album", "artist", "albumartist", "title", "tracknumber", "discnumber", "label", "barcode",
    "catalognumber", "releasetype", "releasestatus", "releasecountry", "media", "genre", "isrc",
]  # fmt: skip

SCHEMA = pa.schema(
    [
        ("recording_mbid", pa.string()),
        ("submission_offset", pa.int32()),
        ("part", pa.int16()),
        *[(name, typ) for name, _, typ in NUMERIC_FIELDS],
        *[(name, pa.string()) for name, _ in STRING_FIELDS],
        *[(f"tag_{t}", pa.string()) for t in TAG_FIELDS],
    ]
)

_MEMBER_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-(\d+)\.json$"
)


def _get(d: dict, path: tuple[str, ...]):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
        if d is None:
            return None
    return d


def _num(v, typ: pa.DataType):
    if v is None or isinstance(v, (dict, list)):
        return None
    try:
        if pa.types.is_boolean(typ):
            return bool(v)
        if pa.types.is_integer(typ):
            return int(v)
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _str(v) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None:
        return None
    s = str(v).strip()
    return s[:MAX_STR] if s else None


def parse_member_name(name: str) -> tuple[str, int] | None:
    """`.../lowlevel/0e/1/<mbid>-<n>.json` -> (mbid, n)."""
    m = _MEMBER_RE.search(name)
    return (m.group(1), int(m.group(2))) if m else None


def extract_row(doc: dict, recording_mbid: str, offset: int, part: int) -> dict:
    """Flatten one low-level JSON document into a row matching SCHEMA."""
    row = {"recording_mbid": recording_mbid, "submission_offset": offset, "part": part}
    for name, path, typ in NUMERIC_FIELDS:
        row[name] = _num(_get(doc, path), typ)
    for name, path in STRING_FIELDS:
        row[name] = _str(_get(doc, path))
    tags = _get(doc, ("metadata", "tags")) or {}
    for t in TAG_FIELDS:
        row[f"tag_{t}"] = _str(tags.get(t))
    return row


# --- byte sources ----------------------------------------------------------------------------
class HashingReader(io.RawIOBase):
    """Wrap a binary stream; hash and count every byte read."""

    def __init__(self, raw, progress: tqdm | None = None):
        self.raw, self.progress = raw, progress
        self.sha256 = hashlib.sha256()
        self.nbytes = 0

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        n = self.raw.readinto(b)
        if n:
            self.sha256.update(memoryview(b)[:n])
            self.nbytes += n
            if self.progress is not None:
                self.progress.update(n)
        return n


class ResumableHTTPReader(io.RawIOBase):
    """Sequential HTTP body reader that reconnects with a Range header after errors."""

    # 120 retries capped at 60 s rides out network outages of about 2 hours (DNS drops included).
    def __init__(self, url: str, retries: int = 120, chunk: int = 1 << 20, timeout: int = 60):
        self.url, self.retries, self.chunk, self.timeout = url, retries, chunk, timeout
        self.pos = 0
        self.length: int | None = None
        self._buf = b""
        self._it: Iterator[bytes] | None = None
        self._open_with_retry(None)

    def readable(self) -> bool:
        return True

    def _open(self) -> None:
        headers = {"Range": f"bytes={self.pos}-"} if self.pos else {}
        r = requests.get(self.url, headers=headers, stream=True, timeout=self.timeout)
        r.raise_for_status()
        if self.pos and r.status_code != 206:
            raise OSError(f"server ignored Range request for {self.url}")
        if self.length is None:
            self.length = int(r.headers.get("Content-Length", 0)) or None
        self._it = r.iter_content(chunk_size=self.chunk)

    def _open_with_retry(self, exc: Exception | None, attempt: int = 0) -> None:
        """(Re)connect, retrying with backoff; a failed reconnect counts as another attempt."""
        while True:
            if exc is not None:
                attempt += 1
                if attempt > self.retries:
                    raise OSError(f"giving up on {self.url} at byte {self.pos}") from exc
                wait = min(60, 2**attempt)
                log.warning(
                    "HTTP error at byte %s (%s); retry %s in %ss", self.pos, exc, attempt, wait
                )
                time.sleep(wait)
            try:
                self._open()
                return
            except (requests.RequestException, OSError) as e:
                exc = e

    def readinto(self, b) -> int:
        while not self._buf:
            try:
                self._buf = next(self._it)
            except StopIteration:
                if self.length is not None and self.pos < self.length:
                    self._buf = b""  # premature EOF: treat as a dropped connection
                    exc: Exception = OSError("premature end of HTTP body")
                else:
                    return 0
            except (requests.RequestException, OSError) as e:
                exc = e
            else:
                break
            self._open_with_retry(exc)
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        self.pos += n
        return n


def part_url(part: int) -> str:
    return f"{BASE_URL}/{DUMP}/{DUMP}-{part}.tar.zst"


def expected_sha256(part: int | None) -> str | None:
    """Look up the published sha256 for a part (or the sample)."""
    if part is None:
        sums = (SAMPLE_PATH.parent / "sample.sha256sums").read_text()
        fname = SAMPLE_PATH.name
    else:
        sums = ResumableHTTPReader(f"{BASE_URL}/{DUMP}/sha256sums").read().decode()
        fname = f"{DUMP}-{part}.tar.zst"
    for line in sums.splitlines():
        h, _, f = line.partition("  ")
        if f.strip() == fname:
            return h
    return None


# --- core ------------------------------------------------------------------------------------
def iter_documents(fileobj) -> Iterator[tuple[str, bytes]]:
    """Yield (member name, raw JSON bytes) from a zstd-compressed tar stream."""
    dctx = zstandard.ZstdDecompressor(max_window_size=2**31)
    with dctx.stream_reader(fileobj, read_size=1 << 20) as zr:
        with tarfile.open(fileobj=zr, mode="r|") as tf:
            for m in tf:
                if m.isfile():
                    yield m.name, tf.extractfile(m).read()


def parse_stream(
    fileobj, part: int, out_path: Path, errors_path: Path, limit: int | None = None
) -> dict:
    """Parse a dump stream into one Parquet file. Returns counters."""
    stats = {"rows": 0, "errors": 0}
    tmp = out_path.with_suffix(".parquet.tmp")
    batch: list[dict] = []
    with (
        pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as writer,
        open(errors_path, "w") as errf,
    ):

        def flush():
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                batch.clear()

        for name, raw in iter_documents(fileobj):
            ident = parse_member_name(name)
            try:
                if ident is None:
                    raise ValueError("unrecognised member name")
                doc = orjson.loads(raw)
                if not isinstance(doc, dict):
                    raise ValueError("document is not an object")
                batch.append(extract_row(doc, ident[0], ident[1], part))
                stats["rows"] += 1
            except (orjson.JSONDecodeError, ValueError) as e:
                stats["errors"] += 1
                errf.write(json.dumps({"member": name, "bytes": len(raw), "error": str(e)}) + "\n")
            if len(batch) >= BATCH_ROWS:
                flush()
            if limit and stats["rows"] >= limit:
                break
        flush()
    tmp.replace(out_path)
    return stats


def process_part(
    part: int | None, out_dir: Path = OUT_DIR, source: str | None = None,
    limit: int | None = None, position: int = 0, verify: bool = True,
) -> dict:  # fmt: skip
    """Parse one dump part (None = local sample) end to end. Skips finished parts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = "sample" if part is None else f"part={part:02d}"
    done = out_dir / f"{tag}.done.json"
    if done.exists() and not limit:
        log.info("%s already done, skipping", tag)
        return json.loads(done.read_text())

    src = source or (str(SAMPLE_PATH) if part is None else part_url(part))
    t0 = time.time()
    if src.startswith("http"):
        raw = ResumableHTTPReader(src)
        total = raw.length
    else:
        raw = open(src, "rb")  # noqa: SIM115 - closed below
        total = Path(src).stat().st_size
    tty = sys.stderr.isatty()  # in a log file, update the bar once a minute instead of 10x/s
    bar = tqdm(total=total, unit="B", unit_scale=True, desc=tag, position=position if tty else 0,
               leave=True, mininterval=0.1 if tty else 60)  # fmt: skip
    reader = HashingReader(raw, bar)
    try:
        stats = parse_stream(
            io.BufferedReader(reader, buffer_size=1 << 20), -1 if part is None else part,
            out_dir / f"{tag}.parquet", out_dir / f"{tag}.errors.jsonl", limit,
        )  # fmt: skip
    finally:
        bar.close()
        raw.close()

    stats.update(part=part, source=src, seconds=round(time.time() - t0, 1),
                 bytes=reader.nbytes, sha256=reader.sha256.hexdigest())  # fmt: skip
    stats["rows_per_s"] = round(stats["rows"] / max(stats["seconds"], 1e-9), 1)
    if limit:  # partial run: no checksum, no done marker
        return stats
    if verify:
        want = expected_sha256(part)
        stats["sha256_ok"] = want == stats["sha256"] if want else None
        if want and not stats["sha256_ok"]:
            bad = out_dir / f"{tag}.parquet"
            bad.replace(bad.with_suffix(".badsha.parquet"))
            raise OSError(f"{tag}: sha256 mismatch ({stats['sha256']} != {want})")
    done.write_text(json.dumps(stats, indent=2))
    return stats


def _parse_parts(spec: str) -> list[int]:
    parts: list[int] = []
    for chunk in spec.split(","):
        a, _, b = chunk.partition("-")
        parts.extend(range(int(a), int(b or a) + 1))
    return parts


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--parts", default="0-29", help="e.g. 0-29 or 0,5,7-9")
    ap.add_argument("--sample", action="store_true", help="parse the local 100k sample dump")
    ap.add_argument("--jobs", type=int, default=3, help="parts processed in parallel")
    ap.add_argument("--limit", type=int, help="stop each part after N rows (testing)")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.sample:
        print(json.dumps(process_part(None, args.out, limit=args.limit), indent=2))
        return
    parts = _parse_parts(args.parts)
    failed = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {
            ex.submit(process_part, p, args.out, None, args.limit, i % args.jobs): p
            for i, p in enumerate(parts)
        }
        for f in as_completed(futs):
            p = futs[f]
            try:
                s = f.result()
                log.info(
                    "part %s: %s rows, %s errors, %ss", p, s["rows"], s["errors"], s["seconds"]
                )
            except Exception as e:  # keep going; rerun picks up failed parts
                failed.append(p)
                log.error("part %s failed: %s", p, e)
    if failed:
        raise SystemExit(f"failed parts (rerun to retry): {sorted(failed)}")


if __name__ == "__main__":
    main()
