import http.server
import json
import threading
from pathlib import Path

import polars as pl
import pytest

from lw.build import parse_lowlevel as pll

FIXTURE = Path(__file__).parent / "fixtures" / "lowlevel_fixture.tar.zst"


@pytest.fixture
def parsed(tmp_path):
    out, err = tmp_path / "f.parquet", tmp_path / "f.errors.jsonl"
    with open(FIXTURE, "rb") as fh:
        stats = pll.parse_stream(fh, 7, out, err)
    return stats, pl.read_parquet(out), err


def test_member_name_parsing():
    name = "x/lowlevel/0e/1/0e11c0fd-a1da-4b88-a438-7ef55c5809ec-12.json"
    assert pll.parse_member_name(name) == ("0e11c0fd-a1da-4b88-a438-7ef55c5809ec", 12)
    assert pll.parse_member_name("x/lowlevel/README") is None


def test_rows_errors_and_schema(parsed):
    stats, df, err = parsed
    assert stats == {"rows": 20, "errors": 2}
    assert df.height == 20
    assert df.columns == pll.SCHEMA.names
    assert (df["part"] == 7).all()
    errors = [json.loads(line) for line in err.read_text().splitlines()]
    assert {e["bytes"] for e in errors} == {0, 9}


def test_known_record_values(parsed):
    """First sample record: Pink Floyd, 'Time' (MP3 192k), checked by hand against the JSON."""
    _, df, _ = parsed
    r = df.filter(pl.col("recording_mbid") == "0e11c0fd-a1da-4b88-a438-7ef55c5809ec").row(
        0, named=True
    )
    assert r["submission_offset"] == 0
    assert r["replay_gain"] == pytest.approx(-6.16133308411, abs=1e-5)
    assert r["codec"] == "mp3" and r["lossless"] is False and r["bit_rate"] == 192000
    assert r["length_s"] == pytest.approx(426.475, abs=1e-3)
    assert r["essentia_version"] == "2.1-beta1" and r["extractor_version"] == "music 1.0"
    assert r["tag_musicbrainz_albumid"] == "25fbfbb4-b1ee-4448-aadf-ae3bc2e2dd27"
    assert r["tag_date"] == "1973-03-24" and r["tag_artist"] == "Pink Floyd"
    assert r["rhythm_bpm"] == pytest.approx(120.764, abs=1e-3)


def test_core_metrics_complete(parsed):
    _, df, _ = parsed
    for c in (
        "replay_gain",
        "dynamic_complexity",
        "average_loudness",
        "spectral_rms_mean",
        "codec",
    ):
        assert df[c].null_count() == 0, c


def test_extract_row_tolerates_missing_and_bad_values():
    row = pll.extract_row(
        {"lowlevel": {"dynamic_complexity": "nan?", "spectral_rms": 3}}, "m", 0, 1
    )
    assert row["dynamic_complexity"] is None and row["spectral_rms_mean"] is None
    assert row["replay_gain"] is None and row["tag_date"] is None
    assert pll._num(float("nan"), pll.pa.float32()) is None


def test_limit_stops_early(tmp_path):
    with open(FIXTURE, "rb") as fh:
        stats = pll.parse_stream(fh, 0, tmp_path / "a.parquet", tmp_path / "a.err", limit=5)
    assert stats["rows"] == 5


def test_parse_parts_spec():
    assert pll._parse_parts("0-2,5,7-8") == [0, 1, 2, 5, 7, 8]


class _FlakyHandler(http.server.BaseHTTPRequestHandler):
    """Serves the fixture; the first full GET drops the connection halfway through."""

    data = FIXTURE.read_bytes()
    dropped = False

    def log_message(self, *a):
        pass

    def do_GET(self):
        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            self.send_response(206)
        else:
            self.send_response(200)
        body = self.data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not rng and not _FlakyHandler.dropped:
            _FlakyHandler.dropped = True
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)


def test_http_reader_resumes_after_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(pll.time, "sleep", lambda s: None)
    srv = http.server.HTTPServer(("127.0.0.1", 0), _FlakyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/fixture.tar.zst"
    try:
        stats = pll.process_part(5, tmp_path, source=url, verify=False)
    finally:
        srv.shutdown()
    assert _FlakyHandler.dropped
    assert stats["rows"] == 20 and stats["bytes"] == FIXTURE.stat().st_size
    assert (tmp_path / "part=05.done.json").exists()
    # second run is skipped via the done marker
    assert pll.process_part(5, tmp_path, source=url, verify=False)["rows"] == 20
