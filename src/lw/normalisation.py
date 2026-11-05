"""P04: the streaming loudness-normalisation timeline (data/reference/normalisation_timeline.csv).

The CSV is hand-built from cited sources. ``era_start()`` defines the "normalisation era"
shaded in later charts: the first date at which a major music service normalised by default,
with at least medium confidence in the date.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

CSV = Path(__file__).resolve().parents[2] / "data/reference/normalisation_timeline.csv"
CONFIDENCE = ["low", "medium", "high"]
MAJOR = ["Spotify", "YouTube", "Apple Music Sound Check", "Tidal", "Amazon Music"]


def _decimal_year(s: str) -> float:
    """'2015', '2015-12' or '2015-12-01' -> decimal year (month midpoint when no day)."""
    parts = [int(p) for p in s.split("-")]
    if len(parts) == 1:
        return parts[0] + 0.5
    y, m = parts[0], parts[1]
    d = parts[2] if len(parts) == 3 else 15
    return y + (date(y, m, d).timetuple().tm_yday - 1) / 365.25


def load(path: Path = CSV) -> pl.DataFrame:
    df = pl.read_csv(path, schema_overrides={"event_date": pl.Utf8, "default_on": pl.Boolean})
    return df.with_columns(
        pl.col("event_date").map_elements(_decimal_year, return_dtype=pl.Float64).alias("t"),
        pl.col("confidence")
        .replace_strict({c: i for i, c in enumerate(CONFIDENCE)}, return_dtype=pl.Int8)
        .alias("conf_rank"),
    ).sort("t")


def era_start(df: pl.DataFrame | None = None, min_conf: str = "medium") -> float:
    """First default-on date at a major service with confidence >= ``min_conf``."""
    df = load() if df is None else df
    ok = df.filter(
        pl.col("default_on")
        & pl.col("service").is_in(MAJOR)
        & (pl.col("conf_rank") >= CONFIDENCE.index(min_conf))
    )
    return float(ok["t"].min())


def era_consolidated(df: pl.DataFrame | None = None, k: int = 3) -> float:
    """Date by which ``k`` distinct major services normalise by default (medium+ confidence)."""
    df = load() if df is None else df
    ok = (
        df.filter(
            pl.col("default_on") & pl.col("service").is_in(MAJOR) & (pl.col("conf_rank") >= 1)
        )
        .group_by("service")
        .agg(pl.col("t").min())
        .sort("t")
    )
    return float(ok["t"][k - 1])
