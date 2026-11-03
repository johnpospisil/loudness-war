# Data

| Source | Licence | Used for | Location |
|---|---|---|---|
| AcousticBrainz low-level and high-level dumps | CC0 | Loudness (EBU R128), LRA, dynamic complexity, spectral features, file tags | acousticbrainz.org/download → streamed, `data/interim/` |
| MusicBrainz JSON dumps | CC0 (core data) | Recordings → releases, dates, release groups, genre tags | `data/interim/` |
| Normalisation timeline | hand-built, cited | Era shading, break years | `data/reference/normalisation_timeline.csv` |
| Own measurements | private | Validation | not redistributed |

## AcousticBrainz low-level → `data/interim/ab_lowlevel/part=NN.parquet` (P05)

One row per submission (file analysed), 55 columns; the schema is `SCHEMA` in `src/lw/build/parse_lowlevel.py`.

- **Keys:** `recording_mbid` and `submission_offset` (from the archive member name), plus `part`.
- **Loudness/dynamics:** `replay_gain` (dB; more negative = louder), `dynamic_complexity` (dB), `average_loudness` (0–1), `spectral_rms_{mean,median,max,var}`, `silence_rate_{20,30,60}db`. **There is no EBU R128 field in AcousticBrainz** (see `notes/p01_access_check.md`).
- **Spectral/rhythm:** centroid, flux, complexity, energy, 4 energy bands, bark flatness, BPM, onset rate. Scalars are the Essentia `mean` statistic.
- **File:** `codec`, `lossless`, `bit_rate` (0 for lossless), `sample_rate`, `length_s`, `md5_encoded`, Essentia/extractor versions.
- **Tags** (`tag_*`, first value only, max 500 chars): release/release-group/track/recording MBIDs, date, originaldate, album, artist, label, barcode, catalog number, release type/status/country, media, genre, ISRC.
- Each part also writes `part=NN.errors.jsonl` (records that failed to parse) and `part=NN.done.json` (rows, errors, bytes, sha256 check, seconds).

