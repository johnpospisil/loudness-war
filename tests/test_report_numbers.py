"""P21: the article's numbers file matches the pinned headline results."""

import json

import pytest

from lw.report import numbers


@pytest.mark.skipif(not numbers.OUT.exists(), reason="run `make report` first")
def test_article_numbers_pinned():
    n = json.loads(numbers.OUT.read_text())
    assert n["data"]["units_headline"] == 2_604_546
    assert n["hero"]["peak_year"] == 2009
    assert n["hero"]["m2016_22"] == pytest.approx(-10.81, abs=0.01)
    assert n["hero"]["m2005_09"] - n["hero"]["m1980s"] == pytest.approx(5.0, abs=0.1)
    assert n["robustness"]["straight"]["share_negative"] == 1.0
    assert abs(n["robustness"]["headline_bend"]["gap"]) < 0.15
    assert n["validation"]["proxy"]["lufs"]["n"] == 149
