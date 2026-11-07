"""P10: tag -> genre map, vote winner, and the committed reference map."""

import csv

import duckdb
import pytest

from lw.build import genres as gn


@pytest.mark.parametrize(
    "tag, genre",
    [
        ("pop punk", "punk"), ("rap metal", "metal"), ("folk rock", "rock"),
        ("country rock", "folk_country"),
        ("blues rock", "rock"), ("Dubstep", "electronic"), ("dub", "reggae"),
        ("dub techno", "electronic"), ("hardcore hip hop", "hip_hop"),
        ("hardcore punk", "punk"), ("happy hardcore", "electronic"),
        ("new jack swing", "rnb_soul"), ("trip hop", "electronic"), ("indie pop", "pop"),
        ("indie rock", "rock"), ("symphonic metal", "metal"), ("symphonic rock", "rock"),
        ("baroque", "classical"), ("baroque pop", "pop"), ("soul jazz", "jazz"),
        ("neo soul", "rnb_soul"), ("ska punk", "punk"), ("ska", "reggae"),
        ("synth-pop", "pop"), ("synthwave", "electronic"), ("country blues", "rnb_soul"),
        ("pop rap", "hip_hop"), ("soundtrack", "other"), ("instrumental", "ignore"),
        ("post-punk", "rock"), ("emo", "punk"), ("garage rock", "rock"),
        ("uk garage", "electronic"), ("hip-hop", "hip_hop"), ("salsa", "other"),
    ],
)  # fmt: skip
def test_map_tag(tag, genre):
    assert gn.map_tag(tag)[0] == genre


def test_unmatched_genre_defaults_to_other():
    assert gn.map_tag("some unheard-of style") == ("other", "default")


def test_winner_votes_ties_and_share():
    con = duckdb.connect()
    con.execute("""create table gmap as select * from (values
        ('rock', 'rock'), ('metal', 'metal'), ('pop', 'pop'), ('experimental', 'other'))
        t(tag, genre)""")
    con.execute("""create table src as select * from (values
        ('a', 'rock', 3), ('a', 'metal', 1), ('a', 'pop', 1),      -- most votes wins
        ('b', 'rock', 2), ('b', 'metal', 2),                       -- tie: metal before rock
        ('c', 'experimental', 1), ('c', 'pop', 1),                 -- tie: other loses
        ('d', 'unmapped tag', 5), ('d', 'pop', 1))                 -- unmapped tags ignored
        t(id, tag, count)""")
    gn._winner(con, "src", "w")
    got = {r[0]: (r[1], round(r[2], 3)) for r in con.execute("select * from w").fetchall()}
    assert got == {"a": ("rock", 0.6), "b": ("metal", 0.5), "c": ("pop", 0.5), "d": ("pop", 1.0)}


def test_committed_map_is_consistent():
    rows = list(csv.DictReader(open(gn.MAP)))
    assert {r["genre"] for r in rows} <= set(gn.GENRES) | {"ignore"}
    # the CSV is what map_tag produces (regenerate with --write-map after editing rules)
    assert all(gn.map_tag(r["tag"])[0] == r["genre"] for r in rows)
    assert len(gn.GENRES) == 12 and set(gn.LABELS) == set(gn.GENRES)


def test_hl_maps_cover_genres():
    for m in gn.HL_MAPS.values():
        assert set(m.values()) <= set(gn.GENRES)


@pytest.mark.skipif(not gn.SUMMARY.exists(), reason="run `make genres` first")
def test_pinned_genres():
    import json

    s = json.loads(gn.SUMMARY.read_text())
    src = s["source_share_main"]
    assert src["rg"] == pytest.approx(0.7976, abs=1e-3)
    assert src["artist"] == pytest.approx(0.0968, abs=1e-3)
    assert src["hl"] == pytest.approx(0.0563, abs=1e-3)
    assert src.get("none", 0) < 0.001
    g = s["genre_share_main"]
    assert g["rock"] == pytest.approx(0.2414, abs=1e-3)
    assert g["electronic"] == pytest.approx(0.2214, abs=1e-3)
    assert s["mb_rg_n"] == 3_271_754
    assert s["agree_rg_genre_artist"] == pytest.approx(0.6773, abs=1e-3)
    assert s["agree_rg_genre_hl_rosamerica"] == pytest.approx(0.3273, abs=1e-3)
