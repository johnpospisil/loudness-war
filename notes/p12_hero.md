# P12: Hero chart v1 and LRA chart

Run 2026-11-07 with `make models` (the P12 part). The yearly table comes from `src/lw/models/yearly.py` and goes to `data/processed/p12_yearly.parquet`; the figures come from `src/lw/viz/p12.py`.

## Headline sample (changed during P12, user decision 2026-11-07)

**`in_headline`** = `in_main_lossless` **and `first_appearance`**: **2,604,546 units**. A unit counts only if its release year is at most one year after the recording's earliest dated MusicBrainz release (`rec_first_year`, built in `dedupe.py`). This removes box sets, best-ofs and other compilations of **old recordings**, which P08's release-group reissue rule can't see, because they are new release groups. It keeps 87% of `in_main_lossless` units (98% of non-compilations, 58% of compilations).

**Why.** The first P12 run on `in_main_lossless` showed single box sets of archive recordings dominating whole years. *Bach 333 – The New Complete Edition* is 5,411 tracks, 4.6% of 2018 (median −19.2). A 2004 complete-works edition is 3,438 tracks (3.9%). Compilations also fell from 35% of units (2005–09) to 15% (2016–22). That shift in composition masked a small post-2009 easing and dragged pre-2015 years down (`figures/p12_weighting_sensitivity.png`).

The old definition stays in `p12_yearly.parquet` as sample `lossless_all_units`, for P19.

## Method

- **Samples:**
  - `headline` = `in_headline`;
  - `all_codec_ex160` = first-appearance `in_main` minus units whose loudness comes from a ≤160 kbps lossy copy (dashed line);
  - `headline_low_sil` = headline units with fewer than 5% near-silent frames (LRA chart, P11);
  - `lossless_all_units` = the pre-change headline.
- **Per release year:** median, P10, P90, n units and n release groups.
- **95% CI on the median: cluster bootstrap by release group.** Each release group gets a Poisson(1) weight; 1,000 replicates; seed 20261107. Tracks of one album share a master and often several editions; a unit test checks that clustering widens the CI.
  - The median CI half-width for est. LUFS is **0.17 LU** (max 0.33).
- **Est. LRA is floored at 0.**
- **Era shading** starts at `era_start()` = 2015.95. The dotted line marks `era_consolidated()` = 2017.90.

## Results: est. LUFS (`figures/p12_hero_lufs.png` + `.html`)

| mean of yearly medians | 1980–89 | 1990–2004 | 2005–09 | 2010–15 | 2016–22 |
|---|---|---|---|---|---|
| **headline** | −15.61 | −12.86 | −10.65 | −10.64 | **−10.81** |
| all codecs excl. ≤160 kbps (first appearance) | −15.47 | −13.02 | −10.79 | −10.61 | −10.78 |
| pre-change headline (`lossless_all_units`) | −15.58 | −12.96 | −10.96 | −10.90 | −10.87 |
| headline P10 / P90 | −21.0 / −10.9 | −20.7 / −9.2 | −19.2 / −7.4 | −18.5 / −7.4 | −17.7 / −7.4 |

- **Median loudness rose about 5 LU**, from a low of −16.2 in 1986 to a peak of −10.41 in 2009.
- **Since then it has eased only slightly.** 2010–17 sits at −10.6 to −10.7, and 2018–21 at −10.85 to −10.99 (yearly CIs about ±0.1–0.2). 2016–22 is **0.2 LU quieter than 2005–15**.
- The easing is gradual and visible from about 2013, so it doesn't look like a step at the era start. Whether 2015/16 is a break against the trend is P13's question.
- **The loud end didn't move:** P90 sits at −7.4 in every period since 2005. **The quiet end rose:** P10 went −19.2 → −17.7. So the distribution narrowed from below.
- **The comparison line tracks the headline** within −0.31 to +0.25 LU in every year (mean −0.03). Restricting to lossless doesn't drive the result.
- **2022 is thin:** 10,362 units from 1,284 release groups, median −10.50 (CI −10.76 to −10.26).

## Results: est. LRA (`figures/p12_lra.png` + `.html`)

| mean of yearly medians | 1980–89 | 1990–2004 | 2005–09 | 2010–15 | 2016–22 |
|---|---|---|---|---|---|
| headline | 7.57 | 7.31 | 6.89 | 6.80 | 6.89 |
| < 5% near-silent frames | 4.33 | 4.14 | 4.04 | 4.03 | 4.07 |
| all codecs excl. ≤160 kbps | 7.42 | 7.03 | 6.50 | 6.46 | 6.64 |

- Est. LRA fell about 0.7 LU from the 1980s to the 2000s and has been flat since 2005. 2016–22 is 0.09 LU above 2010–15, a negligible change.
- Among near-silence-free tracks it is flat at about 4.05 LU since the mid-2000s. Most of the earlier drift tracks the falling share of silence in tracks (P11).

## Weighting sensitivity (`figures/p12_weighting_sensitivity.png`)

Five rules, on the main sample with a lossless copy, for 2005–09 vs 2016–22:

| rule | 2005–09 | 2016–22 |
|---|---|---|
| all units (pre-change headline) | −10.96 | −10.87 |
| **first appearance only (headline)** | **−10.64** | **−10.81** |
| compilations excluded | −10.43 | −10.82 |
| release group capped at 30 units | −10.57 | −10.72 |
| every release group weighted equally (the "average release", a different estimand) | −10.41 | −10.31 |

The three rules that remove old material agree:
- a peak around 2007–09;
- 0.15–0.4 LU lower by 2016–22;
- the easing starts before 2015.

P19 will carry all five as rows of the specification curve.

## Flags for P13+

- P13 runs on `in_headline`. Expect a small negative level/slope change of a few tenths of an LU at most, and check whether it beats the pre-trend (the easing starts about 2010–13).
- The near-silence-free est. LUFS series eases from −9.2 (2008–10) to −10.3 (2020–22), also starting before the era.
- P14: P90 is flat and P10 rose, so look for compression from below rather than the loud tail coming down.
- P10 reweighting targets for the headline are in `genre_mix.parquet` (`weight_headline`).
