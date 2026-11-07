# ruff: noqa: E501  (labels)
"""P14 figures: quantile trends with fitted segmented quantile regressions, and the
coefficient plot by tau."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from lw.models import quantile_trends as qt
from lw.normalisation import era_start
from lw.viz import theme

SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
NOTE = (
    "\nheadline = release years 1980–2022, tier A/B, not a reissue, ≥1 lossless submission, recording's first appearance; "
    "est. LUFS = calibrated replay gain (P03, ±1.3 LU per track)"
)
CAL_MAX = -4.75  # loudest track in the P03 calibration set (measured LUFS)


def _fits():
    return pl.read_parquet(qt.OUT)


def _row(f, variant, spec, tau):
    return f.filter(
        (pl.col("variant") == variant) & (pl.col("spec") == spec) & (pl.col("tau") == tau)
    ).row(0, named=True)


def fig_trends() -> None:
    f, yq = _fits(), pl.read_parquet(qt.YQ)
    theme.apply()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9.2))
    tt = np.linspace(2000, 2022, 300)
    B, K = 2016, qt.HINGE
    span = 6.0
    for ax, tau, lab in [(axes[0, 0], 0.9, "(a) Loudest decile: P90"), (axes[0, 1], 0.5, "(b) Median: P50"),
                         (axes[1, 0], 0.1, "(c) Quietest decile: P10")]:  # fmt: skip
        theme.shade_era(ax, start=era_start(), end=2022.5)
        for v, mk, col, vlab in [("fixed_genre_mix", "o", theme.MUTED, "fixed 2000–14 genre mix (tag genres)"),
                                 ("headline", "o", theme.SERIES[0], "headline (95% CI, release-group bootstrap)")]:  # fmt: skip
            z = yq.filter(
                (pl.col("variant") == v) & (pl.col("tau") == tau) & (pl.col("year") >= 1995)
            ).sort("year")
            x = z["year"].to_numpy()
            if v == "headline":
                ax.errorbar(x, z["q"], yerr=[z["q"] - z["lo"], z["hi"] - z["q"]], fmt=mk, color=col, ms=4.2,
                            lw=1, capsize=0, label=vlab, zorder=3)  # fmt: skip
            else:
                ax.plot(x, z["q"], mk, mfc="none", mec=col, ms=4.6, mew=1, label=vlab, zorder=2)
        r = _row(f, "headline", f"single|2000-2022|{B}", tau)
        p = np.array(r["coef"])
        pre = tt < B
        ax.plot(
            tt[pre],
            p[0] + p[1] * (tt[pre] - B),
            color=theme.TEXT,
            lw=1.6,
            label="QR fit, 2000–15 trend",
        )
        ax.plot(tt[~pre], p[0] + p[1] * (tt[~pre] - B), color=theme.TEXT, lw=1.3, ls=(0, (4, 2.5)),
                label="2000–15 trend projected")  # fmt: skip
        ax.plot(tt[~pre], p[0] + p[2] + (p[1] + p[3]) * (tt[~pre] - B), color=theme.SERIES[1], lw=2.2,
                label="QR fit after 2016")  # fmt: skip
        rb = _row(f, "headline", f"bend|2000-2022|{B}|k{K}", tau)
        pb = np.array(rb["coef"])
        ax.plot(tt, qt.x_bend(tt, K, B) @ pb, color=theme.SERIES[2], lw=1.4, ls=(0, (1, 1.5)),
                label=f"QR fit: bend at {K} + 2016 terms")  # fmt: skip
        r5 = _row(f, "headline", f"single|2005-2022|{B}", tau)
        txt = (f"2016–22 gap vs projected trend (LU, 95% CI bootstrap; ± HAC SE):\n"
               f"  2000–15 trend: {r['gap']:+.2f} [{r['gap_lo']:+.2f}, {r['gap_hi']:+.2f}]; ± {r['hac_gap_se']:.2f}\n"
               f"  2005–15 trend: {r5['gap']:+.2f} [{r5['gap_lo']:+.2f}, {r5['gap_hi']:+.2f}]; ± {r5['hac_gap_se']:.2f}\n"
               f"  bend {K} first: {rb['gap']:+.2f} [{rb['gap_lo']:+.2f}, {rb['gap_hi']:+.2f}]; ± {rb['hac_gap_se']:.2f}")  # fmt: skip
        ax.text(0.98, 0.04, txt, transform=ax.transAxes, ha="right", va="bottom", fontsize=7.8, family="monospace",
                bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.35"))  # fmt: skip
        z = yq.filter(
            (pl.col("variant") == "headline") & (pl.col("tau") == tau) & (pl.col("year") >= 1995)
        )
        lo_, hi_ = float(z["lo"].min()), float(z["hi"].max())
        c = (lo_ + hi_) / 2
        ax.set_ylim(c - span / 2, c + span / 2)
        ax.set_xlim(1994.5, 2022.5)
        ax.set_title(lab, loc="left", fontsize=10.5)
        ax.set_ylabel("Est. LUFS")
    h, lab_ = axes[0, 0].get_legend_handles_labels()
    axes[1, 0].legend(h, lab_, loc="upper left", fontsize=7.8, framealpha=0.92)
    # (d) beyond the modelled range
    ax = axes[1, 1]
    theme.shade_era(ax, start=era_start(), end=2022.5)
    for tau, col in [(0.95, theme.SERIES[3]), (0.99, theme.SERIES[7])]:
        for v, ls in [("headline", "-"), ("fixed_genre_mix", (0, (3, 2)))]:
            z = yq.filter(
                (pl.col("variant") == v) & (pl.col("tau") == tau) & (pl.col("year") >= 1995)
            ).sort("year")
            if v == "headline":
                ax.fill_between(z["year"], z["lo"], z["hi"], color=col, alpha=0.18, lw=0)
            ax.plot(z["year"], z["q"], color=col, lw=2 if v == "headline" else 1.2, ls=ls,
                    label=f"P{round(tau * 100)} {'headline' if v == 'headline' else 'fixed genre mix'}")  # fmt: skip
    ax.axhline(CAL_MAX, color=theme.TEXT, lw=0.9, ls=(0, (1, 2)))
    ax.text(1995, CAL_MAX + 0.12, f"loudest track in the P03 calibration set ({CAL_MAX} LUFS): above this est. LUFS is extrapolated",
            fontsize=7.6, color=theme.TEXT_2)  # fmt: skip
    ax.set_ylim(-9, -3)
    ax.set_xlim(1994.5, 2022.5)
    ax.set_title(
        "(d) The far loud tail (description only, not modelled)", loc="left", fontsize=10.5
    )
    ax.set_ylabel("Est. LUFS")
    ax.legend(loc="lower right", fontsize=7.8, framealpha=0.92, ncol=2)
    for a in axes[1]:
        a.set_xlabel("Release year")
    s = json.loads(qt.SUMMARY.read_text())
    fig.suptitle("The loudest decile did not come down: P90 has sat near −7.4 est. LUFS since 2005. The quiet end kept rising,\n"
                 "mostly through the genre mix (+0.3 LU at a fixed mix after 2016), and the far tail (P99) got louder within genres",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p14_quantile_trends", n=s["n_units"]["headline"], source=SRC,
                   note="each panel spans 6 LU; QR = track-level quantile regression 2000–2022 (n units shown), break 2016; "
                        f"fixed genre mix excludes classifier-only genres; {NOTE}")  # fmt: skip


def fig_coef() -> None:
    f = _fits()
    theme.apply()
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.6), sharex=True)
    panels = [
        (axes[0, 0], "pre_slope", "(a) Pre-trend slope, 2000–15 (LU / year)",
         [("headline", "single|2000-2022|2016", theme.SERIES[0], "headline"),
          ("fixed_genre_mix", "single|2000-2022|2016", theme.MUTED, "fixed 2000–14 genre mix")]),
        (axes[0, 1], "slope", "(b) Slope change at 2016 (LU / year), 2000–15 trend",
         [("headline", "single|2000-2022|2016", theme.SERIES[0], "headline"),
          ("fixed_genre_mix", "single|2000-2022|2016", theme.MUTED, "fixed 2000–14 genre mix")]),
        (axes[1, 0], "gap", "(c) Mean 2016–22 gap vs a straight pre-trend (LU)",
         [("headline", "single|2000-2022|2016", theme.SERIES[0], "pre-trend 2000–15"),
          ("headline", "single|2005-2022|2016", theme.SERIES[1], "pre-trend 2005–15 (on the plateau)")]),
        (axes[1, 1], "gap", f"(d) Mean 2016–22 gap after allowing the {qt.HINGE} bend (LU)",
         [("headline", f"bend|2000-2022|2016|k{qt.HINGE}", theme.SERIES[0], "headline"),
          ("fixed_genre_mix", f"bend|2000-2022|2016|k{qt.HINGE}", theme.MUTED, "fixed 2000–14 genre mix")]),
    ]  # fmt: skip
    for ax, par, title, series in panels:
        ax.axhline(0, color=theme.TEXT, lw=0.9)
        for j, (v, spec, col, lab) in enumerate(series):
            z = f.filter((pl.col("variant") == v) & (pl.col("spec") == spec)).sort("tau")
            x = z["tau"].to_numpy() + (j - 0.5) * 0.008
            ax.fill_between(z["tau"], z[f"{par}_lo"], z[f"{par}_hi"], color=col, alpha=0.2, lw=0)
            ax.plot(
                z["tau"],
                z[par],
                color=col,
                lw=2,
                marker="o",
                ms=3.5,
                label=f"{lab} (band: bootstrap 95%)",
            )
            h = z[f"hac_{par}"].to_numpy()
            ax.errorbar(x, h, yerr=1.96 * z[f"hac_{par}_se"].to_numpy(), fmt="none", ecolor=col, elinewidth=0.9,
                        alpha=0.75, capsize=1.5)  # fmt: skip
        for tau in qt.TAUS:
            ax.axvline(tau, color=theme.GRID, lw=0.8, zorder=0)
        ax.set_title(title, loc="left", fontsize=10.5)
        ax.legend(loc="best", fontsize=7.8, framealpha=0.92)
    for a in axes[1]:
        a.set_xlabel("Quantile τ (0.1 = quietest decile … 0.9 = loudest decile)")
        a.set_xticks([0.1, 0.25, 0.5, 0.75, 0.9])
    fig.suptitle("Before 2016 the quiet end rose fastest (half of it genre mix). After 2016 the loud end sits at or above every trend;\n"
                 "shortfalls are confined to the lower-middle quantiles (≤ 0.5 LU, mostly within year-to-year noise)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    s = json.loads(qt.SUMMARY.read_text())
    theme.save_fig(fig, "p14_quantile_slope_change", n=s["n_units"]["headline"], source=SRC,
                   note="track-level quantile regression on release years 2000–2022 (2005–2022 in c, orange); thin bars = 95% Newey-West CI "
                        f"on the yearly τ-quantile series (year-to-year noise); {NOTE}")  # fmt: skip


def main() -> None:
    fig_trends()
    fig_coef()


if __name__ == "__main__":
    main()
