# P18 — Own-measurement validation

_2026-11-14. Code: `lw.measure.own_rips`, `lw.ingest.drdb`, `lw.models.validation`, `lw.viz.p18`. Rebuild with `make validate` (`RIPS=~/Music/Lossless`). Outputs: `data/processed/p18_summary.json`, `p18_own_tracks.parquet`, `p18_encoding.parquet`, `p18_drdb_bins.parquet` (aggregates only); per-album DR values stay in git-ignored `data/interim/p18/drdb_albums.parquet`._

## Inputs
- **Own CD rips:** 13 CDs, **149 tracks**, all FLAC and AccurateRip-verified, ripped with dBpoweramp:
  - Abbey Road twice: the 1987 EMI CD (MB release dated 1992) and the 2019 Giles Martin remix, disc 1.
  - Odelay, Cannonball & Coltrane, A Love Supreme, Psalm 69, Further Down the Spiral, Becoming X, Bartók (Rahbari), Shostakovich quartets (Eder), Art Angels, Happier Than Ever, BRAT.
  - BRAT is missing tracks 9 and 13 because the disc is damaged.
- **MusicBrainz resolution:**
  - Nine albums carry MB IDs in their tags.
  - Four were tagged from another source. Their releases were found by barcode (UPC, ties broken by catalogue number and track count) or, for Abbey Road 2019, by catalogue number B0030718-02. Their recordings were found by disc and track position.
  - In 135/149 tracks the file's ISRC is attached to the same recording in MB. Ministry's 2001-registered ISRCs belong to other recordings, and the Eder disc has no ISRCs.
- **Meters:**
  - pyloudnorm (the reference);
  - ffmpeg `ebur128`, which agrees with pyloudnorm to a median of 0.04 LU (LUFS) and 0.03 LU (LRA);
  - the AcousticBrainz-era Essentia extractor (P03), whose output goes through the P03 calibration to give est. LUFS and est. LRA.

## Results

### 1. The proxy on lossless CD audio (out of sample; P03 was fitted on AAC)
| | bias (est − measured) | 95% CI (album bootstrap) | SD | 95% limits | RMSE | P03 CV RMSE |
|---|---|---|---|---|---|---|
| est. LUFS, per track | −0.04 LU | [−0.35, +0.34] | 1.15 | −2.31 / +2.22 | 1.15 | 1.34 |
| est. LRA, per track | +0.27 LU | [−0.80, +1.23] | 3.94 | −7.46 / +8.00 | 3.94 | 2.93 |
| est. LUFS, album median (13) | −0.03 LU | [−0.48, +0.38] | 0.82 | | | |

- **LUFS** holds up, and does slightly better than in P03.
- **LRA** is worse than in P03. The two string-quartet / orchestral discs (measured LRA 16–20 LU) are under-predicted by 2.6–4.6 LU (album medians), which is the spread compression P03 reported. Est. LRA ranks albums correctly but compresses the wide-dynamic end.
- **Per-album LUFS bias** runs from −0.7 LU (BRAT) to +1.3 LU (Shostakovich). Hot modern masters read slightly louder than estimated, and quiet classical slightly quieter.

### 2. AcousticBrainz copies vs own measurement
- **Coverage:** 127/149 tracks (11 albums) have AcousticBrainz submissions of the same recording MBID. Bartók and BRAT have none.
- **Same audio, same extractor:** when an AcousticBrainz copy has replay gain within 0.5 dB of our run (98 tracks), the two Essentia runs agree to **0.00 ± 0.08 dB**. The ingest, parse and match chain reproduces the extractor exactly.
- **End to end on the same audio:** AcousticBrainz est. LUFS − own pyloudnorm LUFS = **+0.04 LU** [−0.39, +0.54], SD 1.23, limits −2.37 / +2.46. That is just the proxy error. For LRA: +0.13 LU, SD 2.75.
- **Analysis units in the headline sample** (`in_headline`, the (recording, release) the hero chart uses): 60 own tracks from 5 albums. Unit est. LUFS − own LUFS = **+0.25 LU** [−0.29, +0.88], SD 1.26. 98% of these units carry the same audio as the own rip.
- **Other audio behind the same IDs:** 29 tracks match AcousticBrainz copies that carry different audio. Remasters share recording MBIDs, and tags don't always name the master.
  - Among lossless AcousticBrainz submissions tagged with the **same release** as the own CD, 4.2% are other audio. Almost all are A Love Supreme (9 of 12 are a remaster 3–4 dB louder).
  - Within the **same release group**, 31% are other audio, driven by Abbey Road: 65% of lossless submissions under the album's release group are the louder 2009 remaster. P08's reissue flag catches these only when the file's release tag names the remaster.
  - Five Art Angels tracks have only single 256 kbps AAC copies, 4–9 dB quieter than the CD. They are level-normalised or from another digital master.
  - **None of these mismatched units is in the headline sample.** The headline needs a lossless copy and the first appearance of the recording.

### 3. Lossy encoding (26 tracks, 2 per CD, × 6 encodings)
| encoding | Δ LUFS | Δ LRA | Δ est. LUFS | Δ est. LRA |
|---|---|---|---|---|
| MP3 128k CBR (LAME) | **−0.42** (SD 0.03) | +0.01 | −0.44 | −0.03 |
| MP3 192k CBR | **−0.26** (SD 0.01) | +0.00 | −0.27 | −0.03 |
| MP3 320k CBR | 0.00 | 0.00 | 0.00 | −0.03 |
| MP3 V2 (~190k VBR) | 0.00 | 0.00 | 0.00 | −0.03 |
| AAC 128k (Apple) | −0.05 | −0.02 | −0.06 | −0.05 |
| AAC 256k (Apple) | −0.02 | −0.01 | −0.05 | −0.06 |

- **CBR MP3 at ≤192 kbps lowers the level of the whole signal, by about the same amount on every track.**
  - The lowpass doesn't explain it: low-passing the source at 16–20 kHz changes LUFS by ≤ 0.001 LU.
  - Unweighted RMS drops by the same amount, so it isn't a frequency-weighting effect. The likely cause is the encoder discarding masked components.
  - This **reproduces P09's finding** that ≤160 kbps lossy copies read −0.44 LU in every year. That bitrate-mix gap is an encoding artefact, not mastering. It confirms the decisions to keep a lossless-first headline and to exclude ≤160 kbps copies from the dashed comparison line.
- **LRA and est. LRA are unaffected** by any encoding (|Δ| ≤ 0.06 LU).
- **Sample peaks rise** by 0.2–0.9 dB, the usual lossy overshoot. Irrelevant here, because AcousticBrainz has no peak.

### 4. Dynamic Range Database (internal check; aggregates only)
- **Targets:**
  - 305 albums: the 6 best-covered original albums per year from 1980–2022, the 54 P11 spot-check albums and the 12 own-rip album groups.
  - One artist+album search page each, sent 3 s apart and cached. The site has no robots.txt (404).
- **Matching rules:** lossless CD entries whose title matches (packaging suffixes allowed, remaster labels not) and whose year is within ±1 of the album's first release.
  - **139 albums** matched (1981–2022, 350 DR entries).
  - Misses are mostly classical (composer; performer credits don't match DR's artist names) and pre-CD albums.
- **Correlations** (bootstrap 95% CIs):
  | Our measure vs album DR | overall | within release year |
  |---|---|---|
  | est. LUFS | Spearman **ρ = −0.90** [−0.93, −0.86], ≈ −0.9 DR per LU | **r = −0.72** [−0.80, −0.59] |
  | est. LRA | ρ = +0.13 [−0.03, +0.29] | r = +0.53 [0.38, 0.66] |
  | dynamic complexity | ρ = +0.13 | r = +0.52 |

  DR is a peak-to-RMS (crest) measure, so it tracks loudness closely. LRA measures macro-dynamics, which is a different property, and relates to DR only within a year.
- **P11's Wikipedia 'criticised loud' albums** (9 matched) have a median DR of 5, against 9.25 for the other albums. 6 of the 9 sit below the median DR of albums from within ±2 years.
- Per-album DR values are not published (the site states no licence). Citation: Dynamic Range Database, https://dr.loudness-war.info, accessed 2026-11-14.

## What this means for later prompts
- **The per-track proxy error carries over:** ±2.3 LU (LUFS) and ±7–8 LU (LRA) at 95%. It averages out in yearly medians. Bias is ≈ 0 for LUFS on lossless CD audio, with album-level offsets of ±1 LU by style. Quote est. LRA trends as direction and relative size (as in P03), never as absolute LRA for wide-dynamic music.
- **Master identity is the main risk for track-level claims**, not the meter. P16 (remaster pairs) and the P22 app should say that a release's AcousticBrainz copies can include other masters. P19 should add the spec "drop units whose submissions disagree by > 1 dB replay gain", using `lufs_iqr` or `inconsistent`.
- **The DR check supports the headline measure's ranking of albums** (ρ −0.90 overall, −0.72 within a year). P20 grades this as **moderate**, internal-only evidence: 139 albums, user-submitted DR values, best-covered albums only.

## Limitations
- 13 CDs from one collection. The genre mix follows the owner's taste, and 2 CDs (Bartók, BRAT) have no AcousticBrainz match.
- Own measurements are pyloudnorm on 16-bit CD audio. They don't cover hi-res or vinyl sources.
- The DR Database is self-selected and skews towards rock/metal and audiophile releases. Year ±1 matching can still admit a same-year remaster.
- MP3 encoding used one encoder (LAME via ffmpeg). The AcousticBrainz MP3s come from many encoders.
