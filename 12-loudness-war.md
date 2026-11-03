# Project 12: Is the Loudness War Over?

**Backlog ID:** AU-1 · **Difficulty:** Medium · **Data access:** Open (CC0) · **Estimated time:** 6 weeks

**Working title:** *Turned Down for What: Loudness and Dynamic Range in Recorded Music Before and After Streaming Normalisation*

**One-sentence pitch:** Use AcousticBrainz's millions of loudness measurements, linked to MusicBrainz release dates, to measure whether masters got quieter and more dynamic after streaming services started normalising playback loudness, by genre and by original vs remastered releases.

---

## 0. Day-one access check
- [ ] Download the AcousticBrainz final data dumps (acousticbrainz.org/download). Check whether the smaller CSV feature dumps released at shutdown include `loudness_ebu128` integrated loudness and loudness range; the full low-level JSON dumps are very large.
- [ ] Download the MusicBrainz database dump (or use the MusicBrainz API with rate limits) and join one recording MBID to its releases and release dates.
- [ ] Run `pyloudnorm` on a few of your own audio files to confirm you can reproduce EBU R128 integrated loudness and LRA values.

## 1. The question

**Primary:** Did integrated loudness (LUFS) fall and loudness range (LRA) rise for new releases after streaming normalisation became the default (roughly 2015–2017)?

**Secondary:**
- **Genre:** which genres de-escalated (if any) and which stayed loud (EDM, metal, hip-hop)?
- **Remasters:** are remasters of old albums louder than their original releases, and has that gap shrunk?
- **Other descriptors:** dynamic complexity, crest factor proxies, spectral flatness. Is music denser even if it isn't louder?
- **The floor:** did the *loudest* masters (top decile) come down, or only the median?

**A finding that would be wrong if:** loudness and LRA show no break after 2015 compared with their 2000–2014 trend, in most genres.

## 2. Why now
- Spotify, YouTube, Apple Music, Tidal and others normalise playback loudness (typically around −14 to −16 LUFS), which removes the competitive advantage of a louder master. Engineers have argued for a decade about whether this ended the "loudness war". **Verify each service's normalisation default and date before publishing.**
- The AES published streaming loudness recommendations (TD1004, 2015).
- Most claims rely on a few famous albums. A measurement over millions of tracks is new and charts well.
- It fits your audio and DSP background, so you can speak with authority about the measurements.

## 3. Data sources

| Source | What it gives you | Grain | Where |
|---|---|---|---|
| **AcousticBrainz dumps** | Essentia low-level features per submission: EBU R128 integrated loudness, loudness range, momentary/short-term loudness, average loudness, dynamic complexity, spectral features; file metadata tags (album, date, release MBID) | submission (one file analysed), ~2008–2022 | acousticbrainz.org/download (CC0; project closed 2022) |
| **MusicBrainz** | Recordings, releases, release dates, release groups (original vs reissue), labels, artist countries | recording / release | musicbrainz.org database dumps (CC0 core data) |
| **AcousticBrainz high-level** | Predicted genre, mood (as a supplement to MusicBrainz genre tags) | submission | same dumps |
| **MusicBrainz genre tags** | Community genre tags | release group | MusicBrainz |
| **Normalisation timeline** | Service, default target LUFS, date enabled by default | event | Hand-built (cited) |
| **Your own measurements** | `pyloudnorm` on a set of CDs you own (original vs remaster) as a ground-truth check | track | Local |

**Expected size:** the full low-level dumps are very large (hundreds of GB of JSON). Stream-parse and keep only ~20 fields. The CSV feature dumps, if they include loudness, are much smaller.

## 4. Building the dataset

1. **Parse** AcousticBrainz submissions → Parquet (recording MBID, submission ID, loudness fields, codec/bitrate/sample rate, file tags).
2. **Identify the release:** use the release MBID tag from the file where present (it identifies the *specific* release, e.g. a 2011 remaster); fall back to the earliest release date of the recording.
3. **Release dates and type:** release date, release group first-release date, `is_reissue` flag (release date later than the group's first release).
4. **Deduplicate:** many submissions per recording, so take the median per (recording, release).
5. **Codec effects:** lossy files (MP3 at low bitrates) can change measured peaks, so flag codec and bitrate and check sensitivity.
6. **Checks:** spot-check 50 well-known albums against published measurements (e.g. the Dynamic Range Database, where terms allow use for comparison); your own CD measurements.

## 5. Method

### Headline trend
- **Interrupted time series** of median integrated loudness and LRA by release year (1980–2022), with a break around 2015 and alternative break years (2013–2017).
- **Quantile trends:** 10th, 50th and 90th percentiles. Did the loudest masters change?

### Genre heterogeneity
- Hierarchical model with genre-specific trends and breaks, partially pooled.

### Remasters
- Paired comparison: same recording, original release vs later reissue. Difference in LUFS by reissue year.

### Robustness
- Restrict to lossless files; restrict to releases with an explicit release MBID tag.
- AcousticBrainz contributors are not a random sample of listeners (skews to rock, metal, electronic, and to collectors). Reweight by genre distribution to a reference (e.g. MusicBrainz release counts).
- Coverage stops in 2022: say so and suggest a follow-up with your own measurements.

### What you won't claim
That normalisation *caused* any change. Taste, mastering tools and engineer advocacy all changed at the same time. Present the timing and the genre pattern.

## 6. Charts

| # | Chart | Purpose |
|---|---|---|
| **Hero** | **Median integrated loudness (LUFS) by release year, 1980–2022**, with 10th–90th percentile band and the normalisation era shaded | The headline |
| 2 | Same for loudness range (LRA) | Dynamics, not just level |
| 3 | Small multiples by genre | Who de-escalated |
| 4 | Dumbbell: original vs remaster loudness for famous albums | Shareable |
| 5 | Ridgeline: LUFS distributions by decade | Shape of the distribution |
| 6 | Validation: AcousticBrainz vs your own measurements | Trust |

**Interactive:** "How loud is my album?" Search an album and see its measured loudness against its year and genre.

## 7. Repo skeleton

```
loudness-war/
  README.md, DATA.md, Makefile, pyproject.toml, uv.lock
  src/lw/
    ingest/acousticbrainz_dump.py, musicbrainz_dump.py
    build/parse_lowlevel.py, release_match.py, dedupe.py, genres.py
    measure/pyloudnorm_check.py
    models/its.py, quantile_trends.py, genre_hier.py, remaster_pairs.py
    viz/theme.py, figures.py
  data/reference/normalisation_timeline.csv (cited)
  tests/          # parser fixtures, release-matching cases, pinned medians
  report/index.qmd
  app/
```

## 8. Milestones

| Week | Deliverable |
|---|---|
| 1 | Dumps downloaded; streaming parser; field selection |
| 2 | MusicBrainz joins; release matching; dedupe |
| 3 | Trend + ITS; hero chart v1 |
| 4 | Genre models; remaster pairs |
| 5 | Validation with your own measurements; robustness |
| 6 | Article + album lookup; publish |

## 9. Distribution
- Audio communities love this topic: r/audioengineering, Gearspace, r/audiophile, r/WeAreTheMusicMakers, Sound On Sound, mastering engineers on YouTube.
- Hacker News and r/dataisbeautiful for the hero chart.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Release identification (remaster vs original) | Use file release MBID tags; reissue flags; sensitivity |
| Contributor bias | Genre reweighting; state the limitation |
| Data ends in 2022 | Frame as 1980–2022; propose your own measurement follow-up |
| Lossy codecs affect measurements | Restrict to lossless in robustness checks |

## 11. Stretch goals
- Measure 2023–2026 releases yourself on a sample (from audio you own or have licensed access to).
- Spectral balance trends (has music become brighter or bassier?).
- A JUCE plugin or web tool that shows where a user's master sits in the historical distribution.
