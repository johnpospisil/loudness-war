"""P12: cluster-bootstrap weighted median, and pinned yearly medians."""

import numpy as np
import polars as pl
import pytest

from lw.models import yearly as yr


def test_weighted_median_boot_centres_on_median():
    rng = np.random.default_rng(0)
    x = np.sort(rng.normal(-11, 3, 5000))
    cl = rng.integers(0, 400, 5000)
    b = yr.weighted_median_boot(x, cl, 400, np.random.default_rng(1))
    assert abs(np.median(b) - np.median(x)) < 0.1
    # clusters of similar values (x is sorted, so blocks of 100 are correlated) widen the CI
    b_unit = yr.weighted_median_boot(x, np.arange(5000), 400, np.random.default_rng(2))
    b_block = yr.weighted_median_boot(x, np.arange(5000) // 100, 400, np.random.default_rng(2))
    assert b_block.std() > 2 * b_unit.std()


@pytest.mark.skipif(not yr.OUT.exists(), reason="run `make models` first")
def test_pinned_yearly():
    d = pl.read_parquet(yr.OUT)
    h = d.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs"))
    assert h.height == 43 and h["n"].sum() == 2_997_479

    def mean(a, b):
        return h.filter(pl.col("year").is_between(a, b))["median"].mean()

    assert mean(1980, 1989) == pytest.approx(-15.58, abs=0.02)
    assert mean(2010, 2015) == pytest.approx(-10.90, abs=0.02)
    assert mean(2016, 2022) == pytest.approx(-10.87, abs=0.02)
    assert (h["ci_lo"] <= h["median"]).all() and (h["median"] <= h["ci_hi"]).all()
    lra = d.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lra"))
    assert (lra["p10"] >= 0).all()
