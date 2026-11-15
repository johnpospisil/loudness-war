"""P18: measure the user's own lossless CD rips and the effect of lossy encoding.

Three steps, each resumable, writing to ``data/interim/p18/``:

* ``inventory``: read the tags of every rip under the rips folder and resolve each track to
  a MusicBrainz release and recording. Files tagged by dBpoweramp's MusicBrainz provider
  carry ``MUSICBRAINZ_ALBUMID`` / ``MUSICBRAINZ_TRACKID``. Files tagged from other sources
  carry only a UPC and catalogue number, so the release is found by barcode (catalogue
  number, then track count, break ties) and the recording by disc and track position. The
  file's ISRC is checked against MusicBrainz as an independent confirmation.
* ``measure``: pyloudnorm, ffmpeg ``ebur128`` and the AcousticBrainz-era Essentia extractor
  on every rip (:func:`lw.measure.pyloudnorm_check.measure_file`).
* ``encode``: re-encode a seeded sample of lossless tracks to MP3 and AAC at several
  bitrates with ffmpeg and measure each copy the same way, so the shift that lossy
  encoding adds to LUFS, LRA and the Essentia proxies is known.

CLI::

    python -m lw.measure.own_rips inventory --root ~/Music/Lossless
    python -m lw.measure.own_rips measure [--jobs 3]
    python -m lw.measure.own_rips encode [--per-album 2] [--jobs 3]
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import polars as pl

from lw.measure.pyloudnorm_check import (
    AUDIO_EXT,
    SkipFile,
    essentia_measure,
    max_jobs_for_ram,
    measure_file,
)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data/interim/p18"
MB = ROOT / "data/interim/mb"
MB_RAW = next(iter(sorted((ROOT / "data/raw/musicbrainz").glob("*/mbdump"))), None)
DEFAULT_ROOT = Path.home() / "Music/Lossless"
LOSSLESS_EXT = {".flac", ".wav", ".aif", ".aiff", ".m4a"}  # .m4a only if ALAC (checked)

# Lossy copies to test: (label, codec family, ffmpeg args, nominal kbps).
ENCODINGS = [
    ("mp3_128", "mp3", ["-c:a", "libmp3lame", "-b:a", "128k"], 128),
    ("mp3_192", "mp3", ["-c:a", "libmp3lame", "-b:a", "192k"], 192),
    ("mp3_320", "mp3", ["-c:a", "libmp3lame", "-b:a", "320k"], 320),
    ("mp3_v2", "mp3", ["-c:a", "libmp3lame", "-q:a", "2"], 190),
    ("aac_128", "aac", ["-c:a", "aac_at", "-b:a", "128k"], 128),
    ("aac_256", "aac", ["-c:a", "aac_at", "-b:a", "256k"], 256),
]


# --------------------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------------------
def tags(path: str | Path) -> dict:
    """Format tags (upper-cased keys), codec and duration of one file via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-of", "json", "-show_format", "-show_streams",
         "-select_streams", "a:0", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    d = json.loads(r.stdout)
    t = {k.upper(): v for k, v in (d.get("format", {}).get("tags") or {}).items()}
    s = (d.get("streams") or [{}])[0]
    t["_CODEC"] = s.get("codec_name")
    t["_DURATION"] = float(d.get("format", {}).get("duration") or "nan")
    return t


def _int(x) -> int | None:
    try:
        return int(str(x).split("/")[0])
    except (TypeError, ValueError):
        return None


def norm_barcode(x: str | None) -> str | None:
    """Barcodes compare without leading zeros (UPC-A vs EAN-13 vs 14-digit GTIN)."""
    if not x:
        return None
    d = "".join(ch for ch in str(x) if ch.isdigit()).lstrip("0")
    return d or None


def norm_catalog(x: str | None) -> str | None:
    if not x:
        return None
    return "".join(ch for ch in str(x).upper() if ch.isalnum()).lstrip("0") or None


def scan(root: Path) -> pl.DataFrame:
    """One row per audio file under ``root``; ``.tmp`` and other partial files are ignored."""
    rows = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in AUDIO_EXT or p.name.startswith("."):
            continue
        t = tags(p)
        rows.append(
            {
                "path": str(p),
                "album_dir": str(p.parent.relative_to(root)),
                "codec_file": t["_CODEC"],
                "duration_file_s": t["_DURATION"],
                "artist_tag": t.get("ALBUM_ARTIST") or t.get("ALBUMARTIST") or t.get("ARTIST"),
                "album_tag": t.get("ALBUM"),
                "title_tag": t.get("TITLE"),
                "date_tag": t.get("DATE"),
                "disc": _int(t.get("DISC") or t.get("DISCNUMBER")) or 1,
                "track": _int(t.get("TRACK") or t.get("TRACKNUMBER")),
                "isrc_tag": t.get("ISRC"),
                "barcode_tag": t.get("UPC") or t.get("BARCODE"),
                "catalog_tag": t.get("CATALOGNUMBER"),
                "tag_release_mbid": t.get("MUSICBRAINZ_ALBUMID"),
                "tag_recording_mbid": t.get("MUSICBRAINZ_TRACKID"),
                "accuraterip": t.get("ACCURATERIPRESULT"),
                "accuraterip_discid": t.get("ACCURATERIPDISCID"),
            }
        )
    df = pl.DataFrame(rows, infer_schema_length=None)
    lossless = df["codec_file"].is_in(["flac", "alac"]) | df["codec_file"].str.starts_with("pcm_")
    return df.with_columns(lossless=lossless)


def _pick_release(con, g: pl.DataFrame) -> tuple[str | None, str]:
    """Release MBID for one album folder, and how it was found."""
    rel = g["tag_release_mbid"].drop_nulls()
    if len(rel):
        return rel[0], "tag"
    bc = norm_barcode(g["barcode_tag"].drop_nulls().first())
    cat = norm_catalog(g["catalog_tag"].drop_nulls().first())
    disc_id = g["accuraterip_discid"].drop_nulls().first()
    n_disc = int(disc_id.split("-")[0]) if disc_id else None  # AccurateRip: tracks on disc
    cols = "release_mbid, catalog_number, n_tracks, n_media, country"
    src = f"read_parquet('{MB}/release.parquet')"
    if bc:
        cands = con.sql(
            f"select {cols} from {src} "
            "where ltrim(regexp_replace(barcode, '[^0-9]', '', 'g'), '0') = ?",
            params=[bc],
        ).pl()
    elif cat:  # no barcode tag: catalogue number, restricted to the tagged artist
        artist = (g["artist_tag"].drop_nulls().first() or "").lower()
        if ", the" in artist:  # "Beatles, The" -> "beatles"
            artist = artist.replace(", the", "")
        cands = con.sql(
            f"select {cols} from {src} where ltrim(regexp_replace(upper(catalog_number), "
            "'[^A-Z0-9]', '', 'g'), '0') = ? and lower(artist_credit) like ?",
            params=[cat, f"%{artist}%"],
        ).pl()
    else:
        return None, "none"
    if cands.is_empty():
        return None, "barcode_not_found" if bc else "catalog_not_found"
    cands = cands.with_columns(
        cat_ok=pl.col("catalog_number").map_elements(norm_catalog, return_dtype=pl.Utf8) == cat,
        # a multi-disc set lists all its tracks; the disc ripped is one medium
        n_ok=pl.col("n_tracks") == n_disc if n_disc else pl.lit(False),
        us=pl.col("country") == "US",
    ).sort(["cat_ok", "n_ok", "us", "release_mbid"], descending=[True, True, True, False])
    best = cands.row(0, named=True)
    how = ("barcode+catalog" if best["cat_ok"] else "barcode") if bc else "catalog"
    return best["release_mbid"], f"{how} ({len(cands)} candidates)"


def resolve(df: pl.DataFrame) -> pl.DataFrame:
    """Add release and recording MBIDs, release metadata and an ISRC cross-check."""
    import duckdb

    con = duckdb.connect()
    picks = []
    for (album_dir,), g in df.group_by(["album_dir"], maintain_order=True):
        rid, how = _pick_release(con, g)
        picks.append({"album_dir": album_dir, "release_mbid": rid, "release_source": how})
    df = df.join(pl.DataFrame(picks), on="album_dir", how="left")
    con.register("f", df.select("path", "release_mbid", "disc", "track", "tag_recording_mbid"))
    rec = con.sql(f"""
        with redir as (select old_mbid, new_mbid from read_parquet('{MB}/mbid_redirect.parquet')
                       where entity = 'recording')
        select f.path,
          coalesce(r1.new_mbid, f.tag_recording_mbid, rr.recording_mbid) as recording_mbid,
          case when f.tag_recording_mbid is not null then 'tag' else 'position' end rec_source,
          rr.recording_mbid as position_recording_mbid, rr.track_length_ms
        from f
        left join redir r1 on r1.old_mbid = f.tag_recording_mbid
        left join read_parquet('{MB}/recording_release.parquet') rr
          on rr.release_mbid = f.release_mbid and rr.medium_position = f.disc
         and rr.track_position = f.track""").pl()
    df = df.join(rec, on="path", how="left")
    meta = con.sql(f"""
        select r.release_mbid, r.name release_name, r.release_year, r.country release_country,
          r.release_group_mbid, g.name rg_name, g.first_release_year rg_first_year,
          r.catalog_number mb_catalog
        from read_parquet('{MB}/release.parquet') r
        join read_parquet('{MB}/release_group.parquet') g using (release_group_mbid)
        where r.release_mbid in (select distinct release_mbid from df)""").pl()
    df = df.join(meta, on="release_mbid", how="left")
    df = df.with_columns(isrc_ok=_isrc_check(con, df))
    return df


def _isrc_check(con, df: pl.DataFrame) -> pl.Series:
    """True if any of the file's ISRCs is attached to its recording in MusicBrainz."""
    if MB_RAW is None or not (MB_RAW / "isrc").exists():
        return pl.Series("isrc_ok", [None] * len(df), dtype=pl.Boolean)
    pairs = (
        df.select("path", "recording_mbid", "isrc_tag")
        .with_columns(isrc=pl.col("isrc_tag").str.split(";"))
        .explode("isrc")
        .with_columns(pl.col("isrc").str.strip_chars().str.to_uppercase())
    )
    con.register("p", pairs)
    ok = con.sql(f"""
        with i as (select column1::bigint recording_id, column2 isrc
                   from read_csv('{MB_RAW}/isrc', delim='\\t', header=false, quote='',
                                 escape='', nullstr='\\N', all_varchar=true)
                   where column2 in (select isrc from p))
        select p.path, bool_or(rc.recording_mbid = p.recording_mbid) ok,
               bool_or(i.isrc is not null) known
        from p left join i on i.isrc = p.isrc
        left join read_parquet('{MB}/recording.parquet') rc on rc.recording_id = i.recording_id
        group by p.path""").pl()
    flags = [o if k else None for o, k in zip(ok["ok"], ok["known"], strict=True)]
    m = dict(zip(ok["path"], flags, strict=True))
    return pl.Series("isrc_ok", [m.get(p) for p in df["path"]], dtype=pl.Boolean)


def run_inventory(root: Path, out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    df = resolve(scan(root)).with_columns(root=pl.lit(str(root)))
    path = out / "inventory.parquet"
    df.write_parquet(path)
    by = df.group_by("album_dir", maintain_order=True).agg(
        n=pl.len(),
        lossless=pl.col("lossless").all(),
        release=pl.col("release_source").first(),
        rec_ok=pl.col("recording_mbid").is_not_null().sum(),
        isrc_ok=pl.col("isrc_ok").sum(),
        isrc_known=pl.col("isrc_ok").is_not_null().sum(),
    )
    with pl.Config(tbl_rows=50, fmt_str_lengths=60, tbl_width_chars=200):
        print(by)
    return path


# --------------------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------------------
def _measure_one(path: str) -> dict:
    try:
        return measure_file(path) | {"error": None}
    except SkipFile as e:
        return {"path": path, "error": f"skipped: {e}"}
    except Exception as e:  # logged, never fatal
        return {"path": path, "error": f"{type(e).__name__}: {e}"[:400]}


def _run_pool(fn, items: list, path: Path, jobs: int, key: str) -> Path:
    """Run ``fn`` over ``items`` in a process pool, appending rows to ``path`` (resumable)."""
    done = pl.read_parquet(path) if path.exists() else None
    seen = set(done[key]) if done is not None else set()
    todo = [x for x in items if (x if isinstance(x, str) else x[key]) not in seen]
    jobs = min(jobs, max_jobs_for_ram())
    print(f"{path.name}: {len(seen)} done, {len(todo)} to run with {jobs} workers", flush=True)
    rows, t0 = [], time.time()

    def flush() -> None:
        nonlocal done
        if rows:
            new = pl.DataFrame(rows, infer_schema_length=None)
            done = pl.concat([done, new], how="diagonal_relaxed") if done is not None else new
            done.write_parquet(path)
            rows.clear()

    with ProcessPoolExecutor(jobs) as ex:
        futs = [ex.submit(fn, x) for x in todo]
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if rows[-1].get("error"):
                print(f"  error {rows[-1][key]}: {rows[-1]['error']}", flush=True)
            if i % 20 == 0 or i == len(futs):
                flush()
                rate = i / (time.time() - t0)
                print(f"  {i}/{len(futs)}  ETA {(len(futs) - i) / rate / 60:.0f} min", flush=True)
    flush()
    return path


def run_measure(jobs: int = 3, out: Path = OUT) -> Path:
    inv = pl.read_parquet(out / "inventory.parquet")
    return _run_pool(
        _measure_one, inv["path"].to_list(), out / "measurements.parquet", jobs, "path"
    )


# --------------------------------------------------------------------------------------
# Encoding test
# --------------------------------------------------------------------------------------
def encode_sample(inv: pl.DataFrame, per_album: int = 2, seed: int = 0) -> list[str]:
    """``per_album`` lossless tracks from each album folder, seeded."""
    rng = random.Random(seed)
    out = []
    for (_,), g in inv.filter("lossless").group_by(["album_dir"], maintain_order=True):
        paths = sorted(g["path"])
        out += rng.sample(paths, min(per_album, len(paths)))
    return out


def _encode_one(job: dict) -> dict:
    """Encode one source to one lossy format, measure it, and delete the copy."""
    from lw.measure.pyloudnorm_check import decode, pyloudnorm_measure

    label = job["encoding"]
    _, family, args, kbps = next(e for e in ENCODINGS if e[0] == label)
    row = {"job": job["job"], "path": job["path"], "encoding": label, "family": family,
           "kbps": kbps}  # fmt: skip
    try:
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / ("x.mp3" if family == "mp3" else "x.m4a")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", job["path"], "-map", "0:a:0", *args,
                 str(dst)],
                check=True, capture_output=True,
            )  # fmt: skip
            x, sr = decode(dst)
            row |= pyloudnorm_measure(x, sr) | essentia_measure(dst)
            row["bytes"] = dst.stat().st_size
        row["error"] = None
    except Exception as e:  # logged, never fatal
        row["error"] = f"{type(e).__name__}: {e}"[:400]
    return row


def run_encode(per_album: int = 2, jobs: int = 3, out: Path = OUT) -> Path:
    inv = pl.read_parquet(out / "inventory.parquet")
    jobs_list = [
        {"job": f"{p}|{e[0]}", "path": p, "encoding": e[0]}
        for p in encode_sample(inv, per_album)
        for e in ENCODINGS
    ]
    return _run_pool(_encode_one, jobs_list, out / "encodings.parquet", jobs, "job")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inventory")
    i.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    m = sub.add_parser("measure")
    m.add_argument("--jobs", type=int, default=3)
    e = sub.add_parser("encode")
    e.add_argument("--per-album", type=int, default=2)
    e.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
    if a.cmd == "inventory":
        run_inventory(a.root.expanduser())
    elif a.cmd == "measure":
        run_measure(a.jobs)
    else:
        run_encode(a.per_album, a.jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
