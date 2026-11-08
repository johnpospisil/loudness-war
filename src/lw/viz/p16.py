# ruff: noqa: E501  (labels)
"""P16 figures: remaster gap by reissue year, and the famous-album dumbbell (brief chart 4)."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from lw.models import remaster_pairs as rp
from lw.normalisation import era_start
from lw.viz import theme

SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
NOTE = (
    "\npairs: same recording, both lossless, tier A/B, digital releases only (vinyl / cassette excluded); original = earliest digital non-remaster issue "
    "in the original album's release group (for pre-CD albums its first CD); est. LUFS = calibrated replay gain (P03, ±1.3 LU per track)"
)
SUSPECT = (
    -3.0
)  # a digital remaster > 3 LU quieter than the original master is most likely a mislabelled file


def fig_by_year() -> None:
    s = json.loads(rp.SUMMARY.read_text())
    by = pl.read_parquet(rp.BY_YEAR)
    alb = pl.read_parquet(rp.ALBUMS).filter(
        (pl.col("kind") == "remaster") & pl.col("re_year").is_between(1990, 2022)
    )
    theme.apply()
    fig = plt.figure(figsize=(14, 6.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[2.1, 1, 1], wspace=0.28)
    ax = fig.add_subplot(gs[0])
    theme.shade_era(ax, start=era_start(), end=2022.5)
    ax.axhline(0, color=theme.TEXT, lw=0.9)
    rng = np.random.default_rng(0)
    for grp, col, dx in [
        ("originals before 1990", theme.SERIES[0], -0.15),
        ("1990s originals", theme.SERIES[1], 0.15),
    ]:
        a = alb.filter(
            (pl.col("orig_year") < 1990)
            if grp.startswith("originals")
            else pl.col("orig_year").is_between(1990, 1999)
        )
        ax.scatter(
            a["re_year"].to_numpy() + dx + rng.uniform(-0.12, 0.12, a.height),
            a["d_lufs"],
            s=5,
            color=col,
            alpha=0.12,
            lw=0,
        )
        z = by.filter((pl.col("grp") == grp) & (pl.col("metric") == "d_lufs")).sort("year")
        x = z["year"].to_numpy() + dx
        ax.errorbar(x, z["mean"], yerr=[z["mean"] - z["lo"], z["hi"] - z["mean"]], fmt="o-", color=col, ms=4, lw=1.4,
                    capsize=0, label=f"{grp}: mean of album pairs (95% CI, album bootstrap)")  # fmt: skip
    ax.set_ylim(-4, 7)
    ax.set_xlim(1989.5, 2022.5)
    ax.set_xlabel("Reissue year")
    ax.set_ylabel("Remaster − original master (est. LU)")
    ax.set_title(
        "(a) Labelled remasters: loudness gap by reissue year (dots = album pairs)",
        loc="left",
        fontsize=10.5,
    )
    ax.legend(loc="upper left", fontsize=8, framealpha=0.92)
    seg = s["segmented"]
    ax.text(0.99, 0.02, f"2016–22 vs trend: bend at 2007 first {seg['d_lufs|bend']['gap']:+.2f} LU [{seg['d_lufs|bend']['lo']:+.2f}, {seg['d_lufs|bend']['hi']:+.2f}], p = {seg['d_lufs|bend']['p_joint']:.2f};\n"
            f"straight 2000–15 trend {seg['d_lufs|straight']['gap']:+.2f} [{seg['d_lufs|straight']['lo']:+.2f}, {seg['d_lufs|straight']['hi']:+.2f}], p = {seg['d_lufs|straight']['p_joint']:.2f}  (mixed model, album RE)",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.8,
            bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.3"))  # fmt: skip
    # (b), (c): period effects from the album-level mixed model, by pair kind
    labs = [lab for _, _, lab in rp.PERIODS]
    for j, (metric, title) in enumerate(
        [
            ("d_lufs", "(b) Δ est. LUFS by reissue period"),
            ("d_lra", "(c) Δ est. LRA by reissue period"),
        ]
    ):
        ax2 = fig.add_subplot(gs[j + 1])
        ax2.axhline(0, color=theme.TEXT, lw=0.9)
        for i, (kind, col, lab) in enumerate([("remaster", theme.SERIES[0], "labelled remasters"), ("reissue", theme.MUTED, "other same-album reissues"),
                                             ("later", theme.SERIES[2], "later compilations / box sets")]):  # fmt: skip
            m = s["models"][f"{kind}|album|{metric}"]["period_vs_2010_14"]
            e = np.array([m[x]["est"] for x in labs])
            se = np.array([m[x]["se"] for x in labs])
            xx = np.arange(len(labs)) + (i - 1) * 0.18
            ax2.errorbar(
                xx, e, yerr=1.96 * se, fmt="o-", color=col, ms=4, lw=1.3, capsize=2, label=lab
            )
        ax2.set_xticks(range(len(labs)))
        ax2.set_xticklabels([x.replace("before ", "<") for x in labs], fontsize=8.4)
        ax2.axvspan(3.6, 4.4, color=theme.ERA_FILL, lw=0, zorder=0)
        ax2.set_title(title, loc="left", fontsize=10.5)
        ax2.set_ylabel("Difference from 2010–14 (LU), original decade held fixed", fontsize=8.6)
        if j == 0:
            ax2.legend(loc="lower right", fontsize=7.6, framealpha=0.92)
    c = s["counts"]["remaster"]
    m = s["models"]["remaster|album|d_lufs"]["post2015_vs_2005_14"]
    fig.suptitle(f"Remasters run louder than the original master (album median +{c['album_median_d_lufs']:.1f} LU); the gap peaked in 2005–09.\n"
                 f"2015–22 remasters are {abs(m['est']):.1f} LU [{m['lo']:+.2f}, {m['hi']:+.2f}] less over-loud than 2005–14 ones, but the decline began around 2010, with no step at 2016",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.subplots_adjust(top=0.84, bottom=0.11, left=0.05, right=0.99)
    theme.save_fig(fig, "p16_remaster_gap_by_year", n=c["track_pairs"], source=SRC,
                   note=f"n = track pairs; {c['album_pairs']:,} album pairs of {c['orig_albums']:,} albums; labelled = reissue keyword or 'remaster' in the release name / comment; "
                        f"mixed models: Δ ~ reissue period + original decade, random intercept per original album; {NOTE}")  # fmt: skip


def fig_dumbbell() -> None:
    f = pl.read_parquet(rp.ROOT / "data/processed/p16_famous.parquet").sort("d_lufs")
    theme.apply()
    fig, ax = plt.subplots(figsize=(12.5, 9.2))
    y = np.arange(f.height)
    for i, r in enumerate(f.iter_rows(named=True)):
        r["re_lufs"] = r["orig_lufs"] + r["d_lufs"]  # paired: original + median track difference
        sus = r["d_lufs"] < SUSPECT
        col = (
            theme.MUTED
            if sus
            else (
                theme.SERIES[1]
                if r["d_lufs"] > 0.5
                else (theme.SERIES[0] if r["d_lufs"] < -0.5 else theme.TEXT_2)
            )
        )
        ax.plot(
            [r["orig_lufs"], r["re_lufs"]],
            [i, i],
            color=col,
            lw=2.2,
            alpha=0.6 if sus else 1,
            zorder=1,
        )
        ax.scatter(r["orig_lufs"], i, s=55, color="white", edgecolor=theme.TEXT, lw=1.3, zorder=2)
        ax.scatter(r["re_lufs"], i, s=60, color=col, zorder=3, marker="X" if sus else "o")
        ax.text(max(r["orig_lufs"], r["re_lufs"]) + 0.3, i, f"{r['d_lufs']:+.1f} LU" + ("  (suspect: likely mislabelled file)" if sus else ""),
                va="center", fontsize=8.2, color=theme.TEXT_2)  # fmt: skip
    ax.set_yticks(y)
    ax.set_yticklabels(
        [
            f"{r['artist']} — {r['album'][:38]} ({r['orig_year']} → {r['re_year']})"
            for r in f.iter_rows(named=True)
        ],
        fontsize=8.6,
    )
    ax.set_xlabel("Median est. LUFS over the paired tracks (louder →)")
    ax.set_xlim(-22, -3)
    from matplotlib.lines import Line2D

    h = [Line2D([], [], marker="o", color="white", markeredgecolor=theme.TEXT, ls="", ms=8, label="original master (earliest digital issue)"),
         Line2D([], [], marker="o", color=theme.SERIES[1], ls="", ms=8, label="remaster louder by > 0.5 LU"),
         Line2D([], [], marker="o", color=theme.TEXT_2, ls="", ms=8, label="within ±0.5 LU"),
         Line2D([], [], marker="o", color=theme.SERIES[0], ls="", ms=8, label="remaster quieter by > 0.5 LU"),
         Line2D([], [], marker="X", color=theme.MUTED, ls="", ms=8, label=f"quieter by > {abs(SUSPECT):.0f} LU: suspect edition mismatch")]  # fmt: skip
    fig.legend(
        handles=h,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.925),
        ncol=5,
        fontsize=8.4,
        frameon=False,
    )
    n_up = int((f["d_lufs"] > 0.5).sum())
    fig.suptitle(f"Original vs remaster for {f.height} widely submitted albums: {n_up} remasters are louder by more than 0.5 LU, "
                 f"some by 5–7 LU", x=0.01, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    fig.text(0.01, 0.945, "Albums = the most-submitted originals with a labelled digital remaster (≥ 6 paired tracks, tier-A tags on both sides, one album per artist); "
                 "the remaster with the most paired tracks is shown; remaster point = original + median paired-track difference", fontsize=8.8, color=theme.TEXT_2)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    theme.save_fig(fig, "p16_dumbbell_famous_albums", n=int(f["n_tracks"].sum()), source=SRC,
                   note=f"n = paired tracks; AcousticBrainz-derived estimates, not official measurements; one AB submission set per edition, so a mislabelled file moves an album's value; {NOTE}")  # fmt: skip


def main() -> None:
    fig_by_year()
    fig_dumbbell()


if __name__ == "__main__":
    main()
