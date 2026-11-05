"""P03: EBU R128 conformance (Tech 3341 / 3342) and the Essentia extractor."""

import numpy as np
import pytest
import soundfile as sf

from lw.measure import pyloudnorm_check as plc


@pytest.mark.parametrize("case", plc.CASES, ids=lambda c: c.name)
def test_pyloudnorm_conformance(case):
    x = plc.case_signal(case)
    got = plc.pyloudnorm_measure(x, plc.RATE)[case.metric]
    assert abs(got - case.expected) <= case.tol, f"{case.name}: {got:.3f} vs {case.expected}"


@pytest.mark.parametrize("case", plc.CASES[:2] + plc.CASES[5:6], ids=lambda c: c.name)
def test_ffmpeg_conformance(case, tmp_path):
    wav = tmp_path / "c.wav"
    sf.write(wav, plc.case_signal(case), plc.RATE, subtype="FLOAT")
    got = plc.ffmpeg_ebur128(wav)[f"ff_{case.metric}"]
    assert abs(got - case.expected) <= case.tol


def test_synthetic_hits_target_loudness():
    x = plc.synthetic_programme(-14.0, 4.0, 2.0, seed=1, seconds=20)
    m = plc.pyloudnorm_measure(x, 44_100)
    assert abs(m["lufs"] + 14.0) < 0.1
    assert np.max(np.abs(x)) < 1.0


def test_decode_roundtrip(tmp_path):
    x = plc.case_signal(plc.CASES[0])[: plc.RATE * 5]
    wav = tmp_path / "d.wav"
    sf.write(wav, x, plc.RATE, subtype="FLOAT")
    y, sr = plc.decode(wav)
    assert sr == plc.RATE and y.shape == x.shape
    assert np.max(np.abs(y - x)) < 1e-6


@pytest.mark.skipif(not plc.extractor_available(), reason="Essentia extractor / Rosetta missing")
def test_extractor_steady_pink_noise(tmp_path):
    """Steady pink noise: replay_gain ≈ −(LUFS + 19.1) dB, dynamic complexity near 0."""
    x = plc.synthetic_programme(-18.0, 0.0, 0.0, seed=0, seconds=30)
    wav = tmp_path / "p.wav"
    sf.write(wav, x, 44_100, subtype="PCM_24")
    e = plc.essentia_measure(wav)
    assert e["essentia_version"] == "v2.1_beta2-2-gbb40004"
    assert abs(e["replay_gain"] - (18.0 - 19.1)) < 0.6
    assert e["dynamic_complexity"] < 0.5


# --- memory guards (after the 2026-11-04 audiobook freeze) ----------------------------
def test_check_size_rejects_audiobook_length():
    with pytest.raises(plc.SkipFile, match="duration"):
        plc.check_size(48_000, 2, 39_432.0)  # "1984" audiobook, 11 h


def test_check_size_rejects_hires_over_budget():
    with pytest.raises(plc.SkipFile, match="GB"):
        plc.check_size(192_000, 2, 15 * 60)  # 15 min at 192 kHz: within duration, over RAM


def test_check_size_accepts_long_song():
    plc.check_size(48_000, 2, 10 * 60)  # longest song measured so far is ~10 min


def test_decode_guard_skips_long_file(tmp_path, monkeypatch):
    wav = tmp_path / "long.wav"
    sf.write(wav, np.zeros((48_000 * 3, 2), dtype="float32"), 48_000)
    monkeypatch.setattr(plc, "MAX_DURATION_S", 2.0)
    monkeypatch.setattr(plc.check_size, "__defaults__", (2.0, plc.MAX_FILE_BYTES))
    with pytest.raises(plc.SkipFile):
        plc.decode(wav)
    assert plc._library_one(str(wav))["error"].startswith("skipped")


def test_sample_library_skips_audiobook_folders(tmp_path):
    for d in ["Artist/Album", "eBooks", "Audiobooks/Author"]:
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "a.m4a").write_bytes(b"x")
    picks = plc.sample_library([tmp_path], n=10, per_album=4)
    assert [p.parent.name for p in picks] == ["Album"]


def test_jobs_fit_ram():
    ram = plc.os.sysconf("SC_PAGE_SIZE") * plc.os.sysconf("SC_PHYS_PAGES")
    assert plc.max_jobs_for_ram() * (plc.MAX_FILE_BYTES + plc.WORKER_OVERHEAD_BYTES) <= ram
