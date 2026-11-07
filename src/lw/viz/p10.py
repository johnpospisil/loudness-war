"""P10 figures: genre mix AcousticBrainz vs MusicBrainz, and genre coverage by source."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np

from lw.build.genres import GENRES, LABELS
from lw.normalisation import era_start
from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
MIX = ROOT / "data/processed/genre_mix.parquet"
SUMMARY = ROOT / "data/processed/genre_summary.json"
SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
Y0, Y1 = 1980, 2022
# panel order: largest MB share first
ORDER = ["electronic", "rock", "other", "pop", "hip_hop", "metal", "jazz", "classical",
         "folk_country", "punk", "rnb_soul", "reggae"]  # fmt: skip


def _smooth(y: np.ndarray, k: int = 3) -> np.ndarray:
    """Centred k-year moving average (edges use the available years)."""
    out = np.full_like(y, np.nan, dtype=float)
    for i in range(len(y)):
        lo, hi = max(0, i - k // 2), min(len(y), i + k // 2 + 1)
        out[i] = np.nanmean(y[lo:hi])
    return out


def fig_mix(c) -> None:
    rows = c.execute(f"""select year, genre, mb_share, ab_unit_share, ab_lossless_share,
        mb_rg, ab_units from read_parquet('{MIX}') order by 1""").fetchall()
    years = np.arange(Y0, Y1 + 1)
    d = {g: np.full((3, len(years)), np.nan) for g in GENRES}
    n_mb = n_ab = 0
    for y, g, a, b, ll, nm, na in rows:
        d[g][:, y - Y0] = [100 * a, 100 * b, 100 * (ll or 0)]
        n_mb += nm
        n_ab += na
    theme.apply()
    fig, axes = plt.subplots(3, 4, figsize=(13, 8.4), sharex=True)
    for ax, g in zip(axes.flat, ORDER, strict=True):
        theme.shade_era(ax, start=era_start(), end=Y1 + 0.5, label="")
        mb, ab, ll = (_smooth(v) for v in d[g])
        ax.plot(years, mb, color=theme.MUTED, lw=2.2, label="MusicBrainz release groups")
        ax.plot(years, ab, color=theme.SERIES[0], lw=1.8, label="AcousticBrainz main sample")
        ax.plot(years, ll, color=theme.SERIES[1], lw=1.4, ls=(0, (3, 2)),
                label="AcousticBrainz lossless (headline)")  # fmt: skip
        ax.set_title(LABELS[g], loc="left", fontsize=10.5, fontweight="bold")
        top = np.nanmax([mb, ab, ll])
        ax.set_ylim(0, top * 1.15)
        ax.set_xlim(Y0 - 0.5, Y1 + 0.5)
        ax.set_xticks([1980, 2000, 2020])
        ax.tick_params(labelsize=8.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("Share of year (%)", fontsize=9)
    h, lab = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper left", bbox_to_anchor=(0.01, 0.955), ncol=3, fontsize=9.5)
    fig.suptitle(
        "AcousticBrainz over-represents rock and classical and under-represents hip-hop, "
        "most of all after 2015",
        x=0.01, y=0.995, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    theme.save_fig(fig, "p10_genre_mix_ab_vs_mb", n=n_ab, source=SRC,
                   note=f"AB: main-sample units (recording × release) with a genre; MB: "
                        f"{n_mb:,} Album/EP/Single release groups with a genre, by first-release "
                        f"year; 3-year moving average; shaded = normalisation era")  # fmt: skip


SOURCES = [
    ("rg", "Release-group tags", theme.SERIES[0]),
    ("release", "Release tags", theme.SERIES[2]),
    ("recording", "Recording tags", theme.SERIES[5]),
    ("artist", "Artist tags", theme.SERIES[3]),
    ("hl", "AB audio classifier (flagged)", theme.SERIES[7]),
    ("none", "No genre", theme.MUTED),
]


def fig_coverage(c) -> None:
    rows = c.execute(f"""select year, coalesce(genre_source, 'none'), count(*)
        from read_parquet('{T}') where in_main group by all""").fetchall()
    s = json.loads(SUMMARY.read_text())
    years = np.arange(Y0, Y1 + 1)
    n = {k: np.zeros(len(years)) for k, *_ in SOURCES}
    for y, k, v in rows:
        n[k][y - Y0] += v
    tot = sum(n.values())
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5.4), gridspec_kw={"width_ratios": [1.9, 1]})
    bottom = np.zeros(len(years))
    for k, lab, col in SOURCES:
        share = 100 * n[k] / tot
        a1.bar(years, share, bottom=bottom, color=col, width=0.85, lw=0, label=lab)
        bottom += share
    a1.set_ylim(0, 100)
    a1.set_xlim(Y0 - 0.6, Y1 + 0.6)
    a1.set_ylabel("Share of main-sample units (%)")
    a1.set_xlabel("Release year")
    a1.set_title("Where each unit's genre comes from (first source with a mapped tag)",
                 loc="left", fontsize=10.5, pad=14)  # fmt: skip
    a1.axvline(era_start() - 0.5, color=theme.TEXT, lw=1, ls=(0, (3, 2)))
    a1.text(era_start() - 0.3, 101, "normalisation era →", fontsize=8, color=theme.TEXT_2,
            va="bottom")  # fmt: skip
    a1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8.5, ncol=3)
    # fallback quality: agreement with the release-group genre where both exist
    base = max(s["genre_share_main"].values())
    bars = [
        ("Artist tags", s["agree_rg_genre_artist"], theme.SERIES[3]),
        ("Classifier: rosamerica (used)", s["agree_rg_genre_hl_rosamerica"], theme.SERIES[7]),
        ("Classifier: dortmund", s["agree_rg_genre_hl_dortmund"], theme.MUTED),
        ("Classifier: tzanetakis", s["agree_rg_genre_hl_tzanetakis"], theme.MUTED),
    ]
    y = np.arange(len(bars))[::-1]
    a2.barh(y, [100 * v for _, v, _ in bars], color=[c_ for *_, c_ in bars], height=0.6)
    for yi, (_, v, _) in zip(y, bars, strict=True):
        a2.text(100 * v + 1.5, yi, f"{v:.0%}", va="center", fontsize=9)
    a2.axvline(100 * base, color=theme.TEXT, lw=1, ls=(0, (3, 2)))
    a2.text(100 * base + 1, -0.55, f"always guess the largest genre: {base:.0%}",
            fontsize=8, color=theme.TEXT_2, va="center")  # fmt: skip
    a2.set_ylim(-0.8, len(bars) - 0.5)
    a2.set_yticks(y, [b for b, *_ in bars], fontsize=9)
    a2.set_xlim(0, 100)
    a2.set_xlabel("Agrees with release-group genre (%)")
    a2.set_title("How good are the fallbacks?", loc="left", fontsize=10.5)
    a2.grid(axis="y", visible=False)
    tag = 1 - s["source_share_main"].get("hl", 0) - s["source_share_main"].get("none", 0)
    fig.suptitle(
        f"{tag:.1%} of main-sample units get their genre from MusicBrainz tags; "
        f"the audio classifier fills {s['source_share_main'].get('hl', 0):.1%}",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p10_genre_coverage", n=int(tot.sum()), source=SRC,
                   note="unit = one recording on one release; right panel: main-sample units "
                        "with both a release-group genre and the fallback")  # fmt: skip


def main() -> None:
    c = duckdb.connect()
    fig_mix(c)
    fig_coverage(c)


if __name__ == "__main__":
    main()
