# ruff: noqa: E501  (SQL strings, labels)
"""P17: other descriptors. Is music denser even if it isn't louder?

Descriptors are recomputed per (recording, release) unit as the **median over lossless
submissions only** (P09 took feature medians over all submissions, and lossy encoders low-pass
the signal, which moves centroid and flatness). Headline units (``in_headline``) only.

* ``dynamic_complexity``  Essentia, mean |loudness deviation| (dB); higher = more dynamic
* ``average_loudness``    Essentia, rescaled average loudness in [0, 1]; 1 = little dynamic
                          range (dense), 0 = large range
* ``crest_db``            **frame-level crest proxy**: 20 log10(max frame RMS / mean frame RMS).
                          AcousticBrainz stores **no sample peak**, so a true crest factor
                          (peak - loudness, PLR) is not available; this measures macro-dynamics
                          over ~46 ms frames, not transient peaks
* ``flatness_db``         mean Bark-band spectral flatness (Essentia FlatnessDB, 0-1); higher =
                          flatter, more noise-like spectrum (dense)
* ``centroid_hz``         mean spectral centroid (Hz); brightness
* ``spectral_complexity`` mean number of spectral peaks; textural density
* ``onset_rate``          onsets per second; rhythmic density
* ``silence``             share of frames below -60 dB

Analyses: yearly medians 1980-2022 (release-group cluster bootstrap CIs); genre x period
changes; density at fixed est. LUFS (period effects net of loudness bin and genre, OLS with
release-group cluster SEs on a seeded 25% unit sample); classical / "other" composition check
(P15 follow-up, user decision 2026-11-07). No causal claim (brief §5).

    uv run python -m lw.models.descriptors
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

from lw.models.yearly import weighted_median_boot

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
AB = ROOT / "data/interim/ab_matched.parquet"
TAGS = ROOT / "data/interim/mb/rg_tags.parquet"
UNITS = ROOT / "data/processed/p17_descriptors.parquet"
YEARLY = ROOT / "data/processed/p17_yearly.parquet"
GENRE = ROOT / "data/processed/p17_genre_change.parquet"
DENSITY = ROOT / "data/processed/p17_density.parquet"
COMPOSITION = ROOT / "data/processed/p17_composition.parquet"
SUMMARY = ROOT / "data/processed/p17_summary.json"
SEED = 20261107
REPS = 300
LOSSLESS = "(a.codec in ('flac', 'alac', 'ape', 'wavpack', 'tta') or a.codec like 'pcm%')"  # = dedupe.LOSSLESS_CODEC

DESC = {
    # name: (label, unit, "denser when")
    "dynamic_complexity": ("Dynamic complexity", "dB", "lower"),
    "average_loudness": ("Average loudness (Essentia)", "0–1", "higher"),
    "crest_db": ("Frame crest proxy (max / mean frame RMS)", "dB", "lower"),
    "flatness_db": ("Spectral flatness (Bark bands, Essentia FlatnessDB)", "0–1", "higher"),
    "centroid_hz": ("Spectral centroid", "Hz", None),
    "spectral_complexity": ("Spectral complexity", "peaks", "higher"),
    "onset_rate": ("Onset rate", "per s", "higher"),
    "silence": ("Near-silent frames (< −60 dB)", "share", None),
}
PERIODS = [
    (1990, 1999, "1990–99"),
    (2000, 2008, "2000–08"),
    (2009, 2015, "2009–15"),
    (2016, 2022, "2016–22"),
]


def unit_descriptors(con) -> None:
    """Lossless-only medians per headline unit -> UNITS."""
    con.execute(f"""create or replace temp table keys as
        select recording_mbid, release_mbid, year, release_group_mbid, genre, genre_source, lufs, lra,
               length_s, n_lossless from read_parquet('{T}') where in_headline""")
    con.execute(f"""copy (
        with s as (
            select a.recording_mbid_mb as recording_mbid, a.release_mbid,
                   a.dynamic_complexity, a.average_loudness,
                   20 * log10(a.spectral_rms_max / nullif(a.spectral_rms_mean, 0)) as crest_db,
                   a.barkbands_flatness_db as flatness_db, a.spectral_centroid as centroid_hz,
                   a.spectral_complexity, a.rhythm_onset_rate as onset_rate, a.silence_rate_60db as silence
            from read_parquet('{AB}') a semi join keys k
              on k.recording_mbid = a.recording_mbid_mb and k.release_mbid = a.release_mbid
            where {LOSSLESS})
        select k.*, {", ".join(f"median(s.{c})::float as {c}" for c in DESC)}
        from s join keys k using (recording_mbid, release_mbid)
        group by all) to '{UNITS}' (format parquet, compression zstd)""")


def yearly(units: pl.DataFrame, reps: int = REPS, seed: int = SEED) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for (y,), g in units.filter(pl.col("year").is_between(1980, 2022)).group_by(["year"]):
        cl = (g["release_group_mbid"].fill_null("?").rank("dense") - 1).cast(pl.Int64).to_numpy()
        for c in [*DESC, "lufs"]:
            v = g[c].to_numpy()
            ok = np.isfinite(v)
            o = np.argsort(v[ok])
            x, cc = v[ok][o], cl[ok][o]
            b = weighted_median_boot(x, cc, reps, rng)
            rows.append({"year": int(y), "desc": c, "n": int(ok.sum()), "median": float(np.median(x)),
                         "p25": float(np.quantile(x, 0.25)), "p75": float(np.quantile(x, 0.75)),
                         "lo": float(np.quantile(b, 0.025)), "hi": float(np.quantile(b, 0.975))})  # fmt: skip
    return pl.DataFrame(rows).sort("desc", "year")


def _per(col="year") -> pl.Expr:
    e = None
    for lo, hi, lab in PERIODS:
        c = pl.col(col).is_between(lo, hi)
        e = pl.when(c).then(pl.lit(lab)) if e is None else e.when(c).then(pl.lit(lab))
    return e.otherwise(None)


def genre_change(
    units: pl.DataFrame, a: str = "2009–15", b: str = "2016–22", reps: int = 200, seed: int = SEED
) -> pl.DataFrame:
    """Median change a -> b per genre x descriptor, in LU / native units and in SDs of the
    descriptor's 2000-2022 between-track spread; cluster-bootstrap CI."""
    rng = np.random.default_rng(seed)
    u = units.filter(pl.col("genre").is_not_null() & (pl.col("genre_source") != "hl")).with_columns(
        _per().alias("per")
    )
    sd = {
        c: float(units.filter(pl.col("year").is_between(2000, 2022))[c].drop_nans().std())
        for c in [*DESC, "lufs"]
    }
    rows = []
    for (g,), d in u.filter(pl.col("per").is_in([a, b])).group_by(["genre"]):
        for c in [*DESC, "lufs"]:
            med = {}
            boots = {}
            for p in (a, b):
                z = d.filter((pl.col("per") == p) & pl.col(c).is_finite()).sort(c)
                cl = (z["release_group_mbid"].rank("dense") - 1).cast(pl.Int64).to_numpy()
                med[p] = float(z[c].median())
                boots[p] = weighted_median_boot(z[c].to_numpy(), cl, reps, rng)
            diff = boots[b] - boots[a]
            rows.append({"genre": g, "desc": c, "change": med[b] - med[a], "lo": float(np.quantile(diff, 0.025)),
                         "hi": float(np.quantile(diff, 0.975)), "change_sd": (med[b] - med[a]) / sd[c], "sd": sd[c]})  # fmt: skip
    return pl.DataFrame(rows)


def density(units: pl.DataFrame, frac: float = 0.25, seed: int = SEED) -> tuple[pl.DataFrame, dict]:
    """(1) median descriptor by 1-LU est. LUFS bin x period; (2) period effects at fixed
    loudness bin and genre (OLS, cluster SE by release group) on a seeded unit sample."""
    import statsmodels.formula.api as smf

    u = units.filter(pl.col("year").is_between(1990, 2022)).with_columns(
        _per().alias("per"), pl.col("lufs").floor().clip(-24, -4).alias("lbin")
    )
    tab = (
        u.group_by(["per", "lbin"])
        .agg(pl.len().alias("n"), *[pl.col(c).median() for c in DESC])
        .filter(pl.col("n") >= 200)
    )
    s = u.filter(pl.col("genre").is_not_null() & (pl.col("genre_source") != "hl")).sample(
        fraction=frac, seed=seed
    )
    eff = {}
    for c in DESC:
        d = (
            s.select(c, "per", "lbin", "genre", "release_group_mbid")
            .drop_nulls()
            .filter(pl.col(c).is_finite())
            .to_pandas()
        )
        m = smf.ols(f"{c} ~ C(per, Treatment('2009–15')) + C(lbin) + C(genre)", d).fit(
            cov_type="cluster",
            cov_kwds={"groups": d["release_group_mbid"].astype("category").cat.codes},
        )
        sd = float(d[c].std())
        eff[c] = {lab: {"est": float(m.params.get(f"C(per, Treatment('2009–15'))[T.{lab}]", 0.0)),
                        "se": float(m.bse.get(f"C(per, Treatment('2009–15'))[T.{lab}]", 0.0)), "sd": sd}
                  for _, _, lab in PERIODS}  # fmt: skip
        eff[c]["n"] = len(d)
    return tab.sort("per", "lbin"), eff


# ------------------------------------------------------------ classical / other composition

SUBGROUPS = {
    "classical": [
        (
            "contemporary / crossover / screen",
            r"modern classical|contemporary classical|neo-?classical|minimalis|cinematic|ambient|crossover|soundtrack|score|vgm|video game|new age|electronic|post-rock|piano|stage & screen|epic",
        ),
        (
            "canonical repertoire",
            r"baroque|renaissance|medieval|romantic|opera|symphon|concerto|chamber|choral|sonata|oratorio|lied|mass|string quartet|early music|classical period|orchestral|keyboard",
        ),
    ],
    "other": [
        (
            "soundtrack / score / game",
            r"soundtrack|score|vgm|video game|stage & screen|musical|anime|film",
        ),
        (
            "world / latin / regional",
            r"world|latin|afro|brazil|bossa|samba|tango|flamenco|celtic|j-pop|k-pop|c-pop|mpb|cumbia|salsa|bollywood|turkish|arabic|african|greek|french|chanson|schlager|enka|indian",
        ),
        (
            "experimental / noise / ambient",
            r"experimental|noise|ambient|drone|avant|industrial|sound art|field recording",
        ),
        (
            "spoken / comedy / christmas / new age",
            r"spoken|comedy|audiobook|christmas|new age|meditation|children|holiday",
        ),
    ],
}


def composition(con, units: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Assign classical / other units to tag subgroups (first matching rule over the release
    group's positive-vote tags, most-voted first); compare 2009-15 vs 2016-22 median est.
    LUFS within subgroups and after reweighting 2016-22 to the 2009-15 subgroup mix."""
    out, summ = [], {}
    rng = np.random.default_rng(SEED)
    for genre, groups in SUBGROUPS.items():
        u = units.filter(
            (pl.col("genre") == genre)
            & (pl.col("genre_source") != "hl")
            & pl.col("year").is_between(2000, 2022)
        )
        con.register("rgs", u.select("release_group_mbid").unique().to_arrow())
        tags = con.sql(f"""select t.release_group_mbid, lower(t.tag) as tag, t.count
            from read_parquet('{TAGS}') t semi join rgs r using (release_group_mbid) where t.count > 0""").pl()
        assign = {}
        for (rg,), z in tags.sort("count", descending=True).group_by(
            ["release_group_mbid"], maintain_order=True
        ):
            joined = " | ".join(z["tag"].to_list())
            for lab, rx in groups:
                if pl.Series([joined]).str.contains(rx)[0]:
                    assign[rg] = lab
                    break
        u = u.with_columns(pl.col("release_group_mbid").replace_strict(assign, default="untagged / other tags").alias("sub"),
                           _per().alias("per"))  # fmt: skip
        out.append(u.group_by(["year", "sub"]).agg(pl.len().alias("n"), pl.col("lufs").median(), pl.col("length_s").median(),
                                                   pl.col("silence").median(), pl.col("average_loudness").median())
                   .with_columns(pl.lit(genre).alias("genre")))  # fmt: skip
        a, b = u.filter(pl.col("per") == "2009–15"), u.filter(pl.col("per") == "2016–22")
        sa = a.group_by("sub").len().with_columns((pl.col("len") / pl.col("len").sum()).alias("sa"))
        sb = b.group_by("sub").len().with_columns((pl.col("len") / pl.col("len").sum()).alias("sb"))
        w = (
            sa.join(sb, on="sub")
            .with_columns((pl.col("sa") / pl.col("sb")).alias("w"))
            .select("sub", "w")
        )
        bw = b.join(w, on="sub", how="left").with_columns(pl.col("w").fill_null(0.0))

        def wmed(x, wt):
            o = np.argsort(x)
            cw = np.cumsum(wt[o])
            return float(x[o][np.searchsorted(cw, cw[-1] / 2)])

        raw = float(b["lufs"].median()) - float(a["lufs"].median())
        rew = wmed(bw["lufs"].to_numpy(), bw["w"].to_numpy()) - float(a["lufs"].median())
        # cluster bootstrap of the reweighted change
        boots = []
        ca = (a["release_group_mbid"].rank("dense") - 1).cast(pl.Int64).to_numpy()
        cb = (bw["release_group_mbid"].rank("dense") - 1).cast(pl.Int64).to_numpy()
        for _ in range(200):
            wa = rng.poisson(1.0, int(ca.max()) + 1)[ca].astype(float)
            wb = rng.poisson(1.0, int(cb.max()) + 1)[cb] * bw["w"].to_numpy()
            boots.append((wmed(bw["lufs"].to_numpy(), wb) - wmed(a["lufs"].to_numpy(), wa),
                          wmed(b["lufs"].to_numpy(), rng.poisson(1.0, int(cb.max()) + 1)[cb].astype(float)) - wmed(a["lufs"].to_numpy(), wa)))  # fmt: skip
        bo = np.array(boots)
        within = {}
        for (sub,), z in u.filter(pl.col("per").is_in(["2009–15", "2016–22"])).group_by(["sub"]):
            m = z.group_by("per").agg(pl.col("lufs").median(), pl.len())
            d = dict(zip(m["per"], m["lufs"], strict=True))
            n = dict(zip(m["per"], m["len"], strict=True))
            if len(d) == 2:
                within[sub] = {"change": d["2016–22"] - d["2009–15"], "n_a": n["2009–15"], "n_b": n["2016–22"],
                               "share_a": float(sa.filter(pl.col("sub") == sub)["sa"].sum()),
                               "share_b": float(sb.filter(pl.col("sub") == sub)["sb"].sum())}  # fmt: skip
        summ[genre] = {"raw_change": raw, "raw_lo": float(np.quantile(bo[:, 1], 0.025)), "raw_hi": float(np.quantile(bo[:, 1], 0.975)),
                       "reweighted_change": rew, "rew_lo": float(np.quantile(bo[:, 0], 0.025)), "rew_hi": float(np.quantile(bo[:, 0], 0.975)),
                       "within": within,
                       "length_s": {p: float(z["length_s"].median()) for p, z in (("2009–15", a), ("2016–22", b))},
                       "silence": {p: float(z["silence"].median()) for p, z in (("2009–15", a), ("2016–22", b))}}  # fmt: skip
    return pl.concat(out), summ


def classical_controls(
    con, units: pl.DataFrame, genre: str = "classical", min_units: int = 300
) -> dict:
    """Mean est. LUFS change 2016-22 vs 2009-15 within a genre, unadjusted and net of record
    label (labels with >= min_units units, others pooled) and near-silent share; OLS with
    release-group cluster SEs. Labels proxy for which catalogues AcousticBrainz users submit."""
    import statsmodels.formula.api as smf

    u = units.filter(
        (pl.col("genre") == genre)
        & (pl.col("genre_source") != "hl")
        & pl.col("year").is_between(2009, 2022)
    )
    t = con.sql(
        f"select recording_mbid, release_mbid, release_label from read_parquet('{T}') where in_headline"
    ).pl()
    u = u.join(t, on=["recording_mbid", "release_mbid"], how="left").with_columns(
        (pl.col("year") >= 2016).cast(pl.Int8).alias("post")
    )
    top = (
        u.group_by("release_label")
        .len()
        .filter(pl.col("len") >= min_units)["release_label"]
        .drop_nulls()
        .to_list()
    )
    u = u.with_columns(
        pl.when(pl.col("release_label").is_in(top))
        .then(pl.col("release_label"))
        .otherwise(pl.lit("_other"))
        .alias("lab")
    )
    d = u.select("lufs", "post", "silence", "lab", "release_group_mbid").drop_nulls().to_pandas()
    cl = d["release_group_mbid"].astype("category").cat.codes
    out = {"n_labels": len(top), "n": len(d)}
    for k, f in [("unadjusted", "lufs ~ post"), ("label_fe", "lufs ~ post + C(lab)"), ("label_fe_silence", "lufs ~ post + C(lab) + silence"),
                 ("silence_only", "lufs ~ post + silence")]:  # fmt: skip
        m = smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": cl})
        b, se = float(m.params["post"]), float(m.bse["post"])
        out[k] = {"est": b, "lo": b - 1.96 * se, "hi": b + 1.96 * se}
    sh = (
        u.group_by(["lab", "post"])
        .len()
        .with_columns((pl.col("len") / pl.col("len").sum().over("post")).alias("share"))
    )
    out["label_shares"] = (
        sh.filter(pl.col("lab") != "_other")
        .pivot(on="post", index="lab", values="share")
        .fill_null(0)
        .rename({"0": "2009–15", "1": "2016–22"})
        .sort("2016–22", descending=True)
        .head(8)
        .to_dicts()
    )
    return out


def main() -> None:
    t0 = time.time()
    con = duckdb.connect()
    con.execute("set threads = 4")
    con.execute("set preserve_insertion_order = false")
    if not UNITS.exists():
        unit_descriptors(con)
    units = pl.read_parquet(UNITS)
    print(f"units {units.height:,} ({time.time() - t0:.0f}s)", flush=True)
    s: dict = {
        "n_units": units.height,
        "coverage": {c: float(units[c].is_finite().mean()) for c in DESC},
    }
    y = yearly(units)
    y.write_parquet(YEARLY)
    print(f"yearly ({time.time() - t0:.0f}s)", flush=True)
    per = {}
    for c in [*DESC, "lufs"]:
        z = y.filter(pl.col("desc") == c)
        per[c] = {
            lab: float(z.filter(pl.col("year").is_between(lo, hi))["median"].mean())
            for lo, hi, lab in PERIODS
        }
    s["period_means"] = per
    g = genre_change(units)
    g.write_parquet(GENRE)
    print(f"genre ({time.time() - t0:.0f}s)", flush=True)
    tab, eff = density(units)
    tab.write_parquet(DENSITY)
    s["density_effects"] = eff
    print(f"density ({time.time() - t0:.0f}s)", flush=True)
    comp, cs = composition(con, units)
    comp.write_parquet(COMPOSITION)
    s["composition"] = cs
    s["controls"] = {g: classical_controls(con, units, g) for g in ("classical", "other")}
    SUMMARY.write_text(json.dumps(s, indent=1))
    for c in DESC:
        e = eff[c]["2016–22"]
        print(
            f"{c:20s} periods {[round(v, 3) for v in per[c].values()]}  2016–22 vs 2009–15 at fixed LUFS+genre {e['est']:+.4f} ± {e['se']:.4f} ({e['est'] / e['sd']:+.3f} SD)"
        )
    for k, v in cs.items():
        print(
            k,
            {
                kk: (round(vv, 2) if isinstance(vv, float) else vv)
                for kk, vv in v.items()
                if kk != "within"
            },
        )
        for sub, w in v["within"].items():
            print("   ", sub, {kk: round(vv, 3) for kk, vv in w.items()})
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
