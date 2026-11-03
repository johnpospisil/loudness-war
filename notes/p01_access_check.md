# P01: AcousticBrainz access check (2026-11-02)

## Bottom line

1. **AcousticBrainz has no EBU R128 data.** None of the 114,521 records surveyed (the full 100k sample plus ~5k from each of full parts 0, 14 and 29) has `lowlevel.loudness_ebu128`. Every record was analysed by the extractor `music 1.0`, with Essentia `2.1-beta1` in earlier parts and `2.1-beta2` in later ones. The `loudness_ebu128` block only arrived in later Essentia music extractors (the Essentia docs show it from 2.1-beta6-dev builds). **The brief's LUFS and LRA metrics cannot be read directly from the dumps.**
2. **Loudness proxies are present in 100% of records:**
   - `metadata.audio_properties.replay_gain` (dB): Essentia ReplayGain, the gain needed to bring the track to the RG reference level. **More negative = louder master.** Sample: median −9.4 dB, IQR −12.9 to −4.9.
   - `lowlevel.dynamic_complexity` (dB): average absolute deviation from the global loudness level. It is conceptually close to LRA. Sample: median 4.2, IQR 3.1–6.0.
   - `lowlevel.average_loudness` (0–1): a dynamics index, where 1 means little dynamic range. Sample median 0.82.
   - Also present: `spectral_rms`, `silence_rate_{20,30,60}dB`, and band energies and flatness (bark, erb, mel) for density and spectral-balance work.
3. **The proxies already show the loudness war** in the sample ([figure](../figures/p01_sample_proxies_by_year.png)). Median ReplayGain goes from about −5 to −6 dB (1975–1990) to −11 to −12 dB (2008–2014), and dynamic complexity falls from about 6–7 dB (late 1970s) to about 4 dB (2000s).
4. **The sample stops at 2014; the full dump does not.** The parts are ordered by submission date: part 0 has 0% releases from 2015 or later, part 14 has 38% (max year 2019), and part 29 has 11% (max 2022). The sample is the earliest submissions, so **only the full ingest can answer the post-2015 question.**
5. **The CSV feature dumps are not usable.** Only the `rhythm` and `tonal` CSVs are published; the `lowlevel` CSV (average_loudness, dynamic_complexity) the page lists is not on the server, and it would not include ReplayGain anyway.

## Dump inventory (data.metabrainz.org/pub/musicbrainz/acousticbrainz/dumps/)

| Dump | Files | Size (compressed) | Notes |
|---|---|---|---|
| `acousticbrainz-lowlevel-json-20220623` | 30 × `.tar.zst` (parts **0–29**; part 0 is not in the HTML listing but is in `sha256sums` and downloads fine) | **631.8 GB** (part 0 21.4 GB; 1–29 610.4 GB) | ~1M JSON files per part, ~61 kB each uncompressed (~1.8 TB of JSON in total). 29,460,584 submissions. |
| `acousticbrainz-highlevel-json-20220623` | 30 × `.tar.zst` (0–29) | **41.8 GB** | genre/mood classifier outputs (P10 fallback) |
| `acousticbrainz-sample-json-20220623` | lowlevel sample (2.08 GB, checksum verified); highlevel sample in `sha256sums` | 2.08 GB | 100,000 items, earliest submissions only (≤ 2014) |
| `acousticbrainz-lowlevel-features-20220623` | `rhythm`, `tonal` CSVs only | 1.8 GB | no loudness fields |

## Field coverage

| Field | Sample (100k) | Full part 0 / 14 / 29 heads |
|---|---|---|
| `lowlevel.loudness_ebu128.*` | **0%** | **0% / 0% / 0%** |
| `audio_properties.replay_gain` | 100% | 100% |
| `lowlevel.dynamic_complexity`, `average_loudness`, `spectral_rms`, `spectral_centroid`, `barkbands_flatness_db`, `silence_rate_60dB` | 100% | 100% |
| `audio_properties.codec`, `lossless`, `bit_rate`, `analysis_sample_rate`, `length` | 100% | 100% |
| `tags.musicbrainz_albumid` (release MBID → tier-A matching) | 100% | 100% / 87% / 90% |
| `tags.date` | 98.4% | 98.4% / 98.4% / 97.3% |
| `tags.originaldate` | 60.7% | — |
| `tags.musicbrainz_releasegroupid` | 74.4% | — |
| `tags.label`, `tags.barcode` | 64% / 52% | — |

Codec mix (sample): FLAC 77.4%, MP3 19.1%, Vorbis 2.7%, AAC 0.7%, ALAC < 0.1%. Lossless share is high, which helps the lossless-only robustness check. `bit_rate` is 0 for lossless files.

## Throughput and time estimates

- **Download:** 6.0 MB/s single stream (sample, 349 s for 2.08 GB). Full low-level dump ≈ 632 GB → **~29 h single-stream**; 2–3 parallel streams may cut this to ~10–15 h if the server allows (test in P06). High-level adds ~2 h.
- **Parse:** 2,860–2,940 records/s per Python process (json + tarfile + zstd stream). That is ~3 h single-core for 29.5M records, so the job is **download-bound**. orjson in P05 should be faster still.
- **Disk:** streaming means nothing is stored except Parquet output: ~20 columns × 29.5M rows ≈ 2–4 GB. Peak transient use stays under 25 GB if one part is buffered locally for checksum verification.

## Recommendation

- **Ingest the full low-level dump (all 30 parts) by streaming it**, as decided, plus the high-level dump for genre fallback.
- **Change the headline metrics:**
  - Loudness: **calibrated loudness ≈ LUFS**, mapped from `replay_gain`.
  - Dynamics: **dynamic complexity** as the LRA analogue, with `average_loudness` as a second dynamics measure.
  - Calibrate both against pyloudnorm LUFS and LRA in P03. Run the same Essentia extractor that AcousticBrainz used (static macOS binary `essentia-extractor-v2.1_beta2-2-gbb40004-osx`, SHA-1 verified) and pyloudnorm on the same test signals and real audio, then fit LUFS ~ f(replay_gain) and LRA ~ g(dynamic_complexity) with prediction intervals.
- The binary is x86_64; this Mac is arm64 and **Rosetta 2 is not installed**. Options: install Rosetta (`softwareupdate --install-rosetta`, needs admin), or use the `essentia` pip package (newer version; algorithm parity must be checked).
- **Release year:** use the file's `date` tag only as a fallback; MusicBrainz release dates from the tagged release MBID (P08) are primary.
- **Do not use the 100k sample for any trend estimate** (it ends in 2014). Use it only for parser fixtures and testing.
