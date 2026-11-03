# P02: MusicBrainz access check (2026-11-02)

## Decision: use the full export, not the JSON dumps or the API

| Option | Size | Verdict |
|---|---|---|
| JSON dumps (`release.tar.xz` 23 GB + `release-group.tar.xz` 1 GB) | 24 GB xz | Nested JSON, slow to decompress, no redirect tables |
| **Full export `mbdump.tar.bz2` (7.2 GB) + `mbdump-derived.tar.bz2` (0.5 GB)** | **7.7 GB bz2** | **Chosen.** Postgres COPY text files read directly with DuckDB; no Postgres server needed. Includes `*_gid_redirect` tables. |
| Web service API | — | 1 req/s; unusable at millions of recordings |

- Export **20261101-125824**, schema sequence **31**, both archives SHA-256 verified.
- `src/lw/ingest/musicbrainz_dump.py` streams each archive and writes only 35 tables (~19 GB of text) to `data/raw/musicbrainz/<dump>/mbdump/`. The archives themselves are never stored.
- Column names come from `CreateTables.sql`. All 35 tables match the column count of their file; a multi-line CHECK constraint bug in `area`/`artist`/`label` was fixed and is covered by `tests/test_musicbrainz_dump.py`.
- Probe DuckDB (`data/interim/mb_probe.duckdb`, 2.7 GB, built in 16 s): 40.8M recordings, 58.8M tracks, 6.5M media, 5.9M releases, 13.8M release-date events, 4.6M release groups, 5.0M release-group tag links, 2,220 genres.

## The join path works

recording MBID → (`recording_gid_redirect`) → `track.recording` → `medium` → `release` (date from `release_country` ∪ `release_unknown_country`; status, barcode) → `release_group` (`release_group_meta.first_release_date_*`, primary type, secondary types such as Compilation and Live) → `release_group_tag` ∩ `genre`.

## Match rates (127k AcousticBrainz submissions: 100k sample + 27k from the heads of full parts 1, 2, 3, 29)

[Figure](../figures/p02_ab_mb_match_rates.png). Values are sample / full-dump heads.

| | Sample | Full-dump heads |
|---|---|---|
| Recording MBID resolves directly | 91.0% | 91.3% |
| … only via redirect (merged since analysis) | 8.9% | 8.6% |
| Recording missing | 0.0% | 0.1% |
| Tagged release MBID resolves | 99.9% | 98.0% |
| Tagged release contains the recording (tier A) | 99.4% | 97.1% |
| Release has a date | 97.9% | 94.8% |
| File `date` tag year = MB release year | 91.4% | 87.5% |
| Release group has ≥1 genre tag | 73.6% | 85.0% |
| Reissue flag (release year > group first year + 1) | 10.4% | 12.1% |
| Compilation release group | 16.2% | 22.4% |

## Hand checks (5 recordings)

| Recording | Main recording MBID | Releases on the album's group | Reissues | Notes |
|---|---|---|---|---|
| Nirvana, "Smells Like Teen Spirit" (Nevermind, 1991) | `5fb524f1…` (99 releases) | 134 | 94 | 1991 CD → 1996, 2011, 2021 reissues on the same recording. **"Nevermind (30th Anniversary Super Deluxe)" and "Nevermind (deluxe edition)" are dated 1991**, so the date-based flag misses them. |
| Pink Floyd, "Time" (Dark Side of the Moon, 1973) | `41959321…` (70), `0e11c0fd…` (68) | 162 | 134 | Two recordings with about 70 releases each (why MB keeps them separate is not checked yet); in the AB probe set, tracks resolve to 1984, 1994 and 2003 releases. |
| Metallica, "The Day That Never Comes" (Death Magnetic, 2008) | `3d8e877d…` | 38 | 8 | One FLAC submission from the 2008 release, a good spot-check album. |
| Red Hot Chili Peppers, "Californication" (1999) | `084a24a9…` | 42 | 11 | AB has 1999 FLAC. |
| Daft Punk, "Get Lucky" (Random Access Memories, 2013) | `833f00e1…` | 24 | 9 | The artist credit includes the featured artists, so name matching needs a prefix match. AB has 2013 FLAC + MP3. |

## Implications for P07/P08

1. **Remasters usually share the original's recording MBID** (MB practice), so the recording identifies the song, and **only the release MBID tag identifies the master**. This confirms the brief's approach: dedupe per (recording, release), with tier A = tagged release.
2. **Always resolve redirects:** about 9% of AB recordings were merged after analysis.
3. **The reissue flag needs more than dates.** Some reissues are dated with the original year (Nevermind 30th Anniversary). Add a title/comment keyword flag (remaster, anniversary, deluxe, expanded, legacy, edition) and the medium format (Digital Media after 2005 for a pre-2000 group, which is likely a reissue), then measure how much each changes the reissue share.
4. **The barcode is not independent confirmation.** Picard writes the tag from the matched MB release (97–98% agree when both exist), so it cannot prove the user's file is that edition. P08's checks for wrong editions should compare `length_s` with the MB track length on the tagged release against other releases of the recording, plus the file's `originaldate` tag.
5. **Compilations are 16–22%** and **live releases** are a smaller group; flag both and exclude them in the P19 sensitivity checks.
6. **Genre coverage** of 74–85% from MB tags; the file `genre` tag (97.5%) and the AB high-level dump are fallbacks (P10).
