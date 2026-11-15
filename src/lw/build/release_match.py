# ruff: noqa: E501  (SQL strings)
"""P08: match every AcousticBrainz submission to a MusicBrainz release and flag reissues.

Tiers (first that applies):

* **A**  the file's ``musicbrainz_albumid`` tag (redirects resolved) is a release that contains
         this recording (redirects resolved);
* **B**  the file's date-tag year and album name (normalised) match one of the recording's
         releases; ties go to the earliest-dated release;
* **C**  the recording's earliest release (dated first, Official preferred on a tie);
* unmatched: the recording MBID is not in MusicBrainz, or has no releases.

Per submission we add the release and release-group fields and these flags:

* ``rg_first_year`` = the earlier of MusicBrainz's derived first-release year and the group's own
  earliest release year (the derived value is stale for ~370 groups, P07);
* ``reissue_date``: release year > ``rg_first_year`` + 1;
* ``reissue_keyword``: the release title or disambiguation says remaster / anniversary / reissue /
  legacy edition / expanded (some reissues carry the original date, e.g. Nevermind anniversary
  editions; P02);
* ``is_deluxe``: deluxe / special or collector's edition / bonus tracks. Mostly released alongside
  the standard edition (same master), so it is *not* a reissue flag by itself;
* ``reissue_format``: a format that did not exist at first release (CD for a group first released
  before 1982; Digital Media for one first released before 2000);
* ``is_reissue`` = any of the three; ``is_compilation`` / ``is_live`` / ``is_remix`` from the group;
* ``len_diff_s`` = file length - MB track length on the matched release; for tier A rows more than
  5 s out, ``len_best_s`` is the closest length on any release of the recording, and
  ``wrong_edition_suspect`` marks those where another release fits within 2 s. The barcode tag is
  *not* used: Picard writes it from the matched release, so it is not independent evidence (P02).

    uv run python -m lw.build.release_match
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MB = ROOT / "data" / "interim" / "mb"
LL = ROOT / "data" / "interim" / "ab_lowlevel"
OUT = ROOT / "data" / "interim" / "ab_matched.parquet"

# Title/disambiguation words that mean a later edition of the master (count as a reissue alone)
KEYWORDS = r"remaster|re-master|anniversary|reissue|re-issue|legacy edition|expanded"
# Words for editions usually released alongside the original (86% of "deluxe" share the group's
# first year): flagged as is_deluxe, a reissue only if the date rule also fires
EDITION_KEYWORDS = r"deluxe|special edition|collector'?s edition|bonus tracks?"
LEN_TOL_S, LEN_FIT_S = 5.0, 2.0


def norm(x: str) -> str:
    """SQL: album title normalised for tier-B matching (case, accents, punctuation, spaces)."""
    return f"regexp_replace(strip_accents(lower({x})), '[^a-z0-9]', '', 'g')"


YEAR_RE = "(1[89][0-9]{2}|20[0-9]{2})"
STATUS_RANK = """case rel.status when 'Official' then '0' when 'Promotion' then '2'
    when 'Bootleg' then '4' when 'Pseudo-Release' then '4' else
    case when rel.status is null then '1' else '3' end end"""


def _keys(a: str) -> dict[str, str]:
    """Match-key expressions over a low-level table aliased ``a`` (e.g. ``"s."``)."""
    return {
        "ab_rec": f"{a}recording_mbid",
        "tag_rel": f"coalesce(trim({a}tag_musicbrainz_albumid), '')",
        "tag_y": f"coalesce(regexp_extract(coalesce({a}tag_date, {a}tag_year), '{YEAR_RE}', 1), '')",
        "tag_dt": f"coalesce(left(trim({a}tag_date), 10), '')",
        "tag_alb": f"coalesce({norm(a + 'tag_album')}, '')",
    }


def register_mb(con, mb_dir: Path = MB) -> None:
    for t in ["recording", "recording_release", "release", "release_group", "mbid_redirect"]:
        con.execute(
            f"create or replace view mb_{t} as select * from read_parquet('{mb_dir}/{t}.parquet')"
        )


def match(con, subs: str, out: Path) -> dict:
    """Match the submissions in view ``subs`` (low-level columns) and write ``out``."""
    t0 = time.time()
    q = con.execute
    # 1. distinct match keys (submissions share them: same recording + same tags), with an id
    q(f"""create or replace table k as
        select row_number() over () as kid, * from (
            select distinct {", ".join(f"{e} as {n}" for n, e in _keys("").items())} from {subs})""")
    # 2. resolve recording and release MBIDs through redirects
    q("""create or replace table kr as
        select k.*,
               coalesce(r.recording_mbid, x.new_mbid) as rec,
               case when r.recording_mbid is not null then 'direct'
                    when x.new_mbid is not null then 'redirect' else 'missing' end as rec_resolve,
               coalesce(rl.release_mbid, xr.new_mbid) as tag_rel_res
        from k
        left join mb_recording r on r.recording_mbid = k.ab_rec
        left join (select old_mbid, new_mbid from mb_mbid_redirect where entity = 'recording') x
               on x.old_mbid = k.ab_rec and r.recording_mbid is null
        left join (select release_mbid from mb_release) rl on rl.release_mbid = k.tag_rel
        left join (select old_mbid, new_mbid from mb_mbid_redirect where entity = 'release') xr
               on xr.old_mbid = k.tag_rel and rl.release_mbid is null""")
    # 3. the recording's releases, with what tiers B and C need
    q(f"""create or replace table rr as
        select distinct rr.recording_mbid as rec, rr.release_mbid, rel.release_year,
               rel.release_date, {STATUS_RANK} as status_rank, {norm("rel.name")} as name_norm
        from mb_recording_release rr join mb_release rel using (release_mbid)
        where rr.recording_mbid in (select rec from kr where rec is not null)""")
    q("""create or replace table ma as
        select kr.kid, kr.tag_rel_res as release_mbid, 'A' as tier from kr
        where exists (select 1 from rr where rr.rec = kr.rec and rr.release_mbid = kr.tag_rel_res)""")
    # tier B: same year + album title; prefer the release whose full date equals the tag's
    q("""create or replace table mb_ as
        select kr.kid, arg_min(rr.release_mbid,
                   (case when rr.release_date = kr.tag_dt then '0' else '1' end)
                   || coalesce(rr.release_date, '9999') || rr.status_rank || rr.release_mbid)
               as release_mbid, 'B' as tier
        from kr join rr on rr.rec = kr.rec
             and rr.release_year::varchar = kr.tag_y and rr.name_norm = kr.tag_alb
        where kr.tag_y <> '' and kr.tag_alb <> '' and kr.kid not in (select kid from ma)
        group by kr.kid""")
    # tier C: earliest dated release; undated ones last; then Official > none > Promotion > rest
    q("""create or replace table first_rel as
        select rec, arg_min(release_mbid, coalesce(release_date, '9999') || status_rank
                    || release_mbid) as release_mbid
        from rr group by 1""")
    q("""create or replace table m as
        select kr.*, coalesce(a.release_mbid, b.release_mbid, f.release_mbid) as release_mbid,
               case when a.kid is not null then 'A' when b.kid is not null then 'B'
                    when f.release_mbid is not null then 'C' end as tier
        from kr left join ma a using (kid) left join mb_ b using (kid)
        left join first_rel f on f.rec = kr.rec""")
    # 4. group first year (the earlier of MB's derived value and the group's earliest release)
    q("""create or replace table rg as
        select g.*, least(g.first_release_year, e.min_year) as rg_first_year
        from mb_release_group g
        left join (select release_group_mbid, min(release_year) as min_year from mb_release
                   where release_year between 1900 and 2030 group by 1) e using (release_group_mbid)
        where g.release_group_mbid in (select r.release_group_mbid from mb_release r
                                       where r.release_mbid in (select release_mbid from m))""")
    q("""create or replace table tlen as
        select recording_mbid as rec, release_mbid, min(track_length_ms) / 1000.0 as len_min,
               max(track_length_ms) / 1000.0 as len_max
        from mb_recording_release
        where release_mbid in (select release_mbid from m) group by 1, 2""")
    # 5. one row per submission
    q(f"""create or replace table s as
        select s.*, m.rec as recording_mbid_mb, m.rec_resolve, m.tier as match_tier,
               m.tag_rel <> '' as has_release_tag,
               m.tag_rel <> '' and m.tag_rel_res is null as release_tag_unknown,
               m.release_mbid, rel.name as release_name, rel.comment as release_comment,
               rel.release_date, rel.release_date_precision, rel.release_year,
               rel.country as release_country, rel.status as release_status, rel.formats,
               rel.barcode as release_barcode, rel.label as release_label,
               rel.release_group_mbid, g.name as rg_name, g.primary_type, g.secondary_types,
               g.first_release_date as rg_first_release_date, g.rg_first_year,
               g.is_compilation, g.is_live, g.is_remix, g.is_soundtrack, g.is_djmix,
               m.tag_y <> '' and m.tag_y = rel.release_year::varchar as tag_year_agrees,
               case when m.tier is not null then coalesce(rel.release_year,
                    try_cast(nullif(m.tag_y, '') as integer)) end as year,
               case when m.tier is null then null when rel.release_year is not null then 'release'
                    when m.tag_y <> '' then 'tag' end as year_source,
               case when abs(s.length_s - t.len_min) <= abs(s.length_s - t.len_max)
                    then s.length_s - t.len_min else s.length_s - t.len_max end as len_diff_s
        from {subs} s
        join k on {" and ".join(f"k.{n} = {e}" for n, e in _keys("s.").items())}
        join m on m.kid = k.kid
        left join mb_release rel on rel.release_mbid = m.release_mbid
        left join rg g on g.release_group_mbid = rel.release_group_mbid
        left join tlen t on t.rec = m.rec and t.release_mbid = m.release_mbid""")
    # 6. wrong-edition check, only for tier-A rows whose length is off
    q(f"""create or replace table best as
        select s.recording_mbid, s.submission_offset, s.part, s.release_mbid,
               min(abs(s.length_s - r.track_length_ms / 1000.0)) as len_best_s
        from s join mb_recording_release r on r.recording_mbid = s.recording_mbid_mb
        where s.match_tier = 'A' and abs(s.len_diff_s) > {LEN_TOL_S}
              and r.track_length_ms is not null
        group by all""")
    q(f"""copy (select *, reissue_date or reissue_keyword or reissue_format as is_reissue from (
        select s.*, b.len_best_s,
               coalesce(abs(s.len_diff_s) > {LEN_TOL_S} and b.len_best_s <= {LEN_FIT_S}, false)
                   as wrong_edition_suspect,
               coalesce(s.release_year > s.rg_first_year + 1, false) as reissue_date,
               coalesce(regexp_matches(lower(coalesce(s.release_name, '') || ' '
                        || coalesce(s.release_comment, '')), '{KEYWORDS.replace("'", "''")}'), false)
                   as reissue_keyword,
               coalesce(regexp_matches(lower(coalesce(s.release_name, '') || ' '
                        || coalesce(s.release_comment, '')), '{EDITION_KEYWORDS.replace("'", "''")}'), false)
                   as is_deluxe,
               coalesce((s.rg_first_year < 1982 and list_has_any(s.formats,
                         ['CD', 'Enhanced CD', 'HDCD', 'SHM-CD', 'Blu-spec CD', 'CD-R', 'SACD',
                          'Hybrid SACD', 'Copy Control CD']))
                        or (s.rg_first_year < 2000 and list_contains(s.formats, 'Digital Media')),
                        false) as reissue_format
        from s left join best b
          on b.recording_mbid = s.recording_mbid and b.submission_offset = s.submission_offset
         and b.part = s.part and b.release_mbid = s.release_mbid
    )) to '{out}.tmp' (format parquet, compression zstd, row_group_size 500000)""")
    Path(f"{out}.tmp").replace(out)
    con.execute(f"create or replace view matched as select * from read_parquet('{out}')")
    n, nk = (con.execute(f"select count(*) from {subs}").fetchone()[0],
             con.execute("select count(*) from k").fetchone()[0])  # fmt: skip
    return {"submissions": n, "match_keys": nk, "seconds": round(time.time() - t0, 1)}


def summarise(con) -> dict:
    """Shares used in the notes and pinned in tests (view ``matched``)."""
    one = lambda s: con.execute(s).fetchone()  # noqa: E731
    n = one("select count(*) from matched")[0]
    tiers = dict(
        con.execute(
            "select coalesce(match_tier, 'unmatched'), count(*) from matched group by 1"
        ).fetchall()
    )
    res = dict(con.execute("select rec_resolve, count(*) from matched group by 1").fetchall())
    flags = one("""select avg(is_reissue::int), avg(reissue_date::int), avg(reissue_keyword::int),
        avg(reissue_format::int),
        avg((reissue_keyword and not reissue_date)::int), avg((reissue_format and not reissue_date
            and not reissue_keyword)::int),
        avg(is_compilation::int), avg(is_live::int), avg(is_remix::int), avg(is_deluxe::int),
        avg(wrong_edition_suspect::int), avg((match_tier = 'A' and len_diff_s is null)::int),
        avg(tag_year_agrees::int) filter (where match_tier = 'A')
        from matched where match_tier is not null""")  # fmt: skip
    keys = ["is_reissue", "reissue_date", "reissue_keyword", "reissue_format",
            "keyword_only_adds", "format_only_adds", "is_compilation", "is_live", "is_remix", "is_deluxe",
            "wrong_edition_suspect", "tier_a_no_track_length", "tier_a_tag_year_agrees"]  # fmt: skip
    return {
        "submissions": n,
        "tiers": tiers,
        "recording_resolve": res,
        "release_tag_present": one("select avg(has_release_tag::int) from matched")[0],
        "release_tag_unknown": one("select avg(release_tag_unknown::int) from matched")[0],
        "flags_among_matched": dict(zip(keys, flags, strict=True)),
    }


def main(argv: list[str] | None = None) -> None:
    import duckdb

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--memory", default="7GB")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    tmp = ROOT / "data" / "interim" / "duckdb_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    # an on-disk scratch database: its tables (29.5 M wide rows) can be paged out to disk; an
    # in-memory database cannot, and ran out of memory on the P23 rebuild (16 GB machine)
    db = tmp / "release_match.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    con.execute(f"set memory_limit='{args.memory}'; set temp_directory='{tmp}'")
    con.execute(f"set preserve_insertion_order=false; set threads={args.threads}")
    register_mb(con)
    con.execute(f"create view ll as select * from read_parquet('{LL}/part=*.parquet')")
    stats = match(con, "ll", args.out)
    stats.update(summarise(con))
    (args.out.parent / "ab_matched_summary.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    con.close()
    db.unlink(missing_ok=True)
    db.with_suffix(".duckdb.wal").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
