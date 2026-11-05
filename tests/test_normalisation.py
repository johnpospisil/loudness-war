"""P04: the hand-built normalisation timeline is complete, cited and gives a stable era."""

import polars as pl
import pytest

from lw import normalisation as nz

REQUIRED = [
    "service",
    "platform",
    "event_date",
    "target_LUFS",
    "method",
    "source_url",
    "source_quote",
    "confidence",
]


@pytest.fixture(scope="module")
def df():
    return nz.load()


def test_columns_and_citations(df):
    assert set(REQUIRED) <= set(df.columns)
    assert df.height == 20
    assert df["source_url"].str.starts_with("https://").all()
    assert (df["source_quote"].str.len_chars() > 10).all()
    assert set(df["confidence"]) <= set(nz.CONFIDENCE)


def test_low_confidence_is_flagged(df):
    low = df.filter(pl.col("confidence") == "low")
    assert low.height == 3
    assert low["flag"].str.starts_with("UNVERIFIED").all()


def test_services_covered(df):
    want = {"Spotify", "YouTube", "Tidal", "Amazon Music", "Deezer", "Pandora"}
    assert want <= set(df["service"])
    assert df["service"].str.starts_with("Apple").sum() == 2
    assert {"aes_td1004", "ebu_r128_2010", "itu_bs1770_4"} <= set(df["id"])


def test_era_dates(df):
    assert nz.era_start(df) == pytest.approx(2015.95, abs=0.02)  # YouTube, Dec 2015
    assert nz.era_consolidated(df) == pytest.approx(2017.90, abs=0.02)  # Tidal, Nov 2017


def test_decimal_year():
    assert nz._decimal_year("2015") == 2015.5
    assert 2015.9 < nz._decimal_year("2015-12") < 2016
