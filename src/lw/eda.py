# ruff: noqa: E501  (SQL strings)
"""P11: profile the analysis table and spot-check well-known albums.

* ``profile()`` -> ``data/processed/p11_profile.json``: quantiles of the main audio fields,
  correlations (Pearson and Spearman) in the headline sample, decade medians, implausible-value
  counts, and the silence check (est. LRA with and without near-silent tracks).
* ``spotcheck()`` -> ``data/processed/p11_spotcheck.csv``: each album in
  ``data/reference/spotcheck_albums.csv`` is matched to its MusicBrainz release group (normalised
  title + artist credit, first-release year within 1 year; the group with most units wins). The
  original is the group's non-reissue units; an ``edition_year`` (a criticised remaster) selects
  that year's releases instead. Album median est. LUFS / LRA are placed within the main sample
  of the same release year, overall and within the album's genre (percentile = share of units
  quieter / with smaller LRA).

The test set is the albums Wikipedia's "Loudness war" article cites as criticised for loudness
(``criticised_loud``) or as notably dynamic (``noted_dynamic``); expectation, written before the
run: criticised albums sit above their year's median, most in the top quartile; the dynamic
ones sit below it. The ``reference`` albums are a plausibility grid with no expectation.

    uv run python -m lw.eda
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
T = ROOT / "data/processed/tracks.parquet"
RG = ROOT / "data/interim/mb/release_group.parquet"
ALBUMS = ROOT / "data/reference/spotcheck_albums.csv"
PROFILE = ROOT / "data/processed/p11_profile.json"
SPOT = ROOT / "data/processed/p11_spotcheck.csv"
FIELDS = ["lufs", "lra", "replay_gain", "dynamic_complexity", "average_loudness", "length_s",
          "spectral_centroid", "barkbands_flatness_db", "silence_rate_60db", "n_sub"]  # fmt: skip
PAIRS = [("lufs", "lra"), ("lufs", "average_loudness"), ("lra", "average_loudness"),
         ("lra", "silence_rate_60db"), ("lufs", "spectral_centroid"),
         ("lufs", "barkbands_flatness_db"), ("lufs", "silence_rate_60db")]  # fmt: skip
NORM = "trim(regexp_replace(lower(replace({x}, '’', '''')), '[^a-z0-9]+', ' ', 'g'))"
LOW_SIL = 0.05  # 'near-silence-free': < 5% of frames below -60 dB


def _n(x: str) -> str:
    return NORM.format(x=x)


def profile(c) -> dict:
    out: dict = {}
    for s in ["in_main", "in_main_lossless"]:
        out[s] = {}
        for f in FIELDS:
            q = c.execute(f"""select min({f}), quantile_cont({f}, [0.001, 0.01, 0.1, 0.5, 0.9,
                0.99, 0.999]), max({f}), avg({f}), stddev({f}) from t where {s}""").fetchone()
            out[s][f] = {"min": q[0], "q": dict(zip(["0.1%", "1%", "10%", "50%", "90%", "99%",
                         "99.9%"], q[1], strict=True)), "max": q[2], "mean": q[3], "sd": q[4]}  # fmt: skip
    out["corr_lossless"] = {}
    for a, b in PAIRS:
        r, rs = c.execute(f"""with x as (select {a} a, {b} b, rank() over (order by {a}) ra,
            rank() over (order by {b}) rb from t where in_main_lossless)
            select corr(a, b), corr(ra, rb) from x""").fetchone()
        out["corr_lossless"][f"{a}~{b}"] = {"pearson": r, "spearman": rs}
    out["decades_lossless"] = [dict(zip(["decade", "n", "lufs", "lra", "silence"], r, strict=True))
        for r in c.execute("""select year // 10 * 10, count(*), median(lufs), median(lra),
            median(silence_rate_60db) from t where in_main_lossless group by 1 order by 1""").fetchall()]  # fmt: skip
    out["implausible_main"] = dict(zip(
        ["lufs_gt_-4", "lufs_gt_-3", "lufs_lt_-35", "lra_lt_0", "lra_lt_1", "lra_gt_25",
         "length_gt_30min", "n"],
        c.execute("""select count(*) filter (where lufs > -4), count(*) filter (where lufs > -3),
            count(*) filter (where lufs < -35), count(*) filter (where lra < 0),
            count(*) filter (where lra < 1), count(*) filter (where lra > 25),
            count(*) filter (where length_s > 1800), count(*) from t where in_main""").fetchone(),
        strict=True))  # fmt: skip
    out["old_and_loud_main"] = [dict(zip(["year", "share_gt_-8", "tierB_loud", "tierB_rest"], r,
        strict=True)) for r in c.execute("""select year, avg((lufs > -8)::int),
            avg((match_tier = 'B')::int) filter (where lufs > -8),
            avg((match_tier = 'B')::int) filter (where lufs <= -8)
            from t where in_main and year <= 1990 group by 1 order by 1""").fetchall()]  # fmt: skip
    out["silence_check_lossless"] = [dict(zip(["year3", "n_low_sil", "lra_low_sil", "lra_all",
        "lufs_low_sil", "lufs_all"], r, strict=True)) for r in c.execute(f"""select year // 3 * 3,
            count(*) filter (where silence_rate_60db < {LOW_SIL}),
            median(lra) filter (where silence_rate_60db < {LOW_SIL}), median(lra),
            median(lufs) filter (where silence_rate_60db < {LOW_SIL}), median(lufs)
            from t where in_main_lossless group by 1 order by 1""").fetchall()]  # fmt: skip
    out["low_sil_share_lossless"] = c.execute(
        f"select avg((silence_rate_60db < {LOW_SIL})::int) from t where in_main_lossless").fetchone()[0]  # fmt: skip
    return out


def spotcheck(c):
    c.execute(f"""create or replace temp table alb as select row_number() over () as i, *,
        {_n("artist")} as a_n, {_n("album")} as t_n, coalesce(edition_year, year) as at_year
        from read_csv('{ALBUMS}', header=true, all_varchar=false)""")
    # candidate release groups: normalised title equal, artist contained in the credit
    c.execute(f"""create or replace temp table cand as
        select alb.i, g.release_group_mbid, g.first_release_year, g.primary_type,
          (select count(*) from t where t.release_group_mbid = g.release_group_mbid) as units
        from alb join read_parquet('{RG}') g
          on {_n("g.name")} = alb.t_n and {_n("g.artist_credit")} like '%' || alb.a_n || '%'
         and abs(g.first_release_year - alb.year) <= 1""")
    c.execute("""create or replace temp table pick as select * from cand
        qualify row_number() over (partition by i order by units desc,
          (primary_type = 'Album') desc) = 1""")
    c.execute("""create or replace temp table au as
        select alb.i, t.* from alb join pick using (i)
        join t on t.release_group_mbid = pick.release_group_mbid
        where in_core and case when alb.edition_year is null then not t.is_reissue
                               else t.release_year = alb.edition_year end""")
    c.execute("""create or replace temp table s as select i, count(*) n_units,
          count(*) filter (where n_lossless > 0) n_lossless, median(lufs) lufs, median(lra) lra,
          median(lufs_lossless) lufs_lossless, mode(genre) genre,
          median(silence_rate_60db) silence
        from au group by i""")
    return c.sql("""select alb.artist, alb.album, alb.year, alb.edition_year, alb."group",
          pick.release_group_mbid, s.n_units, s.n_lossless, s.genre, s.lufs, s.lra,
          s.lufs_lossless, s.silence,
          (select avg((y.lufs < s.lufs)::int) from t y where y.in_main and y.year = alb.at_year) pct_lufs_year,
          (select avg((y.lufs < s.lufs)::int) from t y where y.in_main and y.year = alb.at_year
             and y.genre = s.genre) pct_lufs_year_genre,
          (select avg((y.lra < s.lra)::int) from t y where y.in_main and y.year = alb.at_year) pct_lra_year,
          (select median(y.lufs) from t y where y.in_main and y.year = alb.at_year) year_median_lufs,
          alb.source, alb.quote
        from alb left join pick using (i) left join s using (i) order by alb.i""").pl()


def main() -> None:
    c = duckdb.connect()
    c.execute("set memory_limit='8GB'")
    c.execute(f"create or replace temp table t as select * from read_parquet('{T}') where in_core")
    p = profile(c)
    df = spotcheck(c)
    df.write_csv(SPOT)
    crit = df.filter(df["group"] == "criticised_loud").drop_nulls("lufs")
    dyn = df.filter(df["group"] == "noted_dynamic").drop_nulls("lufs")
    p["spotcheck"] = {
        "found": int(df["lufs"].is_not_null().sum()), "listed": df.height,
        "criticised_found": crit.height,
        "criticised_above_year_median": int((crit["pct_lufs_year"] > 0.5).sum()),
        "criticised_top_quartile": int((crit["pct_lufs_year"] >= 0.75).sum()),
        "criticised_median_pct": float(crit["pct_lufs_year"].median()),
        "dynamic_found": dyn.height,
        "dynamic_below_year_median": int((dyn["pct_lufs_year"] < 0.5).sum()),
    }  # fmt: skip
    PROFILE.write_text(json.dumps(p, indent=2, default=float))
    print(json.dumps(p["spotcheck"], indent=2))
    print(df.select(["artist", "album", "year", "edition_year", "group", "n_units", "n_lossless",
                     "genre", "lufs", "lra", "pct_lufs_year", "pct_lufs_year_genre"]))  # fmt: skip


if __name__ == "__main__":
    main()
