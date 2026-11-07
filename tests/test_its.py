"""P13: segmented regression recovers known breaks; pinned headline results."""

import json

import numpy as np
import pytest

from lw.models import its


def _series(level=0.0, slope=0.0, bend=None, b=2016, noise=0.05, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(2000, 2023).astype(float)
    y = -11 + 0.02 * (t - 2000) + level * (t >= b) + slope * (t - b) * (t >= b)
    if bend is not None:
        y = y - 0.15 * np.clip(t - bend, 0, None)
    return t, y + rng.normal(0, noise, len(t))


def test_segmented_recovers_level_and_slope():
    t, y = _series(level=-0.5, slope=-0.05)
    r = its.segmented(t, y, 2016)
    assert r["level"] == pytest.approx(-0.5, abs=0.15)
    assert r["slope"] == pytest.approx(-0.05, abs=0.03)
    assert r["p_level"] < 0.05


def test_no_break_gives_small_gap():
    t, y = _series()
    r = its.segmented(t, y, 2016)
    assert abs(r["gap"]) < 3 * r["gap_se"] + 0.05


def test_two_break_separates_earlier_bend_from_era_break():
    # a bend in 2008 and nothing at 2016: the 2016 terms are not needed
    t, y = _series(bend=2008, seed=3)
    assert its.two_break(t, y, 2008, 2016)["p_joint"] > 0.05
    # a real 2016 step on top of the bend is found
    t, y = _series(bend=2008, level=-0.6, seed=3)
    r = its.two_break(t, y, 2008, 2016)
    assert r["p_joint"] < 0.05 and r["level"] < -0.3


@pytest.mark.skipif(not its.SUMMARY.exists(), reason="run `make models` first")
def test_pinned_headline():
    s = json.loads(its.SUMMARY.read_text())
    m = s["main"]["yearly_median|2000-2022|2016"]
    assert m["gap"] == pytest.approx(-0.56, abs=0.02)
    assert s["main"]["yearly_median|2005-2022|2016"]["gap"] == pytest.approx(-0.26, abs=0.02)
    assert s["scan_headline_lufs_level+slope"]["best_break"] == 2010
    assert s["scan_headline_lufs_hinge"]["best_break"] == 2007
    assert 2015 not in s["scan_headline_lufs_level+slope"]["set95"]
    ps = [v["p_joint"] for v in s["two_break_headline_lufs"].values()]
    assert min(ps) > 0.1  # 2015/16 terms not needed once the 2006-11 bend is allowed
