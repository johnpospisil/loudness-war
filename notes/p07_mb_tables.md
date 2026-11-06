# P07 — MusicBrainz tables

_2026-11-05. Code: `src/lw/build/mb_tables.py` (`make ingest-mb`, about 1 min). Source: full export `20261101-125824`, schema 31 (P02). Output: `data/interim/mb/*.parquet`, 4.4 GB, plus `build.json` with row counts. Tests: `tests/test_mb_tables.py`._

The tables cover **all of MusicBrainz**. Restricting them to AcousticBrainz recordings is P08's job.

| Table | Rows | Contents |
|---|---|---|
| `recording` | 40,791,784 | recording MBID, name, artist credit, length, comment, video flag |
| `recording_release` | 58,760,222 | one row per track: recording MBID, release MBID, medium and track position, track number, track length, medium format, data-track flag |
| `release` | 5,897,156 | release date (earliest event) and its precision, country of that event, number of countries and events, status, packaging, first named label and catalogue number, label count, barcode, comment, formats (in medium order), media and track counts, release-group MBID |
| `release_group` | 4,615,620 | `first_release_date` and precision, primary type, secondary types, flags `is_compilation`, `is_live`, `is_remix`, `is_soundtrack`, `is_djmix`, `is_mixtape`, `is_demo`, `is_spokenword`, `is_audiobook`, release count |
| `rg_tags` | 5,037,558 | release-group MBID, tag, vote count, `is_genre` (the tag is one of MB's 2,220 official genres) |
| `mbid_redirect` | 5,545,207 | old → new MBID for merged recordings (5.12M), releases (192k) and release groups (235k) |

## Rules
- **Partial dates.** MusicBrainz stores year, month and day separately, and any of them can be missing. Each table keeps the parts, a `*_date` string at the available precision (`YYYY`, `YYYY-MM` or `YYYY-MM-DD`, which also sorts correctly as text), and `*_date_precision` (`year`, `month` or `day`). If a month has no year, or a day has no month, the orphan part is dropped. Tests cover YYYY, YYYY-MM, a day with no month, and missing years.
- **Release date = the earliest release event**, taken from `release_country` and `release_unknown_country` together. Events sort by year, then month, then day, with missing parts last. Within the same year, the more precise event wins, so a release with both "1991" and "1991-09-24" gets 1991-09-24. When events tie, the country is chosen deterministically.
- **Label:** the first *named* label by `release_label` id, with the catalogue number chosen the same way.

## What the data looks like
- **Release date precision:** 65.4% day, 3.2% month, 26.1% year, 5.3% undated. Release groups: 67.3% day, 3.2% month, 25.1% year, 4.4% undated.
- **Some years are junk:** 1,271 release years fall before 1900 and 367 after 2026, the largest being 3036. The 1980–2022 sample window removes them.
- **The derived group date is slightly stale.** `release_group_meta.first_release_date` matches the group's own earliest release year in 4.41M of 4.61M groups. For 34 groups it is later than one of the group's releases (for example *Death of a Country* says 2011 but has a 1971 release). For 336 groups it is missing even though a release is dated. **P08 should use the earlier of the group date and the group's own earliest release date.**
- **Release status:** 90.7% Official, 2.0% Promotion, 1.7% Bootleg, 4.8% missing.
- **Release-group types:** Album 2.35M, Single 1.47M, EP 0.60M. Compilation 500k, Live 159k, Remix 80k, Soundtrack 97k.
- **Missing release fields:** label 21%, barcode 53%, country of the earliest event 11.5%. 3.2% of releases have no event at all.
- **First format:** Digital Media 2.92M, CD 1.87M, 12" vinyl 0.41M, unknown 0.24M.
- **Tags:** 92% of the release-group tag links are MB genres. 61,701 links have a vote count of zero or less (down-votes), and **P10 should drop them.** The most-voted genres are electronic, rock, pop, jazz, experimental and hip hop.
- **Track lengths:** missing on 9.5% of `recording_release` rows. P08's wrong-edition check can only run where a length exists.

## AcousticBrainz coverage (full dump, 7,564,215 recordings)
- **89.5% resolve directly, 10.3% only through a recording redirect, and 0.25% (about 18.7k) are missing.** The P02 sample estimated 91.3%, 8.6% and 0.1%. Later parts carry more merged MBIDs, so **resolving redirects is mandatory** in P08.

## Hand check
"Smells Like Teen Spirit" (`5fb524f1…`) sits in the *Nevermind* group, an Album with no secondary types, first released 1991-09-24 and with 100 releases. Its 1991 releases include GB vinyl, Saudi Arabian cassette and two European CD pressings, and the CD comments record their pressing details. The comment field will help P08's keyword flag for reissues.
