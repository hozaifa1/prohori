"""Certification gate, mask QA and conformal width intervals.

Numpy-only at run time.  The fitted parameters are in gate_params.json (written by eval/gate_fit.py); without that file
the legacy hand-set thresholds are used, so `measure.analyze` always works.

What a crack measurement carries
--------------------------------
* a numeric feature vector (observation + per-crack quality numbers; `raw_features`).  The LLM never sees pixels
  (Q-Bench, ICLR 2024: multimodal LLMs are weak at recognising distortions) - it sees these numbers;
* a predicted difficulty `pred` = predicted log(|error| / tolerance), a monotone-signed, log-linear model of the
  features (`predict`).  Certified iff (mask QA passes) and (pred <= theta);
* theta is set by Conformal Risk Control (Angelopoulos et al., ICLR 2024; `crc_threshold`) so that the expected
  fraction of crack measurements that are certified AND wrong is <= alpha (default 5 %).  Wrong means
  |error| > max(0.05 mm, 10 % of the true width) (`tolerance_mm`);
* a split-conformal 90 % interval `interval_mm` (`assess`): residual |error| normalised by the learned scale
  tol(w) * exp(pred), Mondrian-calibrated per measured-width bin;
* reason codes saying which part of the observation vector would have to be at its typical certified level for the
  gate to pass (counterfactual attribution), or a mask-QA code.

Reason codes: too_few_corners, low_resolution, blurry, oblique, glare, noisy, low_coverage, unstable_width,
mask_blowup, mask_holes, mask_fragmented, low_confidence (score too low, nothing single to blame).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

PARAMS_PATH = Path(__file__).with_name("gate_params.json")

CORNERS_TOTAL = 24

# Legacy hand-set thresholds (pre-calibration).  Used when gate_params.json is missing.
LEGACY = {"min_corners": 8, "min_px_per_mm": 8.0, "min_blur_var": 150.0, "max_obliquity_deg": 45.0,
          "max_glare_frac": 0.05}

# "wrong" = |error| > max(TOL_ABS_MM, TOL_REL * true width).  0.05 mm is the resolution of the microscope reference in
# Hassouna et al. (Sci. Rep. 2026) and the tau of METRICS.md; 10 % is tighter than the mean relative error of both
# published phone / LiDAR pipelines (12.7 % and 14.4 %).
TOL_ABS_MM = 0.05
TOL_REL = 0.10

# Mask-QA defaults (Deng et al., CACAIE 2026: EDT blow-up > 2x and holes; fragmentation is our addition).
QA_DEFAULT = {"edt_ratio_max": 2.0, "holes_max": 0, "frag_frac_max": 0.25, "path_cover_min": 0.6}

FEATURES = ["corners_missing", "log_ppm_inv", "log_ures", "log_sigma_px", "log_blur_inv", "obliquity", "glare", "sat",
            "noise", "uncov", "spread", "disagree", "dt_dis", "reproj", "qdef", "log_edt", "gt_roi", "log_w"]

# feature -> reason code (counterfactual attribution works on these groups)
REASON_GROUPS = {
    "too_few_corners": ["corners_missing"],
    "low_resolution": ["log_ppm_inv", "log_ures"],
    "blurry": ["log_sigma_px", "log_blur_inv", "qdef"],
    "oblique": ["obliquity"],
    "glare": ["glare", "sat"],
    "noisy": ["noise"],
    "low_coverage": ["uncov"],
    "unstable_width": ["spread", "disagree", "dt_dis", "log_edt", "reproj"],
}

# Resolution-added width error on textured real concrete, MAE in mm, from the krkCMd benchmark (D15,
# eval/results/krkcmd_metrics.csv, calib == "added", estimator loc_fwhm = the arithmetic of measure.py's FWHM, PSF
# sigma 0.75 px): the error of the estimator at px/mm minus nothing - it is the error vs the SAME estimator at native
# resolution on the same profiles.  Rows = operator-width bins (centres below), columns = px/mm.
U_RES_PPM = [8.0, 10.0, 12.0, 15.0, 20.0, 25.0]
U_RES_W_CENTRES = [0.05, 0.15, 0.25, 0.40, 0.70]  # bins 0-0.1, 0.1-0.2, 0.2-0.3, 0.3-0.5, 0.5-0.9 mm
U_RES_MAE_MM = [[0.136, 0.124, 0.113, 0.093, 0.070, 0.058],
                [0.116, 0.100, 0.095, 0.075, 0.060, 0.050],
                [0.088, 0.071, 0.066, 0.050, 0.039, 0.033],
                [0.080, 0.070, 0.066, 0.052, 0.041, 0.033],
                [0.072, 0.076, 0.055, 0.048, 0.034, 0.027]]


def _ures_fit():
    """Per width bin: MAE = a * ppm^-b (log-log least squares), so the table extrapolates smoothly outside 8-25 px/mm."""
    lp = np.log(U_RES_PPM)
    ab = []
    for row in U_RES_MAE_MM:
        b, la = np.polyfit(lp, np.log(row), 1)
        ab.append((la, -b))
    return np.array(ab)


_URES_AB = _ures_fit()


def u_res_mm(ppm, width_mm):
    """Expected resolution-added width error (MAE, mm) at `ppm` px/mm for a crack of `width_mm`, interpolated over width
    (clamped to the benchmark's 0.05-0.7 mm centres: beyond them the edge-localisation error, which does not grow
    with width, is the right extrapolation)."""
    ppm = max(float(ppm), 1e-3)
    w = float(np.clip(width_mm, U_RES_W_CENTRES[0], U_RES_W_CENTRES[-1]))
    la = float(np.interp(w, U_RES_W_CENTRES, _URES_AB[:, 0]))
    b = float(np.interp(w, U_RES_W_CENTRES, _URES_AB[:, 1]))
    return float(math.exp(la - b * math.log(ppm)))


RAW_KEYS = ["corners", "ppm", "blur_var", "blur_sigma_mm", "sigma_px", "obliquity_deg", "glare_frac", "noise_sigma",
            "reproj_px", "width_mm", "coverage", "spread_rel", "disagree_rel", "dt_rel", "q_core", "sat_frac",
            "edt_ratio", "n_holes", "frag_frac", "path_cover", "locator_gt"]


# ----------------------------------------------------------------------------- definitions

def tolerance_mm(width_mm):
    """Tolerance on the true width: max(0.05 mm, 10 % of the width).  Vectorised."""
    return np.maximum(TOL_ABS_MM, TOL_REL * np.asarray(width_mm, float))


def is_wrong(err_mm, true_width_mm):
    return np.abs(np.asarray(err_mm, float)) > tolerance_mm(true_width_mm)


# ----------------------------------------------------------------------------- CRC and conformal quantiles

def crc_threshold(losses: np.ndarray, thresholds: np.ndarray, alpha: float, B: float = 1.0):
    """Conformal Risk Control (Angelopoulos et al., ICLR 2024, Thm 1).

    losses: (n, K) array, losses[i, k] = L_i(thresholds[k]) in [0, B].  Each L_i must be NON-INCREASING in the
    threshold (a stricter gate can only certify fewer measurements).  thresholds must be ascending.
    Returns (index k_hat, threshold lam_hat): the smallest threshold with (n/(n+1)) * Rhat(lam) + B/(n+1) <= alpha,
    or (None, inf) if even the strictest candidate is infeasible (n too small for this alpha)."""
    L = np.asarray(losses, float)
    n = L.shape[0]
    if n == 0:
        return None, math.inf
    R = L.mean(axis=0)
    ok = (n / (n + 1.0)) * R + B / (n + 1.0) <= alpha + 1e-12
    idx = np.nonzero(ok)[0]
    if len(idx) == 0:
        return None, math.inf
    k = int(idx[0])
    return k, float(np.asarray(thresholds)[k])


def conformal_quantile(scores, alpha: float) -> float:
    """Split-conformal quantile: the ceil((n+1)(1-alpha))-th smallest score (inf if n is too small)."""
    s = np.sort(np.asarray(scores, float))
    n = len(s)
    k = int(math.ceil((n + 1) * (1 - alpha)))
    if n == 0 or k > n:
        return math.inf
    return float(s[k - 1])


# ----------------------------------------------------------------------------- features

def raw_features(obs: dict, crack: dict) -> dict:
    """The numbers the gate looks at, for one crack of one capture (all finite floats)."""
    q = crack.get("quality") or {}
    ppm = float(crack.get("px_per_mm") or obs.get("px_per_mm") or 0.0)
    bs = float(obs.get("blur_sigma_mm") or 0.0)
    sig_mm = bs if bs > 0 else 0.2
    rp = obs.get("reproj_px")
    return {
        "corners": float(obs.get("corners", 0)), "ppm": ppm, "blur_var": float(obs.get("blur_var", 0.0)),
        "blur_sigma_mm": sig_mm, "sigma_px": float(q.get("sigma_px", sig_mm * ppm)),
        "obliquity_deg": float(obs.get("obliquity_deg", 0.0)), "glare_frac": float(obs.get("glare_frac", 0.0)),
        "noise_sigma": float(obs.get("noise_sigma", 0.0)), "reproj_px": float(rp) if rp is not None else 0.0,
        "width_mm": float(crack.get("width_mm", 0.0)), "coverage": float(q.get("coverage", 1.0)),
        "spread_rel": float(q.get("spread_rel", 0.0)), "disagree_rel": float(q.get("disagree_rel", 0.0)),
        "dt_rel": float(q.get("dt_rel", 0.0)), "q_core": float(q.get("q_core", 1.0)),
        "sat_frac": float(q.get("sat_frac", 0.0)), "edt_ratio": float(q.get("edt_ratio", 1.0)),
        "n_holes": float(q.get("n_holes", 0)), "frag_frac": float(q.get("frag_frac", 0.0)),
        "path_cover": float(q.get("path_cover", 1.0)), "locator_gt": float(q.get("locator_gt", 0)),
    }


def design(raw: dict) -> dict:
    """Model features, oriented so that larger = worse (except log_w, sign free)."""
    ppm = max(raw["ppm"], 1e-3)
    return {
        "corners_missing": CORNERS_TOTAL - raw["corners"],
        "log_ppm_inv": -math.log(ppm),
        "log_ures": math.log(u_res_mm(ppm, raw["width_mm"]) / float(tolerance_mm(raw["width_mm"]))),
        "log_sigma_px": math.log(max(raw["sigma_px"], 0.05)),
        "log_blur_inv": -math.log(max(raw["blur_var"], 1.0)),
        "obliquity": raw["obliquity_deg"] / 45.0,
        "glare": raw["glare_frac"],
        "sat": raw["sat_frac"],
        "noise": raw["noise_sigma"],
        "uncov": 1.0 - raw["coverage"],
        "spread": raw["spread_rel"],
        "disagree": raw["disagree_rel"],
        "dt_dis": raw["dt_rel"],
        "reproj": raw["reproj_px"],
        "qdef": max(0.0, 1.0 - raw["q_core"]),
        "log_edt": math.log(max(raw["edt_ratio"], 1.0)),
        "gt_roi": raw["locator_gt"],
        "log_w": math.log(max(raw["width_mm"], 0.05)),
    }


def design_vector(raw: dict) -> np.ndarray:
    d = design(raw)
    return np.array([d[k] for k in FEATURES], float)


# ----------------------------------------------------------------------------- parameters

_cache: dict = {}


def load_params(path: Path | str | None = None, reload: bool = False):
    """Fitted parameters dict, or None if gate_params.json is absent / unreadable."""
    key = str(path or PARAMS_PATH)
    if reload or key not in _cache:
        try:
            _cache[key] = json.loads(Path(key).read_text(encoding="utf-8"))
        except Exception:
            _cache[key] = None
    return _cache[key]


def predict(x: np.ndarray, P: dict) -> float:
    """Predicted log(|error| / tolerance) for a design vector.

    model type "gbm": a monotone-constrained gradient-boosted tree ensemble (constant outside the training range, so it
    never extrapolates); type "linear" (default): clipped, standardised linear model."""
    m = P["model"]
    if m.get("type") == "gbm":
        return _gbm_predict(x, m)
    z = np.clip(x, m["lo"], m["hi"])
    u = (z - np.asarray(m["mean"])) / np.asarray(m["std"])
    return float(m["intercept"] + u @ np.asarray(m["coef"]))


_IDX_URES = FEATURES.index("log_ures")


def predict_eff(x: np.ndarray, P: dict, textured: bool = False) -> float:
    """Prediction used for the decision.  On the printed panel it is `predict`.  On an unknown / textured substrate
    (`textured=True`, i.e. analyze(panel_mode=False)) the panel-calibrated error is combined in quadrature with the
    resolution-added error measured on real textured concrete (krkCMd, u_res / tol): the panel data cannot see substrate
    texture, so this is a conservative surrogate, not a CRC-calibrated quantity."""
    p = predict(x, P)
    if not textured:
        return p
    return float(0.5 * math.log(math.exp(2 * p) + math.exp(2 * float(x[_IDX_URES]))))


def _gbm_predict(x, m: dict) -> float:
    out = float(m["base"])
    for t in m["trees"]:
        i = 0
        while not t["leaf"][i]:
            i = t["l"][i] if x[t["f"][i]] <= t["t"][i] else t["r"][i]
        out += t["v"][i]
    return out


def qa_reasons(raw: dict, qa: dict | None = None) -> list[str]:
    """Mask-QA reason codes (Deng et al., CACAIE 2026)."""
    qa = qa or QA_DEFAULT
    r = []
    if raw["edt_ratio"] > qa["edt_ratio_max"]:
        r.append("mask_blowup")
    if raw["n_holes"] > qa["holes_max"]:
        r.append("mask_holes")
    if raw["frag_frac"] > qa["frag_frac_max"] or raw["path_cover"] < qa["path_cover_min"]:
        r.append("mask_fragmented")
    return r


def ood_reasons(x: np.ndarray, P: dict) -> list[str]:
    """Reason codes for design features that are WORSE than anything in the calibration data (beyond its 99.9th
    percentile).  A tree model is constant out there, which would silently reuse the worst seen conditions as evidence; a
    capture outside the calibrated envelope is not certified."""
    hi = (P.get("ood") or {}).get("hi")
    if hi is None:
        return []
    out = []
    code_of = {f: c for c, fs in REASON_GROUPS.items() for f in fs}
    for j, f in enumerate(FEATURES):
        if f == "log_w":
            continue
        if x[j] > hi[j] + 1e-9:
            c = code_of.get(f, "low_confidence")
            if c not in out:
                out.append(c)
    return out


def attribute(x: np.ndarray, P: dict, theta: float, textured: bool = False) -> list[str]:
    """Reasons for a score failure: greedily reset the feature groups that raise the prediction most to their typical
    certified value until the gate would pass.  Returns [] if the gate passes."""
    p0 = predict_eff(x, P, textured)
    if p0 <= theta:
        return []
    ref = np.asarray(P["reference"]["design"], float)
    idx = {k: i for i, k in enumerate(FEATURES)}
    gains = []
    for code, feats in REASON_GROUPS.items():
        xc = x.copy()
        for f in feats:
            xc[idx[f]] = ref[idx[f]]
        g = p0 - predict_eff(xc, P, textured)
        if g > 1e-9:
            gains.append((g, code))
    gains.sort(reverse=True)
    out, xc = [], x.copy()
    for g, code in gains[:3]:
        for f in REASON_GROUPS[code]:
            xc[idx[f]] = ref[idx[f]]
        out.append(code)
        if predict_eff(xc, P, textured) <= theta:
            return out
    return out + ["low_confidence"] if not out else out


def interval_for(width_mm: float, pred: float, u_model: float, state: str, P: dict, c_ppm: float = 1.0,
                 textured: bool = False):
    """(lo, hi, half_width) of the conformal interval for a crack with measured width `width_mm`.

    Cells hold the conformal quantiles of the normalised signed error (err = measured - true) / scale:
    q_lo (5 %) and q_hi (95 %) for a "signed" interval, or a single symmetric q for |err| / scale."""
    I = P["interval"]
    floor = I.get("scale_floor_mm", 0.01)
    kind = I["scale"]
    if kind == "learned":
        scale = max(floor, float(tolerance_mm(width_mm)) * math.exp(pred))
    elif kind == "heuristic":
        scale = max(floor, u_model)
    elif kind == "heuristic_res":
        scale = max(floor, math.hypot(u_model, u_res_mm(c_ppm, width_mm)))
    else:
        scale = 1.0
    if textured:  # add the textured-substrate resolution term (see predict_eff)
        scale = math.hypot(scale, u_res_mm(c_ppm, width_mm))
    cell = None
    for c in I["cells"]:
        if c["w_lo"] <= width_mm < c["w_hi"] and c.get("state", "any") in ("any", state):
            if cell is None or c.get("state", "any") != "any":
                cell = c
    if cell is None:
        cell = I["cells"][-1]
    if "q_lo" in cell:  # signed: true width in [w - scale*q_hi, w - scale*q_lo]
        lo, hi = width_mm - scale * float(cell["q_hi"]), width_mm - scale * float(cell["q_lo"])
    else:
        half = float(cell["q"]) * scale
        lo, hi = width_mm - half, width_mm + half
    if not (math.isfinite(lo) and math.isfinite(hi)):
        h = float(I.get("fallback_half_mm", 1.0))
        lo, hi = width_mm - h, width_mm + h
    lo, hi = min(lo, width_mm), max(hi, width_mm)  # always contains the reported width (only ever widens: coverage unharmed)
    return lo, hi, 0.5 * (hi - lo)


# ----------------------------------------------------------------------------- the gate

def assess(obs: dict, cracks: list[dict], params: dict | None = None, level: str | None = None,
           textured: bool = False) -> dict:
    """Certify each crack, add the per-crack keys, return the capture-level gate dict.

    Adds to every crack: certified (bool), status ("certified" | "flagged"), reasons (list), risk_ratio (predicted
    |error|/tolerance), interval_mm [lo, hi], interval_level, and replaces uncertainty_mm by the interval half-width.
    Capture-level: certified iff at least one crack is certified; its reasons are those of the best-scoring crack."""
    P = params if params is not None else load_params()
    if P is None:
        return _assess_legacy(obs, cracks)
    level = level or P["default_level"]
    lv = P["levels"][level]
    theta = lv["theta"]
    best = None
    for c in cracks:
        raw = raw_features(obs, c)
        x = design_vector(raw)
        pred = predict_eff(x, P, textured)
        qa = qa_reasons(raw, P.get("qa"))
        score_ok = pred <= theta
        ood = ood_reasons(x, P)
        cert = score_ok and not qa and not ood
        reasons = list(qa) + [r for r in ood if r not in qa]
        if not score_ok:
            reasons += [r for r in attribute(x, P, theta, textured) if r not in reasons]
        c["certified"] = bool(cert)
        c["status"] = "certified" if cert else "flagged"
        c["reasons"] = reasons
        c["risk_ratio"] = round(math.exp(pred), 4)
        lo, hi, half = interval_for(raw["width_mm"], pred, c.get("uncertainty_model_mm", 0.0),
                                    "certified" if cert else "flagged", P, raw["ppm"], textured)
        c["u_res_mm"] = round(u_res_mm(raw["ppm"], raw["width_mm"]), 4)
        c["interval_mm"] = [round(lo, 4), round(hi, 4)]
        c["interval_level"] = P["interval"].get("target", P["interval"]["level"])
        c["uncertainty_mm"] = round(half, 4)
        if best is None or pred < best[0]:
            best = (pred, c)
    n_cert = sum(1 for c in cracks if c["certified"])
    g = {"certified": n_cert > 0, "reasons": [], "mode": "crc_textured" if textured else "crc", "alpha": float(lv["alpha"]),
         "level": level,
         "cracks_certified": n_cert, "cracks_total": len(cracks)}
    if cracks and n_cert == 0:
        g["reasons"] = list(best[1]["reasons"])
    g["measurement"] = ("certified" if n_cert else "flagged") if cracks else "unavailable"
    return g


def _assess_legacy(obs: dict, cracks: list[dict]) -> dict:
    T = LEGACY
    reasons = []
    if obs.get("corners", 0) < T["min_corners"]:
        reasons.append("too_few_corners")
    if obs.get("px_per_mm", 0.0) < T["min_px_per_mm"]:
        reasons.append("low_resolution")
    if obs.get("blur_var", 0.0) < T["min_blur_var"]:
        reasons.append("blurry")
    if obs.get("obliquity_deg", 0.0) > T["max_obliquity_deg"]:
        reasons.append("oblique")
    if obs.get("glare_frac", 0.0) > T["max_glare_frac"]:
        reasons.append("glare")
    cert = not reasons and len(cracks) > 0
    for c in cracks:
        c["certified"] = cert
        c["status"] = "certified" if cert else "flagged"
        c["reasons"] = list(reasons)
        u = float(c.get("uncertainty_model_mm", c.get("uncertainty_mm", 0.0)))
        c["interval_mm"] = [round(c["width_mm"] - 1.645 * u, 4), round(c["width_mm"] + 1.645 * u, 4)]
        c["interval_level"] = 0.9
    return {"certified": cert, "reasons": reasons, "mode": "legacy", "cracks_certified": len(cracks) if cert else 0,
            "cracks_total": len(cracks), "measurement": ("certified" if cert else "flagged") if cracks else "unavailable"}
