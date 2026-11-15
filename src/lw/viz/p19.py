# ruff: noqa: E501  (labels)
"""P19 figures: specification curve of the post-2015 gap, and the genre-reweighted hero chart."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import polars as pl
from matplotlib.lines import Line2D

from lw.models import robustness as rb
from lw.normalisation import era_start
from lw.viz import theme

SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
FORMS = {
    ("straight", "2000-2022"): ("Straight pre-trend, 2000–22 (brief's test)", theme.SERIES[1]),
    ("straight", "2005-2022"): ("Straight pre-trend, 2005–22", theme.SERIES[3]),
    ("bend", "2000-2022"): ("Bend at 2007 + break (bend-first)", theme.SERIES[0]),
}
MARK = {2015: "o", 2016: "D"}
GROUPS = {"baseline": "Baseline", "sample": "Sample", "weighting": "Unit weighting", "matching": "Matching", "measurement": "Measurement",
          "genre": "Genre", "cohort": "Submission cohort"}  # fmt: skip


def fig_spec_curve() -> None:
    r = pl.read_parquet(rb.OUT).sort("gap").with_row_index("x")
    s = json.loads(rb.SUMMARY.read_text())
    specs = [k for k in rb.SPECS if k in set(r["spec"])]
    theme.apply()
    fig, (a, b) = plt.subplots(2, 1, figsize=(13, 11.5), sharex=True,
                               gridspec_kw={"height_ratios": [1.25, 2.1], "hspace": 0.04})  # fmt: skip
    x = r["x"].to_numpy()
    a.axhline(0, color=theme.TEXT, lw=0.9)
    for (form, win), (_lab, col) in FORMS.items():
        for brk, m in MARK.items():
            f = r.filter((pl.col("form") == form) & (pl.col("window") == win) & (pl.col("break") == brk))
            xx, g, se = f["x"].to_numpy(), f["gap"].to_numpy(), f["gap_se"].to_numpy()
            a.vlines(xx, g - 1.96 * se, g + 1.96 * se, color=col, lw=1.1, alpha=0.55)
            a.plot(xx, g, m, color=col, ms=4.6 if m == "o" else 4, mec="white", mew=0.4)
    h = r.filter(pl.col("spec") == "headline")
    a.plot(h["x"], h["gap"], "o", ms=10, mfc="none", mec=theme.TEXT, mew=1.1)
    a.set_ylabel("2016–22 (or 2015–22) gap vs\nfitted counterfactual (LU, 95% CI)")
    hs = [Line2D([], [], color=c, marker="o", ls="-", lw=1, label=lab) for lab, c in FORMS.values()]
    hs += [Line2D([], [], color=theme.TEXT_2, marker=m, ls="", label=f"break {k}") for k, m in MARK.items()]
    hs += [Line2D([], [], marker="o", ms=10, mfc="none", mec=theme.TEXT, ls="", label="headline sample")]
    a.legend(handles=hs, loc="lower right", fontsize=8.5, ncol=2, frameon=False)
    st, bd = s["straight|2000-2022"], s["bend|2000-2022"]
    a.text(0.01, 0.97,
           f"Straight 2000–22 trend: {st['n_estimates']} estimates, all negative, median {st['gap_median']:+.2f} LU, "
           f"{st['share_ci_below_0']:.0%} with CI below 0\n"
           f"Bend-first: median {bd['gap_median']:+.2f} LU, range {bd['gap_min']:+.2f} to {bd['gap_max']:+.2f}; CI below 0 only for "
           "all-codec samples and the late-submission cohort; the album-weighted series sits above 0",
           transform=a.transAxes, va="top", fontsize=8.8, color=theme.TEXT_2)  # fmt: skip
    a.grid(axis="x", visible=False)
    # indicator matrix
    rows: list[tuple[str, str]] = []  # (key, label)
    last = None
    for k in specs:
        grp = rb.SPECS[k][0]
        if grp != last:
            rows.append((f"_{grp}", GROUPS[grp]))
            last = grp
        rows.append((k, rb.SPECS[k][1]))
    rows.append(("_form", "Model form"))
    rows += [(f"form:{f}|{w}", lab.split(" (")[0]) for (f, w), (lab, _) in FORMS.items()]
    rows.append(("_break", "Break year"))
    rows += [(f"break:{k}", str(k)) for k in MARK]
    ypos = {k: i for i, (k, _) in enumerate(rows)}
    for i, (k, _) in enumerate(rows):
        if k.startswith("_"):
            continue
        b.axhline(i, color=theme.GRID, lw=0.6, zorder=0)
    col = [FORMS[(f, w)][1] for f, w in zip(r["form"], r["window"], strict=True)]
    for ycol in [
        [ypos[k] for k in r["spec"]],
        [ypos[f"form:{f}|{w}"] for f, w in zip(r["form"], r["window"], strict=True)],
        [ypos[f"break:{k}"] for k in r["break"]],
    ]:
        b.scatter(x, ycol, c=col, s=11, lw=0)
    b.set_yticks(range(len(rows)))
    b.set_yticklabels([lab for _, lab in rows], fontsize=8.3)
    for t, (k, _) in zip(b.get_yticklabels(), rows, strict=True):
        if k.startswith("_"):
            t.set_fontweight("bold")
            t.set_color(theme.TEXT)
    b.set_ylim(len(rows) - 0.5, -0.5)
    b.grid(False)
    b.set_xlabel("Estimates, sorted by gap")
    b.set_xlim(-1, len(x))
    b.tick_params(axis="x", labelbottom=False)
    fig.suptitle("Is there a post-2015 drop in median loudness? It depends on the model form, not the sample",
                 x=0.01, ha="left", fontsize=13.5, fontweight="bold", y=0.955)  # fmt: skip
    fig.text(0.01, 0.925,
             "Mean post-break gap in median est. LUFS against the fitted counterfactual, for every sample, weighting and model form. "
             "Against a straight pre-trend every spec shows a drop; once the rise is allowed to end in 2007 most estimates are ≈ 0.",
             fontsize=9.3, color=theme.TEXT_2)  # fmt: skip
    note = ("\nYearly (weighted) median est. LUFS per spec, segmented regression with Newey-West SEs (P13). Years with < 500 units dropped; "
            "cohorts also drop years with < 25% of their 2000–14 count (early cohort ends 2017, too few post years: not shown). "
            "≤160 kbps lossy copies read ~0.4 LU quiet (P18). No causal claim.")  # fmt: skip
    fig.subplots_adjust(top=0.88)
    theme.save_fig(fig, "p19_spec_curve", note=f"headline n = {int(h['n_units'][0]):,} units, 2000–22" + note, source=SRC)


def fig_reweighted_hero() -> None:
    y = pl.read_parquet(rb.YEARLY)
    s = json.loads(rb.SUMMARY.read_text())
    get = {k: y.filter(pl.col("spec") == k).sort("year") for k in ["headline", "genre_mb_mix", "genre_fixed_mix"]}
    lines = {"headline": ("Headline (as observed)", theme.SERIES[0]),
             "genre_mb_mix": ("(A) Reweighted to MusicBrainz genre mix of each year", theme.SERIES[1]),
             "genre_fixed_mix": ("(C) Fixed 2000–14 genre mix (within-genre change only)", theme.SERIES[2])}  # fmt: skip
    theme.apply()
    fig, (a, b) = plt.subplots(2, 1, figsize=(12, 8.2), sharex=True,
                               gridspec_kw={"height_ratios": [2.3, 1], "hspace": 0.08})  # fmt: skip
    es = era_start()
    for ax in (a, b):
        theme.shade_era(ax, start=es, end=2022.5, label="Normalisation\nera" if ax is a else "")
    h = get["headline"]
    for k, (lab, c) in lines.items():
        d = get[k]
        a.fill_between(d["year"], d["ci_lo"], d["ci_hi"], color=c, alpha=0.16, lw=0)
        a.plot(d["year"], d["median"], color=c, lw=2.2 if k == "headline" else 1.7, label=lab,
               ls="-" if k == "headline" else "--")  # fmt: skip
        if k != "headline":
            dd = d.join(h.select("year", h="median"), on="year")
            b.plot(dd["year"], dd["median"] - dd["h"], color=c, lw=1.7, ls="--")
    b.axhline(0, color=theme.SERIES[0], lw=1.6)
    a.set_ylabel("Median est. LUFS (95% CI)")
    b.set_ylabel("Difference from\nheadline (LU)")
    b.set_xlabel("Release year")
    b.set_xlim(1979.5, 2022.5)
    a.legend(loc="lower right", fontsize=9, frameon=False)
    A, C = s["genre_mb_mix_minus_headline"], s["genre_fixed_mix_minus_headline"]
    a.text(0.01, 0.97,
           f"(A) MB genre mix: {A['2000-14']:+.2f} LU in 2000–14, {A['2016-22']:+.2f} LU in 2016–22 (a level shift; same shape)\n"
           f"(C) fixed mix: {C['1980s']:+.2f} LU in the 1980s, {C['2000-14']:+.2f} in 2000–14, {C['2016-22']:+.2f} in 2016–22; peak year {C['peak_year']}",
           transform=a.transAxes, va="top", fontsize=9, color=theme.TEXT_2)  # fmt: skip
    fig.suptitle("Reweighting by genre moves the level, not the shape: the rise still ends ~2008 and 2016–22 stays on the plateau",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", y=0.955)  # fmt: skip
    n = int(h["n"].sum())
    note = ("\nHeadline sample, release years 1980–2022; reweighted lines use units with a genre (incl. the flagged rosamerica fallback, as in genre_mix.parquet). "
            "Weighted medians; 95% CI: release-group Poisson bootstrap (300 reps). est. LUFS = calibrated replay gain (P03).")  # fmt: skip
    theme.save_fig(fig, "p19_reweighted_hero", n=n, note=note, source=SRC)


def main() -> None:
    fig_spec_curve()
    fig_reweighted_hero()


if __name__ == "__main__":
    main()
