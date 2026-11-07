# P15: Genre hierarchical model

Run 2026-11-07 with `make models` (the P15 part, ~13 min for 13 fits). The code is `src/lw/models/genre_hier.py`, with figures from `src/lw/viz/p15.py`.

Outputs:
- `data/processed/p15_cells.parquet`;
- `p15_genre_effects.parquet`: per fit × genre, the gap, slopes and posterior probabilities;
- `p15_summary.json`: diagnostics, LOO, rankings; pinned in `tests/test_genre_hier.py`;
- thinned posterior draws in `data/interim/p15/*.npz`.

## Data

- **Cells:** genre × release-year cells of the headline sample (`in_headline`), 2000–2022, 12 genres × 23 years = 276 cells, **1,894,403 units**.
- **Genres** come from MusicBrainz tags only. Classifier-only units (`genre_source = 'hl'`) are excluded, per the user decision of 2026-11-07; including them is a sensitivity check.
- **Three metrics per cell:**
  - median est. LUFS;
  - **P90 est. LUFS** (the loud end, added after P14 by user decision);
  - median est. LRA, floored at 0.
- **Uncertainty:** each metric has a **release-group cluster bootstrap SE** (Poisson weights, 200 reps). Median SEs are 0.07–0.3 LU. Reggae and 2022 cells are thin, and their SEs are correspondingly larger.

## Model (PyMC 6.4, NUTS, 4 chains × 2,000 draws after 2,000 tuning steps, target_accept 0.97)

    straight:  μ_gt = a_g + b_g (t − 2016) + c_g post_t + d_g (t − 2016) post_t
    bend:      μ_gt = a_g + b1_g (t − 2007)₋ + b2_g (t − 2007)₊ + c_g post_t + d_g (t − 2016) post_t

- **Partial pooling.** Every coefficient is partially pooled across genres, with a non-centred normal hierarchy. Priors are weakly informative: slope means N(0, 0.2–0.3) LU/yr, level-change mean N(0, 1) LU, and half-normal genre-spread scales.
- **Cell likelihood:** Normal(μ, √(SE² + σ_g²)), with **AR(1) residuals** (shared φ, conditional likelihood). σ_g is a genre-specific year-to-year noise term, pooled on the log scale. Cell size n enters through the SE, so a big cell is measured precisely but can't outweigh the year-level noise.
- **Gap:** gap_g = c_g + 3 d_g, the mean 2016–22 difference from the genre's own counterfactual.
- **Bend year.** The bend form uses k = 2007, P13's data-driven hinge. It is parameterised around 2007 (the level at the bend, then slopes before and after). The first version, anchored at 2016 with a separate hinge term, mixed poorly on LRA (392 divergences, R-hat 1.02). It's the same model in different coordinates.
- **Straight form:** the brief's own test ("compared with their 2000–2014 trend").

## Diagnostics (`figures/p15_ppc.png`)

All 13 fits:
- **0 divergences**;
- **R-hat ≤ 1.010** (≤ 1.005 for the six main fits);
- **bulk ESS ≥ 753**.

Posterior predictive 95% intervals cover 96–99% of cells, slightly conservative; 50% intervals cover 52–58%. PIT ECDFs stay inside the 95% KS band. φ is 0.2–0.3 in the bend fits and 0.5–0.7 in the straight fits; the straight form leaves serial structure in its residuals.

**LOO (PSIS) strongly prefers the bend form for every metric.** Bend minus straight elpd:

| metric | elpd difference |
|---|---|
| median LUFS | **+59 ± 9** |
| P90 LUFS | +31 ± 6 |
| median LRA | +25 ± 7 |

With AR(1) these are one-step-ahead terms, so the comparison is indicative. A few cells have Pareto k of 0.9–1.1, but the margins are 3.5–6.5 SE.

## Results (`figures/p15_genre_small_multiples.png`, `figures/p15_genre_break_forest.png`)

Mean 2016–22 gap against each genre's own counterfactual, in LU. "Clearly" means posterior P(gap < 0) or P(gap > 0) > 0.95.

| metric | form | pooled gap [95% CrI] | clearly below / above |
|---|---|---|---|
| median est. LUFS | **bend** | **+0.08 [−0.14, +0.31]** | **1 / 2** (metal / classical, other) |
| | straight | −0.37 [−0.62, −0.08] | 7 / 0 |
| P90 est. LUFS | **bend** | **−0.03 [−0.23, +0.18]** | **0 / 1** |
| | straight | −0.34 [−0.57, −0.09] | 8 / 0 |
| median est. LRA | **bend** | **+0.07 [−0.09, +0.21]** | **0 / 1** (hip-hop) |
| | straight | +0.18 [+0.01, +0.35] | 0 / 7 |

1. **On the brief's literal test** (a straight 2000–14/15 trend), loudness is below trend and LRA above trend after 2015 in most genres. All 12 median gaps are negative, 7 of them clearly; 8 of 12 P90 gaps are clearly negative; 7 of 12 LRA gaps are clearly positive. Taken at face value, the hypothesis survives its falsification test.
2. **But the straight trend is the wrong counterfactual, in every genre.**
   - Every genre's median rose clearly before 2007, by **b1 = +0.08 to +0.17 LU/yr**.
   - After 2007 it was **flat or falling: b2 = −0.09 to +0.01**. It was clearly falling already in rock (−0.06), metal (−0.07), punk (−0.08), hip-hop (−0.09) and electronic (−0.03).
   - A straight 2000–15 line through that bend over-projects every genre. LOO confirms this, and so does the 2005–22 window: with the pre-period on the plateau, only 2 of 12 genres are clearly below.
3. **Once each genre's bend is modelled, there is no general post-2016 break:**
   - pooled median gap +0.08 LU (CrI −0.14 to +0.31);
   - 9 of 12 genres within ±0.2 LU.
   - The exceptions:
     - **Metal** is the one clear drop: **−0.33 [−0.59, −0.04]**, P = 0.98, robust to every sensitivity fit. It is also visible in the raw cells: metal's median falls from −9.0 (2015) to about −10.0 (2020–22).
     - **Classical** is clearly *louder*: **+0.52 [+0.04, +1.02]**. **"Other"** (soundtracks, world, experimental) is nearly so, at +0.38 [−0.02, +0.79]. Both are probably composition within the genre (neo-classical, crossover, soundtrack-style releases), not mastering. This is untested.
4. **The loud end (P90) by genre:**
   - no genre clearly below after the bend (jazz −0.30 and reggae −0.23 have P ≈ 0.9 but wide CrIs);
   - **electronic** is the only genre whose loud end kept rising after 2007 (b2 = **+0.054 LU/yr**, CrI +0.02 to +0.09), and it adds +0.24 after 2016 (P(> 0) = 0.96 in the summary count);
   - rock, metal and hip-hop loud ends have been easing since 2007 (b2 −0.03 to −0.07 LU/yr), with no extra step at 2016.

   This matches P14: the overall P90 is flat because electronic's rise offsets slow declines elsewhere.
5. **LRA:** after the bend, only **hip-hop** is clearly more dynamic after 2016: +0.27 [+0.03, +0.56]. Its est. LRA had *fallen* fastest before 2007 (−0.15 LU/yr) and has recovered since. Est. LRA tracks silence (P11), so this may partly be a change in intros, outros and skits rather than mastering.

### Sensitivity (median est. LUFS unless stated)

| fit | pooled gap | clearly below / above |
|---|---|---|
| bend at 2007, break 2016 (main) | +0.08 [−0.14, +0.31] | 1 / 2 |
| break 2015 | +0.08 [−0.16, +0.32] | 1 / 1 |
| bend at 2010 | +0.25 [−0.02, +0.55] | 0 / 2 |
| no AR(1) | +0.10 [−0.12, +0.32] | 1 / 2 |
| priors ×3 wider | +0.10 [−0.14, +0.35] | 1 / 2 |
| including classifier-only genres | +0.08 [−0.13, +0.32] | 1 / 2 |
| straight, window 2005–22 | −0.10 [−0.32, +0.13] | 2 / 0 |
| P90, bend, no AR(1) | −0.02 [−0.21, +0.17] | 1 / 1 |

Metal is the most negative genre in every median-LUFS fit.

## Answer to the brief's falsification test

> *"A finding that would be wrong if: loudness and LRA show no break after 2015 compared with their 2000–2014 trend, in most genres."*

**Against a literal straight 2000–14 trend, most genres do show the predicted break:** quieter (7–8 of 12) and more dynamic (7 of 12). **That trend is mis-specified.** Every genre's loudness rise ended around 2007, years before streaming normalisation became the default. Once that bend is in the model, which fits clearly better (LOO), **no general post-2015 break remains in loudness, the loud end, or LRA.** Only metal (quieter) and hip-hop's LRA (more dynamic) move in the predicted direction, and classical moves the opposite way.

**Verdict:** at genre level, the evidence **does not support** a post-2015 break in most genres. This agrees with P13 (aggregate) and P14 (quantiles). **Strength: moderate.**
- For: consistent across 13 fits, 3 metrics and both genre definitions, with good diagnostics and an out-of-sample preference for the bend form.
- Against: a common bend year (2007) is assumed for all genres; 23 yearly cells per genre; est. LUFS/LRA are proxies; data end in 2022.

No causal claim (brief §5).

## Figures

- `figures/p15_genre_small_multiples.png`: 12 genres (brief chart 3), cell medians and P90 with 95% CIs, posterior fits (95% band) and the no-2016-terms counterfactual. Panels are ordered by the median gap and share one 11 LU scale.
- `figures/p15_genre_break_forest.png`: gap by genre with 95% CrIs for median LUFS, P90 and LRA, in both forms.
- `figures/p15_ppc.png`: PIT ECDFs, interval coverage for all 13 fits, observed vs predicted.

## For later prompts

- **P17:** check whether classical's and "other"'s post-2016 rise is composition (neo-classical/crossover tags, track length, silence).
- **P19:** add the genre-pooled gap (bend and straight) as specification-curve rows. The straight vs bend contrast is the largest single source of spread found so far.
- **P20 / P21:** the brief's falsification test "passes" only under the straight-trend form. The write-up must show both forms and explain why the bend form is preferred (LOO and the per-genre b1/b2 slopes), so it doesn't look like a convenient model choice.
- **Possible extension:** genre-specific bend years. A common k = 2007 is a simplification; the P14 loud end bent around 2004–05.
