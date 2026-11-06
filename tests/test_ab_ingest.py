"""P06: pin the full AcousticBrainz low-level ingest (skips if the data is not present)."""

import json
from pathlib import Path

import pytest

SUMMARY = Path(__file__).resolve().parents[1] / "data/interim/ab_ingest_summary.json"
pytestmark = pytest.mark.skipif(not SUMMARY.exists(), reason="run `make ab-report` first")


@pytest.fixture(scope="module")
def ll():
    return json.loads(SUMMARY.read_text())["lowlevel"]


def test_lowlevel_totals(ll):
    assert ll["parts_done"] == 30 and ll["sha256_ok"] == 30
    assert ll["rows"] == 29_460_584
    assert ll["distinct_recordings"] == 7_564_215
    assert ll["parse_errors"] == 30  # the COPYING member of each part


def test_core_metrics_never_null(ll):
    for f in [
        "replay_gain",
        "dynamic_complexity",
        "average_loudness",
        "codec",
        "length_s",
        "tag_musicbrainz_recordingid",
    ]:
        assert ll["null_rate"][f] == 0


def test_tag_coverage(ll):
    assert ll["null_rate"]["tag_musicbrainz_albumid"] == pytest.approx(0.2453, abs=1e-3)
    assert ll["null_rate"]["tag_date"] == pytest.approx(0.0334, abs=1e-3)
    assert ll["lossless_share"] == pytest.approx(0.3733, abs=1e-3)


@pytest.fixture(scope="module")
def hl():
    s = json.loads(SUMMARY.read_text())
    if "highlevel" not in s:
        pytest.skip("high-level not ingested")
    return s["highlevel"]


def test_highlevel_totals(hl, ll):
    assert hl["parts_done"] == 30 and hl["sha256_ok"] == 30
    assert hl["rows"] == ll["rows"] == 29_460_584  # one high-level doc per low-level doc
    assert hl["parse_errors"] == 30
    # 3,640 keys repeat within a part (7,395 rows) in both dumps, so the join fans out a little
    assert hl["joined_to_lowlevel"] == 29_468_364
    assert hl["md5_agreement_on_join"] > 0.9999


def test_highlevel_empty_records(hl):
    # 145,386 docs (0.49%) carry no classifier output at all; every classifier nulls together
    rates = {
        v
        for k, v in hl["null_rate"].items()
        if k not in ("recording_mbid", "submission_offset", "part")
    }
    assert len({round(r, 6) for r in rates}) == 1
    assert hl["null_rate"]["genre_rosamerica"] == pytest.approx(145_386 / 29_460_584, rel=1e-6)
