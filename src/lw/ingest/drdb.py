"""P18: fetch album-level DR values from the Dynamic Range Database for an internal check.

The Dynamic Range Database (https://dr.loudness-war.info) lists user-submitted DR meter
results (the TT/foobar "DR" crest-factor measure) per album edition. It states no licence,
so this project **publishes only aggregate statistics with a citation, never per-album DR
values** (user decision 2026-11-07). Raw pages and per-album matches stay in git-ignored
``data/raw/drdb/`` and ``data/interim/p18/``.

Politeness: the site has no robots.txt (HTTP 404 on 2026-11-14, so no stated crawl rules);
we send one artist+album search per target album, sequentially, ``DELAY_S`` apart, with a
generic research User-Agent, and cache every page so a re-run sends nothing.

Targets (``targets()``): the best-covered original albums per release year (most
``in_headline`` units), plus the P11 spot-check albums and the user's own rips.

CLI::

    python -m lw.ingest.drdb targets [--per-year 6]
    python -m lw.ingest.drdb fetch
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlencode

import polars as pl
import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/drdb"
OUT = ROOT / "data/interim/p18"
T = ROOT / "data/processed/tracks.parquet"
RG = ROOT / "data/interim/mb/release_group.parquet"
SPOT = ROOT / "data/processed/p11_spotcheck.csv"
BASE = "https://dr.loudness-war.info/"
DELAY_S = 3.0
UA = "Mozilla/5.0 (compatible; loudness-research-script/0.1; one request per album, cached)"
MIN_UNITS = 6  # an album needs >= 6 headline tracks to be a target


def targets(per_year: int = 6, years: tuple[int, int] = (1980, 2022)) -> pl.DataFrame:
    """Albums to look up: top ``per_year`` per release year + spot-check + own rips."""
    import duckdb

    c = duckdb.connect()
    top = c.sql(f"""
        with a as (
          select t.release_group_mbid,
                 any_value(t.year) filter (where t.year = g.first_release_year) as y,
                 count(*) n_units, sum(n_sub) n_sub
          from read_parquet('{T}') t join read_parquet('{RG}') g using (release_group_mbid)
          where t.in_headline and g.primary_type = 'Album' and not g.is_compilation
            and not g.is_live and not g.is_soundtrack and t.year = g.first_release_year
          group by 1 having count(*) >= {MIN_UNITS})
        select release_group_mbid, 'top_per_year' as why from a
        where y between {years[0]} and {years[1]}
        qualify row_number() over (partition by y order by n_units desc, n_sub desc,
                                   release_group_mbid) <= {per_year}""").pl()
    extra = []
    if SPOT.exists():
        s = pl.read_csv(SPOT).filter(pl.col("release_group_mbid").is_not_null())
        extra.append(s.select("release_group_mbid", why=pl.lit("spotcheck")))
    inv = OUT / "inventory.parquet"
    if inv.exists():
        own = pl.read_parquet(inv).select("release_group_mbid").unique().drop_nulls()
        extra.append(own.with_columns(why=pl.lit("own_rip")))
    allt = (
        pl.concat([top, *extra])
        .group_by("release_group_mbid")
        .agg(why=pl.col("why").unique().sort().str.join("+"))
    )
    c.register("allt", allt)
    return c.sql(f"""select allt.*, g.name album, g.artist_credit artist,
            g.first_release_year as "year"
        from allt join read_parquet('{RG}') g using (release_group_mbid)
        order by year, artist, album""").pl()


def _url(artist: str, album: str) -> str:
    return BASE + "?" + urlencode({"artist": artist, "album": album})


def _cache(url: str) -> Path:
    return RAW / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")


def fetch(tg: pl.DataFrame, delay: float = DELAY_S) -> int:
    """Fetch every target's search page that is not cached yet. Returns pages fetched."""
    RAW.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    n = 0
    for i, r in enumerate(tg.iter_rows(named=True), 1):
        url = _url(r["artist"], r["album"])
        path = _cache(url)
        if path.exists():
            continue
        resp = s.get(url, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            print(f"  HTTP {resp.status_code}: stopping; re-run later to resume", flush=True)
            break
        path.write_text(resp.text if resp.ok else "")
        n += 1
        if n % 25 == 0:
            print(f"  {i}/{len(tg)} fetched {n}", flush=True)
        time.sleep(delay)
    return n


_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_VIEW = re.compile(r'/album/view/(\d+)"')


def parse(text: str) -> list[dict]:
    """Rows of a DR search results table: artist, album, year, dr, dr_min, dr_max, codec, source."""
    i = text.find("<tbody")
    out = []
    for row in _ROW.findall(text[i:] if i >= 0 else ""):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in _TD.findall(row)]
        if len(cells) != 8:
            continue
        v = _VIEW.search(row)

        def num(x: str) -> int | None:
            return int(x) if x.isdigit() else None

        out.append({
            "dr_id": int(v.group(1)) if v else None, "dr_artist": cells[0], "dr_album": cells[1],
            "dr_year": num(cells[2]), "dr": num(cells[3]), "dr_min": num(cells[4]),
            "dr_max": num(cells[5]), "dr_codec": cells[6], "dr_source": cells[7],
        })  # fmt: skip
    return out


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("’", "'")).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", s.decode().lower()).strip()


# Bracketed suffixes that name the same master (packaging / bonus tracks), not a remaster.
SAME_MASTER = {
    "limited", "edition", "deluxe", "special", "bonus", "tracks", "track", "version", "us",
    "uk", "eu", "japan", "japanese", "european", "german", "cd", "digipak", "digipack",
    "explicit", "clean", "enhanced", "import", "promo", "original", "first", "pressing",
}  # fmt: skip


def title_match(dr_album: str, album: str) -> str | None:
    """'exact', 'edition' (same master, packaging suffix) or None."""
    a, b = norm(dr_album), norm(album)
    if a == b:
        return "exact"
    if a.startswith(b + " "):
        rest = set(a[len(b) :].split())
        if rest <= SAME_MASTER:
            return "edition"
    return None


def match(tg: pl.DataFrame) -> pl.DataFrame:
    """Per target: DR rows from cached pages that are the original CD master (aggregated)."""
    rows = []
    for r in tg.iter_rows(named=True):
        p = _cache(_url(r["artist"], r["album"]))
        if not p.exists():
            continue
        for d in parse(p.read_text()):
            tm = title_match(d["dr_album"], r["album"])
            keep = (
                tm is not None
                and d["dr"] is not None
                and d["dr_codec"] == "Lossless"
                and d["dr_source"] == "CD"
                and d["dr_year"] is not None
                and abs(d["dr_year"] - r["year"]) <= 1
            )
            rows.append(r | d | {"title_match": tm, "keep": keep})
    df = pl.DataFrame(rows, infer_schema_length=None)
    return df


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("targets")
    t.add_argument("--per-year", type=int, default=6)
    sub.add_parser("fetch")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "targets":
        tg = targets(a.per_year)
        tg.write_parquet(OUT / "drdb_targets.parquet")
        print(tg.group_by("why").len().sort("why"), f"\n{len(tg)} targets")
    else:
        tg = pl.read_parquet(OUT / "drdb_targets.parquet")
        n = fetch(tg)
        m = match(tg)
        m.write_parquet(OUT / "drdb_rows.parquet")
        kept = m.filter("keep")["release_group_mbid"].n_unique() if len(m) else 0
        print(f"fetched {n} pages; {len(m)} DR rows; {kept}/{len(tg)} albums with a CD match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
