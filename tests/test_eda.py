"""P11: pinned EDA results (profile + album spot-check)."""

import json

import pytest

from lw import eda

pytestmark = pytest.mark.skipif(not eda.PROFILE.exists(), reason="run `make eda` first")


def test_spotcheck_expectation():
    s = json.loads(eda.PROFILE.read_text())["spotcheck"]
    assert s["found"] == s["listed"] == 54
    assert s["criticised_found"] == 20 and s["criticised_above_year_median"] == 20
    assert s["criticised_top_quartile"] == 14
    assert s["dynamic_found"] == 2 and s["dynamic_below_year_median"] == 2


def test_decade_medians_and_correlations():
    p = json.loads(eda.PROFILE.read_text())
    med = {d["decade"]: d["lufs"] for d in p["decades_lossless"]}
    assert med[1980] == pytest.approx(-15.76, abs=0.02)
    assert med[2010] == pytest.approx(-10.92, abs=0.02)
    c = p["corr_lossless"]
    assert c["lufs~lra"]["spearman"] == pytest.approx(-0.476, abs=0.005)
    assert c["lra~silence_rate_60db"]["spearman"] == pytest.approx(0.921, abs=0.005)
