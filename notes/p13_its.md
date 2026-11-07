# P13: Interrupted time series

Run 2026-11-07 with `make models` (the P13 part). The code is `src/lw/models/its.py`, with figures from `src/lw/viz/p13.py`.

Outputs:
- `data/processed/p13_its.parquet`: every fit;
- `p13_scan.parquet`: the break-point profile;
- `p13_year_fe.parquet`: genre-adjusted year effects;
- `p13_its_summary.json`: pinned in `tests/test_its.py`.

## Model

On a yearly series y_t, with break year B and post_t = 1 when t ≥ B:

    y_t = a + b (t − B) + c post_t + d (t − B) post_t + e_t

- `c` is the level change and `d` the slope change.
- The counterfactual is the pre-trend projection.
- The **mean post gap** = c + d · mean(t − B) over the post years.
- SEs are Newey-West (HAC, 2 lags, small-sample correction).

Fitted on the **headline** sample (`in_headline`), est. LUFS, yearly medians from P12. The series is 2000–2022 (n = 23 years), as in the brief's "2000–2014 trend". The main breaks are **2015** (decided default) and **2016** (first full era year; `era_start()` = 2015.95).

## Results

| model (headline, est. LUFS) | break | level change | slope change (LU/yr) | mean post gap | pre-slope |
|---|---|---|---|---|---|
| yearly medians, 2000–22 | 2015 | −0.41 ± 0.20 (p 0.04) | −0.056 ± 0.030 | **−0.60 ± 0.22** | +0.054 |
| yearly medians, 2000–22 | 2016 | −0.46 ± 0.20 (p 0.02) | −0.033 ± 0.033 | **−0.56 ± 0.21** | +0.048 |
| yearly medians, 2005–22 (pre-period on the plateau) | 2015 | −0.22 ± 0.15 (p 0.13) | −0.018 ± 0.031 | −0.28 ± 0.17 | +0.015 |
| yearly medians, 2005–22 | 2016 | −0.27 ± 0.14 (p 0.055) | +0.004 ± 0.034 | −0.26 ± 0.14 | +0.011 |
| track-level OLS + genre FE, cluster SE by release group (1.89M tracks; means) | 2016 | −0.29 ± 0.04 | −0.055 ± 0.012 | −0.45 ± 0.04 | +0.032 |
| year FE net of genre, two-step WLS | 2016 | −0.36 ± 0.16 | −0.050 ± 0.024 | −0.51 ± 0.20 | +0.041 |

(± = one SE.)

**At face value**, 2016–22 sits about 0.5 LU below the projected 2000–15 trend, and that's nominally significant. The diagnostics below show that this compares against the wrong counterfactual.

1. **The pre-trend is still rising, but the series had levelled off.** 2000–15 contains the tail of the loudness rise, which peaked at −10.41 in 2009. A straight line through it keeps climbing (+0.05 LU/yr), so any flat post-period reads as a "drop".
   - With the pre-period starting in 2005, on the plateau, the gap halves to **−0.26 to −0.28 LU (p 0.06–0.13)**.
   - On the pre-P12 definition (`lossless_all_units`) it is **−0.09 to −0.10**.
2. **The gap grows when the break is moved *earlier*:**
   - 2000–22 window: 2013 −0.77, 2014 −0.66, 2015 −0.60, 2016 −0.56, 2017 −0.49;
   - 2005–22 window: −0.46 / −0.32 / −0.28 / −0.26 / −0.21.

   A break caused at 2015/16 would peak there instead (`figures/p13_break_year_sensitivity.png`).
3. **The data-driven break is 2007–2010** (`figures/p13_breakpoint_profile.png`):
   - level + slope change: best **2010**, ≈95% set **2006–2011**;
   - continuous bend: best **2007**, set 2006–2009.

   Neither set contains 2015 or 2016. (The set is approximate: years within 3.84 of the minimum of n·log SSR.)
4. **The decisive test: allow the bend, then test the era.** The model is a continuous bend at k plus level/slope terms at B. For k = 2006…2011 and B = 2015/2016, **the 2015/16 terms are never needed**: joint HAC Wald p = **0.13–0.64**, with gaps −0.16 to +0.40 LU whose sign depends on k (`figures/p13_its_fit.png`, panel b). The pre-P12 definition gives the same answer (p 0.10–0.51).
5. **Placebo breaks 1995–2010** (15 pre-years, post truncated at 2014):
   - 88% of them give a larger |gap| than the 2016 estimate;
   - 69% are "significant" at 5%.

   These placebo windows sit inside the real 1995–2009 rise-and-plateau, so they aren't a null distribution. They do show that **HAC p-values from a segmented model on this bending series are anti-conservative**: nominal p ≈ 0.02 for the 2016 level change is not strong evidence.

## Other series (yearly medians)

| series | 2016 gap, 2000–22 window | 2016 gap, 2005–22 | bend + 2016 terms, joint p |
|---|---|---|---|
| all codecs excl. ≤160 kbps (first appearance) | −0.69 | −0.39 | 0.000–0.003 (gap −0.30 to +0.16, sign depends on bend year) |
| headline, < 5% near-silent frames, est. LUFS | −0.89 | −0.37 | 0.00–0.45 (gap −0.29 to +0.27) |
| headline est. LRA | +0.20 LU (above a falling pre-trend) | +0.20 | — |
| headline < 5% near-silent est. LRA | +0.05 | +0.03 | — |

- In two comparison series the era terms are "significant" in the two-break model, but the estimated gap changes sign across bend years. That is the signature of curvature, not a clean step, and with n = 23 and 5 parameters the p-values are fragile. P19 will show this spread.
- Est. LRA sits about +0.2 LU above its own falling pre-trend after 2015, a tiny move towards more dynamics. It vanishes for near-silence-free tracks (+0.03 to +0.05 LU).

## Answer to the brief's falsification test

> *"A finding that would be wrong if: loudness and LRA show no break after 2015 compared with their 2000–2014 trend, in most genres."*

- **Against a straight 2000–14/15 trend, there is a deviation**, about −0.5 LU in est. LUFS. But it **isn't a break at 2015**. The loudness rise ended around **2007–2010**; the data place the break there (≈95% set 2006–2011). Once that bend is modelled, a 2015/16 break adds nothing for the headline (p 0.13–0.64).
- What remains after 2009 is a **slow easing of a few tenths of an LU** that starts years before streaming normalisation became the default.
- **Est. LRA shows no meaningful post-2015 break either:** +0.2 LU, and about 0 without silence.
- **Verdict:** the headline evidence **does not support a distinct post-2015 break**. On the brief's own criterion, the hypothesis that normalisation ended the loudness war at 2015/16 is not supported at the aggregate level. The "in most genres" half is P15's job.
- Per brief §5, none of this is causal. The timing is simply earlier than the era.

**Strength: moderate.** The bend-first test and the break-point profile agree, and the result holds for both sample definitions. On the other side: n = 23 yearly points, fragile HAC inference, est. LUFS is a calibrated proxy (P03), and data end in 2022, so a slow post-2015 decline could still be under way.

## Figures

- `figures/p13_its_fit.png`: (a) single break vs a straight pre-trend; (b) bend first, then the 2016 terms.
- `figures/p13_break_year_sensitivity.png`: candidate era breaks in two windows, plus placebo breaks.
- `figures/p13_breakpoint_profile.png`: profile over break years (headline LUFS, near-silence-free LUFS, LRA).
