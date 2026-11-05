"""P03 figures: R128 conformance and the two proxy calibration fits."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from lw.measure import calibrate as cal
from lw.viz import theme

SRC_CONF = "Data: EBU Tech 3341/3342 test signals (generated)"
SRC_CAL = "Data: author's own library (AAC), measured with Essentia 2.1-beta2 + pyloudnorm"


def conformance() -> None:
    df = pl.read_parquet(cal.IN_DIR / "conformance.parquet")
    theme.apply()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), width_ratios=[5, 4])
    for ax, metric, unit in zip(axes, ["lufs", "lra"], ["LU", "LU"], strict=True):
        d = df.filter(pl.col("metric") == metric)
        tol = d["tol"][0]
        y = np.arange(d.height)[::-1]
        ax.axvspan(-tol, tol, color=theme.ERA_FILL, lw=0, zorder=0)
        ax.axvline(0, color=theme.MUTED, lw=0.8)
        for k, (col, lab) in enumerate(
            [("pyloudnorm", "pyloudnorm"), ("ffmpeg", "ffmpeg ebur128")]
        ):
            err = (d[col] - d["expected"]).to_numpy()
            ax.scatter(
                err,
                y + (0.12 if k == 0 else -0.12),
                s=55,
                color=theme.SERIES[k],
                edgecolor=theme.SURFACE,
                linewidth=2,
                zorder=3,
                label=lab,
            )
        ax.set_yticks(
            y, [f"{c}  (expect {e:g})" for c, e in zip(d["case"], d["expected"], strict=True)]
        )
        ax.set_xlim(-tol * 1.6, tol * 1.6)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.set_xlabel(f"Measured − expected ({unit})")
        what = (
            "Integrated loudness (Tech 3341)" if metric == "lufs" else "Loudness range (Tech 3342)"
        )
        ax.set_title(
            f"{what}\nshaded = ±{tol:g} {unit} tolerance", fontsize=10.5, fontweight="normal"
        )
        ax.text(tol * 1.0, y.max() + 0.6, "pass zone", fontsize=8, color=theme.TEXT_2, ha="right")
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, -0.38), ncol=2)
    fig.suptitle(
        "Both R128 meters pass all 9 EBU conformance cases",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    theme.save_fig(
        fig,
        "p03_r128_conformance",
        n=df.height,
        source=SRC_CONF,
        note="stereo 1 kHz sine cases; ffmpeg reports to 0.1 LU",
    )


def _scatter_fit(ax, lib, syn, model, xcol, ycol, xlabel, ylabel):
    ax.scatter(
        syn[xcol],
        syn[ycol],
        s=22,
        marker="s",
        color=theme.SERIES[1],
        alpha=0.8,
        edgecolor=theme.SURFACE,
        linewidth=0.6,
        zorder=2,
        label=f"Synthetic pink noise (n={syn.height})",
    )
    ax.scatter(
        lib[xcol],
        lib[ycol],
        s=12,
        color=theme.SERIES[0],
        alpha=0.45,
        lw=0,
        zorder=3,
        label=f"Real tracks (n={lib.height:,})",
    )
    if len(model["terms"]) == 1 or model["terms"][1].endswith("^2"):
        xs = np.linspace(lib[xcol].min(), lib[xcol].max(), 200)
        grid = pl.DataFrame({xcol: xs})
        ys = cal.predict_with(model, grid)
        lo, hi = model["cv_pi95"]
        ax.fill_between(
            xs,
            ys + lo,
            ys + hi,
            color=theme.MUTED,
            alpha=0.18,
            lw=0,
            zorder=1,
            label="95% prediction interval (album-held-out CV)",
        )
        ax.plot(xs, ys, color=theme.TEXT, lw=2, zorder=4, label="Calibration fit")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="x", visible=True)


def _resid(ax, lib, models, names, labels, xlabel):
    for k, (n, lab) in enumerate(zip(names, labels, strict=True)):
        m = models[n]
        y = lib[m["target"]].to_numpy()
        oof = cal.grouped_cv(lib, m["target"], m["terms"], lib["album"].to_numpy())
        r = y - oof
        order = np.argsort(y)
        # running median of CV residuals vs measured value
        bins = np.quantile(y, np.linspace(0, 1, 11))
        idx = np.clip(np.digitize(y, bins[1:-1]), 0, 9)
        cx = [np.median(y[idx == b]) for b in range(10)]
        cy = [np.median(r[idx == b]) for b in range(10)]
        q1 = [np.quantile(r[idx == b], 0.1) for b in range(10)]
        q9 = [np.quantile(r[idx == b], 0.9) for b in range(10)]
        ax.fill_between(cx, q1, q9, color=theme.SERIES[k + 2 if k else 0], alpha=0.15, lw=0)
        ax.plot(
            cx,
            cy,
            color=theme.SERIES[k + 2 if k else 0],
            marker="o",
            ms=5,
            label=f"{lab}: CV RMSE {m['cv_rmse']:.2f}",
        )
        del order
    ax.axhline(0, color=theme.MUTED, lw=0.8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Measured − predicted (LU), held-out albums")
    ax.set_title("Residuals by decile: median and P10–P90", fontsize=10.5, fontweight="normal")
    ax.legend(loc="upper left", fontsize=8)


def calibration_figs() -> None:
    res = json.loads(cal.OUT_JSON.read_text())
    models = res["models"]
    lib = cal.load_library()
    syn = pl.read_parquet(cal.IN_DIR / "synthetic.parquet")
    n_alb = res["calibration_set"]["n_albums"]
    theme.apply()

    # LUFS ~ replay_gain
    m = models[res["headline"]["lufs"]]
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(11.5, 4.8), width_ratios=[6, 5])
    _scatter_fit(
        a0,
        lib,
        syn,
        m,
        "replay_gain",
        "lufs",
        "AcousticBrainz replay_gain (dB; more negative = louder)",
        "Integrated loudness, pyloudnorm (LUFS)",
    )
    c = m["coef"]
    a0.text(
        0.97,
        0.97,
        f"LUFS = {c['const']:.2f} {c['replay_gain']:+.3f} × RG\n"
        f"CV RMSE {m['cv_rmse']:.2f} LU · R² {m['r2']:.3f}",
        transform=a0.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        color=theme.TEXT,
    )
    a0.legend(loc="lower left", fontsize=8)
    a0.set_title(
        "Fit on real tracks; synthetic shown for reference", fontsize=10.5, fontweight="normal"
    )
    _resid(
        a1,
        lib,
        models,
        ["lufs_rg", "lufs_rg_dc_al"],
        ["RG only", "RG + DC + avg loudness"],
        "Measured integrated loudness (LUFS)",
    )
    fig.suptitle(
        "ReplayGain maps to LUFS almost one-for-one",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    theme.save_fig(
        fig,
        "p03_rg_vs_lufs",
        n=lib.height,
        source=SRC_CAL,
        note=f"{n_alb} albums; CV holds whole albums out",
    )

    # LRA ~ dynamic_complexity
    m = models[res["headline"]["lra"]]
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(11.5, 4.8), width_ratios=[6, 5])
    _scatter_fit(
        a0,
        lib,
        syn,
        m,
        "dynamic_complexity",
        "lra",
        "AcousticBrainz dynamic_complexity (dB)",
        "Loudness range, pyloudnorm (LU)",
    )
    c = m["coef"]
    a0.text(
        0.03,
        0.97,
        f"LRA = {c['const']:.2f} {c['dynamic_complexity']:+.2f} × DC\n"
        f"CV RMSE {m['cv_rmse']:.2f} LU · R² {m['r2']:.3f} · ρ {m['spearman']:.2f}",
        transform=a0.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        color=theme.TEXT,
    )
    a0.legend(loc="lower right", fontsize=8)
    a0.set_title(
        "Fit on real tracks; synthetic shown for reference", fontsize=10.5, fontweight="normal"
    )
    _resid(
        a1,
        lib,
        models,
        ["lra_dc", "lra_dc_al_rg"],
        ["DC only", "DC + avg loudness + RG"],
        "Measured loudness range (LU)",
    )
    fig.suptitle(
        TITLE_LRA.get("t", "Dynamic complexity tracks LRA, with wide scatter"),
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    theme.save_fig(
        fig,
        "p03_dyncomp_vs_lra",
        n=lib.height,
        source=SRC_CAL,
        note=f"{n_alb} albums; CV holds whole albums out",
    )


TITLE_LRA: dict[str, str] = {}

if __name__ == "__main__":
    conformance()
    calibration_figs()
