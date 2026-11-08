"""P17: period coding, density effects recover a planted shift, pinned results."""

import json

import numpy as np
import polars as pl
import pytest

from lw.models import descriptors as ds


def test_periods_cover_1990_2022():
    d = pl.DataFrame({"year": [1989, 1990, 2008, 2009, 2015, 2016, 2022]}).with_columns(
        ds._per().alias("p")
    )
    assert d["p"].to_list() == [
        None,
        "1990–99",
        "2000–08",
        "2009–15",
        "2009–15",
        "2016–22",
        "2016–22",
    ]


def test_density_effect_recovers_a_shift_at_fixed_loudness():
    rng = np.random.default_rng(0)
    n = 40_000
    year = rng.integers(1990, 2023, n)
    lufs = rng.uniform(-20, -6, n)
    base = 0.1 + 0.01 * (lufs + 20)
    cols = {c: base + rng.normal(0, 0.02, n) for c in ds.DESC}
    cols["flatness_db"] = cols["flatness_db"] + 0.02 * (year >= 2016)  # planted +0.02
    rg = [f"g{i // 5}" for i in range(n)]
    genre = rng.choice(["rock", "pop"], n)
    u = pl.DataFrame({"year": year, "lufs": lufs, "genre": genre, "genre_source": "rg",
                      "release_group_mbid": rg, **cols})  # fmt: skip
    _, eff = ds.density(u, frac=1.0)
    assert eff["flatness_db"]["2016–22"]["est"] == pytest.approx(0.02, abs=0.003)
    assert abs(eff["average_loudness"]["2016–22"]["est"]) < 0.003


@pytest.mark.skipif(not ds.SUMMARY.exists(), reason="run `make models` first")
def test_pinned():
    s = json.loads(ds.SUMMARY.read_text())
    assert s["n_units"] == 2_604_546
    assert min(s["coverage"].values()) > 0.99
    e = s["density_effects"]
    # denser in timbre, not dynamics: flatter spectra at fixed loudness, dynamics unchanged
    assert e["flatness_db"]["2016–22"]["est"] - 1.96 * e["flatness_db"]["2016–22"]["se"] > 0
    assert (
        abs(e["average_loudness"]["2016–22"]["est"])
        < 2 * e["average_loudness"]["2016–22"]["se"] + 0.002
    )
    # classical's post-2016 rise is not significant within record labels
    c = s["controls"]["classical"]
    assert c["unadjusted"]["lo"] > 0 and c["label_fe"]["lo"] < 0
