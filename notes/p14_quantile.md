# P14: Quantile trends

Run 2026-11-07 with `make models` (the P14 part, ~5 min). The code is `src/lw/models/quantile_trends.py`, with figures from `src/lw/viz/p14.py`.

Outputs:
- `data/processed/p14_quantile.parquet`: every fit, with bootstrap and HAC CIs and raw coefficients;
- `p14_yearly_quantiles.parquet`: P5 to P99 by year, with bootstrap CIs;
- `p14_hinge_profile.parquet`;
- `p14_summary.json`: pinned in `tests/test_quantile_trends.py`.

## Question

Did the loudest decile come down? (Brief: "Did the loudest masters change?")

## Method

- **Track-level quantile regression** of est. LUFS on the P13 segmented form, for τ = 0.05 … 0.95. The main quantiles are 0.1, 0.5 and 0.9.
- **Sample:** the headline sample (`in_headline`), release years 2000–2022, **2,011,235 units**.
- **Forms**, as in P13:
  - a single break at 2016 (and 2015) against a straight 2000–15 pre-trend;
  - the same with the pre-period on the plateau (2005–22);
  - **bend first**: a continuous hinge at 2007 (P13's data-driven bend; 2006–2011 also run) plus the level/slope terms at 2016.
- **Solver.** The regressors depend only on the year, so the QR estimating equations reduce to Σ_t x_t W_t (F_t(x_t′β) − τ) = 0, where F_t is year t's weighted empirical CDF. Newton steps solve the exact track-level problem in about 10 ms. Tests check it against statsmodels `QuantReg`, against duplicated-data weights, and by perturbing the solution to confirm it minimises the check loss.
- **Two kinds of CI:**
  - a **release-group cluster bootstrap** (Poisson weights, 500 reps, seed 20261107) for unit-sampling error. It treats each year's deviation from the line as fixed, so it is narrow.
  - **Newey-West** on the yearly τ-quantile series, as P13 did for the median. This includes year-to-year noise and is the relevant one for a break claim, although P13's placebos showed it is anti-conservative on this bending series.
- **Variant `fixed_genre_mix`:** units with a tag-sourced genre are reweighted so that every year has the pooled 2000–14 genre mix. This measures within-genre change and anticipates P19's option C. It excludes classifier-only genres, leaving 1.89M units in 2000–22.

## Results

Mean of the yearly quantiles (est. LUFS, headline):

| quantile | 2005–09 | 2010–15 | 2016–22 | fixed genre mix, 2016–22 vs 2010–15 |
|---|---|---|---|---|
| P5 | −22.20 | −21.48 | −20.44 | +0.45 |
| P10 | −19.23 | −18.47 | −17.66 | +0.34 |
| P25 | −14.19 | −13.88 | −13.82 | −0.18 |
| P50 | −10.66 | −10.64 | −10.81 | −0.29 |
| P75 | −8.63 | −8.67 | −8.80 | −0.21 |
| **P90** | **−7.36** | **−7.39** | **−7.36** | −0.06 |
| P95 | −6.71 | −6.69 | −6.49 | +0.08 |
| P99 (descriptive) | −5.46 | −5.25 | −4.52 | +0.55 |

Mean 2016–22 gap against the projected trend, in LU. Brackets are the bootstrap 95% CI; ± is the HAC SE.

| model | P10 | P50 | **P90** |
|---|---|---|---|
| straight 2000–15 trend | −0.13 [−0.47, +0.19] ± 0.30 | −0.55 [−0.65, −0.46] ± 0.21 | **−0.20 [−0.27, −0.14] ± 0.16** |
| 2005–15 trend (plateau) | −0.36 [−0.84, +0.12] ± 0.35 | −0.28 [−0.43, −0.14] ± 0.14 | **+0.04 [−0.04, +0.11] ± 0.06** |
| bend at 2007, then 2016 terms | −0.33 [−0.86, +0.16] ± 0.35 | −0.14 [−0.29, +0.01] ± 0.08 | **+0.12 [+0.05, +0.21] ± 0.06** |
| same, fixed genre mix | +0.29 [−0.33, +0.85] ± 0.19 | −0.06 [−0.24, +0.10] ± 0.06 | +0.11 [+0.03, +0.20] ± 0.04 |

1. **The loudest decile did not come down.**
   - P90 has sat at −7.3 to −7.5 in every year from 2003 to 2021. It averages −7.36 both before and after 2016.
   - Against a still-rising 2000–15 trend it is 0.2 LU short. Against the plateau trend the gap is +0.04. With the 2007 bend allowed for, it is +0.12 LU *above* the model, a small but bootstrap-significant overshoot.
   - The fixed genre mix gives the same answer. Every specification puts the P90 change after 2016 between −0.3 and +0.2 LU.
2. **The loud end stopped rising first.** The best hinge year from the QR check-loss profile falls with τ:
   - P90–P95: 2004–05;
   - P75–P85: 2006;
   - the median: 2007–09.

   Before 2016 the pre-trend slope is 0.02 LU/yr at P90, against 0.04 at the median and 0.12 at P10 (panel a of `p14_quantile_slope_change.png`). The loud end reached its ceiling in the mid-2000s.
3. **The quiet end kept rising, mostly through the genre mix.**
   - Headline P10 rose about 0.8 LU per period; its best hinge is 2019, so it is still climbing.
   - At a fixed genre mix, P10 is nearly flat from 2005–15 (−18.96 → −18.92) and up 0.3 LU in 2016–22. The fixed mix also halves the pre-2016 slope at τ ≤ 0.2.
   - The quiet tail is mostly classical, which is 15% of the lossless sample and shrinking (P10). So the "narrowing from below" that P12 reported is largely composition, not quiet records getting louder.
4. **Shortfalls are confined to the lower-middle quantiles.** After allowing the bend, τ ≈ 0.15–0.45 sit 0.2–0.5 LU low in the headline. At a fixed genre mix this falls to about 0 to −0.07. The HAC intervals mostly include 0.
5. **The far loud tail got louder after 2015, within genres** (description only):
   - P99 went −5.25 → −4.52 (−4.75 at a fixed mix), and P95 −6.69 → −6.49.
   - The share of units above −6 est. LUFS doubled, from about 2% to about 4%.
   - These are mostly electronic: drum & bass annuals, riddim/dubstep comps, hardcore, and underground Bandcamp releases. Electronic's own P90 rose from −7.9 to −7.1 while hip-hop, metal, rock, pop and R&B fell 0.2–0.6 LU (P15 will model this).
   - **Caveat:** above about −4.75 est. LUFS (the loudest track in the P03 calibration set) the values are extrapolated, so the P99 *level* is uncertain. The rise is relative to earlier years measured the same way.

## Answer

**No, the loudest decile did not come down.** The upper quantiles stopped rising in the mid-2000s, before the median, and have not fallen since. After 2016 they sit at or slightly above every trend we fit, and the extreme tail (P99) rose, inside genres. Together with P13, the aggregate picture is that the loudness war ended in a plateau around 2005–2009, not a retreat after 2015.

**Strength: moderate to strong for "P90 did not fall".** The result holds across three trend forms, two weightings and both CI types, and the yearly values barely move. Weak for the far-tail rise: it is outside the calibration range and driven by a few scenes.

No causal claim (brief §5). Timing only, plus the usual limits: est. LUFS is a proxy with about ±1.3 LU per-track error, which blurs neighbouring quantiles into each other but is stable over time; the data end in 2022; and the contributors are self-selected.

## Figures

- `figures/p14_quantile_trends.png`: P90, P50 and P10 by year (bootstrap CIs, fixed-genre-mix points) with the QR fits, each panel spanning 6 LU; plus P95/P99 with the calibration ceiling.
- `figures/p14_quantile_slope_change.png`: coefficient plot by τ, with pre-slope, slope change, the gap against a straight trend (two windows) and the gap after the bend (two weightings). Bands show the bootstrap 95% CI; bars show the HAC 95% CI.

## For later prompts

- **P15:** the loud tail goes in opposite directions by genre (electronic up; hip-hop, metal, rock, pop and R&B down). Model genre-specific P90 or the share above −8, not only medians.
- **P19:** add the quantile gaps (τ = 0.1/0.9) as specification-curve rows; the fixed-genre-mix weighting here is option C.
- **P21:** headline sentence candidate: "The loudest records never came down; the war ended in a stalemate around 2005–09."
