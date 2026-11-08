"""P16: pairing rules on a hand-built album, mixed-model recovery, pinned results."""

import json

import duckdb
import numpy as np
import polars as pl
import pytest

from lw.models import remaster_pairs as rp


def _unit(rel, rg, year, lufs, fmt, *, first=False, reissue=False, comp=False, kw=False,
          comment=None, tier="A", src="lossless", rec="r1"):  # fmt: skip
    return {"recording_mbid": rec, "release_mbid": rel, "release_group_mbid": rg, "year": year,
            "rg_first_year": 1973 if rg == "album" else year, "rec_first_year": 1973,
            "lufs": lufs, "lra": 8.0, "match_tier": tier, "genre": "rock", "n_sub": 1,
            "is_reissue": reissue, "is_compilation": comp, "first_appearance": first,
            "release_name": "Album", "release_comment": comment, "reissue_keyword": kw,
            "loudness_source": src, "formats": fmt}  # fmt: skip


@pytest.fixture
def album(tmp_path, monkeypatch):
    rows = [
        _unit("lp73", "album", 1973, -19.0, ['12" Vinyl'], first=True),  # vinyl original: excluded
        _unit("cd84", "album", 1984, -16.0, ["CD"], reissue=True),  # first CD = original master
        _unit("cd85", "album", 1985, -16.2, ["CD"], reissue=True),  # second early CD, same master
        _unit("cd11", "album", 2011, -10.0, ["CD"], reissue=True, comment="2011 remaster"),
        _unit("cd95", "album", 1995, -15.0, ["CD"], reissue=True),  # unlabelled reissue
        _unit("lp16", "album", 2016, -13.0, ['12" Vinyl'], reissue=True, kw=True),  # vinyl: out
        _unit("best", "best_of", 2000, -12.0, ["CD"], comp=True),  # later compilation
        _unit("cd11b", "album", 2011, -9.0, ["CD"], reissue=True, kw=True, tier="C"),  # tier C: out
        _unit("dm19", "album", 2019, -8.0, ["Digital Media"], reissue=True, kw=True, src="lossy"),
    ]
    p = tmp_path / "tracks.parquet"
    pl.DataFrame(rows).write_parquet(p)
    monkeypatch.setattr(rp, "T", p)
    return rp.build_pairs(duckdb.connect())


def test_original_is_first_digital_issue(album):
    assert set(album["orig_year"]) == {1984}
    assert album["orig_lufs"][0] == pytest.approx(-16.1)  # median of the 1984/85 CDs
    assert album["orig_first_cd"].all()


def test_kinds_and_exclusions(album):
    k = dict(zip(album["re_release"], album["kind"], strict=True))
    assert k == {"cd11": "remaster", "cd95": "reissue", "best": "later"}
    d = dict(zip(album["re_release"], album["d_lufs"], strict=True))
    assert d["cd11"] == pytest.approx(6.1)


def test_mixed_recovers_a_period_drop():
    rng = np.random.default_rng(0)
    rows = []
    eff = {"before 2000": 0.0, "2000–04": 2.0, "2005–09": 2.5, "2010–14": 2.5, "2015–22": 1.5}
    for a in range(600):
        per = list(eff)[a % 5]
        u = rng.normal(0, 1)
        for _ in range(2):
            rows.append({"orig_rg": f"a{a}", "re_period": per, "orig_decade": "1980s",
                         "d_lufs": eff[per] + u + rng.normal(0, 1)})  # fmt: skip
    m = rp.mixed(pl.DataFrame(rows), "d_lufs", "orig_rg")
    assert m["period_vs_2010_14"]["2015–22"]["est"] == pytest.approx(-1.0, abs=0.35)
    assert m["post2015_vs_2005_14"]["est"] == pytest.approx(-1.0, abs=0.4)  # 1.5 - mean(2.5, 2.5)


@pytest.mark.skipif(not rp.SUMMARY.exists(), reason="run `make models` first")
def test_pinned():
    s = json.loads(rp.SUMMARY.read_text())
    c = s["counts"]["remaster"]
    assert c["track_pairs"] == 16_991
    assert c["orig_albums"] == 1_567
    assert c["album_median_d_lufs"] == pytest.approx(0.8, abs=0.1)
    m = s["models"]["remaster|album|d_lufs"]["post2015_vs_2005_14"]
    assert m["est"] == pytest.approx(-0.47, abs=0.05) and m["hi"] < 0
    # no distinct 2016 step once the 2007 peak is modelled
    assert s["segmented"]["d_lufs|bend"]["p_joint"] > 0.5
