# ruff: noqa: E501  (titles)
"""P21: final article figures (``figures/final_*.png``), re-rendered from the prompt figure code.

Brief charts 1-6 plus the two main-text additions (user decisions 2026-11-14): the P19
specification curve and the P18 encoding shift. Titles follow ``notes/p20_findings.md``.

    uv run python -m lw.viz.final
"""

from __future__ import annotations

import json
import shutil

import duckdb
import polars as pl

from lw.report import numbers
from lw.viz import p11, p12, p15, p16, p18, p19, theme


def titles(n: dict) -> dict[str, tuple[str, str | None]]:
    h, v = n["hero"], n["validation"]["proxy"]["lufs"]
    rise = h["m2005_09"] - h["m1980s"]
    return {
        "p12_hero_lufs": (
            "final_hero_lufs",
            f"Loudness rose about {rise:.0f} LU, then went flat after {h['peak_year']}",
        ),
        "p12_lra": (
            "final_lra",
            "Loudness range drifted down slightly into the 2000s and has been flat since; no rise after streaming normalisation",
        ),
        "p15_genre_small_multiples": ("final_genre_small_multiples", None),
        "p16_dumbbell_famous_albums": ("final_dumbbell_remasters", None),
        "p11_ridgeline_lufs_by_decade": ("final_ridgeline_decades", None),
        "p18_bland_altman": (
            "final_validation",
            f"The estimates agree with direct measurement: on {v['n']} CD tracks the bias is {v['bias']:+.2f} LU "
            f"(typical error {v['rmse']:.2f} LU)",
        ),
        "p19_spec_curve": ("final_spec_curve", None),
        "p18_encoding_shift": ("final_encoding_shift", None),
    }


def main() -> None:
    n = numbers.build()
    theme.FINAL.update(titles(n))
    d = pl.read_parquet(p12.YEARLY)
    for metric in ["lufs", "lra"]:
        p12._png(d, metric)
        p12._html(d, metric)
        src = theme.FIG_DIR / f"p12_{'hero_lufs' if metric == 'lufs' else 'lra'}.html"
        shutil.copy(src, theme.FIG_DIR / f"final_{'hero_lufs' if metric == 'lufs' else 'lra'}.html")
    p15.fig_small_multiples()
    p16.fig_dumbbell()
    p11.fig_ridgeline(
        duckdb.connect(),
        head="in_headline and year between 1980 and 2022",
        unit="unit = one recording on one release; headline = release years 1980–2022, tier A/B, "
        "not a reissue, ≥1 lossless submission, recording's first appearance",
    )
    p18.fig_bland_altman()
    p18.fig_encoding()
    p19.fig_spec_curve()
    theme.FINAL.clear()
    out = sorted(p.name for p in theme.FIG_DIR.glob("final_*"))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
