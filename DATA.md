# Data

Sources, licences, the files each pipeline step writes, field definitions and every exclusion. The method behind each step is in `notes/pNN_*.md`.

## Sources and licences

| Source | Version | Licence | Used for | Where it goes |
|---|---|---|---|---|
| AcousticBrainz low-level dumps (30 parts, 632 GB `tar.zst`) | final dumps (project closed 2022) | CC0 | replay gain, dynamic complexity, spectral features, file tags | streamed over HTTP, never stored; `data/interim/ab_lowlevel/` |
| AcousticBrainz high-level dumps (30 parts) | same | CC0 | genre classifiers (fallback only) | `data/interim/ab_highlevel/` |
| MusicBrainz full export (`mbdump.tar.bz2`, 35 tables) | dump `20261101-125824`, schema 31 | CC0 (core data) | recordings → releases, dates, release groups, types, tags, redirects | `data/raw/musicbrainz/` → `data/interim/mb/` |
| Normalisation timeline | hand-built, 20 cited events | this repo (CC0) | era shading, break years | `data/reference/normalisation_timeline.csv` |
| Proxy calibration | fitted on the author's audio (P03) | this repo (CC0) | replay gain → est. LUFS, dynamic complexity → est. LRA | `data/reference/proxy_calibration.json` |
| Genre map | hand-built, 2,251 tags → 12 genres | this repo (CC0) | genre per unit | `data/reference/genre_map.csv` |
| Author's own audio | 1,185 AAC tracks (P03), 13 CDs / 149 FLAC tracks (P18) | private, not redistributed | calibration and validation | measurements only, in `data/interim/` |
| Dynamic Range Database (dr.loudness-war.info) | accessed 2026-11-14, 305 search pages, cached | no licence stated | an internal check (P18) | `data/raw/drdb/` (git-ignored); **only aggregate statistics are published, never per-album DR values** |

The AcousticBrainz-era Essentia extractor (`streaming_extractor_music` v2.1-beta2, run under Rosetta) and pyloudnorm 0.2.0 (BS.1770-4, Tech 3342 LRA, checked against the EBU 3341/3342 test signals) are the meters used in P03 and P18.

## Layout

- `data/raw/`: downloads and caches. Git-ignored.
- `data/interim/`: Parquet built from the dumps. Git-ignored and large: the low-level part files hold 29.5 M rows.
- `data/processed/`: analysis tables and model outputs. Git-ignored and rebuilt by `make rebuild`.
- `data/reference/`: hand-built and fitted reference files. Committed.
- `app/data/`, `docs/`: the published app data and site. Committed.

## AcousticBrainz low-level → `data/interim/ab_lowlevel/part=NN.parquet` (P05/P06)

One row per submission (one file analysed): 55 columns, 29,460,584 rows. The schema is `SCHEMA` in `src/lw/build/parse_lowlevel.py`.

- **Keys:** `recording_mbid` and `submission_offset` (from the archive member name), plus `part`. The parts are in submission order.
- **Loudness/dynamics:**
  - `replay_gain` (dB; more negative = louder);
  - `dynamic_complexity` (dB);
  - `average_loudness` (0–1);
  - `spectral_rms_{mean,median,max,var}`;
  - `silence_rate_{20,30,60}db`.

  **There is no EBU R128 field in AcousticBrainz** (`notes/p01_access_check.md`), and no sample or true peak.
- **Spectral/rhythm:** centroid, flux, complexity, energy, 4 energy bands, Bark flatness, BPM, onset rate. Scalars are the Essentia `mean` statistic.
- **File:** `codec`, `lossless`, `bit_rate` (0 for lossless), `sample_rate`, `length_s`, `md5_encoded`, and the Essentia/extractor versions.
- **Tags** (`tag_*`, first value only, max 500 chars): release, release-group, track and recording MBIDs, date, originaldate, album, artist, label, barcode, catalogue number, release type/status/country, media, genre, ISRC.
- **Per-part logs:**
  - `part=NN.errors.jsonl` holds records that failed to parse: one non-JSON `COPYING` member per part, and no real failures.
  - `part=NN.done.json` holds rows, errors, bytes, the sha256 check and seconds. All 30 parts match the published sha256.
- **Related tables:**
  - `data/interim/ab_highlevel/` (P06): the rosamerica, dortmund and tzanetakis genre classifiers, keyed like the low-level table.
  - `data/interim/ab_gaintags/` (P09): ReplayGain/MP3Gain tags, encoder and file names, used to exclude gain-altered and stream-ripped lossy files.

## MusicBrainz → `data/interim/mb/*.parquet` (P07)

| table | rows | contents |
|---|---|---|
| `recording` | 40.8 M | recording MBID, name, artist credit, length |
| `recording_release` | 58.8 M | recording ↔ release, medium/track position, format |
| `release` | 5.9 M | date (with precision: year / month / day), country, status, packaging, label, catalogue no., barcode, formats, release group |
| `release_group` | 4.6 M | name, artist credit, primary/secondary types, first release date |
| `rg_tags` | 5.0 M | release-group tags with vote counts, and whether each is a MB genre |
| `mbid_redirect` | 5.5 M | merged MBIDs → current MBID (10.3% of AB recordings resolve only this way) |

## The analysis table: `data/processed/tracks.parquet` (P08–P10)

One row per **unit** = (MusicBrainz recording, release): 9,264,611 units. Key fields:

| field | definition |
|---|---|
| `recording_mbid`, `release_mbid`, `release_group_mbid` | MusicBrainz IDs (redirects resolved) |
| `match_tier` | **A**: the file's release tag names a release containing the recording; **B**: the date and album tags match one of its releases; **C**: fallback to the recording's earliest release (excluded from the main samples) |
| `year` | release year of the matched release |
| `rg_first_year`, `rec_first_year` | first release year of the release group / earliest dated release of the recording |
| `is_reissue` | release year > release group's first year + 1, **or** a reissue keyword (remaster, anniversary, reissue, legacy edition, expanded), **or** the reissue format rule. `is_deluxe` (deluxe / special edition / bonus tracks) is **not** a reissue. |
| `is_compilation`, `is_live`, `is_soundtrack`, `is_remix`, `is_djmix` | MusicBrainz secondary types |
| `n_sub`, `n_lossless`, `n_low_bitrate` | submissions behind the unit |
| `lufs`, `lra` | **est. LUFS / est. LRA**: medians over the unit's lossless submissions if it has any, else its lossy ones (`loudness_source`). est. LUFS = −23.44 − 1.042 × replay_gain; est. LRA = −0.24 + 1.775 × dynamic_complexity (P03; per-track CV RMSE 1.34 LU / 2.93 LU). |
| `lufs_all`, `lufs_lossless`, `lufs_lossy` (and `lra_*`) | the same over all / lossless-only / lossy-only submissions |
| `lufs_iqr`, `lufs_range` (and `lra_*`) | spread across the unit's submissions |
| `inconsistent` | 2+ submissions with LUFS IQR > 1.5 LU or LRA IQR > 3 LU |
| `bit_rate_lossy`, `low_bitrate`, `all_lossless` | codec flags. Lossless = FLAC / ALAC / PCM (WAV, AIFF) / APE / WavPack. |
| other audio features | medians over all submissions; P17 recomputes them from lossless submissions only |
| `genre`, `genre_source`, `genre_share` | one of 12 genres (rock, metal, pop, hip_hop, electronic, jazz, classical, folk_country, rnb_soul (R&B / soul / blues), punk, reggae, other), from release-group → release → recording → artist tags (`genre_source` rg / release / recording / artist), else the AcousticBrainz rosamerica classifier (`hl`, flagged; 33% agreement) |

### Samples (boolean columns)

| flag | definition | units |
|---|---|---|
| `in_core` | release year 1980–2022 | 8,788,511 |
| `in_main` | core, tier A/B, not a reissue | 7,202,054 |
| `in_main_lossless` | main, with at least one lossless submission | 2,997,479 |
| `first_appearance` | release year ≤ the recording's earliest dated MusicBrainz release year + 1 (drops box sets and best-ofs of old recordings) | |
| **`in_headline`** | `in_main_lossless` and `first_appearance`: **the sample behind every headline result** | **2,604,546** |

### Exclusions (per submission, first matching rule; `data/processed/tracks_funnel.json`)

| reason | submissions |
|---|---|
| exact repeats in the dump (one copy kept) | 2,590 |
| no MusicBrainz release found (`unmatched`) | 65,697 |
| shorter than 30 s | 235,350 |
| est. LUFS > 0 | 4,286 |
| est. LUFS < −60 | 126 |
| invalid LRA (dynamic complexity ≤ 0 or est. LRA > 50) | 10,541 |
| lossy file with an MP3Gain tag (`gain_tagged`) | 9,606 |
| lossy file named or tagged as a stream rip (`stream_rip`) | 45,315 |
| **kept** | **29,087,073 of 29,460,584** |

Every excluded submission is logged with its reason in `data/interim/p09_excluded.parquet`.

## Model and report outputs (`data/processed/`)

| prompt | files |
|---|---|
| P11 | `p11_profile.json`, `p11_spotcheck.csv` |
| P12 | `p12_yearly.parquet`: per sample × metric × year: n, release groups, median, P10, P90, release-group bootstrap CI |
| P13 | `p13_its.parquet`, `p13_scan.parquet`, `p13_year_fe.parquet`, `p13_its_summary.json` |
| P14 | `p14_quantile.parquet`, `p14_yearly_quantiles.parquet`, `p14_hinge_profile.parquet`, `p14_summary.json` |
| P15 | `p15_cells.parquet`, `p15_genre_effects.parquet`, `p15_summary.json` (posterior draws in `data/interim/p15/`) |
| P16 | `p16_pairs.parquet`, `p16_album_pairs.parquet`, `p16_by_year.parquet`, `p16_famous.parquet`, `p16_summary.json` |
| P17 | `p17_descriptors.parquet`, `p17_yearly.parquet`, `p17_genre_change.parquet`, `p17_density.parquet`, `p17_composition.parquet`, `p17_summary.json` |
| P18 | `p18_summary.json`, `p18_own_tracks.parquet`, `p18_encoding.parquet`, `p18_drdb_bins.parquet` (aggregates only) |
| P19 | `p19_specs.parquet`, `p19_yearly.parquet`, `p19_summary.json` |
| P21 | `article_numbers.json`: every number the article quotes |
| P10 | `genre_mix.parquet` (AcousticBrainz vs MusicBrainz genre mix and reweighting factors), `genre_summary.json` |

## App data: `app/data/` (P22, committed)

- **`albums.parquet`:** one row per original album (release group) in the headline sample with ≥ 3 measured tracks, 181,582 rows. An album is its most-submitted edition.
  - `mbid`, `title`, `artist`, `type`, `year`, `genre`;
  - `n_tracks`, `n_sub`;
  - `lufs`, `lra` (album median of est. LUFS / est. LRA), `lufs_min`, `lufs_max`;
  - `pct_lufs`, `pct_lufs_genre`, `pct_lra`, `pct_lra_genre`: mid-rank percentile among albums from release year ± 2, overall and within the genre;
  - `title_key`, `artist_key`: normalised search keys.
- **`dist.json`:** histograms of album medians per year and per (year, genre), and the P12 hero series.

## Reproducing what can't be re-downloaded

- **P03 calibration and P18 validation** need the author's own audio. `make calibrate` reads `~/Music/...`, and `make validate` reads `RIPS=~/Music/Lossless`. Their committed outputs are `data/reference/proxy_calibration.json` and the P18 summary numbers pinned in `tests/test_p18_validation.py`.
- Without that audio, `make analysis` stops at `validate`. Everything before it runs from the public dumps.
- **The DR Database check** fetches one search page per album, 3 s apart, and caches them. Its pages are not redistributed.
