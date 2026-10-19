"""Tests for prohori.widthbench on tiny synthetic profiles (no krkCMd download needed)."""
import csv
import math

import numpy as np
import pytest

from prohori import widthbench as wb

ERF = np.vectorize(math.erf)


def synth_profile(width_mm, ppm, blur_mm=0.02, bg_lin=0.5, depth=1.0, length_mm=2.0, centre_mm=None):
    """Encoded 8-bit-valued profile of a dark bar of known width (linear-light model, Gaussian blur)."""
    n = int(round(length_mm * ppm)) | 1
    x = (np.arange(n) + 0.5) / ppm
    c = length_mm / 2 if centre_mm is None else centre_mm
    s = max(blur_mm, 1e-4) * math.sqrt(2)
    pulse = 0.5 * (ERF((x - c + width_mm / 2) / s) - ERF((x - c - width_mm / 2) / s))
    lin = bg_lin * (1.0 - depth * pulse)
    return wb.lin_to_srgb255(lin).astype(np.float32)


def make_profiles(n_stacks=2, plateau=40):
    n = 6 * n_stacks
    X = np.full((n, wb.PROFILE_LEN), 200.0, np.float32)
    for r in range(n):
        if r % 6 == 0:  # stage 1: black plateau of `plateau` px with 20-px ramps
            X[r, 230:230 + plateau] = 0
            X[r, 210:230] = np.linspace(200, 0, 22)[1:-1]
            X[r, 230 + plateau:250 + plateau] = np.linspace(0, 200, 22)[1:-1]
    return wb.Profiles(X, np.zeros(n), np.zeros(n), np.zeros(n), np.array(["s"] * n), np.ones(n, int),
                       np.array(["g"] * n), np.tile(np.arange(1, 7), n_stacks))


# ----------------------------------------------------------------------------- constants / photometry

def test_native_resolution_constants():
    assert wb.UM_PER_PX == pytest.approx(3.96875)
    assert wb.NATIVE_PX_PER_MM == pytest.approx(251.9685, rel=1e-5)


def test_srgb_roundtrip():
    v = np.arange(0, 256, dtype=float)
    assert np.allclose(wb.lin_to_srgb255(wb.srgb_to_lin(v)), v, atol=1e-6)


# ----------------------------------------------------------------------------- simulation

def test_simulate_shape_range_and_determinism():
    X = np.stack([synth_profile(0.4, wb.NATIVE_PX_PER_MM, length_mm=1.99)[:501] for _ in range(4)])
    a = wb.simulate_lowres(X, 15, rng=np.random.default_rng(3))
    b = wb.simulate_lowres(X, 15, rng=np.random.default_rng(3))
    assert a.shape[0] == 4 and 20 <= a.shape[1] <= 31 and a.shape[1] % 2 == 1
    assert np.array_equal(a, b)
    assert a.min() >= 0 and a.max() <= 255 and np.allclose(a, np.round(a))


def test_simulation_conserves_area_without_noise():
    """With the PSF and quantisation but no noise, the darkness integral (linear light) is preserved."""
    ppm = wb.NATIVE_PX_PER_MM
    X = np.stack([synth_profile(0.30, ppm, blur_mm=0.01, length_mm=2.0)[:501]])
    model = wb.SimModel(psf_sigma_px=0.75, noise=False, random_phase=False)
    lin0 = wb.normalise_exposure(wb.srgb_to_lin(X), model.exposure)
    deficit0 = (lin0.max() - lin0[0]).sum() / ppm  # mm x linear intensity, native
    for target in (10, 15, 25):
        Y = wb.simulate_lowres(X, target, model)
        lin = wb.srgb_to_lin(Y)
        deficit = (lin.max() - lin[0]).sum() / target
        assert deficit == pytest.approx(deficit0, rel=0.06)


def test_noise_reduces_with_full_well():
    X = np.tile(np.full(501, 150.0, np.float32), (50, 1))
    lo = wb.simulate_lowres(X, 15, wb.SimModel(full_well_e=500.0, psf_sigma_px=0.0), np.random.default_rng(1))
    hi = wb.simulate_lowres(X, 15, wb.SimModel(full_well_e=50000.0, psf_sigma_px=0.0), np.random.default_rng(1))
    assert lo.std() > 3 * hi.std()


# ----------------------------------------------------------------------------- estimators

@pytest.mark.parametrize("width", [0.4, 1.0])
def test_profile_widths_recovers_known_width_native(width):
    ppm = 100.0
    P = synth_profile(width, ppm, blur_mm=0.02)
    r = wb.profile_widths(P, ppm, sigma_mm=0.02, ink_dark=0.0, bg_mode="local")
    assert r["ink"] == pytest.approx(width / _ink(), rel=0.08)  # area / (INK_RATIO * bg) -> width / 0.9
    assert r["core"] == pytest.approx(width, rel=0.15)
    assert abs(r["fwhm"] - width) < 0.06
    assert abs(r["dt"] - width) < 0.08


def _ink():
    from prohori import measure
    return measure.INK_RATIO


def test_candidates_recover_width_and_survive_lower_resolution():
    for ppm in (60.0, 15.0):
        P = synth_profile(0.5, ppm, blur_mm=0.04, length_mm=2.0)
        c = wb.candidate_widths(P, ppm, sigma_mm=0.04)
        assert c["area"] == pytest.approx(0.5, abs=0.06)
        # `frac` mimics the operator's edge criterion (15 % of the way up from the darkest value, encoded): it reads
        # narrower than the true bar on an ideal blurred rectangle, but must be finite and monotone in width
        assert 0.2 < c["frac"] < 0.55
    narrow = wb.candidate_widths(synth_profile(0.3, 60.0, blur_mm=0.04), 60.0, 0.04)["frac"]
    wide = wb.candidate_widths(synth_profile(0.8, 60.0, blur_mm=0.04), 60.0, 0.04)["frac"]
    assert narrow < wide


def test_refuses_flat_profile():
    P = np.full(501, 180.0, np.float32)
    r = wb.profile_widths(P, 100.0, 0.03, bg_mode="local")
    assert all(not np.isfinite(r[k]) for k in wb.KEYS)


def test_pipeline_adapter_runs_real_measure_one():
    ppm = 15.0
    P = synth_profile(1.0, ppm, blur_mm=0.05, length_mm=2.0)
    r = wb.pipeline_width(P, ppm, sigma_mm=0.06, ink_dark=0.0)
    assert r and "profile_mm" in r and "dt_mm" in r
    assert 0.6 < r["profile_mm"] < 1.5
    # the 1-D reduction with the same as-is background handling agrees with the real code within a pixel or so
    q = wb.profile_widths(P, ppm, sigma_mm=0.06, ink_dark=0.0, bg_mode="global")
    assert abs(q["blend"] - r["profile_mm"]) < 0.1
    assert abs(q["dt"] - r["dt_mm"]) < 0.1


def test_predict_all_is_deterministic_and_worker_independent():
    X = np.stack([synth_profile(0.35, wb.NATIVE_PX_PER_MM, length_mm=1.99)[:501] for _ in range(12)])
    a = wb.predict_all(X, 15, 0.02, include_global=False, seed=4, workers=1, chunk=5)
    b = wb.predict_all(X, 15, 0.02, include_global=False, seed=4, workers=1, chunk=5)
    assert set(a) == set(wb.estimator_names(False))
    for k in a:
        assert np.array_equal(a[k], b[k], equal_nan=True)


# ----------------------------------------------------------------------------- AED port, loader

def test_aed_port_stage1_is_plateau_width():
    p = make_profiles(plateau=40)
    w = wb.aed_vba(p)
    assert w[0] == pytest.approx(40 * wb.UM_PER_PX)  # pixels within 5 levels of the minimum, in um
    assert w[6] == pytest.approx(40 * wb.UM_PER_PX)
    assert len(w) == 12


def test_aed_port_flat_later_stage_is_zero():
    """A later stage whose profile is flat (crack fully healed) reports 0 um."""
    p = make_profiles(plateau=40)
    w = wb.aed_vba(p)
    assert w[1] == 0.0


def test_load_krkcmd_roundtrip(tmp_path):
    header = ["No", "Profile", "Series", "Image", "Gridline", "Stage"] + [f"x{i}" for i in range(1, 502)] + ["MANwidth", "DLMwidth", "AEDwidth"]
    with open(tmp_path / "krkCMd_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for i in range(3):
            w.writerow([i + 1, f"P{i}", "S", 2, "g", i + 1] + [str(float(j % 255)) for j in range(501)] + ["100.0", "101.5", "98.0"])
    p = wb.load_krkcmd(tmp_path, use_cache=False)
    assert len(p) == 3 and p.X.shape == (3, 501)
    assert p.man[0] == 100.0 and p.dlm[0] == 101.5 and p.aed[2] == 98.0
    assert list(p.stage) == [1, 2, 3] and p.cluster[0] == "S|2"
    with pytest.raises(ValueError):
        (tmp_path / "bad").mkdir()
        (tmp_path / "bad" / "krkCMd_table.csv").write_text("a,b\n1,2\n")
        wb.load_krkcmd(tmp_path / "bad", use_cache=False)


# ----------------------------------------------------------------------------- metrics / gate logic

def test_bin_metrics_values():
    ref = np.array([0.2, 0.2, 0.4, 0.4, 0.6, 0.0])
    pred = np.array([0.25, 0.15, 0.40, 0.50, 0.60, 0.3])
    s = wb.bin_metrics(pred, ref, 0.0, 0.5)  # excludes ref == 0 and ref >= 0.5
    assert s["n"] == 4 and s["bias"] == pytest.approx(0.025)
    assert s["mae"] == pytest.approx(0.05) and s["p95"] <= 0.1
    assert s["ratio"] == pytest.approx(np.mean(pred[:4] / ref[:4]))
    pred2 = pred.copy()
    pred2[0] = np.nan
    s2 = wb.bin_metrics(pred2, ref, 0.0, 0.5)
    assert s2["n"] == 3 and s2["ok"] == pytest.approx(0.75)


def test_gate_is_monotone():
    ppm = [10, 15, 20, 25]
    assert wb.gate_from_curve(ppm, [False, True, True, True]) == 15
    assert wb.gate_from_curve(ppm, [True, False, True, True]) == 20  # a failure at 15 pushes the gate above it
    assert wb.gate_from_curve(ppm, [True, True, True, False]) is None


def test_passes_target_flags():
    ok = dict(n=50, bias=0.01, mae=0.04, p95=0.08, ratio=1.02, cov=0.10)
    assert wb.passes_target(ok)["all"]
    bad = dict(ok, mae=0.06)
    r = wb.passes_target(bad)
    assert not r["all"] and not r["mae"] and r["p95"]


def test_cluster_bootstrap_brackets_mae():
    rng = np.random.default_rng(0)
    ref = rng.uniform(0.1, 0.4, 600)
    pred = ref + rng.normal(0, 0.03, 600)
    cl = np.repeat(np.arange(12), 50).astype(str)
    lo, hi = wb.cluster_bootstrap(pred, ref, cl, 0.0, 0.5, "mae", n_boot=100)
    mae = np.abs(pred - ref).mean()
    assert lo <= mae <= hi and hi - lo < 0.02


def test_fit_linear_recovers_map():
    x = np.linspace(0.1, 0.5, 100)
    a, b = wb.fit_linear(x, 0.8 * x + 0.03, np.ones(100, bool))
    assert a == pytest.approx(0.8) and b == pytest.approx(0.03)
