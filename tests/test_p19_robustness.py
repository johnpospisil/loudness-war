"""P19: weighted median, coverage rule, pinned spec-curve numbers."""

import json

import numpy as np
import polars as pl
import pytest

from lw.models import robustness as rb


def test_wmedian_matches_median_with_equal_weights():
    x = np.sort(np.random.default_rng(0).normal(size=1001))
    assert rb.wmedian(x, np.ones_like(x)) == pytest.approx(np.median(x))
    # all the weight on the top half moves the median up
    w = np.r_[np.full(500, 0.01), np.ones(501)]
    assert rb.wmedian(x, w) > np.median(x)


def test_coverage_rule_only_censors_cohorts():
    n = [10_000] * 15 + [9_000] * 5 + [2_000] * 3
    s = pl.DataFrame({"year": list(range(2000, 2023)), "n": n})
    assert rb.covered(s, cohort=False).height == 23
    assert rb.covered(s, cohort=True)["year"].max() == 2019


@pytest.mark.skipif(not rb.SUMMARY.exists(), reason="run `make robustness` first")
def test_pinned():
    s = json.loads(rb.SUMMARY.read_text())
    h = s["by_spec"]
    # the headline row reproduces P13
    assert h["headline|straight|2000-2022|2016"]["gap"] == pytest.approx(-0.56, abs=0.01)
    assert h["headline|bend|2000-2022|2016"]["gap"] == pytest.approx(-0.08, abs=0.01)
    assert s["straight|2000-2022"]["share_negative"] == 1.0
    assert s["bend|2000-2022"]["gap_median"] == pytest.approx(-0.11, abs=0.02)
    assert "cohort_0_9|bend|2000-2022|2016" not in h  # right-censored, too few post years
