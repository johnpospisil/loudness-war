# P16: Remaster pairs

Run 2026-11-07 with `make models` (the P16 part, ~1 min). The code is `src/lw/models/remaster_pairs.py`, with figures from `src/lw/viz/p16.py`.

Outputs in `data/processed/`:
- `p16_pairs.parquet`: track pairs;
- `p16_album_pairs.parquet`;
- `p16_by_year.parquet`;
- `p16_famous.parquet`;
- `p16_summary.json`: pinned in `tests/test_remaster_pairs.py`.

## Questions

Are remasters louder than the originals, and has the gap shrunk since 2015? (Brief §2 and chart 4.)

## Pairing rules

Each pair is the same recording MBID on its **original master** and on a **later release**, with release year ≥ original + 2 and ≤ 2022. MusicBrainz keeps the recording MBID across remasters (P02).

- **Both sides lossless and tier A/B.** A tier-C unit has no release tag, so its edition is unknown.
- **Digital releases only.** Vinyl, cassette, reel, shellac, MiniDisc/DCC and unknown formats are excluded on both sides. *Found while building P16:* a lossless file tagged with an LP release is a vinyl rip (or a mis-tagged CD), so it measures the rip chain, not the master. The first pass, which allowed them, produced implausible "remasters" 6–9 LU quieter than the original.
- **The original master** is the earliest digital, non-remaster issue in the original album's release group, taking the median over issues within one year of it. That album is the recording's first non-compilation release group. **For pre-CD albums this is the first CD (38% of remaster pairs)**, so "original" means the first digital master, not the LP.
- **Kinds of later release:**
  - **`remaster`** (main): same release group, labelled as a remaster by the P08 reissue keyword (remaster, anniversary, reissue, legacy, expanded) or "remaster" in the release name or comment;
  - **`reissue`**: other same-album reissues (represses, other countries and labels);
  - **`later`**: later compilations and box sets in another release group.

| kind | track pairs | recordings | album pairs | original albums | median Δ (track) | identical audio (\|Δ\| < 0.05) |
|---|---|---|---|---|---|---|
| **remaster** | **16,991** | 12,689 | 2,283 | 1,567 | **+1.13 LU** | 17% |
| reissue | 108,885 | 66,898 | 16,543 | 8,294 | +0.01 | 33% |
| later | 145,192 | 78,526 | 69,097 | 22,591 | +0.17 | 19% |

**Noise.** Taggers choose a release by track list, not by audio (P08, P11). So an "original" file can hold a remaster and the other way round. Even after all the filters, track-level Δ spreads ±3 LU in both directions. This mixes zeros and false negatives into every cell and **attenuates the gap**. It affects the trend over time only if mis-tagging rates changed, and there's no sign that they did: the share of identical audio is 7–9% in 2010–22 for 1970s and 1980s originals.

## Results

### How much louder are remasters?

Album-pair median Δ est. LUFS for labelled remasters, by the decade of the original master and the reissue period:

| original master | before 2000 | 2000–04 | 2005–09 | 2010–14 | 2015–22 |
|---|---|---|---|---|---|
| 1970s | 0.0 | +1.95 | +1.73 | +1.91 | 0.0 (34 album pairs) |
| **1980s** (incl. first CDs of 1960s/70s albums) | +0.5 | **+2.56** | **+2.76** | **+2.72** | **+2.29** |
| 1990s | 0.0 | +0.43 | +1.03 | +0.57 | +0.16 |
| 2000s+ | — | 0.0 | 0.0 | 0.0 | 0.0 |

- **Remasters of 1980s CD masters are 2–3 LU louder** than the original master, in every period from 2000 on. Remasters of 1990s masters, which were already loud, are only 0–1 LU louder. Remasters of 2000s masters are identical (0.0).
- **Est. LRA hardly changes:** the median ΔLRA is −0.0 to −0.1 LU in every cell. Remasters are louder with nearly the same macro-dynamics, which fits limiting and makeup gain more than any change to the mix's range. Est. LRA is a coarse proxy (P03), though.
- **Famous albums** (`figures/p16_dumbbell_famous_albums.png`): 13 of 20 are louder by more than 0.5 LU. Graceland 2012 is +7.0, Thriller 2008 +5.9, Out of Time 2016 +5.2, Nevermind 2011 +5.0 and Rubber Soul 2009 +3.4. Five are unchanged (±0.0), meaning the "remaster" files match the original audio. Santana's *Supernatural* (−8.7) is flagged as a suspected edition mismatch, not dropped. The rule is stated in advance: a digital remaster more than 3 LU quieter than the original master is most likely a mislabelled file.

### Has the gap shrunk since 2015?

Album-level mixed model: Δ ~ reissue period + original decade, with a random intercept per original album.

| contrast (labelled remasters) | Δ est. LUFS | Δ est. LRA |
|---|---|---|
| 2005–09 vs 2010–14 | +0.54 ± 0.20 | −0.11 ± 0.05 |
| **2015–22 vs 2010–14** | **−0.20 ± 0.19** | −0.03 ± 0.05 |
| **2015–22 vs mean of 2005–14** | **−0.47 [−0.81, −0.14]** | +0.03 [−0.06, +0.11] |
| track-level model (album RE + recording component), 2015–22 vs 2005–14 | −0.26 [−0.42, −0.10] | −0.11 [−0.17, −0.06] |
| other same-album reissues, 2015–22 vs 2005–14 | +0.10 [−0.05, +0.25] | — |
| later compilations, 2015–22 vs 2005–14 | +0.05 [−0.02, +0.11] | — |

Segmented model on reissue year (album level, 2000–22, original-decade fixed effects, album random intercept), using P13's two forms:

| form | 2016–22 gap vs trend | joint p of the 2016 terms |
|---|---|---|
| **bend at 2007, then 2016 terms** | **+0.06 [−0.65, +0.77]** | **0.90** |
| straight 2000–15 trend | −0.43 [−0.96, +0.11] | 0.25 |

In the bend form, the remaster gap **rose about 0.08 LU per reissue year until 2007, then fell about 0.07 LU a year**.

**Answer.** **Yes, modestly.** 2015–22 remasters are about **0.5 LU less over-loud** than 2005–14 ones, holding the original's era fixed (album level −0.47, track level −0.26; both CIs exclude 0). But:
- the gap **peaked in 2005–09** and was already falling by 2010–14;
- there is **no distinct step at 2015/16** (bend form p = 0.90; straight form p = 0.25);
- remasters of 1980s masters are **still about +2.3 LU louder** in 2015–22.

This is the same timing as new releases (P13–P15): a turn in the late 2000s, not at the normalisation era.

**Strength: moderate** for "remasters are louder than original masters" (large, consistent, and visible in the famous albums). **Weak to moderate** for "the gap shrank": 0.3–0.5 LU against heavy per-album noise and attenuation from mis-tagging, and the 1970s cells are small (34–57 album pairs). No causal claim (brief §5).

## Figures

- `figures/p16_remaster_gap_by_year.png`:
  - (a) mean album-pair Δ by reissue year for pre-1990 and 1990s originals, with album-bootstrap CIs, album-pair dots and both segmented results;
  - (b, c) period effects for remasters, reissues and later compilations, for LUFS and LRA.
- `figures/p16_dumbbell_famous_albums.png`: brief chart 4. 20 widely submitted albums, chosen as the most-submitted originals with a labelled digital remaster, at least 6 paired tracks, tier A on both sides and one album per artist. The remaster point is the original plus the median paired-track difference.

**User decisions (2026-11-07):** keep the automatic, reproducible album rule for the dumbbell (hand-picked iconic albums go to P18's own CD rips instead), and keep the identical-audio albums, with a caption note.

## For later prompts

- **P18:** the user's own CD rips should include an original + remaster pair (already planned). Use them to check the dumbbell albums where possible, and the size of the mis-tag attenuation.
- **P19:** add "remaster gap 2015–22 vs 2005–14" with and without the digital-only filter as a spec row; the vinyl filter matters.
- **P21:** the dumbbell values are AcousticBrainz-derived estimates. Label them as such, and keep the edition-mismatch flag.
