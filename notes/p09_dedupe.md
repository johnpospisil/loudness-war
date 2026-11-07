# P09 — Dedupe and the analysis table

_2026-11-05. Code: `src/lw/build/dedupe.py` (`make dedupe`), figures `src/lw/viz/p09.py`._
_Output: `data/processed/tracks.parquet` (9,269,713 rows, 1.6 GB) and `tracks_funnel.json`.
Excluded submissions, each with its reason: `data/interim/p09_excluded.parquet`._

## What a row is

A **unit** is one MusicBrainz recording on one MusicBrainz release. It holds the median of
every audio feature over that unit's submissions, the submission count, the IQR and range of
estimated LUFS and LRA, codec flags, and the P08 release and group fields.

- 6.77M recordings across 1.22M releases.
- 47% of units have 2 or more submissions. The median is 1 and the mean is 3.1.

LUFS and LRA come from the P03 headline fits:
- LUFS = −23.44 − 1.042 · RG
- LRA = −0.24 + 1.775 · DC

Both are linear, so the median of the calibrated value equals the calibration of the median.

## Funnel

| step | rows | removed |
|---|---:|---:|
| AcousticBrainz submissions | 29,460,584 | |
| exact repeats (same key and audio md5) | 29,457,994 | 2,590 |
| matched to an MB release (P08) | 29,392,297 | 65,697 |
| replay gain and dynamic complexity present and finite | 29,392,297 | 0 |
| duration ≥ 30 s | 29,156,947 | 235,350 |
| estimated LUFS ≤ 0 | 29,152,661 | 4,286 |
| estimated LUFS ≥ −60 | 29,152,535 | 126 |
| valid LRA (DC > 0 and LRA ≤ 50 LU) | 29,141,994 | 10,541 |
| **units** (recording × release) | **9,269,713** | |
| release year 1980–2022 (`in_core`) | 8,793,287 | 476,426 |
| main sample: tier A/B, not a reissue (`in_main`) | 7,206,307 | 1,586,980 |
| … and not `inconsistent` | 6,640,436 | 565,871 |

Quality exclusions remove 0.85% of matched submissions, and most of those are under 30 s.

Exclusions are applied to each submission **before** the median. One broken file therefore can't move a unit's median. A unit only disappears when all of its submissions are excluded.

## The main finding: gain-normalised lossy files

The first build flagged **17.7% of multi-submission units as inconsistent**. These units have a LUFS IQR above 1.5 LU or an LRA IQR above 3 LU. The median IQR, though, is only 0.02 LU. Looking at the raw submissions explained the gap. Within one unit, the spectral RMS, spectral energy, average loudness and silence rate agree to 3–4 digits, yet `replay_gain` differs by 6–10 dB.

The cause is **lossy files whose owners applied MP3Gain or aacgain**. These tools change the stored gain without re-encoding. Essentia normalises the audio before computing its spectral features, so those features match while the measured loudness doesn't.

The evidence:

- **Same-audio pairs** (spectral RMS within 0.5%, energy within 1%, length within 1 s; 8.0M pairs in a 5% sample):

  | pair type | replay gains differ by > 1 dB |
  |---|---:|
  | FLAC–FLAC | 0.09% |
  | ALAC–ALAC | 0.4% |
  | MP3–MP3 | 6.4% |
  | FLAC–MP3 | 16% |
  | AAC–MP3 | 18% |

  A lossless file can't carry an applied gain change.
- **Replay-gain histograms**, release years 1995–2015, Essentia 2.1-beta2 (`figures/p09_lossy_gain_check.png`, left panel):
  - MP3 has a second hump at −6.75 to −4.5 dB, peaking at −5.5 dB. That is about 5–6% more MP3s in the band than FLAC's shape predicts.
  - FLAC has no hump.
  - AAC has a smaller hump at −9 to −8.25 dB.
- **The sample dump keeps the tags.**
  - 7.0k of its 19.1k MP3s carry `mp3gain_minmax`, and 1.9k carry `mp3gain_undo`, which means the gain was actually applied.
  - The MP3Gain-tagged MP3s have a median RG of −1.2 dB, against −5.3 dB for the untagged ones.
  - P05 doesn't parse these tags, so the full dumps don't have them.
- **Essentia 2.1-beta1 vs 2.1-beta2 is not an extractor difference.**
  - Same-audio beta1 and beta2 FLAC pairs agree: the median difference is 0.00 dB and only 0.6% differ by more than 1 dB.
  - Beta1's offset (+2.3 dB at the median, bimodal) comes from its MP3s. That's 365k early submissions with a median RG of −5.5 dB, which is the MP3Gain target.
- **Inconsistency by codec mix** (multi-submission units):

  | unit codecs | inconsistent |
  |---|---:|
  | all lossless | 1.7% |
  | lossy only | 17.8% |
  | mixed | 21% |

**Fix: lossless first.** A unit's `lufs` and `lra` are the medians over its lossless submissions when it has any (`loudness_source = 'lossless'`), and otherwise over its lossy ones. Three alternative columns are kept for robustness checks: `lufs_all` (every submission), `lufs_lossless` and `lufs_lossy`. The same set exists for LRA.

In the main sample:
- 3.00M units (42%) get their loudness from lossless copies.
- 4.21M units (58%) are lossy only. For release years 2015–2022 that's 1.18M of 1.95M.

**Effect on yearly medians.** Within each year, the lossless-first median and the all-codec median differ by at most 0.1 LU. The P03 calibration was fitted on AAC files that weren't gain-normalised, so it isn't affected.

**A watch-point for P12, P13 and P19.** In main-sample units with both a lossless and a lossy copy, the lossy copy reads 0.03–0.10 LU quieter for release years 1980–2012. From 2014 to 2021 that gap jumps to **−0.37 to −0.41 LU**. The share of lossy copies more than 2 LU quieter (the MP3Gain signature) falls at the same time, from ~20% to ~3%. So this new gap is a different effect. Possible causes include lossy copies taken from normalised streams, or from Mastered-for-iTunes or other headroom masters. Either way, it starts right at the break we're testing. Lossy-only units from release years 2016–2021 also read 0.34 LU quieter than lossless-sourced ones (−11.28 vs −10.94 LUFS); for 2010–2015 there is no gap. **An all-codec series could therefore show a spurious post-2015 drop of a few tenths of an LU.** The lossless-only line in P12 and the lossless-only specification in P19 are now the key checks, not optional ones.

## Other choices

- **Inconsistent units:** 2 or more submissions with a LUFS IQR above 1.5 LU or an LRA IQR above 3 LU, which is about one P03 calibration RMSE each. 17.7% of multi-submission units are flagged, almost all because of LUFS (LRA alone: under 1.5%). Dynamic complexity isn't affected by a gain change. These units are kept but flagged, and P19 drops them as one of its specifications.
- **Lossless codecs:** FLAC, ALAC, PCM (WAV/AIFF), APE, WavPack and TTA. AcousticBrainz's own `lossless` flag marks WavPack as lossy, so it isn't used. 22.1% of units are all-lossless and 39.7% have at least one lossless submission.
- **`low_bitrate`:** units whose submissions are all lossy with a median bitrate under 128 kbps. That's 2.0% of units, and the share falls over time.
- **Exact repeats:** a retagged file keeps its audio md5 but can match a different release. The copy kept is the best-matched one (tier, then release MBID), so runs are reproducible.
- **Determinism:** `mode()` breaks ties arbitrarily. The first build moved `units_core` by 6 between two runs. Every `mode()` is now ordered, and two runs give the same checksum over the key columns.
- **Analysis year:** the most common `year` among the unit's submissions, with ties going to the earliest. It only varies when a release is undated and the year comes from tags (P08).
- **Memory:** exact medians and modes can't spill to disk in DuckDB. The first attempt ran out of memory at 6.5 GB. The kept rows are now staged in 48 hash buckets of recordings and aggregated one bucket at a time: 100 s and about 5 GB of temp space, deleted afterwards.

## Numbers

- Main sample: 7,206,307 units. Median estimated LUFS is −11.79 and median estimated LRA is 6.71 LU.
- Units per release year:
  - rise from 15k (1980) to a peak of 366k (2014, all tiers);
  - 273k main-sample units in 2019 and 195k in 2021;
  - **18k in 2022**.
- Tier B grows after 2016 (`figures/p09_tracks_per_year.png`), because recent files often lack release tags.
- Lossless share of units by release year (most common codec): 32% for 1990, 37% for 2015, 56% for 2022. The 2022 figure rests on a thin sample.

## Figures

- `figures/p09_data_funnel.png`
- `figures/p09_tracks_per_year.png`
- `figures/p09_codec_mix_by_year.png`
- `figures/p09_lossy_gain_check.png` (added: the gain-normalisation diagnostic)

## Follow-up decisions (user, 2026-11-05)

1. **The headline sample is lossless only.** `in_main_lossless` means the main sample plus at least one lossless submission: 2,997,536 units, 771,003 of them from 2015–2022. Median estimated LUFS is −11.72 and median LRA is 7.14 LU. P12/P13 use it as the main line, with the all-codec `in_main` line as the dashed comparison.
2. **Re-stream the dumps for gain tags.** `src/lw/build/parse_gaintags.py` (`make ingest-ab-tags`, ~21 h) keeps the normalisation tags and provenance tags for each submission (list in the module docstring).
   - Sample check: 1,866 files carry `mp3gain_undo`. They sit at a replay gain of about 0 dB whatever their step count (`+001` … `+008`), so each file's original level can be recovered: original RG ≈ RG − 1.5 dB × steps.
   - `file_name` is present on every record.
   - Once the stream finishes: correct or flag those files, rebuild `tracks.parquet`, and re-check both the 2014+ lossy gap and the −5.5 dB MP3 hump. The undo-tagged files sit at ~0 dB, not −5.5, so the hump may come from a different tool or target.

## Gain-tag follow-up (2026-11-07)

The re-stream finished: 30/30 parts, 29,460,584 rows (identical to P06), sha256 all OK. The only parse errors are the 31 `COPYING` licence files inside the archives. Every submission joins to its tag row on recording + part + offset + audio md5.

**Gain tags exist in part 0 only.** Part 0 has 2,272 `mp3gain_undo`, 9,792 `mp3gain_minmax` and 200,239 `replaygain_*` tags. Parts 1–29 have none of these, although they still carry 20–30 other tags per file (median). AcousticBrainz must have dropped gain tags from later submissions. So tags can't identify gain-normalised files after the earliest submissions.

**The undo correction doesn't work.** For part-0 MP3s with `mp3gain_undo` and a lossless copy in the same unit, the raw gap grows by about 1.6 LU per step (1 → 8 steps: −6.8 → −17.5 LU). After the 1.5 dB × steps correction, a constant **≈ −5 LU residual** remains at every step count. Files carrying only `mp3gain_minmax` (analysed, with no recorded undo) also read −5.3 LU low. These files were brought to a fixed target as well as shifted, so they are **dropped, not corrected**.

**New exclusions (lossy files only, logged in `p09_excluded.parquet`):**
- `gain_tagged`: any MP3Gain tag. 9,606 submissions.
- `stream_rip`: the file name, encodedby or encoder names Spotify, YouTube, SoundCloud, Audials, Tunebite or Streamripper. 45,315 submissions.
  - Keyword checks against the lossless copy: Spotify −3.3 LU (64% of files more than 2 LU low), SoundCloud −5.7 LU, YouTube −1.8 LU, Audials −1.3 LU.
  - "Tidal", "Pandora", "Deezer" and "stream" are mostly song titles (median about 0 LU), so they aren't used.

Effect on the main table: 9,264,611 units (−5,102); main sample 7,202,054; **headline `in_main_lossless` 2,997,479 (−57)**. Median LUFS moves from −11.792 to −11.789 and median LRA doesn't change.

**The −5.5 dB MP3 hump** is a population of 192 kbps MP3s normalised to about −18 est. LUFS, which is Essentia RG ≈ −5.2 dB and consistent with the standard 89 dB ReplayGain/MP3Gain target. The cluster has a tight spread (SD about 2.3 LU against about 3 LU for the matching lossless copies). It covers 13–14% of 192 kbps MP3s for release years 1980–2009, 24% for 2010–14 and 46% for 2015–19. Without tags it can't be told apart from genuinely quiet masters, and a reference-free detector based on track-to-track spread fails: precision 13–17%, recall 3–24%, and it flags 4–22% of lossless albums. Lossy-only units therefore stay biased quiet, which is why the headline is lossless-only.

**The 2014+ lossy gap is a bitrate-mix effect** (`figures/p09_lossy_gap_by_bitrate.png`). In paired main-sample units:
- lossy copies at 160 kbps or below read **−0.43 to −0.45 LU in every release year from 2008 to 2022**;
- lossy copies above 160 kbps read **−0.02 to −0.05 LU in every year**;
- the low-bitrate share of paired units rises from about 12% (2008) to 50–60% (2018–2021), mostly through 128 kbps MP3 bulk-submitter cohorts (parts 20–27).

The low-bitrate shift grew from about −0.15 LU to −0.44 LU around 2005–07, the loudness-war peak, so it probably tracks how hot the master is. It doesn't change at 2015. So the post-2015 "lossy reads quieter" gap is neither stream normalisation nor a mastering change. It can still bias any all-codec series by a few tenths of an LU.

**For P12/P13/P19:** the headline stays lossless-only. The all-codec dashed line should note this bias. P19 adds a specification that drops units whose lossy copies are ≤ 160 kbps.

## First-appearance flag (added at P12, 2026-11-07)

`dedupe.py` now adds three columns:
- `rec_first_year`: the recording's earliest dated MusicBrainz release, restricted to recordings AcousticBrainz has;
- `first_appearance`: release year ≤ `rec_first_year` + 1; an unknown first year counts as true;
- **`in_headline`** = `in_main_lossless` and `first_appearance`: 2,604,546 units, the headline sample from P12 on.

This drops box sets and best-ofs of old recordings, which the release-group reissue rule misses. The reasons are in `notes/p12_hero.md`.
