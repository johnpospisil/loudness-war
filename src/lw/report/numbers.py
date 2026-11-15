# ruff: noqa: E501  (key paths)
"""P21: every number the article quotes, collected from ``data/processed/`` into one JSON.

The article (``report/index.qmd``) reads ``data/processed/article_numbers.json`` and never
hard-codes a result. Values are rounded only at display time in the article.

    uv run python -m lw.report.numbers
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from lw.normalisation import era_consolidated, era_start

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "data/processed"
OUT = P / "article_numbers.json"


def _j(name: str) -> dict:
    return json.loads((P / name).read_text())


def _period(s: pl.DataFrame, a: int, b: int, col: str = "median") -> float:
    return float(s.filter(pl.col("year").is_between(a, b))[col].mean())


def build() -> dict:
    y = pl.read_parquet(P / "p12_yearly.parquet")
    h = y.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs")).sort("year")
    lra = y.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lra")).sort("year")
    lra_ls = y.filter((pl.col("sample") == "headline_low_sil") & (pl.col("metric") == "lra")).sort(
        "year"
    )
    cmp_ = y.filter((pl.col("sample") == "all_codec_ex192") & (pl.col("metric") == "lufs")).sort(
        "year"
    )
    low = h.sort("median").row(0, named=True)
    peak = h.sort("median", descending=True).row(0, named=True)
    funnel = _j("tracks_funnel.json")["funnel"]
    its = _j("p13_its_summary.json")
    q = _j("p14_summary.json")
    g = _j("p15_summary.json")
    ge = pl.read_parquet(P / "p15_genre_effects.parquet")
    rp = _j("p16_summary.json")
    fam = pl.read_parquet(P / "p16_famous.parquet")
    d = _j("p17_summary.json")
    v = _j("p18_summary.json")
    rb = _j("p19_summary.json")
    rbs = pl.read_parquet(P / "p19_specs.parquet")
    r19 = pl.read_parquet(P / "p19_yearly.parquet")
    alb = r19.filter(pl.col("spec") == "rg_equal")
    cal = json.loads((ROOT / "data/reference/proxy_calibration.json").read_text())["models"]
    ap = pl.read_parquet(P / "p16_album_pairs.parquet").filter(
        (pl.col("kind") == "remaster") & (pl.col("re_year") >= 2000)
    )
    by_dec = {
        r["orig_decade"]: r["d_lufs"]
        for r in ap.group_by("orig_decade").agg(pl.col("d_lufs").median()).to_dicts()
    }
    import duckdb  # noqa: PLC0415

    lowbit = duckdb.sql(f"""select avg((bit_rate_lossy <= 160000)::int) filter (where year between 2015 and 2022),
            avg((bit_rate_lossy <= 160000)::int) filter (where year between 2000 and 2009)
        from read_parquet('{P / "tracks.parquet"}')
        where in_main and first_appearance and loudness_source = 'lossy'""").fetchall()[0]
    fits15 = g["fits"].values()

    def spec(name: str, form: str = "bend", b: int = 2016, window: str = "2000-2022") -> dict:
        r = rbs.filter((pl.col("spec") == name) & (pl.col("form") == form) & (pl.col("break") == b)
                       & (pl.col("window") == window)).row(0, named=True)  # fmt: skip
        return {"gap": r["gap"], "lo": r["gap"] - 1.96 * r["gap_se"], "hi": r["gap"] + 1.96 * r["gap_se"],
                "p_joint": r.get("p_joint")}  # fmt: skip

    def genre(fit: str, name: str) -> dict:
        r = ge.filter((pl.col("fit") == fit) & (pl.col("genre") == name)).row(0, named=True)
        return {k: r[k] for k in ["gap", "gap_lo", "gap_hi", "p_neg", "b1", "b2"]}

    gm = ge.filter(pl.col("fit") == "lufs_median|bend")
    n = {
        "data": {
            "submissions": funnel["submissions"], "units": funnel["units"], "units_main": funnel["units_main"],
            "units_headline": funnel["units_headline"], "years": [int(h["year"].min()), int(h["year"].max())],
            "n_rg_headline": int(h["n_rg"].sum()), "n_2022": int(h["n"][-1]), "n_rg_2022": int(h["n_rg"][-1]),
            "n_albums_app": json.loads((ROOT / "app/data/dist.json").read_text())["n_albums"],
            "ci_halfwidth_median": float(((h["ci_hi"] - h["ci_lo"]) / 2).median()),
        },
        "calibration": {k: {"const": cal[k]["coef"]["const"], "slope": list(cal[k]["coef"].values())[1],
                            "slope_se": list(cal[k]["se_cluster"].values())[1], "cv_rmse": cal[k]["cv_rmse"]}
                        for k in ["lufs_rg", "lra_dc"] if k in cal},
        "lossy_low160_share": {"2015_22": lowbit[0], "2000_09": lowbit[1]},
        "genre_diag": {"n_fits": len(g["fits"]), "max_rhat": max(f["max_rhat"] for f in fits15),
                       "divergences": sum(f["divergences"] for f in g["fits"].values())},
        "era": {"start": era_start(), "consolidated": era_consolidated()},
        "hero": {
            "low_year": low["year"], "low": low["median"], "peak_year": peak["year"], "peak": peak["median"],
            "rise": peak["median"] - low["median"],
            "m1980s": _period(h, 1980, 1989), "m2005_09": _period(h, 2005, 2009), "m2005_15": _period(h, 2005, 2015),
            "m2010_15": _period(h, 2010, 2015), "m2016_22": _period(h, 2016, 2022),
            "range_2009_22": [float(h.filter(pl.col("year") >= 2009)["median"].min()),
                              float(h.filter(pl.col("year") >= 2009)["median"].max())],
            "p90_2005_15": _period(h, 2005, 2015, "p90"), "p90_2016_22": _period(h, 2016, 2022, "p90"),
            "p10_2005_09": _period(h, 2005, 2009, "p10"), "p10_2016_22": _period(h, 2016, 2022, "p10"),
            "cmp_max_abs_diff": float((cmp_["median"] - h["median"]).abs().max()),
            "album_2005_15": _period(alb, 2005, 2015), "album_2016_22": _period(alb, 2016, 2022),
        },
        "lra": {
            "m1980s": _period(lra, 1980, 1989), "m2005_09": _period(lra, 2005, 2009),
            "m2010_15": _period(lra, 2010, 2015), "m2016_22": _period(lra, 2016, 2022),
            "ls_2005_09": _period(lra_ls, 2005, 2009), "ls_2016_22": _period(lra_ls, 2016, 2022),
        },
        "its": {
            "straight_2016": its["main"]["yearly_median|2000-2022|2016"],
            "straight_2005_2016": its["main"]["yearly_median|2005-2022|2016"],
            "bend_2016": its["two_break_headline_lufs"]["hinge2007|2016"],
            "p_joint_range": [min(r["p_joint"] for r in its["two_break_headline_lufs"].values()),
                              max(r["p_joint"] for r in its["two_break_headline_lufs"].values())],
            "scan_hinge": its["scan_headline_lufs_hinge"], "scan_ls": its["scan_headline_lufs_level+slope"],
        },
        "quantile": {
            "p90_straight": q["fits"]["headline|single|2000-2022|2016|0.9"],
            "p90_bend": q["fits"]["headline|bend|2000-2022|2016|k2007|0.9"],
            "hinge_p90": q["hinge_profile_best"]["headline"]["0.9"],
            "hinge_p95": q["hinge_profile_best"]["headline"]["0.95"],
            "hinge_p50": q["hinge_profile_best"]["headline"]["0.5"],
        },
        "genre": {
            "n_units": g["n_units_fit"], "n_genres": g["fits"]["lufs_median|bend"]["n_genres"],
            "median_bend": g["fits"]["lufs_median|bend"], "median_straight": g["fits"]["lufs_median|straight"],
            "p90_bend": g["fits"]["lufs_p90|bend"], "p90_straight": g["fits"]["lufs_p90|straight"],
            "lra_bend": g["fits"]["lra_median|bend"], "lra_straight": g["fits"]["lra_median|straight"],
            "loo": g["loo"], "metal": genre("lufs_median|bend", "metal"),
            "classical": genre("lufs_median|bend", "classical"),
            "electronic_p90": genre("lufs_p90|bend", "electronic"),
            "b1_range": [float(gm["b1"].min()), float(gm["b1"].max())],
            "b2_range": [float(gm["b2"].min()), float(gm["b2"].max())],
            "n_within_02": int((gm["gap"].abs() <= 0.2).sum()),
            "classical_controls": {k: d["controls"]["classical"][k] for k in ["unadjusted", "label_fe", "label_fe_silence"]},
        },
        "remaster": {
            "counts": rp["counts"]["remaster"], "album_median_by_decade": by_dec,
            "post2015_vs_2005_14": rp["models"]["remaster|album|d_lufs"]["post2015_vs_2005_14"],
            "lra_post2015_vs_2005_14": rp["models"]["remaster|album|d_lra"]["post2015_vs_2005_14"],
            "n_famous": fam.height, "n_famous_louder": int((fam["d_lufs"] > 0.5).sum()),
            "famous_top": fam.sort("d_lufs", descending=True).head(4).select("artist", "album", "re_year", "d_lufs").to_dicts(),
        },
        "descriptors": {
            "flatness": d["period_means"]["flatness_db"], "centroid": d["period_means"]["centroid_hz"],
            "crest": d["period_means"]["crest_db"],
            "flatness_sd_2016": d["density_effects"]["flatness_db"]["2016–22"]["est"] / d["density_effects"]["flatness_db"]["2016–22"]["sd"],
            "centroid_2016": d["density_effects"]["centroid_hz"]["2016–22"]["est"],
            "crest_sd_2016": d["density_effects"]["crest_db"]["2016–22"]["est"] / d["density_effects"]["crest_db"]["2016–22"]["sd"],
        },
        "validation": {
            "own": v["own"], "proxy": v["proxy_lossless"], "headline_unit": v["ab_vs_own"]["headline_unit"],
            "same_master_rg": v["ab_vs_own"]["same_master"]["replay_gain_same_extractor"],
            "enc": {k: e["d_lufs"]["mean"] for k, e in v["encoding"].items() if isinstance(e, dict) and "d_lufs" in e},
            "enc_lra_max": max(abs(e["d_lra"]["mean"]) for e in v["encoding"].values() if isinstance(e, dict) and "d_lra" in e),
            "dr": {"n_albums": v["drdb"]["n_albums"], "rho": v["drdb"]["est_lufs"]["spearman"],
                   "within": v["drdb"]["est_lufs"]["within_year_pearson"]},
        },
        "robustness": {
            "n_specs": rbs["spec"].n_unique(), "n_estimates": rbs.height,
            "straight": rb["straight|2000-2022"], "straight_2005": rb["straight|2005-2022"], "bend": rb["bend|2000-2022"],
            "headline_bend": spec("headline"), "album_bend": spec("rg_equal"),
            "mb_mix_bend": spec("genre_mb_mix"), "fixed_mix_bend": spec("genre_fixed_mix"),
            "late_cohort_bend": spec("cohort_20_29"), "ex192_bend": spec("all_codec_ex192"),
            "mb_mix_shift": rb["genre_mb_mix_minus_headline"]["2000-14"],
            "lossless_variants_bend_range": [
                float(rbs.filter((pl.col("form") == "bend") & ~pl.col("spec").str.starts_with("all_codec")
                                 & ~pl.col("spec").str.starts_with("cohort"))["gap"].min()),
                float(rbs.filter((pl.col("form") == "bend") & ~pl.col("spec").str.starts_with("all_codec")
                                 & ~pl.col("spec").str.starts_with("cohort"))["gap"].max())],  # fmt: skip
            "mde": 2.8 * float(its["two_break_headline_lufs"]["hinge2007|2016"]["gap_se"]),
        },
    }  # fmt: skip
    OUT.write_text(json.dumps(n, indent=1, default=float))
    return n


def main() -> None:
    n = build()
    print(f"wrote {OUT} ({len(json.dumps(n, default=float)):,} bytes)")


if __name__ == "__main__":
    main()
