# ruff: noqa: E501  (SQL)
"""P22: compact data for the "How loud is my album?" app (``app/data/``).

* ``albums.parquet``: one row per original album (MusicBrainz release group) in the headline
  sample with >= ``MIN_TRACKS`` tracks: title, artist, year, type, genre, median est. LUFS and
  est. LRA over its tracks, the track range, and its **percentile among albums from the same
  years** (release year ± ``WIN``), overall and within its genre. Normalised search keys.
* ``dist.json``: album-level histograms of median est. LUFS / est. LRA per (year, genre) and
  per year for all genres, plus the hero series (yearly median and P10/P90 of tracks).

Albums are compared with albums (album medians are less spread out than tracks).
Est. LUFS / LRA are the calibrated AcousticBrainz estimates (P03), not measurements.

    uv run python -m lw.app.build
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
RG = ROOT / "data/interim/mb/release_group.parquet"
YEARLY = ROOT / "data/processed/p12_yearly.parquet"
OUT = ROOT / "app/data"
MIN_TRACKS = 3
WIN = 2
LUFS_BINS = np.arange(-32.0, -1.5, 0.5)
LRA_BINS = np.arange(0.0, 20.5, 0.5)
GENRE_LABEL = {"classical": "Classical", "electronic": "Electronic", "folk_country": "Folk / country",
               "hip_hop": "Hip-hop", "jazz": "Jazz", "metal": "Metal", "other": "Other", "pop": "Pop",
               "punk": "Punk", "reggae": "Reggae / ska", "rnb_soul": "R&B / soul / blues", "rock": "Rock"}  # fmt: skip


def albums(con) -> pl.DataFrame:
    return con.sql(f"""
        with t as (
          select release_group_mbid, release_mbid, recording_mbid, year, lufs, greatest(lra, 0) as lra,
                 genre, n_sub
          from read_parquet('{T}') where in_headline and year between 1980 and 2022),
        -- an album = its most-submitted edition (normally the standard one): other editions repeat
        -- its tracks and deluxe ones add demos and bonus tracks
        rel as (select release_group_mbid, release_mbid,
                       row_number() over (partition by release_group_mbid
                                          order by sum(n_sub) desc, count(*) desc, min(year), release_mbid) r
                from t group by release_group_mbid, release_mbid),
        u as (select t.* from t join rel using (release_group_mbid, release_mbid) where rel.r = 1),
        gc as (select release_group_mbid, genre, count(*) n from u where genre is not null
               group by release_group_mbid, genre),
        g as (select *, row_number() over (partition by release_group_mbid order by n desc, genre) r
              from gc)
        select u.release_group_mbid as mbid, rg.name as title, rg.artist_credit as artist,
               coalesce(rg.primary_type, 'Other') as type, min(u.year)::smallint as year,
               any_value(g.genre) as genre, count(*)::smallint as n_tracks, sum(u.n_sub)::int as n_sub,
               round(median(u.lufs), 2)::float as lufs, round(median(u.lra), 2)::float as lra,
               round(min(u.lufs), 1)::float as lufs_min, round(max(u.lufs), 1)::float as lufs_max
        from u join read_parquet('{RG}') rg using (release_group_mbid)
        left join g on g.release_group_mbid = u.release_group_mbid and g.r = 1
        group by u.release_group_mbid, rg.name, rg.artist_credit, rg.primary_type
        having count(*) >= {MIN_TRACKS}
    """).pl()  # fmt: skip


def percentiles(a: pl.DataFrame, col: str, by_genre: bool) -> np.ndarray:
    """Share of albums from release year ± WIN (same genre if ``by_genre``) with a lower value."""
    out = np.full(a.height, np.nan)
    years = a["year"].to_numpy()
    vals = a[col].to_numpy()
    genres = a["genre"].fill_null("?").to_numpy()
    groups = np.unique(genres) if by_genre else [None]
    for g in groups:
        gm = genres == g if by_genre else np.ones(a.height, bool)
        for y in np.unique(years[gm]):
            ref = np.sort(vals[gm & (np.abs(years - y) <= WIN)])
            idx = np.where(gm & (years == y))[0]
            lo = np.searchsorted(ref, vals[idx], side="left")
            hi = np.searchsorted(ref, vals[idx], side="right")
            out[idx] = (lo + hi) / 2 / len(ref) * 100  # mid-rank percentile
    return out


def norm(s: pl.Expr) -> pl.Expr:
    return (s.str.normalize("NFKD").str.replace_all(r"\p{Mn}", "").str.to_lowercase()
            .str.replace_all(r"[^\p{L}\p{N}]+", " ").str.strip_chars())  # fmt: skip


def hist(v: np.ndarray, bins: np.ndarray) -> list[int]:
    return np.histogram(np.clip(v, bins[0], bins[-1] - 1e-9), bins)[0].tolist()


def build() -> dict:
    con = duckdb.connect()
    con.execute("set memory_limit='8GB'")
    a = albums(con)
    a = a.with_columns(
        pct_lufs=pl.Series(percentiles(a, "lufs", False)).round(1),
        pct_lufs_genre=pl.Series(percentiles(a, "lufs", True)).round(1),
        pct_lra=pl.Series(percentiles(a, "lra", False)).round(1),
        pct_lra_genre=pl.Series(percentiles(a, "lra", True)).round(1),
        title_key=norm(pl.col("title")), artist_key=norm(pl.col("artist")),
    ).with_columns(pl.when(pl.col("genre").is_null()).then(None).otherwise(pl.col("pct_lufs_genre")).alias("pct_lufs_genre"),
                   pl.when(pl.col("genre").is_null()).then(None).otherwise(pl.col("pct_lra_genre")).alias("pct_lra_genre"))  # fmt: skip
    a = a.sort("n_sub", descending=True)
    OUT.mkdir(parents=True, exist_ok=True)
    a.write_parquet(
        OUT / "albums.parquet", compression="zstd", compression_level=19, row_group_size=50_000
    )
    # histograms: per (year, genre) and per year (all genres), album medians
    hy: dict = {}
    for (y, g), d in a.group_by("year", "genre"):
        key = f"{y}|{g or 'none'}"
        hy[key] = {
            "lufs": hist(d["lufs"].to_numpy(), LUFS_BINS),
            "lra": hist(d["lra"].to_numpy(), LRA_BINS),
        }
    for (y,), d in a.group_by("year"):
        hy[f"{y}|all"] = {
            "lufs": hist(d["lufs"].to_numpy(), LUFS_BINS),
            "lra": hist(d["lra"].to_numpy(), LRA_BINS),
        }
    yy = pl.read_parquet(YEARLY).filter(pl.col("sample") == "headline").sort("year")
    hero = {m: yy.filter(pl.col("metric") == m).select("year", "median", "p10", "p90").to_dict(as_series=False)
            for m in ["lufs", "lra"]}  # fmt: skip
    med = (
        a.group_by("year")
        .agg(pl.col("lufs").median().alias("lufs"), pl.col("lra").median().alias("lra"))
        .sort("year")
    )
    dist = {"lufs_bins": LUFS_BINS.tolist(), "lra_bins": LRA_BINS.tolist(), "win": WIN, "hist": hy,
            "hero": hero, "album_median": med.to_dict(as_series=False), "genres": GENRE_LABEL,
            "n_albums": a.height, "min_tracks": MIN_TRACKS}  # fmt: skip
    (OUT / "dist.json").write_text(json.dumps(dist, separators=(",", ":")))
    s = {"n_albums": a.height, "albums_mb": (OUT / "albums.parquet").stat().st_size / 1e6,
         "dist_kb": (OUT / "dist.json").stat().st_size / 1e3}  # fmt: skip
    return s


def main() -> None:
    print(build())


if __name__ == "__main__":
    main()
