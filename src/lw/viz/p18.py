# ruff: noqa: E501  (labels)
"""P18 figures: validation scatter, Bland-Altman (brief chart 6), encoding shift, DR Database."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from lw.models import validation as v
from lw.viz import theme

SRC = "Data: AcousticBrainz + MusicBrainz, CC0; own CD rips measured with pyloudnorm"
DR_SRC = "Data: AcousticBrainz + MusicBrainz, CC0; Dynamic Range Database (dr.loudness-war.info, accessed 2026-11-14), aggregates only"
LEVEL_STYLE = {
    "same_release": (theme.SERIES[0], "AB: same release"),
    "same_release_group": (theme.SERIES[1], "AB: same album, other release"),
    "other_release": (theme.SERIES[4], "AB: other release (e.g. remaster)"),
}


def _identity(ax, lo, hi):
    ax.plot([lo, hi], [lo, hi], color=theme.TEXT, lw=0.8, zorder=1)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)


def fig_scatter() -> None:
    s = json.loads(v.SUMMARY.read_text())
    tr = pl.read_parquet(v.OWN)
    theme.apply()
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.4), gridspec_kw={"wspace": 0.28})
    for ax, (meas, est, ab_col, unit, lo, hi, tag) in zip(axes[:2], [
        ("lufs", "est_lufs", "ab_est_lufs", "LUFS", -28, -4, "(a) Integrated loudness"),
        ("lra", "est_lra", "ab_est_lra", "LU", 0, 26, "(b) Loudness range"),
    ], strict=False):  # fmt: skip
        _identity(ax, lo, hi)
        ax.scatter(tr[meas], tr[est], s=16, marker="x", color=theme.MUTED, lw=0.9,
                   label="Own rip, Essentia proxy (same file)", zorder=2)  # fmt: skip
        m = tr.filter(pl.col(ab_col).is_not_null())
        for cond, col, mk, lab in [
            (pl.col("d_rg").abs() < 0.5, theme.SERIES[0], "o", "AcousticBrainz copy, same audio"),
            (pl.col("d_rg").abs() >= 0.5, theme.SERIES[1], "^", "AcousticBrainz copy, other audio (remaster / normalised)"),
        ]:  # fmt: skip
            z = m.filter(cond)
            ax.scatter(z[meas], z[ab_col], s=20, marker=mk, color=col, alpha=0.8, lw=0,
                       label=f"{lab} (n = {z.height})", zorder=3)  # fmt: skip
        p = s["proxy_lossless"][meas]
        ax.text(0.98, 0.03, f"proxy on own lossless: bias {p['bias']:+.2f} {unit.replace('LUFS','LU')}, "
                f"RMSE {p['rmse']:.2f}\n(P03 CV RMSE on AAC: {s['proxy_lossless']['p03_cv_rmse'][meas]:.2f})",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
                bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.3"))  # fmt: skip
        ax.set_xlabel(f"Measured on own CD rip, pyloudnorm ({unit})")
        ax.set_ylabel(f"Estimated ({'est. LUFS' if meas == 'lufs' else 'est. LRA, LU'})")
        ax.set_title(f"{tag}: estimate vs own measurement", loc="left", fontsize=10.5)
        ax.legend(loc="upper left", fontsize=7.8, framealpha=0.92)
    # (c) DR database, binned aggregate
    ax = axes[2]
    b = pl.read_parquet(v.DR_BINS).filter(pl.col("x") == "est_lufs")
    d = s["drdb"]
    ax.fill_between(b["bin"], b["q25"], b["q75"], color=theme.SERIES[0], alpha=0.18, lw=0,
                    label="DR interquartile range of albums in bin")  # fmt: skip
    ax.plot(b["bin"], b["med"], "o-", color=theme.SERIES[0], ms=4, label="Median album DR")
    for x, n, m in zip(b["bin"], b["n"], b["q75"], strict=False):
        ax.text(x, m + 0.3, str(n), ha="center", fontsize=6.8, color=theme.MUTED)
    e = d["est_lufs"]
    ax.text(0.98, 0.97, f"{d['n_albums']} albums ({d['years'][0]}–{d['years'][1]}), original CD entries\n"
            f"Spearman ρ = {e['spearman']['r']:+.2f} [{e['spearman']['lo']:+.2f}, {e['spearman']['hi']:+.2f}]\n"
            f"within release year r = {e['within_year_pearson']['r']:+.2f} [{e['within_year_pearson']['lo']:+.2f}, {e['within_year_pearson']['hi']:+.2f}]\n"
            f"est. LRA vs DR: ρ = {d['est_lra']['spearman']['r']:+.2f}",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.3"))  # fmt: skip
    ax.set_xlabel("Album median est. LUFS (AcousticBrainz, originals)")
    ax.set_ylabel("Dynamic Range Database album DR (dB)")
    ax.set_title("(c) Louder estimate, lower published DR", loc="left", fontsize=10.5)
    ax.legend(loc="lower left", fontsize=7.8, framealpha=0.92)
    fig.suptitle("Do the AcousticBrainz loudness estimates agree with independent measurements?",
                 x=0.01, ha="left", fontsize=13.5, y=1.02)  # fmt: skip
    theme.save_fig(fig, "p18_validation_scatter", n=s["own"]["n_tracks"], source=SRC,
                   note=f"{s['own']['n_albums']} own CDs (FLAC, AccurateRip-verified); (c) bins with ≥ 5 albums, numbers = albums per bin; "
                        f"{DR_SRC.split('; ')[1]}")  # fmt: skip


def _ba(ax, mean, diff, col, label, ba, unit):
    ax.scatter(mean, diff, s=14, color=col, alpha=0.75, lw=0, label=label)
    ax.axhline(0, color=theme.TEXT, lw=0.7)
    ax.axhline(ba["bias"], color=col, lw=1.4)
    for y in ba["loa"]:
        ax.axhline(y, color=col, lw=1, ls="--")
    ax.text(0.98, 0.97, f"bias {ba['bias']:+.2f} {unit} [{ba['bias_ci'][0]:+.2f}, {ba['bias_ci'][1]:+.2f}]\n"
            f"95% limits {ba['loa'][0]:+.2f} / {ba['loa'][1]:+.2f}  (SD {ba['sd']:.2f}, n = {ba['n']})",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox=dict(fc=theme.SURFACE, ec=theme.GRID, boxstyle="round,pad=0.3"))  # fmt: skip


def fig_bland_altman() -> None:
    s = json.loads(v.SUMMARY.read_text())
    tr = pl.read_parquet(v.OWN)
    m = tr.filter(pl.col("ab_est_lufs").is_not_null())
    theme.apply()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), gridspec_kw={"hspace": 0.38, "wspace": 0.22})
    for r, (meas, est, ab_col, unit) in enumerate([
        ("lufs", "est_lufs", "ab_est_lufs", "LU"), ("lra", "est_lra", "ab_est_lra", "LU"),
    ]):  # fmt: skip
        ax = axes[r, 0]
        _ba(ax, (tr[meas] + tr[est]) / 2, tr[est] - tr[meas], theme.MUTED,
            "Own rip: Essentia proxy − pyloudnorm", s["proxy_lossless"][meas], unit)  # fmt: skip
        name = "est. LUFS" if meas == "lufs" else "est. LRA"
        ax.set_title(
            f"({'ac'[r]}) {name}: proxy on the same lossless file", loc="left", fontsize=10.5
        )
        ax.set_xlabel(f"Mean of the two ({'LUFS' if meas == 'lufs' else 'LU'})")
        ax.set_ylabel(f"Estimate − measured ({unit})")
        ax = axes[r, 1]
        same = m.filter(pl.col("d_rg").abs() < 0.5)
        other = m.filter(pl.col("d_rg").abs() >= 0.5)
        ba_same = s["ab_vs_own"]["same_master"][meas]
        _ba(ax, (same[meas] + same[ab_col]) / 2, same[ab_col] - same[meas], theme.SERIES[0],
            f"same audio (AB replay gain within 0.5 dB of own rip, n = {same.height})", ba_same, unit)  # fmt: skip
        ax.scatter((other[meas] + other[ab_col]) / 2, other[ab_col] - other[meas], s=18,
                   marker="^", color=theme.SERIES[1], alpha=0.85, lw=0,
                   label=f"other audio behind the same IDs (n = {other.height})")  # fmt: skip
        ax.set_title(
            f"({'bd'[r]}) {name}: AcousticBrainz copies of the same recording",
            loc="left",
            fontsize=10.5,
        )
        ax.set_xlabel(f"Mean of the two ({'LUFS' if meas == 'lufs' else 'LU'})")
        ax.set_ylabel(f"AcousticBrainz − own measurement ({unit})")
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo - 0.25 * (hi - lo), hi + 0.12 * (hi - lo))  # room for legend and stats
        ax.legend(loc="lower left", fontsize=7.6, framealpha=0.92)
    fig.suptitle("Bland–Altman: AcousticBrainz estimates vs pyloudnorm on own CD rips",
                 x=0.01, ha="left", fontsize=13.5, y=0.98)  # fmt: skip
    theme.save_fig(fig, "p18_bland_altman", n=tr.height, source=SRC,
                   note="solid = mean difference (bias, 95% CI by album bootstrap), dashed = 95% limits of agreement; "
                        "est. LUFS / LRA = P03 calibration of Essentia replay gain / dynamic complexity\n"
                        "(b, d) triangles above 0: remasters tagged as the original album (Abbey Road 1987 CD, A Love Supreme); "
                        "below 0: single AAC copies 4–9 dB quieter (Art Angels; level-normalised or another master), excluded from the headline, which needs a lossless copy")  # fmt: skip


def fig_encoding() -> None:
    s = json.loads(v.SUMMARY.read_text())
    enc = pl.read_parquet(v.ENC)
    labs = [e[0] for e in __import__("lw.measure.own_rips", fromlist=["ENCODINGS"]).ENCODINGS]
    theme.apply()
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.8), sharey=True, gridspec_kw={"wspace": 0.08})
    rng = np.random.default_rng(0)
    for ax, (k, title) in zip(axes, [
        ("d_lufs", "(a) LUFS (pyloudnorm)"), ("d_lra", "(b) LRA (pyloudnorm)"),
        ("d_est_lufs", "(c) est. LUFS (Essentia replay gain)"), ("d_est_lra", "(d) est. LRA (dyn. complexity)"),
    ], strict=False):  # fmt: skip
        ax.axvline(0, color=theme.TEXT, lw=0.8)
        for i, lab in enumerate(labs):
            z = enc.filter(pl.col("encoding") == lab)[k].to_numpy()
            col = theme.SERIES[0] if lab.startswith("mp3") else theme.SERIES[1]
            ax.scatter(z, i + rng.uniform(-0.18, 0.18, z.size), s=8, color=col, alpha=0.35, lw=0)
            ax.plot(z.mean(), i, "D", color=col, ms=6, mec=theme.TEXT, mew=0.6)
            ax.annotate(f"{z.mean():+.2f}", (z.mean(), i), xytext=(0, -11), textcoords="offset points",
                        ha="center", va="top", fontsize=7.6)  # fmt: skip
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_xlabel("Lossy copy − lossless source (LU)")
    axes[0].set_yticks(
        range(len(labs)),
        [
            lb.replace("_", " ")
            .replace("v2", "V2 (~190k)")
            .upper()
            .replace("V2 (~190K)", "V2 (~190k)")
            + ("" if "v2" in lb else "k")
            for lb in labs
        ],
    )
    axes[0].invert_yaxis()
    fig.suptitle("CBR MP3 at 128–192 kbps reads 0.26–0.42 LU quieter; MP3 320k / V2 and AAC barely move the meters (diamond = mean)", x=0.01,
                 ha="left", fontsize=13.5, y=1.03)  # fmt: skip
    theme.save_fig(fig, "p18_encoding_shift", n=enc.height, source=SRC,
                   note=f"{s['encoding']['n_sources']} lossless tracks (2 per own CD, seed 0) re-encoded with ffmpeg: LAME MP3 CBR / V2, Apple AAC (aac_at) CBR")  # fmt: skip


def main() -> None:
    for f in (fig_scatter, fig_bland_altman, fig_encoding):
        f()
        print("wrote", f.__name__)


if __name__ == "__main__":
    main()
