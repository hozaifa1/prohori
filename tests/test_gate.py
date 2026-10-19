"""Tests for prohori.gate (CRC, conformal quantiles, QA, assess) and the degradation generator."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from prohori import gate as G

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))


# ------------------------------------------------------------------ definitions

def test_tolerance_and_wrong():
    assert G.tolerance_mm(0.3) == pytest.approx(0.05)
    assert G.tolerance_mm(0.5) == pytest.approx(0.05)
    assert G.tolerance_mm(3.0) == pytest.approx(0.30)
    assert list(G.is_wrong([0.04, 0.06, 0.25, 0.35], [0.3, 0.3, 3.0, 3.0])) == [False, True, False, True]


# ------------------------------------------------------------------ CRC / conformal

def _sim(n, rng):
    """Captures with a quality score s (higher = better) and a loss that is more likely when s is low."""
    s = rng.uniform(0, 1, n)
    wrong = rng.uniform(0, 1, n) < 0.6 * (1 - s) ** 2
    return s, wrong


def test_crc_controls_risk_in_expectation():
    """Angelopoulos et al. Thm 1: E[L_{n+1}(lam_hat)] <= alpha.  Check by simulation over many calibration draws."""
    rng = np.random.default_rng(0)
    alpha = 0.05
    grid = np.linspace(0, 1, 201)  # lambda: certify iff s >= lambda (non-increasing loss in lambda)
    risks, certs = [], []
    for _ in range(300):
        s, w = _sim(300, rng)
        L = ((s[:, None] >= grid[None, :]) & w[:, None]).astype(float)
        k, lam = G.crc_threshold(L, grid, alpha)
        assert k is not None
        st, wt = _sim(20000, rng)
        risks.append(float(((st >= lam) & wt).mean()))
        certs.append(float((st >= lam).mean()))
    assert np.mean(risks) <= alpha + 0.004  # Monte-Carlo slack
    assert np.mean(certs) > 0.3  # and it is not trivially refusing everything


def test_crc_infeasible_when_n_too_small():
    L = np.zeros((10, 5))
    k, lam = G.crc_threshold(L, np.arange(5.0), alpha=0.05)  # B/(n+1) = 0.09 > alpha
    assert k is None and lam == math.inf


def test_conformal_quantile_coverage_and_small_n():
    rng = np.random.default_rng(1)
    cov = []
    for _ in range(400):
        cal = np.abs(rng.standard_normal(99))
        q = G.conformal_quantile(cal, 0.1)
        cov.append(np.mean(np.abs(rng.standard_normal(2000)) <= q))
    assert 0.89 <= np.mean(cov) <= 0.925
    assert G.conformal_quantile([1.0, 2.0], 0.1) == math.inf
    assert G.conformal_quantile([], 0.1) == math.inf


# ------------------------------------------------------------------ QA

def _raw(**kw):
    r = {"corners": 24, "ppm": 14.0, "blur_var": 250.0, "blur_sigma_mm": 0.09, "sigma_px": 1.2, "obliquity_deg": 8.0,
         "glare_frac": 0.0, "noise_sigma": 1.0, "reproj_px": 1.0, "width_mm": 0.5, "coverage": 1.0, "spread_rel": 0.05,
         "disagree_rel": 0.08, "dt_rel": 0.05, "q_core": 0.9, "sat_frac": 0.0, "edt_ratio": 1.3, "n_holes": 0,
         "frag_frac": 0.0, "path_cover": 0.98, "locator_gt": 0}
    r.update(kw)
    return r


def test_qa_reasons():
    assert G.qa_reasons(_raw()) == []
    assert G.qa_reasons(_raw(edt_ratio=2.5)) == ["mask_blowup"]
    assert G.qa_reasons(_raw(n_holes=1)) == ["mask_holes"]
    assert G.qa_reasons(_raw(frag_frac=0.5)) == ["mask_fragmented"]
    assert G.qa_reasons(_raw(path_cover=0.3)) == ["mask_fragmented"]
    assert set(G.qa_reasons(_raw(edt_ratio=3, n_holes=2, frag_frac=0.9))) == {"mask_blowup", "mask_holes", "mask_fragmented"}


# ------------------------------------------------------------------ assess (synthetic parameters, independent of the fit)

def _params():
    feats = G.FEATURES
    coef = np.zeros(len(feats))
    coef[feats.index("log_sigma_px")] = 0.8
    coef[feats.index("log_ppm_inv")] = 0.6
    coef[feats.index("noise")] = 0.3
    P = {
        "model": {"features": feats, "lo": [-1e9] * len(feats), "hi": [1e9] * len(feats), "mean": [0.0] * len(feats),
                  "std": [1.0] * len(feats), "coef": coef.tolist(), "intercept": -1.5},
        "levels": {"0.05": {"alpha": 0.05, "theta": -1.2}}, "default_level": "0.05", "qa": dict(G.QA_DEFAULT),
        "reference": {"design": G.design_vector(_raw()).tolist()},
        "interval": {"level": 0.9, "scale": "learned", "scale_floor_mm": 0.01,
                     "cells": [{"w_lo": 0.0, "w_hi": None, "state": "any", "q": 2.0}]},
    }
    P["interval"]["cells"][0]["w_hi"] = math.inf
    return P


def _crack(width=0.5, **q):
    quality = {"sigma_px": 1.2, "coverage": 1.0, "spread_rel": 0.05, "disagree_rel": 0.08, "dt_rel": 0.05, "q_core": 0.9,
               "sat_frac": 0.0, "edt_ratio": 1.3, "n_holes": 0, "frag_frac": 0.0, "path_cover": 0.98, "locator_gt": 0}
    quality.update(q)
    return {"id": "K1", "width_mm": width, "uncertainty_mm": 0.1, "uncertainty_model_mm": 0.1, "px_per_mm": 14.0,
            "quality": quality}


OBS = {"corners": 24, "blur_var": 250.0, "blur_sigma_mm": 0.09, "obliquity_deg": 8.0, "glare_frac": 0.0,
       "noise_sigma": 1.0, "reproj_px": 1.0, "px_per_mm": 14.0}


def test_assess_certifies_good_and_flags_bad_with_reasons():
    P = _params()
    good = [_crack()]
    g = G.assess(OBS, good, P)
    assert g["certified"] and g["reasons"] == [] and g["cracks_certified"] == 1
    c = good[0]
    assert c["certified"] and c["status"] == "certified"
    lo, hi = c["interval_mm"]
    assert lo < c["width_mm"] < hi
    assert c["uncertainty_mm"] == pytest.approx((hi - lo) / 2, abs=1e-3)

    bad = _crack(sigma_px=6.0)
    bad["px_per_mm"] = 4.0
    obs = dict(OBS, px_per_mm=4.0, blur_sigma_mm=1.5)
    g2 = G.assess(obs, [bad], P)
    assert not g2["certified"] and g2["measurement"] == "flagged"
    assert not bad["certified"] and bad["status"] == "flagged"
    assert set(bad["reasons"]) & {"blurry", "low_resolution"}
    assert bad["width_mm"] == 0.5  # the width is still returned
    assert bad["interval_mm"][1] - bad["interval_mm"][0] > good[0]["interval_mm"][1] - good[0]["interval_mm"][0]


def test_assess_mask_qa_overrides_score():
    P = _params()
    c = _crack(edt_ratio=3.0)
    g = G.assess(OBS, [c], P)
    assert not g["certified"] and "mask_blowup" in c["reasons"] and g["reasons"] == c["reasons"]


def test_assess_no_cracks_is_unavailable():
    g = G.assess(OBS, [], _params())
    assert g["certified"] is False and g["measurement"] == "unavailable" and g["cracks_total"] == 0


def test_assess_never_extrapolates():
    P = _params()
    P["model"]["lo"] = [0.0] * len(G.FEATURES)
    P["model"]["hi"] = [1.0] * len(G.FEATURES)
    # absurdly good input is clipped to the calibrated range: score cannot beat the best seen condition
    c = _crack(sigma_px=1e-9)
    G.assess(dict(OBS, noise_sigma=-5.0), [c], P)
    assert math.isfinite(c["risk_ratio"])


def test_legacy_fallback(monkeypatch):
    monkeypatch.setattr(G, "load_params", lambda *a, **k: None)
    good = [_crack()]
    assert G.assess(OBS, good)["certified"] and good[0]["status"] == "certified" and good[0]["interval_mm"]
    bad = [_crack()]
    g = G.assess(dict(OBS, blur_var=50.0), bad)
    assert not g["certified"] and g["reasons"] == ["blurry"] and g["mode"] == "legacy"


# ------------------------------------------------------------------ shipped parameters

def test_u_res_table_and_monotonicity():
    # krkCMd resolution-added MAE (FWHM, 0.30-0.50 mm bin): 80 / 70 / 66 / 52 / 41 / 33 um at 8 / 10 / 12 / 15 / 20 / 25 px/mm
    for ppm, um in zip([8, 10, 12, 15, 20, 25], [80, 70, 66, 52, 41, 33]):
        assert G.u_res_mm(ppm, 0.4) * 1000 == pytest.approx(um, rel=0.12)
    for w in (0.1, 0.4, 1.0, 3.0):
        v = [G.u_res_mm(p, w) for p in (4, 8, 15, 25, 50)]
        assert all(a > b for a, b in zip(v, v[1:]))  # more px/mm, less added error
    assert G.u_res_mm(15, 5.0) == G.u_res_mm(15, 0.7)  # clamped beyond the benchmark's widths


def _shipped():
    P = G.load_params(reload=True)
    if P is None:
        pytest.skip("gate_params.json not fitted yet")
    return P


def test_shipped_params_schema_and_monotone():
    P = _shipped()
    m = P["model"]
    assert m["features"] == G.FEATURES and m["type"] == "gbm" and len(m["trees"]) >= 20
    for t in m["trees"]:
        n = len(t["f"])
        assert all(len(t[k]) == n for k in ("t", "l", "r", "v", "leaf"))
    assert P["default_level"] in P["levels"] and P["strict_level"] in P["levels"]
    assert P["levels"][P["default_level"]]["alpha"] <= 0.05
    assert P["levels"][P["strict_level"]]["theta"] <= P["levels"][P["default_level"]]["theta"]
    assert P["interval"]["level"] >= 0.9 and P["interval"]["cells"]
    assert len(P["reference"]["design"]) == len(G.FEATURES)
    # the monotone constraint: making any badness feature worse can never lower the predicted error
    rng = np.random.default_rng(0)
    ref = np.asarray(P["reference"]["design"])
    spread = np.abs(ref) * 0.3 + 0.2
    for _ in range(40):
        x = ref + rng.normal(0, 1, len(ref)) * spread
        p0 = G.predict(x, P)
        for j, f in enumerate(G.FEATURES):
            if f == "log_w":
                continue
            x2 = x.copy()
            x2[j] += 2.0 * spread[j]
            assert G.predict(x2, P) >= p0 - 1e-9, f


def test_shipped_gate_certifies_clean_wide_and_flags_degraded():
    P = _shipped()
    good = [_crack(width=1.0)]
    g = G.assess(OBS, good, P)
    assert g["certified"] and good[0]["certified"] and good[0]["reasons"] == [], (g, good[0])
    lo, hi = good[0]["interval_mm"]
    assert lo < 1.0 < hi and hi - lo < 1.0
    bad = _crack(width=1.0, sigma_px=6.0, coverage=0.5, spread_rel=0.6)
    bad["px_per_mm"] = 3.0
    g2 = G.assess(dict(OBS, px_per_mm=3.0, blur_sigma_mm=2.0, blur_var=10.0, noise_sigma=9.0), [bad], P)
    assert not g2["certified"] and g2["measurement"] == "flagged" and g2["reasons"]
    assert bad["width_mm"] == 1.0 and bad["status"] == "flagged"
    assert (bad["interval_mm"][1] - bad["interval_mm"][0]) > (good[0]["interval_mm"][1] - good[0]["interval_mm"][0])


def test_strict_level_is_stricter():
    P = _shipped()
    n_def = n_str = 0
    rng = np.random.default_rng(3)
    for _ in range(60):
        c = _crack(width=float(rng.uniform(0.5, 3.0)), sigma_px=float(rng.uniform(1, 5)), spread_rel=float(rng.uniform(0.02, 0.3)))
        c2 = dict(c, quality=dict(c["quality"]))
        G.assess(OBS, [c], P)
        G.assess(OBS, [c2], P, level=P["strict_level"])
        n_def += c["certified"]
        n_str += c2["certified"]
        assert not (c2["certified"] and not c["certified"])
    assert n_str <= n_def


def test_textured_surface_adds_resolution_term_width_dependent():
    """On an unknown (textured) substrate the krkCMd resolution-added error is combined in quadrature: thin cracks need
    more px/mm, wide cracks barely care (the cutoff is width-dependent)."""
    P = _shipped()
    obs = dict(OBS, px_per_mm=8.0)
    thin = _crack(width=0.3)
    thin["px_per_mm"] = 8.0
    wide = _crack(width=2.0)
    wide["px_per_mm"] = 8.0
    G.assess(obs, [thin], P, textured=True)
    G.assess(obs, [wide], P, textured=True)
    assert not thin["certified"] and "low_resolution" in thin["reasons"]
    assert wide["certified"]
    sharp = _crack(width=0.3)
    sharp["px_per_mm"] = 30.0
    p_panel = _crack(width=0.3)
    p_panel["px_per_mm"] = 8.0
    G.assess(dict(OBS, px_per_mm=8.0), [p_panel], P, textured=False)
    G.assess(dict(OBS, px_per_mm=8.0), [thin], P, textured=True)
    assert thin["risk_ratio"] >= p_panel["risk_ratio"]
    assert thin["interval_mm"][1] - thin["interval_mm"][0] >= p_panel["interval_mm"][1] - p_panel["interval_mm"][0] - 1e-9


# ------------------------------------------------------------------ degradation generator

def test_recipes_are_deterministic_and_documented_ranges():
    import gate_degrade as gd
    a = gd.sample_recipe(np.random.default_rng([1, 2, 3]))
    b = gd.sample_recipe(np.random.default_rng([1, 2, 3]))
    assert a == b
    json.dumps(a)
    n_tilt = sum(1 for i in range(400) if gd.sample_recipe(np.random.default_rng(i))["tilt"])
    assert 0.35 < n_tilt / 400 < 0.55


def test_apply_recipe_geometry_and_determinism():
    import gate_degrade as gd
    rng = np.random.default_rng(0)
    img = (rng.uniform(60, 220, (300, 400, 3))).astype(np.uint8)
    H = np.array([[1.5, 0, 100], [0, 1.5, 80], [0, 0, 1]], float)
    recipe = {"tilt": {"deg": 20.0, "axis_deg": 30.0}, "scale": 0.5, "blur": {"kind": "gauss", "sigma": 1.0},
              "glare": [{"x_mm": 20, "y_mm": 20, "radius_frac": 0.1, "aspect": 1.0, "angle_deg": 0, "gain": 1.5}],
              "noise": {"sigma": 3.0, "seed": 5}, "jpeg": {"q": 50}}
    o1 = gd.apply_recipe(img, recipe, H, (200, 150))
    o2 = gd.apply_recipe(img, recipe, H, (200, 150))
    assert o1.shape == (150, 200, 3) and o1.dtype == np.uint8
    assert np.array_equal(o1, o2)
    ident = gd.apply_recipe(img, {"tilt": None, "scale": 1.0, "blur": None, "glare": None, "noise": None, "jpeg": None},
                            H, (200, 150))
    assert np.array_equal(ident, img)


def test_glare_saturates_and_tilt_keeps_pivot():
    import gate_degrade as gd
    img = np.full((300, 400, 3), 120, np.uint8)
    H = np.array([[1.0, 0, 200], [0, 1.0, 150], [0, 0, 1]], float)  # board (0,0) -> pixel (200,150)
    r = {"tilt": None, "scale": 1.0, "blur": None, "noise": None, "jpeg": None,
         "glare": [{"x_mm": 0, "y_mm": 0, "radius_frac": 0.1, "aspect": 1.0, "angle_deg": 0, "gain": 2.0}]}
    o = gd.apply_recipe(img, r, H, (200, 150))
    assert o[150, 200].min() == 255 and o[0, 0, 0] == 120
    Ht = gd.tilt_homography(400, 300, 30.0, 45.0, (200, 150))
    p = Ht @ np.array([200.0, 150.0, 1.0])
    assert np.allclose(p[:2] / p[2], [200, 150], atol=1e-6)
