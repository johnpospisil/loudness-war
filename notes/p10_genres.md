# P10: Genre assignment

Run 2026-11-07 with `make genres` (about 1.5 min). The code is `src/lw/build/genres.py`, the map is `data/reference/genre_map.csv`, and the figures are `src/lw/viz/p10.py`.

## Outputs

- **`tracks.parquet`** gains these columns:
  - `genre`: one of 12 top-level genres;
  - `genre_source`: `rg` / `release` / `recording` / `artist` / `hl`;
  - `genre_share`: the winning genre's share of mapped votes;
  - `genre_rg` and `genre_artist`, kept for comparison;
  - `genre_hl` (the classifier used) and `genre_hl_{rosamerica,dortmund,tzanetakis}`.

  The step is idempotent, but **`make dedupe` rewrites `tracks.parquet` without these columns**, so `make build` runs `genres` after `dedupe`.
- **`data/processed/genre_mix.parquet`** has, per release year × genre:
  - MusicBrainz release-group counts and shares;
  - AcousticBrainz main-sample shares per unit, per release group, and for the lossless sample;
  - `weight` and `weight_lossless` (MB share ÷ AB share): **the P19 reweighting targets.**
- **`data/processed/genre_summary.json`**: coverage, genre shares and fallback agreement. Pinned in `tests/test_genres.py`.

## The 12 genres

Rock · metal · pop · hip-hop · electronic · jazz · classical · folk/country · R&B/soul/blues · punk · reggae/ska · other.

- **Blues** goes in R&B/soul (relabelled "R&B / soul / blues"), except blues rock, which goes to rock.
- **"Other"** holds soundtracks and scores, video-game music, Latin and world styles, comedy and spoken word, Christmas, experimental, noise and new age.

## The tag map

`map_tag()` maps all **2,220 MusicBrainz official genres plus 31 frequent non-genre tags** whose meaning is clear: `soundtrack`, `vgm`, `hip-hop`, `rap`, `pop/rock`, `indie`, `alternative` and so on. Other non-genre tags (`offizielle charts`, `english`, `male vocalist` …) are ignored. Rules are applied in this order:

1. **207 exact overrides**, written while reviewing the 420 heaviest tags. They resolve word collisions: `dub techno`, `hardcore hip hop`, `happy hardcore`, `new jack swing`, `indie pop`, `synth-pop`, `garage rock` vs `uk garage`, `baroque pop`, `rock opera` …
2. **Ordered regex rules, most specific genre first:** metal → punk → hip-hop → reggae → jazz → classical → folk/country → R&B/soul → electronic → rock → pop → other. So `pop punk` → punk, `rap metal` → metal, `country rock` → folk/country.
3. **Anything else → `other` (rule `default`).** That is 1,035 rare tags, which together carry **0.28% of tag weight** after the review.

`instrumental` and `a cappella` are not genres. They map to `ignore` and add no votes.

**Check against MusicBrainz's own hierarchy.** The `subgenre` links (`l_genre_genre`, fetched at P10) give 1,594 tags with a parent. The map agrees with a parent's genre for **94.9% of tag weight** (70% of tags unweighted; rare tags are where it disagrees). After the review, the heavy disagreements I followed MusicBrainz on were folk rock, dream pop, power pop, jangle pop and noise pop, all now rock.

Kept on purpose:
- jazz rock and nu jazz → jazz (MusicBrainz: rock / electronic);
- coldwave → electronic (MB: post-punk);
- glam metal → metal (MB: hard rock);
- classical crossover → classical (MB: pop).

Each row of the CSV records the rule that fired, the MB parents and the tag's weight in the main sample.

## Assignment

For each entity, every mapped tag adds its positive vote count to its genre, and the genre with the most votes wins. Ties go to the more specific genre, in the order metal, punk, hip-hop, reggae, electronic, jazz, classical, folk/country, R&B/soul, rock, pop, other. This is because a generic tag (rock, pop) usually sits beside a specific one. The median winning share at release-group level is **0.86**.

A unit takes its genre from the first source that has a mapped tag:

| source | share of main sample (7.20M units) |
|---|---|
| release-group tags | **79.8%** |
| release tags | 1.3% |
| recording tags | 3.6% |
| artist tags (release group's credited artists, votes summed) | **9.7%** |
| AcousticBrainz classifier (flagged) | 5.6% |
| none | 0.02% |

**Artist tags are an addition to the brief's plan**, which used release-group tags with the classifier as the only fallback. They needed the `artist_credit_name` table, which was fetched at P10 with `python -m lw.ingest.musicbrainz_dump --only …`. That is a partial stream of the core archive that stops once the tables are found, so it can't check the archive's sha256; bz2's CRC on every block still guards the data. Where both exist, the artist genre agrees with the release-group genre **68%** of the time, against 33% for the best classifier.

**The AcousticBrainz classifiers are weak.** Agreement with the release-group genre on the 5.7M main-sample units that have both:

- **rosamerica 33%** (39% on the 8 classes it can name). It's the best of the three, with 82% recall on classical and 0% on metal, punk, folk and reggae, which it can't name.
- dortmund 28%: it calls 95% of electronic correctly but labels most other music electronic too.
- tzanetakis 6%: it calls almost everything jazz.
- For comparison, always guessing the largest genre (rock) scores 24%.

Rosamerica is the fallback, but **`genre_source = 'hl'` units should be left out of the genre model (P15)**, or at least checked with and without them. Their genre is barely better than a guess.

## Genre mix: AcousticBrainz vs MusicBrainz (`figures/p10_genre_mix_ab_vs_mb.png`)

The MusicBrainz reference covers **3,271,754 Album/EP/Single release groups** with a first-release year from 1980 to 2022. 2,239,442 of them (68%) get a genre: 42% from their own tags, 26% via artist tags. Untagged release groups are left out, and tagged ones lean towards popular, well-catalogued releases, so the reference is "MusicBrainz's tagged catalogue", not all music released.

| genre | MB release groups | AB units (main) | AB release groups | AB lossless units |
|---|---|---|---|---|
| electronic | 25.5% | 22.1% | 25.6% | 20.0% |
| rock | 19.0% | **24.1%** | 21.2% | 23.5% |
| other | 10.6% | 7.2% | 6.4% | 7.4% |
| pop | 9.2% | 7.3% | 9.6% | 7.0% |
| hip-hop | 7.0% | 4.9% | 5.2% | 4.4% |
| metal | 7.0% | 6.2% | 6.0% | 5.8% |
| jazz | 5.0% | 6.4% | 6.4% | 6.0% |
| classical | 4.7% | **8.4%** | 5.2% | **14.7%** |
| folk/country | 4.3% | 4.5% | 3.9% | 3.5% |
| punk | 3.5% | 2.7% | 2.7% | 2.1% |
| R&B/soul/blues | 2.9% | 4.9% | 6.6% | 4.5% |
| reggae/ska | 1.2% | 1.3% | 1.2% | 1.1% |

(Shares are pooled over 1980–2022.)

- **Overall the mixes are close.** The brief expected the contributor bias to favour rock, metal and electronic. In fact rock and classical are over-represented, and metal and electronic are at or below their MusicBrainz share.
- **Rock** is over-represented mostly before 1995: 34% of AB units in 1980–94, against 26% in MB.
- **Classical** units are over-represented partly because classical releases have many tracks; at release-group level the gap shrinks to 5.2% vs 4.7%. Classical collectors also favour lossless, so classical is **15% of the headline lossless sample**.
- **Hip-hop is the gap that matters for the break test.** In MusicBrainz its share climbs to 11.1% for 2015–2022 and about 15% by 2022, while AcousticBrainz stays at about 6.6%. Hip-hop is a loud genre, so any post-2015 genre-mix effect in the headline series runs *against* finding a drop. P19's reweighting will show by how much.
- **The implied weights** (MB share ÷ AB share per year × genre) run 0.37–4.3 for the main sample and 0.19–6.7 for the lossless sample. That is workable, but the lossless extremes (punk and folk before 1990, hip-hop after 2015) will widen the CIs in P19.
- **Units vs release groups.** The reference counts release groups, while AcousticBrainz counts tracks. The P19 weights make the *track* mix match the MusicBrainz *release* mix, which is the defensible target ("the average release"). Write that down when P19 is presented.

## Figures

- `figures/p10_genre_mix_ab_vs_mb.png`: genre share by year in 12 panels, MB vs AB main vs AB lossless, 3-year moving average.
- `figures/p10_genre_coverage.png`: genre source by year, and how often each fallback agrees with the release-group genre.

## For later prompts

- **P15:** genre model on tag-sourced genres. Exclude `genre_source = 'hl'`, or run it as a sensitivity check. Report `genre_share` as the label-uncertainty measure; could down-weight units with share < 0.5.
- **P19:** reweight with `genre_mix.parquet` (`weight` for `in_main`, `weight_lossless` for `in_main_lossless`).
- **P22 (app):** the genre distribution per year uses the same `genre` column.
