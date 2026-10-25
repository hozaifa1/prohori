"""Fitting library for the certification gate (used by eval/gate_fit.py and tests).

Pipeline for one set of calibration groups (`fit_pipeline`):
  1. score model: predicts log(|error| / tolerance) from the gate's design features.  Two families:
       "gbm"    monotone-constrained gradient-boosted trees (every badness feature may only raise the prediction),
                exported as plain arrays (numpy-only at run time)            <- deployed
       "linear" sign-constrained ridge (kept for the comparison table)
     cross-fitted by source photo, so every calibration row has a prediction from a model that never saw its group;
  2. Conformal Risk Control (Angelopoulos et al., ICLR 2024) on the out-of-fold predictions -> theta per level alpha;
  3. split-conformal 90 % interval: normalised error, Mondrian cells by measured-width bin (and by certified/flagged state);
  4. final score model refitted on all calibration rows (the deployed one).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori import gate as G  # noqa: E402

ALPHAS = [0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]
W_EDGES = [0.0, 0.45, 0.9, 1.25, 1.75, 2.5, math.inf]  # measured-width bins ~ {0.3,0.4} | {0.5,0.75} | {1} | {1.5} | {2} | {3} mm
EPS_MM = 0.005
FREE_SIGN = {"log_w"}
MODEL_KIND = "gbm"
GBM_KW = dict(max_depth=3, max_iter=100, learning_rate=0.1, min_samples_leaf=60)


# ----------------------------------------------------------------------------- data

def load_rows(path=None) -> pd.DataFrame:
    path = path or ROOT / "eval" / "results" / "gate_calibration_features.parquet"
    df = pd.read_parquet(path)
    df = df[df["crack"] != ""].copy().reset_index(drop=True)
    df["cap"] = df["photo"] + "|" + df["v"].astype(str)
    return df


TONER_BLEED_MM = 0.0137  # per edge, horizontal specimens of the printed panel (research/WIDTH_AUTORESEARCH.md, METRICS 1a)


def alt_truth(df: pd.DataFrame) -> dict:
    """Secondary reference: the toner-corrected width (nominal + 2 x bleed) and 'wrong' against it (same tolerance rule)."""
    t = df["true_mm"].values + 2.0 * TONER_BLEED_MM
    err = df["width_mm"].values - t
    return {"true_corr": t, "err_corr": err, "wrong_corr": np.abs(err) > G.tolerance_mm(t)}


def raw_from_row(r) -> dict:
    bs = r["obs_blur_sigma_mm"]
    sig_mm = bs if bs and bs > 0 else 0.2
    return {
        "corners": float(r["obs_corners"]), "ppm": float(r["ppm"]), "blur_var": float(r["obs_blur_var"]),
        "blur_sigma_mm": float(sig_mm), "sigma_px": float(r["q_sigma_px"]), "obliquity_deg": float(r["obs_obliquity_deg"]),
        "glare_frac": float(r["obs_glare_frac"]), "noise_sigma": float(r["obs_noise_sigma"]),
        "reproj_px": 0.0 if pd.isna(r["obs_reproj_px"]) else float(r["obs_reproj_px"]),
        "width_mm": float(r["width_mm"]), "coverage": float(r["q_coverage"]), "spread_rel": float(r["q_spread_rel"]),
        "disagree_rel": float(r["q_disagree_rel"]), "dt_rel": float(r["q_dt_rel"]), "q_core": float(r["q_q_core"]),
        "sat_frac": float(r["q_sat_frac"]), "edt_ratio": float(r["q_edt_ratio"]), "n_holes": float(r["q_n_holes"]),
        "frag_frac": float(r["q_frag_frac"]), "path_cover": float(r["q_path_cover"]),
        "locator_gt": float(r["q_locator_gt"]),
    }


def prepare(df: pd.DataFrame) -> dict:
    """Design matrix and per-row quantities as numpy arrays (everything a worker process needs)."""
    raws = [raw_from_row(r) for _, r in df.iterrows()]
    X = np.array([G.design_vector(r) for r in raws])
    tol = G.tolerance_mm(df["true_mm"].values)
    y = np.log((df["abs_err_mm"].values + EPS_MM) / tol)
    w = df["width_mm"].values
    ppm = np.array([r["ppm"] for r in raws])
    return {"X": X, "y": y, "raws": raws, "cap": df["cap"].values, "group": df["group"].values,
            "wrong": df["wrong"].astype(bool).values, "err": df["err_mm"].values, "true": df["true_mm"].values,
            "w": w, "u": df["u_model_mm"].values, "tol": tol, "ppm": ppm,
            "ures": np.array([G.u_res_mm(p, x) for p, x in zip(ppm, w)]), "v": df["v"].values}


def light(D: dict) -> dict:
    """Arrays only (picklable cheaply for worker processes)."""
    return {k: v for k, v in D.items() if k not in ("raws", "df")}


def qa_pass(raws, qa=None):
    return np.array([not G.qa_reasons(r, qa) for r in raws])


# ----------------------------------------------------------------------------- score models

def _free_mask():
    return np.array([f in FREE_SIGN for f in G.FEATURES])


def fit_linear(X, y, ridge=3.0, clip_q=(0.5, 99.5)):
    """Sign-constrained ridge regression in standardised, winsorised feature space."""
    lo, hi = np.percentile(X, clip_q[0], axis=0), np.percentile(X, clip_q[1], axis=0)
    Z = np.clip(X, lo, hi)
    mu, sd = Z.mean(0), Z.std(0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    U = (Z - mu) / sd
    ym = y.mean()
    p = U.shape[1]
    A = np.vstack([U, math.sqrt(ridge) * np.eye(p)])
    b = np.concatenate([y - ym, np.zeros(p)])
    lb = np.where(_free_mask(), -np.inf, 0.0)
    res = lsq_linear(A, b, bounds=(lb, np.full(p, np.inf)), method="bvls")
    return {"type": "linear", "features": list(G.FEATURES), "lo": lo.tolist(), "hi": hi.tolist(), "mean": mu.tolist(),
            "std": sd.tolist(), "coef": res.x.tolist(), "intercept": float(ym)}


def fit_gbm(X, y, feats=None, **kw):
    """Monotone-constrained histogram gradient boosting, exported to arrays (see gate._gbm_predict).  `feats`: the names
    of the columns of X (default `gate.FEATURES`; the distance experiment appends candidate columns)."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    feats = list(feats or G.FEATURES)
    cst = [0 if f in FREE_SIGN else 1 for f in feats]
    m = HistGradientBoostingRegressor(random_state=0, monotonic_cst=cst, **{**GBM_KW, **kw}).fit(X, y)
    trees = []
    for it in m._predictors:
        n = it[0].nodes
        trees.append({"f": n["feature_idx"].astype(int).tolist(), "t": [float(v) for v in n["num_threshold"]],
                      "l": n["left"].astype(int).tolist(), "r": n["right"].astype(int).tolist(),
                      "v": [float(v) for v in n["value"]], "leaf": n["is_leaf"].astype(int).tolist()})
    return {"type": "gbm", "features": feats, "base": float(np.ravel(m._baseline_prediction)[0]),
            "trees": trees, "_sk": m}


def fit_model(X, y, kind=None, feats=None, **kw):
    kind = kind or MODEL_KIND
    return fit_gbm(X, y, feats=feats, **kw) if kind == "gbm" else fit_linear(X, y, **kw)


def predict_many(model, X):
    if model["type"] == "gbm":
        return _gbm_many(model, X)
    z = np.clip(X, model["lo"], model["hi"])
    return model["intercept"] + ((z - np.asarray(model["mean"])) / np.asarray(model["std"])) @ np.asarray(model["coef"])


def _gbm_many(model, X):
    n = len(X)
    out = np.full(n, model["base"])
    rows = np.arange(n)
    for t in model["trees"]:
        f, th, l, r, v, leaf = (np.asarray(t[k]) for k in ("f", "t", "l", "r", "v", "leaf"))
        idx = np.zeros(n, int)
        for _ in range(12):
            isleaf = leaf[idx].astype(bool)
            if isleaf.all():
                break
            go_left = X[rows, f[idx]] <= th[idx]
            idx = np.where(isleaf, idx, np.where(go_left, l[idx], r[idx]))
        out += v[idx]
    return out


def serialisable(model):
    return {k: v for k, v in model.items() if not k.startswith("_")}


def oof_predict(D, groups, k=5, seed=0, kind=None, **kw):
    """Out-of-fold predictions for rows of `groups` (grouped k-fold)."""
    rng = np.random.default_rng(seed)
    gl = np.array(sorted(groups))
    rng.shuffle(gl)
    folds = np.array_split(gl, min(k, len(gl)))
    pred = np.full(len(D["y"]), np.nan)
    ing = np.isin(D["group"], gl)
    for f in folds:
        te = np.isin(D["group"], f)
        tr = ing & ~te
        m = fit_model(D["X"][tr], D["y"][tr], kind, feats=D.get("feats"), **kw)
        pred[te] = predict_many(m, D["X"][te])
    return pred


# ----------------------------------------------------------------------------- risk machinery

def loss_matrix(cap, pred, qa, wrong, thetas):
    """(n_captures, K): per-capture mean over its measured cracks of 1[QA & pred <= theta] * wrong."""
    order = np.argsort(cap, kind="stable")
    cap_s, pred_s, qa_s, wr_s = cap[order], pred[order], qa[order], wrong[order]
    starts = np.r_[0, np.nonzero(cap_s[1:] != cap_s[:-1])[0] + 1]
    counts = np.diff(np.r_[starts, len(cap_s)])
    hit = (qa_s & wr_s)[:, None] & (pred_s[:, None] <= thetas[None, :])
    sums = np.add.reduceat(hit.astype(np.float32), starts, axis=0)
    return sums / counts[:, None], cap_s[starts]


def theta_grid(pred, qa, K=300):
    p = pred[qa]
    if len(p) == 0:
        return np.array([-np.inf])
    q = np.quantile(p, np.linspace(0, 1, K))
    return np.unique(np.r_[-np.inf, q])


def crc_thetas(cap, pred, qa, wrong, alphas, K=300):
    """CRC thresholds theta (certify iff QA and pred <= theta) for several levels at once; lam = -theta is the CRC
    parameter.  Returns {alpha: (theta, n_captures, empirical risk at theta or None)}."""
    th = theta_grid(pred, qa, K)
    L, caps = loss_matrix(cap, pred, qa, wrong, th)
    lam = -th[::-1]
    Lr = L[:, ::-1]
    out = {}
    for a in alphas:
        k, lam_hat = G.crc_threshold(Lr, lam, a)
        out[a] = (-math.inf, len(caps), None) if k is None else (-lam_hat, len(caps), float(Lr[:, k].mean()))
    return out


def eval_gate(D, mask, pred, qa, theta):
    """Held-out metrics for rows `mask`: joint risks, conditional risk, certification rates."""
    cap, wrong = D["cap"][mask], D["wrong"][mask]
    cert = qa[mask] & (pred[mask] <= theta)
    n = int(mask.sum())
    cw = cert & wrong
    L, _ = loss_matrix(cap, pred[mask], qa[mask], wrong, np.array([theta]))
    caps_cert = pd.Series(cert).groupby(cap).any()
    return {"n_rows": n, "n_caps": int(len(caps_cert)), "cert_rate": float(cert.mean()) if n else math.nan,
            "joint_risk_pooled": float(cw.sum() / n) if n else math.nan,
            "joint_risk_capture": float(L.mean()) if n else math.nan,
            "cond_risk": float(cw.sum() / cert.sum()) if cert.sum() else math.nan,
            "capture_cert_rate": float(caps_cert.mean()) if n else math.nan}


# ----------------------------------------------------------------------------- intervals

def w_bin(w):
    return np.searchsorted(W_EDGES, w, side="right") - 1


def interval_scale(D, pred, kind):
    """Per-row scale (mm) the error is normalised by: learned = tol(w_hat) * exp(pred); heuristic = the 1-sigma model of
    measure._uncertainty; heuristic_res = that plus the krkCMd resolution-added term u_res(px/mm, w) in quadrature;
    const = 1 (plain absolute error)."""
    if kind == "learned":
        return np.maximum(0.01, G.tolerance_mm(D["w"]) * np.exp(pred))
    if kind == "heuristic":
        return np.maximum(0.01, D["u"])
    if kind == "heuristic_res":
        return np.maximum(0.01, np.hypot(D["u"], D["ures"]))
    return np.ones(len(D["y"]))


def fit_intervals(D, rows, pred, cert, kind="learned", by_state=False, signed=False, level=0.9):
    """Mondrian split-conformal cells.  rows: calibration rows; pred: (out-of-fold) predictions."""
    scale = interval_scale(D, pred, kind)
    e = D["err"] / scale
    wb = w_bin(D["w"])
    cells = []
    for b in range(len(W_EDGES) - 1):
        for st in (["certified", "flagged"] if by_state else ["any"]):
            m = rows & (wb == b)
            if st == "certified":
                m = m & cert
            elif st == "flagged":
                m = m & ~cert
            pool = rows & (wb == b)
            src = m if m.sum() >= 60 else pool
            hi_w = None if math.isinf(W_EDGES[b + 1]) else W_EDGES[b + 1]
            cell = {"w_lo": W_EDGES[b], "w_hi": hi_w, "state": st, "n": int(m.sum())}
            if signed:
                a2 = (1 - level) / 2
                cell["q_hi"] = float(_cq(e[src], 1 - a2))
                cell["q_lo"] = float(-_cq(-e[src], 1 - a2))
            else:
                cell["q"] = float(G.conformal_quantile(np.abs(e[src]), 1 - level))
            cells.append(cell)
    return {"level": level, "scale": kind, "scale_floor_mm": 0.01, "cells": cells, "by_state": by_state, "signed": signed}


def _cq(v, level):
    """Upper conformal quantile of v at `level` (ceil((n+1) level)-th smallest)."""
    s = np.sort(np.asarray(v, float))
    n = len(s)
    k = int(math.ceil((n + 1) * level))
    return math.inf if (n == 0 or k > n) else float(s[k - 1])


def interval_bounds(D, pred, cert, I):
    """Per-row (lo, hi) of the conformal interval for the TRUE width, same logic as gate.interval_for."""
    scale = interval_scale(D, pred, I["scale"])
    wb = w_bin(D["w"])
    lo = np.full(len(pred), np.nan)
    hi = np.full(len(pred), np.nan)
    for c in I["cells"]:
        b = int(np.searchsorted(W_EDGES, c["w_lo"], side="right") - 1)
        m = wb == b
        if c["state"] == "certified":
            m = m & cert
        elif c["state"] == "flagged":
            m = m & ~cert
        if "q_lo" in c:
            lo[m] = D["w"][m] - scale[m] * c["q_hi"]
            hi[m] = D["w"][m] - scale[m] * c["q_lo"]
        else:
            lo[m] = D["w"][m] - c["q"] * scale[m]
            hi[m] = D["w"][m] + c["q"] * scale[m]
    return np.minimum(lo, D["w"]), np.maximum(hi, D["w"])


# ----------------------------------------------------------------------------- pipeline

def fit_pipeline(D, groups, alphas=ALPHAS, k=5, seed=0, kind=None, interval_variants=(("learned", True, False),),
                 interval_alpha=0.05, qa=None):
    """Fit everything on the rows of `groups`.  interval_variants: tuples (scale kind, by_state, signed), all fitted on
    the same out-of-fold predictions; `intervals` is a dict keyed by that tuple."""
    rows = np.isin(D["group"], list(groups))
    qa = D["qa"] if qa is None else qa
    pred_oof = oof_predict(D, groups, k=k, seed=seed, kind=kind)
    levels = {}
    for a, (th, ncap, emp) in crc_thetas(D["cap"][rows], pred_oof[rows], qa[rows], D["wrong"][rows], list(alphas)).items():
        levels[f"{a:g}"] = {"alpha": a, "theta": th, "n_calibration_captures": ncap, "empirical_risk": emp}
    model = fit_model(D["X"][rows], D["y"][rows], kind, feats=D.get("feats"))
    th_i = levels[f"{interval_alpha:g}"]["theta"]
    cert_oof = qa & (pred_oof <= th_i)
    p0 = np.where(rows, pred_oof, 0.0)
    intervals = {v: fit_intervals(D, rows, p0, cert_oof, v[0], v[1], v[2], v[3] if len(v) > 3 else 0.9) for v in interval_variants}
    cm = rows & cert_oof
    ref = np.median(D["X"][cm], axis=0) if cm.sum() else np.median(D["X"][rows], axis=0)
    return {"model": model, "levels": levels, "intervals": intervals, "ref": ref, "oof": pred_oof, "qa": qa,
            "rows": rows}
