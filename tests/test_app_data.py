"""P22: the app's album table is consistent with the headline sample."""

import json

import polars as pl
import pytest

from lw.app import build

pytestmark = pytest.mark.skipif(not (build.OUT / "albums.parquet").exists(),
                                reason="run `make app` first")  # fmt: skip


def test_albums_table():
    a = pl.read_parquet(build.OUT / "albums.parquet")
    assert a["mbid"].is_unique().all()
    assert a["n_tracks"].min() >= build.MIN_TRACKS
    assert a["year"].is_between(1980, 2022).all()
    assert a.select(pl.col("pct_lufs").is_between(0, 100).all()).item()
    # the standard edition defines the album: track counts match the familiar releases
    dm = a.filter((pl.col("title_key") == "death magnetic") & (pl.col("artist_key") == "metallica"))
    assert dm["n_tracks"][0] == 10 and dm["pct_lufs"][0] > 99


def test_dist_histograms_cover_albums():
    d = json.loads((build.OUT / "dist.json").read_text())
    total = sum(sum(v["lufs"]) for k, v in d["hist"].items() if k.endswith("|all"))
    assert total == d["n_albums"]
