# P03 — Calibrating the AcousticBrainz loudness proxies

_2026-11-04. Outputs: `data/reference/proxy_calibration.json`, `figures/p03_*.png`, raw measurements in `data/interim/p03_calibration/`. Rebuild with `make calibrate`._

## Why
AcousticBrainz has no EBU R128 fields (P01). We estimate integrated loudness from `audio_properties.replay_gain` and loudness range from `lowlevel.dynamic_complexity`. P03 measures how well those proxies track real R128 values.

## Method
1. **Meter conformance.** pyloudnorm 0.2.0 and ffmpeg `ebur128` were run on generated EBU Tech 3341 (cases 1–5) and Tech 3342 (cases 1–4) signals. Both pass all 9 cases. pyloudnorm reads 0.02–0.06 LU low on 3341 (tolerance ±0.1) and exact on 3342.
2. **Same audio through both pipelines.** The AcousticBrainz-era extractor (Essentia `streaming_extractor_music` v2.1_beta2, `music 1.0` profile, under Rosetta) and pyloudnorm were run on the same files:
   - 72 synthetic pink-noise programmes of controlled loudness and dynamics;
   - a sample of the author's library, up to 4 tracks per album, seed 0.

   On real music, pyloudnorm and ffmpeg agree to a median of 0.04 LU for LUFS (P99 0.09) and 0.03 LU for LRA.
3. **Fit.** OLS, with 10-fold cross-validation that holds out whole albums and cluster-robust SEs by album. The fit uses **real tracks only**. Pink noise is shown for reference but left out: it sits outside the music domain, with a bias of +1.6 LU for LUFS and +2.5 LU for LRA.

## Calibration set
- **1,185 tracks, 322 albums, 134 artists.**
- 1,184 tracks are AAC and 1 is PCM.
- Measured LUFS: median −12.4, P10–P90 −19.5 to −8.2.
- Measured LRA: median 6.8 LU.

## Results (headline models)
| Target | Model | CV RMSE | 95% PI (per track) | R² | Spearman | Max bias by predicted quintile |
|---|---|---|---|---|---|---|
| LUFS | −23.44 − 1.042 × replay_gain | **1.34 LU** | −2.6 / +2.5 | 0.929 | 0.947 | 0.15 LU |
| LRA | −0.24 + 1.775 × dynamic_complexity | **2.93 LU** | −5.3 / +5.8 | 0.672 | 0.797 | 0.40 LU |

Adding dynamic complexity and average loudness lowers the LUFS CV RMSE only from 1.34 to 1.24 LU. For LRA, adding average loudness and replay gain lowers it from 2.93 to 2.51 LU. All variants are kept in the JSON for robustness checks (P19). The headline stays with the single-proxy models because they are transparent and their error is close to the multi-term fits.

The replay_gain slope (−1.04) is close to −1, so the proxy is essentially an offset: a track with replay_gain 0 dB measures about −23.4 LUFS. We fit that intercept rather than assume a nominal ReplayGain reference level.

## Caveats for later prompts
- **Per-track vs per-year error.** A single track's estimate is good to about ±2.6 LU (LUFS) and about ±5.5 LU (LRA). Yearly medians average the random part away, but not any bias that changes by genre, era or codec. P18 and P19 check that.
- **LRA spread is compressed.** Predicted LRA has an SD of 4.2 LU against 5.1 LU measured. Year-to-year differences in *estimated* LRA are therefore probably attenuated, by roughly 15–20%. Report LRA trends as direction and relative size, and quote dynamic complexity directly as well.
- **The loudest tracks are under-predicted.** Among the loudest decile of measured tracks, the median residual is +1.0 LU. Part of this is regression to the mean (residuals plotted against the measured value always slope). Binned by *predicted* value, the bias is ≤0.15 LU, and that is what applies when we take medians of predictions.
- **The calibration set is lossy and comes from one library.** AcousticBrainz submissions are a mix of MP3, FLAC and other formats. P18 measures how much encoding shifts the meters. Genre and era mix follow the author's taste, not AcousticBrainz's.
- **Exclusions (from the 2026-11-04 memory-guard fix):**
  - 9 genuine tracks over 20 minutes were skipped (long jazz and classical, e.g. *Bitches Brew*, Beethoven 9 iv).
  - 6 truncated 64 KB files were skipped.
  - Audiobook, podcast and eBook folders are never sampled.

  As a result, very long, wide-dynamic pieces are slightly under-represented at the top of the LRA range.

## Incident: 2026-11-04 machine freeze
The first `library` run decoded three audiobooks whole (1.2–11 h each) in 5 parallel workers, about 64 GB on a 16 GB machine. The compressor hit its segment limit and the Mac had to be force-restarted (`panic: btn_rst`). Fix in `pyloudnorm_check.py`:
- ffprobe pre-check, skipping files over 20 minutes or over a 3 GB decode budget (measured peak about 28 B per sample per channel);
- audiobook and podcast folders excluded;
- the number of workers capped by physical RAM (3 here).

Tests cover each guard.
