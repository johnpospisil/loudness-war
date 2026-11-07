"""P14: the year-only quantile-regression solver is exact; it recovers quantile-specific breaks;
pinned headline results."""

import json

import numpy as np
import polars as pl
import pytest
import statsmodels.api as sm

from lw.models import quantile_trends as qt


def _data(n_per=4000, top_drop=0.0, seed=0):
    """Years 2000-2022; the upper tail (only) drops by top_drop from 2016."""
    rng = np.random.default_rng(seed)
    year = np.repeat(np.arange(2000, 2023), n_per)
    t = year.astype(float)
    base = -11 + 0.03 * (t - 2000)
    z = rng.normal(0, 3, len(t))
    y = base + z - top_drop * (t >= 2016) * (z > 0) * (z / 3)
    return year, y


def _fit(year, y, tau, X_fn, w=None):
    Y = qt.Years(year, y)
    w = np.ones(len(y)) if w is None else w[Y.order]
    X = X_fn(Y.years.astype(float))
    return qt.qr_fit(Y, X, tau, Y.cum(w))


def test_solver_matches_statsmodels_quantreg():
    year, y = _data(n_per=600, seed=1)
    for tau in (0.1, 0.5, 0.9):
        b = _fit(year, y, tau, lambda t: qt.x_single(t, 2016))
        ref = sm.QuantReg(y, qt.x_single(year.astype(float), 2016)).fit(q=tau).params
        assert np.allclose(b, ref, atol=0.03), (tau, b, ref)


def test_solver_minimises_check_loss():
    year, y = _data(n_per=500, seed=2)
    Y = qt.Years(year, y)
    X = qt.x_bend(Y.years.astype(float), 2007, 2016)
    w = np.ones(len(y))
    b = qt.qr_fit(Y, X, 0.9, Y.cum(w))
    best = qt.check_loss(Y, X, b, 0.9, w)
    rng = np.random.default_rng(0)
    for _ in range(30):
        assert qt.check_loss(Y, X, b + rng.normal(0, 0.02, len(b)), 0.9, w) >= best - 1e-6


def test_upper_tail_break_found_only_in_upper_quantiles():
    year, y = _data(top_drop=1.5, seed=3)
    g = {}
    for tau in (0.1, 0.5, 0.9):
        b = _fit(year, y, tau, lambda t: qt.x_single(t, 2016))
        g[tau] = qt.summarise_params({"break": 2016}, np.arange(2000, 2023.0), b)["gap"]
    assert abs(g[0.1]) < 0.15 and abs(g[0.5]) < 0.15
    # above the median z shrinks by half: the P90 drops by 0.5 * 1.2816 sd = 0.5 * 3.84
    assert g[0.9] == pytest.approx(-0.5 * 1.2816 * 3, abs=0.25)


def test_integer_weights_equal_duplicated_data():
    year, y = _data(n_per=300, seed=4)
    w = np.where(np.arange(len(y)) % 3 == 0, 2.0, 1.0)
    b_w = _fit(year, y, 0.75, lambda t: qt.x_single(t, 2016), w=w)
    dup = np.arange(len(y))[w == 2.0]
    b_d = _fit(np.concatenate([year, year[dup]]), np.concatenate([y, y[dup]]), 0.75,
               lambda t: qt.x_single(t, 2016))  # fmt: skip
    assert np.allclose(b_w, b_d, atol=1e-3)


def test_genre_weights_give_every_year_the_reference_mix():
    df = pl.DataFrame({
        "year": [2000] * 4 + [2001] * 4 + [2020] * 4,
        "genre": ["rock", "rock", "rock", "pop", "rock", "pop", "pop", None, "pop", "pop", "pop", "rock"],  # noqa: E501
    })  # fmt: skip
    w = qt.genre_weights(df, 2000, 2001)
    d = df.with_columns(pl.Series("w", w))
    ref = {"rock": 4 / 7, "pop": 3 / 7}
    for yr in (2000, 2001, 2020):
        z = d.filter((pl.col("year") == yr) & pl.col("genre").is_not_null())
        tot = z["w"].sum()
        for g, r in ref.items():
            assert z.filter(pl.col("genre") == g)["w"].sum() / tot == pytest.approx(r)
    assert d.filter(pl.col("genre").is_null())["w"].sum() == 0


@pytest.mark.skipif(not qt.SUMMARY.exists(), reason="run `make models` first")
def test_pinned_headline():
    s = json.loads(qt.SUMMARY.read_text())
    assert s["n_units"]["headline"] == 2_011_235
    f = s["fits"]
    # the loudest decile did not come down against the plateau-era trend
    p90 = f["headline|single|2005-2022|2016|0.9"]
    assert p90["gap"] == pytest.approx(0.04, abs=0.02)
    assert p90["gap_lo"] < 0 < p90["gap_hi"]
    # bend first: the loudest decile sits slightly above the bend model
    assert f["headline|bend|2000-2022|2016|k2007|0.9"]["gap"] == pytest.approx(0.12, abs=0.03)
    # median: the P13 shortfall against a straight 2000-15 trend
    assert f["headline|single|2000-2022|2016|0.5"]["gap"] == pytest.approx(-0.55, abs=0.03)
