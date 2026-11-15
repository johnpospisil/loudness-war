# P22 — "How loud is my album?" app

_2026-11-14. Code: `lw.app.build` (data), `app/` (static page), `lw.app.site` (assembles `docs/`). Rebuild with `make site`._

## What it does
- **Search:** an album or artist, accent- and punctuation-insensitive, with every word required. Up to 200 matches are kept (exact title or artist match first, then most submitted) and **listed in release-year order, oldest first** (user request 2026-11-14).
- **Album page:**
  - median est. LUFS and est. LRA;
  - percentile among albums released within ±2 years, overall and within the album's genre;
  - a meter-style histogram of those albums, switchable between all genres and the album's genre, and between loudness and loudness range;
  - the album as a dot on the hero trend line;
  - a MusicBrainz link.
- **Deep links:** `app/#<release-group MBID>`.
- **Runs in the browser:** DuckDB-WASM 1.29.0 (jsdelivr) loads `data/albums.parquet` (12.4 MB, zstd) once, about 2 s locally. There is no server.

## Data (`app/data/`)
- **One row per original album (release group)** in the headline sample, release years 1980–2022, with at least 3 measured tracks: **181,582 albums**.
- **An album is its most-submitted edition** (ranked by submissions, then units, then the earliest year), so the track list is the familiar one. The first build pooled every edition, which gave "131 tracks" for Californication and let Death Magnetic's deluxe demos pull its median from −3.9 to −7.2.
- **Percentiles compare album medians with album medians**, using the mid-rank among albums from release year ± 2 (and the same genre). Album medians are less spread out than tracks, so comparing them with track percentiles would overstate extremes.
- **`dist.json`** (157 KB) holds per-year and per-(year, genre) histograms of album medians (0.5 LU bins) and the P12 hero series.
- **Spot checks:**

  | album | est. LUFS | percentile | tracks |
  |---|---|---|---|
  | Death Magnetic | −3.9 | 99.8 | 10 |
  | Californication | −4.3 | 99.9 | 15 |
  | Thriller | −10.3 | 91 | 9 |
  | Nevermind | −13.3 | 73 | 12 |
  | Random Access Memories | −11.6 | 36 | 14 |

## Site (`docs/`, for GitHub Pages "deploy from branch: main /docs")
- `index.html`: the article, with its links rewritten to `app/` and `figures/`.
- `app/`: the album lookup.
- `figures/final_*`: the interactive hero and LRA charts, plus the PNGs.
- `.nojekyll`.
- Total 20.8 MB, all static.

## Tests
- **`tests/test_app_data.py`:** unique IDs, the track minimum, percentile ranges, Death Magnetic = 10 tracks above the 99th percentile, and histograms that sum to the album count.
- **`app/tests/smoke.js`** (Playwright, Chromium), 18 checks:
  - the catalogue loads;
  - search finds Californication and finds Björk from "bjork";
  - a no-match search shows a message;
  - the album page shows its value and the verdict text, the histogram with the album's bin highlighted, and the trend dot;
  - the deep-link hash is set and works in a fresh page;
  - the genre and metric toggles work;
  - there's no horizontal scroll at 375 px;
  - the article links to the app and the interactive chart resolve;
  - no console or page errors.

  To run it, serve `docs/` (`python3 -m http.server 8765 -d docs`), then run `node run.js app/tests/smoke.js` from the Playwright skill directory (`SITE_URL`, `HEADLESS=1` and `SHOT` are optional).
- **Screenshots:** `figures/p22_app_screenshot.png` (desktop) and `_mobile.png` (375 px).

## Limits
- Albums with fewer than 3 measured tracks, reissues and remasters are not searchable. The app shows original releases only, as in the article.
- Values are estimates (±1.2 LU per track). A few albums may mix copies of different masters behind shared recording IDs (P18). The page says so under "What these numbers are".
- DuckDB-WASM and the fonts load from CDNs (jsdelivr, Google Fonts).
