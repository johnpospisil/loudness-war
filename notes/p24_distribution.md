# P24 — Distribution kit (drafts)

_2026-11-15. Drafts only; John posts them. Every number comes from
`data/processed/article_numbers.json` and the wording follows `notes/p20_findings.md`
(say "flat", never "slightly quieter"; say "before", never "because of"; no causal claim)._

Links:
- Article: https://johnpospisil.github.io/loudness-war/
- App ("How loud is my album?"): https://johnpospisil.github.io/loudness-war/app/
- Code: https://github.com/johnpospisil/loudness-war

Images:
- `figures/social_hero_1x1.png` (1080 × 1080): Reddit, Instagram, Mastodon
- `figures/social_hero_16x9.png` (1920 × 1080): link previews, X/Bluesky, slides
- `figures/final_hero_lufs.png`: full chart with n per year, for the methods-forward posts

**Check each venue's current rules before posting.** For example, r/dataisbeautiful requires
`[OC]` in the title and a comment from the author naming the data source and tools.

---

## 1. r/dataisbeautiful

**Image:** `social_hero_1x1.png`

**Title:**
> [OC] The loudness war ended around 2008, before streaming services started turning loud songs down: median loudness of 2.6 million tracks, 1980–2022

**Top comment (post within minutes):**

> **Source:** [AcousticBrainz](https://acousticbrainz.org) (29.5 million audio analyses submitted by
> volunteers, CC0), matched to release dates via [MusicBrainz](https://musicbrainz.org) (CC0).
> After de-duplication and filtering: 2,604,546 tracks, each counted on its original release
> (no reissues or remasters), with at least one lossless copy analysed.
>
> **Tools:** Python (polars, DuckDB, statsmodels, PyMC), matplotlib. Code and full write-up:
> https://johnpospisil.github.io/loudness-war/
>
> **What it shows:** median loudness rose about 5 LU from the mid-1980s (≈ −16 LUFS) to a peak in
> 2009 (−10.4), then went flat. Spotify, YouTube, Apple Music and Tidal switched loudness
> normalisation on by default between Dec 2015 and Nov 2017 (shaded). There's no drop after
> that: 2016–22 averages −10.8 vs −10.7 for 2005–09. Statistically, any post-2015 step
> larger than ~0.2 LU would have shown up.
>
> **Caveats:**
> - AcousticBrainz has no true LUFS measurement, so loudness is estimated from its replay-gain value,
>   calibrated against direct measurement (±1.3 LU per track, unbiased on CD audio). Medians
>   of thousands of tracks per year are much tighter (95% CI ≈ ±0.2 LU).
> - The sample is whatever people ripped and submitted, not all music. Reweighting to the
>   MusicBrainz genre mix shifts the level, not the shape.
> - Data stop in 2022 (AcousticBrainz closed). The chart shows timing, not cause.
>
> There's also a lookup tool where you can see how loud any album is versus its year:
> https://johnpospisil.github.io/loudness-war/app/

---

## 2. r/audioengineering and Gearspace (Mastering forum)

Methods first: this audience will ask about the measure before the result.

**Image:** `final_hero_lufs.png` (full chart, with the n-per-year panel)

**Title:**
> Did streaming normalisation end the loudness war? 2.6M tracks say the plateau came first (~2008)

**Body:**

> I spent a few months on the AcousticBrainz dump (29.5M Essentia analyses, 1980–2022) to test the
> common claim that loudness normalisation on Spotify/YouTube/Apple Music ended the loudness war.
>
> **Short answer:** median loudness of new releases rose about 5 LU from the mid-80s and stopped
> rising around 2007–09, 6–10 years before normalisation became the default. There's no further step
> down after 2015–16: the post-2015 change is −0.08 ± 0.08 LU against the trend once the
> late-2000s bend is modelled. That rules out a step larger than ~0.2 LU.
>
> **How it was measured (the part you'll want to poke at):**
> - **No R128 in AcousticBrainz.** Every record is from the Essentia `music 1.0` extractor, which
>   gives replay gain but not integrated loudness. I calibrated replay gain against
>   pyloudnorm/ffmpeg R128 (both pass EBU Tech 3341/3342). Checked out of sample on 149 lossless CD
>   tracks from 13 albums: bias −0.04 LU, RMSE 1.15 LU. The LRA estimate (from dynamic
>   complexity) is much weaker (±4 LU per track), so I only use it for direction.
> - **Codec matters.** Low-bitrate CBR MP3 (≤192k) reads 0.26–0.42 LU quieter than the same
>   lossless audio. Its share grew after 2014 and faked a post-streaming "decline" in the raw
>   data, so the headline uses tracks with a lossless source.
> - **Originals only.** Reissues and remasters are excluded via MusicBrainz release dates and
>   keywords, and so are box sets and best-ofs of older recordings. Otherwise a 2011 remaster
>   of a 1985 album counts as 2011.
> - **Robustness.** 19 sample/weighting choices × 3 trend models × 2 break years. Against a
>   straight 2000–15 trend, 2016–22 always looks ~0.6 LU low. But that trend over-projects
>   past the 2008 plateau; with the bend, every lossless variant is ≈ 0.
>
> **Other results:**
> - **The loudest 10% never came down.** P90 is ≈ −7.4 est. LUFS every year 2003–21.
> - **Remasters run louder than the original CD master.** Median +1.1 LU per track; 1980s
>   CD masters +2–3 LU. The gap peaked for 2005–09 remasters and has eased a little since,
>   with no step at 2016.
> - **Since 2009, spectra got flatter and darker** at fixed loudness and genre, while dynamic
>   measures stayed put. Denser in timbre, not in dynamics. This is one descriptor, so treat it
>   as moderate evidence.
>
> **Limits:**
> - The sample is volunteer submissions: whatever people ripped, skewed to rock and classical.
> - The data end in 2022.
> - It shows timing only. It can't say *why* mastering levels stopped rising.
>
> Write-up: https://johnpospisil.github.io/loudness-war/ · code:
> https://github.com/johnpospisil/loudness-war · album lookup:
> https://johnpospisil.github.io/loudness-war/app/
>
> Happy to dig into specific albums or methods questions.

---

## 3. Hacker News

**Title (Show HN, since there's a tool):**
> Show HN: Is the loudness war over? 2.6M tracks from AcousticBrainz, 1980–2022

**URL:** https://johnpospisil.github.io/loudness-war/

**First comment (author):**

> I wanted to test the common story that streaming loudness normalisation (Spotify, YouTube, Apple
> Music, Tidal; default-on between Dec 2015 and Nov 2017) ended the loudness war.
>
> The answer from the data: median loudness of new releases rose ~5 LU from the mid-80s, then
> **plateaued around 2007–09, before normalisation**, and hasn't moved since. There's no step
> down after 2015 that's larger than ~0.2 LU.
>
> Data: the AcousticBrainz dump (29.5M volunteer-submitted audio analyses, CC0), matched to
> MusicBrainz release dates.
>
> A few things that were harder than expected:
> - AcousticBrainz has no LUFS, only replay gain from an older Essentia extractor. I calibrated it
>   against pyloudnorm on my own CD rips (bias −0.04 LU, RMSE 1.15 LU per track).
> - Low-bitrate MP3 copies read ~0.4 LU quiet. Their share rose after 2014, which produced a fake
>   "post-streaming decline" until I switched to lossless-first.
> - Reissues and box sets of old recordings carry new dates, so a 2011 remaster lands in 2011
>   unless you filter on the recording's first release.
> - A straight-line pre-trend makes the post-2015 years look 0.6 LU "too quiet". That's an artefact
>   of fitting a line through a curve that already bent in 2008. I show both forms (spec curve
>   in the article).
>
> Stack: polars + DuckDB over Parquet, statsmodels and PyMC, Quarto for the article. The album
> lookup is a static page running DuckDB-WASM over a 181k-album Parquet file on GitHub Pages
> (no server). Code: https://github.com/johnpospisil/loudness-war

---

## 4. Press note (one paragraph)

> **The loudness war ended in a stalemate before streaming stepped in, a 2.6-million-track analysis finds.**
> A new open-data analysis by John Pospisil of 2.6 million tracks released between 1980 and 2022
> finds that the "loudness war" did not end when streaming services began turning loud songs
> down. The median loudness of new releases rose by about 5 loudness units (LU) from the
> mid-1980s and stopped rising around 2007–09. Spotify, YouTube, Apple Music and Tidal made
> loudness normalisation the default between late 2015 and late 2017, years after that
> plateau, and there has been no measurable drop since. The loudest tenth of releases has not
> come down at all. The study uses the open AcousticBrainz and MusicBrainz databases (CC0),
> with loudness estimated from audio features and checked against direct measurement of CDs.
> It covers music that volunteers submitted, not every release, and shows timing rather than
> cause. The article, code and an album lookup tool are at
> https://johnpospisil.github.io/loudness-war/.

---

## Pre-flight checklist

- [ ] Article, app and both images load on a phone (Cmd+Shift+R once on desktop to drop cached app files).
- [ ] Numbers in the drafts still match `article_numbers.json` if the pipeline is re-run.
- [ ] No per-album Dynamic Range Database values anywhere (aggregates only, with citation).
- [ ] Reply to "correlation ≠ causation" with the stated limits; don't argue cause either way.
- [ ] Space posts out (Reddit and HN on different days); be around for the first two hours of each.
