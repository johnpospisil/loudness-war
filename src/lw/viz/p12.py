# ruff: noqa: E501  (labels)
"""P12 figures: hero chart (median est. LUFS by release year) and the LRA chart, PNG + HTML."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
import polars as pl

from lw.normalisation import era_consolidated, era_start
from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
YEARLY = ROOT / "data/processed/p12_yearly.parquet"
SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
Y0, Y1 = 1980, 2022
CAL = {"lufs": "est. LUFS = calibrated AcousticBrainz replay gain (P03; ±1.3 LU per track)",
       "lra": "est. LRA = calibrated dynamic complexity (P03; ±2.9 LU per track); includes silence, floored at 0"}  # fmt: skip
UNIT = "unit = one recording on one release; headline = release years 1980–2022, tier A/B match, not a reissue, ≥1 lossless submission, recording's first appearance (≤1 year after its first release)"
CI = "95% CI: release-group bootstrap (1,000 reps)"


def _get(d: pl.DataFrame, sample: str, metric: str) -> pl.DataFrame:
    return d.filter((pl.col("sample") == sample) & (pl.col("metric") == metric)).sort("year")


def _period(h: pl.DataFrame, a: int, b: int, col: str = "median") -> float:
    return float(h.filter(pl.col("year").is_between(a, b))[col].mean())


def _png(d: pl.DataFrame, metric: str) -> None:
    h = _get(d, "headline", metric)
    cmp_ = _get(d, "all_codec_ex160", metric)
    low = _get(d, "headline_low_sil", metric)
    yy = h["year"].to_numpy()
    blue, orange, grey = theme.SERIES[0], theme.SERIES[1], theme.TEXT_2
    theme.apply()
    fig, (ax, an) = plt.subplots(2, 1, figsize=(11, 6.8), sharex=True,
                                 gridspec_kw={"height_ratios": [4.2, 1], "hspace": 0.08})  # fmt: skip
    for a in (ax, an):
        theme.shade_era(
            a, start=era_start(), end=Y1 + 0.5, label="" if a is an else "Normalisation era"
        )
    c3 = era_consolidated()
    ax.axvline(c3, color=theme.MUTED, lw=0.9, ls=(0, (1, 2)))
    ax.fill_between(
        yy, h["p10"], h["p90"], color=theme.SEQ_BLUE[0], lw=0, label="headline: P10–P90 of units"
    )
    ax.fill_between(
        yy,
        h["ci_lo"],
        h["ci_hi"],
        color=theme.SEQ_BLUE[5],
        lw=0,
        alpha=0.9,
        label="headline: 95% CI on the median",
    )
    ax.plot(
        yy,
        h["median"],
        color=blue,
        lw=2.2,
        marker="o",
        ms=3.2,
        label="headline: median (lossless source)",
    )
    ax.plot(cmp_["year"], cmp_["median"], color=grey, lw=1.4, ls=(0, (4, 2.5)),
            label="all codecs, excluding ≤160 kbps: median")  # fmt: skip
    if metric == "lra":
        ax.fill_between(low["year"], low["ci_lo"], low["ci_hi"], color=orange, alpha=0.3, lw=0)
        ax.plot(low["year"], low["median"], color=orange, lw=2.0, marker="o", ms=3,
                label="headline, < 5% near-silent frames: median (95% CI)")  # fmt: skip
        ax.set_ylim(0, 15)
        ax.set_ylabel("Estimated loudness range (LU)")
    else:
        ax.set_ylim(-23, -5)
        ax.set_ylabel("Estimated integrated loudness (LUFS)")
    # period annotations
    for a, b in [(1980, 1989), (2005, 2009), (2016, 2022)]:
        v = _period(h, a, b)
        ax.annotate(f"{a}–{str(b)[2:]}: {v:.1f}", ((a + b) / 2, v),
                    xytext=(0, 14 if metric == "lufs" else -26), textcoords="offset points",
                    ha="center", fontsize=8.5, color=blue, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc=theme.SURFACE, ec="none", alpha=0.85))  # fmt: skip
    ax.text(c3 + 0.15, 0.9 if metric == "lufs" else 0.03, "3 major services\nnormalise by default",
            transform=ax.get_xaxis_transform(), fontsize=7.5, color=theme.TEXT_2,
            va="top" if metric == "lufs" else "bottom")  # fmt: skip
    if metric == "lufs":
        ax.legend(loc="upper left", fontsize=8.2, framealpha=0.92)
    else:
        ax.legend(loc="lower left", fontsize=8.2, framealpha=0.92, ncol=2)
    an.bar(yy, h["n"] / 1e3, color=theme.SEQ_BLUE[3], width=0.8, lw=0)
    an.set_ylabel("Units (k)", fontsize=8.5)
    an.tick_params(labelsize=8)
    an.set_xlim(Y0 - 0.6, Y1 + 0.6)
    an.set_xlabel("Release year")
    an.text(
        Y1 + 0.4,
        h["n"][-1] / 1e3 + 8,
        f"{h['n'][-1]:,}",
        ha="right",
        fontsize=7.5,
        color=theme.TEXT_2,
    )
    pre, post = _period(h, 2010, 2015), _period(h, 2016, 2022)
    if metric == "lufs":
        base = _period(h, 2005, 2015)
        title = (
            f"Loudness rose about {_period(h, 2005, 2009) - _period(h, 1980, 1989):.0f} LU until the late 2000s "
            f"and has barely moved since: 2016–22 is {base - post:.1f} LU quieter than 2005–15"
        )
        sub = (
            f"Median est. LUFS by release year · mean of yearly medians 2010–15: {pre:.2f}, "
            f"2016–22: {post:.2f}"
        )
    else:
        lp, lq = _period(low, 2005, 2009), _period(low, 2016, 2022)
        title = (
            "Loudness range drifted down slowly and has barely changed since 2005; "
            "without silence it has been flat since the mid-2000s"
        )
        sub = (
            f"Median est. LRA by release year · headline 2010–15: {pre:.2f} LU, 2016–22: {post:.2f} LU · "
            f"< 5% near-silent 2005–09: {lp:.2f}, 2016–22: {lq:.2f}"
        )
    fig.suptitle(title, x=0.01, y=0.995, ha="left", fontsize=12.5, fontweight="bold")
    ax.set_title(sub, loc="left", fontsize=9.5, color=theme.TEXT_2)
    fig.subplots_adjust(top=0.9)
    theme.save_fig(fig, f"p12_{'hero_lufs' if metric == 'lufs' else 'lra'}", n=int(h["n"].sum()),
                   source=SRC, note=f"{CAL[metric]} · {CI}\n{UNIT}")  # fmt: skip


def _html(d: pl.DataFrame, metric: str) -> None:
    h = _get(d, "headline", metric)
    cmp_ = _get(d, "all_codec_ex160", metric)
    low = _get(d, "headline_low_sil", metric)
    unit = "LUFS" if metric == "lufs" else "LU"
    name = "est. LUFS" if metric == "lufs" else "est. LRA"
    hover = (f"<b>%{{x}}</b><br>median %{{y:.2f}} {unit}<br>95% CI %{{customdata[0]:.2f}} to %{{customdata[1]:.2f}}"
             "<br>P10 %{customdata[2]:.1f} · P90 %{customdata[3]:.1f}<br>n = %{customdata[4]:,} units, "
             "%{customdata[5]:,} release groups<extra></extra>")  # fmt: skip

    def cd(x):
        return np.column_stack([x["ci_lo"], x["ci_hi"], x["p10"], x["p90"], x["n"], x["n_rg"]])

    fig = go.Figure()
    fig.add_vrect(x0=era_start(), x1=Y1 + 0.5, fillcolor="#bdbab2", opacity=0.3, line_width=0,
                  layer="above")  # fmt: skip
    fig.add_annotation(x=era_start(), y=1, xref="x", yref="paper", text="Normalisation era",
                       showarrow=False, xanchor="left", yanchor="top",
                       font=dict(size=11, color=theme.TEXT_2))  # fmt: skip
    yy = h["year"].to_list()
    fig.add_trace(go.Scatter(x=yy + yy[::-1], y=h["p90"].to_list() + h["p10"].to_list()[::-1], fill="toself",
                             fillcolor=theme.SEQ_BLUE[0], line_width=0, hoverinfo="skip", name="P10–P90"))  # fmt: skip
    fig.add_trace(go.Scatter(x=yy + yy[::-1], y=h["ci_hi"].to_list() + h["ci_lo"].to_list()[::-1], fill="toself",
                             fillcolor=theme.SEQ_BLUE[5], line_width=0, hoverinfo="skip", name="95% CI"))  # fmt: skip
    fig.add_trace(go.Scatter(x=yy, y=h["median"], mode="lines+markers", name="headline median (lossless)",
                             line=dict(color=theme.SERIES[0], width=3), customdata=cd(h), hovertemplate=hover))  # fmt: skip
    fig.add_trace(go.Scatter(x=cmp_["year"], y=cmp_["median"], mode="lines", name="all codecs, excl. ≤160 kbps",
                             line=dict(color=theme.TEXT_2, width=1.6, dash="dash"), customdata=cd(cmp_),
                             hovertemplate=hover))  # fmt: skip
    if metric == "lra":
        fig.add_trace(go.Scatter(x=low["year"], y=low["median"], mode="lines+markers",
                                 name="< 5% near-silent frames", line=dict(color=theme.SERIES[1], width=2.4),
                                 customdata=cd(low), hovertemplate=hover))  # fmt: skip
    title = ("Median estimated loudness by release year, 1980–2022" if metric == "lufs"
             else "Median estimated loudness range by release year, 1980–2022")  # fmt: skip
    fig.update_layout(
        title=dict(text=f"<b>{title}</b><br><sup>{CAL[metric]} · {CI}</sup>", x=0.01),
        template="simple_white", paper_bgcolor=theme.SURFACE, plot_bgcolor=theme.SURFACE,
        font=dict(family="Helvetica, Arial, sans-serif", color=theme.TEXT), hovermode="closest",
        xaxis=dict(title="Release year", range=[Y0 - 0.5, Y1 + 0.5]),
        yaxis=dict(title=f"{name} ({unit})", gridcolor=theme.GRID, showgrid=True),
        legend=dict(orientation="h", y=-0.14), margin=dict(l=60, r=20, t=90, b=130),
        height=640,
    )  # fmt: skip
    if metric == "lra":
        fig.update_yaxes(range=[0, 15])
    fig.add_annotation(
        text=f"{SRC} · n = {int(h['n'].sum()):,} units · {UNIT}",
        xref="paper",
        yref="paper",
        x=0,
        y=-0.25,
        showarrow=False,
        font=dict(size=10, color=theme.MUTED),
        xanchor="left",
    )
    out = theme.FIG_DIR / f"p12_{'hero_lufs' if metric == 'lufs' else 'lra'}.html"
    fig.write_html(out, include_plotlyjs="cdn", full_html=True, config={"displaylogo": False})


def _wmed(x: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][np.searchsorted(cw, cw[-1] / 2)])


def fig_sensitivity() -> None:
    """How the yearly median depends on weighting / which units count (point estimates)."""
    import duckdb

    c = duckdb.connect()
    c.execute("set memory_limit='8GB'")
    mb = ROOT / "data/interim/mb"
    d = c.sql(f"""with rf as (select rr.recording_mbid, min(r.release_year) rec_first_year
            from read_parquet('{mb}/recording_release.parquet') rr
            join read_parquet('{mb}/release.parquet') r using (release_mbid)
            where r.release_year is not null group by 1)
        select t.year, t.lufs, coalesce(t.is_compilation, false) comp,
          t.year - rf.rec_first_year <= 1 as first_app,
          count(*) over (partition by t.year, t.release_group_mbid) n_rg
        from read_parquet('{ROOT}/data/processed/tracks.parquet') t
        left join rf on rf.recording_mbid = t.recording_mbid
        where t.in_main_lossless""").pl()
    variants = {
        "all units, incl. old recordings in new box sets (pre-P12 headline)": lambda g: np.median(g["lufs"]),
        "recording's first appearance only (headline, 87% of units)": lambda g: np.median(g.filter(pl.col("first_app").fill_null(False))["lufs"]),
        "compilations excluded": lambda g: np.median(g.filter(~pl.col("comp"))["lufs"]),
        "release group capped at 30 units": lambda g: _wmed(g["lufs"].to_numpy(), np.minimum(1, 30 / g["n_rg"].to_numpy())),
        "every release group weighted equally": lambda g: _wmed(g["lufs"].to_numpy(), 1 / g["n_rg"].to_numpy()),
    }  # fmt: skip
    rows = {k: [] for k in variants}
    years = list(range(1995, Y1 + 1))
    by = {y: g for (y,), g in d.group_by(["year"])}
    for y in years:
        for k, f in variants.items():
            rows[k].append(f(by[y]))
    theme.apply()
    fig, ax = plt.subplots(figsize=(11, 5.4))
    theme.shade_era(ax, start=era_start(), end=Y1 + 0.5)
    cols = [theme.SERIES[0], theme.SERIES[1], theme.SERIES[2], theme.SERIES[3], theme.SERIES[6]]
    for (k, v), col in zip(rows.items(), cols, strict=True):
        ax.plot(years, v, color=col, lw=2.6 if "(headline" in k else 1.6, marker="o", ms=2.6,
                label=f"{k}: 2005–09 {np.mean(v[10:15]):.2f}, 2016–22 {np.mean(v[21:]):.2f}")  # fmt: skip
    ax.set_xlim(1994.5, Y1 + 0.5)
    ax.set_ylabel("Median est. LUFS")
    ax.set_xlabel("Release year")
    ax.legend(loc="lower right", fontsize=8.2, framealpha=0.92)
    fig.suptitle("Which units count moves the post-2005 level by up to 0.5 LU and the post-2015 "
                 "change by up to 0.4 LU", x=0.01, ha="left", fontsize=12.5, fontweight="bold")  # fmt: skip
    ax.set_title("Main sample with a lossless copy, median est. LUFS by release year under five "
                 "weighting / inclusion rules (period means in the legend)", loc="left", fontsize=9.5,
                 color=theme.TEXT_2)  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p12_weighting_sensitivity", n=d.height, source=SRC,
                   note="first appearance = release year ≤ the recording's earliest MusicBrainz "
                        "release year + 1; box sets of archive recordings (e.g. a 5,411-track "
                        "2018 Bach edition) dominate single years")  # fmt: skip


def main() -> None:
    d = pl.read_parquet(YEARLY)
    for m in ["lufs", "lra"]:
        _png(d, m)
        _html(d, m)
    fig_sensitivity()


if __name__ == "__main__":
    main()
