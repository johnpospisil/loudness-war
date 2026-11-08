# ruff: noqa: E501  (labels)
"""P17 figures: descriptor trends, density vs loudness, genre x descriptor change, classical /
other composition."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import LinearSegmentedColormap

from lw.models import descriptors as ds
from lw.models.genre_hier import LABELS
from lw.normalisation import era_start
from lw.viz import theme

SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
NOTE = (
    "\nheadline = release years 1980–2022, tier A/B, not a reissue, ≥1 lossless submission, recording's first appearance; "
    "descriptors = Essentia (AcousticBrainz) medians over each unit's lossless submissions"
)
ORDER = [
    "average_loudness",
    "dynamic_complexity",
    "crest_db",
    "flatness_db",
    "spectral_complexity",
    "onset_rate",
    "centroid_hz",
    "silence",
]
PCOL = {
    "1990–99": theme.SEQ_BLUE[3],
    "2000–08": theme.SEQ_BLUE[7],
    "2009–15": theme.SEQ_BLUE[11],
    "2016–22": theme.SERIES[1],
}


def _summary():
    return json.loads(ds.SUMMARY.read_text())


def fig_trends() -> None:
    y = pl.read_parquet(ds.YEARLY)
    s = _summary()
    theme.apply()
    fig, axes = plt.subplots(2, 4, figsize=(16, 7.6), sharex=True)
    for ax, c in zip(axes.flat, ORDER, strict=True):
        lab, unit, denser = ds.DESC[c]
        z = y.filter(pl.col("desc") == c).sort("year")
        theme.shade_era(ax, start=era_start(), end=2022.5, label="")
        ax.fill_between(z["year"], z["p25"], z["p75"], color=theme.SEQ_BLUE[0], lw=0, label="IQR")
        ax.fill_between(
            z["year"], z["lo"], z["hi"], color=theme.SEQ_BLUE[4], lw=0, label="95% CI of median"
        )
        ax.plot(z["year"], z["median"], color=theme.SERIES[0], lw=2, label="median")
        ax.axvline(2009, color=theme.MUTED, lw=0.8, ls=(0, (1, 2)))
        p = s["period_means"][c]
        ax.set_title(f"{lab} ({unit})", loc="left", fontsize=10)
        txt = f"denser = {denser}" if denser else ""
        txt += ("\n" if txt else "") + f"2009–15 {p['2009–15']:.3g} → 2016–22 {p['2016–22']:.3g}"
        ax.text(0.02, 0.97, txt, transform=ax.transAxes, va="top", fontsize=7.8, color=theme.TEXT_2,
                bbox=dict(fc=theme.SURFACE, ec="none", alpha=0.85, pad=1.5))  # fmt: skip
        ax.set_xlim(1979.5, 2022.5)
    for a in axes[1]:
        a.set_xlabel("Release year")
    axes[0, 0].legend(loc="lower right", fontsize=7.6, framealpha=0.9)
    fig.suptitle("Dynamics tracked loudness (denser until ~2009, flat since); spectra kept getting flatter and darker after 2009, with no turn at 2016",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    fig.text(0.01, 0.935, "Yearly medians of Essentia descriptors, headline sample; dotted line = 2009 (est. LUFS peak, P12); shaded = normalisation era. "
             "No sample peak exists in AcousticBrainz, so 'crest' is a frame-level proxy (loudest ÷ mean 46-ms frame RMS), not PLR.",
             fontsize=9, color=theme.TEXT_2)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    theme.save_fig(fig, "p17_descriptor_trends", n=s["n_units"], source=SRC,
                   note=f"95% CI = release-group cluster bootstrap (300 reps); {NOTE}")  # fmt: skip


def fig_density() -> None:
    tab = pl.read_parquet(ds.DENSITY)
    s = _summary()
    theme.apply()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    boxpos = {"average_loudness": (0.98, 0.04, "right", "bottom"), "crest_db": (0.02, 0.04, "left", "bottom"),
              "flatness_db": (0.02, 0.04, "left", "bottom"), "spectral_complexity": (0.02, 0.97, "left", "top")}  # fmt: skip
    for ax, c in zip(
        axes.flat,
        ["average_loudness", "crest_db", "flatness_db", "spectral_complexity"],
        strict=True,
    ):
        lab, unit, denser = ds.DESC[c]
        for per, col in PCOL.items():
            z = tab.filter(pl.col("per") == per).sort("lbin")
            ax.plot(
                z["lbin"] + 0.5,
                z[c],
                "o-",
                color=col,
                ms=3.5,
                lw=1.8 if per == "2016–22" else 1.4,
                label=per,
            )
        e = s["density_effects"][c]
        txt = "Period effect vs 2009–15 at the same est. LUFS bin and genre:\n" + "\n".join(
            f"  {p}: {e[p]['est']:+.3g} ± {1.96 * e[p]['se']:.2g}  ({e[p]['est'] / e[p]['sd']:+.2f} SD)"
            for p in ("1990–99", "2000–08", "2016–22")
        )
        bx, by_, ha, va = boxpos[c]
        ax.text(bx, by_, txt, transform=ax.transAxes, ha=ha, va=va, fontsize=7.8, family="monospace",
                bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.3"))  # fmt: skip
        ax.set_title(f"{lab} ({unit}); denser = {denser}", loc="left", fontsize=10.5)
        ax.set_xlabel("Est. LUFS (1-LU bins)")
        ax.set_xlim(-24.5, -3.5)
    axes[0, 1].legend(
        title="release years", loc="upper right", fontsize=8.2, title_fontsize=8.2, framealpha=0.92
    )
    fig.suptitle("At the same loudness, 2016–22 dynamics match 2009–15 (average loudness, crest), but spectra are flatter (+0.16 SD) and a little less complex:\n"
                 "denser in timbre, not in dynamics",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p17_density_vs_loudness", n=s["n_units"], source=SRC,
                   note="lines = median per (period, 1-LU est. LUFS bin) with ≥ 200 units; period effects: OLS descriptor ~ period + LUFS bin + genre on a seeded 25% sample "
                        f"of tag-genre units 1990–2022, release-group cluster SEs, ± = 95%; SD = descriptor's spread in that sample; {NOTE}")  # fmt: skip


def fig_genre() -> None:
    g = pl.read_parquet(ds.GENRE)
    s = _summary()
    cols = ["lufs", *ORDER]
    sign = {c: (-1 if ds.DESC.get(c, ("", "", "higher"))[2] == "lower" else 1) for c in cols}
    genres = list(g.filter(pl.col("desc") == "lufs").sort("change", descending=True)["genre"])
    M = np.array(
        [
            [
                sign[c] * g.filter((pl.col("genre") == gg) & (pl.col("desc") == c))["change_sd"][0]
                for c in cols
            ]
            for gg in genres
        ]
    )
    theme.apply()
    fig, ax = plt.subplots(figsize=(13.5, 7.2))
    cmap = LinearSegmentedColormap.from_list("div", [theme.DIV_NEG, theme.DIV_MID, theme.DIV_POS])
    lim = 0.5
    ax.imshow(M, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    for i, gg in enumerate(genres):
        for j, c in enumerate(cols):
            r = g.filter((pl.col("genre") == gg) & (pl.col("desc") == c)).row(0, named=True)
            sig = (r["lo"] > 0) or (r["hi"] < 0)
            v = r["change"]
            fmt = (
                f"{v:+.0f}"
                if c == "centroid_hz"
                else (f"{v:+.3f}" if c in ("average_loudness", "silence") else f"{v:+.2f}")
            )
            ax.text(j, i, fmt, ha="center", va="center", fontsize=8, fontweight="bold" if sig else "normal",
                    color=theme.TEXT if abs(M[i, j]) < 0.35 else "white")  # fmt: skip
    heads = {"lufs": "Est. LUFS\n(louder +)", "average_loudness": "Avg loudness\n(denser +)", "dynamic_complexity": "Dyn. complexity\n(denser = −)",
             "crest_db": "Frame crest\n(denser = −)", "flatness_db": "Flatness 0–1\n(denser +)", "spectral_complexity": "Spectral cplx\n(denser +)",
             "onset_rate": "Onset rate\n(denser +)", "centroid_hz": "Centroid Hz\n(brighter +)", "silence": "Near-silent\nshare (+)"}  # fmt: skip
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([heads[c] for c in cols], fontsize=8.6)
    ax.set_yticks(range(len(genres)))
    ax.set_yticklabels([LABELS[x] for x in genres])
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.suptitle("2009–15 → 2016–22 by genre: dynamics moved with loudness (quieter genres got more dynamic); spectra got flatter and darker almost everywhere",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.text(0.01, 0.925, "Cell text = change in native units (bold = 95% release-group bootstrap CI excludes 0); colour = change in SDs of the descriptor's 2000–22 spread, "
             "oriented so red = louder / denser / brighter / more silence", fontsize=9, color=theme.TEXT_2)  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.915))
    theme.save_fig(fig, "p17_genre_descriptor_change", n=s["n_units"], source=SRC,
                   note=f"genres from MusicBrainz tags (classifier-only units excluded); rows ordered by the est. LUFS change; {NOTE}")  # fmt: skip


def fig_composition() -> None:
    comp = pl.read_parquet(ds.COMPOSITION)
    s = _summary()["composition"]
    theme.apply()
    fig, axes = plt.subplots(
        1, 3, figsize=(17, 5.6), gridspec_kw={"width_ratios": [1.1, 1.1, 0.75]}
    )
    c = comp.filter(pl.col("genre") == "classical").with_columns(
        (pl.col("n") / pl.col("n").sum().over("year")).alias("share")
    )
    subs = ["canonical repertoire", "contemporary / crossover / screen", "untagged / other tags"]
    cols = [theme.SERIES[0], theme.SERIES[1], theme.MUTED]
    for sub, col in zip(subs, cols, strict=True):
        z = c.filter(pl.col("sub") == sub).sort("year")
        axes[0].plot(z["year"], z["share"], "o-", color=col, ms=3, lw=1.6, label=sub)
        zz = z.filter(pl.col("n") >= 100)
        axes[1].plot(zz["year"], zz["lufs"], "o-", color=col, ms=3, lw=1.6, label=sub)
    for a in axes[:2]:
        theme.shade_era(a, start=era_start(), end=2022.5, label="")
        a.set_xlabel("Release year")
        a.set_xlim(1999.5, 2022.5)
    axes[0].set_ylabel("Share of classical units")
    axes[0].set_title(
        "(a) Classical: sub-genre mix (release-group tags)", loc="left", fontsize=10.5
    )
    axes[0].legend(fontsize=8, loc="upper left", framealpha=0.92)
    axes[1].set_ylabel("Median est. LUFS")
    axes[1].set_title(
        "(b) Classical: median loudness by sub-genre (cells ≥ 100 units)", loc="left", fontsize=10.5
    )
    ax = axes[2]
    ctl = _summary()["controls"]
    rows = []
    for g, lab in (("classical", "Classical"), ("other", "Other")):
        r = s[g]
        rows += [(f"{lab}: observed (median)", r["raw_change"], r["raw_lo"], r["raw_hi"], theme.MUTED),
                 (f"{lab}: at 2009–15 sub-genre (tag) mix", r["reweighted_change"], r["rew_lo"], r["rew_hi"], theme.SERIES[1]),
                 (f"{lab}: mean, unadjusted (OLS)", ctl[g]["unadjusted"]["est"], ctl[g]["unadjusted"]["lo"], ctl[g]["unadjusted"]["hi"], theme.TEXT_2),
                 (f"{lab}: mean, net of record label", ctl[g]["label_fe"]["est"], ctl[g]["label_fe"]["lo"], ctl[g]["label_fe"]["hi"], theme.SERIES[0]),
                 (f"{lab}: net of label + near-silent share", ctl[g]["label_fe_silence"]["est"], ctl[g]["label_fe_silence"]["lo"], ctl[g]["label_fe_silence"]["hi"], theme.SEQ_BLUE[11])]  # fmt: skip
    ys = []
    for i, (_lab, e, lo, hi, col) in enumerate(rows):
        yy = len(rows) - 1 - i + (0.5 if i < 5 else 0)
        ys.append(yy)
        ax.errorbar([e], [yy], xerr=[[e - lo], [hi - e]], fmt="o", color=col, ms=6, capsize=3)
    ax.axvline(0, color=theme.TEXT, lw=0.9)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.2)
    ax.set_xlim(-0.6, 1.0)
    ax.set_ylim(-0.7, len(rows) + 0.2)
    ax.set_xlabel("Est. LUFS, 2016–22 minus 2009–15 (LU, 95% CI)")
    ax.set_title("(c) How much of the rise is composition?", loc="left", fontsize=10.5)
    c2 = ctl["classical"]
    fig.suptitle(f"Classical's post-2016 rise is composition, but by record label, not sub-genre: {c2['unadjusted']['est']:+.2f} LU unadjusted, "
                 f"{c2['label_fe']['est']:+.2f} within labels, {c2['label_fe_silence']['est']:+.2f} with less silence also held fixed",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p17_classical_composition", n=int(comp.filter(pl.col("year") >= 2009)["n"].sum()), source=SRC,
                   note="(a, b): only ~30% of classical release groups carry a sub-genre tag beyond 'classical'; sub-genre = first matching rule over the release group's positive-vote MusicBrainz tags (most-voted first);\n"
                        f"'other' uses soundtrack / world / experimental / spoken groups; label models: OLS on units 2009–22, labels with ≥ 300 units as fixed effects (others pooled), release-group cluster SEs;\nmedian CIs = release-group cluster bootstrap (200 reps); {NOTE}")  # fmt: skip


def main() -> None:
    fig_trends()
    fig_density()
    fig_genre()
    fig_composition()


if __name__ == "__main__":
    main()
