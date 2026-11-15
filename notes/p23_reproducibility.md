# P23 — Reproducibility pass

_2026-11-15._ Goal: `make all` rebuilds everything from raw data, tests pin the key numbers,
README / DATA.md finished, ruff + pytest clean.

## What was run

1. **Full rebuild (run 1)**: `make rebuild` (= `analysis site check`) from the ingested
   Parquet (`data/interim/`). The ingest itself (`make ingest`, ~2 days, network-bound,
   resumable) was not re-downloaded; its outputs were checksum-verified at P06.
2. **Second pass (run 2)**: `make dedupe genres eda models robustness validate app report site`
   on top of run 1, then every output in `data/processed/` and `app/data/` compared with a
   snapshot of run 1 (38 files: exact match, then order-free and to 1e-9 for floats).

## Fixes needed to make the rebuild work

| Problem | Fix |
| --- | --- |
| `release_match` ran out of memory (6.5 GiB): in-memory DuckDB temp tables cannot spill | on-disk scratch DB `data/interim/duckdb_tmp/release_match.duckdb` (deleted at the end), plain tables, `--threads 4` |
| P10 high-level genre fallback used DuckDB `mode()`, which breaks ties arbitrarily (1,825 units changed genre between runs) | per-classifier `arg_max(label, (n, label))`: ties go to the alphabetically last label |
| P15 cell bootstrap: polars `group_by` without `maintain_order` fed a shared RNG in arbitrary order (R-hat 1.0127 in one run) | sorted input, `maintain_order=True` |
| P16 original release group: `row_number()` tie | tie-break on release-group MBID; famous-album sort keys made total |
| P17 descriptor bootstraps: same RNG-order issue as P15 | units sorted on load, loops with `maintain_order` |
| P13 track-level genre FE: `to_dummies(drop_first=True)` dropped whichever genre DuckDB returned first, so the year-FE two-step gap moved by 0.013 LU | rows sorted before the design matrix (reference genre fixed) |
| P16 pair genre `any_value()` and album `first()` on unordered rows (3 pairs) | `min(genre)`; pairs sorted, `maintain_order=True` |
| P18 seeded bootstraps resampled rows in arrival order (CIs moved by up to 0.03; one album list reordered) | inputs sorted (on values rounded to 1e-9) before resampling; album list tie-broken by name |
| P09 exact-repeat submissions: tie on `replay_gain` kept an arbitrary copy (454 units differ in spectral centroid / flatness / BPM at the 4th significant figure; loudness unaffected) | more tie-break columns in the `row_number()` order |

## Run-to-run result

* **Identical** (exact): `p12_yearly`, `p19_specs`, `p19_summary`, `p14_*`, `p15_cells`,
  `p16_by_year`, `p16_famous`, `p17_*`, `p18_own_tracks`, `p18_encoding`, `p18_drdb_bins`,
  `genre_mix`, `dist.json`; `albums.parquet` and `p17_composition` identical as sets.
* **Fixed after run 2, then verified by running the step twice**: P13 (byte-identical except
  run time), P16 (byte-identical), P18 (identical except last-bit float noise).
* **Remaining, accepted**:
  - P15's two no-AR sensitivity fits differ by ≤ 0.006 LU in the pooled gap (ranks 7/8 swap
    in one), i.e. within Monte Carlo error. Main fits are identical, and refitting the same
    cells in one process is bit-for-bit reproducible, so this is floating-point noise in the
    compiled sampler amplified by NUTS. These rows are not quoted in the article.
  - The P09 tie-break fix takes effect on the next `make dedupe`; it changes only the 454
    descriptor values above.
* **P16 pin changed**: 16,991 → **16,993** track pairs once the original-album tie-break was
  fixed (median Δ 1.131 → 1.129 LU; post-2015 contrast −0.473 LU in both). Test updated.

## Headline numbers are unchanged

Hero yearly medians, the P13 bend-first gap, the P19 specification curve and every article
number reproduce exactly (P18 CIs aside, which moved at the second decimal before the fix).

## Monitoring a long run

`scripts/make_progress.sh LOG TARGET...` draws a progress bar for a make run whose output
goes to `LOG` (e.g. `make rebuild > run.log 2>&1 &` then `scripts/make_progress.sh run.log rebuild`).
