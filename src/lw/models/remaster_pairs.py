# ruff: noqa: E501  (SQL strings, table rows)
"""P16: remaster pairs. Is a reissue louder than the original, and has that gap shrunk?

**Pairs.** For each recording, the *original* is its first appearance on a non-reissue release
(``first_appearance and not is_reissue``); its est. LUFS / LRA is the median over the original
release units of that release group. Each later release (release year >= original + 2) of the
same recording becomes a pair. Both sides must be **lossless** (codec effects cancel) and
**tier A/B matched** (a tier-C unit has no release tag, so its edition is unknown). Kinds:

* ``remaster``  same release group, reissue flagged by keyword (remaster, anniversary,
                reissue, legacy, expanded) or 'remaster' in the release name / comment: the
                **main sample**;
* ``reissue``   same release group, other reissues (represses, country / label editions, many
                with the original master);
* ``later``     a later appearance on another release group (best-ofs, box sets).

Delta = reissue - original (positive = the reissue is louder / wider).

**Noise.** Taggers pick a release by track list, not audio, so an "original" file can hold a
remaster and vice versa (P08, P11). That mixes zero and negative deltas into every cell and
attenuates the gap; it changes the *trend* only if mis-tagging rates change over time.

**Models.**

* track level (brief's spec): MixedLM delta ~ C(reissue period) + C(original decade), random
  intercept per original album with a variance component per recording;
* album level: per (original album, reissue release) the median delta over its tracks, then
  MixedLM with a random intercept per original album (albums are remastered more than once);
* by reissue year: album-pair mean delta for pre-1990 and 1990s originals, with a cluster
  bootstrap (original album) CI.

The question "has the gap shrunk since 2015?" is the 2015-22 minus 2005-14 period contrast,
holding the original's decade fixed. No causal claim (brief §5).

Outputs ``data/processed/p16_pairs.parquet`` (track pairs), ``p16_album_pairs.parquet``,
``p16_by_year.parquet``, ``p16_summary.json``.

    uv run python -m lw.models.remaster_pairs
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
RG = ROOT / "data/interim/mb/release_group.parquet"
PAIRS = ROOT / "data/processed/p16_pairs.parquet"
ALBUMS = ROOT / "data/processed/p16_album_pairs.parquet"
BY_YEAR = ROOT / "data/processed/p16_by_year.parquet"
SUMMARY = ROOT / "data/processed/p16_summary.json"
REPS = 1000
SEED = 20261107
PERIODS = [(0, 1999, "before 2000"), (2000, 2004, "2000–04"), (2005, 2009, "2005–09"),
           (2010, 2014, "2010–14"), (2015, 2022, "2015–22")]  # fmt: skip
DECADES = [(0, 1969, "pre-1970"), (1970, 1979, "1970s"), (1980, 1989, "1980s"),
           (1990, 1999, "1990s"), (2000, 9999, "2000s+")]  # fmt: skip
REMASTER_RE = "remaster"


def _period(col: str, cuts) -> pl.Expr:
    e = None
    for lo, hi, lab in cuts:
        c = pl.col(col).is_between(lo, hi)
        e = pl.when(c).then(pl.lit(lab)) if e is None else e.when(c).then(pl.lit(lab))
    return e.otherwise(None)


ANALOG = "vinyl|cassette|reel|shellac|8-track|acetate|wax cylinder|unknown|dcc|minidisc"


def build_pairs(con) -> pl.DataFrame:
    """Track pairs (recording, original master, later release), digital releases only."""
    con.execute(f"""create or replace temp table u as
        select recording_mbid, release_mbid, release_group_mbid as rg, year, rg_first_year, rec_first_year,
               lufs, greatest(lra, 0) as lra, match_tier = 'A' as tier_a, genre, n_sub, is_reissue,
               is_compilation, first_appearance, release_name, release_comment,
               (reissue_keyword or regexp_matches(lower(coalesce(release_comment, '') || ' ' || coalesce(release_name, '')), '{REMASTER_RE}')) as labelled
        from read_parquet('{T}')
        where match_tier in ('A', 'B') and loudness_source = 'lossless' and year <= 2022
          and len(formats) > 0
          and not list_bool_or(list_transform(formats, lambda x: regexp_matches(lower(x), '{ANALOG}')))""")
    # the recording's original album: a non-compilation release group first released by
    # the recording's first year + 1 (earliest; ties -> most units)
    con.execute("""create or replace temp table orig_rg as
        select recording_mbid, rg as orig_rg, rg_first_year from u
        where not is_compilation and rg_first_year <= coalesce(rec_first_year, rg_first_year) + 1
        group by recording_mbid, rg, rg_first_year
        qualify row_number() over (partition by recording_mbid order by rg_first_year, count(*) desc, rg) = 1""")
    # original master = earliest digital, non-remaster issue in that release group (+1 year)
    con.execute("""create or replace temp table orig as
        with c as (select u.*, o.orig_rg, min(u.year) over (partition by u.recording_mbid) as y0
                   from u join orig_rg o on o.recording_mbid = u.recording_mbid and o.orig_rg = u.rg
                   where not u.labelled)
        select recording_mbid, orig_rg, min(year) as orig_year, any_value(rg_first_year) as rg_first_year,
               median(lufs) as orig_lufs, median(lra) as orig_lra, count(*) as n_orig,
               bool_and(tier_a) as orig_tier_a, min(genre) as genre, sum(n_sub) as orig_subs
        from c where year <= y0 + 1 group by 1, 2""")
    df = con.sql("""select o.*, (o.orig_year > o.rg_first_year + 1) as orig_first_cd,
            u.release_mbid as re_release, u.rg as re_rg, u.year as re_year, u.lufs as re_lufs,
            u.lra as re_lra, u.tier_a as re_tier_a, u.release_name, u.release_comment,
            case when u.rg = o.orig_rg and u.labelled then 'remaster'
                 when u.rg = o.orig_rg then 'reissue'
                 when not u.first_appearance then 'later' end as kind
        from orig o join u using (recording_mbid)
        where u.year >= o.orig_year + 2""").pl()
    df = df.filter(pl.col("kind").is_not_null()).with_columns(
        (pl.col("re_lufs") - pl.col("orig_lufs")).alias("d_lufs"),
        (pl.col("re_lra") - pl.col("orig_lra")).alias("d_lra"),
        _period("re_year", PERIODS).alias("re_period"),
        _period("orig_year", DECADES).alias("orig_decade"),
    )
    # fixed row order: album_pairs takes first() per album, and DuckDB's order is arbitrary
    return df.with_columns((pl.col("d_lufs").abs() < 0.05).alias("identical")).sort(
        "orig_rg", "re_release", "recording_mbid"
    )


def album_pairs(pairs: pl.DataFrame) -> pl.DataFrame:
    return (
        pairs.group_by(["kind", "orig_rg", "re_release"], maintain_order=True)
        .agg(
            pl.len().alias("n_tracks"),
            pl.col("orig_year").min(),
            pl.col("re_year").first(),
            pl.col("d_lufs").median(),
            pl.col("d_lra").median(),
            pl.col("orig_lufs").median(),
            pl.col("re_lufs").median(),
            pl.col("identical").mean().alias("share_identical"),
            pl.col("genre").first(),
            pl.col("orig_subs").sum(),
            (pl.col("orig_tier_a") & pl.col("re_tier_a")).all().alias("tier_a"),
            pl.col("release_comment").first(),
            pl.col("orig_first_cd").first(),
        )
        .with_columns(
            _period("re_year", PERIODS).alias("re_period"),
            _period("orig_year", DECADES).alias("orig_decade"),
        )
    )


def mixed(df: pl.DataFrame, y: str, groups: str, vc: str | None = None) -> dict:
    """MixedLM y ~ C(re_period) + C(orig_decade); random intercept per ``groups`` (plus a
    variance component per ``vc``). Returns period effects (ref 2010–14) and the contrast
    2015–22 minus 2005–14 (mean of 2005–09 and 2010–14)."""
    import statsmodels.formula.api as smf

    d = (
        df.select(y, "re_period", "orig_decade", groups, *([vc] if vc else []))
        .drop_nulls()
        .to_pandas()
    )
    m = smf.mixedlm(f"{y} ~ C(re_period, Treatment('2010–14')) + C(orig_decade, Treatment('1980s'))",
                    d, groups=d[groups], re_formula="1", vc_formula={vc: f"0 + C({vc})"} if vc else None)  # fmt: skip
    r = m.fit(reml=True, method=["lbfgs"])
    names = list(r.params.index)
    p, V = np.asarray(r.params), np.asarray(r.cov_params())
    k = {lab: names.index(f"C(re_period, Treatment('2010–14'))[T.{lab}]")
         for _, _, lab in PERIODS if lab != "2010–14"}  # fmt: skip

    def contrast(w: dict) -> tuple[float, float]:
        g = np.zeros(len(p))
        for lab, v in w.items():
            if lab in k:
                g[k[lab]] += v
        return float(g @ p), float(np.sqrt(g @ V @ g))

    eff = {lab: contrast({lab: 1.0}) for _, _, lab in PERIODS}
    est, se = contrast({"2015–22": 1.0, "2005–09": -0.5})  # minus mean(2005–09, 2010–14 = 0)
    return {"n": len(d), "n_groups": int(d[groups].nunique()),
            "period_vs_2010_14": {lab: {"est": e, "se": s} for lab, (e, s) in eff.items()},
            "post2015_vs_2005_14": {"est": est, "se": se, "lo": est - 1.96 * se, "hi": est + 1.96 * se},
            "re_sd": float(np.sqrt(r.cov_re.iloc[0, 0])), "resid_sd": float(np.sqrt(r.scale)),
            "vc_sd": float(np.sqrt(r.vcomp[0])) if vc else None,
            "converged": bool(r.converged)}  # fmt: skip


def segmented_mixed(
    albums: pl.DataFrame,
    y: str = "d_lufs",
    form: str = "bend",
    b: int = 2016,
    k: int = 2007,
    lo: int = 2000,
) -> dict:
    """Album-pair delta on reissue year, P13 forms, original-decade FE, random intercept per
    original album: straight (lo-2022) or bend (hinge at k) plus level / slope change at b.
    Returns the mean 2016-22 gap (c + 3 d) and the joint Wald p of the two b-terms."""
    import statsmodels.formula.api as smf

    d = (
        albums.filter(pl.col("re_year").is_between(lo, 2022))
        .with_columns(
            (pl.col("re_year") - b).cast(pl.Float64).alias("s"),
            (pl.col("re_year") >= b).cast(pl.Float64).alias("post"),
            (pl.col("re_year") - k).clip(0).cast(pl.Float64).alias("hinge"),
        )
        .with_columns((pl.col("s") * pl.col("post")).alias("spost"))
        .to_pandas()
    )
    f = f"{y} ~ s + post + spost + C(orig_decade)" + (" + hinge" if form == "bend" else "")
    r = smf.mixedlm(f, d, groups=d["orig_rg"]).fit(reml=True, method=["lbfgs"])
    names = list(r.params.index)
    p, V = np.asarray(r.params), np.asarray(r.cov_params())
    g = np.zeros(len(p))
    g[names.index("post")], g[names.index("spost")] = 1.0, 3.0
    R = np.zeros((2, len(p)))
    R[0, names.index("post")], R[1, names.index("spost")] = 1, 1
    w = r.wald_test(R, scalar=True)
    est, se = float(g @ p), float(np.sqrt(g @ V @ g))
    return {"form": form, "n": len(d), "gap": est, "gap_se": se, "lo": est - 1.96 * se, "hi": est + 1.96 * se,
            "p_joint": float(w.pvalue), "pre_slope": float(r.params["s"]),
            "hinge_slope": float(r.params["hinge"]) if form == "bend" else None}  # fmt: skip


def by_year(albums: pl.DataFrame, reps: int = REPS, seed: int = SEED) -> pl.DataFrame:
    """Mean album-pair delta by reissue year and original-era group, cluster bootstrap CI."""
    rng = np.random.default_rng(seed)
    a = albums.filter((pl.col("kind") == "remaster") & pl.col("re_year").is_between(1990, 2022)).with_columns(
        pl.when(pl.col("orig_year") < 1990).then(pl.lit("originals before 1990"))
        .when(pl.col("orig_year") < 2000).then(pl.lit("1990s originals")).otherwise(None).alias("grp")
    ).filter(pl.col("grp").is_not_null())  # fmt: skip
    rows = []
    for (grp,), g in a.sort("grp", "orig_rg", "re_release").group_by(["grp"], maintain_order=True):
        cl = (g["orig_rg"].rank("dense") - 1).cast(pl.Int64).to_numpy()
        k = int(cl.max()) + 1
        yr = g["re_year"].to_numpy()
        for metric in ("d_lufs", "d_lra"):
            v = g[metric].to_numpy()
            W = rng.poisson(1.0, (reps, k))[:, cl].astype(float)
            for y in np.unique(yr):
                m = yr == y
                if m.sum() < 5:
                    continue
                w = W[:, m]
                bs = (w * v[m]).sum(1) / np.maximum(w.sum(1), 1e-9)
                rows.append({"grp": grp, "metric": metric, "year": int(y), "n_albums": int(m.sum()),
                             "n_orig_albums": int(len(np.unique(cl[m]))), "mean": float(v[m].mean()),
                             "median": float(np.median(v[m])),
                             "lo": float(np.quantile(bs, 0.025)), "hi": float(np.quantile(bs, 0.975))})  # fmt: skip
    return pl.DataFrame(rows).sort("grp", "metric", "year")


def artist_names(con, rgs: list[str]) -> dict[str, str]:
    """Credited artist name per release group (``release_group.artist_credit`` holds the name)."""
    d = pl.read_parquet(RG, columns=["release_group_mbid", "artist_credit"]).filter(
        pl.col("release_group_mbid").is_in(rgs)
    )
    return dict(zip(d["release_group_mbid"], d["artist_credit"], strict=True))


def famous(
    albums: pl.DataFrame, pairs: pl.DataFrame, con, k: int = 20, min_tracks: int = 6
) -> pl.DataFrame:
    """~k widely submitted albums with a labelled remaster: one remaster per album (the one
    with the most paired tracks; ties -> later reissue), tier A on both sides, one album per
    artist. 'Widely submitted' = most AcousticBrainz submissions of the original tracks."""
    a = albums.filter((pl.col("kind") == "remaster") & pl.col("tier_a") & (pl.col("n_tracks") >= min_tracks)
                      & (pl.col("orig_year") < 2000))  # fmt: skip
    a = (
        a.sort(["n_tracks", "re_year", "re_release"], descending=True)
        .group_by("orig_rg", maintain_order=True)
        .first()
    )
    a = a.sort(["orig_subs", "orig_rg"], descending=[True, False]).head(200)
    names = artist_names(con, a["orig_rg"].to_list())
    rg = pl.read_parquet(RG, columns=["release_group_mbid", "name"])
    a = a.join(rg, left_on="orig_rg", right_on="release_group_mbid", how="left").with_columns(
        pl.col("orig_rg").replace_strict(names, default=None).alias("artist")
    )
    a = a.filter(pl.col("artist").is_not_null() & ~pl.col("artist").is_in(["Various Artists"]))
    a = a.group_by("artist", maintain_order=True).first().head(k)
    return a.select("artist", pl.col("name").alias("album"), "orig_year", "re_year", "n_tracks", "orig_lufs",
                    "re_lufs", "d_lufs", "d_lra", "release_comment", "orig_subs", "orig_rg", "re_release")  # fmt: skip


def main() -> None:
    t0 = time.time()
    con = duckdb.connect()
    con.execute("set threads = 4")
    pairs = build_pairs(con)
    pairs.write_parquet(PAIRS)
    albums = album_pairs(pairs)
    albums.write_parquet(ALBUMS)
    print(
        f"pairs {pairs.height:,} / album pairs {albums.height:,} ({time.time() - t0:.0f}s)",
        flush=True,
    )
    s: dict = {"counts": {}, "models": {}, "cells": {}}
    for kind in ("remaster", "reissue", "later"):
        p, a = pairs.filter(pl.col("kind") == kind), albums.filter(pl.col("kind") == kind)
        s["counts"][kind] = {"track_pairs": p.height, "recordings": p["recording_mbid"].n_unique(),
                             "album_pairs": a.height, "orig_albums": a["orig_rg"].n_unique(),
                             "median_d_lufs": float(p["d_lufs"].median()), "share_identical": float(p["identical"].mean()),
                             "album_median_d_lufs": float(a["d_lufs"].median())}  # fmt: skip
        for y in ("d_lufs", "d_lra"):
            s["models"][f"{kind}|album|{y}"] = mixed(a, y, "orig_rg")
            print(
                f"{kind} album {y}: post2015 vs 2005-14 {s['models'][f'{kind}|album|{y}']['post2015_vs_2005_14']}",
                flush=True,
            )
    rem = albums.filter(pl.col("kind") == "remaster")
    s["segmented"] = {}
    for y in ("d_lufs", "d_lra"):
        for form in ("bend", "straight"):
            s["segmented"][f"{y}|{form}"] = r = segmented_mixed(rem, y, form)
            print(
                f"segmented {y} {form}: gap {r['gap']:+.2f} [{r['lo']:+.2f}, {r['hi']:+.2f}] p_joint {r['p_joint']:.3f}",
                flush=True,
            )
    for y in ("d_lufs", "d_lra"):
        s["models"][f"remaster|track|{y}"] = mixed(
            pairs.filter(pl.col("kind") == "remaster"), y, "orig_rg", vc="recording_mbid"
        )
        print(
            f"remaster track {y}: {s['models'][f'remaster|track|{y}']['post2015_vs_2005_14']}",
            flush=True,
        )
    # descriptive cells: album-pair median delta, reissue period x original decade (remasters)
    c = (
        albums.filter(pl.col("kind") == "remaster")
        .group_by(["orig_decade", "re_period"])
        .agg(
            pl.len().alias("album_pairs"),
            pl.col("d_lufs").median(),
            pl.col("d_lra").median(),
            pl.col("share_identical").mean(),
        )
    )
    s["cells"] = c.sort("orig_decade", "re_period").to_dicts()
    by_year(albums).write_parquet(BY_YEAR)
    f = famous(albums, pairs, con)
    f.write_parquet(ROOT / "data/processed/p16_famous.parquet")
    s["famous"] = f.select(
        "artist", "album", "orig_year", "re_year", "n_tracks", "d_lufs"
    ).to_dicts()
    SUMMARY.write_text(json.dumps(s, indent=1, default=float))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
