"""Shared chart theme: palette, rcParams, and a save helper that stamps the source line.

Palette is the validated dataviz reference instance (light mode). Categorical slots are
assigned in fixed order, never cycled; past 8 series fold into "Other" or facet.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

FIG_DIR = Path(__file__).resolve().parents[3] / "figures"
SOURCE = "Data: AcousticBrainz + MusicBrainz (CC0)"

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e1"

# Categorical, fixed order (blue, orange, aqua, yellow, magenta, green, violet, red).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

# Sequential blue ramp (100 -> 700) for magnitude encodings (heatmaps, ridgelines by decade).
SEQ_BLUE = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]

# Diverging blue <-> red with gray midpoint (e.g. remaster minus original LUFS).
DIV_NEG, DIV_MID, DIV_POS = "#2a78d6", "#f0efec", "#e34948"

# Neutral band for the streaming-normalisation era; percentile bands use a tint of the series.
ERA_FILL = "#ecebe7"
# figure name -> (final name, replacement suptitle or None); used by lw.viz.final
FINAL: dict[str, tuple[str, str | None]] = {}


def apply() -> None:
    """Install the project rcParams. Call once at the top of any figure script."""
    mpl.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 10,
            "text.color": TEXT,
            "axes.labelcolor": TEXT_2,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlepad": 12,
            "axes.edgecolor": MUTED,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "axes.axisbelow": True,
            "axes.prop_cycle": mpl.cycler(color=SERIES),
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": TEXT_2,
            "ytick.color": TEXT_2,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "lines.linewidth": 2,
            "lines.solid_capstyle": "round",
            "legend.frameon": False,
            "legend.fontsize": 9,
        }
    )


def shade_era(ax, start: float = 2015, end: float = 2022.5, label: str = "Normalisation\nera"):
    """Shade the normalisation era behind the data and label it at the top."""
    ax.axvspan(start, end, color=ERA_FILL, zorder=0, lw=0)
    ax.text(
        start + 0.3,
        0.98,
        label,
        transform=ax.get_xaxis_transform(),
        ha="left",
        va="top",
        fontsize=8.5,
        color=TEXT_2,
    )


def save_fig(
    fig,
    name: str,
    n: int | None = None,
    note: str | None = None,
    source: str = SOURCE,
    dpi: int = 200,
) -> Path:
    """Stamp source/n/note in the bottom-left and write figures/<name>.png.

    ``FINAL`` (set by ``lw.viz.final``) renames a figure and replaces its suptitle, so the
    article versions reuse the prompt figures' code unchanged."""
    if name in FINAL:
        name, title = FINAL[name]
        if fig._suptitle is not None:
            if title:
                fig._suptitle.set_text(title)
            fig._suptitle.set_fontweight("bold")
    bits = [source]
    if n is not None:
        bits.append(f"n = {n:,}")
    if note:
        bits.append(note)
    fig.text(0.01, -0.01, " · ".join(bits), ha="left", va="top", fontsize=7.5, color=MUTED)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return path


def _preview() -> Path:
    """Render palette swatches and a synthetic sample line chart (no real data)."""
    import numpy as np

    apply()
    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(9, 6.5), height_ratios=[1, 3])

    ax0.set_title("Theme preview: categorical palette (fixed order)")
    for i, c in enumerate(SERIES):
        ax0.barh(0, 0.9, left=i, color=c, height=0.6)
        ax0.text(i + 0.45, -0.55, f"{i + 1}\n{c}", ha="center", va="top", fontsize=8, color=TEXT_2)
    ax0.set_xlim(-0.1, 8)
    ax0.set_ylim(-1.4, 0.5)
    ax0.axis("off")

    rng = np.random.default_rng(0)
    years = np.arange(1980, 2023)
    med = -17 + 7 / (1 + np.exp(-(years - 1997) / 3)) - 1.2 * (years > 2014) * (years - 2014) / 8
    shade_era(ax1)
    ax1.fill_between(
        years, med - 3.5, med + 2.5, color=SERIES[0], alpha=0.15, lw=0, label="P10–P90"
    )
    ax1.plot(years, med + rng.normal(0, 0.15, years.size), color=SERIES[0], label="Median")
    ax1.plot(
        years, med - 2 + rng.normal(0, 0.2, years.size), color=SERIES[1], label="Second series"
    )
    ax1.set_title("Sample line chart (synthetic data, layout only)", fontsize=11)
    ax1.set_ylabel("Integrated loudness (LUFS)")
    ax1.set_xlim(1980, 2022.5)
    ax1.legend(loc="upper left")
    fig.tight_layout()
    return save_fig(fig, "p00_theme_preview", note="SYNTHETIC — theme preview only")


if __name__ == "__main__":
    print(_preview())
