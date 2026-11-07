"""P15: cell bootstrap, design, the hierarchical model recovers known genre breaks; pinned
results."""

import json

import numpy as np
import polars as pl
import pytest

from lw.models import genre_hier as gh


def test_boot_q_clusters_widen_the_se():
    rng = np.random.default_rng(0)
    # 40 albums of 10 tracks; album effects make tracks within an album alike
    album = np.repeat(np.arange(40), 10)
    v = rng.normal(0, 1, 40)[album] + rng.normal(0, 0.3, 400)
    o = np.argsort(v)
    se_cl = gh._boot_q(v[o], album[o], 0.5, 300, np.random.default_rng(1)).std()
    se_iid = gh._boot_q(v[o], np.arange(400)[o], 0.5, 300, np.random.default_rng(1)).std()
    assert se_cl > 1.5 * se_iid


def test_design_terms():
    t = np.array([2005.0, 2007.0, 2016.0, 2020.0])
    x = gh.design(t, 2016, 2007)
    assert x["post"].tolist() == [0, 0, 1, 1]
    assert x["spost"].tolist() == [0, 0, 0, 4]
    assert x["hinge"].tolist() == [0, 0, 9, 13]
    assert "hinge" not in gh.design(t, 2016, None)


def _cells(gaps: dict, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for g, gap in gaps.items():
        base = rng.normal(-11, 2)
        for y in range(2000, 2023):
            mu = base + 0.15 * min(y - 2007, 0) + gap * (y >= 2016)
            rows.append({"genre": g, "year": y, "lufs_median": mu + rng.normal(0, 0.12),
                         "lufs_median_se": 0.08})  # fmt: skip
    return pl.DataFrame(rows)


@pytest.mark.slow
def test_model_recovers_a_genre_specific_drop():
    gaps = {"rock": 0.0, "metal": -0.8, "pop": 0.0, "jazz": 0.0, "electronic": 0.0, "punk": 0.0}
    idata, data = gh.fit(
        _cells(gaps), "lufs_median", "bend", draws=500, tune=1500, chains=2, target_accept=0.99
    )
    e = {r["genre"]: r for r in gh.effects(idata, data, "t", "lufs_median")}
    assert e["metal"]["p_neg"] > 0.99
    assert e["metal"]["gap"] == pytest.approx(-0.8, abs=0.3)
    for g in ("rock", "pop", "jazz"):
        assert e[g]["gap_lo"] < 0 < e[g]["gap_hi"]
    assert gh.diagnostics(idata)["divergences"] <= 10  # <1% of 1,000 draws


@pytest.mark.skipif(not gh.SUMMARY.exists(), reason="run `make models` first")
def test_pinned():
    s = json.loads(gh.SUMMARY.read_text())
    assert s["n_units_fit"] == 1_894_403
    for k, f in s["fits"].items():
        assert f["max_rhat"] < (1.01 if f["main"] else 1.011), k
        assert f["min_ess_bulk"] > 400, k
        assert f["divergences"] == 0, k
    # the bend form predicts better than the brief's straight pre-trend, for every metric
    for m, r in s["loo"].items():
        assert r["diff"] > 2 * r["se"], m
    # straight form: most genres "drop"; bend form: almost none
    assert s["fits"]["lufs_median|straight"]["n_gap_neg_95"] >= 6
    f = s["fits"]["lufs_median|bend"]
    assert f["n_genres"] == 12
    assert f["n_gap_neg_95"] <= 2  # no general post-2016 drop across genres
