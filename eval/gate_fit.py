"""Fit, validate and write the certification gate.

Reads eval/results/gate_calibration_features.parquet (built by gate_make_dataset.py) and writes
  src/prohori/gate_params.json            deployed parameters (score model, CRC thresholds, conformal intervals, QA)
  eval/results/gate_report.md             all tables
  eval/results/gate_summary.json          machine-readable headline numbers (read by run_panel_photos.py)
  eval/results/gate_risk_coverage.png     risk-coverage curves (held-out)
  eval/results/gate_interval_coverage.png coverage per true-width bin, before / after

Usage: python eval/gate_fit.py [--reps 100] [--workers 6] [--quick] [--no-write] [--features file.parquet] [--stage DIR]
  --stage DIR writes gate_params.json, gate_report.md, gate_summary.json and the figures into DIR instead of the repository
  (used to fit on a candidate dataset, or on the legacy one, without touching the deployed gate).
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")  # boosting inside worker processes; avoids thread thrash

import argparse
import itertools
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "src"))
import gate_lib as L  # noqa: E402
from prohori import gate as G  # noqa: E402

RES = ROOT / "eval" / "results"
SEED = 11
TEST_GROUPS_N = 6
TRUE_W = [0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
LEVELS = (0.90, 0.92, 0.94)
VARIANTS = [(k, s, False, lv) for k in ("heuristic", "heuristic_res", "learned") for s in (False, True) for lv in LEVELS] +            [("learned", True, True, lv) for lv in LEVELS]


def pct(x, nd=1):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{nd}f}%"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def vname(v):
    k, s, g, lv = v
    return f"{k} scale, {'signed' if g else 'symmetric'}, by width bin{' x state' if s else ''}, nominal {lv:.2f}"


# ----------------------------------------------------------------------------- risk-coverage

def risk_coverage(pred, qa, wrong):
    """Order rows by predicted difficulty (QA-failed rows last); cumulative certified fraction / risks."""
    key = np.where(qa, pred, np.inf)
    o = np.argsort(key, kind="stable")
    n_ok = int(qa.sum())
    cw = np.cumsum(wrong[o])
    k = np.arange(1, len(o) + 1)
    return (k / len(o))[:n_ok], (cw / k)[:n_ok], (cw / len(o))[:n_ok]


def aurc(cond):
    return float(np.mean(cond)) if len(cond) else math.nan


def cov_at(cov, risk, target):
    ok = np.nonzero(risk <= target)[0]
    return float(cov[ok.max()]) if len(ok) else 0.0


def summarize(vals):
    v = np.array([x for x in vals if not (isinstance(x, float) and math.isnan(x))], float)
    return (np.nan, np.nan, np.nan) if not len(v) else (float(v.mean()), float(np.percentile(v, 5)), float(np.percentile(v, 95)))


def fmt3(t, f=pct):
    return f"{f(t[0])} [{f(t[1])}, {f(t[2])}]"


# ----------------------------------------------------------------------------- worker jobs

_D: dict = {}


def _init(D):
    global _D
    _D = D
    os.environ["OMP_NUM_THREADS"] = "1"


def interval_cover(D, mask, cert, lo, hi):
    inside = (D["true"] >= lo) & (D["true"] <= hi)
    half = 0.5 * (hi - lo)
    d = {"all": float(inside[mask].mean()), "cert": float(inside[mask & cert].mean()) if (mask & cert).any() else math.nan,
         "flag": float(inside[mask & ~cert].mean()) if (mask & ~cert).any() else math.nan,
         "half_cert_med": float(np.median(half[mask & cert])) if (mask & cert).any() else math.nan,
         "half_all_med": float(np.median(half[mask]))}
    for w in TRUE_W:
        m = mask & np.isclose(D["true"], w)
        d[f"w{w}"] = float(inside[m].mean()) if m.any() else math.nan
    lt, ge = mask & (D["true"] < 0.5), mask & (D["true"] >= 0.5)
    d["lt0.5"] = float(inside[lt].mean()) if lt.any() else math.nan
    d["ge0.5"] = float(inside[ge].mean()) if ge.any() else math.nan
    return d


def split_job(args):
    """One grouped split: fit on the training groups, evaluate every level and interval variant on the held-out groups."""
    rep, te_groups, groups, seed, level_for_state = args
    D = _D
    tr = [g for g in groups if g not in te_groups]
    P = L.fit_pipeline(D, tr, seed=seed, interval_variants=VARIANTS, interval_alpha=level_for_state)
    te = np.isin(D["group"], te_groups)
    pred = L.predict_many(P["model"], D["X"])
    out = {"rep": rep, "test_groups": list(te_groups), "levels": {}, "cover": {}}
    Dalt = dict(D, wrong=D["wrong_alt"])
    out["alt"] = {}
    for k, lv in P["levels"].items():
        out["levels"][k] = L.eval_gate(D, te, pred, D["qa"], lv["theta"])
        out["alt"][k] = L.eval_gate(Dalt, te, pred, D["qa"], lv["theta"])
    cert = D["qa"] & (pred <= P["levels"][f"{level_for_state:g}"]["theta"])
    for v, I in P["intervals"].items():
        lo, hi = L.interval_bounds(D, pred, cert, I)
        out["cover"][v] = interval_cover(D, te, cert, lo, hi)
    return out


def logo_job(args):
    """Leave one source photo out; returns predictions/certification/intervals for the held-out rows."""
    g, groups, theta_alpha, variant, seed = args
    D = _D
    tr = [x for x in groups if x != g]
    P = L.fit_pipeline(D, tr, seed=seed, interval_variants=[variant], interval_alpha=theta_alpha)
    pred = L.predict_many(P["model"], D["X"])
    th = P["levels"][f"{theta_alpha:g}"]["theta"]
    cert = D["qa"] & (pred <= th)
    lo, hi = L.interval_bounds(D, pred, cert, P["intervals"][variant])
    m = D["group"] == g
    return g, np.where(m)[0], pred[m], cert[m], lo[m], hi[m]


# ----------------------------------------------------------------------------- model families (pooled OOF)

def grouped_oof(D, groups, k, seed, fn):
    rng = np.random.default_rng(seed)
    gl = np.array(sorted(groups))
    rng.shuffle(gl)
    pred = np.full(len(D["y"]), np.nan)
    for f in np.array_split(gl, k):
        te = np.isin(D["group"], f)
        pred[te] = fn(D["X"][~te], D["y"][~te], D["wrong"][~te])(D["X"][te])
    return pred


def families():
    from scipy.optimize import minimize
    from sklearn.ensemble import HistGradientBoostingRegressor

    def mk(model_kind, **kw):
        def f(X, y, w):
            m = L.fit_model(X, y, model_kind, **kw)
            return lambda Z: L.predict_many(m, Z)
        return f

    def gbm_free(X, y, w):
        m = HistGradientBoostingRegressor(random_state=0, **L.GBM_KW).fit(X, y)
        return m.predict

    def logit(X, y, w):
        lo, hi = np.percentile(X, 0.5, axis=0), np.percentile(X, 99.5, axis=0)
        Z = np.clip(X, lo, hi)
        mu, sd = Z.mean(0), np.where(Z.std(0) < 1e-9, 1, Z.std(0))
        U = (Z - mu) / sd
        yy = w.astype(float)
        bounds = [(None, None)] + [((None, None) if f in L.FREE_SIGN else (0, None)) for f in G.FEATURES]

        def nll(t):
            s = t[0] + U @ t[1:]
            return float(np.mean(np.logaddexp(0, s) - yy * s) + 0.5 * 3.0 / len(yy) * np.sum(t[1:] ** 2))

        def gr(t):
            s = t[0] + U @ t[1:]
            pr = 1 / (1 + np.exp(-s))
            return np.r_[np.mean(pr - yy), U.T @ (pr - yy) / len(yy) + 3.0 / len(yy) * t[1:]]
        t = minimize(nll, np.zeros(U.shape[1] + 1), jac=gr, bounds=bounds, method="L-BFGS-B").x
        return lambda Z: t[0] + ((np.clip(Z, lo, hi) - mu) / sd) @ t[1:]

    return {"monotone gradient boosting (depth 3, 100 trees) - deployed": mk("gbm"),
            "unconstrained gradient boosting (reference)": gbm_free,
            "sign-constrained ridge on log(err/tol)": mk("linear", ridge=3.0),
            "sign-constrained logistic on 'wrong'": logit}


# ----------------------------------------------------------------------------- operating thresholds

def operating_thresholds(model, theta, ref, refs_by_w):
    """Single-feature thresholds: `ref` = a good-condition design vector (best decile of the calibration rows); for the
    width-dependent px/mm requirement, `refs_by_w[w]` = the good-condition vector of cracks of that width."""
    idx = {f: i for i, f in enumerate(G.FEATURES)}
    Pm = {"model": model}

    def pred_with(r0, w=None, **kw):
        x = np.asarray(r0, float).copy()
        if w is not None:
            x[idx["log_w"]] = math.log(w)
        for k, v in kw.items():
            x[idx[k]] = v
        return G.predict(x, Pm)

    def solve(fn, lo, hi):
        a, b = fn(lo) <= theta, fn(hi) <= theta
        if a == b:
            return "always passes" if a else "never passes"
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if (fn(mid) <= theta) == a:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def ppm_terms(p, w):
        return {"log_ppm_inv": -math.log(p), "log_ures": math.log(G.u_res_mm(p, w) / float(G.tolerance_mm(w)))}
    wref = math.exp(ref[idx["log_w"]])
    out = {"min_corners": solve(lambda c: pred_with(ref, corners_missing=G.CORNERS_TOTAL - c), 4, 24),
           "min_px_per_mm": solve(lambda p: pred_with(ref, **ppm_terms(p, wref)), 3.0, 30.0),
           "min_blur_var": solve(lambda v: pred_with(ref, log_blur_inv=-math.log(v)), 1.0, 3000.0),
           "max_blur_sigma_px": solve(lambda s: pred_with(ref, log_sigma_px=math.log(s)), 0.2, 10.0),
           "max_obliquity_deg": solve(lambda d: pred_with(ref, obliquity=d / 45.0), 0.0, 80.0),
           "max_glare_frac": solve(lambda g: pred_with(ref, glare=g), 0.0, 0.5),
           "max_noise_sigma": solve(lambda s: pred_with(ref, noise=s), 0.0, 20.0)}
    out = {k: (v if isinstance(v, str) else round(float(v), 3)) for k, v in out.items()}
    req = {}
    for w in TRUE_W:
        v = solve(lambda p: pred_with(refs_by_w[w], w=w, **ppm_terms(p, w)), 3.0, 30.0)
        req[f"{w:g}"] = v if isinstance(v, str) else round(float(v), 2)
    return out, req


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--features", default=None)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--deploy", action="store_true", help="write src/prohori/gate_params.json and eval/results/gate_* (otherwise --stage DIR is required)")
    a = ap.parse_args()
    if not a.stage and not a.deploy and not a.no_write:
        sys.exit("refusing to overwrite the deployed gate: pass --stage DIR (candidate fit) or --deploy")
    out_res = Path(a.stage) if a.stage else RES
    out_params = (Path(a.stage) / "gate_params.json") if a.stage else ROOT / "src" / "prohori" / "gate_params.json"
    out_res.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    df = L.load_rows(a.features)
    D = L.prepare(df)
    D["qa"] = L.qa_pass(D["raws"])
    est_name = "legacy" if a.features and "legacy" in str(a.features) else "shipped (measure.CFG)"
    alt = L.alt_truth(df)  # secondary reference: toner-corrected width; the fitted rule is not changed by it
    D["wrong_alt"], D["err_alt"], D["true_alt"] = alt["wrong_corr"], alt["err_corr"], alt["true_corr"]
    groups = sorted(set(D["group"]))
    n_rows, n_caps = len(df), df["cap"].nunique()
    wr = D["wrong"]
    print(f"{n_rows} crack rows, {n_caps} captures, {len(groups)} groups", flush=True)
    rep, summary = [], {}
    Dl = L.light(D)
    pool = mp.Pool(a.workers, initializer=_init, initargs=(Dl,))
    reps = 12 if a.quick else a.reps

    # ---------------------------------------------------------------- 0. dataset
    rep += ["# Gate calibration report\n",
            f"Generated by `eval/gate_fit.py` from `{a.features or 'eval/results/gate_calibration_features.parquet'}` "
            f"(width estimator of the dataset: **{est_name}**).\n", "## 0. Calibration dataset\n",
            f"* source photos with a detectable board (groups; burst frames merged): **{len(groups)}** (of 29 photos; the others "
            f"never yield a board, so nothing can be derived from them)",
            f"* derived captures with >= 1 measured crack: **{n_caps}**; crack measurements: **{n_rows}**; wrong "
            f"(|err| > tol): {pct(wr.mean())}",
            "* degradations: tilt, downscale, Gaussian/motion blur, specular glare, sensor noise, JPEG (`eval/gate_degrade.py`, "
            "distribution `DIST`); every variant keeps the printed true widths.\n"]
    rep.append(md_table(["subset", "crack rows", "wrong rate", "MAE mm"],
                        [[nm, int(m.sum()), pct(wr[m].mean()), f"{np.mean(np.abs(D['err'][m])):.3f}"]
                         for nm, m in [("original photos (v0)", D["v"] == 0), ("derived (v>0)", D["v"] > 0)]]) + "\n")

    # krkCMd resolution table consistency
    try:
        km = pd.read_csv(ROOT / "eval" / "results" / "krkcmd_metrics.csv")
        a_ = km[(km.calib == "added") & (km.psf_sigma_px == 0.75) & (km.estimator == "loc_fwhm")]
        bins = ["0.0-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.5", "0.5-0.9"]
        tab = np.array([[float(a_[(a_.bin == b) & (a_.ppm == p)].mae_mm.iloc[0]) for p in G.U_RES_PPM] for b in bins])
        dmax = float(np.abs(tab - np.array(G.U_RES_MAE_MM)).max())
        rep.append(f"u_res table (resolution-added MAE from `krkcmd_metrics.csv`, FWHM, PSF 0.75 px) matches `gate.U_RES_MAE_MM` "
                   f"to {dmax * 1000:.1f} um.\n")
        assert dmax < 0.0011, dmax
    except FileNotFoundError:
        rep.append("krkcmd_metrics.csv not found: u_res table not re-verified.\n")

    # ---------------------------------------------------------------- 1. definition
    rep += ["## 1. Risk definition\n",
            "* **wrong**: |ŵ − w| > max(0.05 mm, 10 % · w) with w the printed (nominal) width.  0.05 mm is the resolution of the "
            "microscope reference in Hassouna et al. (Sci. Rep. 2026) and the tau of METRICS.md; 10 % is tighter than the mean "
            "relative error of both published pipelines (12.7 %, Hassouna; 14.4 %, Deng).  The nominal width is the reference "
            "(toner spread on the print is not corrected), so errors below ~0.03 mm should not be over-read.  "
            "**Width convention:** the panel truth is the full printed stroke width; krkCMd's `MANwidth` is the operator's "
            "black-core width, so the krkCMd-derived `u_res` term is used only as a *resolution-added* error (estimator at "
            "px/mm vs the same estimator at native), never as an accuracy against the panel truth.",
            "* **certified**: mask QA passes **and** predicted log(|err|/tol) <= theta.",
            "* **risk** (the CRC loss, Angelopoulos et al. 2024): per capture i, L_i(λ) = (1/m_i) Σ_j 1[crack j certified at λ] · "
            "1[crack j wrong], m_i = measured cracks in the capture (a fixed denominator, so L_i is non-increasing in "
            "λ = −theta and bounded by B = 1).  Captures with no measured crack have L = 0 and are left out of the calibration "
            "set (conservative).",
            "* also reported: pooled joint rate (certified-and-wrong / all measured) and the conditional rate "
            "P(wrong | certified) = certified-and-wrong / certified, which is what a user feels.\n"]

    # ---------------------------------------------------------------- 2. mask QA
    rep.append("## 2. Mask QA (Deng et al., CACAIE 2026)\n")
    qa_rows = []
    for name, fn in [("mask_blowup: EDT max / median along skeleton > 2.0", lambda r: r["edt_ratio"] > 2.0),
                     ("mask_holes: >= 1 interior hole (>= 0.02 mm2)", lambda r: r["n_holes"] > 0),
                     ("mask_fragmented: frag_frac > 0.25 or path_cover < 0.6",
                      lambda r: r["frag_frac"] > 0.25 or r["path_cover"] < 0.6)]:
        m = np.array([fn(r) for r in D["raws"]])
        qa_rows.append([name, pct(m.mean(), 2), pct(wr[m].mean()) if m.any() else "n/a", pct(wr[~m].mean())])
    m = ~D["qa"]
    qa_rows.append(["any QA reason (rejected)", pct(m.mean(), 2), pct(wr[m].mean()) if m.any() else "n/a", pct(wr[~m].mean())])
    rep.append(md_table(["rule", "rejects", "wrong rate among rejected", "wrong rate among accepted"], qa_rows) + "\n")
    sw = []
    for thr in (1.5, 2.0, 2.5, 3.0):
        m = np.array([r["edt_ratio"] > thr for r in D["raws"]])
        sw.append([f"{thr:g}", pct(m.mean(), 2), pct(wr[m].mean()) if m.any() else "n/a"])
    rep.append("EDT-ratio threshold sensitivity (paper value 2.0, not tuned):\n")
    rep.append(md_table(["edt_ratio >", "rejects", "wrong among rejected"], sw) + "\n")
    summary["qa"] = qa_rows

    # ---------------------------------------------------------------- 3. score model comparison
    rep.append("## 3. Score model comparison (pooled out-of-fold, 7-fold grouped CV)\n")
    fam = families()
    allpred = {n: grouped_oof(D, groups, 7, 0, fn) for n, fn in fam.items()}
    sig_px = np.array([r["sigma_px"] for r in D["raws"]])
    allpred["ranking by blur sigma in px alone"] = sig_px
    allpred["ranking by px/mm alone (low = bad)"] = -D["ppm"]
    allpred["ranking by blur_var alone (low = bad)"] = -np.array([r["blur_var"] for r in D["raws"]])
    cv_rows = []
    for name, p in allpred.items():
        cov, cond, joint = risk_coverage(p, D["qa"], wr)
        cv_rows.append([name, f"{aurc(cond):.4f}", pct(cov_at(cov, cond, 0.05)), pct(cov_at(cov, joint, 0.05))])
    leg = np.array([(r["corners"] >= 8 and r["ppm"] >= 8 and r["blur_var"] >= 150 and r["obliquity_deg"] <= 45 and
                     r["glare_frac"] <= 0.05) for r in D["raws"]]) & D["qa"]
    cv_rows.append(["legacy hand-set gate (one point)", "n/a",
                    f"{pct(leg.mean())} certified, cond. wrong {pct(wr[leg].mean())}", f"joint {pct((leg & wr).mean())}"])
    rep.append(md_table(["score", "AURC (conditional risk)", "certified fraction at cond. risk <= 5 %",
                         "certified fraction at joint risk <= 5 %"], cv_rows) + "\n")
    rep.append("Oracle-threshold comparison on pooled out-of-fold predictions (optimistic but comparable across rows); lower AURC "
               "is better.  The monotone-constrained boosted trees are deployed: the additive models (linear / logistic) leave a "
               "large gap, i.e. the error depends on interactions (resolution x blur x width) that a sum of per-feature effects "
               "cannot express, and monotonicity keeps every feature's effect physically sane.\n")
    summary["family_cv"] = {r[0]: r[1:] for r in cv_rows}

    # ---------------------------------------------------------------- 4/5. repeated grouped splits (meta-calibration)
    rng = np.random.default_rng(SEED)
    jobs = []
    for r in range(reps):
        te_g = sorted(rng.choice(groups, TEST_GROUPS_N, replace=False))
        jobs.append((r, te_g, groups, 100 + r, 0.05))
    print(f"repeated splits: {reps} jobs", flush=True)
    R = pool.map(split_job, jobs, chunksize=1)
    print(f"  done {time.time() - t0:.0f}s", flush=True)
    keys = [f"{a_:g}" for a_ in L.ALPHAS]
    rows5 = []
    for k in keys:
        crc = summarize([r["levels"][k]["joint_risk_capture"] for r in R])
        rows5.append([k, fmt3(crc, lambda x: pct(x, 2)), fmt3(summarize([r["levels"][k]["joint_risk_pooled"] for r in R]), lambda x: pct(x, 2)),
                      fmt3(summarize([r["levels"][k]["cond_risk"] for r in R])), fmt3(summarize([r["levels"][k]["cert_rate"] for r in R])),
                      pct(float(np.mean([r["levels"][k]["joint_risk_capture"] <= float(k) for r in R])), 0)])
    rep.append(f"## 4. Held-out risk of the CRC gate: {reps} random group splits ({TEST_GROUPS_N} test source photos each; mean [5th, 95th percentile])\n")
    rep.append("`alpha_cal` is the level handed to CRC on the calibration groups.  CRC guarantees the held-out risk only for "
               "exchangeable captures; here whole source photos are held out, so the realised held-out risk can sit above "
               "alpha_cal.  The deployed default level is therefore **meta-calibrated**: the largest alpha_cal whose mean held-out "
               "risk over these splits is <= 5 %.\n")
    rep.append(md_table(["alpha_cal", "held-out risk (CRC loss)", "pooled joint", "P(wrong|cert)", "cracks certified",
                         "splits with risk <= alpha_cal"], rows5) + "\n")
    mean_risk = {k: float(np.mean([r["levels"][k]["joint_risk_capture"] for r in R])) for k in keys}
    mean_cond = {k: float(np.nanmean([r["levels"][k]["cond_risk"] for r in R])) for k in keys}
    ok_joint = [k for k in keys if mean_risk[k] <= 0.05]
    ok_cond = [k for k in keys if mean_cond[k] <= 0.05]
    default_level = ok_joint[-1] if ok_joint else keys[0]
    strict_level = ok_cond[-1] if ok_cond else keys[0]
    rep.append(f"Selected: **default level alpha_cal = {default_level}** (mean held-out risk {pct(mean_risk[default_level], 2)}, "
               f"P(wrong | certified) {pct(mean_cond[default_level])}); **strict level alpha_cal = {strict_level}** (mean held-out "
               f"P(wrong | certified) {pct(mean_cond[strict_level])}, cracks certified "
               f"{pct(float(np.mean([r['levels'][strict_level]['cert_rate'] for r in R])))}).\n")
    summary["repeated"] = {k: row[1:] for k, row in zip(keys, rows5)}
    summary["default_level"], summary["strict_level"] = default_level, strict_level
    rows5a = [[k, fmt3(summarize([r["alt"][k]["joint_risk_capture"] for r in R]), lambda x: pct(x, 2)),
               fmt3(summarize([r["alt"][k]["cond_risk"] for r in R])), fmt3(summarize([r["alt"][k]["cert_rate"] for r in R]))] for k in keys]
    rep.append("### Secondary reference: toner-corrected width (nominal + 2 x 0.0137 mm)\n")
    rep.append("The same fitted gates and the same certified sets as the table above, scored against the toner-corrected width "
               "(`gate_lib.alt_truth`; same tolerance rule, with w the corrected width).  The fitted rule is not changed by it.\n")
    rep.append(md_table(["alpha_cal", "held-out risk (CRC loss)", "P(wrong|cert)", "cracks certified"], rows5a) + "\n")
    summary["repeated_alt"] = {k: row[1:] for k, row in zip(keys, rows5a)}

    # fixed split
    r0 = np.random.default_rng(SEED + 1)
    test_groups = sorted(r0.choice(groups, TEST_GROUPS_N, replace=False))
    fit_groups = [g for g in groups if g not in test_groups]
    Pfix = L.fit_pipeline(D, fit_groups, seed=1, interval_variants=[("learned", True, False, 0.9)])
    te = np.isin(D["group"], test_groups)
    pred_fix = L.predict_many(Pfix["model"], D["X"])
    rep.append(f"### One fixed held-out split (fit on {len(fit_groups)} source photos, test on {len(test_groups)}: "
               f"{', '.join(g[-6:] for g in test_groups)})\n")
    rows4 = []
    for k in keys:
        lv = Pfix["levels"][k]
        e = L.eval_gate(D, te, pred_fix, D["qa"], lv["theta"])
        eo = L.eval_gate(D, te & (D["v"] == 0), pred_fix, D["qa"], lv["theta"])
        rows4.append([k, f"{lv['theta']:.3f}", pct(lv["empirical_risk"], 2), pct(e["joint_risk_capture"], 2), pct(e["cond_risk"], 1),
                      pct(e["cert_rate"], 1), pct(e["capture_cert_rate"], 1), pct(eo["cert_rate"], 1)])
    rep.append(md_table(["alpha_cal", "theta", "cal. risk (OOF)", "held-out risk (CRC loss)", "held-out P(wrong|cert)", "cracks certified",
                         "captures with >= 1 certified", "cracks certified, original photos only"], rows4) + "\n")
    summary["fixed_split"] = {"test_groups": test_groups, "rows": {r[0]: r[1:] for r in rows4}}

    # block CV
    blocks = np.array_split(groups, 4)
    rows_b = []
    for b in blocks:
        tr_g = [g for g in groups if g not in b]
        Pb = L.fit_pipeline(D, tr_g, seed=2, interval_variants=[("learned", True, False, 0.9)])
        pb = L.predict_many(Pb["model"], D["X"])
        tb = np.isin(D["group"], b)
        e = L.eval_gate(D, tb, pb, D["qa"], Pb["levels"][default_level]["theta"])
        rows_b.append([f"{b[0][-6:]}..{b[-1][-6:]}", len(b), pct(e["joint_risk_capture"], 2), pct(e["cond_risk"], 1), pct(e["cert_rate"], 1)])
    rep.append(f"Time-contiguous blocks (harder: neighbouring photos share panel, light and pose), alpha_cal = {default_level}:\n")
    rep.append(md_table(["block of photos", "groups", "held-out risk", "P(wrong|cert)", "cracks certified"], rows_b) + "\n")
    summary["blocks"] = rows_b

    # ---------------------------------------------------------------- 6. intervals
    rep.append("## 5. Conformal 90 % width interval\n")
    inside_old = np.abs(D["err"]) <= 1.645 * D["u"]
    inside_old1 = np.abs(D["err"]) <= D["u"]
    vrows = []
    score = {}
    for v in VARIANTS:
        cv = [r["cover"][v] for r in R]
        worst = np.mean([min(c[f"w{w}"] for w in TRUE_W if not math.isnan(c[f"w{w}"])) for c in cv])
        allc = np.mean([c["all"] for c in cv])
        half = np.nanmean([c["half_cert_med"] for c in cv])
        score[v] = (allc >= 0.90, worst - 3.0 * (allc - 0.90) - 0.5 * max(0.0, half - 0.15))
        vrows.append([vname(v), fmt3(summarize([c["all"] for c in cv])), pct(summarize([c["cert"] for c in cv])[0]),
                      pct(worst), f"{half:.3f}"])
    rep.append(md_table(["interval", "coverage, all rows [5,95]", "coverage, certified", "mean of worst per-specimen coverage",
                         "median half-width, certified (mm)"], vrows) + "\n")
    best = max(score, key=score.get)
    rep.append(f"Selected for deployment: **{vname(best)}**: among variants whose mean held-out coverage is >= 0.90, the best "
               "mean worst-specimen coverage minus 3 x the over-coverage (overall coverage - 0.90) minus 0.5 x the median certified half-width above 0.15 mm.  The nominal level is "
               "raised above 0.90 where needed because whole source photos are held out (group shift), the same meta-calibration "
               "as the risk level.\n")
    summary["interval_selected"] = list(best)
    Rsel = [r["cover"][best] for r in R]
    cov_rows, cov_sel = [], {}
    for w in TRUE_W:
        m_all = np.isclose(D["true"], w)
        after = np.nanmean([c[f"w{w}"] for c in Rsel])
        cov_rows.append([f"{w:g}", int(m_all.sum()), pct(float(inside_old1[m_all].mean())), pct(float(inside_old[m_all].mean())), pct(after)])
        cov_sel[w] = (float(inside_old1[m_all].mean()), float(inside_old[m_all].mean()), float(after))
    lt = D["true"] < 0.5
    cov_rows.append(["< 0.5 mm", int(lt.sum()), pct(float(inside_old1[lt].mean())), pct(float(inside_old[lt].mean())), pct(np.nanmean([c["lt0.5"] for c in Rsel]))])
    cov_rows.append([">= 0.5 mm", int((~lt).sum()), pct(float(inside_old1[~lt].mean())), pct(float(inside_old[~lt].mean())), pct(np.nanmean([c["ge0.5"] for c in Rsel]))])
    cov_rows.append(["all", len(lt), pct(float(inside_old1.mean())), pct(float(inside_old.mean())), pct(np.nanmean([c["all"] for c in Rsel]))])
    rep.append("Coverage per true-width bin on **held-out groups** (after = mean over the random group splits; before = the old "
               "heuristic `uncertainty_mm`, which has no fitting, so every row is held-out for it): the old model as a ±1σ band "
               "(its nominal 68 %) and as a ±1.645σ band (nominal 90 %).\n")
    rep.append(md_table(["true width mm", "n rows", "before: ±1σ", "before: ±1.645σ (nominal 90 %)", "after: conformal 90 %"], cov_rows) + "\n")
    cc = np.nanmean([c["cert"] for c in Rsel])
    rep.append(f"Held-out coverage among **certified** rows: {pct(cc)}; median interval half-width among certified "
               f"{np.nanmean([c['half_cert_med'] for c in Rsel]):.3f} mm.\n")
    summary["coverage_per_bin"] = {str(w): cov_sel[w] for w in TRUE_W}
    summary["coverage_overall"] = [float(inside_old1.mean()), float(inside_old.mean()), float(np.nanmean([c["all"] for c in Rsel]))]

    # ---------------------------------------------------------------- 7. LOGO
    print("leave-one-group-out", flush=True)
    lj = [(g, groups, float(default_level), best, 300 + i) for i, g in enumerate(groups)]
    LG = pool.map(logo_job, lj, chunksize=1)
    pred_logo = np.full(len(D["y"]), np.nan)
    cert_logo = np.zeros(len(D["y"]), bool)
    lo_logo = np.full(len(D["y"]), np.nan)
    hi_logo = np.full(len(D["y"]), np.nan)
    for g, ix, p_, c_, lo_, hi_ in LG:
        pred_logo[ix], cert_logo[ix], lo_logo[ix], hi_logo[ix] = p_, c_, lo_, hi_
    inside_logo = (D["true"] >= lo_logo) & (D["true"] <= hi_logo)
    v0 = D["v"] == 0
    logo = []
    for name, m in [("original photos (v0)", v0), ("all derived captures", ~v0)]:
        c = cert_logo & m
        logo.append([name, int(m.sum()), pct(c.sum() / m.sum()), pct(float((c & wr).sum() / m.sum()), 2), pct(float((c & wr).sum() / max(c.sum(), 1)), 1),
                     f"{np.mean(np.abs(D['err'][c])):.3f}" if c.any() else "n/a",
                     f"{np.mean(np.abs(D['err'][m & ~cert_logo])):.3f}" if (m & ~cert_logo).any() else "n/a", pct(float(inside_logo[m].mean()))])
    rep.append(f"## 6. Every source photo held out once (leave-one-group-out, alpha_cal = {default_level})\n")
    rep.append(md_table(["subset", "crack rows", "certified", "certified-and-wrong (joint)", "P(wrong|certified)", "MAE certified mm",
                         "MAE not certified mm", "90 % interval coverage"], logo) + "\n")
    wn_rows = []
    for w in TRUE_W:
        m = np.isclose(D["true"], w) & v0
        c = m & cert_logo
        wn_rows.append([f"{w:g}", int(m.sum()), int(c.sum()), int((c & wr).sum())])
    rep.append("Original (undegraded) photos by nominal width, held-out gate: certified count and certified-and-wrong count:\n")
    rep.append(md_table(["width mm", "measured", "certified", "certified & wrong"], wn_rows) + "\n")
    summary["logo"] = logo
    logo_alt = []
    for name, m in [("original photos (v0)", v0), ("all derived captures", ~v0)]:
        c = cert_logo & m
        logo_alt.append([name, pct(float((c & D["wrong_alt"]).sum() / m.sum()), 2), pct(float((c & D["wrong_alt"]).sum() / max(c.sum(), 1)), 1),
                         f"{np.mean(np.abs(D['err_alt'][c])):.3f}" if c.any() else "n/a"])
    rep.append("Same certified sets scored against the toner-corrected width:\n")
    rep.append(md_table(["subset", "certified-and-wrong (joint)", "P(wrong|certified)", "MAE certified mm"], logo_alt) + "\n")
    summary["logo_alt"] = logo_alt

    # ---------------------------------------------------------------- 8. deployed fit
    levels_all = [float(k) for k in keys]
    Pall = L.fit_pipeline(D, groups, alphas=levels_all, seed=3, interval_variants=[best], interval_alpha=float(default_level))
    th_def = Pall["levels"][default_level]["theta"]
    th_str = Pall["levels"][strict_level]["theta"]
    pred_all = L.predict_many(Pall["model"], D["X"])
    ref = Pall["ref"]
    qa_ok = D["qa"]
    good = qa_ok & (pred_all <= np.percentile(pred_all[qa_ok], 10))
    ref_good = np.median(D["X"][good], axis=0)
    refs_w = {}
    for w in TRUE_W:
        mw = qa_ok & np.isclose(D["true"], w)
        gw = mw & (pred_all <= np.percentile(pred_all[mw], 20))
        refs_w[w] = np.median(D["X"][gw], axis=0)
    thr, req = operating_thresholds(Pall["model"], th_def, ref_good, refs_w)
    thr_s, req_s = operating_thresholds(Pall["model"], th_str, ref_good, refs_w)
    rep.append("## 7. What the deployed gate requires\n")
    rep.append(f"Default level (alpha_cal = {default_level}, theta = {th_def:.3f}).  Single-feature operating thresholds, all other "
               "features at a good-condition reference (median of the best decile of the calibration rows); a number is the "
               "value at which the decision flips, otherwise it says whether that feature alone always / never passes:\n")
    rep.append("```\n" + json.dumps(thr) + "\n```\n")
    rep.append("**Required px/mm by crack width** (all other features at the median of the best 20 % of calibration rows of that "
               "width; searched over 3-30 px/mm, the calibrated range; a number = the lowest px/mm at which such a crack can pass, otherwise "
               "whether it always / never passes there) - "
               "the krkCMd-based `u_res` term and the learned width dependence make it width-dependent:\n")
    rep.append(md_table(["width mm"] + [f"{w:g}" for w in TRUE_W], [["default level"] + [req[f"{w:g}"] for w in TRUE_W],
                                                                   ["strict level"] + [req_s[f"{w:g}"] for w in TRUE_W]]) + "\n")
    rep.append("Empirical check on the calibration set: certified fraction and wrong rate by px/mm band and width, default level (in-sample "
               "predictions of the deployed model):\n")
    cert_all = D["qa"] & (pred_all <= th_def)
    bands = [(0, 8), (8, 12), (12, 16), (16, 20), (20, 100)]
    erows = []
    for lo_, hi_ in bands:
        m = (D["ppm"] >= lo_) & (D["ppm"] < hi_)
        for nm, wm in [("< 0.5 mm", D["true"] < 0.5), (">= 0.5 mm", D["true"] >= 0.5)]:
            mm = m & wm
            c = mm & cert_all
            erows.append([f"{lo_}-{hi_}", nm, int(mm.sum()), pct(c.sum() / max(mm.sum(), 1)), pct(float((c & wr).sum() / max(c.sum(), 1)))])
    rep.append(md_table(["px/mm", "width", "rows", "certified", "P(wrong|certified)"], erows) + "\n")
    rep.append("Marginal certification by single observation values (default level, in-sample predictions; all other features vary "
               "freely, so this describes the gate, it is not a per-feature threshold):\n")
    mrows = []
    for nm, vals, edges in [("blur_var (Laplacian variance)", np.array([r["blur_var"] for r in D["raws"]]), [0, 50, 100, 150, 250, 500, 1e9]),
                            ("blur sigma (px)", sig_px, [0, 1, 1.5, 2, 3, 5, 1e9]),
                            ("obliquity (deg)", np.array([r["obliquity_deg"] for r in D["raws"]]), [0, 10, 20, 30, 40, 90]),
                            ("glare fraction", np.array([r["glare_frac"] for r in D["raws"]]), [0, 0.001, 0.01, 0.05, 1.01]),
                            ("noise sigma (grey levels)", np.array([r["noise_sigma"] for r in D["raws"]]), [0, 1, 2, 4, 8, 1e9]),
                            ("corners", np.array([r["corners"] for r in D["raws"]]), [0, 8, 16, 24, 25])]:
        for lo_, hi_ in zip(edges[:-1], edges[1:]):
            m = (vals >= lo_) & (vals < hi_)
            if m.sum() < 30:
                continue
            c = m & cert_all
            mrows.append([nm, f"[{lo_:g}, {hi_:g})", int(m.sum()), pct(c.sum() / m.sum()), pct(float((c & wr).sum() / max(c.sum(), 1)))])
    rep.append(md_table(["observation", "range", "rows", "certified", "P(wrong|certified)"], mrows) + "\n")
    summary["required_ppm"] = {"default": req, "strict": req_s, "thresholds": thr}

    I = Pall["intervals"][best]
    rep.append("Deployed Mondrian cells (conformal quantiles of the normalised error; scale = " + best[0] + "):\n")
    rep.append(md_table(["measured width bin mm", "state", "quantile(s)", "n cal rows"],
                        [[f"{c['w_lo']:g}-" + ("inf" if c["w_hi"] is None else f"{c['w_hi']:g}"), c["state"],
                          (f"{c['q_lo']:.2f} / {c['q_hi']:.2f}" if "q_lo" in c else f"{c['q']:.2f}"), c["n"]] for c in I["cells"]]) + "\n")
    lo_a, hi_a = L.interval_bounds(D, pred_all, cert_all, I)
    mh = float(np.median((0.5 * (hi_a - lo_a))[cert_all]))
    ppm_med = float(np.median(D["ppm"]))
    rep.append(f"Morphological margin (MICCAI 2025 score reduced to the width domain: symmetric dilate/erode radius per edge = "
               f"half-width / 2): median among certified = {mh / 2:.3f} mm = {mh / 2 * ppm_med:.2f} px at the median {ppm_med:.1f} px/mm.\n")
    rep.append("CRC thresholds on all groups: " + ", ".join(f"alpha_cal {k}: theta {v['theta']:.3f} (calibration risk {pct(v['empirical_risk'], 2)})"
                                                            for k, v in Pall["levels"].items()) + "\n")
    rep.append(f"CRC finite-sample slack B/(n+1) with n = {n_caps} derived captures: {1 / (n_caps + 1):.4f}.  The captures are not independent "
               f"(only {len(groups)} source photos): the *group-level* slack would be 1/({len(groups)}+1) = {1 / (len(groups) + 1):.3f}, i.e. a "
               "group-level CRC at alpha = 0.05 is infeasible with this few photos; the grouped held-out experiments above are the empirical check.\n")
    imp = None
    try:
        from sklearn.inspection import permutation_importance
        imp = permutation_importance(Pall["model"]["_sk"], D["X"], D["y"], n_repeats=3, random_state=0, n_jobs=1)
        order = np.argsort(-imp.importances_mean)[:8]
        rep.append("Permutation importance of the deployed model (increase of squared error when a feature is shuffled; top 8): " +
                   ", ".join(f"`{G.FEATURES[i]}` {imp.importances_mean[i]:.3f}" for i in order) + "\n")
    except Exception as e:  # pragma: no cover
        rep.append(f"(permutation importance unavailable: {e})\n")

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if not str(k).startswith("_")}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, float) and math.isinf(o):
            return 1e9 if o > 0 else -1e9
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.integer):
            return int(o)
        return o
    I2 = clean(I)
    I2["target"] = 0.9  # the coverage we claim (the held-out mean is reported); "level" is the nominal calibration level
    for c in I2["cells"]:
        if c["w_hi"] is None:
            c["w_hi"] = 1e9
    params = {
        "version": 2, "created": time.strftime("%Y-%m-%d"),
        "definition": {
            "wrong": "|width_mm - true_width_mm| > max(0.05 mm, 0.10 * true_width_mm)",
            "certified": "mask QA passes AND model prediction <= theta (level default_level)",
            "risk": "CRC loss per capture = mean over its measured cracks of 1[certified]*1[wrong]; E[loss] <= alpha_cal "
                    "(Angelopoulos et al. ICLR 2024); exchangeable unit = capture drawn from gate_degrade.DIST applied to a source "
                    "photo of the printed panel; default_level is meta-calibrated on grouped held-out splits",
            "prediction": "pred ~ log(|err|/tol): monotone-constrained gradient boosted trees on gate.FEATURES",
            "width_convention": "true width = full printed stroke width of the panel (not an operator black-core width)",
        },
        "tolerance": {"abs_mm": G.TOL_ABS_MM, "rel": G.TOL_REL},
        "qa": dict(G.QA_DEFAULT),
        "model": clean(L.serialisable(Pall["model"])),
        "levels": {k: {"alpha": v["alpha"], "theta": v["theta"], "n_calibration_captures": v["n_calibration_captures"],
                       "empirical_risk": v["empirical_risk"],
                       "heldout_mean_risk": mean_risk.get(k), "heldout_mean_cond_risk": mean_cond.get(k)} for k, v in Pall["levels"].items()},
        "default_level": default_level, "strict_level": strict_level,
        "ood": {"hi": [float(v) for v in np.percentile(D["X"], 99.9, axis=0)],
                "note": "design features worse than the 99.9th percentile of the calibration data are out of range: not certified"},
        "reference": {"design": [float(x) for x in ref], "note": "median design vector of certified calibration rows"},
        "interval": I2,
        "agent_thresholds": thr, "required_px_per_mm": {"default": req, "strict": req_s},
        "u_res": {"ppm": G.U_RES_PPM, "w_centres": G.U_RES_W_CENTRES, "mae_mm": G.U_RES_MAE_MM,
                  "source": "krkcmd_metrics.csv, calib=added, estimator loc_fwhm, PSF 0.75 px"},
        "provenance": {"groups": groups, "n_captures": int(n_caps), "n_rows": int(n_rows), "seed": SEED,
                       "degradation_dist": __import__("gate_degrade").DIST},
    }
    params = clean(params)

    # ---------------------------------------------------------------- figures
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    pr = np.where(np.isnan(pred_logo), 99.0, pred_logo)
    curves = {"fitted score (every source photo held out)": (risk_coverage(pr, D["qa"], wr), "#1b6ca8", 2.2),
              "blur sigma in px alone": (risk_coverage(sig_px, D["qa"], wr), "#d98b1f", 1.4),
              "random order": (risk_coverage(np.random.default_rng(0).random(len(pr)), D["qa"], wr), "#999999", 1.0),
              "oracle order (best possible)": (risk_coverage(np.abs(D["err"]) / D["tol"], D["qa"], wr), "#2e8b57", 1.0)}
    for j, (axx, ttl) in enumerate(zip(ax, ["Conditional: P(wrong | certified)", "Joint: certified-and-wrong / all measured (CRC loss)"])):
        for lab, ((cx, cd, jt), col, lw) in curves.items():
            axx.plot(100 * cx, 100 * (cd if j == 0 else jt), label=lab, color=col, lw=lw)
        axx.axhline(5, color="#c0392b", ls="--", lw=1)
        axx.set_xlabel("certified fraction of measured cracks (%)")
        axx.set_ylabel("certified-but-wrong rate (%)")
        axx.set_title(ttl, fontsize=10)
        axx.set_ylim(0, 40 if j == 0 else 25)
        axx.grid(alpha=0.25)
    for k in keys:
        cx = np.mean([r["levels"][k]["cert_rate"] for r in R])
        mk = "D" if k in (default_level, strict_level) else "o"
        ax[0].plot(100 * cx, 100 * mean_cond[k], mk, color="#c0392b", ms=5)
        ax[1].plot(100 * cx, 100 * np.mean([r["levels"][k]["joint_risk_pooled"] for r in R]), mk, color="#c0392b", ms=5)
        if k in (default_level, strict_level):
            ax[1].annotate(("default" if k == default_level else "strict") + f" α={k}", (100 * cx, 100 * np.mean([r["levels"][k]["joint_risk_pooled"] for r in R])),
                           textcoords="offset points", xytext=(6, -12), fontsize=8)
    ax[0].plot([], [], "o", color="#c0392b", label="CRC operating points (held-out groups, mean of splits)")
    ax[0].plot(100 * leg.mean(), 100 * wr[leg].mean(), "s", color="black", label="legacy hand-set gate")
    ax[1].plot(100 * leg.mean(), 100 * (leg & wr).mean(), "s", color="black")
    ax[0].legend(fontsize=7.5, loc="upper left")
    fig.suptitle(f"Prohori gate: risk-coverage on held-out groups ({n_rows} crack measurements, {len(groups)} source photos)", fontsize=10)
    fig.tight_layout()
    if not a.no_write:
        fig.savefig(out_res / "gate_risk_coverage.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    xs = np.arange(len(TRUE_W))
    ax.bar(xs - 0.27, [100 * cov_sel[w][0] for w in TRUE_W], 0.27, label="before ±1σ (nominal 68 %)", color="#bbbbbb")
    ax.bar(xs, [100 * cov_sel[w][1] for w in TRUE_W], 0.27, label="before ±1.645σ (nominal 90 %)", color="#d98b1f")
    ax.bar(xs + 0.27, [100 * cov_sel[w][2] for w in TRUE_W], 0.27, label="after: conformal 90 %", color="#1b6ca8")
    ax.axhline(90, color="#c0392b", ls="--", lw=1)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{w:g}" for w in TRUE_W])
    ax.set_xlabel("true crack width (mm)")
    ax.set_ylabel("held-out coverage (%)")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    if not a.no_write:
        fig.savefig(out_res / "gate_interval_coverage.png", dpi=150)
    plt.close(fig)

    pool.close()
    if not a.no_write:
        out_params.write_text(json.dumps(params, separators=(",", ":")), encoding="utf-8")
        (out_res / "gate_report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
        (out_res / "gate_summary.json").write_text(json.dumps(clean(summary), indent=1, default=str), encoding="utf-8")
        np.save(out_res / "gate_logo_cert.npy", np.vstack([cert_logo, np.nan_to_num(pred_logo, nan=99.0)]))
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
