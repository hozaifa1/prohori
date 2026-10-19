"""Fast tests for prohori.measure on a synthetic render of the printed test panel (no phone photos needed)."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from prohori import measure

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data/print/PRINT_ME_test_panel_A4.pdf"


@pytest.fixture(scope="module")
def synthetic_photo():
    fitz = pytest.importorskip("pymupdf")
    if not PDF.exists():
        pytest.skip("test panel PDF not present")
    dpi = 300  # ~11.8 px/mm, close to a real phone photo at ~25 cm
    pix = fitz.open(PDF)[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    page = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).astype(np.float32)
    page = 35.0 + page * (225.0 - 35.0) / 255.0  # photographed toner / paper levels
    # below the board, printed strokes are lighter than the board's solid black (as on the real print): scale their
    # darkness to 80 % in linear light
    y_cracks = int(135 / 25.4 * dpi)
    lin = (page[y_cracks:] / 255.0) ** 2.2
    paper = (225.0 / 255.0) ** 2.2
    page[y_cracks:] = 255.0 * (paper - (paper - lin) * 0.8) ** (1 / 2.2)
    h, w = page.shape
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[110, 70], [w - 30, 10], [w - 120, h - 60], [20, h - 20]])  # mild perspective (~8 deg)
    photo = cv2.warpPerspective(page, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=90)
    photo = cv2.GaussianBlur(photo, (0, 0), 0.9)
    photo = photo + np.random.default_rng(0).normal(0, 2.0, photo.shape)
    photo = np.clip(photo, 0, 255).astype(np.uint8)
    return cv2.cvtColor(photo, cv2.COLOR_GRAY2BGR)


def test_analyze_synthetic_panel(synthetic_photo):
    r = measure.analyze(synthetic_photo, panel_mode=True)
    json.dumps(r)  # plain python types only
    assert r["ok"], r["error"]
    obs = r["observation"]
    assert obs["corners"] == 24 and obs["corners_total"] == 24
    assert obs["image_w"] == synthetic_photo.shape[1] and obs["image_h"] == synthetic_photo.shape[0]
    assert 8 < obs["px_per_mm"] < 14
    assert obs["obliquity_deg"] < 25
    assert r["gate"]["certified"], (r["gate"], [(c["id"], c["reasons"]) for c in r["cracks"]])
    ids = [c["id"] for c in r["cracks"]]
    assert ids == [f"C{i}" for i in range(1, 9)]
    errs = []
    for c in r["cracks"]:
        assert c["true_width_mm"] is not None and c["uncertainty_mm"] > 0
        assert 2 <= len(c["polyline_px"]) <= 60
        assert c["length_mm"] > 60
        errs.append(abs(c["width_mm"] - c["true_width_mm"]))
        assert errs[-1] < max(0.12, 0.12 * c["true_width_mm"]), (c["id"], c["width_mm"], c["true_width_mm"])
    assert float(np.mean(errs)) < 0.08
    assert r["timing_ms"]["total"] < 5000


def test_observation_vector_is_numeric_and_well_defined(synthetic_photo):
    r = measure.analyze(synthetic_photo)
    o = r["observation"]
    for k in ("corners", "blur_var", "px_per_mm", "obliquity_deg", "glare_frac", "crack_px_extent", "crack_coverage",
              "noise_sigma", "blur_sigma_mm", "reproj_px"):
        assert isinstance(o[k], (int, float)) and np.isfinite(o[k]), k
    assert o["board_found"] is True
    assert o["crack_coverage"] == 1.0 and o["crack_px_extent"] > 1000
    assert 0 <= o["glare_frac"] <= 1 and o["noise_sigma"] >= 0 and o["blur_sigma_mm"] > 0


def test_crack_flags_interval_and_quality(synthetic_photo):
    r = measure.analyze(synthetic_photo)
    g = r["gate"]
    assert g["cracks_total"] == 8 and g["cracks_certified"] >= 1 and g["mode"] in ("crc", "legacy")
    for c in r["cracks"]:
        assert isinstance(c["certified"], bool) and c["status"] in ("certified", "flagged")
        assert isinstance(c["reasons"], list)
        lo, hi = c["interval_mm"]
        assert lo <= c["width_mm"] <= hi and lo < hi and c["interval_level"] == 0.9
        q = c["quality"]
        for k in ("coverage", "spread_rel", "disagree_rel", "dt_rel", "q_core", "sat_frac", "edt_ratio", "n_holes",
                  "frag_frac", "path_cover", "sigma_px"):
            assert np.isfinite(q[k]), k
        assert q["edt_ratio"] >= 1.0 and 0 <= q["coverage"] <= 1 and 0 <= q["frag_frac"] <= 1
    json.dumps(r)


def test_apply_gate_false_and_debug_roundtrip(synthetic_photo):
    r0 = measure.analyze(synthetic_photo, apply_gate=False, debug=True)
    assert r0["gate"]["mode"] == "off" and r0["gate"]["certified"] is False
    for c in r0["cracks"]:
        assert "certified" not in c and "raw" in c
        # the blend is a pure function of the raw numbers: re-evaluating it reproduces the reported width
        raw = c["raw"]
        b = measure.blend_widths(np.array(raw["area"]), raw["Dcore"], raw["Dink"],
                                 np.array([np.nan if v is None else v for v in raw["fwhm"]]), raw["sigma_mm"])
        assert abs(float(np.median(b["w_i"])) - c["width_mm"]) < 1e-3
    r1 = measure.analyze(synthetic_photo)
    assert [c["width_mm"] for c in r1["cracks"]] == [c["width_mm"] for c in r0["cracks"]]  # gating never changes widths


def test_degraded_capture_is_flagged_not_dropped(synthetic_photo):
    """Heavy blur + low resolution: widths are still returned but the gate refuses and gives reasons."""
    small = cv2.resize(synthetic_photo, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)  # ~3 px/mm
    bad = cv2.GaussianBlur(small, (0, 0), 3.0)
    r = measure.analyze(bad)
    assert r["gate"]["certified"] is False
    if r["cracks"]:
        assert r["gate"]["reasons"], r["gate"]
        assert all(c["status"] == "flagged" for c in r["cracks"])
    else:
        assert r["gate"]["reasons"] or r["error"]


def test_analyze_speed_12mp(synthetic_photo):
    """Spec: < 1.5 s per 12 MP image (the synthetic render is ~3.5 MP, so scale up to a 12 MP canvas)."""
    import time
    big = cv2.resize(synthetic_photo, (4096, 3072), interpolation=cv2.INTER_CUBIC)
    measure.analyze(big)  # warm-up (detector construction, LUTs)
    t = min((lambda t0: (measure.analyze(big), time.perf_counter() - t0)[1])(time.perf_counter()) for _ in range(2))
    assert t < 3.0, t  # generous CI bound; eval/run_panel_photos.py reports the real-photo median (spec: < 1.5 s)


def test_overlay(synthetic_photo):
    r = measure.analyze(synthetic_photo)
    ov = measure.draw_overlay(synthetic_photo, r)
    assert ov.ndim == 3 and ov.shape[2] == 3 and ov.dtype == np.uint8
    assert max(ov.shape[:2]) <= 1600


@pytest.mark.parametrize("bad", [
    None,
    np.zeros((0, 0, 3), np.uint8),
    np.zeros((50, 50, 3), np.uint8),
    np.full((600, 800, 3), 255, np.uint8),
    np.random.default_rng(1).integers(0, 255, (480, 640, 3), dtype=np.uint8),
    np.zeros((300, 300), np.uint8),
    "not an image",
])
def test_never_raises_on_bad_input(bad):
    r = measure.analyze(bad)
    json.dumps(r)
    assert r["ok"] is False
    assert r["cracks"] == []
    assert r["gate"]["certified"] is False and r["gate"]["reasons"]
    for k in ("corners", "corners_total", "blur_var", "px_per_mm", "obliquity_deg", "glare_frac", "crack_px_extent",
              "image_w", "image_h"):
        assert k in r["observation"]
    for k in ("detect", "rectify", "measure", "total"):
        assert k in r["timing_ms"]
    if isinstance(bad, np.ndarray) and bad.size:
        out = measure.draw_overlay(bad, r)
        assert out.ndim == 3
