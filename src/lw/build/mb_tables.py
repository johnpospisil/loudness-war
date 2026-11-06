"""P07: MusicBrainz full export -> analysis-ready Parquet tables in data/interim/mb/.

Reads the Postgres COPY text files fetched at P02 (``lw.ingest.musicbrainz_dump.connect()``)
and writes, for **all** of MusicBrainz (P08 does the AcousticBrainz matching):

* ``recording.parquet``        recording MBID, name, artist credit, length, comment, video
* ``recording_release.parquet`` recording MBID -> release MBID, medium/track position,
                                track length, medium format (one row per track)
* ``release.parquet``          release date (earliest event) + precision, country, status,
                                packaging, label, catalogue no., barcode, formats, group MBID
* ``release_group.parquet``    first_release_date + precision, primary/secondary types,
                                is_compilation / is_live / is_remix / ... flags
* ``rg_tags.parquet``          release-group tag, vote count, whether it is an MB genre
* ``mbid_redirect.parquet``    merged MBIDs (recording, release, release_group): old -> new

Partial dates: MusicBrainz stores year/month/day separately and any may be NULL. We keep the
parts, a ``*_date`` string at the precision we have (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``) and
a ``*_date_precision`` (``year``/``month``/``day``, NULL when there is no year). A release's
date is its earliest event across ``release_country`` and ``release_unknown_country``, ordered
by year, then month, then day with missing parts last (so "1991-09-24" beats "1991" in the same
year: the more precise event wins a tie on the year).

    uv run python -m lw.build.mb_tables
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "interim" / "mb"
TABLES = [
    "mbid_redirect",
    "recording",
    "release_group",
    "rg_tags",
    "release",
    "recording_release",
]
# release-group secondary types we turn into boolean flags (MB names -> column)
SECONDARY_FLAGS = {
    "Compilation": "is_compilation",
    "Live": "is_live",
    "Remix": "is_remix",
    "Soundtrack": "is_soundtrack",
    "DJ-mix": "is_djmix",
    "Mixtape/Street": "is_mixtape",
    "Demo": "is_demo",
    "Spokenword": "is_spokenword",
    "Audiobook": "is_audiobook",
}


def _int(col: str) -> str:
    return f"try_cast({col} as integer)"


def partial_date(y: str, m: str, d: str, name: str) -> str:
    """SQL select-list items for a partial date given its year/month/day expressions.

    Produces ``{name}_year``, ``{name}_month``, ``{name}_day``, ``{name}_date`` (string at the
    available precision) and ``{name}_date_precision``. A month without a year, or a day without
    a month, is dropped (MusicBrainz allows them but they cannot be placed in time).
    """
    yy = _int(y)
    mm = f"case when {yy} is not null then {_int(m)} end"
    dd = f"case when ({mm}) is not null then {_int(d)} end"
    return f"""
        {yy} as {name}_year,
        {mm} as {name}_month,
        {dd} as {name}_day,
        case
            when {yy} is null then null
            when ({mm}) is null then lpad({yy}::varchar, 4, '0')
            when ({dd}) is null then lpad({yy}::varchar, 4, '0') || '-' || lpad(({mm})::varchar, 2, '0')
            else lpad({yy}::varchar, 4, '0') || '-' || lpad(({mm})::varchar, 2, '0')
                 || '-' || lpad(({dd})::varchar, 2, '0')
        end as {name}_date,
        case when {yy} is null then null when ({mm}) is null then 'year'
             when ({dd}) is null then 'month' else 'day' end as {name}_date_precision"""  # noqa: E501


def _bool(col: str) -> str:
    return f"({col} = 't')"


SQL: dict[str, str] = {}

SQL["mbid_redirect"] = """
    select 'recording' as entity, r.gid as old_mbid, t.gid as new_mbid
    from recording_gid_redirect r join recording t on t.id = r.new_id
    union all
    select 'release', r.gid, t.gid
    from release_gid_redirect r join release t on t.id = r.new_id
    union all
    select 'release_group', r.gid, t.gid
    from release_group_gid_redirect r join release_group t on t.id = r.new_id
"""

SQL["recording"] = f"""
    select r.gid as recording_mbid, {_int("r.id")} as recording_id, r.name,
           ac.name as artist_credit, {_int("r.length")} as length_ms,
           nullif(r.comment, '') as comment, {_bool("r.video")} as video
    from recording r left join artist_credit ac on ac.id = r.artist_credit
"""

SQL["release_group"] = f"""
    with sec as (
        select j.release_group, list(st.name order by st.name) as secondary_types
        from release_group_secondary_type_join j
        join release_group_secondary_type st on st.id = j.secondary_type
        group by 1
    )
    select g.gid as release_group_mbid, {_int("g.id")} as release_group_id, g.name,
           ac.name as artist_credit, pt.name as primary_type,
           coalesce(sec.secondary_types, []::varchar[]) as secondary_types,
           {", ".join(
               f"coalesce(list_contains(sec.secondary_types, '{k}'), false) as {v}"
               for k, v in SECONDARY_FLAGS.items()
           )},
           {partial_date("m.first_release_date_year", "m.first_release_date_month",
                         "m.first_release_date_day", "first_release")},
           {_int("m.release_count")} as release_count,
           nullif(g.comment, '') as comment
    from release_group g
    left join artist_credit ac on ac.id = g.artist_credit
    left join release_group_primary_type pt on pt.id = g.type
    left join release_group_meta m on m.id = g.id
    left join sec on sec.release_group = g.id
"""  # fmt: skip

SQL["rg_tags"] = f"""
    select g.gid as release_group_mbid, t.name as tag, {_int("rt.count")} as count,
           t.name in (select name from genre) as is_genre
    from release_group_tag rt
    join release_group g on g.id = rt.release_group
    join tag t on t.id = rt.tag
"""

SQL["release"] = f"""
    with ev as (
        select release, country, date_year, date_month, date_day from release_country
        union all
        select release, null, date_year, date_month, date_day from release_unknown_country
    ),
    ev2 as (
        select ev.release, iso.code as country,
               {_int("date_year")} as y, {_int("date_month")} as m, {_int("date_day")} as d
        from ev left join iso_3166_1 iso on iso.area = ev.country
    ),
    first_ev as (
        select release, first(country order by k, country nulls last) as country,
               arg_min(y, k) as y,
               arg_min(m, k) as m, arg_min(d, k) as d,
               count(distinct country) as n_countries, count(*) as n_events
        from (
            select *, (coalesce(y, 99999) * 10000 + coalesce(m, 99) * 100 + coalesce(d, 99))
                      as k
            from ev2
        ) group by 1
    ),
    -- first *named* label / non-empty catalogue no. by release_label id (arg_min skips NULLs)
    lab as (
        select rl.release, arg_min(l.name, {_int("rl.id")}) as label,
               arg_min(nullif(rl.catalog_number, ''), {_int("rl.id")}) as catalog_number,
               count(*) as n_labels
        from release_label rl left join label l on l.id = rl.label
        group by 1
    ),
    med as (
        select me.release, count(*) as n_media, sum({_int("me.track_count")}) as n_tracks,
               list(coalesce(mf.name, '(unknown)') order by {_int("me.position")}) as formats
        from medium me left join medium_format mf on mf.id = me.format
        group by 1
    )
    select r.gid as release_mbid, {_int("r.id")} as release_id, r.name,
           ac.name as artist_credit, g.gid as release_group_mbid,
           {partial_date("f.y", "f.m", "f.d", "release")},
           f.country, coalesce(f.n_countries, 0) as n_countries,
           coalesce(f.n_events, 0) as n_events,
           st.name as status, pk.name as packaging,
           lab.label, lab.catalog_number, coalesce(lab.n_labels, 0) as n_labels,
           nullif(r.barcode, '') as barcode, nullif(r.comment, '') as comment,
           coalesce(med.n_media, 0) as n_media, med.n_tracks,
           coalesce(med.formats, []::varchar[]) as formats
    from release r
    left join artist_credit ac on ac.id = r.artist_credit
    left join release_group g on g.id = r.release_group
    left join first_ev f on f.release = r.id
    left join release_status st on st.id = r.status
    left join release_packaging pk on pk.id = r.packaging
    left join lab on lab.release = r.id
    left join med on med.release = r.id
"""  # fmt: skip

SQL["recording_release"] = f"""
    select rec.gid as recording_mbid, rel.gid as release_mbid,
           {_int("me.position")} as medium_position, {_int("t.position")} as track_position,
           t.number as track_number, {_int("t.length")} as track_length_ms,
           mf.name as medium_format, {_bool("t.is_data_track")} as is_data_track
    from track t
    join recording rec on rec.id = t.recording
    join medium me on me.id = t.medium
    join release rel on rel.id = me.release
    left join medium_format mf on mf.id = me.format
"""


def build(con, out: Path = OUT_DIR, tables: list[str] | None = None) -> dict:
    """Write each table to ``out/<name>.parquet``; returns row counts and timings."""
    out.mkdir(parents=True, exist_ok=True)
    stats = {}
    for name in tables or TABLES:
        t0 = time.time()
        tmp = out / f"{name}.parquet.tmp"
        con.execute(
            f"copy ({SQL[name]}) to '{tmp}' "
            "(format parquet, compression zstd, row_group_size 500000)"
        )
        tmp.replace(out / f"{name}.parquet")
        n = con.execute(f"select count(*) from read_parquet('{out / name}.parquet')").fetchone()[0]
        stats[name] = {"rows": n, "seconds": round(time.time() - t0, 1)}
        print(f"{name}: {n:,} rows in {stats[name]['seconds']}s", flush=True)
    return stats


def main(argv: list[str] | None = None) -> None:
    from lw.ingest import musicbrainz_dump as mbd

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dump", help="export directory name (default: latest fetched)")
    ap.add_argument("--tables", nargs="*", choices=TABLES)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--memory", default="6GB", help="DuckDB memory_limit (16 GB machine)")
    args = ap.parse_args(argv)
    con = mbd.connect(args.dump)
    tmpdir = ROOT / "data" / "interim" / "duckdb_tmp"
    con.execute(f"set memory_limit='{args.memory}'; set temp_directory='{tmpdir}'")
    con.execute("set preserve_insertion_order=false")
    stats = build(con, args.out, args.tables)
    d = mbd.dump_dir(args.dump)
    meta = {"dump": d.name, "schema_sequence": (d / "SCHEMA_SEQUENCE").read_text().strip()}
    log = args.out / "build.json"
    prev = json.loads(log.read_text()) if log.exists() else {}
    prev.update(meta)
    prev.setdefault("tables", {}).update(stats)
    log.write_text(json.dumps(prev, indent=2))


if __name__ == "__main__":
    main()
