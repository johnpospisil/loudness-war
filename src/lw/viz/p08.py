"""P08 figure: share of submissions by match tier and year, plus the reissue flags by year."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np

from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
M = ROOT / "data/interim/ab_matched.parquet"
SUMMARY = ROOT / "data/interim/ab_matched_summary.json"
SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
Y0, Y1 = 1980, 2022


def fig_tiers() -> None:
    s = json.loads(SUMMARY.read_text())
    c = duckdb.connect()
    rows = c.execute(f"""
        select year, match_tier, count(*),
               sum(reissue_date::int), sum((reissue_keyword and not reissue_date)::int),
               sum((reissue_format and not reissue_date and not reissue_keyword)::int)
        from read_parquet('{M}') where year between {Y0} and {Y1} and match_tier is not null
        group by 1, 2""").fetchall()
    years = np.arange(Y0, Y1 + 1)
    tiers = ["A", "B", "C"]
    n = np.zeros((3, len(years)))
    re = np.zeros((3, len(years)))
    for y, t, k, rd, rk, rf in rows:
        i = y - Y0
        n[tiers.index(t), i] += k
        re[:, i] += (rd, rk, rf)
    tot = n.sum(0)
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    labels = ["A: release tag", "B: date + album title", "C: earliest release"]
    colors = [theme.SERIES[0], theme.SERIES[1], theme.SERIES[3]]
    a1.stackplot(years, n / tot * 100, colors=colors, labels=labels, alpha=0.9, lw=0)
    a1.set_ylim(0, 100)
    a1.set_xlim(Y0, Y1)
    a1.set_ylabel("Share of matched submissions (%)")
    a1.set_title("How each submission was matched", loc="left", fontsize=10.5)
    a1.legend(loc="lower center", bbox_to_anchor=(0.62, 0.02), fontsize=8.5, framealpha=0.9)
    ax_n = a1.twinx()
    ax_n.plot(years, tot / 1e6, color=theme.TEXT, lw=1.2, ls=(0, (3, 2)))
    ax_n.set_ylabel("Matched submissions per year (millions, dashed)", fontsize=8.5)
    ax_n.grid(False)
    ax_n.set_ylim(0, tot.max() / 1e6 * 1.15)

    names = ["date: year > group's first year + 1", "+ title keyword only", "+ format only"]
    rc = [theme.SERIES[2], theme.SERIES[4], theme.MUTED]
    a2.stackplot(years, re / tot * 100, colors=rc, labels=names, alpha=0.9, lw=0)
    a2.set_xlim(Y0, Y1)
    a2.set_ylabel("Flagged as reissue (% of matched)")
    a2.set_title("Reissue flag, by which rule catches it", loc="left", fontsize=10.5)
    a2.legend(loc="upper right", fontsize=8.5, framealpha=0.9)
    for a in (a1, a2):
        a.set_xlabel("Release year of the matched release")

    t = s["tiers"]
    un = t.get("unmatched", 0) / s["submissions"]
    fig.suptitle(
        f"{t['A'] / s['submissions']:.0%} of submissions match on their own release tag; "
        f"{s['flags_among_matched']['is_reissue']:.0%} of matched ones are reissues",
        x=0.01, ha="left", fontsize=13, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(
        fig,
        "p08_match_tiers",
        n=int(tot.sum()),
        source=SRC,
        note=f"matched submissions {Y0}-{Y1}; {un:.1%} of all submissions unmatched "
        "(recording not in MB or on no release)",
    )


if __name__ == "__main__":
    fig_tiers()
