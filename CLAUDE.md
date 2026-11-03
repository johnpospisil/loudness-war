# CLAUDE.md — Is the Loudness War Over? (AU-1)

Project brief: [12-loudness-war.md](12-loudness-war.md). Read it before any prompt.

## Progress

- ✅ DONE! P00: Repo scaffold
- ✅ DONE! P01: AcousticBrainz access probe
- ⬜ P02: MusicBrainz access probe ← next

## How we work

- Run the prompts below **in order**, one per session turn. The user types `Run P07` (or similar).
- Work as an expert data scientist: state assumptions, check the data before modelling, and report uncertainty (CIs, sensitivity). Never claim causation (brief §5, "What you won't claim").
- **After every prompt:** (1) list every figure created, with its path, and show it (Read the PNG); (2) give 3–5 bullet findings or numbers; (3) ask any questions that came up; (4) tick the prompt below as `- [x] ✅ DONE! **Pxx: …** _Done YYYY-MM-DD: one-line result._` and add "✅ DONE" to a phase heading once all its prompts are done. Also update the **Progress** list at the top: add a `✅ DONE! Pxx` line and move the `← next` marker.
- Figures: `figures/pNN_<name>.png` (static, 200 dpi) and, for the hero and interactive charts, `.html` as well. Every figure uses `src/lw/viz/theme.py`. Each figure must work as a standalone image: title, units (LUFS, LU), n, and source line ("Data: AcousticBrainz + MusicBrainz, CC0").
- Data layout: `data/raw/` (downloads, git-ignored), `data/interim/` (Parquet), `data/processed/` (analysis tables), `data/reference/` (hand-built, committed). Big dumps are **streamed and parsed on the fly, never stored whole** (240 GB free disk).
- Stack: Python 3.12 via `uv`, polars + DuckDB for data, pyarrow Parquet, statsmodels / PyMC for models, matplotlib (static) + Plotly or Observable (interactive), Quarto for the report, pytest for tests.
- Every pipeline step is a `make` target and is idempotent. Pin key numbers (row counts, medians) in tests once they are known.
- Commit after each prompt with message `Pxx: <summary>`.

## Decisions (defaults; update if the user changes them)

- **Metrics (changed at P01, 2026-11-02):** AcousticBrainz has **no `loudness_ebu128`** (every record comes from the Essentia `music 1.0` extractor). Headline loudness = **calibrated loudness (≈ LUFS) from `audio_properties.replay_gain`**; dynamics = **`lowlevel.dynamic_complexity`** (LRA analogue), plus `average_loudness`. P03 calibrates both against pyloudnorm LUFS/LRA. Charts label the measure "estimated LUFS" and give the calibration error. See `notes/p01_access_check.md`.
- Core sample: release years 1980–2022, tracks with valid `replay_gain` and `dynamic_complexity`. The 100k sample dump ends in 2014 and is used **only** for fixtures and tests.
- Dump parts 0–29 are in submission order (part 0 ≤ 2014; later parts reach 2022), so all 30 parts are needed.
- Headline break year: 2015, with 2013–2017 as alternatives.
- "Lossless" = FLAC/ALAC/WAV/AIFF; lossy is flagged and dropped in robustness checks.
- Genre: MusicBrainz release-group tags mapped to ~12 top-level genres; AcousticBrainz high-level genre used only as a fallback, and flagged.
- Ingest scale: **stream the full low-level dumps** (user decision, 2026-11-02).
- Own audio: **some rips, mostly lossy** (user decision, 2026-11-02). P18 treats them as secondary evidence, and the R128 test signals plus published measurements serve as the main check. Ask the user for the folder path at P03.
- App: **static site on GitHub Pages** (user decision, 2026-11-02).
- Genre model: **Bayesian, PyMC** (user decision, 2026-11-02).

---

## Phase 0 — Setup and day-one access check

- [x] ✅ DONE! **P00: Repo scaffold.** _Done 2026-11-02: git repo, uv env (Py 3.12, PyMC installed), Makefile, theme.py with validated palette + save_fig, 3 tests pass, ruff clean._ `git init`; create the skeleton from brief §7 (`src/lw/...`, `tests/`, `report/`, `app/`, `data/`, `figures/`, `notes/`); `pyproject.toml` with uv, ruff, pytest; `.gitignore` for `data/raw`, `data/interim`; Makefile with stub targets; `src/lw/viz/theme.py` (one palette, fonts, a `save_fig()` helper that writes the source line); README and DATA.md stubs. Verify with `uv run pytest` (one smoke test) and `make help`. *Figures: `figures/p00_theme_preview.png` (swatch and sample line chart).*

- [x] ✅ DONE! **P01: AcousticBrainz access probe.** _Done 2026-11-02: no EBU R128 in any record (114k surveyed); replay_gain and dynamic_complexity are 100% present and show the war; full dump is 30 parts, 632 GB, ~29 h at 6 MB/s; sample ends in 2014._ List every file on acousticbrainz.org/download with its size: low-level JSON dumps, high-level dumps, CSV feature dumps, sample dumps. Download the **sample** low-level dump and the CSV feature dump headers. Confirm, quoting field paths, whether `lowlevel.loudness_ebu128.integrated`, `.loudness_range`, `.momentary`, `.short_term`, `average_loudness`, `dynamic_complexity`, `spectral_flatness_db`, codec, bitrate, sample rate, `metadata.tags` (release MBID, date) exist in each format. Estimate the total download size and parse time for the full dump. Write `notes/p01_access_check.md` with a recommendation (CSV-only, or streamed full JSON). *Figures: none (table in the notes).*

- [ ] **P02: MusicBrainz access probe.** Compare the options: the JSON dumps (`release`, `release-group`, `recording`), the Postgres dump (needs a local Postgres), and the API (rate-limited). Default to the JSON dumps. Download them and confirm we can get recording MBID → releases → release date, release-group first-release date, primary and secondary types (Compilation, Live, Remix…), genre tags, label and country. Hand-check 5 known recordings (e.g. "Smells Like Teen Spirit" original vs 2011 remaster). Write `notes/p02_mb_access.md`. *Figures: none.*

- [ ] **P03: Reproduce EBU R128 with pyloudnorm and calibrate the AcousticBrainz proxies.** *(Expanded at P01.)* Run the AcousticBrainz-era Essentia extractor (`data/raw/essentia_extractor/streaming_extractor_music`, needs Rosetta, or the `essentia` pip package with parity checked) and pyloudnorm on the same audio: R128 test signals, synthetic signals of controlled loudness and crest factor, and the user's files. Fit LUFS ~ f(`replay_gain`) and LRA ~ g(`dynamic_complexity`) with prediction intervals; save the result to `data/reference/proxy_calibration.json`. *Original scope:* Write `src/lw/measure/pyloudnorm_check.py`. Validate against EBU Tech 3341/3342 test signals (generate a 1 kHz sine at −23 dBFS, which should read −23 LUFS, plus the LRA test cases), with tolerance tests in pytest. Where Essentia is installable, compare pyloudnorm against Essentia's `LoudnessEBUR128` on the same files, since AcousticBrainz used Essentia, and record any systematic offset. Run it on a few of the user's own files if provided. *Figures: `figures/p03_r128_conformance.png` (expected vs measured on the test signals), `figures/p03_rg_vs_lufs.png`, `figures/p03_dyncomp_vs_lra.png` (calibration fits).*

- [ ] **P04: Normalisation timeline.** Research and build `data/reference/normalisation_timeline.csv` with columns service, platform, default_on_date, target_LUFS, method (track/album), source_url, source_quote, confidence. Cover Spotify, YouTube, Apple Music / iTunes Sound Check, Tidal, Amazon Music, Deezer, Pandora, plus AES TD1004 (2015) and ITU-R BS.1770 / EBU R128 milestones. Flag anything we could not verify. *Figures: `figures/p04_normalisation_timeline.png` (timeline strip; it is also the shaded band reused in later charts).*

## Phase 1 — Build the dataset

- [ ] **P05: Streaming low-level parser.** Write `src/lw/build/parse_lowlevel.py`. It streams `tar.zst` (local file or HTTP), parses each JSON with orjson, keeps ~25 fields (recording MBID, submission offset, Essentia version, replay_gain, dynamic_complexity, average_loudness, spectral_rms, silence rates, band energies, spectral flatness/centroid, codec, bitrate, sample rate, lossless flag, length, tag release MBID, tag date, tag album/artist), and writes Parquet in row-group batches. Make it resumable per archive part, and log malformed records rather than crashing. Build test fixtures from 20 real sample-dump records. Run it on the sample dump and report throughput. *Figures: none.*

- [ ] **P06: Full AcousticBrainz ingest.** Run P05 over every low-level dump part (background job, resumable, checksums verified), plus the high-level genre/mood fields we need. Delete each archive once it is parsed, or stream it so it never touches disk. Report rows, failures, field null rates and wall time. *Figures: `figures/p06_submissions_by_codec.png`, `figures/p06_field_coverage.png` (null rate per field).*

- [ ] **P07: MusicBrainz tables.** Write `src/lw/ingest/musicbrainz_dump.py` to turn the JSON dumps into Parquet tables: `recording_release` (recording MBID, release MBID, medium/track position), `release` (date, precision, country, status, packaging, label, barcode, release group), `release_group` (first_release_date, primary/secondary types), `rg_tags` (tag, count). Add tests for partial dates (YYYY, YYYY-MM). *Figures: none.*

- [ ] **P08: Release matching and reissue flag.** Write `src/lw/build/release_match.py`. Tier A: the file's release MBID tag is a valid release that contains this recording. Tier B: the file's date tag plus album name match one of the recording's releases. Tier C: fall back to the recording's earliest release. Compute `release_year`, `rg_first_year`, `is_reissue` (release year > rg first year + 1), `is_compilation`, `is_live`. Write pytest cases for 10 hand-verified tricky cases (remasters, deluxe editions, compilations). *Figures: `figures/p08_match_tiers.png` (share of tracks by tier and year).*

- [ ] **P09: Dedupe and the analysis table.** Write `src/lw/build/dedupe.py`: take the median per (recording, release), keep the submission count and IQR, and use the IQR to flag inconsistent measurements. Add codec/bitrate flags. Apply exclusions (LUFS > 0 or < −60, duration < 30 s, invalid LRA) and log each one. Output `data/processed/tracks.parquet`. *Figures: `figures/p09_data_funnel.png` (rows surviving each step), `figures/p09_tracks_per_year.png`, `figures/p09_codec_mix_by_year.png`.*

- [ ] **P10: Genre assignment.** Write `src/lw/build/genres.py`: map MusicBrainz tags to ~12 top-level genres (rock, metal, pop, hip-hop, electronic/EDM, jazz, classical, folk/country, R&B/soul, punk, reggae, other) with the map kept in `data/reference/genre_map.csv`; use AcousticBrainz high-level as a fallback. Compare the genre mix in AcousticBrainz against all MusicBrainz releases per year; this comparison gives the reweighting targets for P19. *Figures: `figures/p10_genre_mix_ab_vs_mb.png`, `figures/p10_genre_coverage.png`.*

- [ ] **P11: EDA and sanity checks.** Profile `tracks.parquet`: distributions, outliers, and the correlation between LUFS, LRA, dynamic complexity and average_loudness. Spot-check 50 well-known albums (Death Magnetic, Californication, (What's the Story) Morning Glory?, Random Access Memories, etc.) against published values where their terms allow. Flag anything implausible. Write `notes/p11_eda.md`. *Figures: `figures/p11_ridgeline_lufs_by_decade.png` (brief chart 5), `figures/p11_lufs_vs_lra.png` (hexbin), `figures/p11_spotcheck_albums.png`.*

## Phase 2 — Models and core charts

- [ ] **P12: Hero chart v1 and LRA chart.** Plot median LUFS by release year, 1980–2022, with the P10–P90 band, bootstrap CI on the median, the normalisation era shaded from P04, and n per year shown. Make the same chart for LRA. Use tier A+B matches with no reissues as the main sample, and overlay the all-tracks line as a dashed comparison. *Figures: `figures/p12_hero_lufs.png` + `.html`, `figures/p12_lra.png` + `.html` (brief charts 1–2).*

- [ ] **P13: Interrupted time series.** Write `src/lw/models/its.py`: a segmented regression of the yearly median (and a track-level model with year fixed effects) with level and slope change at 2015, Newey-West SEs, and pre-trend projection. Re-run with break years 2013–2017, placebo breaks (1995–2010), and a data-driven break search (Bai-Perron or a likelihood-profile scan). Answer the brief's falsification test: is there a break vs the 2000–2014 trend? *Figures: `figures/p13_its_fit.png` (observed vs counterfactual), `figures/p13_break_year_sensitivity.png`, `figures/p13_breakpoint_profile.png`.*

- [ ] **P14: Quantile trends.** Write `src/lw/models/quantile_trends.py`: quantile regression (τ = 0.1, 0.5, 0.9) with the same segmented form, with bootstrap CIs. Did the loudest decile come down? *Figures: `figures/p14_quantile_trends.png`, `figures/p14_quantile_slope_change.png` (coefficient plot by τ).*

- [ ] **P15: Genre hierarchical model.** Write `src/lw/models/genre_hier.py`: a partially pooled Bayesian model in PyMC (genre-varying intercept, pre-slope, break level and slope change), fitted on genre-year cells weighted by n. Run diagnostics (R-hat, ESS, posterior predictive checks). Rank genres by post-2015 change. *Figures: `figures/p15_genre_small_multiples.png` (brief chart 3), `figures/p15_genre_break_forest.png`, `figures/p15_ppc.png`.*

- [ ] **P16: Remaster pairs.** Write `src/lw/models/remaster_pairs.py`: pair the same recording's original release with its later reissue(s). Plot ΔLUFS and ΔLRA by reissue year, with a mixed model including a recording random effect. Has the remaster gap shrunk since 2015? Pick ~20 famous albums for the dumbbell chart. *Figures: `figures/p16_remaster_gap_by_year.png`, `figures/p16_dumbbell_famous_albums.png` (brief chart 4).*

- [ ] **P17: Other descriptors.** Trend dynamic complexity, a crest-factor proxy (peak − loudness, if peak is available; otherwise say so), spectral flatness and spectral centroid by year and genre. Is music denser even if it isn't louder? *Figures: `figures/p17_descriptor_trends.png`, `figures/p17_density_vs_loudness.png`.*

## Phase 3 — Validation and robustness

- [ ] **P18: Own-measurement validation.** Run pyloudnorm (plus the P03 Essentia offset) on the user's own lossless rips, matching them to AcousticBrainz by recording MBID (via tags or AcoustID). Report a Bland-Altman analysis and the mean/SD of the difference, split by lossless vs lossy (the user's files are mostly lossy, so also measure how much MP3/AAC encoding shifts LUFS and LRA by re-encoding a few lossless files with ffmpeg). Use the spot-check albums from P11 as the main external check. *Figures: `figures/p18_validation_scatter.png`, `figures/p18_bland_altman.png` (brief chart 6).*

- [ ] **P19: Robustness and specification curve.** Re-estimate the P13 break under: lossless-only, tier A matches only, excluding reissues and compilations, genre-reweighted to the MusicBrainz mix (P10), one submission per recording, excluding high-IQR tracks, and submission-date cohorts (to check for contributor drift). Show all the estimates in one chart. *Figures: `figures/p19_spec_curve.png`, `figures/p19_reweighted_hero.png`.*

- [ ] **P20: Results QA.** Run the `data:validate-data` skill over the whole analysis: methodology, leakage, multiple-comparison risk, and whether each claim follows from its evidence. Write `notes/p20_findings.md` with the final claims, each tagged strong/moderate/weak, and the limitations (coverage ends in 2022, contributor bias, no causal claim). *Figures: none, or fixes to earlier ones.*

## Phase 4 — Publish

- [ ] **P21: Article.** Write `report/index.qmd` (Quarto, HTML): the narrative "Turned Down for What", with the hero chart up front, methods in a collapsible appendix, and every number pulled from `data/processed/` (none hard-coded). Run `quarto render`. *Figures: final versions of the hero chart and charts 2–6 (`figures/final_*.png`).*

- [ ] **P22: "How loud is my album?" app.** Build a static web app in `app/`: search an album or artist and see its LUFS/LRA against its year and genre distribution. It loads a precomputed compact Parquet/JSON via DuckDB-WASM, so it needs no server and deploys to GitHub Pages. Test with Playwright. *Figures: `figures/p22_app_screenshot.png`.*

- [ ] **P23: Reproducibility pass.** `make all` rebuilds everything from raw data; tests pin row counts and headline medians. Finish README.md (findings, how to reproduce) and DATA.md (sources, licences, field definitions, exclusions). Run ruff and pytest until clean. *Figures: none.*

- [ ] **P24: Distribution kit.** Draft posts for r/dataisbeautiful (hero chart, OC rules), r/audioengineering / Gearspace (methods-forward, measurement caveats), Hacker News (title + first comment), and a one-paragraph press note. Draft only; the user posts them. *Figures: social-crop versions of the hero chart (`figures/social_hero_1x1.png`, `_16x9.png`).*

## Stretch

- [ ] **S01: 2023–2026 follow-up.** Measure a sample of recent releases from the user's own or licensed audio with pyloudnorm, calibrated using P03 and P18, and extend the hero chart (marked clearly as a different method).
- [ ] **S02: Spectral balance trends.** Has music become brighter or bassier? Use band energies and centroid by year and genre.
- [ ] **S03: JUCE plugin / web tool.** Show where the user's master sits in the historical distribution, for its year and genre.
