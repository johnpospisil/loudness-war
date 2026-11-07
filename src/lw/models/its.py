# ruff: noqa: E501  (SQL strings, table rows)
"""P13: interrupted time series (segmented regression) for the 2015/16 break.

Model on a yearly series y_t (t = release year, B = break year, post = t >= B)::

    y_t = a + b (t - B) + c post_t + d (t - B) post_t + e_t

``c`` is the level change at B against the pre-trend, ``d`` the slope change; the pre-trend
projection a + b (t - B) is the counterfactual, and the mean post-period gap is
c + d * mean(t - B | post). Standard errors are Newey-West (HAC, 2 lags, small-sample
correction; n is about 23 years).

Variants:

* **yearly medians** (``p12_yearly.parquet``) for the headline and comparison series; window
  2000-2022 (the brief's "2000-2014 trend") and 2005-2022 (pre-period starting on the plateau);
* **track level**: OLS of est. LUFS on the same terms plus genre fixed effects, SEs clustered by
  release group (means, not medians; tags-sourced genres only);
* **year fixed effects, two step**: year effects from est. LUFS ~ C(year) + C(genre) (cluster SEs),
  then the segmented model on them, weighted by 1 / SE^2, HAC SEs;
* **break-year sensitivity** 2013-2017, **placebo breaks** 1995-2010 with the same window shape
  (15 pre-years, up to 7 post-years, truncated at 2014 so no placebo window reaches the era);
* **data-driven break search**: for every candidate year 2004-2019 inside 2000-2022, the SSR
  of the segmented model (and of a continuous hinge, slope change only); the profile minimum
  is the estimated break and the set of years within 3.84 of the minimum deviance
  (n log SSR) an approximate 95% set.

Outputs ``data/processed/p13_its.parquet`` (every fit, tidy) and ``p13_its_summary.json``.
No causal claim: a break shows timing, not cause (brief §5).

    uv run python -m lw.models.its
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[3]
YEARLY = ROOT / "data/processed/p12_yearly.parquet"
T = ROOT / "data/processed/tracks.parquet"
OUT = ROOT / "data/processed/p13_its.parquet"
SUMMARY = ROOT / "data/processed/p13_its_summary.json"
WINDOWS = {"2000-2022": (2000, 2022), "2005-2022": (2005, 2022)}
BREAKS = [2013, 2014, 2015, 2016, 2017]
PLACEBOS = list(range(1995, 2011))
HAC = {"maxlags": 2, "use_correction": True}
SCAN = (2004, 2019)


def design(t: np.ndarray, b: int, hinge_only: bool = False) -> np.ndarray:
    s = t - b
    post = (t >= b).astype(float)
    cols = [np.ones_like(s, dtype=float), s] + ([] if hinge_only else [post]) + [s * post]
    return np.column_stack(cols)


def segmented(t: np.ndarray, y: np.ndarray, b: int, w: np.ndarray | None = None) -> dict:
    """Fit the segmented model; return level/slope change with HAC SEs and the post-period gap."""
    X = design(t, b)
    m = (sm.WLS(y, X, weights=w) if w is not None else sm.OLS(y, X)).fit(
        cov_type="HAC", cov_kwds=HAC
    )
    p = np.asarray(m.params)
    V = np.asarray(m.cov_params())
    post = t >= b
    g = np.array([0, 0, 1, float(np.mean(t[post] - b))])  # mean gap over the post years
    gap, gap_se = float(g @ p), float(np.sqrt(g @ V @ g))
    se = np.sqrt(np.diag(V))
    return {"break": b, "n": len(t), "n_post": int(post.sum()),
            "pre_slope": p[1], "pre_slope_se": se[1],
            "level": p[2], "level_se": se[2], "slope": p[3], "slope_se": se[3],
            "gap": gap, "gap_se": gap_se, "ssr": float(m.ssr),
            "p_level": float(m.pvalues[2]), "p_slope": float(m.pvalues[3])}  # fmt: skip


def _series(d: pl.DataFrame, sample: str, metric: str, lo: int, hi: int):
    s = d.filter((pl.col("sample") == sample) & (pl.col("metric") == metric)
                 & pl.col("year").is_between(lo, hi)).sort("year")  # fmt: skip
    return s["year"].to_numpy().astype(float), s["median"].to_numpy(), s


def yearly_fits(d: pl.DataFrame) -> list[dict]:
    rows = []
    series = [("headline", "lufs"), ("headline", "lra"), ("all_codec_ex160", "lufs"),
              ("headline_low_sil", "lufs"), ("headline_low_sil", "lra"),
              ("lossless_all_units", "lufs")]  # fmt: skip
    for sample, metric in series:
        for wname, (lo, hi) in WINDOWS.items():
            t, y, _ = _series(d, sample, metric, lo, hi)
            for b in BREAKS:
                rows.append({"kind": "main", "model": "yearly_median", "sample": sample,
                             "metric": metric, "window": wname, **segmented(t, y, b)})  # fmt: skip
        # placebo breaks: 15 pre-years, post truncated at 2014
        for b in PLACEBOS:
            t, y, _ = _series(d, sample, metric, b - 15, min(b + 7, 2014))
            if (t >= b).sum() >= 4:
                rows.append({"kind": "placebo", "model": "yearly_median", "sample": sample,
                             "metric": metric, "window": f"{b - 15}-{min(b + 7, 2014)}",
                             **segmented(t, y, b)})  # fmt: skip
    return rows


def two_break(t: np.ndarray, y: np.ndarray, k: int, b: int) -> dict:
    """Continuous hinge at k (the end of the loudness rise) plus level/slope change at b.

    Tests whether the era break b adds anything once the earlier bend is allowed for: joint HAC
    Wald test of the two b-terms."""
    hk = np.clip(t - k, 0, None)
    X = np.column_stack([np.ones_like(t), t - b, hk, (t >= b).astype(float), (t - b) * (t >= b)])
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds=HAC)
    p, V = np.asarray(m.params), np.asarray(m.cov_params())
    post = t >= b
    g = np.array([0, 0, 0, 1, float(np.mean(t[post] - b))])
    w = m.wald_test(np.eye(5)[3:], scalar=True)
    se = np.sqrt(np.diag(V))
    return {"hinge_year": k, "break": b, "n": len(t), "n_post": int(post.sum()),
            "pre_slope": p[1], "pre_slope_se": se[1], "hinge_slope": p[2], "hinge_slope_se": se[2],
            "level": p[3], "level_se": se[3], "slope": p[4], "slope_se": se[4],
            "gap": float(g @ p), "gap_se": float(np.sqrt(g @ V @ g)), "ssr": float(m.ssr),
            "p_level": float(m.pvalues[3]), "p_slope": float(m.pvalues[4]),
            "p_joint": float(w.pvalue)}  # fmt: skip


def scan(d: pl.DataFrame, sample: str = "headline", metric: str = "lufs") -> list[dict]:
    t, y, _ = _series(d, sample, metric, *WINDOWS["2000-2022"])
    n = len(t)
    ssr0 = float(sm.OLS(y, np.column_stack([np.ones(n), t - t.mean()])).fit().ssr)
    rows = []
    for b in range(SCAN[0], SCAN[1] + 1):
        for form, hinge in [("level+slope", False), ("hinge", True)]:
            X = design(t, b, hinge_only=hinge)
            ssr = float(sm.OLS(y, X).fit().ssr)
            k = X.shape[1] - 2
            f = ((ssr0 - ssr) / k) / (ssr / (n - X.shape[1]))
            rows.append({"sample": sample, "metric": metric, "form": form, "break": b, "ssr": ssr,
                         "deviance": n * np.log(ssr / n), "F": f, "n": n,
                         "bic": n * np.log(ssr / n) + (X.shape[1] + 1) * np.log(n)})  # fmt: skip
    return rows


def track_level(con, b: int, lo: int = 2000, hi: int = 2022) -> list[dict]:
    """Track-level segmented OLS with genre FE (cluster SE by release group), and the
    two-step year-FE version."""
    df = con.sql(f"""select year, lufs, genre, release_group_mbid from read_parquet('{T}')
        where in_headline and year between {lo} and {hi} and genre_source <> 'hl'
          and genre is not null""").pl()
    t = df["year"].to_numpy().astype(float)
    y = df["lufs"].to_numpy()
    G = df.select("genre").to_dummies(drop_first=True).to_numpy().astype(float)
    cl = (df["release_group_mbid"].fill_null("?").rank("dense")).to_numpy()
    X = np.column_stack([design(t, b), G])
    m = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": cl})
    p, V = np.asarray(m.params), np.asarray(m.cov_params())
    post = t >= b
    gv = np.zeros(len(p))
    gv[2], gv[3] = 1, float(np.mean(np.unique(t[post]) - b))
    out = [{"kind": "main", "model": "track_ols_genre_fe", "sample": "headline", "metric": "lufs",
            "window": f"{lo}-{hi}", "break": b, "n": len(y), "n_post": int(post.sum()),
            "pre_slope": p[1], "pre_slope_se": np.sqrt(V[1, 1]), "level": p[2],
            "level_se": np.sqrt(V[2, 2]), "slope": p[3], "slope_se": np.sqrt(V[3, 3]),
            "gap": float(gv @ p), "gap_se": float(np.sqrt(gv @ V @ gv)), "ssr": float(m.ssr),
            "p_level": float(m.pvalues[2]), "p_slope": float(m.pvalues[3])}]  # fmt: skip
    # two-step: year effects net of genre, then the segmented model on them
    years = np.arange(lo, hi + 1)
    Y = (t[:, None] == years[None, 1:]).astype(float)
    m2 = sm.OLS(y, np.column_stack([np.ones(len(y)), Y, G])).fit(
        cov_type="cluster", cov_kwds={"groups": cl}
    )
    fe = np.concatenate([[0.0], np.asarray(m2.params)[1 : len(years)]]) + m2.params[0]
    se = np.concatenate(
        [
            [np.sqrt(m2.cov_params()[0, 0])],
            np.sqrt(np.diag(np.asarray(m2.cov_params()))[1 : len(years)]),
        ]
    )
    r = segmented(years.astype(float), fe, b, w=1 / se**2)
    out.append({"kind": "main", "model": "year_fe_two_step", "sample": "headline", "metric": "lufs",
                "window": f"{lo}-{hi}", **r})  # fmt: skip
    return out, years, fe, se


def main() -> None:
    t0 = time.time()
    d = pl.read_parquet(YEARLY)
    rows = yearly_fits(d)
    con = duckdb.connect()
    con.execute("set memory_limit='8GB'")
    fe_rows = {}
    for b in [2015, 2016]:
        r, years, fe, se = track_level(con, b)
        rows += r
        fe_rows[b] = (years, fe, se)
    tb = []
    for sample in ["headline", "all_codec_ex160", "lossless_all_units", "headline_low_sil"]:
        t, y, _ = _series(d, sample, "lufs", *WINDOWS["2000-2022"])
        for k in range(2006, 2012):
            for b in [2015, 2016]:
                tb.append({"kind": "two_break", "model": "yearly_median", "sample": sample,
                           "metric": "lufs", "window": "2000-2022", **two_break(t, y, k, b)})  # fmt: skip
    rows += tb
    res = pl.DataFrame(rows, infer_schema_length=None)
    res.write_parquet(OUT)
    sc = pl.DataFrame(scan(d) + scan(d, "headline_low_sil", "lufs") + scan(d, "headline", "lra"))
    sc.write_parquet(OUT.with_name("p13_scan.parquet"))
    years, fe, se = fe_rows[2016]
    pl.DataFrame({"year": years, "fe": fe, "se": se}).write_parquet(
        OUT.with_name("p13_year_fe.parquet")
    )

    def pick(**k):
        f = res
        for a, v in k.items():
            f = f.filter(pl.col(a) == v)
        return f.row(0, named=True)

    s = {"seconds": round(time.time() - t0, 1), "main": {}}
    for b in [2015, 2016]:
        for model, sample, window in [("yearly_median", "headline", "2000-2022"),
                                      ("yearly_median", "headline", "2005-2022"),
                                      ("track_ols_genre_fe", "headline", "2000-2022"),
                                      ("year_fe_two_step", "headline", "2000-2022")]:  # fmt: skip
            r = pick(
                kind="main",
                model=model,
                sample=sample,
                metric="lufs",
                window=window,
                **{"break": b},
            )
            s["main"][f"{model}|{window}|{b}"] = {k: r[k] for k in ["level", "level_se", "slope", "slope_se", "gap", "gap_se", "pre_slope", "p_level", "p_slope", "n"]}  # fmt: skip
    pl_ = res.filter(
        (pl.col("kind") == "placebo")
        & (pl.col("sample") == "headline")
        & (pl.col("metric") == "lufs")
    )
    main16 = pick(
        kind="main",
        model="yearly_median",
        sample="headline",
        metric="lufs",
        window="2000-2022",
        **{"break": 2016},
    )
    s["placebo_headline_lufs"] = {
        "n": pl_.height, "gap_sd": float(pl_["gap"].std()), "gap_abs_median": float(pl_["gap"].abs().median()),
        "share_abs_gap_ge_main2016": float((pl_["gap"].abs() >= abs(main16["gap"])).mean()),
        "share_p_level_lt_05": float((pl_["p_level"] < 0.05).mean()),
    }  # fmt: skip
    for form in ["level+slope", "hinge"]:
        x = sc.filter(
            (pl.col("sample") == "headline")
            & (pl.col("metric") == "lufs")
            & (pl.col("form") == form)
        )
        best = x.sort("ssr").row(0, named=True)
        dev_min = x["deviance"].min()
        s[f"scan_headline_lufs_{form}"] = {"best_break": best["break"], "F": best["F"],
            "set95": x.filter(pl.col("deviance") <= dev_min + 3.84)["break"].to_list()}  # fmt: skip
    x = res.filter((pl.col("kind") == "two_break") & (pl.col("sample") == "headline"))
    s["two_break_headline_lufs"] = {
        f"hinge{r['hinge_year']}|{r['break']}": {k: r[k] for k in ["level", "level_se", "slope", "slope_se", "gap", "gap_se", "p_joint", "hinge_slope"]}
        for r in x.iter_rows(named=True)}  # fmt: skip
    SUMMARY.write_text(json.dumps(s, indent=2, default=float))
    print(json.dumps(s, indent=2, default=float))


if __name__ == "__main__":
    main()
