"""P09 follow-up: re-stream the low-level dump and keep only gain-normalisation and provenance tags.

P09 found lossy files whose owners had applied MP3Gain / aacgain. The audio is unchanged, but
the level is shifted, so the estimated LUFS is wrong. The P05 parser did not keep the tags that
show this. This pass keeps them per submission (``data/interim/ab_gaintags/part=NN.parquet``,
joined on recording MBID + part + offset + audio md5):

* ``mp3gain_undo`` (gain applied, in 1.5 dB steps: ``+006,+006,N``), ``mp3gain_minmax`` and
  ``mp3gain_album_minmax`` (analysed only), ``replaygain_*``, ``r128_*`` and ``itunnorm``
  (metadata only: a player reads these, the audio is unchanged);
* provenance: ``encoder``, ``encodedby``, ``encoding``, ``encodersettings``, ``comment``,
  ``description``, ``notes``, ``source``, ``website``, ``copyright`` and ``file_name``
  (basename). These help separate CD rips from store downloads and stream rips (the 2014+
  lossy-vs-lossless gap, notes/p09_dedupe.md);
* ``gain_keys``: every tag key matching gain / norm / r128 / soundcheck / loudness / volume, so
  rarer conventions are not lost.

The P05 streaming machinery is reused: Range-resume HTTP, sha256 check, per-part done markers.
No archive touches disk.

    uv run python -m lw.build.parse_gaintags --parts 0-29 --jobs 2
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from lw.build import parse_lowlevel as ll

OUT_DIR = ll.ROOT / "data" / "interim" / "ab_gaintags"
BATCH_ROWS = 200_000
log = logging.getLogger("parse_gaintags")

GAIN_TAGS = [
    "mp3gain_undo", "mp3gain_minmax", "mp3gain_album_minmax", "replaygain_track_gain",
    "replaygain_album_gain", "replaygain_track_peak", "replaygain_reference_loudness",
    "r128_track_gain", "r128_album_gain", "itunnorm",
]  # fmt: skip
PROVENANCE_TAGS = [
    "encoder", "encodedby", "encoding", "encodersettings", "comment", "description", "notes",
    "source", "website", "copyright", "file_name",
]  # fmt: skip
GAIN_KEY_RE = re.compile(r"gain|norm|r128|soundcheck|loudness|volume", re.I)
MAX_STR = 200

SCHEMA = pa.schema(
    [
        ("recording_mbid", pa.string()),
        ("submission_offset", pa.int32()),
        ("part", pa.int16()),
        ("md5_encoded", pa.string()),
        ("codec", pa.string()),
        *[(f"tag_{t}", pa.string()) for t in GAIN_TAGS + PROVENANCE_TAGS],
        ("gain_keys", pa.list_(pa.string())),
        ("n_tags", pa.int16()),
    ]
)


def _first(v) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None:
        return None
    s = str(v).strip()
    return s[:MAX_STR] if s else None


def extract_row(doc: dict, recording_mbid: str, offset: int, part: int) -> dict:
    meta = doc.get("metadata") or {}
    ap = meta.get("audio_properties") or {}
    tags = meta.get("tags") or {}
    lower = {str(k).lower(): v for k, v in tags.items()}
    row = {
        "recording_mbid": recording_mbid,
        "submission_offset": offset,
        "part": part,
        "md5_encoded": _first(ap.get("md5_encoded")),
        "codec": _first(ap.get("codec")),
        "gain_keys": sorted(k for k in lower if GAIN_KEY_RE.search(k)) or None,
        "n_tags": min(len(lower), 32767),
    }
    for t in GAIN_TAGS + PROVENANCE_TAGS:
        row[f"tag_{t}"] = _first(lower.get(t))
    return row


def parse_stream(fileobj, part: int, out_path: Path, errors_path: Path, limit=None) -> dict:
    stats = {"rows": 0, "errors": 0}
    tmp = out_path.with_suffix(".parquet.tmp")
    batch: list[dict] = []
    with (
        pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as writer,
        open(errors_path, "w") as errf,
    ):
        for name, raw in ll.iter_documents(fileobj):
            ident = ll.parse_member_name(name)
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
                writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                batch.clear()
            if limit and stats["rows"] >= limit:
                break
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
    tmp.replace(out_path)
    return stats


def process_part(part: int | None, out_dir: Path = OUT_DIR, limit=None, position=0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = "sample" if part is None else f"part={part:02d}"
    done = out_dir / f"{tag}.done.json"
    if done.exists() and not limit:
        return json.loads(done.read_text())
    src = str(ll.SAMPLE_PATH) if part is None else ll.part_url(part)
    t0 = time.time()
    if src.startswith("http"):
        raw = ll.ResumableHTTPReader(src)
        total = raw.length
    else:
        raw = open(src, "rb")  # noqa: SIM115 - closed below
        total = Path(src).stat().st_size
    tty = sys.stderr.isatty()
    bar = tqdm(total=total, unit="B", unit_scale=True, desc=f"tags {tag}",
               position=position if tty else 0, mininterval=0.1 if tty else 60)  # fmt: skip
    reader = ll.HashingReader(raw, bar)
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
    if limit:
        return stats
    want = ll.expected_sha256(part)
    stats["sha256_ok"] = want == stats["sha256"] if want else None
    if want and not stats["sha256_ok"]:
        bad = out_dir / f"{tag}.parquet"
        bad.replace(bad.with_suffix(".badsha.parquet"))
        raise OSError(f"{tag}: sha256 mismatch")
    done.write_text(json.dumps(stats, indent=2))
    return stats


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--parts", default="0-29")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.sample:
        print(json.dumps(process_part(None, args.out, args.limit), indent=2))
        return
    parts = ll._parse_parts(args.parts)
    failed = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(process_part, p, args.out, args.limit, i % args.jobs): p
                for i, p in enumerate(parts)}  # fmt: skip
        for f in as_completed(futs):
            p = futs[f]
            try:
                s = f.result()
                log.info(
                    "part %s: %s rows, %s errors, %ss", p, s["rows"], s["errors"], s["seconds"]
                )
            except Exception as e:  # keep going; a rerun retries failed parts
                failed.append(p)
                log.error("part %s failed: %s", p, e)
    if failed:
        raise SystemExit(f"failed parts (rerun to retry): {sorted(failed)}")


if __name__ == "__main__":
    main()
