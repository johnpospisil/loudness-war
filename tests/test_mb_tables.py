"""P07: MusicBrainz tables — partial dates, earliest-event rule, flags, and pinned counts."""

import json
from pathlib import Path

import duckdb
import pytest

from lw.build import mb_tables as mt

BUILD = Path(__file__).resolve().parents[1] / "data/interim/mb/build.json"


def _view(con, name, cols, rows):
    """A VARCHAR view like the COPY-text views made by musicbrainz_dump.connect()."""
    if rows:
        vals = ", ".join(
            "(" + ", ".join("null" if v is None else f"'{v}'" for v in r) + ")" for r in rows
        )
        body = f"select * from (values {vals}) t({', '.join(cols)})"
    else:
        body = "select " + ", ".join(f"null::varchar as {c}" for c in cols) + " where false"
    con.execute(
        f"create or replace view {name} as select "
        + ", ".join(f"{c}::varchar as {c}" for c in cols)
        + f" from ({body})"
    )


def _dates(rows):
    con = duckdb.connect()
    _view(con, "d", ["y", "m", "d"], rows)
    return con.execute(f"select {mt.partial_date('y', 'm', 'd', 'x')} from d").fetchall()


@pytest.mark.parametrize(
    "ymd, expect",
    [
        (("1991", "09", "24"), (1991, 9, 24, "1991-09-24", "day")),
        (("1991", "9", None), (1991, 9, None, "1991-09", "month")),  # YYYY-MM
        (("1991", None, None), (1991, None, None, "1991", "year")),  # YYYY
        (("1991", None, "24"), (1991, None, None, "1991", "year")),  # day without month dropped
        ((None, "09", "24"), (None, None, None, None, None)),  # no year: undated
        ((None, None, None), (None, None, None, None, None)),
        (("812", None, None), (812, None, None, "0812", "year")),  # zero-padded, sorts right
    ],
)
def test_partial_date(ymd, expect):
    assert _dates([ymd])[0] == expect


def test_partial_dates_sort_as_strings():
    got = [r[3] for r in _dates([("1991", "9", "24"), ("1991", None, None), ("1990", "12", None)])]
    assert sorted(got) == ["1990-12", "1991", "1991-09-24"]


@pytest.fixture
def con():
    """A tiny synthetic export: one group with 3 releases, one redirect, two tags."""
    c = duckdb.connect()
    v = lambda n, cols, rows: _view(c, n, cols, rows)  # noqa: E731
    v("artist_credit", ["id", "name"], [("1", "Nirvana")])
    v(
        "release_group",
        ["id", "gid", "name", "artist_credit", "type", "comment"],
        [("10", "rg-a", "Nevermind", "1", "1", ""), ("11", "rg-b", "Hits", "1", None, "")],
    )
    v("release_group_primary_type", ["id", "name"], [("1", "Album")])
    v("release_group_secondary_type", ["id", "name"], [("1", "Compilation"), ("6", "Live")])
    v(
        "release_group_secondary_type_join",
        ["release_group", "secondary_type"],
        [("11", "1"), ("11", "6")],
    )
    v(
        "release_group_meta",
        [
            "id",
            "release_count",
            "first_release_date_year",
            "first_release_date_month",
            "first_release_date_day",
        ],
        [("10", "3", "1991", "9", "24"), ("11", "1", "2001", None, None)],
    )
    v(
        "release",
        [
            "id",
            "gid",
            "name",
            "artist_credit",
            "release_group",
            "status",
            "packaging",
            "barcode",
            "comment",
        ],
        [
            ("100", "rel-1", "Nevermind", "1", "10", "1", None, "720642442524", ""),
            ("101", "rel-2", "Nevermind", "1", "10", "1", None, "", "remaster"),
            ("102", "rel-3", "Nevermind", "1", "10", None, None, None, ""),
        ],
    )
    # rel-1: a precise and a year-only event in 1991 plus a 1992 one; rel-3: no events
    v(
        "release_country",
        ["release", "country", "date_year", "date_month", "date_day"],
        [
            ("100", "222", "1992", "1", None),
            ("100", "221", "1991", None, None),
            ("100", "223", "1991", "9", "24"),
            ("101", "222", "2011", "9", "19"),
        ],
    )
    v(
        "release_unknown_country",
        ["release", "date_year", "date_month", "date_day"],
        [("101", "2011", None, None)],
    )
    v("iso_3166_1", ["area", "code"], [("221", "GB"), ("222", "US"), ("223", "DE")])
    v("release_status", ["id", "name"], [("1", "Official")])
    v("release_packaging", ["id", "name"], [])
    v("label", ["id", "name"], [("7", "DGC")])
    v(
        "release_label",
        ["id", "release", "label", "catalog_number"],
        [("2", "100", "7", "DGC-24425"), ("1", "100", None, "")],
    )
    v("medium_format", ["id", "name"], [("1", "CD"), ("12", "Digital Media")])
    v(
        "medium",
        ["id", "release", "position", "format", "track_count"],
        [
            ("1000", "100", "1", "1", "12"),
            ("1001", "101", "2", "12", "4"),
            ("1002", "101", "1", "1", "13"),
        ],
    )
    v(
        "recording",
        ["id", "gid", "name", "artist_credit", "length", "comment", "video"],
        [("5", "rec-1", "Smells Like Teen Spirit", "1", "301000", "", "f")],
    )
    v(
        "track",
        ["id", "recording", "medium", "position", "number", "length", "is_data_track"],
        [("1", "5", "1000", "1", "1", "301920", "f"), ("2", "5", "1002", "1", "1", "301000", "f")],
    )
    v("recording_gid_redirect", ["gid", "new_id"], [("rec-old", "5")])
    v("release_gid_redirect", ["gid", "new_id"], [])
    v("release_group_gid_redirect", ["gid", "new_id"], [])
    v("tag", ["id", "name"], [("1", "grunge"), ("2", "seen live")])
    v("genre", ["id", "name"], [("1", "grunge")])
    v("release_group_tag", ["release_group", "tag", "count"], [("10", "1", "12"), ("10", "2", "1")])
    return c  # fmt: skip


def _rows(c, tmp_path, name):
    mt.build(c, tmp_path, [name])
    rel = c.execute(f"select * from read_parquet('{tmp_path}/{name}.parquet')")
    cols = [d[0] for d in rel.description]
    return {r[0]: dict(zip(cols, r, strict=True)) for r in rel.fetchall()}


def test_release_earliest_event_and_fields(con, tmp_path):
    r = _rows(con, tmp_path, "release")
    a = r["rel-1"]
    # 1991-09-24 (DE) beats year-only 1991 (GB) and 1992 (US)
    assert (a["release_date"], a["release_date_precision"], a["country"]) == (
        "1991-09-24", "day", "DE")  # fmt: skip
    assert (a["n_events"], a["n_countries"], a["status"]) == (3, 3, "Official")
    assert (a["label"], a["n_labels"]) == ("DGC", 2)  # first *named* label; id 1 has none
    assert a["catalog_number"] == "DGC-24425"
    assert a["barcode"] == "720642442524" and a["formats"] == ["CD"]
    b = r["rel-2"]  # unknown-country year-only event loses to the dated one in the same year
    assert (b["release_date"], b["country"]) == ("2011-09-19", "US")
    assert b["formats"] == ["CD", "Digital Media"]  # ordered by medium position
    assert (b["barcode"], b["comment"], b["n_media"], b["n_tracks"]) == (None, "remaster", 2, 17)
    c = r["rel-3"]
    assert c["release_date"] is None and c["n_events"] == 0 and c["formats"] == []
    assert c["release_group_mbid"] == "rg-a"


def test_release_group_types_and_dates(con, tmp_path):
    g = _rows(con, tmp_path, "release_group")
    assert g["rg-a"]["first_release_date"] == "1991-09-24"
    assert g["rg-a"]["primary_type"] == "Album" and g["rg-a"]["secondary_types"] == []
    assert not g["rg-a"]["is_compilation"]
    h = g["rg-b"]
    assert h["first_release_date"] == "2001" and h["first_release_date_precision"] == "year"
    assert h["secondary_types"] == ["Compilation", "Live"]
    assert h["is_compilation"] and h["is_live"] and not h["is_remix"]
    assert h["primary_type"] is None


def test_recording_release_tags_redirects(con, tmp_path):
    mt.build(con, tmp_path, ["recording_release"])
    rr = con.execute(
        f"select release_mbid, medium_format, track_length_ms, is_data_track "
        f"from read_parquet('{tmp_path}/recording_release.parquet') order by 1"
    ).fetchall()
    assert rr == [("rel-1", "CD", 301920, False), ("rel-2", "CD", 301000, False)]
    t = _rows(con, tmp_path, "rg_tags")
    assert t["rg-a"]["tag"] in {"grunge", "seen live"}
    tags = con.execute(
        f"select tag, count, is_genre from read_parquet('{tmp_path}/rg_tags.parquet') order by 1"
    ).fetchall()
    assert tags == [("grunge", 12, True), ("seen live", 1, False)]
    red = _rows(con, tmp_path, "mbid_redirect")
    assert red["recording"]["old_mbid"] == "rec-old" and red["recording"]["new_mbid"] == "rec-1"


@pytest.mark.skipif(not BUILD.exists(), reason="run `make ingest-mb` first")
def test_pinned_counts():
    t = json.loads(BUILD.read_text())
    assert t["dump"] == "20261101-125824"
    rows = {k: v["rows"] for k, v in t["tables"].items()}
    assert rows == {
        "mbid_redirect": 5_545_207,
        "release_group": 4_615_620,
        "rg_tags": 5_037_558,
        "recording": 40_791_784,
        "release": 5_897_156,
        "recording_release": 58_760_222,
    }
