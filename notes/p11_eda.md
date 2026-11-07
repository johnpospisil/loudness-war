# P11: EDA and sanity checks

Run 2026-11-07 with `make eda`. The code is `src/lw/eda.py` and `src/lw/viz/p11.py`. Outputs are `data/processed/p11_profile.json` and `data/processed/p11_spotcheck.csv`, with key numbers pinned in `tests/test_eda.py`.

"Est. LUFS / LRA" means the AcousticBrainz proxies calibrated in P03 (CV RMSE 1.34 LU / 2.93 LU per track). The headline sample is `in_main_lossless` (3.0M units); the main sample is `in_main` (7.2M).

## 1. Distributions

| (headline sample) | P1 | P10 | median | P90 | P99 |
|---|---|---|---|---|---|
| est. LUFS | −28.9 | −19.8 | −11.7 | −7.8 | −5.5 |
| est. LRA (LU) | 2.2 | 3.9 | 7.1 | 13.5 | 22.7 |
| length (s) | 45 | 119 | 229 | 400 | 852 |
| near-silent frames (< −60 dB) | 0.5% | 2.9% | 10.7% | 36% | 63% |

**Median est. LUFS by decade:** 1980s −15.8, 1990s −13.7, 2000s −11.1, 2010s −10.9, 2020s −10.9 (`figures/p11_ridgeline_lufs_by_decade.png`).
- The whole distribution moved, not just its tail: the loud shoulder that builds through the 1990s becomes the mode by the 2000s.
- The 1980s level fits early CD mastering, roughly −14 to −18 LUFS.

## 2. Correlations (headline sample, Spearman)

| pair | ρ | reading |
|---|---|---|
| est. LUFS ~ est. LRA | −0.48 | louder tracks have less range, as expected |
| est. LRA ~ near-silent frame share | **+0.92** | see section 4 |
| est. LRA ~ average_loudness | −0.79 | Essentia's `average_loudness` is low for quiet, sparse tracks |
| est. LUFS ~ average_loudness | +0.56 | |
| est. LUFS ~ spectral centroid | +0.46 | louder masters are brighter |
| est. LUFS ~ bark-band flatness | −0.48 | |

Est. LUFS and est. LRA are linear in replay_gain and dynamic_complexity, so they correlate ±1 with those by construction.

## 3. Outliers and implausible values (main sample, 7.20M units)

- **Est. LUFS above −4: 17,565 (0.24%); above −3: 8,862.** These are mostly electronic, noise and metal, 36% from 2015–19. Real masters do reach about −3 LUFS, so they stay.
  - One caveat: the calibration extrapolates there. P03 found the loudest decile under-predicted by about 1 LU per track.
- **Est. LUFS below −35: 8,750.** These are classical, ambient and field recordings. They stay.
- **Est. LRA below 0: 171; below 1: 5,324.** Negative LRA is impossible. It happens when dynamic_complexity is near zero (the intercept is −0.24). This is too rare to matter for medians, but **P12 should floor est. LRA at 0** for display.
- **Est. LRA above 25: 34,121**, mostly classical and silence-heavy tracks (section 4).
- **Longer than 30 minutes: 7,629** (DJ mixes, full-work classical files). They stay; a robustness check could drop them.
- **`average_loudness` < 0.2 for 10% of units.** These are quiet, sparse tracks (classical first, with a median of 40% near-silent frames). It's a property of the descriptor, not a parse error. Extractor 2.1-beta5-dev shows more of them, but it has only 2.8k units.

## 4. Est. LRA is strongly tied to silence

Est. LRA (from dynamic complexity) correlates **ρ = 0.92** with the share of near-silent frames. EBU R128 LRA gates silence out (absolute −70 LUFS and relative −20 LU gates), so true LRA should depend on it much less.

- The median near-silent share falls from about 12% (1980s) to about 9.5% (2020s). Est. LRA falls with it, from 7.4 to 6.8 LU (`figures/p11_silence_vs_lra.png`).
- **Among units with fewer than 5% near-silent frames (22% of the headline sample), est. LRA barely moves:** 4.4 LU (1980–82) → 4.05 LU (2001–22).
- The P03 alternative fit (DC + average_loudness, CV RMSE 2.54 LU) gives the same trend shape, 0.7 LU lower, and is just as tied to silence (ρ = 0.90). So switching calibration doesn't fix this.
- **Implication for P12 and P17.** The est. LRA trend mixes two things: less dynamic range within the music, and less silence in tracks (fewer gaps and fades, shorter quiet intros). The second may itself be a production trend, but it isn't "loudness range" in the R128 sense. **P12 should show the near-silence-free LRA line next to the all-units line**, and the text should say est. LRA is a dynamics proxy that includes silence.
- The near-silence-free subset also shows **est. LUFS peaking around 2007 (−9.2) and easing to about −10.1 by 2019** (all units: flat at −10.9). That subset differs in genre mix, so this is a lead for P12/P15, not a finding.

## 5. Edition mismatch (old releases measured from remastered files)

- Some "original release" units are clearly later remasters tagged with the original release. ***Back in Black*:** units tagged to 1980 vinyl and cassette releases read −9.2 est. LUFS, while the 1986 US CD reads −16.0.
- **Aggregate check:** in 1980–96, units tagged to vinyl or cassette releases read 1–2.6 LU louder than CD-tagged units of the same year. But **within genre the gap almost disappears** (1984–90: rock +0.02 LU, metal +0.2, pop +0.5). For the same recording in 1980–90 the median paired difference is **0.0 LU** (mean +0.17; 27% of pairs > +1 LU, 23% < −1 LU).
- So the aggregate gap was genre mix: classical is mostly CD-tagged and quiet. There is no systematic bias in the yearly medians, but **individual classic albums can carry remaster loudness**. That matters for the P16 remaster pairs, the P16 dumbbell chart and the P22 album lookup. 30% of pre-1991 main-sample units are tagged to vinyl or cassette releases (24% in the lossless sample).
- 1980s units with est. LUFS above −8 are 1–3% of each year. Tier-B matches are over-represented among them (20–26% vs 12–19%), which fits misdated files.

## 6. Album spot-check (`figures/p11_spotcheck_albums.png`)

**Published values and their terms.**
- The main public per-album loudness database (dr.loudness-war.info) states no licence ("Copyright © 2022", no API or export), so its values aren't used.
- The test set comes from **Wikipedia's "Loudness war" article** (CC BY-SA), which cites:
  - 20 albums criticised for loud or clipped masters;
  - 2 noted as dynamic: *Random Access Memories* ("We never tried to make it loud") and *Chinese Democracy* ("the least compression").
- Added to these are 32 famous reference albums, giving 54 in all (`data/reference/spotcheck_albums.csv`, with the source quote per row).

**Method.** Each album is matched to its MusicBrainz release group: normalised title, artist inside the credit, first-release year within 1 year, and the group with the most units. All **54 of 54** matched.
- The album value is the median over its non-reissue units, or over its edition year's releases for the three criticised reissues (Duran Duran ×2 2010, *Raw Power* 1997).
- It is placed within the main sample of the same release year.

**Expectation, written before the run:** criticised albums above their year's median, most in the top quartile; dynamic albums below the median.

| result | |
|---|---|
| criticised above year median | **20 / 20** (one-sided sign test p ≈ 1e-6) |
| criticised in top quartile | 14 / 20; median percentile 0.88 |
| *Californication* / *Death Magnetic* / *Raw Power* (1997) | 100th / 99th / 99th percentile |
| *Morning Glory?* | 95th percentile of 1995 (−8.9 est. LUFS vs year median −13.9) |
| weakest | Duran Duran (2010 remaster) 51st, *Seven and the Ragged Tiger* (2010) 68th, Paul Simon *Surprise* 63rd |
| *Random Access Memories* / *Chinese Democracy* | 42nd / 48th percentile (below median, as expected) |

The weakest two are remasters ranked against 2010 new releases, which were already loud. *Raw Power* 1997 rests on only 3 units.

**Reference albums look plausible:**
- *Brothers in Arms* (1985) −17.5 est. LUFS, 30th percentile, high LRA;
- *Buena Vista Social Club* −15.4;
- *The Marshall Mathers LP* −7.8;
- *Back to Black* −7.8;
- *Back in Black* −9.2, inflated by the edition mismatch above.

**Caveats.** "Criticised" albums are a selected set: critics pick famously loud records, so this checks *ranking*, not absolute level. The proxy's absolute accuracy is P03's (1.3 LU per track) and P18's job.

## Flags for later prompts

- **P12:** floor est. LRA at 0. Add the near-silence-free LRA line. Say est. LRA includes silence.
- **P15 / P17:** silence share as a covariate or descriptor; the post-2007 LUFS easing among dense tracks.
- **P16 / P22:** watch out for edition mismatch in individual classic albums. Prefer tier-A units on CD/digital releases for pre-1990 originals in the dumbbell chart.
- **P19:** possible specs: drop tracks > 30 min; near-silence-free subset.

## Figures

- `figures/p11_ridgeline_lufs_by_decade.png` (brief chart 5)
- `figures/p11_lufs_vs_lra.png` (2D histogram, all vs near-silence-free)
- `figures/p11_spotcheck_albums.png`
- `figures/p11_silence_vs_lra.png` (added: the silence check)
