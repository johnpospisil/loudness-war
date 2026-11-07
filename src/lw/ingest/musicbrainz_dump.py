"""Fetch the MusicBrainz full export (Postgres COPY text files) and keep only the tables we need.

The export is streamed (HTTP -> sha256 -> bz2 -> tar) and only the selected `mbdump/<table>`
members are written to `data/raw/musicbrainz/<dump date>/`. These are tab-separated files with
no header, so they are read later with DuckDB using the column order from CreateTables.sql
(see `columns()`). No Postgres server is needed.

    uv run python -m lw.ingest.musicbrainz_dump            # latest export
"""

from __future__ import annotations

import argparse
import bz2
import io
import json
import re
import tarfile
import time
from pathlib import Path

import requests
from tqdm import tqdm

from lw.build.parse_lowlevel import HashingReader, ResumableHTTPReader

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "musicbrainz"
BASE = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport"
SCHEMA_URL = "https://raw.githubusercontent.com/metabrainz/musicbrainz-server/master/admin/sql/CreateTables.sql"

# Tables kept from each archive. Core: recordings -> tracks -> media -> releases -> groups,
# release dates/countries, labels, artists, types, ISRCs, and gid redirects for merged MBIDs.
TABLES = {
    "mbdump.tar.bz2": [
        "recording", "recording_gid_redirect", "track", "medium", "medium_format",
        "release", "release_gid_redirect", "release_country", "release_unknown_country",
        "release_status", "release_packaging", "release_label", "label",
        "release_group", "release_group_gid_redirect", "release_group_primary_type",
        "release_group_secondary_type", "release_group_secondary_type_join",
        "artist_credit", "artist", "area", "country_area", "iso_3166_1", "isrc", "genre",
        "tag", "release_group_tag", "recording_tag", "release_tag", "artist_tag",
        "release_group_meta", "release_meta", "recording_meta", "replication_control",
        "artist_credit_name", "l_genre_genre", "link", "link_type",  # added at P10
    ],
    "mbdump-derived.tar.bz2": [
        "tag", "release_group_tag", "recording_tag", "release_tag", "artist_tag",
        "release_group_meta", "release_meta", "recording_meta", "genre",
    ],
}  # fmt: skip
META = {"TIMESTAMP", "SCHEMA_SEQUENCE", "REPLICATION_SEQUENCE", "COPYING", "README"}


def latest_dump() -> str:
    return requests.get(f"{BASE}/LATEST", timeout=60).text.strip()


def fetch(archive: str, dump: str, out: Path, only: list[str] | None = None) -> dict:
    """Stream one archive, writing only wanted members. Skips if already done.

    ``only`` fetches just those tables (added later, e.g. P10's ``artist_credit_name``) into the
    same export directory, with their own done marker, and stops once all of them are written.
    """
    tag = f".{'+'.join(sorted(only))}" if only else ""
    done = out / f"{archive}{tag}.done.json"
    if done.exists():
        return json.loads(done.read_text())
    want = set(only or TABLES[archive])
    url = f"{BASE}/{dump}/{archive}"
    raw = ResumableHTTPReader(url)
    bar = tqdm(total=raw.length, unit="B", unit_scale=True, desc=archive)
    reader = HashingReader(raw, bar)
    kept: dict[str, int] = {}
    t0 = time.time()
    with (
        bz2.open(io.BufferedReader(reader, 1 << 20), "rb") as zf,
        tarfile.open(fileobj=zf, mode="r|") as tf,
    ):
        for m in tf:
            if not m.isfile():
                continue
            name = Path(m.name).name
            if only and want <= {Path(k).name for k in kept}:
                break  # partial read: the sha256 below cannot be checked
            if (m.name.startswith("mbdump/") and name in want) or (name in META and not only):
                dest = out / ("mbdump" if m.name.startswith("mbdump/") else "") / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fh:
                    src = tf.extractfile(m)
                    while chunk := src.read(1 << 22):
                        fh.write(chunk)
                kept[m.name] = m.size
    bar.close()
    if only:
        missing = want - {Path(k).name for k in kept}
        if missing:
            raise OSError(f"{archive}: tables not found: {sorted(missing)}")
        stats = {"archive": archive, "dump": dump, "only": sorted(only),
                 "bytes": reader.nbytes, "sha256_ok": None,
                 "seconds": round(time.time() - t0, 1), "kept": kept}  # fmt: skip
        done.write_text(json.dumps(stats, indent=2))
        return stats
    sums = requests.get(f"{BASE}/{dump}/SHA256SUMS", timeout=60).text
    expect = next((ln.split()[0] for ln in sums.splitlines() if ln.endswith(archive)), None)
    stats = {
        "archive": archive, "dump": dump, "bytes": reader.nbytes,
        "sha256": reader.sha256.hexdigest(), "sha256_ok": expect == reader.sha256.hexdigest(),
        "seconds": round(time.time() - t0, 1), "kept": kept,
    }  # fmt: skip
    if not stats["sha256_ok"]:
        raise OSError(f"{archive}: sha256 mismatch")
    done.write_text(json.dumps(stats, indent=2))
    return stats


def columns(table: str, schema_sql: str) -> list[str]:
    """Column names for `table`, in COPY order, parsed from CreateTables.sql."""
    m = re.search(rf"CREATE TABLE {re.escape(table)}\s*\((.*?)\n\);", schema_sql, re.S)
    if not m:
        raise KeyError(table)
    cols = []
    depth = 0  # multi-line CHECK constraints continue at depth > 0; only depth-0 lines are columns
    for line in m.group(1).splitlines():
        line = line.split("--")[0].strip()
        at_top = depth == 0
        depth += line.count("(") - line.count(")")
        if not at_top or not line or not re.match(r'"?[a-z_][a-z0-9_]*"?\s', line + " "):
            continue
        if line.upper().startswith(("CONSTRAINT", "CHECK", "PRIMARY KEY", "UNIQUE")):
            continue
        cols.append(line.split()[0].strip('",'))
    return cols


def schema_sql(out: Path) -> str:
    path = out / "CreateTables.sql"
    if not path.exists():
        path.write_text(requests.get(SCHEMA_URL, timeout=60).text)
    return path.read_text()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", help="export directory name (default: LATEST)")
    ap.add_argument("--only", help="comma-separated extra core tables to add to an export")
    args = ap.parse_args(argv)
    dump = args.dump or latest_dump()
    out = RAW / dump
    out.mkdir(parents=True, exist_ok=True)
    if args.only:
        s = fetch("mbdump.tar.bz2", dump, out, only=args.only.split(","))
        print(f"mbdump.tar.bz2: {sorted(s['kept'])}, {s['seconds']}s")
        return
    for archive in ("mbdump-derived.tar.bz2", "mbdump.tar.bz2"):
        s = fetch(archive, dump, out)
        print(f"{archive}: {len(s['kept'])} members, sha256_ok={s['sha256_ok']}, {s['seconds']}s")
    schema_sql(out)
    print("schema sequence:", (out / "SCHEMA_SEQUENCE").read_text().strip())


if __name__ == "__main__":
    main()


def dump_dir(dump: str | None = None) -> Path:
    """Most recent fetched export directory (or the named one)."""
    if dump:
        return RAW / dump
    dirs = sorted(p for p in RAW.iterdir() if (p / "mbdump").is_dir())
    if not dirs:
        raise FileNotFoundError("no MusicBrainz export fetched; run lw.ingest.musicbrainz_dump")
    return dirs[-1]


def connect(dump: str | None = None, con=None):
    """DuckDB connection with one view per fetched table, columns named from CreateTables.sql.

    Values are read as VARCHAR (Postgres COPY text: tab-separated, \\N = NULL); cast in queries.
    """
    import duckdb

    d = dump_dir(dump)
    sql = schema_sql(d)
    con = con or duckdb.connect()
    for f in sorted((d / "mbdump").iterdir()):
        try:
            cols = columns(f.name, sql)
        except KeyError:
            continue
        col_spec = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in cols) + "}"
        con.execute(
            f"CREATE OR REPLACE VIEW {f.name} AS SELECT * FROM read_csv('{f}', delim='\\t', "
            f"header=false, quote='', escape='', nullstr='\\N', columns={col_spec})"
        )
    return con
