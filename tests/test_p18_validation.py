"""P18: rip resolution helpers, DR Database parsing / matching, Bland-Altman."""

import numpy as np
import polars as pl
import pytest

from lw.ingest import drdb
from lw.measure import own_rips
from lw.models import validation


def test_barcode_normalisation():
    # UPC-A, EAN-13 and 14-digit GTIN of the same product compare equal
    assert own_rips.norm_barcode("075678611698") == own_rips.norm_barcode("0075678611698")
    assert own_rips.norm_barcode("00602435973654") == "602435973654"
    assert own_rips.norm_barcode("") is None and own_rips.norm_barcode(None) is None


def test_catalog_normalisation():
    assert own_rips.norm_catalog("B0030718-02") == own_rips.norm_catalog("b0030718 02")
    assert own_rips.norm_catalog("CDP 7 46446 2") == "CDP7464462"


def test_title_match_rules():
    assert drdb.title_match("Death Magnetic", "Death Magnetic") == "exact"
    assert drdb.title_match("Death Magnetic (limited edition)", "Death Magnetic") == "edition"
    assert drdb.title_match("Death Magnetic (Blackened Master)", "Death Magnetic") is None
    assert drdb.title_match("Death Magnetic [2014 Pono Music Digital Download]",
                            "Death Magnetic") is None  # fmt: skip
    # packaging words count as the same master; later remasters are caught by the year rule
    assert drdb.title_match("A Love Supreme - Deluxe Edition", "A Love Supreme") == "edition"
    assert drdb.title_match("Abbey Road (Remastered)", "Abbey Road") is None


ROW = """<table><tbody><tr>
<td><a href="/?artist=Metallica">Metallica</a></td>
<td><a href="/album/view/123">Death Magnetic</a></td>
<td>2008</td><td><span class="badge-dr">03</span></td><td><span>02</span></td>
<td><span>04</span></td><td>Lossless</td><td>CD</td></tr></tbody></table>"""


def test_parse_dr_row():
    (r,) = drdb.parse(ROW)
    assert r == {"dr_id": 123, "dr_artist": "Metallica", "dr_album": "Death Magnetic",
                 "dr_year": 2008, "dr": 3, "dr_min": 2, "dr_max": 4, "dr_codec": "Lossless",
                 "dr_source": "CD"}  # fmt: skip


def test_bland_altman_known_bias():
    rng = np.random.default_rng(1)
    a = rng.normal(-10, 3, 400)
    b = a + 0.5 + rng.normal(0, 1, 400)
    ba = validation.bland_altman(a, b, np.repeat(np.arange(40), 10))
    assert ba["bias"] == pytest.approx(0.5, abs=0.15)
    assert ba["sd"] == pytest.approx(1.0, abs=0.1)
    assert ba["bias_ci"][0] < 0.5 < ba["bias_ci"][1]
    assert ba["loa"][1] - ba["loa"][0] == pytest.approx(2 * 1.96 * ba["sd"])


def test_dr_bins_aggregate_only():
    a = pl.DataFrame({"est_lufs": np.linspace(-20, -6, 40), "est_lra": np.linspace(2, 12, 40),
                      "dr": np.linspace(14, 4, 40)})  # fmt: skip
    b = validation.dr_bins(a)
    assert (b["n"] >= 5).all()  # no bin small enough to reveal single albums
    assert b.filter(pl.col("x") == "est_lufs")["med"].is_sorted(descending=True)


@pytest.mark.skipif(not validation.SUMMARY.exists(), reason="run `make validate` first")
def test_pinned():
    import json

    s = json.loads(validation.SUMMARY.read_text())
    assert s["own"]["n_tracks"] == 149 and s["own"]["n_albums"] == 13
    assert s["own"]["accuraterip_accurate"] == 149
    # the P03 proxy holds on lossless CD audio it was not fitted on
    assert s["proxy_lossless"]["lufs"]["bias"] == pytest.approx(-0.04, abs=0.02)
    assert s["proxy_lossless"]["lufs"]["rmse"] == pytest.approx(1.15, abs=0.02)
    # same audio in AcousticBrainz -> same extractor output
    assert abs(s["ab_vs_own"]["same_master"]["replay_gain_same_extractor"]["bias"]) < 0.05
    assert s["ab_vs_own"]["headline_unit"]["lufs"]["n"] == 60
    assert s["encoding"]["mp3_128"]["d_lufs"]["mean"] == pytest.approx(-0.42, abs=0.02)
    assert abs(s["encoding"]["mp3_320"]["d_lufs"]["mean"]) < 0.01
    assert s["drdb"]["n_albums"] == 139
    assert s["drdb"]["est_lufs"]["spearman"]["r"] == pytest.approx(-0.90, abs=0.01)
