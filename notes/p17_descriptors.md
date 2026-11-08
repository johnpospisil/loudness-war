# P17: Other descriptors

Run 2026-11-07 with `make models` (the P17 part, ~2.5 min). The code is `src/lw/models/descriptors.py`, with figures from `src/lw/viz/p17.py`.

Outputs in `data/processed/`:
- `p17_descriptors.parquet`: per unit;
- `p17_yearly.parquet`;
- `p17_genre_change.parquet`;
- `p17_density.parquet`;
- `p17_composition.parquet`;
- `p17_summary.json`: pinned in `tests/test_descriptors.py`.

## Question

Is music denser even if it isn't louder? And, added by user decision on 2026-11-07, is classical's (and "other"'s) post-2016 rise in loudness a change in what's released (composition) rather than in mastering?

## Descriptors (headline sample, 2,604,546 units, 100% coverage)

All descriptors are **recomputed from lossless submissions only**, taking the median per unit from `ab_matched`. P09's feature columns are medians over all submissions, and lossy encoders low-pass the signal, which shifts centroid and flatness.

| descriptor | meaning | denser when |
|---|---|---|
| average loudness (Essentia, 0–1) | rescaled average loudness; 1 = small dynamic range | higher |
| dynamic complexity (dB) | mean loudness deviation | lower |
| **frame crest proxy (dB)** | 20·log10(loudest ÷ mean 46-ms frame RMS) | lower |
| spectral flatness (Bark bands, Essentia FlatnessDB, 0–1) | flat, noise-like spectrum | higher |
| spectral complexity | number of spectral peaks | higher |
| onset rate (per s) | rhythmic event density | higher |
| spectral centroid (Hz) | brightness | n/a |
| near-silent frames | share of frames below −60 dB | n/a |

**No true crest factor.** AcousticBrainz stores **no sample peak or true peak**, so the brief's "peak − loudness" crest factor (PLR) can't be computed. The frame crest proxy captures macro-dynamics over frames of about 46 ms. It misses the transient peaks that limiting removes, so it is **not** a substitute for PLR.

## Results

### Trends (`figures/p17_descriptor_trends.png`): mean of yearly medians

| descriptor | 1990–99 | 2000–08 | 2009–15 | 2016–22 |
|---|---|---|---|---|
| average loudness | 0.793 | 0.845 | 0.858 | 0.851 |
| dynamic complexity (dB) | 4.34 | 4.06 | 3.96 | 4.02 |
| frame crest proxy (dB) | 10.27 | 9.27 | 8.87 | 8.90 |
| **spectral flatness** | 0.166 | 0.172 | 0.175 | **0.190** |
| spectral complexity | 13.7 | 14.3 | 15.1 | 14.5 |
| onset rate | 3.44 | 3.44 | 3.39 | 3.37 |
| **spectral centroid (Hz)** | 1,261 | 1,213 | 1,193 | **1,130** |
| near-silent share | 0.121 | 0.104 | 0.095 | 0.096 |

- **The dynamics measures followed loudness.** Average loudness, dynamic complexity and the crest proxy all moved towards "denser" through the 1990s and 2000s, then have been **flat since about 2009**, with no turn at 2016.
- **The spectral measures kept moving after 2009.** Flatness rose fastest after 2015 (0.175 → 0.190), and the centroid fell about 60 Hz, so spectra got flatter and darker. Spectral complexity peaked in 2009–15 and eased.

### Density at fixed loudness (`figures/p17_density_vs_loudness.png`)

The model is OLS descriptor ~ period + 1-LU est. LUFS bin + genre, fitted on a seeded 25% sample of tag-genre units from 1990–2022, with release-group cluster SEs. The table shows 2016–22 against 2009–15.

| descriptor | effect | in SDs |
|---|---|---|
| average loudness | +0.0015 ± 0.0035 | 0.00 |
| dynamic complexity | +0.007 ± 0.031 | 0.00 |
| frame crest proxy | −0.08 ± 0.04 dB | −0.02 |
| **spectral flatness** | **+0.0117 ± 0.0010** | **+0.16** |
| spectral complexity | −0.30 ± 0.09 | −0.04 |
| onset rate | −0.09 ± 0.02 | −0.07 |
| spectral centroid | −60 ± 6 Hz | −0.12 |

**Answer: denser in timbre, not in dynamics.** At the same est. LUFS and genre, 2016–22 music has the same dynamics as 2009–15 music: average loudness, dynamic complexity and crest are all at 0.00–0.02 SD. Its spectra, though, are flatter (+0.16 SD) and darker (−0.12 SD). The 1990s were sparser at the same loudness in both senses: −0.42 SD in flatness and +0.10 SD in average loudness.

The flatness rise is small in absolute terms, and it's **not attributed to anything**. Candidates include production styles (sub-bass-heavy mixes, saturation, lo-fi textures) and changes in what AcousticBrainz users submitted; neither is tested here. Brief §5 applies.

### By genre, 2009–15 → 2016–22 (`figures/p17_genre_descriptor_change.png`)

- **Dynamics moved with loudness in every genre.** The genres that got quieter (hip-hop −0.29, pop −0.25, R&B −0.17 LU) got more dynamic: dynamic complexity +0.17 to +0.40, crest +0.27 to +0.40. Classical, the genre that got louder, got less dynamic (crest −0.59).
- **Spectra got flatter in 11 of 12 genres** and darker in 10. The changes are largest in hip-hop (flatness +0.03, centroid −154 Hz, spectral complexity −2.1), pop (−146 Hz) and R&B (−100 Hz).

### Classical and "other" composition check (P15 follow-up, `figures/p17_classical_composition.png`)

**Sub-genre tags don't explain it.**
- At the 2009–15 sub-genre mix, classical's median change is still +0.48 LU (95% CI +0.19 to +0.77), against +0.52 observed.
- The rise is *within* canonical repertoire (+0.65), while contemporary/crossover/screen got quieter (−0.27).
- Caveat: only about 30% of classical release groups carry a sub-genre tag beyond "classical".

**Record label explains about half, and silence most of the rest.** OLS on classical units 2009–22 with release-group cluster SEs, mean change 2016–22 vs 2009–15:

| model | classical | other |
|---|---|---|
| unadjusted | +0.44 [+0.14, +0.74] | +0.32 [+0.06, +0.59] |
| silence only | +0.30 [+0.00, +0.60] | +0.19 [−0.05, +0.43] |
| **label fixed effects** (60 / 68 labels with ≥ 300 units) | **+0.20 [−0.09, +0.50]** | +0.21 [−0.05, +0.46] |
| label FE + near-silent share | **+0.12 [−0.18, +0.41]** | +0.09 [−0.15, +0.33] |

- **The label mix shifted:**
  - Deutsche Grammophon went from 3.5% to 10.0% of classical units, and Alpha Classics from 0.5% to 5.4%;
  - Brilliant Classics, BIS and Chandos shrank.
- **Within labels the rise isn't significant.** Within Deutsche Grammophon, median est. LUFS is flat (−19.11 → −19.09).
- **Tracks got shorter and quieter-free:** median near-silent share 0.31 → 0.27, length 214 → 201 s.

**Conclusion.** Classical's +0.5 LU after 2016, which P15 flagged as "clearly louder", is **mostly a shift in which labels' releases AcousticBrainz users submitted, plus less silence in the tracks**. It isn't evidence that classical masters got louder. The same holds for "other". Strength: moderate. Labels proxy for catalogue, and catalogue is self-selected by contributors.

## Figures

- `figures/p17_descriptor_trends.png`: 8 descriptors, yearly medians 1980–2022 with IQR and cluster-bootstrap CIs.
- `figures/p17_density_vs_loudness.png`: descriptor by est. LUFS bin for four periods, plus the period effects at fixed loudness and genre.
- `figures/p17_genre_descriptor_change.png`: genre × descriptor change 2009–15 → 2016–22 (extra figure).
- `figures/p17_classical_composition.png`: classical sub-genre mix, loudness by sub-genre, and the composition decomposition (extra figure).

## For later prompts

- **P19:** add the classical/"other" label-FE result next to P15's genre ranking, and the flatness-at-fixed-loudness effect as a descriptor row.
- **P20:** the "denser in timbre" claim is new and modest (+0.16 SD), and it rests on one Essentia descriptor; tag it moderate, not strong. The "no crest factor" limitation goes in the limitations list.
- **S02 (spectral balance):** the falling centroid (−60 Hz at fixed loudness, −154 Hz in hip-hop) is the starting point.
