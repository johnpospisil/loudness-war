"""P12: yearly distribution of est. LUFS / LRA with cluster-bootstrap CIs on the median.

For each sample × metric × release year: n units, n release groups, median, P10, P90, and a
95% percentile CI on the median from a **cluster (release-group) Poisson bootstrap**: every
release group gets a Poisson(1) weight per replicate and the weighted median is recomputed.
Tracks of one album share a mastering engineer and often appear on several editions, so a
unit-level bootstrap would understate the uncertainty.

Samples (CLAUDE.md decisions):

* ``headline``          ``in_headline``: main sample, a lossless submission, and the
                        recording's first appearance (user decision 2026-11-07)
* ``all_codec_ex160``   first-appearance ``in_main`` units minus those whose loudness comes from
                        a lossy copy at <= 160 kbps (the dashed comparison; low-bitrate copies
                        read ~0.44 LU quiet, notes/p09_dedupe.md)
* ``lossless_all_units`` ``in_main_lossless``, the headline before 2026-11-07 (old recordings in
                        new box sets / best-ofs included), kept for P19
* ``headline_low_sil``  headline units with < 5% near-silent frames (LRA chart; P11 showed est.
                        LRA tracks silence)

Est. LRA is floored at 0 (dynamic_complexity near 0 maps slightly below it).

Output: ``data/processed/p12_yearly.parquet``.

    uv run python -m lw.models.yearly
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
OUT = ROOT / "data/processed/p12_yearly.parquet"
Y0, Y1 = 1980, 2022
B = 1000
SEED = 20261107
LOW_SIL = 0.05
SAMPLES = {
    "headline": "in_headline",
    "all_codec_ex160": "in_main and first_appearance and not (loudness_source = 'lossy'"
    " and coalesce(bit_rate_lossy, 1e9) <= 160000)",
    "headline_low_sil": f"in_headline and silence_rate_60db < {LOW_SIL}",
    "lossless_all_units": "in_main_lossless",  # pre-2026-11-07 headline, kept for P19
}  # fmt: skip
METRICS = ["lufs", "lra"]


def weighted_median_boot(x: np.ndarray, cl: np.ndarray, b: int, rng) -> np.ndarray:
    """Medians of x under b Poisson(1) cluster-weight replicates. x is sorted; cl in 0..k-1."""
    k = int(cl.max()) + 1
    out = np.empty(b)
    for r in range(b):
        w = rng.poisson(1.0, k)[cl].astype(np.float64)
        cw = np.cumsum(w)
        out[r] = x[np.searchsorted(cw, cw[-1] / 2.0)]
    return out


def yearly(con, where: str, metric: str, b: int = B, seed: int = SEED) -> pl.DataFrame:
    expr = "greatest(lra, 0)" if metric == "lra" else metric
    df = con.sql(f"""select year, release_group_mbid, {expr} as v
        from read_parquet('{T}') where ({where}) and year between {Y0} and {Y1}
          and {expr} is not null""").pl()
    rng = np.random.default_rng(seed)
    rows = []
    for (y,), g in df.sort("year").group_by(["year"], maintain_order=True):
        g = g.sort("v")
        x = g["v"].to_numpy()
        cl = (g["release_group_mbid"].fill_null("?").rank("dense") - 1).cast(pl.Int64).to_numpy()
        boots = weighted_median_boot(x, cl, b, rng)
        rows.append({
            "year": y, "n": len(x), "n_rg": int(cl.max()) + 1, "median": float(np.median(x)),
            "p10": float(np.quantile(x, 0.1)), "p90": float(np.quantile(x, 0.9)),
            "ci_lo": float(np.quantile(boots, 0.025)), "ci_hi": float(np.quantile(boots, 0.975)),
            "boot_sd": float(boots.std(ddof=1)),
        })  # fmt: skip
    return pl.DataFrame(rows)


def build(out: Path = OUT, b: int = B) -> pl.DataFrame:
    con = duckdb.connect()
    con.execute("set memory_limit='8GB'")
    parts = []
    for s, where in SAMPLES.items():
        for m in METRICS:
            t0 = time.time()
            d = yearly(con, where, m, b).with_columns(sample=pl.lit(s), metric=pl.lit(m))
            parts.append(d)
            print(f"{s:18s} {m}: {d['n'].sum():>9,} units, {time.time() - t0:.1f}s")
    res = pl.concat(parts).select("sample", "metric", pl.exclude("sample", "metric"))
    res.write_parquet(out)
    return res


def main() -> None:
    res = build()
    with pl.Config(tbl_rows=50, tbl_cols=12):
        print(res.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs")))


if __name__ == "__main__":
    main()
