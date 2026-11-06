# P06 — Full AcousticBrainz ingest

_2026-11-05. Code: `src/lw/build/parse_lowlevel.py`, `src/lw/build/parse_highlevel.py`, report `src/lw/viz/p06.py` (`make ingest-ab`, `make ingest-ab-hl`, `make ab-report`). Summary: `data/interim/ab_ingest_summary.json`. Pinned in `tests/test_ab_ingest.py`._

## What was ingested
Both dumps were streamed over HTTP into Parquet, one file per part. The archives were never written to disk, and every part was checked against the published sha256.

| | Low-level | High-level |
|---|---|---|
| Parts | 30/30, sha256 30/30 OK | 30/30, sha256 30/30 OK |
| Compressed bytes | 631.8 GB | 41.8 GB |
| Rows (submissions) | 29,460,584 | 29,460,584 |
| Distinct recordings | 7,564,215 | (same) |
| Parse failures | 30, one non-JSON `COPYING` member per part; 0 real failures | 30, same cause |
| Time | wall clock 2026-11-02 19:26 → 2026-11-04 18:41; sum of part times 70.2 h on 2 streams | sum of part times 2.6 h on 2 streams (about 1.4 h wall clock) |
| Output | `data/interim/ab_lowlevel/part=NN.parquet` | `data/interim/ab_highlevel/part=NN.parquet` |

The low-level wall clock includes a DNS outage that stopped every part (fixed with connect retries, commit `4604b95`) and the machine crash during P03, which forced part 28 to re-run.

## Null rates (low-level)
- **Audio features are 0% null:** `replay_gain`, `dynamic_complexity`, `average_loudness`, spectral, rhythm and band energies. Codec, bit rate and length are also 0%, and `sample_rate` is 0.7%.
- **Tags are what's missing.** These feed P08:

  | Tag | Null rate |
  |---|---|
  | release MBID | 24.5% |
  | release-group MBID | 32.1% |
  | date | 3.3% |
  | originaldate | 49.8% |
  | barcode | 61.4% |
  | genre | 21.5% |
  | album | 1.1% |
  | artist | 0.5% |

  The 24.5% with no release MBID can't reach tier A in P08 and fall back to tiers B and C.

## Codec mix
MP3 is 52%, FLAC 34.5%, AAC 9.6%, ALAC 2.6% and Vorbis 1%. Lossless is 37.3% overall, but it swings from about 5% to about 75% between parts. A few bulk submitters drive the swings: part 24, for example, holds 1M submissions from only 31,725 releases. **P19 must test submitter and cohort effects**, using the `part` and `submission_offset` columns as proxies, because the dump has no submitter ID.

## Joining high-level to low-level
- Every high-level row has a low-level row with the same key `(recording_mbid, submission_offset)`, and the reverse is also true: both anti-joins are empty. On the joined rows, `md5_encoded` agrees in 99.99%.
- **The key is not quite unique.** 3,640 keys appear 2–6 times within a single part, in both dumps alike (7,395 rows, 0.025%). 69% of these repeats have identical audio md5. The join therefore returns 29,468,364 rows. P09's dedupe takes the median per (recording, release), which removes these repeats.
- **145,386 high-level documents (0.49%) have no classifier output.** All 18 classifiers are null together, and most of these rows are in parts 6 and 11. Their low-level rows look ordinary (median length 225 s, same extractor), so the server most likely skipped them. They only lose the genre fallback.
- Models version: `v2.1_beta1` everywhere.

## Caveats carried forward
- Submissions are not recordings: 7.56M recordings have 29.5M submissions. Dedupe is P09.
- The high-level genre classifiers are a **fallback only**, flagged downstream (P10).
- Repeated keys mean `(recording_mbid, submission_offset)` must not be treated as a primary key before P09.
