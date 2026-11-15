# ruff: noqa: E501  (SQL strings, spec table)
"""P19: robustness of the post-2015 break across samples, weights and model forms.

Every **spec** is a sample (a filter on ``tracks.parquet``) plus optional unit weights. For
each spec the yearly (weighted) median est. LUFS is computed, 1980-2022, and the P13 models
are fitted to it:

* ``straight``  the brief's literal test: segmented regression against a straight pre-trend,
                break B = 2015 or 2016, window 2000-2022 or 2005-2022 (``its.segmented``);
* ``bend``      bend-first: a continuous hinge at 2007 (the end of the rise, P13/P15) plus the
                level/slope change at B, window 2000-2022 (``its.two_break``); joint HAC Wald
                p of the two B-terms.

The estimate shown is the **mean post-period gap** (level + slope × mean(t − B)) against the
fitted counterfactual, with HAC (Newey-West, 2 lags) SEs, as in P13. CLAUDE.md "Break
framing": both forms are always reported side by side.

Specs (CLAUDE.md decisions; "headline" = ``in_headline``):

* sample definition: headline; previous headline ``in_main_lossless`` (no first-appearance
  rule); all codecs excluding <= 160 kbps lossy (dashed line); all codecs incl. <= 160 kbps;
  every submission lossless;
* weighting (P12 rules): release group capped at 30 units; every release group weighted
  equally (the "average album", a different estimand);
* matching: tier A only; no compilations; studio originals only (no compilation, live,
  soundtrack, remix, DJ-mix, deluxe);
* measurement: drop units whose submissions' replay gain spans > 1 dB (P18: other masters
  behind shared recording IDs; ``lufs_range`` > 1.042 LU); drop ``inconsistent`` (IQR) units;
  one unit per recording (earliest release, then most submissions);
* genre: tag-sourced genres only (no rosamerica fallback); reweighted to the MusicBrainz
  release-group mix by year (A, ``genre_mix.weight_headline``); fixed genre mix (C, direct
  standardisation on the 2000-2014 headline mix: within-genre change only);
* contributor drift: submission-date cohorts by the unit's first dump part (0-9, 10-19,
  20-29; parts are in submission order).

Outputs ``data/processed/p19_specs.parquet`` (every fit), ``p19_yearly.parquet`` (yearly
series per spec, cluster-bootstrap CIs for the headline and the reweighted series) and
``p19_summary.json``. No causal claim.

    uv run python -m lw.models.robustness
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

from lw.models import its

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
GMIX = ROOT / "data/processed/genre_mix.parquet"
OUT = ROOT / "data/processed/p19_specs.parquet"
YEARLY = ROOT / "data/processed/p19_yearly.parquet"
SUMMARY = ROOT / "data/processed/p19_summary.json"
Y0, Y1 = 1980, 2022
HINGE = 2007
BREAKS = [2015, 2016]
RG_1DB = 1.042  # 1 dB of replay gain in est. LUFS (P03 slope)
FIXED_MIX = (2000, 2014)
B_BOOT = 300
# coverage rule: a year enters the fits only with >= MIN_N units; for the submission cohorts,
# which are right-censored (early submitters cannot hold releases from after their submission
# date), also >= MIN_SHARE of the cohort's mean 2000-2014 count. A fit needs >= MIN_POST
# post-break years.
MIN_N, MIN_SHARE, MIN_POST = 500, 0.25, 4
SEED = 20261114
BOOT_SPECS = [
    "rg_equal",
    "headline",
    "genre_mb_mix",
    "genre_fixed_mix",
    "rg_range_le_1db",
    "one_per_recording",
]

# name -> (group, label, filter on the loaded frame); weights are added in ``weights``
SPECS: dict[str, tuple[str, str, str]] = {
    "headline": ("baseline", "Headline sample", "in_headline"),
    "in_main_lossless": ("sample", "No first-appearance rule (pre-P12 headline)", "in_main_lossless"),
    "all_codec_ex160": ("sample", "All codecs, excl. ≤160 kbps lossy", "in_main and first_appearance and not low160"),
    "all_codec_ex192": ("sample", "All codecs, excl. ≤192 kbps lossy", "in_main and first_appearance and not low192"),
    "all_codec": ("sample", "All codecs, incl. ≤160 kbps lossy", "in_main and first_appearance"),
    "all_lossless": ("sample", "Every submission lossless", "in_headline and all_lossless"),
    "rg_cap30": ("weighting", "Release group capped at 30 units", "in_headline"),
    "rg_equal": ("weighting", "Every release group weighted equally", "in_headline"),
    "tier_a": ("matching", "Tier A matches only", "in_headline and match_tier = 'A'"),
    "no_compilation": ("matching", "No compilations", "in_headline and not is_compilation"),
    "studio_originals": ("matching", "Studio originals only", "in_headline and not (is_compilation or is_live or is_soundtrack or is_remix or is_djmix or is_deluxe)"),
    "rg_range_le_1db": ("measurement", "Submissions agree within 1 dB RG", "in_headline and not rg_gt1"),
    "not_inconsistent": ("measurement", "No high-IQR units", "in_headline and not inconsistent"),
    "one_per_recording": ("measurement", "One unit per recording", "in_headline and rec_first"),
    "genre_tags_only": ("genre", "Tag-sourced genres only", "in_headline and genre is not null and genre_source <> 'hl'"),
    "genre_mb_mix": ("genre", "Reweighted to MB genre mix (A)", "in_headline and genre is not null"),
    "genre_fixed_mix": ("genre", "Fixed 2000–14 genre mix (C)", "in_headline and genre is not null"),
    "cohort_0_9": ("cohort", "Submitted early (dump parts 0–9)", "in_headline and first_part between 0 and 9"),
    "cohort_10_19": ("cohort", "Submitted mid (parts 10–19)", "in_headline and first_part between 10 and 19"),
    "cohort_20_29": ("cohort", "Submitted late (parts 20–29)", "in_headline and first_part between 20 and 29"),
}  # fmt: skip


def load(con) -> pl.DataFrame:
    """Units in ``in_main`` or the headline, 1980-2022, with the flags the specs need."""
    return con.sql(f"""
        select year, lufs::double as lufs, genre, genre_source, match_tier, first_part,
          coalesce(in_headline, false) as in_headline, coalesce(in_main, false) as in_main,
          coalesce(in_main_lossless, false) as in_main_lossless,
          coalesce(first_appearance, false) as first_appearance,
          coalesce(all_lossless, false) as all_lossless, coalesce(inconsistent, false) as inconsistent,
          coalesce(is_compilation, false) as is_compilation, coalesce(is_live, false) as is_live,
          coalesce(is_soundtrack, false) as is_soundtrack, coalesce(is_remix, false) as is_remix,
          coalesce(is_djmix, false) as is_djmix, coalesce(is_deluxe, false) as is_deluxe,
          (loudness_source = 'lossy' and coalesce(bit_rate_lossy, 1e9) <= 160000) as low160,
          (loudness_source = 'lossy' and coalesce(bit_rate_lossy, 1e9) <= 192000) as low192,
          (n_sub >= 2 and coalesce(lufs_range, 0) > {RG_1DB}) as rg_gt1,
          coalesce(in_headline and row_number() over (
              partition by recording_mbid, in_headline order by year, n_sub desc, release_mbid) = 1,
            false) as rec_first,
          dense_rank() over (order by release_group_mbid) as cl
        from read_parquet('{T}')
        where (in_main or in_headline) and year between {Y0} and {Y1} and lufs is not null
    """).pl()  # fmt: skip


def weights(name: str, d: pl.DataFrame) -> pl.Series | None:
    """Unit weights for the reweighted specs (None = equal weights)."""
    if name in ("rg_cap30", "rg_equal"):
        n = d.select(pl.len().over("year", "cl"))["len"].cast(pl.Float64)
        return (30.0 / n).clip(upper_bound=1.0) if name == "rg_cap30" else 1.0 / n
    if name == "genre_mb_mix":
        g = pl.read_parquet(GMIX).select("year", "genre", w="weight_headline")
        return d.join(g, on=["year", "genre"], how="left", maintain_order="left")["w"].fill_null(
            0.0
        )
    if name == "genre_fixed_mix":
        # direct standardisation: weight_{y,g} = fixed share_g / share_{y,g}
        sh = (
            d.group_by("year", "genre")
            .len()
            .with_columns(s=pl.col("len") / pl.col("len").sum().over("year"))
        )
        fx = (d.filter(pl.col("year").is_between(*FIXED_MIX)).group_by("genre").len()
              .with_columns(f=pl.col("len") / pl.col("len").sum()).select("genre", "f"))  # fmt: skip
        w = sh.join(fx, on="genre", how="left").with_columns(
            w=pl.col("f").fill_null(0.0) / pl.col("s")
        )
        return d.join(w.select("year", "genre", "w"), on=["year", "genre"], how="left",
                      maintain_order="left")["w"]  # fmt: skip
    return None


def wmedian(x: np.ndarray, w: np.ndarray) -> float:
    """Weighted median of sorted x (lower median at exactly half, as in P12)."""
    cw = np.cumsum(w)
    return float(x[np.searchsorted(cw, cw[-1] / 2.0)])


def yearly(d: pl.DataFrame, w: pl.Series | None, boot: int = 0, seed: int = SEED) -> pl.DataFrame:
    d = d.select("year", "lufs", "cl").with_columns(w=w if w is not None else pl.lit(1.0))
    d = d.filter(pl.col("w") > 0)
    rng = np.random.default_rng(seed)
    rows = []
    for (y,), g in d.sort("year", "lufs").group_by(["year"], maintain_order=True):
        x, wt = g["lufs"].to_numpy(), g["w"].to_numpy()
        r = {"year": y, "n": len(x), "median": wmedian(x, wt),
             "n_eff": float(wt.sum() ** 2 / (wt**2).sum())}  # fmt: skip
        if boot:
            cl = g["cl"].rank("dense").cast(pl.Int64).to_numpy() - 1
            k = int(cl.max()) + 1
            b = np.array([wmedian(x, wt * rng.poisson(1.0, k)[cl]) for _ in range(boot)])
            r |= {"ci_lo": float(np.quantile(b, 0.025)), "ci_hi": float(np.quantile(b, 0.975))}
        rows.append(r)
    return pl.DataFrame(rows)


def covered(s: pl.DataFrame, cohort: bool) -> pl.DataFrame:
    base = s.filter(pl.col("year").is_between(2000, 2014))["n"].mean()
    return s.filter((pl.col("n") >= MIN_N) & ((pl.col("n") >= MIN_SHARE * base) | (not cohort)))


def fits(s: pl.DataFrame) -> list[dict]:
    out = []
    for b in BREAKS:
        if s.filter(pl.col("year") >= b).height < MIN_POST:
            continue
        for wname, (lo, hi) in its.WINDOWS.items():
            x = s.filter(pl.col("year").is_between(lo, hi)).sort("year")
            t, y = x["year"].to_numpy().astype(float), x["median"].to_numpy()
            out.append({"form": "straight", "window": wname, **its.segmented(t, y, b)})
        x = s.filter(pl.col("year").is_between(*its.WINDOWS["2000-2022"])).sort("year")
        t, y = x["year"].to_numpy().astype(float), x["median"].to_numpy()
        r = its.two_break(t, y, HINGE, b)
        out.append({"form": "bend", "window": "2000-2022",
                    **{k: r[k] for k in ["break", "n", "n_post", "level", "level_se", "slope",
                                         "slope_se", "gap", "gap_se", "ssr", "p_level",
                                         "p_slope", "p_joint", "hinge_slope"]}})  # fmt: skip
    return out


def run() -> dict:
    t0 = time.time()
    con = duckdb.connect()
    con.execute("set memory_limit='10GB'")
    d = load(con)
    print(f"loaded {d.height:,} units in {time.time() - t0:.0f}s")
    rows, series = [], []
    for name, (group, label, where) in SPECS.items():
        sub = d.filter(pl.sql_expr(where))
        w = weights(name, sub)
        s = yearly(sub, w, boot=B_BOOT if name in BOOT_SPECS else 0)
        series.append(s.with_columns(spec=pl.lit(name)))
        pre = covered(s, group == "cohort").filter(pl.col("year").is_between(2000, 2022))
        for f in fits(pre):
            rows.append({"spec": name, "group": group, "label": label,
                         "n_units": int(pre["n"].sum()), "min_year_n": int(pre["n"].min()),
                         "last_year": int(pre["year"].max()), **f})  # fmt: skip
        print(f"{name:20s} {int(pre['n'].sum()):>9,} units 2000-22  {time.time() - t0:.0f}s")
    res = pl.DataFrame(rows, infer_schema_length=None)
    res.write_parquet(OUT)
    ys = pl.concat(series, how="diagonal").select("spec", pl.exclude("spec"))
    ys.write_parquet(YEARLY)
    return summarise(res, ys)


def summarise(res: pl.DataFrame, ys: pl.DataFrame) -> dict:
    def stats(f: pl.DataFrame) -> dict:
        lo, hi = f["gap"] - 1.96 * f["gap_se"], f["gap"] + 1.96 * f["gap_se"]
        return {"n_estimates": f.height, "gap_median": float(f["gap"].median()),
                "gap_min": float(f["gap"].min()), "gap_max": float(f["gap"].max()),
                "share_negative": float((f["gap"] < 0).mean()),
                "share_ci_below_0": float((hi < 0).mean()), "share_ci_above_0": float((lo > 0).mean())}  # fmt: skip

    s: dict = {"hinge": HINGE, "breaks": BREAKS, "specs": {k: v[1] for k, v in SPECS.items()}}
    for form, window in [
        ("straight", "2000-2022"),
        ("straight", "2005-2022"),
        ("bend", "2000-2022"),
    ]:
        f = res.filter((pl.col("form") == form) & (pl.col("window") == window))
        s[f"{form}|{window}"] = stats(f)
        if form == "bend":
            s[f"{form}|{window}"]["share_p_joint_lt_05"] = float((f["p_joint"] < 0.05).mean())
    s["by_spec"] = {
        r["spec"] + f"|{r['form']}|{r['window']}|{r['break']}": {
            k: r[k]
            for k in [
                "gap",
                "gap_se",
                "p_level",
                "p_joint",
                "n_units",
                "min_year_n",
                "last_year",
                "n_post",
            ]
        }
        for r in res.iter_rows(named=True)
    }
    h = ys.filter(pl.col("spec") == "headline").select("year", h="median")
    for k in ["genre_mb_mix", "genre_fixed_mix"]:
        x = ys.filter(pl.col("spec") == k).join(h, on="year")
        s[f"{k}_minus_headline"] = {
            "1980s": float(x.filter(pl.col("year") < 1990).select((pl.col("median") - pl.col("h")).mean()).item()),
            "2000-14": float(x.filter(pl.col("year").is_between(2000, 2014)).select((pl.col("median") - pl.col("h")).mean()).item()),
            "2016-22": float(x.filter(pl.col("year") >= 2016).select((pl.col("median") - pl.col("h")).mean()).item()),
            "peak_year": int(x.sort("median", descending=True)["year"][0]),
            "min_n_eff": float(x["n_eff"].min()),
        }  # fmt: skip
    SUMMARY.write_text(json.dumps(s, indent=2, default=float))
    return s


def main() -> None:
    s = run()
    print(json.dumps({k: v for k, v in s.items() if k != "by_spec"}, indent=2, default=float))


if __name__ == "__main__":
    main()
