# ruff: noqa: E501  (SQL strings, labels)
"""P15: partially pooled (Bayesian, PyMC) genre model for the 2015/16 break.

**Cells.** Genre x release-year cells of the headline sample (``in_headline``), tag-sourced
genres only (``genre_source <> 'hl'``; user decision 2026-11-07, the classifier fallback is a
sensitivity check). Per cell: n units, median est. LUFS, **P90 est. LUFS** (the loud end, user
decision 2026-11-07 after P14) and median est. LRA (floored at 0), each with a
**release-group cluster bootstrap SE** (Poisson(1) weights, 200 reps). Cells 1990-2022 are
built; models use 2000-2022.

**Model** (per metric; g = genre, t = year, s = t - B, B = 2016, post = t >= B)::

    mu_gt = a_g + b_g s + c_g post + d_g s post                          (straight)
    mu_gt = a_g + b1_g (t - k)_- + b2_g (t - k)_+ + c_g post + d_g s post   (bend)

* ``straight``: the brief's form, a straight 2000-15 pre-trend;
* ``bend``: plus a continuous hinge at k = 2007 (P13's data-driven bend), so the 2016 terms
  are tested against a pre-trend that may already have levelled off.

Every coefficient is partially pooled across genres (non-centred normal hierarchy). The cell
likelihood combines the bootstrap SE with a genre-specific year-level residual sigma_g (pooled
on the log scale), with **AR(1)** residuals (shared phi; conditional likelihood, first year
stationary). Weighting by n enters through the SE: big cells are measured more precisely,
but no cell can outweigh the year-to-year noise sigma_g.

The mean 2016-22 gap of genre g against its own counterfactual is
``gap_g = c_g + d_g * mean(t - B | post) = c_g + 3 d_g``.

Outputs: ``data/processed/p15_cells.parquet``, ``p15_genre_effects.parquet``,
``p15_summary.json``; thinned posterior draws in ``data/interim/p15/*.npz``. No causal claim (brief §5).

    uv run python -m lw.models.genre_hier
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
T = ROOT / "data/processed/tracks.parquet"
CELLS = ROOT / "data/processed/p15_cells.parquet"
EFFECTS = ROOT / "data/processed/p15_genre_effects.parquet"
SUMMARY = ROOT / "data/processed/p15_summary.json"
IDATA = ROOT / "data/interim/p15"
Y0, Y1 = 1990, 2022
FIT = (2000, 2022)
B, K = 2016, 2007
REPS = 200
SEED = 20261107
GENRES = ["rock", "metal", "punk", "pop", "hip_hop", "rnb_soul", "electronic", "reggae",
          "folk_country", "jazz", "classical", "other"]  # fmt: skip
LABELS = {"rock": "Rock", "metal": "Metal", "punk": "Punk", "pop": "Pop", "hip_hop": "Hip-hop",
          "rnb_soul": "R&B / soul / blues", "electronic": "Electronic", "reggae": "Reggae / ska",
          "folk_country": "Folk / country", "jazz": "Jazz", "classical": "Classical", "other": "Other"}  # fmt: skip
METRICS = {"lufs_median": ("lufs", 0.5), "lufs_p90": ("lufs", 0.9), "lra_median": ("lra", 0.5)}


# ---------------------------------------------------------------- cells


def _boot_q(v: np.ndarray, cl: np.ndarray, q: float, reps: int, rng) -> np.ndarray:
    """Quantile q of sorted v under reps Poisson(1) cluster-weight replicates."""
    k = int(cl.max()) + 1
    out = np.empty(reps)
    for r in range(reps):
        cw = np.cumsum(rng.poisson(1.0, k)[cl])
        out[r] = v[min(np.searchsorted(cw, q * cw[-1]), len(v) - 1)]
    return out


def build_cells(con, reps: int = REPS, seed: int = SEED) -> pl.DataFrame:
    df = con.sql(f"""select year, genre, genre_source = 'hl' as hl, lufs, greatest(lra, 0) as lra,
            release_group_mbid
        from read_parquet('{T}') where in_headline and year between {Y0} and {Y1}
          and genre is not null""").pl()
    rng = np.random.default_rng(seed)
    rows = []
    for source, d in [("tags", df.filter(~pl.col("hl"))), ("tags+hl", df)]:
        # sorted, so the bootstrap draws do not depend on row order (P23 reproducibility)
        for (g, y), c in d.sort("genre", "year").group_by(["genre", "year"], maintain_order=True):
            row = {"source": source, "genre": g, "year": int(y), "n": len(c),
                   "n_rg": c["release_group_mbid"].n_unique(),
                   "share_gt8": float((c["lufs"] > -8).mean())}  # fmt: skip
            cl = (c["release_group_mbid"].fill_null("?").rank("dense") - 1).cast(pl.Int64)
            for name, (col, q) in METRICS.items():
                o = np.argsort(c[col].to_numpy(), kind="stable")
                v = c[col].to_numpy()[o]
                row[name] = float(np.quantile(v, q))
                row[f"{name}_se"] = float(_boot_q(v, cl.to_numpy()[o], q, reps, rng).std(ddof=1))
            rows.append(row)
    return pl.DataFrame(rows).sort("source", "genre", "year")


# ---------------------------------------------------------------- model


def design(t: np.ndarray, b: int = B, k: int | None = K) -> dict[str, np.ndarray]:
    s = t - b
    post = (t >= b).astype(float)
    x = {"s": s, "post": post, "spost": s * post}
    if k is not None:
        x["hinge"] = np.clip(t - k, 0, None)
    return x


def fit(cells: pl.DataFrame, metric: str, form: str = "bend", *, b: int = B, k: int = K,
        lo: int = FIT[0], hi: int = FIT[1], ar: bool = True, prior_scale: float = 1.0,
        draws: int = 2000, tune: int = 2000, chains: int = 4, seed: int = SEED, target_accept: float = 0.97):  # fmt: skip
    """Fit the hierarchical segmented model; returns (idata, data dict)."""
    import pymc as pm

    c = cells.filter(pl.col("year").is_between(lo, hi)).sort("genre", "year")
    genres = [g for g in GENRES if g in set(c["genre"])]
    gi = np.array([genres.index(g) for g in c["genre"]])
    t = c["year"].to_numpy().astype(float)
    y = c[metric].to_numpy()
    se = np.maximum(c[f"{metric}_se"].to_numpy(), 1e-3)
    x = design(t, b, k if form == "bend" else None)
    first = np.r_[True, gi[1:] != gi[:-1]]
    prev = np.r_[0, np.arange(len(y) - 1)]
    ps = prior_scale
    ybar = float(np.mean(y))
    with pm.Model(coords={"genre": genres}):

        def hier(name, mu_sd, tau_sd, mu0=0.0):
            mu = pm.Normal(f"mu_{name}", mu0, mu_sd * ps)
            tau = pm.HalfNormal(f"tau_{name}", tau_sd * ps)
            z = pm.Normal(f"z_{name}", 0, 1, dims="genre")
            return pm.Deterministic(name, mu + tau * z, dims="genre"), mu

        a, _ = hier("a", 5.0, 5.0, ybar)
        cc, mu_c = hier("c", 1.0, 0.5)
        dd, mu_d = hier("d", 0.2, 0.1)
        if form == "bend":
            # anchored at the bend: a = level at k, b1 / b2 = slopes before / after k
            # (same model as b (t - B) + h (t - k)_+, but far less correlated)
            b1, _ = hier("b1", 0.3, 0.15)
            b2, _ = hier("b2", 0.2, 0.1)
            trend = b1[gi] * np.minimum(t - k, 0) + b2[gi] * np.maximum(t - k, 0)
        else:
            bb, _ = hier("b", 0.2, 0.1)
            trend = bb[gi] * x["s"]
        mu = a[gi] + trend + cc[gi] * x["post"] + dd[gi] * x["spost"]
        ls_mu = pm.Normal("log_sigma_mu", np.log(0.2), 1.0)
        ls_tau = pm.HalfNormal("log_sigma_tau", 0.5)
        ls_z = pm.Normal("log_sigma_z", 0, 1, dims="genre")
        sigma = pm.Deterministic("sigma", pm.math.exp(ls_mu + ls_tau * ls_z), dims="genre")
        sd = pm.math.sqrt(se**2 + sigma[gi] ** 2)
        if ar:
            phi = pm.Uniform("phi", -0.95, 0.95)
            resid_prev = y[prev] - mu[prev]
            mean = pm.math.switch(first, mu, mu + phi * resid_prev)
            sd = pm.math.switch(first, sd / pm.math.sqrt(1 - phi**2), sd)
        else:
            mean = mu
        pm.Normal("y", mean, sd, observed=y)
        post_mean = float(np.mean(np.unique(t[t >= b]) - b))
        pm.Deterministic("gap", cc + dd * post_mean, dims="genre")
        pm.Deterministic("gap_pooled", mu_c + mu_d * post_mean)
        idata = pm.sample(draws=draws, tune=tune, chains=chains, cores=min(chains, 4),
                          target_accept=target_accept, random_seed=seed, progressbar=False)  # fmt: skip
        pm.compute_log_likelihood(idata, progressbar=False)
        pp = pm.sample_posterior_predictive(idata, random_seed=seed, progressbar=False)
        idata["posterior_predictive"] = pp["posterior_predictive"]
    data = {"genres": genres, "gi": gi, "t": t, "y": y, "se": se, "first": first, "form": form,
            "b": b, "k": k, "post_mean": post_mean}  # fmt: skip
    return idata, data


def diagnostics(idata, var_names=None) -> dict:
    import arviz as az

    names = var_names or [
        v for v in idata["posterior"].data_vars if not v.startswith(("z_", "log_sigma_z"))
    ]
    s = az.summary(idata, var_names=names)
    rhat = np.asarray(s["r_hat"], dtype=float)
    return {"max_rhat": float(np.nanmax(rhat)),
            "min_ess_bulk": float(np.nanmin(np.asarray(s["ess_bulk"], dtype=float))),
            "min_ess_tail": float(np.nanmin(np.asarray(s["ess_tail"], dtype=float))),
            "divergences": int(np.asarray(idata["sample_stats"]["divergences"]).sum())}  # fmt: skip


def draws(idata, name: str) -> np.ndarray:
    """Posterior draws stacked over chains: (n_draws, ...)."""
    v = np.asarray(idata["posterior"][name])
    return v.reshape((-1,) + v.shape[2:])


def effects(idata, data: dict, fit_id: str, metric: str) -> list[dict]:
    rows = []
    gap = draws(idata, "gap")
    names = ["a", "b1", "b2", "c", "d"] if data["form"] == "bend" else ["a", "b", "c", "d"]
    P = {n: draws(idata, n) for n in names}
    for j, g in enumerate(data["genres"]):
        x = gap[:, j]
        r = {"fit": fit_id, "metric": metric, "genre": g, "gap": float(x.mean()),
             "gap_lo": float(np.quantile(x, 0.025)), "gap_hi": float(np.quantile(x, 0.975)),
             "p_neg": float((x < 0).mean()), "p_lt_m02": float((x < -0.2).mean())}  # fmt: skip
        for n, v in P.items():
            r[n] = float(v[:, j].mean())
            r[f"{n}_lo"], r[f"{n}_hi"] = (float(q) for q in np.quantile(v[:, j], [0.025, 0.975]))
        rows.append(r)
    x = draws(idata, "gap_pooled")
    rows.append({"fit": fit_id, "metric": metric, "genre": "_pooled", "gap": float(x.mean()),
                 "gap_lo": float(np.quantile(x, 0.025)), "gap_hi": float(np.quantile(x, 0.975)),
                 "p_neg": float((x < 0).mean()), "p_lt_m02": float((x < -0.2).mean())})  # fmt: skip
    return rows


def ppc_stats(idata, data: dict) -> dict:
    """Coverage of the 50% / 95% posterior predictive intervals and a PIT vector."""
    yrep = np.asarray(idata["posterior_predictive"]["y"])
    yrep = yrep.reshape(-1, yrep.shape[-1])
    y = data["y"]
    lo50, hi50 = np.quantile(yrep, [0.25, 0.75], axis=0)
    lo95, hi95 = np.quantile(yrep, [0.025, 0.975], axis=0)
    pit = (yrep < y).mean(axis=0)
    return {"cover50": float(((y >= lo50) & (y <= hi50)).mean()),
            "cover95": float(((y >= lo95) & (y <= hi95)).mean()), "pit": pit.tolist()}  # fmt: skip


def loo_compare(loos: dict) -> dict:
    """PSIS-LOO elpd of the bend vs the straight form, per metric (pointwise difference SE).

    With AR(1) residuals the pointwise terms are one-step-ahead conditionals, so this compares
    one-step predictive fit; indicative, not exact leave-future-out."""
    out = {}
    for metric in METRICS:
        a, b = loos.get(f"{metric}|bend"), loos.get(f"{metric}|straight")
        if a is None or b is None:
            continue
        d = np.asarray(a.elpd_i).ravel() - np.asarray(b.elpd_i).ravel()
        out[metric] = {"elpd_bend": float(a.elpd), "elpd_straight": float(b.elpd),
                       "diff": float(d.sum()), "se": float(np.sqrt(len(d)) * d.std(ddof=1)),
                       "max_k": float(max(np.nanmax(np.asarray(a.pareto_k)), np.nanmax(np.asarray(b.pareto_k))))}  # fmt: skip
    return out


def save_draws(idata, data: dict, path: Path, thin: int = 4) -> None:
    """Posterior draws the figures need (thinned), the posterior predictive and the data."""
    post = {n: draws(idata, n)[::thin] for n in ("a", "b", "b1", "b2", "c", "d", "gap", "sigma", "phi")
            if n in idata["posterior"]}  # fmt: skip
    yrep = np.asarray(idata["posterior_predictive"]["y"])
    yrep = yrep.reshape(-1, yrep.shape[-1])[::thin]
    np.savez_compressed(path, **post, yrep=yrep, genres=np.array(data["genres"]), gi=data["gi"],
                        t=data["t"], y=data["y"], se=data["se"], brk=data["b"],
                        hinge_k=data["k"] if data["form"] == "bend" else -1)  # fmt: skip


def load_draws(fit_id: str) -> dict:
    z = np.load(IDATA / f"{fit_id.replace('|', '__')}.npz")
    return {k: z[k] for k in z.files}


# ---------------------------------------------------------------- main


def fit_specs() -> list[dict]:
    main = [{"id": f"{m}|{f}", "metric": m, "form": f, "kw": {}, "main": True}
            for m in METRICS for f in ("bend", "straight")]  # fmt: skip
    sens = [
        {"id": "lufs_median|straight|2005-22", "metric": "lufs_median", "form": "straight", "kw": {"lo": 2005}},
        {"id": "lufs_median|bend|k2010", "metric": "lufs_median", "form": "bend", "kw": {"k": 2010}},
        {"id": "lufs_median|bend|B2015", "metric": "lufs_median", "form": "bend", "kw": {"b": 2015}},
        {"id": "lufs_median|bend|no_ar", "metric": "lufs_median", "form": "bend", "kw": {"ar": False}},
        {"id": "lufs_median|bend|wide_priors", "metric": "lufs_median", "form": "bend", "kw": {"prior_scale": 3.0}},
        {"id": "lufs_median|bend|incl_hl", "metric": "lufs_median", "form": "bend", "kw": {}, "source": "tags+hl"},
        {"id": "lufs_p90|bend|no_ar", "metric": "lufs_p90", "form": "bend", "kw": {"ar": False}},
    ]  # fmt: skip
    return main + [dict(s, main=False) for s in sens]


def main(only: list[str] | None = None) -> None:
    t0 = time.time()
    if CELLS.exists() and only:
        cells_all = pl.read_parquet(CELLS)
    else:
        con = duckdb.connect()
        con.execute("set threads = 4")
        cells_all = build_cells(con)
        cells_all.write_parquet(CELLS)
        print(f"cells: {cells_all.height} ({time.time() - t0:.0f}s)", flush=True)
    IDATA.mkdir(parents=True, exist_ok=True)
    eff, summ, loos = [], {"fits": {}}, {}
    for spec in fit_specs():
        if only and spec["id"] not in only:
            continue
        cells = cells_all.filter(pl.col("source") == spec.get("source", "tags"))
        t1 = time.time()
        idata, data = fit(cells, spec["metric"], spec["form"], **spec["kw"])
        d = diagnostics(idata)
        p = ppc_stats(idata, data)
        e = effects(idata, data, spec["id"], spec["metric"])
        eff += e
        g = [r for r in e if r["genre"] != "_pooled"]
        pooled = next(r for r in e if r["genre"] == "_pooled")
        phi = draws(idata, "phi") if "phi" in idata["posterior"] else None
        summ["fits"][spec["id"]] = {
            "main": spec["main"], **d, "cover50": p["cover50"], "cover95": p["cover95"],
            "phi": None if phi is None else float(phi.mean()),
            "pooled_gap": [round(pooled[k], 3) for k in ("gap", "gap_lo", "gap_hi")],
            "n_genres": len(g),
            "n_gap_neg_95": sum(r["p_neg"] > 0.95 for r in g),
            "n_gap_pos_95": sum(r["p_neg"] < 0.05 for r in g),
            "n_gap_lt_m02_90": sum(r["p_lt_m02"] > 0.9 for r in g),
            "ranking": [r["genre"] for r in sorted(g, key=lambda r: r["gap"])],
            "seconds": round(time.time() - t1),
        }  # fmt: skip
        if spec["main"]:
            import arviz as az

            loos[spec["id"]] = az.loo(idata)
            save_draws(idata, data, IDATA / f"{spec['id'].replace('|', '__')}.npz")
        f = summ["fits"][spec["id"]]
        print(f"{spec['id']:32s} rhat {d['max_rhat']:.3f} ess {d['min_ess_bulk']:.0f}/{d['min_ess_tail']:.0f} "
              f"div {d['divergences']} cov95 {p['cover95']:.2f} pooled {f['pooled_gap']} "
              f"neg95 {f['n_gap_neg_95']}/{len(g)} pos95 {f['n_gap_pos_95']} ({f['seconds']}s)", flush=True)  # fmt: skip
    if loos:
        summ["loo"] = loo_compare(loos)
        for m_, r in summ["loo"].items():
            print(
                f"LOO {m_}: bend - straight = {r['diff']:+.1f} ± {r['se']:.1f} (max Pareto k {r['max_k']:.2f})"
            )
    new = pl.DataFrame(eff)
    if only and EFFECTS.exists():
        old = pl.read_parquet(EFFECTS).filter(~pl.col("fit").is_in(only))
        new = pl.concat([old, new], how="diagonal")
        prev = json.loads(SUMMARY.read_text())
        summ["fits"] = {**prev["fits"], **summ["fits"]}
        summ["loo"] = {**prev.get("loo", {}), **summ.get("loo", {})}
    new.write_parquet(EFFECTS)
    summ["n_units_fit"] = int(
        cells_all.filter((pl.col("source") == "tags") & pl.col("year").is_between(*FIT))["n"].sum()
    )
    SUMMARY.write_text(json.dumps(summ, indent=1))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:] or None)
