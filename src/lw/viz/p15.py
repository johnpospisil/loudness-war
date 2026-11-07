# ruff: noqa: E501  (labels)
"""P15 figures: genre small multiples (brief chart 3), break forest plot, posterior predictive
checks."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from lw.models import genre_hier as gh
from lw.normalisation import era_start
from lw.viz import theme

SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
NOTE = (
    "\nheadline = release years 1980–2022, tier A/B, not a reissue, ≥1 lossless submission, recording's first appearance; "
    "genres from MusicBrainz tags (classifier-only units excluded); est. LUFS / LRA = calibrated Essentia proxies (P03)"
)
MAIN = [
    ("lufs_median", "Median est. LUFS"),
    ("lufs_p90", "P90 est. LUFS (loud end)"),
    ("lra_median", "Median est. LRA"),
]


def _mu(d: dict, j: int, tt: np.ndarray, counterfactual: bool = False) -> np.ndarray:
    """Posterior draws of the fitted line for genre j at years tt: (draws, len(tt))."""
    b, k = int(d["brk"]), int(d["hinge_k"])
    s = tt - b
    post = (tt >= b).astype(float)
    if k > 0:
        m = (d["a"][:, j, None] + d["b1"][:, j, None] * np.minimum(tt - k, 0)
             + d["b2"][:, j, None] * np.maximum(tt - k, 0))  # fmt: skip
    else:
        m = d["a"][:, j, None] + d["b"][:, j, None] * s
    if not counterfactual:
        m = m + d["c"][:, j, None] * post + d["d"][:, j, None] * (s * post)
    return m


def _eff():
    return pl.read_parquet(gh.EFFECTS)


def fig_small_multiples() -> None:
    cells = pl.read_parquet(gh.CELLS).filter(
        (pl.col("source") == "tags") & (pl.col("year") >= 1995)
    )
    eff = _eff()
    dm, dp = gh.load_draws("lufs_median|bend"), gh.load_draws("lufs_p90|bend")
    order = list(
        eff.filter((pl.col("fit") == "lufs_median|bend") & (pl.col("genre") != "_pooled")).sort(
            "gap"
        )["genre"]
    )
    theme.apply()
    fig, axes = plt.subplots(3, 4, figsize=(15.5, 11.2), sharex=True)
    tt = np.linspace(2000, 2022, 221)
    span = max(float(cells.filter(pl.col("genre") == g)["lufs_p90"].max()) - float(cells.filter(pl.col("genre") == g)["lufs_median"].min())
               for g in order) + 1.0  # common span: every panel on the same LU scale  # fmt: skip
    for ax, g in zip(axes.flat, order, strict=True):
        theme.shade_era(ax, start=era_start(), end=2022.5, label="")
        c = cells.filter(pl.col("genre") == g).sort("year")
        for metric, d, col in [
            ("lufs_median", dm, theme.SERIES[0]),
            ("lufs_p90", dp, theme.SERIES[1]),
        ]:
            ax.errorbar(c["year"], c[metric], yerr=1.96 * c[f"{metric}_se"].to_numpy(), fmt="o", ms=2.8,
                        color=col, lw=0.8, capsize=0, alpha=0.85)  # fmt: skip
            j = list(d["genres"]).index(g)
            m, m0 = _mu(d, j, tt), _mu(d, j, tt, counterfactual=True)
            ax.fill_between(
                tt, *np.quantile(m, [0.025, 0.975], axis=0), color=col, alpha=0.18, lw=0
            )
            ax.plot(tt, m.mean(0), color=col, lw=1.8)
            post = tt >= int(d["brk"])
            ax.plot(tt[post], m0.mean(0)[post], color=theme.TEXT, lw=1.1, ls=(0, (3, 2)))
        mid = (float(c["lufs_median"].min()) + float(c["lufs_p90"].max())) / 2
        ax.set_ylim(mid - span / 2, mid + span / 2)
        e = {
            r["metric"]: r
            for r in eff.filter(
                (pl.col("genre") == g) & pl.col("fit").is_in(["lufs_median|bend", "lufs_p90|bend"])
            ).iter_rows(named=True)
        }
        n = int(c.filter(pl.col("year").is_between(*gh.FIT))["n"].sum())
        em, ep = e["lufs_median"], e["lufs_p90"]
        ax.set_title(f"{gh.LABELS[g]}  (n = {n:,})", loc="left", fontsize=10, pad=17)
        ax.text(0, 1.015, f"2016–22 gap: median {em['gap']:+.2f} [{em['gap_lo']:+.2f}, {em['gap_hi']:+.2f}] · "
                f"P90 {ep['gap']:+.2f} [{ep['gap_lo']:+.2f}, {ep['gap_hi']:+.2f}]",
                transform=ax.transAxes, fontsize=7.6, color=theme.TEXT_2, va="bottom")  # fmt: skip
        ax.set_xlim(1994.5, 2022.5)
    for a in axes[:, 0]:
        a.set_ylabel("Est. LUFS")
    for a in axes[-1]:
        a.set_xlabel("Release year")
    from matplotlib.lines import Line2D

    h = [Line2D([], [], color=theme.SERIES[1], marker="o", lw=1.8, ms=4, label="P90 (loud end): cells ± 95% CI and posterior fit"),
         Line2D([], [], color=theme.SERIES[0], marker="o", lw=1.8, ms=4, label="median: cells ± 95% CI and posterior fit (band 95%)"),
         Line2D([], [], color=theme.TEXT, lw=1.1, ls=(0, (3, 2)), label="counterfactual: no 2016 terms (bend at 2007 kept)")]  # fmt: skip
    fig.legend(
        handles=h,
        loc="upper right",
        bbox_to_anchor=(0.995, 0.965),
        fontsize=8.4,
        ncol=3,
        frameon=False,
    )
    s = json.loads(gh.SUMMARY.read_text())["fits"]
    fm, fp = s["lufs_median|bend"], s["lufs_p90|bend"]

    def k(x):
        return "none" if x == 0 else f"only {x} of {fm['n_genres']}"

    fig.suptitle(f"Genre by genre, no general post-2016 drop: once each genre's 2007 bend is allowed for, {k(fm['n_gap_neg_95'])} sits clearly below "
                 f"its own trend in median loudness, and {k(fp['n_gap_neg_95'])} at the loud end",
                 x=0.01, y=0.995, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    fig.text(0.01, 0.962, f"Panels ordered from the largest post-2016 drop in median loudness (top left) to the largest rise; every panel spans {span:.0f} LU; gap = mean 2016–22 difference from the genre’s own counterfactual (LU, 95% CrI); shaded = normalisation era",
             fontsize=9.2, color=theme.TEXT_2)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    theme.save_fig(fig, "p15_genre_small_multiples", n=json.loads(gh.SUMMARY.read_text())["n_units_fit"], source=SRC,
                   note=f"partially pooled Bayesian segmented model on genre × year cells 2000–2022 (PyMC; AR(1) residuals; cell SEs from a release-group bootstrap); {NOTE}")  # fmt: skip


def fig_forest() -> None:
    eff = _eff()
    s = json.loads(gh.SUMMARY.read_text())["fits"]
    order = list(
        eff.filter((pl.col("fit") == "lufs_median|bend") & (pl.col("genre") != "_pooled")).sort(
            "gap", descending=True
        )["genre"]
    )
    rows = order + ["_pooled"]
    theme.apply()
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 7.4), sharey=True)
    ypos = {g: i for i, g in enumerate(rows)}
    for ax, (metric, title) in zip(axes, MAIN, strict=True):
        ax.axvline(0, color=theme.TEXT, lw=0.9)
        ax.axhspan(len(rows) - 1.5, len(rows) - 0.5, color=theme.ERA_FILL, lw=0)
        for form, dy, mk, fc, lab in [("bend", 0.17, "o", None, "bend at 2007 first, then 2016 terms"),
                                      ("straight", -0.17, "o", "none", "straight 2000–15 pre-trend (brief's form)")]:  # fmt: skip
            z = eff.filter(pl.col("fit") == f"{metric}|{form}")
            for r in z.iter_rows(named=True):
                y = ypos[r["genre"]] + dy
                col = theme.SERIES[0] if form == "bend" else theme.MUTED
                ax.plot(
                    [r["gap_lo"], r["gap_hi"]], [y, y], color=col, lw=1.6 if form == "bend" else 1.1
                )
                ax.plot(r["gap"], y, mk, color=col, mfc=col if fc is None else "white", ms=5.5 if form == "bend" else 5,
                        label=lab if r["genre"] == rows[0] else None)  # fmt: skip
        f = s[f"{metric}|bend"]
        fs = s[f"{metric}|straight"]
        ax.set_title(f"{title}\nclearly below / above (95%): bend {f['n_gap_neg_95']} / {f['n_gap_pos_95']}; straight {fs['n_gap_neg_95']} / {fs['n_gap_pos_95']}",
                     loc="left", fontsize=10)  # fmt: skip
        ax.set_xlabel("Mean 2016–22 gap vs the genre's own counterfactual (LU, 95% CrI)")
    axes[0].set_yticks(range(len(rows)))
    axes[0].set_yticklabels([gh.LABELS.get(g, "All genres (pooled mean)") for g in rows])
    axes[0].set_ylim(-0.6, len(rows) - 0.4)
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(
        h, lab, loc="upper left", bbox_to_anchor=(0.115, 0.905), fontsize=8.8, ncol=2, frameon=False
    )
    fm, fst = s["lufs_median|bend"], s["lufs_median|straight"]
    loo = json.loads(gh.SUMMARY.read_text()).get("loo", {})
    lm = loo.get("lufs_median")
    fig.suptitle(f"Genres ranked by post-2016 change in median loudness: pooled gap {fm['pooled_gap'][0]:+.2f} LU "
                 f"[{fm['pooled_gap'][1]:+.2f}, {fm['pooled_gap'][2]:+.2f}] once the 2007 bend is allowed for,\n"
                 f"{fst['pooled_gap'][0]:+.2f} against the brief's straight 2000–15 trend, which fits worse in every metric"
                 + (f" (LOO: bend better by {lm['diff']:.0f} ± {lm['se']:.0f} elpd for median LUFS)" if lm else ""),
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.875))
    theme.save_fig(fig, "p15_genre_break_forest", n=json.loads(gh.SUMMARY.read_text())["n_units_fit"], source=SRC,
                   note=f"gap = level change + 3 × slope change (mean over 2016–22); ordered by the median-loudness gap (bend form); 'clearly' = posterior P(gap < 0) or P(gap > 0) > 0.95; {NOTE}")  # fmt: skip


def fig_ppc() -> None:
    s = json.loads(gh.SUMMARY.read_text())["fits"]
    theme.apply()
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
    # (a) PIT ECDF minus uniform for the six main fits
    ax = axes[0]
    n = None
    for i, (metric, title) in enumerate(MAIN):
        for form, ls in [("bend", "-"), ("straight", (0, (3, 2)))]:
            d = gh.load_draws(f"{metric}|{form}")
            pit = (d["yrep"] < d["y"]).mean(0)
            n = len(pit)
            u = np.linspace(0, 1, 201)
            ax.plot(u, (pit[:, None] <= u).mean(0) - u, color=theme.SERIES[i], ls=ls, lw=1.5,
                    label=f"{title.split(' (')[0]}, {form}")  # fmt: skip
    band = 1.36 / np.sqrt(n)
    ax.axhspan(-band, band, color=theme.GRID, alpha=0.7, lw=0)
    ax.axhline(0, color=theme.TEXT, lw=0.8)
    ax.set_xlabel("PIT value")
    ax.set_ylabel("ECDF(PIT) − uniform")
    ax.set_title("(a) Calibration: PIT ECDF (grey = 95% KS band)", loc="left", fontsize=10.5)
    ax.legend(fontsize=7.4, loc="lower left", framealpha=0.92)
    ax.set_ylim(-0.2, 0.2)
    # (b) coverage of posterior predictive intervals, all fits
    ax = axes[1]
    ids = list(s)
    yy = np.arange(len(ids))
    ax.barh(
        yy - 0.2,
        [s[i]["cover50"] for i in ids],
        height=0.38,
        color=theme.SERIES[0],
        label="50% interval",
    )
    ax.barh(
        yy + 0.2,
        [s[i]["cover95"] for i in ids],
        height=0.38,
        color=theme.SERIES[2],
        label="95% interval",
    )
    for x in (0.5, 0.95):
        ax.axvline(x, color=theme.TEXT, lw=0.9, ls=(0, (3, 2)))
    ax.set_yticks(yy)
    ax.set_yticklabels([i.replace("|", " · ") for i in ids], fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Share of cells inside the posterior predictive interval")
    ax.set_title("(b) Interval coverage, every fit", loc="left", fontsize=10.5)
    ax.legend(fontsize=7.8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False)
    ax.set_title("(b) Interval coverage, every fit", loc="left", fontsize=10.5, pad=22)
    # (c) observed vs predicted, median LUFS (bend)
    ax = axes[2]
    d = gh.load_draws("lufs_median|bend")
    pm_, lo, hi = d["yrep"].mean(0), *np.quantile(d["yrep"], [0.025, 0.975], axis=0)
    post = d["t"] >= int(d["brk"])
    for msk, col, lab in [
        (~post, theme.MUTED, "2000–15 cells"),
        (post, theme.SERIES[1], "2016–22 cells"),
    ]:
        ax.errorbar(d["y"][msk], pm_[msk], yerr=[pm_[msk] - lo[msk], hi[msk] - pm_[msk]], fmt="o", ms=3, color=col,
                    lw=0.6, alpha=0.8, label=lab)  # fmt: skip
    r = [float(min(d["y"].min(), lo.min())) - 0.5, float(max(d["y"].max(), hi.max())) + 0.5]
    ax.plot(r, r, color=theme.TEXT, lw=0.9)
    ax.set_xlabel("Observed cell median (est. LUFS)")
    ax.set_ylabel("Posterior predictive (mean, 95% interval)")
    ax.set_title(
        "(c) Median est. LUFS, bend form: observed vs predicted", loc="left", fontsize=10.5
    )
    ax.legend(fontsize=7.8, loc="upper left", framealpha=0.92)
    worst = max(s[i]["max_rhat"] for i in ids)
    ess = min(s[i]["min_ess_bulk"] for i in ids)
    div = sum(s[i]["divergences"] for i in ids)
    c95 = [s[i]["cover95"] for i in ids]
    fig.suptitle(f"Posterior predictive checks: the model reproduces the cells, slightly conservatively (95% coverage {min(c95):.2f}–{max(c95):.2f});\n"
                 f"all {len(ids)} fits converged (R-hat ≤ {worst:.3f}, bulk ESS ≥ {ess:.0f}, {div} divergences)",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p15_ppc", n=json.loads(gh.SUMMARY.read_text())["n_units_fit"], source=SRC,
                   note=f"one-step-ahead posterior predictive (AR(1) conditional likelihood) on genre × year cells 2000–2022; 4 chains × 2,000 draws; {NOTE}")  # fmt: skip


def main() -> None:
    fig_small_multiples()
    fig_forest()
    fig_ppc()


if __name__ == "__main__":
    main()
