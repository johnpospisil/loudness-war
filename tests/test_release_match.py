"""P08: hand-verified release-matching cases against the real MusicBrainz tables.

Cases marked (rip) are from the user's own AccurateRip-verified CD rips, tagged with Picard,
so the edition is known for certain. Expectations come from the edition, not from the matcher.
Skips when data/interim/mb/ has not been built (`make ingest-mb`).
"""

from pathlib import Path

import duckdb
import pytest

from lw.build import release_match as rm

MB = Path(__file__).resolve().parents[1] / "data/interim/mb"
pytestmark = pytest.mark.skipif(not (MB / "release.parquet").exists(), reason="no MB tables")

# name: (recording MBID, release-MBID tag, date tag, album tag, length s)
CASES = {
    # (rip) 1992 CD of a 1969 album: a reissue by date
    "abbey_road_1992_cd": ("485bbe7f-d0f7-4ffe-8adb-0f1093dd2dbf",
                           "e50d234a-3737-4f57-a363-0ce3b083d80f", "1992", "Abbey Road", 260.6),
    # the 2009 stereo remaster of the same recording: reissue by date and keyword
    "abbey_road_2009_remaster": ("485bbe7f-d0f7-4ffe-8adb-0f1093dd2dbf",
                                 "c93e1d4c-89fa-3139-9c65-8542a39f07d1", "2009-09-09",
                                 "Abbey Road", 259.9),
    # (rip) 1991 CD of a 1959 jazz album
    "cannonball_coltrane_1991": ("b680a8f5-a8d1-44e0-b2b7-fa7f63431d7b",
                                 "28858094-3ec6-3156-abbb-da11691ee6f0", "1991-08-20",
                                 "Cannonball & Coltrane", 281.5),
    # (rip) 2001 edition of a 1965 album
    "love_supreme_2001": ("0827b81a-c1df-4601-9b63-226fd3d70feb",
                          "a1229823-aa96-33bb-a7fb-64f56b32cfb5", "2001-09", "A Love Supreme",
                          467.5),
    # (rip) US release (1997) of a 1996 UK album: same master, NOT a reissue (+1 year rule)
    "becoming_x_us_1997": ("4f63ca52-1d4c-4c27-ac65-e30584b337ac",
                           "0e60ad28-3654-464b-befc-96eb7ee0ff88", "1997-02-25", "Becoming X",
                           278.1),
    # (rip) UK remix album: remix flag, not a reissue
    "further_down_the_spiral_uk": ("7ad693df-b012-427c-8d2b-3d85f493a9db",
                                   "738ec18c-820f-3faa-af24-b65de42de7bf", "1995",
                                   "Further Down the Spiral", 243.4),
    # (rip) Odelay without its release tag: tier B on year + title, exact tag date preferred
    "odelay_tier_b": ("b218b076-2ac7-476f-a749-ff0a774f10b1", None, "1996-06-18", "Odelay",
                      194.1),
    # Odelay track carrying a wrong release tag (Abbey Road): not tier A, falls back to B
    "odelay_wrong_release_tag": ("b218b076-2ac7-476f-a749-ff0a774f10b1",
                                 "e50d234a-3737-4f57-a363-0ce3b083d80f", "1996-06-18", "Odelay",
                                 194.1),
    # (rip) Psalm 69: the tagged release has no date in MB, so the year comes from the tag
    "psalm_69_undated_release": ("ea62ee85-fcef-4030-89b2-07c54eb18c9a",
                                 "f03129ed-529b-4408-8da1-136b23648244", "1992", "Psalm 69",
                                 331.0),
    # same recording with no tags at all: tier C must not pick the bootleg
    "psalm_69_no_tags": ("ea62ee85-fcef-4030-89b2-07c54eb18c9a", None, None, None, 331.0),
    # Nevermind 30th Anniversary Super Deluxe, dated 1991 in MB: only the keyword catches it
    "nevermind_30th_dated_1991": ("5fb524f1-8cc8-4c04-a921-e34c0a911ea7",
                                  "a29d92bd-5691-4515-a0e2-9476d86cad40", "1991-09-24",
                                  "Nevermind (30th Anniversary Super Deluxe)", 301.0),
    # Nevermind 30th anniversary digital (2021): date, keyword and format all fire
    "nevermind_2021_digital": ("5fb524f1-8cc8-4c04-a921-e34c0a911ea7",
                               "50bb97bf-8bb1-4574-8c70-76c86d1daf5b", "2021-11-12", "Nevermind",
                               301.0),
    # Death Magnetic "limited edition" (2008): an original; "edition" alone is not a reissue
    "death_magnetic_limited": ("6d6efe2b-2905-4061-8fc7-94a8161e5e37",
                               "c52a1f97-de6f-44c0-ae07-98700f0333eb", "2008", "Death Magnetic",
                               428.3),
    # The Beatles "1" (2000): compilation
    "beatles_1_compilation": ("1f518811-7cf9-4bdc-a656-0958e130f312",
                              "4a1ccbbd-364f-4a53-b60d-3e81ae04befe", "2000", "1", 180.0),
    # deluxe edition released with the album (2013): is_deluxe, but not a reissue
    "the_1975_deluxe_2013": ("4b294041-efee-4e94-827c-6172ff2c59d4",
                             "ac2b87af-2774-4575-a72a-db31c8865264", "2013-08-30", "The 1975",
                             207.0),
    # "Legacy" in a title is not the Legacy Edition reissue series
    "tron_legacy_title": ("3bab4565-1d34-4848-a648-df20b649aebb",
                          "d07a00a3-0582-4f32-abd0-0cd8349c3e95", "2010-12-06", "TRON: Legacy",
                          658.0),
    # a recording MBID that does not exist: unmatched
    "unknown_recording": ("00000000-0000-4000-8000-000000000000", None, "2010", "Nothing", 200.0),
}  # fmt: skip


def run() -> dict[str, dict]:
    con = duckdb.connect()
    rm.register_mb(con, MB)
    vals = []
    for i, (rec, rel, date, alb, length) in enumerate(CASES.values()):
        lit = lambda v: "null" if v is None else "'" + str(v).replace("'", "''") + "'"  # noqa: E731
        vals.append(f"({lit(rec)}, {i}, 0, {lit(rel)}, {lit(date)}, null, {lit(alb)}, {length})")
    con.execute(
        "create view subs as select * from (values " + ", ".join(vals) + ") t(recording_mbid, "
        "submission_offset, part, tag_musicbrainz_albumid, tag_date, tag_year, tag_album, "
        "length_s)"
    )
    out = Path("/tmp") / f"p08_cases_{id(con)}.parquet"
    rm.match(con, "subs", out)
    rel = con.execute("select * from matched order by submission_offset")
    cols = [d[0] for d in rel.description]
    rows = [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
    out.unlink()
    return dict(zip(CASES, rows, strict=True))


@pytest.fixture(scope="module")
def r():
    return run()


def test_reissues_by_date(r):
    for name, (year, first) in {
        "abbey_road_1992_cd": (1992, 1969),
        "cannonball_coltrane_1991": (1991, 1959),
        "love_supreme_2001": (2001, 1965),
    }.items():
        x = r[name]
        assert (x["match_tier"], x["year"], x["rg_first_year"]) == ("A", year, first), name
        assert x["reissue_date"] and x["is_reissue"] and not x["is_compilation"], name
        assert abs(x["len_diff_s"]) < 1 and not x["wrong_edition_suspect"], name


def test_remaster_flags(r):
    x = r["abbey_road_2009_remaster"]
    assert x["match_tier"] == "A" and x["year"] == 2009
    assert x["reissue_date"] and x["reissue_keyword"] and x["is_reissue"]
    y = r["nevermind_2021_digital"]
    assert y["reissue_date"] and y["reissue_keyword"] and y["reissue_format"]


def test_reissue_dated_like_the_original(r):
    x = r["nevermind_30th_dated_1991"]
    assert x["match_tier"] == "A" and x["year"] == 1991 and x["rg_first_year"] == 1991
    assert not x["reissue_date"] and x["reissue_keyword"] and x["is_reissue"]


def test_not_reissues(r):
    b = r["becoming_x_us_1997"]
    assert (b["match_tier"], b["year"], b["rg_first_year"]) == ("A", 1997, 1996)
    assert not b["is_reissue"]
    s = r["further_down_the_spiral_uk"]
    assert s["match_tier"] == "A" and s["is_remix"] and not s["is_reissue"]
    d = r["death_magnetic_limited"]
    assert d["match_tier"] == "A" and d["year"] == 2008 and not d["is_reissue"]


def test_tier_b(r):
    for name in ["odelay_tier_b", "odelay_wrong_release_tag"]:
        x = r[name]
        assert x["match_tier"] == "B", name
        assert (x["release_name"], x["release_date"]) == ("Odelay", "1996-06-18"), name
        assert not x["is_reissue"], name
    assert r["odelay_wrong_release_tag"]["has_release_tag"]


def test_undated_release_and_tier_c(r):
    a = r["psalm_69_undated_release"]
    assert a["match_tier"] == "A" and a["release_year"] is None
    assert (a["year"], a["year_source"]) == (1992, "tag")
    c = r["psalm_69_no_tags"]
    assert c["match_tier"] == "C" and c["release_status"] != "Bootleg"
    assert c["release_mbid"] == "f03129ed-529b-4408-8da1-136b23648244"


def test_compilation_and_unmatched(r):
    x = r["beatles_1_compilation"]
    assert x["match_tier"] == "A" and x["is_compilation"] and x["year"] == 2000
    u = r["unknown_recording"]
    assert u["match_tier"] is None and u["rec_resolve"] == "missing" and u["release_mbid"] is None
    assert u["year"] is None  # no year for unmatched rows, even with a date tag


def test_deluxe_is_not_a_reissue(r):
    x = r["the_1975_deluxe_2013"]
    assert x["match_tier"] == "A" and x["year"] == 2013 and x["rg_first_year"] == 2013
    assert x["is_deluxe"] and not x["reissue_keyword"] and not x["is_reissue"]
    t = r["tron_legacy_title"]
    assert t["match_tier"] == "A" and not t["reissue_keyword"] and not t["is_deluxe"]


SUMMARY = MB.parent / "ab_matched_summary.json"


@pytest.mark.skipif(not SUMMARY.exists(), reason="run `make match` first")
def test_pinned_full_match():
    import json

    s = json.loads(SUMMARY.read_text())
    assert s["submissions"] == 29_460_584
    assert s["tiers"] == {"A": 21_498_798, "B": 3_784_549, "C": 4_111_532, "unmatched": 65_705}
    assert s["recording_resolve"]["redirect"] == 3_301_469
    f = s["flags_among_matched"]
    assert f["is_reissue"] == pytest.approx(0.1122, abs=1e-3)
    assert f["reissue_date"] == pytest.approx(0.1022, abs=1e-3)
    assert f["is_deluxe"] == pytest.approx(0.0250, abs=1e-3)
    assert f["is_compilation"] == pytest.approx(0.2321, abs=1e-3)
    assert f["wrong_edition_suspect"] == pytest.approx(0.0072, abs=1e-3)
