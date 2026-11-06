"""P06: high-level parser on 20 real records + 1 bad member."""

from pathlib import Path

import polars as pl
import pytest

from lw.build import parse_highlevel as hl

FIXTURE = Path(__file__).parent / "fixtures" / "highlevel_fixture.tar.zst"


@pytest.fixture
def parsed(tmp_path):
    s = hl.process_part(0, tmp_path, source=str(FIXTURE), verify=False)
    return s, pl.read_parquet(tmp_path / "part=00.parquet")


def test_rows_errors_schema(parsed):
    s, df = parsed
    assert (s["rows"], s["errors"]) == (20, 1)
    assert df.columns == hl.SCHEMA.names
    assert df.height == df.select("recording_mbid", "submission_offset").unique().height


def test_known_first_record(parsed):
    _, df = parsed
    r = df.row(0, named=True)  # Pink Floyd - Time (first member of part 0)
    assert r["recording_mbid"] == "0e11c0fd-a1da-4b88-a438-7ef55c5809ec"
    assert r["danceability"] == "not_danceable"
    assert r["danceability_p"] == pytest.approx(0.58838, abs=1e-4)
    assert r["md5_encoded"] == "156d2092079f1f3605876e9d335aa569"


def test_classifiers_complete(parsed):
    _, df = parsed
    for c in hl.CLASSIFIERS:
        assert df[c].null_count() == 0 and df[f"{c}_p"].is_between(0, 1).all()


def test_extract_row_tolerates_missing():
    r = hl.extract_row({"highlevel": {"gender": "bad"}}, "x", 0, 0)
    assert r["gender"] is None and r["mood_sad"] is None
