# ruff: noqa: E501  (plot calls kept on one line each, as in the other viz modules)
"""P24: social-crop versions of the hero chart, at exact pixel sizes.

``figures/social_hero_1x1.png`` (1080 x 1080) and ``figures/social_hero_16x9.png``
(1920 x 1080). Same data and wording as the article hero (``final_hero_lufs``), simplified
for a phone screen: median, 95% CI, P10-P90 band, normalisation era, three period labels.
Saved without ``bbox_inches='tight'`` so the aspect ratio stays exact.

    uv run python -m lw.viz.social
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import polars as pl

from lw.normalisation import era_start
from lw.report import numbers
from lw.viz import p12, theme

SIZES = {"1x1": (5.4, 5.4), "16x9": (9.6, 5.4)}  # inches at 200 dpi -> 1080x1080, 1920x1080
DPI = 200
URL = "johnpospisil.github.io/loudness-war"


def _period(h: pl.DataFrame, a: int, b: int) -> float:
    return float(h.filter(pl.col("year").is_between(a, b))["median"].mean())


def fig_social(kind: str) -> str:
    n = json.loads(numbers.OUT.read_text())["hero"]
    h = pl.read_parquet(p12.YEARLY)
    h = h.filter((pl.col("sample") == "headline") & (pl.col("metric") == "lufs")).sort("year")
    yy, blue = h["year"].to_numpy(), theme.SERIES[0]
    square = kind == "1x1"
    theme.apply()
    w, ht = SIZES[kind]
    fig = plt.figure(figsize=(w, ht), facecolor=theme.SURFACE)
    # fixed layout (figure fractions): title block, plot, footer
    left, right = (0.13, 0.96) if square else (0.075, 0.975)
    bottom, top = (0.18, 0.74) if square else (0.18, 0.78)
    ax = fig.add_axes((left, bottom, right - left, top - bottom))

    theme.shade_era(ax, start=era_start(), end=p12.Y1 + 0.5, label="")
    ax.text(era_start() + 0.3, 0.97, "Streaming\nnormalisation", transform=ax.get_xaxis_transform(),
            ha="left", va="top", fontsize=7.5 if square else 8.5, color=theme.TEXT_2)  # fmt: skip
    ax.fill_between(yy, h["p10"], h["p90"], color=theme.SEQ_BLUE[0], lw=0,
                    label="middle 80% of tracks")  # fmt: skip
    ax.fill_between(yy, h["ci_lo"], h["ci_hi"], color=theme.SEQ_BLUE[5], lw=0, alpha=0.9,
                    label="95% CI on the median")  # fmt: skip
    ax.plot(yy, h["median"], color=blue, lw=2.6, marker="o", ms=3.0, label="median track")
    fs = 9 if square else 10.5
    for a, b, lab in [(1980, 1989, "1980s"), (2005, 2009, "2005–09"), (2016, 2022, "2016–22")]:
        v = _period(h, a, b)
        ax.annotate(f"{lab}\n{v:.1f}", ((a + b) / 2, v), xytext=(0, 16), textcoords="offset points",
                    ha="center", va="bottom", fontsize=fs, color=blue, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=theme.SURFACE, ec="none", alpha=0.85))  # fmt: skip
    ax.set_xlim(p12.Y0 - 0.6, p12.Y1 + 0.6)
    ax.set_ylim(-23, -5)
    ax.set_ylabel("Estimated loudness (LUFS)", fontsize=8.5 if square else 9.5)
    ax.set_xlabel("Release year", fontsize=8.5 if square else 9.5)
    ax.tick_params(labelsize=8 if square else 9)
    ax.legend(loc="lower right", fontsize=7.5 if square else 8.5, framealpha=0.92)

    rise = n["m2005_09"] - n["m1980s"]
    title = f"Loudness rose about {rise:.0f} LU, then went flat after {n['peak_year']}"
    if square:
        title = f"Loudness rose about {rise:.0f} LU,\nthen went flat after {n['peak_year']}"
    total = int(h["n"].sum())
    sub = (f"Median estimated loudness of {total / 1e6:.1f} million tracks by release year. "
           "Louder is higher.\nNo drop after streaming services began turning loud tracks down.")  # fmt: skip
    fig.text(0.04 if square else 0.025, 0.965, title, ha="left", va="top",
             fontsize=15 if square else 17, fontweight="bold", color=theme.TEXT)  # fmt: skip
    fig.text(0.04 if square else 0.025, 0.835 if square else 0.875, sub, ha="left", va="top",
             fontsize=8 if square else 9.5, color=theme.TEXT_2, linespacing=1.35)  # fmt: skip
    foot = (f"Data: AcousticBrainz + MusicBrainz (CC0) · n = {total:,} tracks, 1980–2022 · "
            "LUFS estimated from calibrated replay gain (±1.3 LU per track)\n"
            f"Grey: streaming services normalise loudness by default from late 2015 · {URL}")  # fmt: skip
    if square:
        foot = (f"Data: AcousticBrainz + MusicBrainz (CC0) · n = {total:,} tracks\n"
                "LUFS estimated from calibrated replay gain (±1.3 LU per track)\n"
                f"Grey: normalisation by default from late 2015 · {URL}")  # fmt: skip
    fig.text(0.04 if square else 0.025, 0.02, foot, ha="left", va="bottom",
             fontsize=6.3 if square else 7.5, color=theme.MUTED, linespacing=1.4)  # fmt: skip
    path = theme.FIG_DIR / f"social_hero_{kind}.png"
    fig.savefig(path, dpi=DPI, facecolor=theme.SURFACE)
    plt.close(fig)
    return str(path)


def main() -> None:
    for k in SIZES:
        print(fig_social(k))


if __name__ == "__main__":
    main()
