# P04 — Normalisation timeline

_2026-11-05. Data: `data/reference/normalisation_timeline.csv` (20 events). Loader and era definition: `src/lw/normalisation.py`. Figure: `figures/p04_normalisation_timeline.png` (`make timeline`)._

## What's in the CSV
One row per dated event, covering:
- **Services:** Spotify, YouTube, Apple Sound Check, Tidal, Amazon Music, Deezer and Pandora.
- **Standards:** ITU-R BS.1770 (2006, -2, -4, -5), EBU R 128, and AES TD1004 and TD1008.

Each row has a source URL, a short verbatim quote, a confidence rating (high / medium / low) and a `flag` column. Columns:

| Column | Meaning |
|---|---|
| `event_date`, `date_precision` | `date_precision` is `day`, `month` or `year`. **`by` means first evidence that it was already true, not the start date.** |
| `default_on` | Whether the service normalised by default from this event. The brief's `default_on_date` is `event_date` where `default_on` is true. |
| `target_LUFS`, `method`, `measure` | Target, track or album normalisation, and the measurement method (ReplayGain, proprietary, BS.1770). |

## Confidence
- **High (8 events):** primary sources (Apple newsroom, EBU, ITU, Spotify support) or a contemporaneous trade report with a quoted announcement (Tidal 2017, audioXpress).
- **Medium (9 events):** consistent reports from mastering engineers who measured the change (mostly Ian Shepherd at MeterPlugs and Production Advice), with no official announcement. This covers YouTube 2015 and 2019, Spotify 2017 and 2020, Amazon 2019 and Apple 2022.
- **Low or unverified (3 events, flagged `UNVERIFIED`):**
  - **When Spotify first normalised.** The only dated claim is an unsourced how-to article saying 2009. Spotify is well documented as normalising by default by 2017.
  - **Pandora.** Normalising by 2018-05. The target is unknown; third-party sites say about −14 LUFS without a source.
  - **Deezer.** −15 LUFS and on by default on desktop and web by 2019-10. The start date is unknown.

## The "normalisation era" for later charts
- **`era_start()` = 2015.95 (YouTube, December 2015).** This is the first default-on date at a major service with at least medium confidence. Spotify was very probably normalising earlier, but that date is unverified.
- **`era_consolidated()` = 2017.90 (Tidal, November 2017).** By this date three major services (Spotify, YouTube, Tidal) normalised by default.
- AES TD1004 (October 2015) and BS.1770-4 (October 2015) fall in the same quarter as the YouTube change.

**What this means for P13:** the headline break year of 2015 fits the timeline. The 2013–2017 sensitivity range covers the uncertainty, which runs from a possibly earlier Spotify start to the 2017 consolidation. Because release year is a whole year and masters are made months before release, **2016 is an equally defensible break**. P13 should report 2015 and 2016 side by side, not only as part of the sensitivity scan.

## Limits
- Most service dates come from outside measurement, not announcements. Services rarely announce these changes.
- The defaults differ by platform. Examples: Deezer mobile didn't normalise in 2019; Spotify's web player and third-party devices still don't; Apple turns normalisation on by default only on new installs.
- "On by default" does not mean "the listener hears it normalised". We have no data on how many listeners turn it off.
- Targets changed over time. For example, Spotify moved from about −11 to −14 LUFS by 2017 and switched to true LUFS measurement from December 2020. The CSV records each change as a separate event.
- None of this is causal evidence. The timeline only gives the timing (brief §5).
