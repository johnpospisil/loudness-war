# ruff: noqa: E501  (SQL strings)
"""P09: collapse matched submissions to one row per (recording, release): the analysis table.

Steps, each counted in the funnel (``data/processed/tracks_funnel.json``):

1. **Exact repeats.** 2,525 (recording, part, offset, audio md5) keys occur more than once in the
   dump (P06). One copy of each is kept: the best-matched one (tier, then release MBID), since a
   retagged file keeps its audio md5 but can match a different release.
2. **Exclusions, per submission**, so that one bad file cannot move a release's median. The first
   rule that applies is the reason; every excluded submission is logged with it in
   ``data/interim/p09_excluded.parquet``:
   ``unmatched`` (no MB release, P08) · ``no_features`` (replay_gain or dynamic_complexity
   missing or not finite) · ``short`` (< 30 s) · ``lufs_gt_0`` / ``lufs_lt_-60`` (estimated LUFS
   outside [-60, 0]) · ``invalid_lra`` (dynamic_complexity <= 0, or estimated LRA > 50 LU) ·
   ``gain_tagged`` (lossy file carrying an MP3Gain tag: ``mp3gain_undo`` / ``_minmax`` /
   ``_album_minmax``; these read 5-16 LU below the lossless copy, and the 1.5 dB-per-step undo
   correction leaves a ~-5 LU residual, so they are dropped, not corrected) · ``stream_rip``
   (lossy file whose name / encodedby / encoder names Spotify, YouTube, SoundCloud, Audials,
   Tunebite or Streamripper). The two tag reasons need ``data/interim/ab_gaintags``; the dump
   only kept gain tags in part 0, so ``gain_tagged`` reaches early submissions only.
3. **Dedupe.** Median of every audio feature per (MB recording, release), with the submission
   count and the IQR of the estimated LUFS and LRA. ``inconsistent`` flags units with 2+
   submissions whose LUFS IQR > 1.5 LU or LRA IQR > 3 LU. These are about one calibration RMSE
   (P03: 1.34 LU and 2.93 LU), and different encodes of the same master should agree far more
   closely than that. LUFS and LRA are linear in replay_gain and dynamic_complexity
   (``data/reference/proxy_calibration.json``), so their medians equal the calibrated medians.
4. **Codec flags.** A submission is lossless when its codec is FLAC / ALAC / PCM (WAV, AIFF) /
   APE / WavPack. AcousticBrainz's own flag marks WavPack lossy, so it is not used.
   ``low_bitrate`` marks units whose submissions are all lossy with a median bitrate below
   128 kbps.
5. **Lossless first.** ``lufs`` / ``lra`` are the medians over the unit's lossless submissions
   when it has any (``loudness_source = 'lossless'``), else over its lossy ones. Some lossy
   files had MP3Gain / aacgain applied by their owners: the audio is identical but the level is
   shifted, typically to replay_gain ~ -5.5 dB, i.e. several LU quieter than the master. FLAC
   pairs of the same audio agree in 99.9% of cases; pairs involving MP3 disagree in 6-18%
   (notes/p09_dedupe.md). ``lufs_all`` (all submissions), ``lufs_lossless`` and ``lufs_lossy``
   are kept for robustness checks.

The output is ``data/processed/tracks.parquet``, with all years. ``in_core`` marks 1980-2022 and
``in_main`` marks core, tier A/B, not a reissue; ``in_main_lossless`` also requires a lossless
submission (user decision 2026-11-05). ``in_headline`` (the headline sample from P12 on, user
decision 2026-11-07) further requires ``first_appearance``: the unit's year is at most one year
after the recording's earliest dated MusicBrainz release, so box sets and best-ofs of old
recordings (which P08's release-group reissue rule misses) leave the headline.

    uv run python -m lw.build.dedupe
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "interim" / "ab_matched.parquet"
OUT = ROOT / "data" / "processed" / "tracks.parquet"
CAL = ROOT / "data" / "reference" / "proxy_calibration.json"
EXCLUDED = ROOT / "data" / "interim" / "p09_excluded.parquet"

MIN_LEN_S = 30.0
LUFS_MIN, LUFS_MAX = -60.0, 0.0
LRA_MAX = 50.0
IQR_LUFS, IQR_LRA = 1.5, 3.0
LOW_BITRATE = 128_000
CORE = (1980, 2022)
FIRST_APP_SLACK = 1  # years after the recording's first dated release still counted as "new"
MB = ROOT / "data" / "interim" / "mb"
LOSSLESS_CODEC = "(codec in ('flac', 'alac', 'ape', 'wavpack', 'tta') or codec like 'pcm%')"
TAGS = ROOT / "data" / "interim" / "ab_gaintags"
# appended last so the earlier funnel counts are unchanged; lossy submissions only
TAG_REASONS = ["gain_tagged", "stream_rip"]
REASONS = ["unmatched", "no_features", "short", "lufs_gt_0", "lufs_lt_-60", "invalid_lra",
           *TAG_REASONS]  # fmt: skip
# named services / recorder tools only: 'tidal', 'pandora', 'deezer', 'stream' are mostly song
# titles in file names and show no level shift (notes/p09_dedupe.md, gain-tag follow-up)
STREAM_RIP_RE = "spotify|youtube|soundcloud|audials|tunebite|streamripper"

# audio features carried to the unit as medians (replay_gain/dynamic_complexity handled apart)
FEATURES = [
    "average_loudness", "spectral_rms_mean", "spectral_centroid", "spectral_flux",
    "spectral_complexity", "spectral_energy", "barkbands_flatness_db", "energyband_low",
    "energyband_mid_low", "energyband_mid_high", "energyband_high", "silence_rate_60db",
    "rhythm_bpm", "rhythm_onset_rate", "length_s", "len_diff_s",
]  # fmt: skip
# release / group fields: constant within a release, so any_value
RELEASE_COLS = [
    "release_group_mbid", "release_name", "release_comment", "release_date",
    "release_date_precision", "release_year", "release_country", "release_status", "formats",
    "release_label", "rg_name", "primary_type", "secondary_types", "rg_first_release_date",
    "rg_first_year", "is_compilation", "is_live", "is_remix", "is_soundtrack", "is_djmix",
    "reissue_date", "reissue_keyword", "is_deluxe", "reissue_format", "is_reissue",
]  # fmt: skip


def calibration(path: Path = CAL) -> dict[str, tuple[float, float]]:
    """(const, slope) of the headline LUFS ~ replay_gain and LRA ~ dynamic_complexity fits."""
    c = json.loads(path.read_text())
    out = {}
    for target, x in [("lufs", "replay_gain"), ("lra", "dynamic_complexity")]:
        m = c["models"][c["headline"][target]]
        assert m["terms"] == [x], m["terms"]
        out[target] = (m["coef"]["const"], m["coef"][x])
    return out


def dedupe(
    con,
    src: str,
    out: Path,
    excluded: Path = EXCLUDED,
    cal: dict | None = None,
    buckets: int = 48,
    tags: str | None = None,
    rec_first: str | None = None,
) -> dict:
    """Build the analysis table from the view/table ``src`` (P08 columns). Returns the funnel.

    ``tags`` is a table/view of per-submission gain and provenance tags (``parse_gaintags``);
    without it the two tag exclusions remove nothing. ``rec_first`` is a table/view of
    (recording_mbid, rec_first_year): each recording's earliest dated MusicBrainz release; without
    it every unit counts as a first appearance.
    """
    cal = cal or calibration()
    (a0, a1), (b0, b1) = cal["lufs"], cal["lra"]
    lufs = f"({a0} + {a1} * replay_gain)"
    lra = f"({b0} + {b1} * dynamic_complexity)"
    key = "recording_mbid, part, submission_offset, md5_encoded"
    t0 = time.time()
    f: dict[str, int] = {"submissions": con.execute(f"select count(*) from {src}").fetchone()[0]}

    # 1. exact repeats: only the few repeated keys go through the window
    con.execute(f"""create or replace temp table rep as
        select {key} from {src} group by all having count(*) > 1""")
    con.execute(f"""create or replace temp view s1 as
        select * from {src} anti join rep using ({key})
        union all by name
        select * from (select * from {src} semi join rep using ({key}))
        qualify row_number() over (partition by {key} order by match_tier nulls last,
            release_mbid nulls last, tag_album, tag_date, replay_gain) = 1""")
    if tags is None:
        con.execute("""create or replace temp view s1t as
            select *, false as gain_tagged, false as stream_rip from s1""")
    else:
        prov = "lower(concat_ws(' ', tag_file_name, tag_encodedby, tag_encoder))"
        # keep only the few flagged keys (~60k of 29M), so the join below stays small
        con.execute(f"""create or replace temp table gt as select {key},
            bool_or(g) as gain_tagged, bool_or(r) as stream_rip
            from (select {key},
                coalesce(tag_mp3gain_undo, tag_mp3gain_minmax, tag_mp3gain_album_minmax)
                    is not null as g,
                regexp_matches({prov}, '{STREAM_RIP_RE}') as r
              from {tags})
            where g or r group by all""")
        con.execute(f"""create or replace temp view s1t as select s1.*,
            coalesce(gt.gain_tagged, false) as gain_tagged,
            coalesce(gt.stream_rip, false) as stream_rip
            from s1 left join gt using ({key})""")

    # 2. exclusion reason per submission (first rule that applies)
    finite = "(x is not null and isfinite(x))"
    reason = f"""case
        when match_tier is null then 'unmatched'
        when not {finite.replace("x", "replay_gain")} or not {finite.replace("x", "dynamic_complexity")} then 'no_features'
        when length_s is null or length_s < {MIN_LEN_S} then 'short'
        when {lufs} > {LUFS_MAX} then 'lufs_gt_0'
        when {lufs} < {LUFS_MIN} then 'lufs_lt_-60'
        when dynamic_complexity <= 0 or {lra} > {LRA_MAX} then 'invalid_lra'
        when gain_tagged and not {LOSSLESS_CODEC} then 'gain_tagged'
        when stream_rip and not {LOSSLESS_CODEC} then 'stream_rip'
        end"""
    con.execute(f"create or replace temp view s2 as select *, {reason} as excl from s1t")
    excluded.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""copy (select recording_mbid, part, submission_offset, recording_mbid_mb,
            release_mbid, match_tier, year, codec, length_s, replay_gain, dynamic_complexity,
            {lufs} as lufs, {lra} as lra, excl as reason
        from s2 where excl is not null) to '{excluded}' (format parquet, compression zstd)""")
    by = dict(
        con.execute(
            f"select reason, count(*) from read_parquet('{excluded}') group by 1"
        ).fetchall()
    )
    f["after_repeats"] = con.execute("select count(*) from s1").fetchone()[0]
    left = f["after_repeats"]
    f["excluded"] = {}
    for r in REASONS:
        f["excluded"][r] = by.get(r, 0)
        left -= by.get(r, 0)
        f[f"after_{r}"] = left

    # 3-4. one row per (recording, release)
    q = lambda e, p: f"quantile_cont({e}, {p})"  # noqa: E731
    feats = ",\n        ".join(f"median({c})::float as {c}" for c in FEATURES)
    rel = ",\n        ".join(f"any_value({c}) as {c}" for c in RELEASE_COLS)
    ll = LOSSLESS_CODEC
    # exact medians/modes cannot spill, so stage the kept rows in hash buckets of recordings
    # (a unit never spans buckets) and aggregate one bucket at a time
    import shutil

    stage = excluded.parent / "p09_stage"
    shutil.rmtree(stage, ignore_errors=True)
    cols = ["recording_mbid_mb", "release_mbid", "codec", "replay_gain", "dynamic_complexity",
            "bit_rate", "match_tier", "year", "year_source", "tag_year_agrees",
            "wrong_edition_suspect", "essentia_version", "part", "submission_offset",
            *FEATURES, *RELEASE_COLS]  # fmt: skip
    con.execute(f"""copy (select {", ".join(cols)}, hash(recording_mbid_mb) % {buckets} as b
        from s2 where excl is null) to '{stage}'
        (format parquet, compression zstd, partition_by (b))""")
    parts = out.with_name(out.name + ".parts")
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True)
    for b in range(buckets):
        src_b = stage / f"b={b}"
        if not src_b.exists():
            continue
        con.execute(f"""copy (
    with u as (
      select recording_mbid_mb as recording_mbid, release_mbid,
        count(*)::int as n_sub,
        count(*) filter (where {ll})::int as n_lossless,
        median(replay_gain)::float as replay_gain,
        median(dynamic_complexity)::float as dynamic_complexity,
        {q("replay_gain", 0.75)} - {q("replay_gain", 0.25)} as rg_iqr,
        {q("dynamic_complexity", 0.75)} - {q("dynamic_complexity", 0.25)} as dc_iqr,
        max(replay_gain) - min(replay_gain) as rg_range,
        max(dynamic_complexity) - min(dynamic_complexity) as dc_range,
        median(replay_gain) filter (where {ll}) as rg_lossless,
        median(dynamic_complexity) filter (where {ll}) as dc_lossless,
        median(replay_gain) filter (where not {ll}) as rg_lossy,
        median(dynamic_complexity) filter (where not {ll}) as dc_lossy,
        mode(codec order by codec) as codec,
        list_sort(list_distinct(list(codec))) as codecs,
        median(bit_rate) filter (where not {ll} and bit_rate > 0) as bit_rate_lossy,
        count(*) filter (where not {ll} and bit_rate > 0 and bit_rate < {LOW_BITRATE})::int as n_low_bitrate,
        min(match_tier) as match_tier,
        mode(year order by year) as year,
        mode(year_source order by year_source) as year_source,
        avg(tag_year_agrees::int)::float as tag_year_agrees,
        avg(wrong_edition_suspect::int)::float as wrong_edition_share,
        mode(essentia_version order by essentia_version) as essentia_version,
        min(part)::smallint as first_part,
        arg_min(submission_offset, (part, submission_offset)) as first_offset,
        {feats},
        {rel}
      from read_parquet('{src_b}/*.parquet')
      group by recording_mbid_mb, release_mbid)
    select * exclude (rg_iqr, dc_iqr, rg_range, dc_range, rg_lossless, dc_lossless, rg_lossy, dc_lossy),
      ({a0} + {a1} * coalesce(rg_lossless, rg_lossy))::float as lufs,
      ({b0} + {b1} * coalesce(dc_lossless, dc_lossy))::float as lra,
      if(n_lossless > 0, 'lossless', 'lossy') as loudness_source,
      ({a0} + {a1} * replay_gain)::float as lufs_all,
      ({b0} + {b1} * dynamic_complexity)::float as lra_all,
      (abs({a1}) * rg_iqr)::float as lufs_iqr,
      (abs({b1}) * dc_iqr)::float as lra_iqr,
      (abs({a1}) * rg_range)::float as lufs_range,
      (abs({b1}) * dc_range)::float as lra_range,
      ({a0} + {a1} * rg_lossless)::float as lufs_lossless,
      ({b0} + {b1} * dc_lossless)::float as lra_lossless,
      ({a0} + {a1} * rg_lossy)::float as lufs_lossy,
      ({b0} + {b1} * dc_lossy)::float as lra_lossy,
      n_sub >= 2 and (abs({a1}) * rg_iqr > {IQR_LUFS} or abs({b1}) * dc_iqr > {IQR_LRA}) as inconsistent,
      n_lossless = n_sub as all_lossless,
      coalesce(n_lossless = 0 and bit_rate_lossy < {LOW_BITRATE}, false) as low_bitrate,
      coalesce(year between {CORE[0]} and {CORE[1]}, false) as in_core,
      coalesce(year between {CORE[0]} and {CORE[1]} and match_tier in ('A', 'B') and not is_reissue, false) as in_main,
      coalesce(year between {CORE[0]} and {CORE[1]} and match_tier in ('A', 'B') and not is_reissue, false)
        and n_lossless > 0 as in_main_lossless
    from u
    ) to '{parts}/b{b:03d}.parquet' (format parquet, compression zstd)""")
    tmp = out.with_name(out.name + ".tmp")
    out.parent.mkdir(parents=True, exist_ok=True)
    rf = rec_first or "(select null::varchar as recording_mbid, null::int as rec_first_year)"
    # first appearance: the release is within a year of the recording's first dated release
    # (P12, user decision 2026-11-07); unknown first year -> kept
    con.execute(f"""copy (select p.*, rf.rec_first_year::int as rec_first_year,
            coalesce(p.year <= rf.rec_first_year + {FIRST_APP_SLACK}, true) as first_appearance,
            p.in_main_lossless and coalesce(p.year <= rf.rec_first_year + {FIRST_APP_SLACK}, true)
              as in_headline
        from read_parquet('{parts}/*.parquet') p left join {rf} rf using (recording_mbid))
        to '{tmp}' (format parquet, compression zstd, row_group_size 500000)""")
    tmp.rename(out)
    shutil.rmtree(parts)
    shutil.rmtree(stage)
    con.execute(f"create or replace view tracks as select * from read_parquet('{out}')")
    (f["units"], f["units_core"], f["units_main"], f["units_main_consistent"],
     f["units_main_lossless"], f["units_headline"]) = con.execute(
        "select count(*), count(*) filter (where in_core), count(*) filter (where in_main),"
        " count(*) filter (where in_main and not inconsistent),"
        " count(*) filter (where in_main_lossless), count(*) filter (where in_headline) from tracks"
    ).fetchone()  # fmt: skip
    f["seconds"] = round(time.time() - t0, 1)
    return f


def summarise(con) -> dict:
    """Headline numbers for the notes and the pinned test."""
    r = con.execute("""select count(*), sum(n_sub), median(n_sub), avg((n_sub >= 2)::int),
        avg(inconsistent::int) filter (where n_sub >= 2), avg(all_lossless::int),
        avg((n_lossless > 0)::int), avg(low_bitrate::int),
        median(lufs) filter (where in_main), median(lra) filter (where in_main),
        median(lufs_iqr) filter (where n_sub >= 2), median(lra_iqr) filter (where n_sub >= 2),
        count(distinct recording_mbid), count(distinct release_mbid)
        from tracks""").fetchone()
    k = ["units", "submissions_kept", "median_n_sub", "share_multi", "inconsistent_among_multi",
         "share_all_lossless", "share_any_lossless", "share_low_bitrate", "median_lufs_main",
         "median_lra_main", "median_lufs_iqr_multi", "median_lra_iqr_multi", "recordings",
         "releases"]  # fmt: skip
    return {a: (round(b, 6) if isinstance(b, float) else b) for a, b in zip(k, r, strict=True)}


def main(argv: list[str] | None = None) -> None:
    import duckdb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--memory", default="7GB")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    con = duckdb.connect()
    tmp = ROOT / "data" / "interim" / "duckdb_tmp"
    con.execute(f"set memory_limit='{args.memory}'; set temp_directory='{tmp}'")
    con.execute("set preserve_insertion_order=false")
    con.execute(f"create view m as select * from read_parquet('{SRC}')")
    tags = None
    if len(list(TAGS.glob("part=*.done.json"))) == 30:
        con.execute(f"create view gtags as select * from read_parquet('{TAGS}/part=*.parquet')")
        tags = "gtags"
    else:
        print(f"warning: {TAGS} incomplete; gain_tagged / stream_rip exclusions skipped")
    con.execute(f"""create temp table rec_first as
        select rr.recording_mbid, min(r.release_year) as rec_first_year
        from read_parquet('{MB}/recording_release.parquet') rr
        join read_parquet('{MB}/release.parquet') r using (release_mbid)
        where r.release_year is not null
          and rr.recording_mbid in (select distinct recording_mbid_mb from m)
        group by 1""")  # only recordings AcousticBrainz has (keeps the join small)
    stats = {"funnel": dedupe(con, "m", args.out, tags=tags, rec_first="rec_first")}
    stats["summary"] = summarise(con)
    stats["thresholds"] = {"min_len_s": MIN_LEN_S, "lufs": [LUFS_MIN, LUFS_MAX],
                           "lra_max": LRA_MAX, "iqr_lufs": IQR_LUFS, "iqr_lra": IQR_LRA,
                           "low_bitrate": LOW_BITRATE, "core": list(CORE)}  # fmt: skip
    (args.out.parent / "tracks_funnel.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
