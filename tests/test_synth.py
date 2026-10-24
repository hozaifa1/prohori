"""Tests of the synthetic generator: determinism, exact crack-width rasterisation, geometric ground truth."""
import json
import math

import cv2
import numpy as np
import pytest

from prohori import synth as S

needs_assets = pytest.mark.skipif(
    not S.list_textures() or not S.crack_mask_entries(S.SynthConfig().crack_sources),
    reason="textures / crack masks not downloaded (see research/DATASETS.md)")

SMALL = dict(width=2048, height=1536, ppm_range=(6.0, 7.0), crack_extent_mm=(35.0, 60.0))


def small_cfg(**kw):
    return S.SynthConfig(**{**SMALL, **kw})


def straight_graph(width_mm=0.5, length_mm=60.0, step=0.25):
    n = int(length_mm / step) + 1
    pts = np.stack([np.arange(n) * step, np.zeros(n)], 1)
    edges = np.stack([np.arange(n - 1), np.arange(1, n)], 1)
    return S.CrackGraph(pts, np.full(n, width_mm), np.full(n, 1.0), edges, "toy", "toy")


@pytest.mark.parametrize("width", [0.15, 0.3, 0.5, 1.0, 2.5])
def test_swept_disc_rasterisation_has_exact_width(width):
    """Integrated coverage / length == width: the ground-truth width is exact by construction."""
    g = straight_graph(width)
    ss = 32.0
    cov, lo = S.rasterise_crack(g.pts, g, ss)
    area_mm2 = cov.astype(np.float64).sum() / 255.0 / ss ** 2
    length = 60.0 + width                           # round end caps add radius on each side: area = w * L + pi r^2
    expected = width * 60.0 + math.pi * (width / 2) ** 2
    assert area_mm2 == pytest.approx(expected, rel=0.02)
    # and the width measured on the 1-D profile through the middle equals the width
    col = cov[:, cov.shape[1] // 2].astype(np.float64) / 255.0
    assert col.sum() / ss == pytest.approx(width, rel=0.03)


def test_look_at_pose_is_a_proper_rotation_and_looks_at_target():
    R, C = S.look_at_pose(np.array([70.0, 50.0]), 600.0, math.radians(30), 1.0, 0.7)
    assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-9)
    assert C[2] < 0                                       # camera in front of the board frame (z points into the wall)
    K = np.array([[3000.0, 0, 1023.5], [0, 3000.0, 767.5], [0, 0, 1]])
    p = S.project(R, C, K, np.zeros(2), np.array([[70.0, 50.0]]))[0]
    assert p == pytest.approx([1023.5, 767.5], abs=1e-6)  # the look-at point projects to the principal point


def test_plane_map_inverts_projection_with_distortion():
    R, C = S.look_at_pose(np.array([70.0, 50.0]), 500.0, math.radians(25), 2.0, -0.5)
    K = np.array([[3200.0, 0, 1023.5], [0, 3200.0, 767.5], [0, 0, 1]])
    dist = np.array([0.02, -0.004])
    X, Y = S.plane_map(R, C, K, dist, 2048, 1536)
    pts = np.array([[20.0, 10.0], [100.0, 80.0], [140.0, 20.0]])
    uv = S.project(R, C, K, dist, pts)
    for (u, v), (x, y) in zip(uv, pts):
        iu, iv = int(round(u)), int(round(v))
        assert 0 <= iu < 2048 and 0 <= iv < 1536
        # sub-pixel: plane position of the pixel centre differs from the point by at most one pixel footprint (~0.2 mm)
        assert abs(X[iv, iu] - x) < 0.35 and abs(Y[iv, iu] - y) < 0.35


@needs_assets
def test_render_is_deterministic():
    cfg = small_cfg()
    a = S.render(5, cfg)
    b = S.render(5, cfg)
    assert a[0] == b[0]
    assert a[2]["crack"]["stations_mm"] == b[2]["crack"]["stations_mm"]
    c = S.render(6, cfg)
    assert c[0] != a[0]


@needs_assets
def test_render_gt_matches_detected_board_and_json_roundtrip():
    cfg = small_cfg()
    buf, img, gt = S.render(11, cfg)
    json.loads(json.dumps(gt))                                                  # JSON serialisable
    assert img.shape == (cfg.height, cfg.width, 3)
    w = np.array([s[2] for s in gt["crack"]["stations_mm"]])
    assert gt["crack"]["width_p10_mm"] <= gt["crack"]["width_median_mm"] <= gt["crack"]["width_p90_mm"]
    assert 0.05 <= w.min() and w.max() <= 9.5
    # the board must be detectable and its detected inner corners must sit on the ground-truth corners (< 1 px)
    from prohori.board import make_board
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cp = cv2.aruco.CharucoParameters()
    cp.minMarkers = 1
    det = cv2.aruco.CharucoDetector(make_board(), cp, cv2.aruco.DetectorParameters())
    corners, ids, _, _ = det.detectBoard(grey)
    assert ids is not None and len(ids) >= 18
    gt_px = np.array(gt["board"]["corners_px"])[ids.ravel()]
    err = np.hypot(*(corners.reshape(-1, 2) - gt_px).T)
    assert np.median(err) < 0.8 and np.percentile(err, 90) < 2.0
    # GT scale agrees with the detection-based scale
    assert 4.0 < gt["scale"]["ppm_board"] < 12.0


@needs_assets
def test_crack_is_darker_than_surroundings_at_gt_stations():
    cfg = small_cfg(p_glare=0.0, p_shadow=0.0, p_motion=0.0, p_defocus=0.0, crack_width_mm=(1.6, 2.5))
    buf, img, gt = S.render(3, cfg)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    st = np.array(gt["crack"]["stations_px"])
    w = np.array([s[2] for s in gt["crack"]["stations_mm"]])
    ok = (st[:, 0] > 20) & (st[:, 0] < cfg.width - 20) & (st[:, 1] > 20) & (st[:, 1] < cfg.height - 20)
    on = g[st[ok, 1].round().astype(int), st[ok, 0].round().astype(int)]
    bg = cv2.GaussianBlur(g, (0, 0), 25)[st[ok, 1].round().astype(int), st[ok, 0].round().astype(int)]
    wide = w[ok] > 0.8                                   # wide parts must be clearly resolved at ~6 px/mm
    assert wide.sum() > 3
    assert np.median(on[wide] / bg[wide]) < 0.85
