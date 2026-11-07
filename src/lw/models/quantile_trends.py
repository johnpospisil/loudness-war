# ruff: noqa: E501  (SQL strings, table rows)
"""P14: quantile trends. Did the loudest decile come down?

Track-level **quantile regression** of est. LUFS on the P13 segmented form (release year t,
break B, post = t >= B)::

    Q_tau(y | t) = a + b (t - B) + c post_t + d (t - B) post_t

fitted on every headline unit (``in_headline``) 2000-2022 for tau = 0.05 ... 0.95; the main
quantiles are 0.1, 0.5 and 0.9. Also the P13 "bend first" form: a continuous hinge at k (the
end of the loudness rise, P13 profile: 2007) plus the level/slope terms at B.

**Solver.** The regressors depend on the year only, so the QR estimating equations reduce to
sum_t x_t W_t (F_t(x_t'beta) - tau) = 0, with F_t the weighted empirical CDF of year t. Newton
steps on that 4-5 parameter system (density from a +/-0.3 LU difference of F_t) solve the exact
track-level problem in ~10 ms, checked against statsmodels ``QuantReg`` in the tests.

**Uncertainty, two ways** (both reported):

* **cluster bootstrap by release group** (Poisson(1) weights, as in P12): the sampling error of
  the units; it treats each year's deviation from the line as fixed, so it is narrow;
* **Newey-West (HAC)** on the yearly tau-quantile series (as P13 does for the median): includes
  year-to-year noise; the honest one for a "break" claim, though P13's placebos showed it is
  anti-conservative on this bending series.

**Variants:** ``headline`` (every unit weighted 1) and ``fixed_genre_mix`` (tag-sourced genres
only, units reweighted so every year has the pooled 2000-2014 genre mix: within-genre change,
no genre-mix shift; the P19 option C weighting).

Est. LUFS is calibrated only up to about -5 LUFS (P03 calibration set max -4.75, P99 -5.9), so
quantiles above 0.95 are described, not modelled. Per-track proxy error (+/-1.3 LU) widens
the observed distribution; if it is stable over time, changes in the quantiles carry over but the
tails mix in neighbouring values.

Outputs ``data/processed/p14_quantile.parquet`` (tidy fits), ``p14_yearly_quantiles.parquet``
and ``p14_summary.json``. No causal claim (brief §5).

    uv run python -m lw.models.quantile_trends
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

from lw.models import its

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
OUT = ROOT / "data/processed/p14_quantile.parquet"
YQ = ROOT / "data/processed/p14_yearly_quantiles.parquet"
SUMMARY = ROOT / "data/processed/p14_summary.json"
TAUS = (0.1, 0.5, 0.9)
GRID = tuple(round(0.05 * i, 2) for i in range(1, 20))
DESCRIBE = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)
REPS = 500
SEED = 20261107
HINGE = 2007  # P13 data-driven bend (continuous hinge profile minimum)
HINGES = range(2006, 2012)  # P13 approx. 95% set of both profile forms
SCAN = (2004, 2019)
H = 0.3  # LU half-width for the Newton density step


# ---------------------------------------------------------------- solver


class Years:
    """Units sorted by (year, value), with per-year slices; the fixed part of every fit."""

    def __init__(self, year: np.ndarray, v: np.ndarray):
        o = np.lexsort((v, year))
        self.year, self.v = year[o], v[o].astype(np.float64)
        self.order = o
        self.years = np.unique(self.year)
        self.s = np.searchsorted(self.year, self.years)
        self.e = np.searchsorted(self.year, self.years, side="right")

    def cum(self, w: np.ndarray) -> list[np.ndarray]:
        """Per-year cumulative weights for unit weights w (in sorted order)."""
        return [np.cumsum(w[s:e]) for s, e in zip(self.s, self.e, strict=True)]

    def F(self, q: np.ndarray, cw: list[np.ndarray]) -> np.ndarray:
        return np.array([np.interp(qq, self.v[s:e], c, left=0.0) / c[-1]
                         for qq, s, e, c in zip(q, self.s, self.e, cw, strict=True)])  # fmt: skip

    def quantiles(self, tau: float, cw: list[np.ndarray]) -> np.ndarray:
        return np.array([self.v[s:e][min(np.searchsorted(c, tau * c[-1]), e - s - 1)]
                         for s, e, c in zip(self.s, self.e, cw, strict=True)])  # fmt: skip


def qr_fit(Y: Years, X: np.ndarray, tau: float, cw: list[np.ndarray], it: int = 60) -> np.ndarray:
    """Exact (up to ~1e-4 LU) track-level quantile regression on year-only regressors X
    (one row per year in ``Y.years``)."""
    W = np.array([c[-1] for c in cw])
    b = np.linalg.lstsq(X * np.sqrt(W)[:, None], Y.quantiles(tau, cw) * np.sqrt(W), rcond=None)[0]
    for _ in range(it):
        q = X @ b
        psi = X.T @ (W * (Y.F(q, cw) - tau))
        f = np.maximum((Y.F(q + H, cw) - Y.F(q - H, cw)) / (2 * H), 1e-3)
        step = np.linalg.solve((X * (W * f)[:, None]).T @ X, psi)
        b = b - step
        if np.max(np.abs(step)) < 1e-5:
            break
    return b


def check_loss(Y: Years, X: np.ndarray, b: np.ndarray, tau: float, w: np.ndarray) -> float:
    q = X @ b
    tot = 0.0
    for qq, s, e in zip(q, Y.s, Y.e, strict=True):
        r = Y.v[s:e] - qq
        tot += float(np.sum(w[s:e] * np.where(r >= 0, tau * r, (tau - 1) * r)))
    return tot


# ---------------------------------------------------------------- models


def x_single(t: np.ndarray, b: int) -> np.ndarray:
    return its.design(t, b)


def x_bend(t: np.ndarray, k: int, b: int) -> np.ndarray:
    return np.column_stack([np.ones_like(t), t - b, np.clip(t - k, 0, None),
                            (t >= b).astype(float), (t - b) * (t >= b)])  # fmt: skip


def gap_vec(t: np.ndarray, b: int, p: int) -> np.ndarray:
    g = np.zeros(p)
    g[p - 2], g[p - 1] = 1.0, float(np.mean(t[t >= b] - b))
    return g


def model_specs() -> list[dict]:
    """Model id, window, break, hinge; the bootstrap covers the tau grid for 'grid' models."""
    m = []
    for lo in (2000, 2005):
        for b in (2015, 2016):
            m.append({"model": "single", "window": f"{lo}-2022", "lo": lo, "break": b, "hinge": None,
                      "grid": b == 2016})  # fmt: skip
    m.append(
        {
            "model": "bend",
            "window": "2000-2022",
            "lo": 2000,
            "break": 2016,
            "hinge": HINGE,
            "grid": True,
        }
    )
    for k in HINGES:
        if k != HINGE:
            m.append(
                {
                    "model": "bend",
                    "window": "2000-2022",
                    "lo": 2000,
                    "break": 2016,
                    "hinge": k,
                    "grid": False,
                }
            )
    return m


def _X(spec: dict, t: np.ndarray) -> np.ndarray:
    return (
        x_single(t, spec["break"])
        if spec["model"] == "single"
        else x_bend(t, spec["hinge"], spec["break"])
    )


def summarise_params(spec: dict, t: np.ndarray, p: np.ndarray) -> dict:
    k = len(p)
    g = gap_vec(t, spec["break"], k)
    return {"pre_slope": p[1], "level": p[k - 2], "slope": p[k - 1], "gap": float(g @ p),
            **({"hinge_slope": p[2]} if k == 5 else {})}  # fmt: skip


PARAMS = ("pre_slope", "level", "slope", "gap", "hinge_slope")


# ---------------------------------------------------------------- data


def load(con) -> pl.DataFrame:
    return con.sql(f"""select year, lufs, release_group_mbid,
            case when genre_source <> 'hl' then genre end as genre
        from read_parquet('{T}') where in_headline and year between 1980 and 2022""").pl()


def genre_weights(df: pl.DataFrame, lo: int = 2000, hi: int = 2014) -> np.ndarray:
    """Weights giving every year the pooled lo-hi genre mix (tag genres; others weight 0)."""
    g = df.filter(pl.col("genre").is_not_null())
    ref = (
        g.filter(pl.col("year").is_between(lo, hi))
        .group_by("genre")
        .len()
        .with_columns((pl.col("len") / pl.col("len").sum()).alias("ref"))
    )
    yr = (
        g.group_by(["year", "genre"])
        .len()
        .with_columns((pl.col("len") / pl.col("len").sum().over("year")).alias("share"))
    )
    w = yr.join(ref.select("genre", "ref"), on="genre", how="left").with_columns(
        (pl.col("ref").fill_null(0) / pl.col("share")).alias("w")
    )
    return (
        df.join(w.select("year", "genre", "w"), on=["year", "genre"], how="left")["w"]
        .fill_null(0.0)
        .to_numpy()
    )


# ---------------------------------------------------------------- main


def _hac_series(t, q, spec):
    if spec["model"] == "single":
        r = its.segmented(t, q, spec["break"])
    else:
        r = its.two_break(t, q, spec["hinge"], spec["break"])
    return r


def fit_all(
    df: pl.DataFrame, reps: int = REPS, seed: int = SEED
) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    variants = {"headline": np.ones(len(df)), "fixed_genre_mix": genre_weights(df)}
    cl_all = (df["release_group_mbid"].fill_null("?").rank("dense") - 1).cast(pl.Int64).to_numpy()
    k_cl = int(cl_all.max()) + 1
    specs = model_specs()
    rows, yq_rows, extra = [], [], {}
    for vname, w0_all in variants.items():
        # yearly quantiles 1980-2022 (description + figure), bootstrap CIs
        Yall = Years(df["year"].to_numpy(), df["lufs"].to_numpy())
        w_all, c_all = w0_all[Yall.order], cl_all[Yall.order]
        keep = w_all > 0
        # windowed data for the fits
        sel = (Yall.year >= 2000) & keep
        Y = Years(Yall.year[sel], Yall.v[sel])
        w0, cl = w_all[sel][Y.order], c_all[sel][Y.order]
        t = Y.years.astype(float)
        cw0 = Y.cum(w0)
        cwa = Yall.cum(w_all)
        # point estimates
        point = {}
        for spec in specs:
            taus = GRID if spec["grid"] else TAUS
            for tau in taus:
                m = Y.years >= spec["lo"]
                Ys = _sub(Y, m)
                Xs = _X(spec, t[m])
                cws = [c for c, mm in zip(cw0, m, strict=True) if mm]
                p = qr_fit(Ys, Xs, tau, cws)
                point[(_sid(spec), tau)] = p
                # HAC on the yearly tau-quantile series
                qy = Ys.quantiles(tau, cws)
                hac = _hac_series(t[m], qy, spec)
                rows.append({"variant": vname, "spec": _sid(spec), **{k: spec[k] for k in ("model", "window", "break", "hinge")},
                             "tau": tau, "n_units": int(np.isin(Y.year, Y.years[m]).sum()), "n_years": int(m.sum()),
                             "coef": [float(x) for x in p],
                             **{f"{k}": v for k, v in summarise_params(spec, t[m], p).items()},
                             **{f"hac_{k}": hac[k] for k in ("pre_slope", "level", "slope", "gap") if k in hac},
                             **{f"hac_{k}_se": hac[f"{k}_se"] for k in ("pre_slope", "level", "slope", "gap")},
                             "hac_p_joint": hac.get("p_joint")})  # fmt: skip
        # bootstrap
        rng = np.random.default_rng(seed)
        boots: dict = {key: [] for key in point}
        yq_boot = {tau: [] for tau in DESCRIBE}
        t0 = time.time()
        for r in range(reps):
            pw = rng.poisson(1.0, k_cl).astype(np.float64)
            wr = w0 * pw[cl]
            cwr = Y.cum(wr)
            for (sid, tau), _ in point.items():
                spec = next(s for s in specs if _sid(s) == sid)
                m = Y.years >= spec["lo"]
                Xs = _X(spec, t[m])
                p = qr_fit(_sub(Y, m), Xs, tau, [c for c, mm in zip(cwr, m, strict=True) if mm])
                boots[(sid, tau)].append(list(summarise_params(spec, t[m], p).values()))
            cwra = Yall.cum(w_all * pw[c_all])
            for tau in DESCRIBE:
                yq_boot[tau].append(Yall.quantiles(tau, cwra))
            if r in (0, 9) or (r + 1) % 100 == 0:
                print(f"  {vname}: bootstrap {r + 1}/{reps} ({time.time() - t0:.0f}s)", flush=True)
        for row in rows:
            if row["variant"] != vname:
                continue
            spec = next(s for s in specs if _sid(s) == row["spec"])
            bs = np.array(boots[(row["spec"], row["tau"])])
            names = list(
                summarise_params(spec, t, np.zeros(4 if spec["model"] == "single" else 5)).keys()
            )
            for j, nm in enumerate(names):
                row[f"{nm}_se"] = float(bs[:, j].std(ddof=1))
                row[f"{nm}_lo"], row[f"{nm}_hi"] = (
                    float(x) for x in np.quantile(bs[:, j], [0.025, 0.975])
                )
        n_year = np.array(
            [int(((w_all > 0)[s:e]).sum()) for s, e in zip(Yall.s, Yall.e, strict=True)]
        )
        for tau in DESCRIBE:
            est = Yall.quantiles(tau, cwa)
            b = np.array(yq_boot[tau])
            lo, hi = np.quantile(b, [0.025, 0.975], axis=0)
            for j, y in enumerate(Yall.years):
                yq_rows.append({"variant": vname, "year": int(y), "tau": tau, "q": float(est[j]),
                                "lo": float(lo[j]), "hi": float(hi[j]), "n": int(n_year[j])})  # fmt: skip
        # where does each quantile bend? hinge-only QR profile over 2004-2019 (point estimates)
        prof = []
        for tau in GRID:
            for kk in range(SCAN[0], SCAN[1] + 1):
                X = its.design(t, kk, hinge_only=True)
                p = qr_fit(Y, X, tau, cw0)
                prof.append({"tau": tau, "hinge": kk, "loss": check_loss(Y, X, p, tau, w0)})
        extra[vname] = pl.DataFrame(prof)
    return pl.DataFrame(rows), pl.DataFrame(yq_rows), extra


def _sid(spec: dict) -> str:
    return f"{spec['model']}|{spec['window']}|{spec['break']}" + (
        f"|k{spec['hinge']}" if spec["hinge"] else ""
    )


def _sub(Y: Years, m: np.ndarray) -> Years:
    """View of Y restricted to the years where m is true (m indexes Y.years)."""
    S = Years.__new__(Years)
    S.year, S.v, S.order = Y.year, Y.v, Y.order
    S.years, S.s, S.e = Y.years[m], Y.s[m], Y.e[m]
    return S


def summary(fits: pl.DataFrame, yq: pl.DataFrame, prof: dict) -> dict:
    out: dict = {"n_units": {}, "fits": {}, "hinge_profile_best": {}, "describe": {}}
    for v in ("headline", "fixed_genre_mix"):
        f = fits.filter(pl.col("variant") == v)
        for r in f.filter(pl.col("tau").is_in(list(TAUS))).iter_rows(named=True):
            out["fits"][f"{v}|{r['spec']}|{r['tau']}"] = {
                k: (round(r[k], 4) if isinstance(r[k], float) else r[k])
                for k in ("gap", "gap_lo", "gap_hi", "hac_gap", "hac_gap_se", "level", "slope", "pre_slope",
                          "pre_slope_lo", "pre_slope_hi", "hac_p_joint") if k in r and r[k] is not None}  # fmt: skip
        pr = prof[v]
        best = pr.sort("loss").group_by("tau", maintain_order=True).first().sort("tau")
        out["hinge_profile_best"][v] = {
            str(r["tau"]): r["hinge"] for r in best.iter_rows(named=True)
        }
        y = yq.filter(pl.col("variant") == v)
        for tau in DESCRIBE:
            z = y.filter(pl.col("tau") == tau)

            def per(a, b, z=z):
                return round(float(z.filter(pl.col("year").is_between(a, b))["q"].mean()), 3)

            out["describe"][f"{v}|{tau}"] = {
                "2005-09": per(2005, 2009),
                "2010-15": per(2010, 2015),
                "2016-22": per(2016, 2022),
            }
        out["n_units"][v] = int(
            y.filter((pl.col("tau") == 0.5) & (pl.col("year") >= 2000))["n"].sum()
        )
    return out


def main() -> None:
    t0 = time.time()
    con = duckdb.connect()
    con.execute("set threads = 4")
    df = load(con)
    fits, yq, prof = fit_all(df)
    fits.write_parquet(OUT)
    yq.write_parquet(YQ)
    pl.concat([p.with_columns(pl.lit(v).alias("variant")) for v, p in prof.items()]).write_parquet(
        OUT.with_name("p14_hinge_profile.parquet")
    )
    s = summary(fits, yq, prof)
    SUMMARY.write_text(json.dumps(s, indent=1))
    for k, r in s["fits"].items():
        if (
            "single|2000-2022|2016" in k
            or "single|2005-2022|2016" in k
            or "bend|2000-2022|2016|k2007" in k
        ):
            print(
                f"{k:55s} gap {r['gap']:+.2f} [{r['gap_lo']:+.2f}, {r['gap_hi']:+.2f}]  HAC {r['hac_gap']:+.2f} ± {r['hac_gap_se']:.2f}"
            )
    print("best hinge by tau:", s["hinge_profile_best"])
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
