# P12: Hero chart v1 and LRA chart

Run 2026-11-07 with `make models` (the P12 part). The yearly table comes from `src/lw/models/yearly.py` and goes to `data/processed/p12_yearly.parquet`; the figures come from `src/lw/viz/p12.py`.

## Method

- **Samples:**
  - **headline** = `in_main_lossless`: 2,997,479 units, 1980–2022.
  - **comparison** = `in_main` minus units whose loudness comes from a ≤160 kbps lossy copy (user decision, P09).
  - **near-silence-free** = headline units with fewer than 5% frames below −60 dB, for the LRA chart (P11).
- **Per release year:** median, P10, P90, n units and n release groups.
- **95% CI on the median: cluster bootstrap by release group.** Each release group gets a Poisson(1) weight; 1,000 replicates; seed 20261107. Tracks from one album share a master and often several editions, so a track-level bootstrap would understate the uncertainty.
  - Median CI half-width: 0.19 LU for est. LUFS (max 0.45) and 0.15 LU for est. LRA.
  - A unit test checks that clustering widens the CI.
- **Est. LRA is floored at 0** (171 units were below 0).
- **Era shading** starts at `era_start()` = 2015.95 (P04). The dotted line marks `era_consolidated()` = 2017.90, when three major services normalise by default.

## Results: est. LUFS (`figures/p12_hero_lufs.png` + `.html`)

| mean of yearly medians | 1980–89 | 1990–2004 | 2005–09 | 2010–15 | 2016–22 |
|---|---|---|---|---|---|
| headline | −15.58 | −12.96 | −10.96 | −10.90 | −10.87 |
| all codecs excl. ≤160 kbps | −15.45 | −13.12 | −10.99 | −10.80 | −10.84 |
| P10 / P90 (headline) | −20.9 / −11.0 | −20.7 / −9.2 | −20.2 / −7.5 | −19.2 / −7.5 | −17.9 / −7.4 |

- **Median loudness rose about 5 LU from the late 1980s (low point −16.2 in 1986) to the mid-2000s, then held steady.** In the headline series there is no visible drop after the era starts. Formal test: P13.
- **The loudest decile didn't come down.** P90 stays at −7.4 to −7.5 from 2005 to 2022. The quiet end rose (P10 −20.2 → −17.9), so the distribution **narrowed from below**. P14 tests this formally.
- **The comparison line tracks the headline** within ±0.33 LU in every year (mean difference −0.01 LU). The lossless restriction doesn't drive the result.
- **2022 is thin:** 10,558 units from 1,290 release groups. Its median (−10.48) has a CI of ±0.24.

## Results: est. LRA (`figures/p12_lra.png` + `.html`)

| mean of yearly medians | 1980–89 | 1990–2004 | 2005–09 | 2010–15 | 2016–22 |
|---|---|---|---|---|---|
| headline | 7.57 | 7.37 | 7.10 | 6.99 | 6.92 |
| < 5% near-silent frames | 4.35 | 4.16 | 4.05 | 4.05 | 4.07 |
| all codecs excl. ≤160 kbps | 7.41 | 7.07 | 6.63 | 6.57 | 6.66 |

- Est. LRA drifted down by about 0.6 LU over four decades, with **no rebound after 2015**.
- Among near-silence-free tracks it has been **flat since the mid-2000s (4.05 → 4.07)**. As P11 showed, most of the headline drift tracks the falling share of silence in tracks.

## The weighting question (`figures/p12_weighting_sensitivity.png`)

**The 2004 and 2018 dips each come from one huge box set.**
- 2018: *Bach 333 – The New Complete Edition*, 5,411 tracks, 4.6% of the year's headline units, median −19.2.
- 2004: a complete-works edition with 3,438 tracks, 3.9%.

These are archive recordings in a new release group, so P08's reissue flag (release year > group's first year + 1) doesn't catch them. Compilations make up 35% of headline units in 2005–09 and only 15% in 2016–22. That compositional shift **masks a small post-2009 easing** in the headline series:

| median est. LUFS, headline sample | 2005–09 | 2016–22 | change |
|---|---|---|---|
| every unit counts once (current headline) | −10.96 | −10.87 | +0.09 |
| **only the recording's first appearance** (release year ≤ the recording's earliest MB release year + 1; keeps 87% of units, 98% of non-compilations) | −10.64 | −10.81 | −0.17 |
| compilations excluded | −10.43 | −10.82 | −0.39 |
| each release group capped at 30 units | −10.57 | −10.72 | −0.15 |
| every release group weighted equally (a different estimand: the average release) | −10.41 | −10.31 | +0.10 |

The three rules that remove old material in new packaging agree:
- the level peaks around **2007–09 at about −10.4 to −10.5**;
- it is **0.15–0.4 LU lower by 2016–22**;
- the easing starts **before 2015** (2010–14 already lower than 2009).

The "first appearance" rule targets the estimand most directly: "loudness of music newly released that year". It also generalises the reissue logic from release group to recording. **Changing the headline definition is a user decision** (question raised after P12).

## Flags for P13+

- P13 should be run on whichever headline definition is chosen. The other definitions become rows in the P19 specification curve.
- The near-silence-free est. LUFS series eases from −9.2 (2008–10) to −10.3 (2020–22) and starts about 2011. Again, that is before the era.
- P14: the loud tail is flat, while the quiet tail rose.
