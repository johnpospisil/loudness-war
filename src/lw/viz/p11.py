# ruff: noqa: E501  (SQL strings, labels)
"""P11 figures: LUFS ridgeline by decade, LUFS vs LRA, album spot-check, silence vs LRA."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import LogNorm

from lw.normalisation import era_start
from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
SPOT = ROOT / "data/processed/p11_spotcheck.csv"
PROFILE = ROOT / "data/processed/p11_profile.json"
SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
Y0, Y1 = 1980, 2022
HEAD = "in_main_lossless"
UNIT = "unit = one recording on one release; headline sample (main, lossless source)"
CAL = "est. LUFS / LRA = AcousticBrainz proxies calibrated in P03 (RMSE 1.3 LU / 2.9 LU)"


def fig_ridgeline(c, head: str = HEAD, unit: str = UNIT) -> None:
    """``head``/``unit``: sample filter and its footnote (P21 passes the final headline)."""
    HEAD = head  # noqa: N806
    lo, hi, w = -32.0, -2.0, 0.25
    rows = c.execute(f"""select year // 10 * 10 d, floor(lufs / {w}) * {w} b, count(*)
        from read_parquet('{T}') where {HEAD} and lufs between {lo} and {hi}
        group by all""").fetchall()
    med = dict(
        c.execute(f"""select year // 10 * 10, median(lufs) from read_parquet('{T}')
        where {HEAD} group by 1""").fetchall()
    )
    ns = dict(
        c.execute(f"""select year // 10 * 10, count(*) from read_parquet('{T}')
        where {HEAD} group by 1""").fetchall()
    )
    decades = sorted(med)
    edges = np.arange(lo, hi + w / 2, w)
    theme.apply()
    fig, ax = plt.subplots(figsize=(10, 6.2))
    cols = [theme.SEQ_BLUE[i] for i in (3, 5, 7, 9, 11)]
    step = 1.0
    for k, d in enumerate(decades):
        h = np.zeros(len(edges))
        for dd, b, n in rows:
            if dd == d:
                h[int(round((b - lo) / w))] += n
        h = np.convolve(h, np.ones(5) / 5, mode="same")
        h = h / h.max() * 1.15
        base = (len(decades) - 1 - k) * step
        ax.fill_between(edges + w / 2, base, base + h, color=cols[k], alpha=0.9, lw=0,
                        zorder=10 - k)  # fmt: skip
        ax.plot(edges + w / 2, base + h, color=theme.SURFACE, lw=1.2, zorder=10 - k)
        ax.plot([med[d]] * 2, [base, base + np.interp(med[d], edges + w / 2, h)],
                color=theme.TEXT, lw=1.3, zorder=11)  # fmt: skip
        ax.text(lo + 0.3, base + 0.18, f"{d}s", fontsize=10.5, fontweight="bold", zorder=12)
        ax.text(lo + 0.3, base + 0.55, f"n = {ns[d]:,}", fontsize=8, color=theme.TEXT_2,
                zorder=12)  # fmt: skip
        ax.text(med[d] + 0.25, base + 0.12, f"{med[d]:.1f}", fontsize=8.5, zorder=12)
    ax.set_xlim(lo, hi)
    ax.set_yticks([])
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Estimated integrated loudness (LUFS; right = louder)")
    fig.suptitle(
        f"The whole distribution moved up {med[2010] - med[1980]:.0f} LU from the 1980s to "
        "the 2010s, then stopped",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    ax.set_title("Distribution of est. LUFS by release decade (line and label = median)",
                 loc="left", fontsize=10)  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p11_ridgeline_lufs_by_decade", n=sum(ns.values()), source=SRC,
                   note=f"{unit}; {CAL}")  # fmt: skip


def _hex(ax, c, where: str, title: str):
    bx, by = 0.25, 0.25
    rows = c.execute(f"""select floor(lufs / {bx}) * {bx}, floor(lra / {by}) * {by}, count(*)
        from read_parquet('{T}') where {HEAD} and {where}
          and lufs between -35 and -2 and lra between 0 and 25 group by all""").fetchall()
    xe, ye = np.arange(-35, -2 + bx, bx), np.arange(0, 25 + by, by)
    H = np.zeros((len(ye) - 1, len(xe) - 1))
    for x, y, n in rows:
        i, j = int(round((y - 0) / by)), int(round((x + 35) / bx))
        if 0 <= i < H.shape[0] and 0 <= j < H.shape[1]:
            H[i, j] += n
    m = ax.pcolormesh(xe, ye, np.where(H > 0, H, np.nan), cmap="Blues", norm=LogNorm(1, H.max()),
                      shading="flat", rasterized=True)  # fmt: skip
    r = c.execute(f"""with x as (select lufs a, lra b, rank() over (order by lufs) ra,
        rank() over (order by lra) rb from read_parquet('{T}') where {HEAD} and {where})
        select corr(ra, rb), count(*) from x""").fetchone()
    ax.set_title(f"{title}\nSpearman ρ = {r[0]:.2f}, n = {r[1]:,}", loc="left", fontsize=10)
    ax.set_xlabel("Est. LUFS")
    return m, r[1]


def fig_hexbin(c) -> None:
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.6), sharey=True)
    fig.subplots_adjust(top=0.8, wspace=0.08)
    m, n1 = _hex(a1, c, "true", "All headline-sample units")
    _hex(a2, c, "silence_rate_60db < 0.05", "Units with < 5% near-silent frames")
    a1.set_ylabel("Est. LRA (LU)")
    cb = fig.colorbar(m, ax=[a1, a2], shrink=0.85, pad=0.015)
    cb.set_label("Units per 0.25 × 0.25 cell (log)")
    fig.suptitle(
        "Louder tracks have less loudness range, but much of the spread in est. LRA comes "
        "from silence",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    theme.save_fig(fig, "p11_lufs_vs_lra", n=n1, source=SRC,
                   note=f"{UNIT}; near-silent = below −60 dB; {CAL}")  # fmt: skip


def fig_spotcheck(c) -> None:
    d = pl.read_csv(SPOT).with_columns(
        pl.coalesce("edition_year", "year").alias("at_year"))  # fmt: skip
    band = c.execute(f"""select year, quantile_cont(lufs, 0.1), median(lufs),
        quantile_cont(lufs, 0.9) from read_parquet('{T}') where in_main
        and year between {Y0} and {Y1} group by 1 order by 1""").fetchall()
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 7.2), gridspec_kw={"width_ratios": [1.55, 1]})
    yy = [r[0] for r in band]
    theme.shade_era(a1, start=era_start(), end=Y1 + 0.5)
    a1.fill_between(yy, [r[1] for r in band], [r[3] for r in band], color=theme.SEQ_BLUE[1],
                    lw=0, label="main sample, P10–P90")  # fmt: skip
    a1.plot(yy, [r[2] for r in band], color=theme.SERIES[0], lw=1.8, label="main sample, median")
    sty = {"criticised_loud": (theme.SERIES[7], "o", "criticised as loud (Wikipedia)"),
           "noted_dynamic": (theme.SERIES[2], "D", "noted as dynamic (Wikipedia)"),
           "reference": (theme.MUTED, "o", "reference album (no expectation)")}  # fmt: skip
    for g, (col, mk, lab) in sty.items():
        s = d.filter(pl.col("group") == g)
        a1.scatter(s["at_year"], s["lufs"], color=col, marker=mk, s=34, zorder=5, label=lab,
                   edgecolor=theme.SURFACE, lw=0.6)  # fmt: skip
    for name in ["Death Magnetic", "Californication", "(What's the Story) Morning Glory?",
                 "Random Access Memories", "Brothers in Arms", "Back in Black"]:  # fmt: skip
        r = d.filter(pl.col("album") == name).row(0, named=True)
        short = {"(What's the Story) Morning Glory?": "Morning Glory?"}.get(name, name)
        a1.annotate(short, (r["at_year"], r["lufs"]), xytext=(6, 4), textcoords="offset points",
                    fontsize=8.2, color=theme.TEXT)  # fmt: skip
    a1.set_xlim(Y0 - 0.5, Y1 + 0.5)
    a1.set_ylim(-22, -4)
    a1.set_xlabel("Release year (edition year for the three criticised reissues)")
    a1.set_ylabel("Album median est. LUFS")
    a1.legend(loc="lower right", fontsize=8.2, framealpha=0.92)
    a1.set_title("54 well-known albums against their release year", loc="left", fontsize=10.5)
    # right: percentile within release year, test set only
    s = d.filter(pl.col("group") != "reference").sort("pct_lufs_year")
    y = np.arange(s.height)
    cols = [sty[g][0] for g in s["group"]]
    a2.axvline(50, color=theme.TEXT, lw=1, ls=(0, (3, 2)))
    a2.axvspan(75, 100, color=theme.ERA_FILL, lw=0, zorder=0)
    a2.text(76, s.height - 0.3, "top quartile", fontsize=8, color=theme.TEXT_2, va="top")
    a2.scatter(100 * s["pct_lufs_year"], y, color=cols, s=36, zorder=5)
    labs = [f"{a} — {b}" + (f" ({e})" if e else "")
            for a, b, e in zip(s["artist"], s["album"], s["edition_year"], strict=True)]  # fmt: skip
    labs = [lab if len(lab) < 46 else lab[:44] + "…" for lab in labs]
    a2.set_yticks(y, labs, fontsize=7.8)
    a2.set_xlim(0, 100)
    a2.set_xlabel("Percentile of est. LUFS within its release year (%)")
    a2.set_title("Where the cited albums rank in their year", loc="left", fontsize=10.5)
    a2.grid(axis="y", visible=False)
    p = json.loads(PROFILE.read_text())["spotcheck"]
    fig.suptitle(
        f"All {p['criticised_found']} albums criticised as loud sit above their year's median "
        f"({p['criticised_top_quartile']} in the top quartile); both 'dynamic' albums sit below",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p11_spotcheck_albums", n=int(d["n_units"].sum()), source=SRC,
                   note="n = units across the 54 albums; album = median over its original-"
                        "release units (non-reissue); percentiles against the main sample; "
                        "list: data/reference/spotcheck_albums.csv")  # fmt: skip


def fig_silence(c) -> None:
    p = json.loads(PROFILE.read_text())
    rows = c.execute(f"""select year, median(lra), median(lra) filter (where silence_rate_60db < 0.05),
        median(silence_rate_60db), count(*) from read_parquet('{T}') where {HEAD}
        and year between {Y0} and {Y1} group by 1 order by 1""").fetchall()
    yy = [r[0] for r in rows]
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8))
    for a in (a1, a2):
        theme.shade_era(a, start=era_start(), end=Y1 + 0.5)
    a1.plot(yy, [r[1] for r in rows], color=theme.SERIES[0], lw=1.9, marker="o", ms=2.8,
            label="all headline units")  # fmt: skip
    a1.plot(yy, [r[2] for r in rows], color=theme.SERIES[1], lw=1.9, marker="o", ms=2.8,
            label=f"< 5% near-silent frames ({p['low_sil_share_lossless']:.0%} of units)")  # fmt: skip
    a1.set_ylim(0, 9)
    a1.set_ylabel("Median est. LRA (LU)")
    a1.set_xlabel("Release year")
    a1.legend(loc="lower left", fontsize=8.5)
    a1.set_title("Median est. LRA by release year", loc="left", fontsize=10.5)
    a2.plot(yy, [100 * r[3] for r in rows], color=theme.TEXT, lw=1.8)
    a2.set_ylim(0, 15)
    a2.set_ylabel("Median share of near-silent frames (%)")
    a2.set_xlabel("Release year")
    corr = p["corr_lossless"]["lra~silence_rate_60db"]["spearman"]
    a2.set_title(f"Near-silent frames per track (Spearman ρ with est. LRA = {corr:.2f})",
                 loc="left", fontsize=10.5)  # fmt: skip
    fig.suptitle(
        "Est. LRA falls with the amount of silence in tracks; among tracks with almost no "
        "silence it barely moves",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p11_silence_vs_lra", n=sum(r[4] for r in rows), source=SRC,
                   note=f"{UNIT}; near-silent = below −60 dB (Essentia silence_rate_60dB)")  # fmt: skip


def main() -> None:
    c = duckdb.connect()
    fig_ridgeline(c)
    fig_hexbin(c)
    fig_spotcheck(c)
    fig_silence(c)


if __name__ == "__main__":
    main()
