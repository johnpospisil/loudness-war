"""P09: dedupe to (recording, release), per-submission exclusions, codec flags, pinned counts."""

import json
from pathlib import Path

import duckdb
import polars as pl
import pytest

from lw.build import dedupe as dd

CAL = {"lufs": (-23.0, -1.0), "lra": (0.0, 2.0)}  # simple numbers: LUFS = -23 - RG, LRA = 2 DC


def base(**kw):
    row = {
        "recording_mbid": "r1", "part": 0, "submission_offset": 0, "md5_encoded": "m",
        "recording_mbid_mb": "r1", "release_mbid": "rel1", "match_tier": "A", "year": 1995,
        "year_source": "release", "codec": "flac", "bit_rate": 0, "length_s": 200.0,
        "replay_gain": -10.0, "dynamic_complexity": 4.0, "tag_year_agrees": True,
        "wrong_edition_suspect": False, "essentia_version": "2.1",
        "formats": ["CD"], "secondary_types": [], "tag_album": "x", "tag_date": "1995",
    }  # fmt: skip
    for c in dd.FEATURES:
        row.setdefault(c, 1.0)
    for c in dd.RELEASE_COLS:
        row.setdefault(c, False if c.startswith(("is_", "reissue_")) else None)
    row["release_year"] = row["rg_first_year"] = 1995
    row.update(kw)
    return row


def run(rows, tmp_path):
    con = duckdb.connect()
    df = pl.DataFrame(rows, infer_schema_length=None)
    for c in df.columns:  # untyped all-null columns -> varchar
        if df[c].dtype == pl.Null:
            df = df.with_columns(pl.col(c).cast(pl.Utf8))
    con.register("src_df", df)
    con.execute("create table src as select * from src_df")
    f = dd.dedupe(con, "src", tmp_path / "t.parquet", tmp_path / "x.parquet", cal=CAL)
    t = {(r["recording_mbid"], r["release_mbid"]): r
         for r in pl.read_parquet(tmp_path / "t.parquet").to_dicts()}  # fmt: skip
    x = pl.read_parquet(tmp_path / "x.parquet")
    return f, t, x


def test_median_iqr_and_flags(tmp_path):
    rows = [
        base(submission_offset=i, md5_encoded=f"m{i}", replay_gain=rg, dynamic_complexity=dc,
             codec=c, bit_rate=b)
        for i, (rg, dc, c, b) in enumerate([(-10, 4, "flac", 0), (-9, 5, "mp3", 320000),
                                            (-8, 6, "mp3", 320000), (-4, 4, "mp3", 320000)])
    ]  # fmt: skip
    # unit 2: one lossy low-bitrate submission on another release
    rows.append(base(release_mbid="rel2", codec="mp3", bit_rate=96000, md5_encoded="z"))
    f, t, _ = run(rows, tmp_path)
    u = t[("r1", "rel1")]
    assert u["n_sub"] == 4 and u["n_lossless"] == 1 and not u["all_lossless"]
    assert u["replay_gain"] == pytest.approx(-8.5) and u["lufs_all"] == pytest.approx(-14.5)
    # lossless first: the one FLAC (RG -10, DC 4) sets lufs/lra; the MP3s give lufs_lossy
    assert u["loudness_source"] == "lossless" and u["lufs"] == pytest.approx(-13.0)
    assert u["lufs_lossy"] == pytest.approx(-15.0) and u["lra_all"] == pytest.approx(9.0)
    # RG quartiles (linear interp) -9.25 and -7.0 -> LUFS IQR 2.25 > 1.5: inconsistent
    assert u["lufs_iqr"] == pytest.approx(2.25) and u["inconsistent"]
    assert u["lufs_lossless"] == pytest.approx(-13.0) and u["lra"] == pytest.approx(8.0)
    assert u["codec"] == "mp3" and u["codecs"] == ["flac", "mp3"] and not u["low_bitrate"]
    v = t[("r1", "rel2")]
    assert v["n_sub"] == 1 and v["low_bitrate"] and not v["inconsistent"]
    assert v["lufs_lossless"] is None and v["in_main"] and v["in_core"]
    assert v["loudness_source"] == "lossy" and v["lufs"] == pytest.approx(-13.0)
    assert f["units"] == 2 and f["units_main"] == 2


def test_exclusions_and_repeats(tmp_path):
    rows = [
        base(),
        base(),  # exact repeat (same key and md5): dropped, not counted twice
        base(submission_offset=1, md5_encoded="other"),
        base(submission_offset=2, match_tier=None, release_mbid=None),  # unmatched
        base(submission_offset=3, replay_gain=float("nan")),  # no_features
        base(submission_offset=4, length_s=12.0),  # short
        base(submission_offset=5, replay_gain=-30.0),  # LUFS +7: lufs_gt_0
        base(submission_offset=6, replay_gain=40.0),  # LUFS -63
        base(submission_offset=7, dynamic_complexity=0.0),  # invalid_lra
        base(submission_offset=8, dynamic_complexity=30.0),  # LRA 60 > 50: invalid_lra
        base(submission_offset=9, replay_gain=0.0),  # wildly different, but valid: kept
    ]
    f, t, x = run(rows, tmp_path)
    assert f["submissions"] == 11 and f["after_repeats"] == 10
    assert f["excluded"] == {"unmatched": 1, "no_features": 1, "short": 1, "lufs_gt_0": 1,
                             "lufs_lt_-60": 1, "invalid_lra": 2}  # fmt: skip
    assert f["after_invalid_lra"] == 3 and len(x) == 7
    u = t[("r1", "rel1")]
    assert u["n_sub"] == 3 and u["lufs"] == pytest.approx(-13.0)  # median of -13, -13, -23
    assert sorted(x["reason"].to_list()) == sorted(dd.REASONS + ["invalid_lra"])


def test_core_and_main_sample(tmp_path):
    rows = [
        base(release_mbid="a", year=1975, md5_encoded="1"),
        base(release_mbid="b", year=2001, is_reissue=True, md5_encoded="2"),
        base(release_mbid="c", year=2001, match_tier="C", md5_encoded="3"),
        base(release_mbid="d", year=None, md5_encoded="4"),
    ]
    _, t, _ = run(rows, tmp_path)
    flags = {k[1]: (v["in_core"], v["in_main"]) for k, v in t.items()}
    assert flags == {
        "a": (False, False),
        "b": (True, False),
        "c": (True, False),
        "d": (False, False),
    }


def test_calibration_file():
    c = dd.calibration()
    assert c["lufs"][1] == pytest.approx(-1.0416, abs=1e-3)
    assert c["lra"][1] == pytest.approx(1.7753, abs=1e-3)


FUNNEL = Path(__file__).resolve().parents[1] / "data/processed/tracks_funnel.json"


@pytest.mark.skipif(not FUNNEL.exists(), reason="run `make dedupe` first")
def test_pinned_funnel():
    s = json.loads(FUNNEL.read_text())
    f = s["funnel"]
    assert f["submissions"] == 29_460_584
    assert f["after_repeats"] == 29_457_994  # 2,590 exact repeats
    # 8 of P08's 65,705 unmatched rows were exact repeats
    assert f["excluded"] == {
        "unmatched": 65_697, "no_features": 0, "short": 235_350,
        "lufs_gt_0": 4_286, "lufs_lt_-60": 126, "invalid_lra": 10_541,
    }  # fmt: skip
    assert (f["units"], f["units_core"], f["units_main"]) == (9_269_713, 8_793_287, 7_206_307)
    assert f["units_main_consistent"] == 6_640_436
    assert f["units_main_lossless"] == 2_997_536  # headline sample (P12/P13)
    m = s["summary"]
    assert m["recordings"] == 6_773_007 and m["releases"] == 1_215_764
    assert m["median_lufs_main"] == pytest.approx(-11.79, abs=0.01)
    assert m["median_lra_main"] == pytest.approx(6.71, abs=0.01)
    assert m["inconsistent_among_multi"] == pytest.approx(0.1773, abs=1e-3)
