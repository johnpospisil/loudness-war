"""P03: calibrate AcousticBrainz proxies against pyloudnorm LUFS / LRA.

Fits LUFS ~ f(replay_gain [, dynamic_complexity, average_loudness]) and
LRA ~ g(dynamic_complexity [, ...]) on real music measured by both meters, picks a model by
album-grouped cross-validation, and writes ``data/reference/proxy_calibration.json``.

Use :func:`predict` downstream (P09+) to turn AcousticBrainz columns into estimated
LUFS / LRA with a per-track 95% prediction interval.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[3]
IN_DIR = ROOT / "data/interim/p03_calibration"
OUT_JSON = ROOT / "data/reference/proxy_calibration.json"
N_FOLDS = 10
SEED = 0

# candidate models: name -> (target, list of (column, transform) terms)
CANDIDATES: dict[str, dict] = {
    "lufs_rg": {"target": "lufs", "terms": ["replay_gain"]},
    "lufs_rg_dc": {"target": "lufs", "terms": ["replay_gain", "dynamic_complexity"]},
    "lufs_rg_dc_al": {
        "target": "lufs",
        "terms": ["replay_gain", "dynamic_complexity", "average_loudness"],
    },
    "lra_dc": {"target": "lra", "terms": ["dynamic_complexity"]},
    "lra_dc_sq": {"target": "lra", "terms": ["dynamic_complexity", "dynamic_complexity^2"]},
    "lra_dc_al": {"target": "lra", "terms": ["dynamic_complexity", "average_loudness"]},
    "lra_dc_al_rg": {
        "target": "lra",
        "terms": ["dynamic_complexity", "average_loudness", "replay_gain"],
    },
}
# headline maps used for the "estimated LUFS" and "estimated LRA" columns
HEADLINE = {"lufs": "lufs_rg", "lra": "lra_dc"}


def design(df: pl.DataFrame, terms: list[str]) -> np.ndarray:
    cols = []
    for t in terms:
        if t.endswith("^2"):
            cols.append(df[t[:-2]].to_numpy() ** 2)
        else:
            cols.append(df[t].to_numpy())
    return sm.add_constant(np.column_stack(cols), has_constant="add")


def load_library(path: Path = IN_DIR / "library.parquet") -> pl.DataFrame:
    """Clean measured tracks: no errors, ≥30 s, finite meters, one row per distinct audio."""
    df = pl.read_parquet(path)
    if "error" in df.columns:
        df = df.filter(pl.col("error").is_null())
    df = df.filter(
        (pl.col("duration_s") >= 30)
        & pl.col("lufs").is_finite()
        & pl.col("lra").is_finite()
        & pl.col("replay_gain").is_not_null()
    )
    p = pl.col("path")
    df = df.with_columns(
        album=p.str.replace(r"/[^/]+$", ""),
        artist=p.str.replace(r"/[^/]+/[^/]+$", "").str.replace(r"^.*/", ""),
    )
    # the same audio can sit in both library folders: dedupe on the measured values
    return df.unique(["replay_gain", "length_s", "lufs"], keep="first", maintain_order=True)


def grouped_cv(
    df: pl.DataFrame,
    target: str,
    terms: list[str],
    groups: np.ndarray,
    k: int = N_FOLDS,
    seed: int = SEED,
) -> np.ndarray:
    """Out-of-fold predictions with whole albums held out (tracks within an album correlate)."""
    rng = np.random.default_rng(seed)
    uniq = rng.permutation(np.unique(groups))
    fold_of = {g: i % k for i, g in enumerate(uniq)}
    folds = np.array([fold_of[g] for g in groups])
    X, y = design(df, terms), df[target].to_numpy()
    pred = np.empty_like(y)
    for f in range(k):
        tr, te = folds != f, folds == f
        beta = np.linalg.lstsq(X[tr], y[tr], rcond=None)[0]
        pred[te] = X[te] @ beta
    return pred


def fit_one(df: pl.DataFrame, name: str) -> dict:
    spec = CANDIDATES[name]
    target, terms = spec["target"], spec["terms"]
    X, y = design(df, terms), df[target].to_numpy()
    groups = df["album"].to_numpy()
    codes = np.unique(groups, return_inverse=True)[1]
    ols = sm.OLS(y, X).fit()
    rob = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": codes})
    oof = grouped_cv(df, target, terms, groups)
    res_cv = y - oof
    # binned residuals across the fitted range: is the map biased at the extremes?
    fitted = ols.fittedvalues
    edges = np.quantile(fitted, np.linspace(0, 1, 6))
    bins = np.clip(np.digitize(fitted, edges[1:-1]), 0, 4)
    bias = [float(np.mean(res_cv[bins == b])) for b in range(5)]
    return {
        "name": name,
        "target": target,
        "terms": terms,
        "coef": dict(zip(["const", *terms], map(float, ols.params), strict=True)),
        "cov_cluster": rob.cov_params().tolist(),
        "se_cluster": dict(zip(["const", *terms], map(float, rob.bse), strict=True)),
        "resid_sd": float(np.sqrt(ols.scale)),
        "r2": float(ols.rsquared),
        "cv_rmse": float(np.sqrt(np.mean(res_cv**2))),
        "cv_mae": float(np.mean(np.abs(res_cv))),
        "cv_pi95": [float(np.quantile(res_cv, 0.025)), float(np.quantile(res_cv, 0.975))],
        "cv_bias_by_quintile": bias,
        "spearman": float(
            pl.DataFrame({"a": oof, "b": y}).select(pl.corr("a", "b", method="spearman")).item()
        ),
    }


def predictor_range(df: pl.DataFrame) -> dict:
    out = {}
    for c in ["replay_gain", "dynamic_complexity", "average_loudness", "lufs", "lra"]:
        v = df[c].to_numpy()
        out[c] = {
            "min": float(v.min()),
            "p01": float(np.quantile(v, 0.01)),
            "median": float(np.median(v)),
            "p99": float(np.quantile(v, 0.99)),
            "max": float(v.max()),
        }
    return out


def calibrate(write: bool = True) -> dict:
    from importlib.metadata import version

    df = load_library()
    models = {name: fit_one(df, name) for name in CANDIDATES}
    syn = pl.read_parquet(IN_DIR / "synthetic.parquet")
    for m in models.values():  # out-of-domain check: apply the music fit to pink noise
        pred = predict_with(m, syn)
        r = syn[m["target"]].to_numpy() - pred
        m["synthetic_rmse"] = float(np.sqrt(np.mean(r**2)))
        m["synthetic_bias"] = float(np.mean(r))
    out = {
        "created": date.today().isoformat(),
        "description": (
            "Maps AcousticBrainz Essentia proxies to EBU R128 measures. Fitted on real "
            "music measured with both the AcousticBrainz extractor and pyloudnorm. "
            "Prediction intervals are per-track; yearly medians average much of this "
            "error away but not any bias by genre or era (see notes/p03_calibration.md)."
        ),
        "extractor": "essentia streaming_extractor_music v2.1_beta2-2-gbb40004 (music 1.0)",
        "reference_meter": f"pyloudnorm {version('pyloudnorm')} (BS.1770-4, Tech 3342 LRA)",
        "calibration_set": {
            "n_tracks": df.height,
            "n_albums": df["album"].n_unique(),
            "n_artists": df["artist"].n_unique(),
            "codecs": df["codec"].value_counts().sort("count", descending=True).rows(),
            "domain": predictor_range(df),
        },
        "cv": f"{N_FOLDS}-fold, albums held out together, seed {SEED}",
        "headline": HEADLINE,
        "models": models,
    }
    if write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")
    return out


def predict_with(model: dict, df: pl.DataFrame) -> np.ndarray:
    X = design(df, model["terms"])
    beta = np.array([model["coef"][k] for k in ["const", *model["terms"]]])
    return X @ beta


def predict(
    df: pl.DataFrame, target: str = "lufs", model: str | None = None, calib_path: Path = OUT_JSON
) -> pl.DataFrame:
    """Add ``est_<target>`` and its 95% per-track interval (``_lo``, ``_hi``) to ``df``."""
    cal = json.loads(Path(calib_path).read_text())
    m = cal["models"][model or cal["headline"][target]]
    est = predict_with(m, df)
    lo, hi = m["cv_pi95"]
    return df.with_columns(
        pl.Series(f"est_{target}", est),
        pl.Series(f"est_{target}_lo", est + lo),
        pl.Series(f"est_{target}_hi", est + hi),
    )


if __name__ == "__main__":
    res = calibrate()
    for name, m in res["models"].items():
        print(
            f"{name:14s} R2={m['r2']:.3f} cvRMSE={m['cv_rmse']:.2f} "
            f"PI95={m['cv_pi95'][0]:+.2f}/{m['cv_pi95'][1]:+.2f} "
            f"rho={m['spearman']:.3f} synthRMSE={m['synthetic_rmse']:.2f} coef={m['coef']}"
        )
    print(
        f"-> {OUT_JSON}  (n={res['calibration_set']['n_tracks']}, "
        f"albums={res['calibration_set']['n_albums']})"
    )
