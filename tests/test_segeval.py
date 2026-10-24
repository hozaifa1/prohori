"""Unit tests for prohori.segeval on toy masks (no datasets needed) + locator cross-check with measure.py."""
import math

import cv2
import numpy as np
import pytest

from prohori import segeval as SE


def line_mask(shape=(80, 120), y=40, x0=10, x1=110, th=3):
    m = np.zeros(shape, np.uint8)
    cv2.line(m, (x0, y), (x1, y), 1, th)
    return m.astype(bool)


def test_confusion_and_prf():
    gt = np.zeros((4, 4), bool)
    gt[:2] = True
    pr = np.zeros((4, 4), bool)
    pr[1:3] = True
    tp, fp, fn, tn = SE.confusion(pr, gt)
    assert (tp, fp, fn, tn) == (4, 4, 4, 4)
    m = SE.prf_iou(tp, fp, fn)
    assert m["precision"] == pytest.approx(0.5) and m["recall"] == pytest.approx(0.5)
    assert m["f1"] == pytest.approx(0.5) and m["iou"] == pytest.approx(4 / 12)


def test_iou_equals_f1_over_two_minus_f1():
    rng = np.random.default_rng(0)
    for _ in range(20):
        tp, fp, fn = (int(x) for x in rng.integers(1, 500, 3))
        m = SE.prf_iou(tp, fp, fn)
        assert m["iou"] == pytest.approx(SE.iou_from_f1(m["f1"]), rel=1e-12)


def test_perfect_and_empty():
    g = line_mask()
    assert SE.prf_iou(*SE.confusion(g, g)[:3])["iou"] == 1.0
    assert SE.cl_iou(g, g, 0) == pytest.approx(1.0)
    z = np.zeros_like(g)
    assert math.isnan(SE.cl_iou(z, z, 0))
    assert SE.prf_iou(0, 0, 0)["f1"] == 0.0


def test_clIoU_tolerance_monotone_and_shift():
    gt = line_mask(y=40)
    shifted = line_mask(y=42)            # parallel line, 2 px away
    v = [SE.cl_iou(shifted, gt, r) for r in (0, 1, 2, 4)]
    assert v[0] < 0.05                   # exact-pixel centreline agreement is ~0
    assert v == sorted(v)                # larger tolerance never lowers clIoU
    assert v[2] > 0.9 and v[3] > 0.9     # 2 px shift is within rho = 2


def test_clIoU_penalises_missing_and_spurious():
    gt = line_mask()
    half = line_mask(x1=60)              # half of the crack found
    assert SE.cl_iou(half, gt, 2) == pytest.approx(0.5, abs=0.06)
    spur = gt | line_mask(y=10)          # extra false line
    assert SE.cl_iou(spur, gt, 2) == pytest.approx(0.5, abs=0.06)
    tp, fp, fn = SE.cl_counts(SE.skeleton(half), SE.skeleton(gt), 2)
    assert fp == 0 and tp / (tp + fn) == pytest.approx(0.5, abs=0.06)


def test_skeleton_is_thin_and_centred():
    gt = line_mask(th=7)
    sk = SE.skeleton(gt)
    assert sk.sum() < gt.sum() / 4
    ys, _ = np.nonzero(sk)
    assert abs(ys.mean() - 40) < 1.0


def test_sweep_ods_ois():
    gt = line_mask(th=5)
    # score map: crack = 0.9 plus noise, background 0.2 plus a 0.5 distractor blob
    score = np.full(gt.shape, 0.2, np.float32)
    score[gt] = 0.9
    score[:15, :15] = 0.5
    thr = [0.1, 0.3, 0.6, 0.95]
    acc = SE.SweepAccumulator(thr, rhos=(0, 2))
    for _ in range(3):
        acc.add(gt, SE.sweep_from_scores(score, thr))
    f1 = [c.metrics()["f1"] for c in acc.pix]
    assert f1[0] < f1[1] < f1[2] and f1[3] == 0.0       # sweep behaves
    assert acc.ods_index() == 2 and acc.ods() == pytest.approx(1.0)
    assert acc.ois() == pytest.approx(1.0)
    s = acc.summary(default_index=1)
    assert s["ODS_iou"] == pytest.approx(1.0) and s["at_ods"]["clIoU_2px"] == pytest.approx(1.0)
    assert s["at_default"]["precision"] < 1.0


def test_ois_ignores_images_without_crack():
    gt = line_mask()
    acc = SE.SweepAccumulator([0.5])
    acc.add(gt, [gt])
    acc.add(np.zeros_like(gt), [np.zeros_like(gt)])
    assert acc.ois() == pytest.approx(1.0) and acc.n_with_crack == 1 and acc.n_images == 2


# ---------------------------------------------------------------- classical locator


def synth_crack_image(shape=(300, 400)):
    img = np.full(shape, 190, np.uint8)
    rng = np.random.default_rng(1)
    img = np.clip(img + rng.normal(0, 3, shape), 0, 255).astype(np.uint8)
    gt = np.zeros(shape, np.uint8)
    pts = np.array([[20, 150], [120, 170], [220, 140], [380, 160]], np.int32)
    cv2.polylines(gt, [pts], False, 1, 4)
    img[gt > 0] = 60
    return cv2.GaussianBlur(img, (0, 0), 0.8), gt.astype(bool)


def test_locator_finds_a_clean_crack():
    img, gt = synth_crack_image()
    loc = SE.ClassicalLocator(px_per_mm=5.0)
    m = loc(img, 0.12)
    tp, fp, fn, _ = SE.confusion(m, gt)
    assert tp / gt.sum() > 0.9               # the crack is located
    assert SE.cl_iou(m, gt, 2) > 0.7


def test_locator_ignores_short_blob():
    img = np.full((300, 400), 190, np.uint8)
    cv2.circle(img, (200, 150), 8, 50, -1)
    assert not SE.ClassicalLocator(5.0)(img, 0.12).any()   # short, wide blob: filtered by length/width rules


def test_locator_matches_measure_py():
    """The re-implementation must give the same mask as the real measure._locate_cracks (same thresholds)."""
    measure = pytest.importorskip("prohori.measure")
    if not hasattr(measure, "_locate_cracks"):
        pytest.skip("measure._locate_cracks not available")
    img, gt = synth_crack_image()
    try:
        ref = SE.measure_locator_mask(img, 5.0)
    except Exception as e:                    # private API changed upstream
        pytest.skip(f"measure._locate_cracks signature changed: {e}")
    mine = SE.ClassicalLocator(5.0)(img, SE.LOC_DARK_THRESH)
    inter = (mine & ref).sum()
    union = (mine | ref).sum()
    assert union > 0 and inter / union > 0.98
