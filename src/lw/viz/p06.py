"""P06: AcousticBrainz ingest report — totals, failures, null rates, codec mix, figures.

Writes data/interim/ab_ingest_summary.json and figures/p06_*.png. High-level coverage is
included when data/interim/ab_highlevel/ has parts (it is ingested separately).
"""

from __future__ import annotations

import glob
import json
from datetime import datetime
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np

from lw.viz import theme

ROOT = Path(__file__).resolve().parents[3]
LL = ROOT / "data/interim/ab_lowlevel"
HL = ROOT / "data/interim/ab_highlevel"
OUT = ROOT / "data/interim/ab_ingest_summary.json"
SRC = "Data: AcousticBrainz low-level dump 2022-06-23 (CC0)"
CODECS = ["mp3", "flac", "aac", "alac", "vorbis"]  # others pooled
# Fields that matter downstream, grouped for the coverage chart.
GROUPS = {
    "Loudness / dynamics": ["replay_gain", "dynamic_complexity", "average_loudness",
                            "spectral_rms_mean", "silence_rate_60db"],
    "Spectral / rhythm": ["spectral_centroid", "spectral_flux", "barkbands_flatness_db",
                          "energyband_low", "energyband_high", "rhythm_bpm"],
    "File / codec": ["codec", "lossless", "bit_rate", "sample_rate", "length_s",
                     "essentia_version"],
    "Tags (for MusicBrainz matching)": ["tag_musicbrainz_recordingid", "tag_musicbrainz_albumid",
                                        "tag_musicbrainz_releasegroupid", "tag_date",
                                        "tag_originaldate", "tag_album", "tag_artist",
                                        "tag_barcode", "tag_genre"],
}  # fmt: skip


def _con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute(f"create view ll as select * from read_parquet('{LL}/part=*.parquet')")
    return c


def null_rates(c, view: str = "ll") -> dict[str, float]:
    cols = [r[0] for r in c.execute(f"describe {view}").fetchall()]
    q = "select count(*), " + ", ".join(f'count("{x}")' for x in cols) + f" from {view}"
    n, *counts = c.execute(q).fetchone()
    return {x: 1 - v / n for x, v in zip(cols, counts, strict=True)}


def _done(d: Path) -> list[dict]:
    return [json.loads(Path(f).read_text()) for f in sorted(glob.glob(f"{d}/part=*.done.json"))]


def summary() -> dict:
    c = _con()
    done = _done(LL)
    n, recs, lossless = c.execute(
        "select count(*), count(distinct recording_mbid), avg(lossless::int) from ll"
    ).fetchone()
    by_part = c.execute(
        "select part, count(*), avg(lossless::int), "
        "avg((replay_gain is not null and dynamic_complexity is not null)::int) "
        "from ll group by part order by part"
    ).fetchall()
    codec = dict(c.execute("select codec, count(*) from ll group by 1 order by 2 desc").fetchall())
    subs = c.execute(
        "select n, count(*) from (select recording_mbid, count(*) n from ll group by 1) "
        "group by 1 order by 1"
    ).fetchall()
    s = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "lowlevel": {
            "parts_done": len(done),
            "rows": n,
            "distinct_recordings": recs,
            "lossless_share": lossless,
            "parse_errors": sum(d["errors"] for d in done),
            "parse_error_kinds": "one non-JSON member per part (COPYING licence file)",
            "sha256_ok": sum(bool(d.get("sha256_ok")) for d in done),
            "bytes": sum(d["bytes"] for d in done),
            "part_seconds_sum": sum(d["seconds"] for d in done),
            "wall_clock": {
                "start": "2026-11-02T19:26",
                "end": "2026-11-04T18:41",
                "note": "2 parallel streams; includes a DNS outage and a "
                "machine restart (part 28 re-run)",
            },  # fmt: skip
            "by_part": [
                {"part": p, "rows": r, "lossless": lo, "core_complete": cc}
                for p, r, lo, cc in by_part
            ],  # fmt: skip
            "codec": codec,
            "submissions_per_recording": {int(k): v for k, v in subs[:10]},
            "null_rate": null_rates(c),
        },
    }
    hl_parts = sorted(glob.glob(f"{HL}/part=*.parquet"))
    if hl_parts:
        c.execute(f"create view hl as select * from read_parquet('{HL}/part=*.parquet')")
        hdone = _done(HL)
        hn = c.execute("select count(*) from hl").fetchone()[0]
        joined = c.execute(
            "select count(*) from hl join ll using (recording_mbid, submission_offset)"
        ).fetchone()[0]
        md5_ok = c.execute(
            "select avg((hl.md5_encoded = ll.md5_encoded)::int) from hl "
            "join ll using (recording_mbid, submission_offset)"
        ).fetchone()[0]
        s["highlevel"] = {
            "parts_done": len(hdone),
            "parts_present": len(hl_parts),
            "rows": hn,
            "parse_errors": sum(d["errors"] for d in hdone),
            "sha256_ok": sum(bool(d.get("sha256_ok")) for d in hdone),
            "bytes": sum(d["bytes"] for d in hdone),
            "part_seconds_sum": sum(d["seconds"] for d in hdone),
            "joined_to_lowlevel": joined,
            "md5_agreement_on_join": md5_ok,
            "null_rate": null_rates(c, "hl"),
        }
    OUT.write_text(json.dumps(s, indent=2, default=float))
    return s


def fig_codec(s: dict) -> None:
    bp = s["lowlevel"]["by_part"]
    c = _con()
    rows = c.execute(
        "select part, case when codec in ('mp3','flac','aac','alac','vorbis') then codec "
        "else 'other' end k, count(*) from ll group by 1, 2"
    ).fetchall()
    parts = [b["part"] for b in bp]
    keys = [*CODECS, "other"]
    m = np.zeros((len(keys), len(parts)))
    for p, k, v in rows:
        m[keys.index(k), parts.index(p)] = v
    share = m / m.sum(0)
    theme.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.3), width_ratios=[3, 2])
    colors = [*theme.SERIES[: len(CODECS)], theme.MUTED]
    a1.stackplot(parts, share * 100, colors=colors, labels=keys, alpha=0.9, lw=0)
    a1.set_xlim(0, parts[-1])
    a1.set_ylim(0, 100)
    a1.set_xlabel("Dump part (≈ submission order, 2014 → 2022)")
    a1.set_ylabel("Share of submissions (%)")
    a1.set_title("Codec mix by dump part", loc="left", fontsize=10.5)
    lossless = [b["lossless"] * 100 for b in bp]
    a1.plot(parts, lossless, color=theme.TEXT, lw=1.6, ls=(0, (3, 2)), label="lossless total")
    a1.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=8.5)
    tot = m.sum(1) / 1e6
    order = np.argsort(tot)
    a2.barh([keys[i] for i in order], tot[order], color=[colors[i] for i in order])
    for y, i in enumerate(order):
        a2.text(tot[i] + 0.2, y, f"{tot[i]:.1f}M", va="center", fontsize=8.5, color=theme.TEXT_2)
    a2.set_xlabel("Submissions (millions)")
    a2.set_title("All parts", loc="left", fontsize=10.5)
    a2.grid(axis="y", visible=False)
    a2.set_xlim(0, tot.max() * 1.2)
    fig.suptitle(
        f"Half of AcousticBrainz is MP3 and {s['lowlevel']['lossless_share']:.0%} is lossless, "
        "but the mix swings part to part",
        x=0.01, ha="left", fontsize=13, fontweight="bold",
    )  # fmt: skip
    a1.text(
        0.0,
        -0.2,
        "Swings track a few large submitters (e.g. part 24: 1M submissions from 32k releases)",
        transform=a1.transAxes,
        fontsize=8.5,
        color=theme.TEXT_2,
    )
    fig.tight_layout()
    theme.save_fig(fig, "p06_submissions_by_codec", n=s["lowlevel"]["rows"], source=SRC,
                   note="lossless = FLAC/ALAC/PCM/APE (extractor flag)")  # fmt: skip


def fig_coverage(s: dict) -> None:
    nr = s["lowlevel"]["null_rate"]
    labels, vals, grp = [], [], []
    for g, cols in GROUPS.items():
        for col in cols:
            labels.append(col.removeprefix("tag_"))
            vals.append(nr[col] * 100)
            grp.append(g)
    groups = list(GROUPS)
    if "highlevel" in s:  # every classifier is null together, so one bar covers them all
        g = "High-level (genre fallback, P10)"
        groups.append(g)
        for col in ["genre_rosamerica", "mood_aggressive"]:
            labels.append(f"hl {col}")
            vals.append(s["highlevel"]["null_rate"][col] * 100)
            grp.append(g)
    theme.apply()
    fig, ax = plt.subplots(figsize=(9, 7.2))
    y = np.arange(len(labels))[::-1]
    gi = {g: i for i, g in enumerate(groups)}
    ax.barh(y, vals, color=[theme.SERIES[gi[g]] for g in grp], height=0.7)
    zero = [v < 0.05 for v in vals]
    ax.scatter(
        [0.4] * sum(zero),
        y[np.array(zero)],
        s=18,
        zorder=3,
        color=[theme.SERIES[gi[g]] for g, z in zip(grp, zero, strict=True) if z],
    )
    for yy, v in zip(y, vals, strict=True):
        ax.text(v + 1, yy, f"{v:.1f}%" if v >= 0.05 else "0%", va="center", fontsize=8,
                color=theme.TEXT_2)  # fmt: skip
    ax.set_yticks(y, labels, fontsize=8.5)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Missing (null) in % of submissions")
    ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=theme.SERIES[i]) for i in range(len(groups))]
    ax.legend(handles, groups, loc="lower right", fontsize=8.5)
    fig.suptitle("Audio features are complete; file tags are what's missing", x=0.01, ha="left",
                 fontsize=13, fontweight="bold")  # fmt: skip
    ax.set_title("Null rate per field in the parsed low- and high-level tables", loc="left",
                 fontsize=10,
                 color=theme.TEXT_2)  # fmt: skip
    theme.save_fig(
        fig,
        "p06_field_coverage",
        n=s["lowlevel"]["rows"],
        source=SRC.replace("low-level dump", "low- and high-level dumps"),
        note="recording MBID comes from the file name, so it is never null; hl = high-level dump",
    )
    return None


def main() -> None:
    s = summary()
    fig_codec(s)
    fig_coverage(s)
    ll = s["lowlevel"]
    print(f"low-level: {ll['rows']:,} rows, {ll['distinct_recordings']:,} recordings, "
          f"{ll['parse_errors']} errors, sha ok {ll['sha256_ok']}/30")  # fmt: skip
    if "highlevel" in s:
        h = s["highlevel"]
        print(f"high-level: {h['parts_done']}/30 parts, {h['rows']:,} rows, "
              f"joined {h['joined_to_lowlevel']:,}")  # fmt: skip


if __name__ == "__main__":
    main()
