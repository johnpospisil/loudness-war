# P08 — Release matching and reissue flag

_2026-11-05. Code: `src/lw/build/release_match.py`. Figure: `src/lw/viz/p08.py`. Run with `make match` (about 15 min; DuckDB spills up to ~76 GB to `data/interim/duckdb_tmp` and deletes it afterwards). Output: `data/interim/ab_matched.parquet`, 8.1 GB with one row per submission (every low-level column plus the match columns), and `ab_matched_summary.json`. Tests: `tests/test_release_match.py`, with 18 hand-verified cases plus pinned totals._

## Tiers (29,460,584 submissions)
| Tier | Rule | Submissions | Share |
|---|---|---|---|
| A | The file's release-MBID tag (redirect resolved) is a release containing this recording (redirect resolved) | 21,498,798 | 73.0% |
| B | The file's date-tag year and normalised album title match one of the recording's releases. Ties go to an exact full-date match, then the earliest date, then status. | 3,784,549 | 12.8% |
| C | The recording's earliest release. Dated releases come first; ties and undated releases go by status: Official, then none, then Promotion, with Bootleg and Pseudo-Release last. | 4,111,532 | 14.0% |
| none | The recording isn't in MusicBrainz (47,165) or is on no release | 65,705 | 0.2% |

- **Redirects:** 3.30M submissions (11.2%) resolve only through a recording redirect.
- **Release tags:** 75.5% of submissions carry one; 0.2% of tags point to a release that no longer exists.
- **Tag year:** for tier A, the date-tag year agrees with the MusicBrainz release year in 82.5% of submissions.
- **Tier A over time:** A rises from about 50% of submissions in 1980 to 75–78% in 1990–2019, then falls to 54% in 2020–22, when 39% match by tier B. Recent files are often not tagged with Picard.
- **The analysis year** is `year`: the matched release's year, or the date-tag year when that release is undated (`year_source = 'tag'`, 573k rows). It is null for unmatched rows. 94.9% of matched submissions fall in 1980–2022.
- **2022 is thin:** matched submissions per year fall from 979k (2019) to 672k (2020), 334k (2021) and 25k (2022). P12 must show n per year and treat 2022 with care.

## Reissue flags (shares of matched submissions)
| Flag | Rule | Share |
|---|---|---|
| `reissue_date` | Release year > the group's first year + 1. The group's first year is the earlier of MusicBrainz's derived value and the group's own earliest release (P07). | 10.2% |
| `reissue_keyword` | Title or disambiguation contains *remaster, anniversary, reissue, legacy edition, expanded* | 1.4% (adds 0.4 pt beyond the date rule) |
| `reissue_format` | CD for a group first released before 1982, or Digital Media before 2000 | 5.7% (adds 0.6 pt) |
| **`is_reissue`** | Any of the three | **11.2%** |
| `is_deluxe` | *deluxe, special or collector's edition, bonus tracks*. Informational, **not** a reissue flag. | 2.5% |
| `is_compilation` / `is_live` / `is_remix` | Release-group secondary types | 23.2% / 4.9% / 1.1% |

**A change made during P08.** The first full run also counted "deluxe", "special edition" and "bonus tracks" as reissue keywords. These added 2.4 pt of reissues on top of the date rule, peaking in 2010–2015, just before the 2015 break. On inspection, 86% of "deluxe" hits share the album's first year: they are editions released alongside the standard one, with the same master (The 1975, *Born Sinner*, *X*…). "legacy" also matched *TRON: Legacy*. Treating these as reissues would have dropped real new releases from P12's main sample in exactly the pre-break years. They now go into `is_deluxe`, and "legacy" matches only "legacy edition". The keywords that remain are mostly misdated reissues: 96% of "anniversary" hits carry the original year, as with the Nevermind 30th Anniversary edition dated 1991.

**Where reissues come from:** 51–55% of submissions from groups first released in the 1950s, 60s or 70s are reissues, against 32% for the 1980s, 11% for the 1990s and about 6% for 2000 onwards. Most reissues are on CD (2.63M) or Digital Media (0.90M). By release year, the reissue share peaks at 26% in 1987, the early CD back-catalogue era.

## Wrong-edition check
For tier A, `len_diff_s` is the file length minus the MusicBrainz track length on the tagged release. Where it is more than 5 s, `len_best_s` looks for the closest length on any release of the same recording. **0.7% of matched submissions are `wrong_edition_suspect`**: more than 5 s off the tagged release, while another release fits within 2 s. For example, a Ramones file tagged *All The Stuff (And More) – Vol. 1* carries the *Ramones* release ID and is 7.2 s off, while another release fits within 0.0 s. 1.1% of tier A rows can't be checked because MusicBrainz has no track length for them. The barcode is not used as evidence (P02).

## Hand-verified cases (`tests/test_release_match.py`)
Seven come from the user's own AccurateRip-verified, Picard-tagged CD rips, so the edition is certain:
- Abbey Road (1992 CD), Cannonball & Coltrane (1991) and A Love Supreme (2001) are reissues by date.
- Becoming X (US 1997 release of a 1996 album) is **not** a reissue under the +1 year rule.
- Further Down the Spiral (UK) is a remix and not a reissue.
- Odelay with no release tag, and Odelay with a wrong one, both match by tier B to the 1996-06-18 release.
- Psalm 69: the tagged release is undated in MusicBrainz, so the year comes from the tag. With no tags at all, tier C picks the Official release, not the bootleg.

From the dump:
- The Abbey Road 2009 remaster and the 2021 digital Nevermind fire the date, keyword and format rules.
- The Nevermind 30th Anniversary Super Deluxe is dated 1991, and only the keyword rule catches it.
- Death Magnetic "limited edition" is not a reissue.
- The 1975 deluxe edition gets `is_deluxe` but is not a reissue.
- *TRON: Legacy* does not trip the keyword rule.
- The Beatles' "1" is a compilation.
- An unknown recording is unmatched and gets no year.

## For later prompts
- **P09:** dedupe per (recording, release) on `recording_mbid_mb` + `release_mbid`, not on the AcousticBrainz MBID, because redirects merge some of them. 3,755 repeated submission keys from P06 are still in the table.
- **P12 main sample:** tiers A and B, `not is_reissue`, and `year` between 1980 and 2022. Robustness checks (P19): tier A only, dropping `wrong_edition_suspect`, dropping `is_deluxe`, and dropping compilations and live releases.
