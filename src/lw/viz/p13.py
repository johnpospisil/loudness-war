# ruff: noqa: E501  (labels)
"""P13 figures: ITS fit, break-year sensitivity with placebos, break-point profile."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import statsmodels.api as sm

from lw.models import its
from lw.normalisation import era_start
from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
NOTE = (
    "\nheadline = release years 1980–2022, tier A/B, not a reissue, ≥1 lossless submission, recording's first appearance; "
    "est. LUFS = calibrated replay gain (P03, ±1.3 LU per track)"
)


def _yearly():
    d = pl.read_parquet(its.YEARLY)
    h = d.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs")
                 & pl.col("year").is_between(2000, 2022)).sort("year")  # fmt: skip
    return d, h


def fig_fit() -> None:
    d, h = _yearly()
    s = json.loads(its.SUMMARY.read_text())
    t, y = h["year"].to_numpy().astype(float), h["median"].to_numpy()
    n_units = int(h["n"].sum())
    B = 2016
    k = s["scan_headline_lufs_hinge"]["best_break"]
    theme.apply()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), sharey=True)
    tt = np.linspace(2000, 2022, 400)
    for ax in axes:
        theme.shade_era(ax, start=era_start(), end=2022.5)
        ax.fill_between(t, h["ci_lo"], h["ci_hi"], color=theme.SEQ_BLUE[2], lw=0)
        ax.plot(t, y, "o", color=theme.SERIES[0], ms=4.5, label="median est. LUFS (95% CI)")
        ax.set_xlabel("Release year")
        ax.set_xlim(1999.5, 2022.5)
    # (a) single break against the straight 2000-2015 trend
    m = sm.OLS(y, its.design(t, B)).fit()
    p = m.params
    pre = tt < B
    a = axes[0]
    a.plot(
        tt[pre],
        p[0] + p[1] * (tt[pre] - B),
        color=theme.TEXT,
        lw=1.8,
        label="fitted pre-trend (2000–2015)",
    )
    a.plot(
        tt[~pre],
        p[0] + p[1] * (tt[~pre] - B),
        color=theme.TEXT,
        lw=1.5,
        ls=(0, (4, 2.5)),
        label="pre-trend projected (counterfactual)",
    )
    a.plot(
        tt[~pre],
        p[0] + p[2] + (p[1] + p[3]) * (tt[~pre] - B),
        color=theme.SERIES[1],
        lw=2.2,
        label="fitted after the 2016 break",
    )
    r = s["main"][f"yearly_median|2000-2022|{B}"]
    a.text(0.02, 0.04, f"Break at {B}, window 2000–2022\nmean post gap {r['gap']:+.2f} LU (95% CI {r['gap'] - 1.96 * r['gap_se']:+.2f} to {r['gap'] + 1.96 * r['gap_se']:+.2f})\n"
           f"pre-trend slope {r['pre_slope']:+.3f} LU/yr — still rising, though the series had levelled off",
           transform=a.transAxes, fontsize=8.6, va="bottom", bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.35"))  # fmt: skip
    a.set_title("(a) One break at 2016 against a straight 2000–15 trend", loc="left", fontsize=10.5)
    a.set_ylabel("Median est. LUFS (headline)")
    a.legend(loc="upper left", fontsize=8.2, framealpha=0.92)
    # (b) bend at k plus 2016 terms
    tb = its.two_break(t, y, k, B)
    X = np.column_stack(
        [
            np.ones_like(tt),
            tt - B,
            np.clip(tt - k, 0, None),
            (tt >= B).astype(float),
            (tt - B) * (tt >= B),
        ]
    )
    Xd = np.column_stack(
        [
            np.ones_like(t),
            t - B,
            np.clip(t - k, 0, None),
            (t >= B).astype(float),
            (t - B) * (t >= B),
        ]
    )
    p2 = sm.OLS(y, Xd).fit().params
    X0 = X.copy()
    X0[:, 3:] = 0
    b = axes[1]
    b.plot(
        tt, X0 @ p2, color=theme.TEXT, lw=1.5, ls=(0, (4, 2.5)), label=f"bend at {k}, no 2016 terms"
    )
    b.plot(
        tt, X @ p2, color=theme.SERIES[1], lw=2.2, label=f"bend at {k} + level/slope change at {B}"
    )
    b.axvline(k, color=theme.MUTED, lw=0.9, ls=(0, (1, 2)))
    b.text(
        k + 0.2,
        0.62,
        f"bend {k}",
        transform=b.get_xaxis_transform(),
        fontsize=8,
        color=theme.TEXT_2,
        va="top",
    )
    b.text(0.02, 0.04, f"Extra 2016 terms: mean post gap {tb['gap']:+.2f} LU (95% CI {tb['gap'] - 1.96 * tb['gap_se']:+.2f} to {tb['gap'] + 1.96 * tb['gap_se']:+.2f})\n"
           f"joint test of the two 2016 terms: p = {tb['p_joint']:.2f} (HAC); across bends 2006–11 and breaks 2015/16: p 0.13–0.64",
           transform=b.transAxes, fontsize=8.6, va="bottom", bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.35"))  # fmt: skip
    b.set_title(
        f"(b) Allow the data-driven bend ({k}) first, then test 2016", loc="left", fontsize=10.5
    )
    b.legend(loc="upper left", fontsize=8.2, framealpha=0.92)
    fig.suptitle("Against a straight 2000–15 trend, 2016–22 sits ~0.5 LU low; but the bend came around 2007–10, "
                 "and a 2016 break adds nothing once it is allowed for",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p13_its_fit", n=n_units, source=SRC,
                   note=f"yearly medians 2000–2022, OLS, Newey-West SEs (2 lags); {NOTE}")  # fmt: skip


def fig_sensitivity() -> None:
    r = pl.read_parquet(its.OUT).filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs")
                                        & (pl.col("model") == "yearly_median"))  # fmt: skip
    theme.apply()
    fig, ax = plt.subplots(figsize=(11.5, 5.4))
    theme.shade_era(ax, start=era_start(), end=2017.6)
    ax.axhline(0, color=theme.TEXT, lw=0.9)
    sty = [("placebo", None, theme.MUTED, "placebo breaks 1995–2010 (15 pre-years, post ends ≤ 2014)", 0),
           ("main", "2000-2022", theme.SERIES[0], "candidate era breaks, window 2000–2022", -0.12),
           ("main", "2005-2022", theme.SERIES[1], "candidate era breaks, window 2005–2022 (pre-period on the plateau)", 0.12)]  # fmt: skip
    for kind, win, col, lab, dx in sty:
        x = r.filter(pl.col("kind") == kind)
        if win:
            x = x.filter(pl.col("window") == win)
        x = x.sort("break")
        bx = x["break"].to_numpy() + dx
        ax.errorbar(bx, x["gap"], yerr=1.96 * x["gap_se"].to_numpy(), fmt="o", color=col, ms=5,
                    capsize=2.5, lw=1.3, label=lab)  # fmt: skip
    ax.set_xlabel("Break year")
    ax.set_ylabel("Mean post-break gap vs projected pre-trend (LU)")
    ax.set_xlim(1994.3, 2017.7)
    ax.legend(loc="lower left", fontsize=8.4, framealpha=0.92)
    fig.suptitle("The post-2015 gap is small next to the bends the model finds during the loudness rise, "
                 "and grows when the break is moved earlier",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    ax.set_title("Segmented model on yearly median est. LUFS (headline); points = mean gap over the post years, bars = 95% CI (HAC)",
                 loc="left", fontsize=9.5, color=theme.TEXT_2)  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p13_break_year_sensitivity", n=int(pl.read_parquet(its.YEARLY).filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs"))["n"].sum()),
                   source=SRC, note=f"placebo gaps reflect the real 1995–2009 rise and plateau, so they show how readily the model finds 'breaks' in a bending series; {NOTE}")  # fmt: skip


def fig_profile() -> None:
    sc = pl.read_parquet(its.OUT.with_name("p13_scan.parquet"))
    theme.apply()
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.9))
    series = [("headline", "lufs", theme.SERIES[0], "headline est. LUFS"),
              ("headline_low_sil", "lufs", theme.SERIES[1], "headline, < 5% near-silent frames, est. LUFS"),
              ("headline", "lra", theme.SERIES[2], "headline est. LRA")]  # fmt: skip
    for ax, form, title in [(axes[0], "level+slope", "Level + slope change at the break"),
                            (axes[1], "hinge", "Continuous bend (slope change only)")]:  # fmt: skip
        theme.shade_era(ax, start=era_start(), end=2019.5)
        for sample, metric, col, lab in series:
            x = sc.filter(
                (pl.col("sample") == sample)
                & (pl.col("metric") == metric)
                & (pl.col("form") == form)
            ).sort("break")
            dev = x["deviance"].to_numpy() - x["deviance"].min()
            ax.plot(x["break"], dev, color=col, lw=2.2 if sample == "headline" and metric == "lufs" else 1.4,
                    marker="o", ms=3.5, label=lab)  # fmt: skip
            j = int(np.argmin(dev))
            ax.plot(x["break"][j], 0, marker="v", color=col, ms=9)
        ax.axhline(3.84, color=theme.TEXT, lw=0.9, ls=(0, (3, 2)))
        ax.text(2019.3, 4.2, "≈95% set: Δ < 3.84", fontsize=8, color=theme.TEXT_2, ha="right")
        ax.set_ylim(0, 25)
        ax.set_xlim(2003.5, 2019.5)
        ax.set_xlabel("Candidate break year")
        ax.set_title(title, loc="left", fontsize=10.5)
    axes[0].set_ylabel("Δ deviance from the best break (n·log SSR)")
    axes[0].legend(loc="upper left", fontsize=8.2, framealpha=0.92)
    s = json.loads(its.SUMMARY.read_text())
    a, b = s["scan_headline_lufs_level+slope"], s["scan_headline_lufs_hinge"]
    fig.suptitle(f"The data put the headline bend at {b['best_break']}–{a['best_break']} "
                 f"(≈95% sets {min(a['set95'] + b['set95'])}–{max(a['set95'] + b['set95'])}), not at the 2015–16 normalisation era",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p13_breakpoint_profile", n=int(pl.read_parquet(its.YEARLY).filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs"))["n"].sum()),
                   source=SRC, note=f"profile over single breaks 2004–2019 in yearly medians 2000–2022 (n = 23 years); {NOTE}")  # fmt: skip


def main() -> None:
    fig_fit()
    fig_sensitivity()
    fig_profile()


if __name__ == "__main__":
    main()
