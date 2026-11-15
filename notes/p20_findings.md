# P20 — Results QA and final claims

_2026-11-14. A `data:validate-data` review of P03–P19: methodology, leakage, multiple comparisons, and whether each claim follows from its evidence. The fixes made during the review are listed at the end. P21 must take its claims, strength tags and wording from this file._

## Overall assessment: **share, with the caveats below**

The core result is reproducible and robust to every sample, weighting and genre choice tried: **the loudness rise ended around 2007–09, and there is no distinct post-2015 break.** Two things needed correcting during QA:
- the "slight easing since 2016" depends on how units are weighted;
- one promised P19 row was missing.

Both are now fixed. No calculation errors were found.

## Final claims

| # | claim | strength | evidence | wording for P21 |
|---|---|---|---|---|
| 1 | Median loudness of new releases rose about **5 LU**, from about −16 est. LUFS (1986) to −10.4 (2009). | **strong** | P12. Holds in every sample and weighting (P19) and in the DR Database ranking (ρ −0.90, P18). Calibration slope SE is 1.3%, so the 5 LU is ±0.07 from scale. | "rose about 5 LU" |
| 2 | **The rise ended around 2007–09**, years before streaming normalisation (default-on Dec 2015 – Nov 2017). | **strong** | Break scan: 95% set 2006–11, no 2015/16 (P13). Every genre bends around 2007; LOO prefers the bend by 25–59 elpd (P15). The loud end stopped first, 2004–05 (P14). Holds in all P19 specs. | "the rise stopped around 2007–09" |
| 3 | Against the brief's literal test (a straight 2000–14/15 trend), 2016–22 is about **0.6 LU below trend**, and most genres "pass". | **strong as a statement about that test; not evidence of a break** | 38/38 P19 estimates negative, median −0.61. 7–8 of 12 genres (P15). | Always show this **alongside** claim 4, and explain why the straight trend over-projects (CLAUDE.md "Break framing"). |
| 4 | **Once the 2007 bend is modelled, there is no distinct post-2015 break** in median loudness, the loud end or LRA. | **moderate** | Headline bend gap −0.08 ± 0.08 LU (joint p 0.23). P19 lossless variants run −0.18 to +0.17. Genre pooled +0.08 [−0.14, +0.31] (P15). P90 −0.03 (P15), +0.12 (P14). Remaster gap: no 2016 step, p 0.90 (P16). **Power:** the headline bend SE is 0.078, so the minimum detectable step (80% power, 2.8 × SE) is **≈ 0.22 LU**. "No break" means "no break larger than about 0.2 LU". | "no sign of a turn at 2015–16 larger than about 0.2 LU" |
| 5 | Since 2009 loudness has been **flat to within a few tenths of an LU**. | **moderate** | Track-weighted headline 2016–22 is 0.17 LU below 2005–15. **Album-weighted it is 0.01 LU** (−10.26 → −10.27), and the bend gap is **+0.14 to +0.17 LU** (P20 fix, below). The sign depends on whether a track or an album is the unit. | "**flat**" or "a plateau". **Do not** say "slightly quieter since 2016" without naming the weighting. |
| 6 | **The loudest decile never came down**: P90 ≈ −7.4 est. LUFS every year 2003–21. | **strong** (for "did not fall") | P14: three trend forms, two weightings, both CI types. P15 P90 pooled −0.03. | "the loudest records never came down" |
| 7 | The far loud tail (P99) rose after 2015, mostly in electronic. | **weak** | P14/P15. Values above −4.75 est. LUFS lie beyond the calibration range; a few scenes drive it. | Mention only as a hedged aside. |
| 8 | Est. LRA fell ~0.7 LU into the 2000s and has been flat since 2005. There is no post-2015 rise once silence is accounted for. | **moderate** | P12/P13/P15. The proxy tracks silence (ρ 0.92), and per-track error is ±7–8 LU (P18). Without silence it is flat at about 4.05. | Directions only; no absolute LRA values for wide-dynamic music. |
| 9 | **Remasters are louder than the original master**: median +1.1 LU per track; 1980s CD masters +2–3 LU. | **moderate** (strong in direction) | P16. Mis-tagged editions attenuate the gap; P18 found other masters behind shared IDs (Abbey Road, A Love Supreme). | "remasters are typically 1–3 LU louder" |
| 10 | The remaster gap peaked in 2005–09 and is about 0.3–0.5 LU smaller in 2015–22, with no 2016 step. | **weak–moderate** | P16 (album −0.47 [−0.81, −0.14], track −0.26; bend p 0.90). Small 1970s cells. | "has eased a little since the late 2000s" |
| 11 | Since 2009 music is **denser in timbre, not dynamics**: at fixed loudness and genre, spectra are flatter (+0.16 SD) and darker (−60 Hz); dynamics are unchanged. | **moderate** | P17. Rests on one Essentia descriptor. The SEs are clustered by release group, not by year, so they are optimistic. Contributor mix is untested. | "spectra got flatter and darker" |
| 12 | Genre exceptions: metal is quieter after 2016 (−0.33); classical/"other" are louder, but that is label mix and less silence, not mastering. | **weak** (metal); **moderate** (classical explanation) | P15/P17. Multiple comparisons: P(gap) > 0.95 one-sided on each side is about 10% two-sided per genre, so roughly 1 of 12 would flag by chance. P15 flagged 3 (1 below, 2 above), consistent with a near-null. | Metal: "the one genre with a hint of a post-2016 drop"; never as a headline. |
| 13 | The measure is valid. The proxy is unbiased on lossless CD audio (−0.04 LU, RMSE 1.15). The AcousticBrainz pipeline reproduces the extractor exactly on the same audio. Album ranking matches the DR Database. | **strong** (proxy) / **moderate** (DR: internal only, aggregates) | P03, P18. | Methods appendix, plus the encoding-shift figure in the main text (user decision). |
| 14 | Low-bitrate MP3 (≤192k CBR) reads 0.26–0.42 LU quiet. That explains the lossy gap in the data, which is why the headline is lossless-first. | **strong** | P18 controlled re-encode (SD ≤ 0.03); it matches P09's −0.44 LU. | Main text figure (user decision). |

**Answer to the brief's falsification test** ("wrong if loudness and LRA show no break after 2015 vs their 2000–2014 trend, in most genres"):
- **Literal reading:** passes, because the straight trend is exceeded in most genres.
- **Correctly specified trend** (the bend fits better by LOO in every genre): fails, with no general post-2015 break.

**Verdict: the hypothesis that streaming normalisation ended the loudness war is not supported. The war ended in a stalemate around 2007–09, before normalisation became the default.** No causal claim either way: the data show timing, not cause (brief §5).

## Methodology review

- **Question framing.** "Is the loudness war over?" splits into "did loudness stop rising" (yes, around 2007–09) and "did it fall after normalisation" (no detectable step). P21 should keep these apart. A "no" to the second doesn't imply the war is still going on.
- **Population.** The headline is a self-selected AcousticBrainz contributor sample (people who rip CDs or buy lossless), not all released music. The genre reweighting toward MusicBrainz's genre mix (P19) moves the level by +0.30 LU but not the shape. It can't correct for selection *within* genres (which albums contributors own).
- **Metric.** Est. LUFS is calibrated replay gain, not measured R128. It is monotone and near-linear (slope 1.042 ± 0.014), so yearly differences are robust, and per-track error averages out in medians. Genre/era bias of ±1 LU at album level (P18) would matter only if the style mix within a genre shifted a lot.
- **Comparison and baseline.** The central choice is the counterfactual trend. The bend form is chosen on fit (LOO, the break scan), not on the result. The bend year was estimated from the same series, but P13 swept k = 2006–11 and P15 tried 2010: the conclusion holds for every k (joint p 0.13–0.64).
- **Leakage.**
  - P03 calibration was fitted on the user's AAC files; P18 validated it out of sample on lossless CDs.
  - Nothing about the outcome entered sample definitions, with one exception: the first-appearance rule was introduced after looking at P12 years dominated by box sets. P19 shows the result with and without it (bend gap 0.00 to −0.08).
  - DR Database targets were chosen by coverage, not by loudness.
- **Multiple comparisons.**
  - Around 115 spec-curve estimates, 13 Bayesian fits × 12 genres, and about 20 quantiles. Individual "significant" cells (metal, P90 +0.12, the late cohort) are not reportable as findings.
  - The claims rest on patterns that recur across forms. The P19 specs share most units, so "% significant" is not a vote count.
  - P13 placebos showed that HAC p-values on this bending 23-point series are anti-conservative.

## Issues found

1. **[Medium; fixed] The "slight easing" depended on the weighting.** The track-weighted headline puts 2016–22 0.17 LU below 2005–15. With every release group weighted equally, the drop is 0.01 LU, and the bend-form gap is **+0.14 / +0.17 LU** (joint p 0.01 / 0.05). Albums with many tracks drive the small decline. *Fix:* added `rg_cap30` and `rg_equal` to P19, as P12 had promised. Claim 5 is reworded to "flat".
2. **[Medium; fixed] P19 was missing the P12 weighting rows** (above).
3. **[Medium; fixed] The dashed comparison line carried the lossy-only dip** (P19). *Fix (user decision):* it now excludes ≤192 kbps lossy copies. The hero chart was regenerated, and P13 refitted with an `all_codec_ex192` series (bend + 2016 gap −0.15 ± 0.09, joint p 0.002). This line still shows a small extra dip, which the caption must state.
4. **[Low; open, P21 caveat] The late-submission cohort shows −0.26 LU after the bend** (p 0.03). It can't be separated from contributor drift, because there is no submitter ID.
5. **[Low; open] Some SEs ignore year-level noise.** P17's fixed-loudness effects and P14's cluster bootstrap don't account for it. The directions survive, but the CIs are too narrow. They are flagged in claims 6 and 11.
6. **[Low; open] Coverage ends in 2022, and 2022 is thin** (10,362 units, 1,284 release groups). A slow decline after 2020 couldn't be detected yet.

## Calculation spot-checks (recomputed from `tracks.parquet`, independent of the pipeline code)

- Headline units: 2,604,546. ✔ Matches P12 and CLAUDE.md.
- Yearly headline medians 1980–2022: max |difference| from `p12_yearly.parquet` = 0.000. ✔
- Means of yearly medians: 1980–89 −15.61, 2005–15 −10.64, 2010–15 −10.64, 2016–22 −10.81; peak 2009 at −10.41. ✔ Matches P12 and the hero subtitle.
- P19 headline rows reproduce P13 (−0.60 / −0.56 straight, −0.06 / −0.08 bend). ✔
- P18 pinned numbers were re-run in the test suite (158 tests pass). ✔
- Album-weighted series: 2005–15 −10.26, 2016–22 −10.27 → issue 1.

## Visualisation review

- **Hero (`p12_hero_lufs.png`).** The title "rose about 5 LU … barely moved since: 2016–22 is 0.2 LU quieter" is true for track weighting. For P21, prefer "has been flat since 2009", or add "(track-weighted)". The y-axis isn't zero-based, which is correct for a line chart, and the units are labelled.
- **Spec curve.** States the dependence on model form plainly, with the headline marked. It goes in the P21 main text (user decision).
- **Small multiples (P15).** Shared 11 LU scale. ✔
- **Dumbbell (P16).** Values are AcousticBrainz estimates; keep the edition-mismatch flag and the identical-audio note.

## Required caveats for P21 / P24

- Est. LUFS / est. LRA are **calibrated estimates** from AcousticBrainz features, not R128 measurements: ±1.2–1.3 LU per track for LUFS, ±3–4 LU for LRA.
- The sample is **self-selected AcousticBrainz submissions** (lossless-first, tagged to MusicBrainz), skewed to rock and classical. Results describe this corpus; reweighting toward MusicBrainz's genre mix doesn't change the shape.
- **Data end in 2022**, the last year is thin, and post-2015 coverage comes mainly from late submitters.
- **"No break" means no step larger than about 0.2 LU**, and is stated against a bend fitted at 2007, with the straight-trend result shown alongside.
- "Flat since 2009" holds whether tracks or albums are weighted. The direction of the residual ±0.2 LU does not.
- **No causal claims.** Timing is compared with the normalisation timeline (P04); it does not establish cause.
- **No true crest factor** (AcousticBrainz stores no peaks). The DR Database figures are aggregates only, cited, with no per-album values.
- Remasters share recording IDs with the originals, so release-level values can mix masters (P18).

## Fixes made during P20
- `lw.models.robustness`: `rg_cap30` and `rg_equal` specs (now 20 specs, 114 estimates); spec-curve annotation updated.
- `lw.models.yearly` / `its` / `viz.p12`: dashed comparison is now `all_codec_ex192` (user decision 2026-11-14); `all_codec_ex160` is kept for the record. Hero and P13 figures regenerated.
