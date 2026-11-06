"""P06: stream-parse the AcousticBrainz *high-level* dump (genre / mood classifiers) to Parquet.

Each record holds 18 Gaia SVM classifiers. For each we keep the winning label and its
probability; genre ones are only a fallback for P10 (MusicBrainz tags come first) and are
flagged as such downstream. Reuses the low-level streaming machinery (Range-resume HTTP,
sha256 check, per-part done markers), so a part never touches disk as an archive.

    uv run python -m lw.build.parse_highlevel --parts 0-29 --jobs 2
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from lw.build import parse_lowlevel as ll

OUT_DIR = ll.ROOT / "data" / "interim" / "ab_highlevel"
DUMP = "acousticbrainz-highlevel-json-20220623"
BATCH_ROWS = 100_000

log = logging.getLogger("parse_highlevel")

CLASSIFIERS = [
    "danceability",
    "gender",
    "genre_dortmund",
    "genre_electronic",
    "genre_rosamerica",
    "genre_tzanetakis",
    "ismir04_rhythm",
    "mood_acoustic",
    "mood_aggressive",
    "mood_electronic",
    "mood_happy",
    "mood_party",
    "mood_relaxed",
    "mood_sad",
    "moods_mirex",
    "timbre",
    "tonal_atonal",
    "voice_instrumental",
]

SCHEMA = pa.schema(
    [
        ("recording_mbid", pa.string()),
        ("submission_offset", pa.int32()),
        ("part", pa.int16()),
        ("md5_encoded", pa.string()),
        ("hl_models_version", pa.string()),
        *[f for c in CLASSIFIERS for f in ((c, pa.string()), (f"{c}_p", pa.float32()))],
    ]
)


def extract_row(doc: dict, recording_mbid: str, offset: int, part: int) -> dict:
    """Flatten one high-level document: label + probability per classifier."""
    hl = doc.get("highlevel") or {}
    row = {
        "recording_mbid": recording_mbid,
        "submission_offset": offset,
        "part": part,
        "md5_encoded": ll._str(ll._get(doc, ("metadata", "audio_properties", "md5_encoded"))),
        "hl_models_version": None,
    }
    for c in CLASSIFIERS:
        d = hl.get(c)
        if not isinstance(d, dict):
            row[c], row[f"{c}_p"] = None, None
            continue
        row[c] = ll._str(d.get("value"))
        row[f"{c}_p"] = ll._num(d.get("probability"), pa.float32())
        if row["hl_models_version"] is None:
            row["hl_models_version"] = ll._str(ll._get(d, ("version", "models_essentia_git_sha")))
    return row


def part_url(part: int) -> str:
    return f"{ll.BASE_URL}/{DUMP}/{DUMP}-{part}.tar.zst"


def expected_sha256(part: int) -> str | None:
    sums = ll.ResumableHTTPReader(f"{ll.BASE_URL}/{DUMP}/sha256sums").read().decode()
    fname = f"{DUMP}-{part}.tar.zst"
    for line in sums.splitlines():
        h, _, f = line.partition("  ")
        if f.strip() == fname:
            return h
    return None


def parse_stream(
    fileobj, part: int, out_path: Path, errors_path: Path, limit: int | None = None
) -> dict:
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
                flush()
            if limit and stats["rows"] >= limit:
                break
        flush()
    tmp.replace(out_path)
    return stats


def process_part(
    part: int,
    out_dir: Path = OUT_DIR,
    source: str | None = None,
    limit: int | None = None,
    position: int = 0,
    verify: bool = True,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"part={part:02d}"
    done = out_dir / f"{tag}.done.json"
    if done.exists() and not limit:
        log.info("%s already done, skipping", tag)
        return json.loads(done.read_text())
    src = source or part_url(part)
    t0 = time.time()
    if src.startswith("http"):
        raw = ll.ResumableHTTPReader(src)
        total = raw.length
    else:
        raw = open(src, "rb")  # noqa: SIM115 - closed below
        total = Path(src).stat().st_size
    tty = sys.stderr.isatty()
    bar = tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        desc=f"hl {tag}",
        position=position if tty else 0,
        leave=True,
        mininterval=0.1 if tty else 60,
    )
    reader = ll.HashingReader(raw, bar)
    try:
        stats = parse_stream(
            io.BufferedReader(reader, buffer_size=1 << 20),
            part,
            out_dir / f"{tag}.parquet",
            out_dir / f"{tag}.errors.jsonl",
            limit,
        )
    finally:
        bar.close()
        raw.close()
    stats.update(
        part=part,
        source=src,
        seconds=round(time.time() - t0, 1),
        bytes=reader.nbytes,
        sha256=reader.sha256.hexdigest(),
    )
    stats["rows_per_s"] = round(stats["rows"] / max(stats["seconds"], 1e-9), 1)
    if limit:
        return stats
    if verify and src.startswith("http"):
        want = expected_sha256(part)
        stats["sha256_ok"] = want == stats["sha256"] if want else None
        if want and not stats["sha256_ok"]:
            bad = out_dir / f"{tag}.parquet"
            bad.replace(bad.with_suffix(".badsha.parquet"))
            raise OSError(f"{tag}: sha256 mismatch ({stats['sha256']} != {want})")
    done.write_text(json.dumps(stats, indent=2))
    return stats


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--parts", default="0-29")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parts = ll._parse_parts(args.parts)
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
                    "hl part %s: %s rows, %s errors, %ss", p, s["rows"], s["errors"], s["seconds"]
                )
            except Exception as e:
                failed.append(p)
                log.error("hl part %s failed: %s", p, e)
    if failed:
        raise SystemExit(f"failed parts (rerun to retry): {sorted(failed)}")


if __name__ == "__main__":
    main()
