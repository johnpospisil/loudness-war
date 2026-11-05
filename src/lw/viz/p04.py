"""P04 figure: the normalisation timeline strip (services + standards)."""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from lw import normalisation as nz
from lw.viz import theme

SRC = (
    "Sources: service docs, AES/EBU/ITU, mastering-engineer measurements"
    " (see normalisation_timeline.csv)"
)
ROWS = [
    "Apple Music Sound Check",
    "Spotify",
    "YouTube",
    "Tidal",
    "Pandora",
    "Amazon Music",
    "Deezer",
    "Standards",
]
LABEL = {"Apple Music Sound Check": "Apple (Sound Check)"}
X0, X1 = 2001.5, 2027.6


def _marker(ax, x, y, conf, color):
    face = {"high": color, "medium": color, "low": theme.SURFACE}[conf]
    alpha = {"high": 1.0, "medium": 0.55, "low": 1.0}[conf]
    ax.scatter(x, y, s=70, color=face, alpha=alpha, edgecolor=color, linewidth=1.6, zorder=4)
    if conf == "medium":  # re-stroke the edge at full opacity
        ax.scatter(x, y, s=70, facecolor="none", edgecolor=color, linewidth=1.6, zorder=5)


def timeline() -> None:
    df = nz.load()
    start, consol = nz.era_start(df), nz.era_consolidated(df)
    theme.apply()
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.axvspan(start, X1, color=theme.ERA_FILL, lw=0, zorder=0)
    ax.axvline(start, color=theme.MUTED, lw=0.8, ls=(0, (2, 2)), zorder=1)
    ax.axvline(consol, color=theme.MUTED, lw=0.8, ls=(0, (2, 2)), zorder=1)
    ax.text(
        start - 0.15,
        len(ROWS) - 0.35,
        "Normalisation era starts\n(YouTube, Dec 2015)",
        fontsize=8.5,
        color=theme.TEXT_2,
        va="bottom",
        ha="right",
    )
    ax.text(
        consol + 0.15,
        len(ROWS) - 0.35,
        "3 major services on\nby default (Nov 2017)",
        fontsize=8.5,
        color=theme.TEXT_2,
        va="bottom",
        ha="left",
    )

    for i, row in enumerate(ROWS):
        y = len(ROWS) - 1 - i
        is_std = row == "Standards"
        d = df.filter(pl_kind(df, row))
        color = theme.MUTED if is_std else theme.SERIES[0]
        on = d.filter(d["default_on"].fill_null(False))
        if not is_std and on.height:  # bar: normalising by default (dotted while unverified)
            t_low = float(on["t"].min())
            firm = on.filter(on["confidence"] != "low")
            t_firm = float(firm["t"].min()) if firm.height else X1 - 0.3
            kw = dict(color=color, lw=3, alpha=0.35, zorder=2, solid_capstyle="butt")
            if t_low < t_firm:
                ax.plot([t_low, t_firm], [y, y], ls=(0, (1, 1.5)), **kw)
            if t_firm < X1 - 0.3:
                ax.plot([t_firm, X1 - 0.3], [y, y], ls="-", **kw)
        for r in d.iter_rows(named=True):
            _marker(ax, r["t"], y, r["confidence"], color)
            lab = _short(r)
            if lab:
                below = is_std and r["id"].startswith("itu_bs1770_") and r["id"] != "itu_bs1770_0"
                ax.annotate(
                    lab,
                    (r["t"], y),
                    xytext=(0, -10 if below else 9),
                    textcoords="offset points",
                    ha="center",
                    va="top" if below else "bottom",
                    fontsize=7.2,
                    color=theme.TEXT_2,
                )
    ax.set_yticks(range(len(ROWS)), [LABEL.get(r, r) for r in ROWS][::-1])
    ax.set_ylim(-1.0, len(ROWS) + 0.4)
    ax.set_xlim(X0, X1)
    ax.set_xticks(range(2002, 2027, 2))
    ax.grid(axis="x", visible=True)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Date")
    fig.suptitle(
        "Loudness normalisation went default between late 2015 and 2017",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_title(
        "Dots = dated events; bar = normalising by default (dotted = start date unverified). "
        "Labels: target in LUFS",
        loc="left",
        fontsize=9.5,
        color=theme.TEXT_2,
    )
    handles = [
        Line2D([], [], marker="o", ls="", ms=8, color=theme.SERIES[0], label="high confidence"),
        Line2D(
            [],
            [],
            marker="o",
            ls="",
            ms=8,
            color=theme.SERIES[0],
            alpha=0.55,
            markeredgecolor=theme.SERIES[0],
            label="medium",
        ),
        Line2D(
            [],
            [],
            marker="o",
            ls="",
            ms=8,
            markerfacecolor=theme.SURFACE,
            markeredgecolor=theme.SERIES[0],
            label="low / unverified",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="center left",
        bbox_to_anchor=(0.0, 0.3),
        ncol=1,
        fontsize=8.5,
        title="Date confidence",
        title_fontsize=8.5,
        alignment="left",
    )
    theme.save_fig(
        fig,
        "p04_normalisation_timeline",
        n=df.height,
        source=SRC,
        note="events; dates marked 'by' are first evidence, not start dates",
    )


def pl_kind(df, row):
    import polars as pl

    if row == "Standards":
        return pl.col("kind") == "standard"
    if row.startswith("Apple"):
        return pl.col("service").str.starts_with("Apple")
    return pl.col("service") == row


def _short(r) -> str:
    tgt = r["target_LUFS"]
    if r["kind"] == "standard":
        name = {
            "aes_td1004": "AES TD1004",
            "aes_td1008": "AES TD1008",
            "ebu_r128_2010": "R128",
            "itu_bs1770_0": "BS.1770",
            "itu_bs1770_2": "BS.1770-2",
            "itu_bs1770_4": "BS.1770-4",
            "itu_bs1770_5": "BS.1770-5",
        }.get(r["id"], "")
        return f"{name} {tgt:g}" if tgt is not None and name.startswith(("AES", "R1")) else name
    if r["id"] == "apple_soundcheck_2002":
        return "opt-in"
    if r["id"] == "spotify_now":
        return ""
    return f"{tgt:g}" if tgt is not None else "?"


if __name__ == "__main__":
    timeline()
