"""P09 figures: data funnel, units per release year, and codec mix by year."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np

from lw.normalisation import era_start
from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
FUNNEL = ROOT / "data/processed/tracks_funnel.json"
SRC = "Data: AcousticBrainz + MusicBrainz, CC0"
Y0, Y1 = 1980, 2022
UNIT = "unit = one recording on one release (median of its submissions)"


def fig_funnel(s: dict) -> None:
    f = s["funnel"]
    steps = [
        ("AcousticBrainz submissions", f["submissions"], "sub"),
        ("exact repeats removed", f["after_repeats"], "sub"),
        ("matched to a MusicBrainz release", f["after_unmatched"], "sub"),
        ("replay gain + dynamic complexity present", f["after_no_features"], "sub"),
        ("duration ≥ 30 s", f["after_short"], "sub"),
        ("estimated LUFS ≤ 0", f["after_lufs_gt_0"], "sub"),
        ("estimated LUFS ≥ −60", f["after_lufs_lt_-60"], "sub"),
        ("valid LRA (DC > 0, LRA ≤ 50 LU)", f["after_invalid_lra"], "sub"),
        *(
            [
                ("lossy: no MP3Gain tag", f["after_gain_tagged"], "sub"),
                ("lossy: not a named stream rip", f["after_stream_rip"], "sub"),
            ]
            if "after_stream_rip" in f
            else []
        ),  # fmt: skip
        ("→ units (recording × release)", f["units"], "unit"),
        ("release year 1980–2022", f["units_core"], "unit"),
        ("main sample: tier A/B, not a reissue", f["units_main"], "unit"),
        ("  … and consistent submissions", f["units_main_consistent"], "unit"),
        ("headline: main sample with a lossless copy", f["units_main_lossless"], "head"),
    ]
    theme.apply()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    y = np.arange(len(steps))[::-1]
    vals = np.array([v for _, v, _ in steps]) / 1e6
    cols = [{"sub": theme.SERIES[0], "unit": theme.SERIES[2], "head": theme.SERIES[6]}[k]
            for *_, k in steps]  # fmt: skip
    ax.barh(y, vals, color=cols, height=0.68)
    prev = None
    for yi, (_lab, v, k), vm in zip(y, steps, vals, strict=True):
        drop = ""
        if prev is not None and prev[1] == k and prev[0] != v:
            drop = f"   −{prev[0] - v:,}"
        if k == "head":
            drop = f"   {v / f['units_main']:.0%} of the main sample"
        ax.text(vm + 0.25, yi, f"{v:,}{drop}", va="center", fontsize=8.5, color=theme.TEXT)
        prev = (v, k)
    ax.set_yticks(y, [lab for lab, *_ in steps], fontsize=9)
    ax.set_xlim(0, vals.max() * 1.32)
    ax.set_xlabel("Rows (millions)")
    ax.grid(axis="y", visible=False)
    ax.text(0.98, 0.9, "submissions", color=theme.SERIES[0], transform=ax.transAxes,
            ha="right", fontsize=9, fontweight="bold")  # fmt: skip
    ax.text(0.98, 0.2, "units", color=theme.SERIES[2], transform=ax.transAxes, ha="right",
            fontsize=9, fontweight="bold")  # fmt: skip
    ex = sum(v for k, v in f["excluded"].items() if k != "unmatched")
    fig.suptitle(
        f"Quality exclusions remove {ex / f['after_unmatched']:.1%} of matched submissions; "
        f"{f['units_main_lossless'] / 1e6:.1f}M lossless units make the headline sample",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p09_data_funnel", n=f["units_main_lossless"], source=SRC, note=UNIT)


def fig_per_year(c) -> None:
    rows = c.execute(f"""select year, match_tier, count(*), count(*) filter (where in_main),
        count(*) filter (where is_reissue) from read_parquet('{T}')
        where in_core group by 1, 2""").fetchall()
    years = np.arange(Y0, Y1 + 1)
    tiers = ["A", "B", "C"]
    n = np.zeros((3, len(years)))
    main = np.zeros(len(years))
    for y, t, k, km, _ in rows:
        n[tiers.index(t), y - Y0] += k
        main[y - Y0] += km
    theme.apply()
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    theme.shade_era(ax, start=era_start(), end=Y1 + 0.5)
    bottom = np.zeros(len(years))
    labs = ["A: release tag", "B: date + album title", "C: earliest release (fallback)"]
    for i, (lab, col) in enumerate(zip(labs, [theme.SERIES[0], theme.SERIES[1], theme.SERIES[3]],
                                       strict=True)):  # fmt: skip
        ax.bar(years, n[i] / 1e3, bottom=bottom, color=col, width=0.82, label=lab, lw=0)
        bottom += n[i] / 1e3
    ax.plot(years, main / 1e3, color=theme.TEXT, lw=1.6, marker="o", ms=2.8,
            label="main sample (A/B, not reissue)")  # fmt: skip
    ax.set_xlim(Y0 - 0.6, Y1 + 0.6)
    ax.set_ylabel("Units per release year (thousands)")
    ax.set_xlabel("Release year")
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)
    for yy in (2019, 2022):
        i = yy - Y0
        ax.annotate(f"{int(main[i]):,}", (yy, main[i] / 1e3), xytext=(-4, 12),
                    textcoords="offset points", ha="center", fontsize=8,
                    bbox=dict(boxstyle="round,pad=0.2", fc=theme.SURFACE, ec="none"))  # fmt: skip
    pk = years[np.argmax(n.sum(0))]
    fig.suptitle(
        f"Coverage peaks in {pk} and thins after 2019: "
        f"{int(main[-1]):,} main-sample units for 2022",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p09_tracks_per_year", n=int(n.sum()), source=SRC,
                   note=f"{UNIT}; release years {Y0}–{Y1}")  # fmt: skip


GROUPS = [
    ("FLAC", "codec = 'flac'"),
    (
        "ALAC / PCM / other lossless",
        "codec in ('alac', 'ape', 'wavpack', 'tta') or codec like 'pcm%'",
    ),
    ("MP3", "codec in ('mp3', 'mp3float')"),
    ("AAC", "codec = 'aac'"),
    ("other lossy (Vorbis, WMA, …)", "true"),
]


def fig_codec(c) -> None:
    case = "case " + " ".join(f"when {w} then {i}" for i, (_, w) in enumerate(GROUPS)) + " end"
    rows = c.execute(f"""select year, {case} as g, count(*), sum(low_bitrate::int)
        from read_parquet('{T}') where in_core group by 1, 2""").fetchall()
    years = np.arange(Y0, Y1 + 1)
    n = np.zeros((len(GROUPS), len(years)))
    low = np.zeros(len(years))
    for y, g, k, lb in rows:
        n[g, y - Y0] += k
        low[y - Y0] += lb
    tot = n.sum(0)
    share = n / tot * 100
    theme.apply()
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    cols = [theme.SERIES[0], theme.SERIES[6], theme.SERIES[1], theme.SERIES[3], theme.MUTED]
    ax.stackplot(years, share, colors=cols, labels=[g for g, _ in GROUPS], alpha=0.92, lw=0)
    ax.plot(years, low / tot * 100, color=theme.TEXT, lw=1.4, ls=(0, (3, 2)),
            label="lossy < 128 kbps (share of all)")  # fmt: skip
    ax.axvline(era_start(), color=theme.TEXT_2, lw=0.8, ls=":")
    ax.text(era_start() + 0.3, 97, "normalisation era", fontsize=8, color=theme.SURFACE,
            va="top")  # fmt: skip
    ax.set_xlim(Y0, Y1)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of units (%)")
    ax.set_xlabel("Release year")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8.5, frameon=False)
    ll = (n[0] + n[1]) / tot * 100
    i90, i15 = 1990 - Y0, 2015 - Y0
    fig.suptitle(
        f"Lossless share by release year: {ll[i90]:.0f}% for 1990, {ll[i15]:.0f}% for 2015, "
        f"{ll[-1]:.0f}% for 2022",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p09_codec_mix_by_year", n=int(tot.sum()), source=SRC,
                   note=f"{UNIT}; codec = most common among its submissions")  # fmt: skip


def fig_gain_check() -> None:
    """Gain-normalised lossy files: RG histogram by codec, and the lossy - lossless gap."""
    m = ROOT / "data/interim/ab_matched.parquet"
    c = duckdb.connect()
    c.execute("set memory_limit='6GB'")
    h = c.execute(f"""select codec, floor(replay_gain * 4) / 4 + 0.125 b, count(*)
        from read_parquet('{m}') where match_tier is not null and length_s >= 30
          and essentia_version = '2.1-beta2' and year between 1995 and 2015
          and codec in ('flac', 'mp3', 'aac') and replay_gain between -18 and 4
        group by all""").fetchall()
    g = c.execute(f"""select year, median(lufs_lossy - lufs_lossless), count(*),
          avg((lufs_lossy - lufs_lossless < -2)::int)
        from read_parquet('{T}') where in_main and lufs_lossy is not null
          and lufs_lossless is not null group by 1 order by 1""").fetchall()
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for k, col in [("flac", theme.SERIES[0]), ("mp3", theme.SERIES[1]), ("aac", theme.SERIES[3])]:
        rows = sorted((b, n) for cc, b, n in h if cc == k)
        tot = sum(n for _, n in rows)
        a1.plot([b for b, _ in rows], [100 * n / tot for _, n in rows], color=col, lw=1.8,
                label=k.upper())  # fmt: skip
    a1.axvspan(-6.75, -4.5, color=theme.ERA_FILL, zorder=0, lw=0)
    a1.text(-5.6, 2.05, "MP3Gain\ntarget", ha="center", fontsize=8.5, color=theme.TEXT_2)
    a1.set_xlabel("Essentia replay gain (dB; higher = quieter file)")
    a1.set_ylabel("Share of submissions per 0.25 dB (%)")
    a1.set_title("Release years 1995–2015, extractor 2.1-beta2", loc="left", fontsize=10.5)
    a1.legend(fontsize=8.5, loc="upper left")
    yy = np.array([r[0] for r in g if Y0 <= r[0] <= Y1])
    sel = [r for r in g if Y0 <= r[0] <= Y1]
    a2.axhline(0, color=theme.MUTED, lw=0.8)
    theme.shade_era(a2, start=era_start(), end=Y1 + 0.5)
    a2.plot(yy, [r[1] for r in sel], color=theme.SERIES[1], lw=1.8, marker="o", ms=3,
            label="median lossy − lossless (LU)")  # fmt: skip
    a2.set_ylabel("Lossy − lossless estimated LUFS (LU)")
    a2.set_xlabel("Release year")
    a2.set_title("Same unit, lossy vs lossless submissions", loc="left", fontsize=10.5)
    ax = a2.twinx()
    ax.plot(yy, [100 * r[3] for r in sel], color=theme.TEXT, lw=1.2, ls=(0, (3, 2)))
    ax.set_ylabel("Lossy copy > 2 LU quieter (% of units, dashed)", fontsize=8.5)
    ax.grid(False)
    ax.set_ylim(0, 25)
    a2.set_ylim(-1, 0.3)
    a2.legend(fontsize=8.5, loc="lower left")
    fig.suptitle(
        "Some lossy files were gain-normalised by their owners, so P09 takes loudness from "
        "lossless copies first",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p09_lossy_gain_check", n=int(sum(r[2] for r in sel)), source=SRC,
                   note="right: main-sample units with lossless + lossy submissions")  # fmt: skip


def fig_lossy_gap_bitrate(c) -> None:
    """The 2014+ lossy - lossless gap is a bitrate-mix effect: constant within bitrate class."""
    g = c.execute(f"""select year, bit_rate_lossy <= 160000 as low, count(*) n,
          median(lufs_lossy - lufs_lossless) d
        from read_parquet('{T}') where in_main and lufs_lossy is not null
          and lufs_lossless is not null and bit_rate_lossy is not null
          and year between {Y0} and {Y1} group by all order by 1""").fetchall()
    years = np.arange(Y0, Y1 + 1)
    by = {(y, lo): (n, d) for y, lo, n, d in g}
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for a in (a1, a2):
        theme.shade_era(a, start=era_start(), end=Y1 + 0.5)
    a1.axhline(0, color=theme.MUTED, lw=0.8)
    for lo, col, lab in [(True, theme.SERIES[1], "lossy copy ≤ 160 kbps"),
                         (False, theme.SERIES[0], "lossy copy > 160 kbps")]:  # fmt: skip
        yy = [y for y in years if (y, lo) in by]
        a1.plot(yy, [by[(y, lo)][1] for y in yy], color=col, lw=1.8, marker="o", ms=3, label=lab)
    a1.set_ylim(-0.7, 0.2)
    a1.set_xlabel("Release year")
    a1.set_ylabel("Median lossy − lossless est. LUFS (LU)")
    a1.set_title("Same unit: within each bitrate class, no change after 2007", loc="left",
                 fontsize=10.5)  # fmt: skip
    a1.legend(fontsize=8.5, loc="lower left")
    share = [100 * by.get((y, True), (0, 0))[0]
             / max(1, by.get((y, True), (0, 0))[0] + by.get((y, False), (0, 0))[0])
             for y in years]  # fmt: skip
    a2.bar(years, share, color=theme.SERIES[1], width=0.8)
    a2.set_ylim(0, 100)
    a2.set_xlabel("Release year")
    a2.set_ylabel("Units whose lossy copy is ≤ 160 kbps (%)")
    a2.set_title("…but low-bitrate copies became common for recent releases", loc="left",
                 fontsize=10.5)  # fmt: skip
    fig.suptitle(
        "The post-2014 lossy gap comes from more low-bitrate copies, not from a change in "
        "mastering or streaming",
        x=0.01, ha="left", fontsize=12.5, fontweight="bold",
    )  # fmt: skip
    fig.tight_layout()
    theme.save_fig(fig, "p09_lossy_gap_by_bitrate", n=int(sum(r[2] for r in g)), source=SRC,
                   note="main-sample units with lossless + lossy submissions; "
                        "bitrate = median over the unit's lossy copies")  # fmt: skip


def main() -> None:
    s = json.loads(FUNNEL.read_text())
    c = duckdb.connect()
    fig_funnel(s)
    fig_per_year(c)
    fig_codec(c)
    fig_gain_check()
    fig_lossy_gap_bitrate(c)


if __name__ == "__main__":
    main()
