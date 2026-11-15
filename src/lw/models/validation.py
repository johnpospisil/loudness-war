"""P18: validate the AcousticBrainz loudness estimates against independent measurements.

Four checks, results in ``data/processed/p18_*``:

1. **Proxy on lossless CD audio** (out of sample for P03, which was fitted on AAC): on the
   user's own rips, est. LUFS / est. LRA from the Essentia extractor vs pyloudnorm.
2. **AcousticBrainz vs own measurement** (end to end): for every own track, the
   AcousticBrainz submissions of the same recording MBID, at the closest available level
   (same release > same release group > any release of the recording; remasters share
   recording MBIDs, so the last level can be a different master). Bland-Altman on
   pyloudnorm LUFS / LRA vs AcousticBrainz est. LUFS / est. LRA.
3. **Lossy encoding shift**: each re-encoded copy minus its lossless source.
4. **Dynamic Range Database** (internal check): album DR vs our album-level est. LUFS /
   est. LRA, overall and within release year. Only aggregate statistics are written to
   ``data/processed``; per-album DR values stay in git-ignored ``data/interim/p18``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from lw.measure.calibrate import predict

ROOT = Path(__file__).resolve().parents[3]
IN = ROOT / "data/interim/p18"
AB = ROOT / "data/interim/ab_matched.parquet"
T = ROOT / "data/processed/tracks.parquet"
SPOT = ROOT / "data/processed/p11_spotcheck.csv"
OUT = ROOT / "data/processed"
OWN = OUT / "p18_own_tracks.parquet"
ENC = OUT / "p18_encoding.parquet"
DR_BINS = OUT / "p18_drdb_bins.parquet"
SUMMARY = OUT / "p18_summary.json"
DR_ALBUMS = IN / "drdb_albums.parquet"  # per-album DR: interim only, never published
LEVELS = ["same_release", "same_release_group", "other_release"]
N_BOOT = 2000
SEED = 0


def _est(df: pl.DataFrame) -> pl.DataFrame:
    """Add calibrated est. LUFS and est. LRA (floored at 0, as in P09)."""
    df = predict(df, "lufs")
    df = predict(df, "lra").with_columns(pl.col("est_lra").clip(lower_bound=0))
    return df.drop([c for c in df.columns if c.endswith(("_lo", "_hi"))])


def own_tracks() -> pl.DataFrame:
    inv = pl.read_parquet(IN / "inventory.parquet")
    m = pl.read_parquet(IN / "measurements.parquet").filter(pl.col("error").is_null())
    df = inv.join(m.drop("error"), on="path", how="inner")
    return _est(df)


def ab_matches(own: pl.DataFrame) -> pl.DataFrame:
    """AcousticBrainz submissions of each own recording, labelled by match level."""
    import duckdb

    c = duckdb.connect()
    c.register("o", own.select("path", "recording_mbid", "release_mbid", "release_group_mbid"))
    ab = c.sql(f"""
        select o.path, a.release_mbid ab_release, a.release_group_mbid ab_rg, a.is_reissue,
          a.release_year ab_release_year, a.match_tier, a.replay_gain, a.dynamic_complexity,
          a.average_loudness, a.codec, a.lossless, a.bit_rate, a.length_s ab_length_s,
          case when a.release_mbid = o.release_mbid then 'same_release'
               when a.release_group_mbid = o.release_group_mbid then 'same_release_group'
               else 'other_release' end as level
        from o join read_parquet('{AB}') a on a.recording_mbid_mb = o.recording_mbid
        where a.match_tier in ('A', 'B', 'C')""").pl()
    # lossless as P09 defines it (FLAC/ALAC/PCM/APE/WavPack/TTA), not Essentia's flag
    ll = pl.col("codec").str.to_lowercase().str.contains("flac|alac|pcm|ape|wavpack|tta")
    return _est(ab.with_columns(ab_lossless=ll))


def best_match(own: pl.DataFrame, ab: pl.DataFrame) -> pl.DataFrame:
    """Per own track: AB estimate at the closest level, lossless submissions first."""
    rank = {lv: i for i, lv in enumerate(LEVELS)}
    ab = ab.with_columns(lv_rank=pl.col("level").replace_strict(rank, return_dtype=pl.Int8))
    best = ab.group_by("path").agg(pl.col("lv_rank").min().alias("best_rank"))
    ab = ab.join(best, on="path").filter(pl.col("lv_rank") == pl.col("best_rank"))
    has_ll = ab.group_by("path").agg(pl.col("ab_lossless").any().alias("has_ll"))
    ab = ab.join(has_ll, on="path").filter(~pl.col("has_ll") | pl.col("ab_lossless"))
    agg = ab.group_by("path").agg(
        level=pl.col("level").first(),
        ab_n=pl.len(),
        ab_lossless=pl.col("ab_lossless").first(),
        ab_est_lufs=pl.col("est_lufs").median(),
        ab_est_lra=pl.col("est_lra").median(),
        ab_replay_gain=pl.col("replay_gain").median(),
        ab_dynamic_complexity=pl.col("dynamic_complexity").median(),
        ab_length_s=pl.col("ab_length_s").median(),
        ab_reissue=pl.col("is_reissue").any(),
    )
    return own.join(agg, on="path", how="left").with_columns(
        d_lufs=pl.col("ab_est_lufs") - pl.col("lufs"),
        d_lra=pl.col("ab_est_lra") - pl.col("lra"),
        d_rg=pl.col("ab_replay_gain") - pl.col("replay_gain"),
        d_len=pl.col("ab_length_s") - pl.col("duration_s"),
    )


def bland_altman(a: np.ndarray, b: np.ndarray, groups: np.ndarray | None = None) -> dict:
    """Bias (b − a), SD, 95% limits of agreement, with a cluster bootstrap CI on the bias."""
    d = b - a
    ok = np.isfinite(d)
    d, groups = d[ok], (groups[ok] if groups is not None else np.arange(ok.sum()))
    out = {"n": int(d.size), "bias": float(d.mean()), "sd": float(d.std(ddof=1)),
           "median": float(np.median(d)), "mae": float(np.abs(d).mean())}  # fmt: skip
    out["loa"] = [out["bias"] - 1.96 * out["sd"], out["bias"] + 1.96 * out["sd"]]
    rng = np.random.default_rng(SEED)
    g = np.unique(groups)
    idx = {k: np.flatnonzero(groups == k) for k in g}
    boots = []
    for _ in range(N_BOOT):
        pick = rng.choice(g, g.size)
        boots.append(d[np.concatenate([idx[k] for k in pick])].mean())
    out["bias_ci"] = [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))]
    out["n_albums"] = int(g.size)
    return out


def encoding_shift(own: pl.DataFrame) -> pl.DataFrame:
    enc = _est(pl.read_parquet(IN / "encodings.parquet").filter(pl.col("error").is_null()))
    src = own.select(
        "path", "album_dir", src_lufs="lufs", src_lra="lra", src_est_lufs="est_lufs",
        src_est_lra="est_lra", src_rg="replay_gain", src_dc="dynamic_complexity",
        src_peak="peak_dbfs",
    )  # fmt: skip
    return enc.join(src, on="path").with_columns(
        d_lufs=pl.col("lufs") - pl.col("src_lufs"),
        d_lra=pl.col("lra") - pl.col("src_lra"),
        d_est_lufs=pl.col("est_lufs") - pl.col("src_est_lufs"),
        d_est_lra=pl.col("est_lra") - pl.col("src_est_lra"),
        d_rg=pl.col("replay_gain") - pl.col("src_rg"),
        d_dc=pl.col("dynamic_complexity") - pl.col("src_dc"),
        d_peak=pl.col("peak_dbfs") - pl.col("src_peak"),
    )


# --------------------------------------------------------------------------------------
# Dynamic Range Database
# --------------------------------------------------------------------------------------
def dr_albums() -> pl.DataFrame:
    """Per target album: median DR of original-CD entries + our album-level estimates."""
    import duckdb

    rows = pl.read_parquet(IN / "drdb_rows.parquet").filter("keep")
    dr = rows.group_by("release_group_mbid").agg(
        dr=pl.col("dr").median(), dr_n=pl.len(), year=pl.col("year").first(),
        why=pl.col("why").first(),
    )  # fmt: skip
    c = duckdb.connect()
    c.register("dr", dr)
    ours = c.sql(f"""
        select t.release_group_mbid, count(*) n_units, median(t.lufs) est_lufs,
          median(t.lra) est_lra, median(t.dynamic_complexity) dyn_complexity,
          median(t.silence_rate_60db) silence, mode(t.genre) genre,
          avg((t.loudness_source = 'lossless')::int) lossless_share
        from read_parquet('{T}') t
        where t.release_group_mbid in (select release_group_mbid from dr)
          and t.in_core and not t.is_reissue and t.year <= t.rg_first_year + 1
        group by 1""").pl()
    out = dr.join(ours, on="release_group_mbid", how="inner")
    if SPOT.exists():
        sp = pl.read_csv(SPOT).select("release_group_mbid", spot_group="group").drop_nulls()
        out = out.join(sp.unique("release_group_mbid"), on="release_group_mbid", how="left")
    return out


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    from scipy.stats import spearmanr

    return float(spearmanr(x, y).statistic)


def _boot_corr(x: np.ndarray, y: np.ndarray, fn) -> dict:
    rng = np.random.default_rng(SEED)
    est = fn(x, y)
    b = [fn(x[i], y[i]) for i in (rng.integers(0, x.size, x.size) for _ in range(N_BOOT))]
    return {"r": est, "lo": float(np.quantile(b, 0.025)), "hi": float(np.quantile(b, 0.975))}


def _within_year(df: pl.DataFrame, col: str) -> np.ndarray:
    return (df[col] - df.select(pl.col(col).mean().over("year"))[col]).to_numpy()


def dr_stats(a: pl.DataFrame) -> dict:
    pearson = lambda x, y: float(np.corrcoef(x, y)[0, 1])  # noqa: E731
    out = {"n_albums": a.height, "n_dr_entries": int(a["dr_n"].sum()),
           "years": [int(a["year"].min()), int(a["year"].max())]}  # fmt: skip
    for col in ["est_lufs", "est_lra", "dyn_complexity"]:
        x, y = a[col].to_numpy(), a["dr"].to_numpy()
        multi = a.filter(pl.len().over("year") >= 2)
        out[col] = {
            "spearman": _boot_corr(x, y, _spearman),
            "pearson": _boot_corr(x, y, pearson),
            "within_year_pearson": _boot_corr(
                _within_year(multi, col), _within_year(multi, "dr"), pearson
            ),
            "slope_dr_per_unit": float(np.polyfit(x, y, 1)[0]),
        }
    # agreement on direction: P11 Wikipedia 'criticised loud' albums vs the rest, same years
    if "spot_group" in a.columns:
        loud = a.filter(pl.col("spot_group") == "criticised_loud")
        out["criticised_loud"] = {
            "n": loud.height,
            "median_dr": float(loud["dr"].median()) if loud.height else None,
            "median_dr_others": float(a.filter(pl.col("spot_group").is_null() |
                (pl.col("spot_group") != "criticised_loud"))["dr"].median()),
            "share_below_year_median_dr": float(np.mean([  # vs albums within +-2 years
                r["dr"] < a.filter(pl.col("year").is_between(r["year"] - 2, r["year"] + 2))[
                    "dr"].median() for r in loud.iter_rows(named=True)])) if loud.height else None,
        }  # fmt: skip
    return out


def dr_bins(a: pl.DataFrame, width: float = 1.5) -> pl.DataFrame:
    """Aggregate only (>= 5 albums per bin): DR quartiles per est. LUFS / est. LRA bin."""
    out = []
    for col in ["est_lufs", "est_lra"]:
        b = (a[col] / width).floor() * width + width / 2
        g = a.with_columns(bin=b).group_by("bin").agg(
            n=pl.len(), q25=pl.col("dr").quantile(0.25), med=pl.col("dr").median(),
            q75=pl.col("dr").quantile(0.75),
        ).filter(pl.col("n") >= 5).sort("bin")  # fmt: skip
        out.append(g.with_columns(x=pl.lit(col)))
    return pl.concat(out)


def run() -> dict:
    own = own_tracks()
    ab = ab_matches(own)
    tr = best_match(own, ab)
    tr.write_parquet(OWN)
    s: dict = {"own": {
        "n_tracks": tr.height, "n_albums": tr["album_dir"].n_unique(),
        "all_lossless": bool(tr["lossless"].all()),
        "accuraterip_accurate": int(tr["accuraterip"].str.contains("Accurate").sum()),
        "lufs_range": [float(tr["lufs"].min()), float(tr["lufs"].max())],
        "lra_range": [float(tr["lra"].min()), float(tr["lra"].max())],
        "meters_pyln_vs_ffmpeg_lufs_median_abs": float((tr["lufs"] - tr["ff_lufs"]).abs().median()),
        "meters_pyln_vs_ffmpeg_lra_median_abs": float((tr["lra"] - tr["ff_lra"]).abs().median()),
    }}  # fmt: skip
    g = tr["album_dir"].to_numpy()
    s["proxy_lossless"] = {
        "lufs": bland_altman(tr["lufs"].to_numpy(), tr["est_lufs"].to_numpy(), g),
        "lra": bland_altman(tr["lra"].to_numpy(), tr["est_lra"].to_numpy(), g),
        "p03_cv_rmse": {"lufs": 1.34, "lra": 2.93},
    }
    s["proxy_lossless"]["lufs"]["rmse"] = float(
        np.sqrt(np.nanmean((tr["est_lufs"] - tr["lufs"]).to_numpy() ** 2))
    )
    s["proxy_lossless"]["lra"]["rmse"] = float(
        np.sqrt(np.nanmean((tr["est_lra"] - tr["lra"]).to_numpy() ** 2))
    )
    s["proxy_lossless"]["album_level"] = _album_level(tr)
    m = tr.filter(pl.col("ab_est_lufs").is_not_null())
    s["ab_vs_own"] = {"n_tracks_matched": m.height, "n_albums_matched": m["album_dir"].n_unique(),
                      "by_album": _by_album(tr)}  # fmt: skip
    s["ab_vs_own"]["master_mix"] = _master_mix(own, ab)
    unit = _unit_compare(tr)
    if unit.height >= 3:
        gu = unit["album_dir"].to_numpy()
        s["ab_vs_own"]["analysis_unit"] = {
            "lufs": bland_altman(unit["lufs"].to_numpy(), unit["unit_lufs"].to_numpy(), gu),
            "lra": bland_altman(unit["lra"].to_numpy(), unit["unit_lra"].to_numpy(), gu),
            "in_headline": int(unit["in_headline"].sum()),
            "share_rg_within_0_5db": float((unit["d_unit_rg"].abs() < 0.5).mean()),
        }
        h = unit.filter("in_headline")
        if h.height >= 3:
            gh = h["album_dir"].to_numpy()
            s["ab_vs_own"]["headline_unit"] = {
                "lufs": bland_altman(h["lufs"].to_numpy(), h["unit_lufs"].to_numpy(), gh),
                "lra": bland_altman(h["lra"].to_numpy(), h["unit_lra"].to_numpy(), gh),
                "share_rg_within_0_5db": float((h["d_unit_rg"].abs() < 0.5).mean()),
                "n_albums": h["album_dir"].n_unique(),
            }
    for lv in [*LEVELS, "same_master"]:
        z = (m.filter(pl.col("d_rg").abs() < 0.5) if lv == "same_master"
             else m.filter(pl.col("level") == lv))  # fmt: skip
        if z.height < 3:
            continue
        gz = z["album_dir"].to_numpy()
        s["ab_vs_own"][lv] = {
            "lufs": bland_altman(z["lufs"].to_numpy(), z["ab_est_lufs"].to_numpy(), gz),
            "lra": bland_altman(z["lra"].to_numpy(), z["ab_est_lra"].to_numpy(), gz),
            "replay_gain_same_extractor": bland_altman(
                z["replay_gain"].to_numpy(), z["ab_replay_gain"].to_numpy(), gz),
            "share_rg_within_0_5db": float((z["d_rg"].abs() < 0.5).mean()),
            "share_lossless": float(z["ab_lossless"].mean()),
        }  # fmt: skip
    # encoding
    if (IN / "encodings.parquet").exists():
        enc = encoding_shift(own)
        enc.write_parquet(ENC)
        s["encoding"] = {"n_sources": enc["path"].n_unique()}
        for (lab,), z in enc.group_by(["encoding"], maintain_order=True):
            s["encoding"][lab] = {
                k: {"mean": float(z[k].mean()), "sd": float(z[k].std()),
                    "p05": float(z[k].quantile(0.05)), "p95": float(z[k].quantile(0.95)),
                    "max_abs": float(z[k].abs().max())}
                for k in ["d_lufs", "d_lra", "d_est_lufs", "d_est_lra", "d_rg", "d_dc", "d_peak"]
            } | {"n": z.height}  # fmt: skip
    # DR database
    if (IN / "drdb_rows.parquet").exists():
        a = dr_albums()
        a.write_parquet(DR_ALBUMS)
        dr_bins(a).write_parquet(DR_BINS)
        s["drdb"] = dr_stats(a)
        rows = pl.read_parquet(IN / "drdb_rows.parquet")
        tg = pl.read_parquet(IN / "drdb_targets.parquet")
        s["drdb"]["n_targets"] = tg.height
        s["drdb"]["n_targets_with_any_row"] = rows["release_group_mbid"].n_unique()
        s["drdb"]["n_targets_with_cd_match"] = int(
            rows.filter("keep")["release_group_mbid"].n_unique()
        )
        s["drdb"]["fetched"] = "2026-11-14"
        s["drdb"]["citation"] = (
            "Dynamic Range Database, https://dr.loudness-war.info (accessed 2026-11-14)"
        )
    SUMMARY.write_text(json.dumps(s, indent=2) + "\n")
    return s


def _master_mix(own: pl.DataFrame, ab: pl.DataFrame) -> dict:
    """How often do AB submissions tagged with the same release / album carry other audio?

    Same extractor on the same audio gives replay gain within ~0.1 dB, so |Δ replay gain|
    > 1 dB against the own rip means a different master (or edition) behind the same tags.
    """
    z = ab.join(own.select("path", own_rg="replay_gain"), on="path").with_columns(
        diff=(pl.col("replay_gain") - pl.col("own_rg")).abs() > 1.0
    )
    out = {}
    for lv in LEVELS[:2]:
        q = z.filter((pl.col("level") == lv) & pl.col("ab_lossless"))
        out[lv] = {"n_submissions": q.height, "share_other_master": float(q["diff"].mean())
                   if q.height else None,
                   "albums": q.group_by(pl.col("path").str.extract(r"Lossless/([^/]+/[^/]+)/"))
                   .agg(n=pl.len(), share=pl.col("diff").mean()).sort("share", descending=True)
                   .rename({"path": "album_dir"}).to_dicts()}  # fmt: skip
    return out


def _unit_compare(tr: pl.DataFrame) -> pl.DataFrame:
    """Own track vs the analysis unit (recording, own release) in tracks.parquet."""
    import duckdb

    c = duckdb.connect()
    c.register("o", tr.select("path", "album_dir", "recording_mbid", "release_mbid", "lufs",
                              "lra", "replay_gain"))  # fmt: skip
    return c.sql(f"""select o.*, t.lufs unit_lufs, t.lra unit_lra, t.in_headline, t.n_sub,
          t.replay_gain - o.replay_gain d_unit_rg
        from o join read_parquet('{T}') t using (recording_mbid, release_mbid)""").pl()


def _album_level(tr: pl.DataFrame) -> dict:
    """Album medians of the proxy vs measured: the level later analyses work at."""
    a = tr.group_by("album_dir").agg(pl.col("lufs", "est_lufs", "lra", "est_lra").median())
    return {
        "lufs": bland_altman(a["lufs"].to_numpy(), a["est_lufs"].to_numpy()),
        "lra": bland_altman(a["lra"].to_numpy(), a["est_lra"].to_numpy()),
    }


def _by_album(tr: pl.DataFrame) -> list[dict]:
    a = tr.group_by("album_dir", maintain_order=True).agg(
        n=pl.len(), year=pl.col("release_year").first(), rg_year=pl.col("rg_first_year").first(),
        lufs=pl.col("lufs").median(), est_lufs=pl.col("est_lufs").median(),
        lra=pl.col("lra").median(), est_lra=pl.col("est_lra").median(),
        matched=pl.col("ab_est_lufs").is_not_null().sum(),
        level=pl.col("level").drop_nulls().mode().first(),
        ab_est_lufs=pl.col("ab_est_lufs").median(), d_lufs=pl.col("d_lufs").median(),
        d_rg=pl.col("d_rg").median(), d_lra=pl.col("d_lra").median(),
    )  # fmt: skip
    return a.to_dicts()


if __name__ == "__main__":
    s = run()
    print(json.dumps({k: v for k, v in s.items() if k != "ab_vs_own"}, indent=1)[:3000])
    print(json.dumps({k: v for k, v in s["ab_vs_own"].items() if k != "by_album"}, indent=1)[:3000])
