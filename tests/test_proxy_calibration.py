"""P03: pin the fitted AcousticBrainz-proxy calibration (data/reference/proxy_calibration.json)."""

import json
from pathlib import Path

import pytest

CAL = Path(__file__).resolve().parents[1] / "data/reference/proxy_calibration.json"


@pytest.fixture(scope="module")
def cal():
    return json.loads(CAL.read_text())


def test_headline_models(cal):
    assert cal["headline"] == {"lufs": "lufs_rg", "lra": "lra_dc"}


def test_calibration_set(cal):
    s = cal["calibration_set"]
    assert s["n_tracks"] == 1185 and s["n_albums"] == 322


def test_lufs_from_replay_gain(cal):
    m = cal["models"]["lufs_rg"]
    assert m["coef"]["const"] == pytest.approx(-23.44, abs=0.01)
    assert m["coef"]["replay_gain"] == pytest.approx(-1.042, abs=0.001)
    assert m["cv_rmse"] == pytest.approx(1.34, abs=0.01)
    assert max(abs(b) for b in m["cv_bias_by_quintile"]) < 0.2  # LU, by predicted quintile


def test_lra_from_dynamic_complexity(cal):
    m = cal["models"]["lra_dc"]
    assert m["coef"]["dynamic_complexity"] == pytest.approx(1.775, abs=0.001)
    assert m["cv_rmse"] == pytest.approx(2.93, abs=0.01)
    assert max(abs(b) for b in m["cv_bias_by_quintile"]) < 0.5
