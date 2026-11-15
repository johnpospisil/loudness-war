# P19 — Robustness and specification curve

_2026-11-14. Code: `lw.models.robustness`, `lw.viz.p19`; `make robustness`. Outputs: `data/processed/p19_specs.parquet` (every fit), `p19_yearly.parquet` (yearly series per spec), `p19_summary.json`._

## Design
- **Each spec** is a sample filter, plus unit weights for the genre specs. For each spec we take the yearly (weighted) median est. LUFS and fit the P13 models.
- **Model forms**, each with a break B = 2015 or 2016:
  - **Straight pre-trend** (the brief's test), window 2000–22 or 2005–22.
  - **Bend-first**: a continuous hinge at 2007 plus the level/slope change at B, window 2000–22.
- **Estimate shown:** the mean post-break gap against the fitted counterfactual, with Newey-West SEs. 17 specs × 6 fits = 102 estimates; the early-submission cohort can't be fitted (see below).
- **Coverage rule:** a year is used only if it has ≥ 500 units. Submission cohorts also need ≥ 25% of their own 2000–14 yearly count. Cohorts are right-censored: early submitters can't hold later releases.
- A fit needs ≥ 4 post-break years. The early cohort (dump parts 0–9) ends in 2017, so it drops out.

## Results (gap in LU, ± 1.96·SE)
| spec | straight 2000–22, B=2016 | straight 2005–22, B=2016 | bend 2007 + B=2016 (joint p) |
|---|---|---|---|
| Headline | −0.56 ± 0.41 | −0.26 ± 0.28 | −0.08 ± 0.16 (0.23) |
| No first-appearance rule | −0.29 | −0.10 | 0.00 (0.18) |
| Every submission lossless | −0.48 | −0.25 | −0.12 (0.38) |
| Tier A only | −0.43 | −0.12 | +0.06 (0.19) |
| No compilations / studio originals | −0.65 / −0.68 | −0.23 / −0.20 | −0.03 / −0.01 |
| RG agrees within 1 dB (P18) | −0.59 | −0.34 | −0.17 (0.14) |
| No high-IQR units / one unit per recording | −0.55 / −0.55 | −0.29 / −0.30 | −0.12 / −0.13 |
| Genre (A) MB mix / (C) fixed 2000–14 mix | −0.67 / −0.62 | −0.27 / −0.20 | −0.07 / −0.01 |
| All codecs excl. ≤160k / ≤192k / incl. all | −0.69 / −0.64 / −0.86 | −0.39 / −0.32 / −0.55 | **−0.22 / −0.15 / −0.37** (p 0.003 / 0.002 / 0.02) |
| Cohort mid (parts 10–19) / late (20–29) | −0.33 / −0.62 | −0.26 / −0.40 | −0.26 ± 0.61 / **−0.26 ± 0.20** (p 0.03) |

- **Straight-trend test:**
  - All 34 estimates (2000–22 window) are negative. The median is −0.62 LU, and 91% have a CI below 0.
  - With the 2005–22 window the median is −0.29, and 41% have a CI below 0.
- **Bend-first:**
  - The median is −0.11 LU, with a range of −0.42 to +0.07. 18% have a CI below 0.
  - Every lossless-headline variant (sample, matching, measurement, genre) lies between −0.18 and +0.07, with no significant joint test.
  - **The model form decides the answer, not the sample choice.**
- **Genre reweighting moves the level, not the shape:**
  - (A) The MusicBrainz genre mix adds about +0.30 LU from 2000 onwards (MB has more hip-hop and pop than AcousticBrainz) and ≈ 0 in the 1980s.
  - (C) A fixed mix leaves the 2000–14 level unchanged, but 1980s values come out −0.17 and 2016–22 values −0.20 LU (2021–22 −0.35 to −0.45). Within-genre loudness rose slightly more than observed, and drifted a little lower after 2016.
  - Both still peak in 2008. Neither shows a 2016 step once the bend is fitted (p 0.18, 0.50).
- **Residual dips:**
  - **All-codec samples:** about −0.2 LU even after the bend. The lossy-only units above 192 kbps fell 0.22 LU between 2009–14 and 2016–22 (−10.61 → −10.83), while lossless units did not. P18 found that 256k AAC, 320k and V2 encoding move LUFS by ≤ 0.05 LU, so it isn't the encoding. It is either which music exists only as lossy files after 2016, or level-altered downloads/rips the P09 flags miss. The data can't separate the two. The lossless headline avoids the issue; the dashed comparison line inherits it.
  - **Late-submission cohort (parts 20–29, most of the 2016–22 data):** −0.26 [−0.46, −0.06] after the bend. The mid cohort is −0.26 but very noisy. With no submitter ID, contributor drift can't be ruled out here. Cohort medians for 2000–17 sit within about 0.2 LU of each other, except the mid cohort, which is 0.3–0.6 LU quieter in 2000–10.

## For P20
- **Strong:** the 2016–22 median lies below a straight 2000–15 extrapolation in every spec.
- **Strong:** the rise ended around 2007–08 in every sample and weighting.
- **Moderate:** there is no distinct post-2015 break in the lossless headline once the bend is modelled (all lossless variants ≈ 0). Two caveats: all-codec samples and the late cohort show about −0.2 LU, so a small post-2016 easing can't be excluded. Its size is bounded at about 0.3 LU.
- The headline's genre composition doesn't drive the result.

## Limitations
- The yearly-median fits have 18–23 points, so HAC SEs are approximate. The specs are not independent: they share most units, so the share of significant estimates is not a vote count.
- Cohorts are defined by dump part, which is a proxy for submission date. There is no submitter ID.
