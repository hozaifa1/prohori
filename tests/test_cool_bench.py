"""Tests for eval/cool_bench.py (the COOL benchmark and accuracy-invariance harness)."""
import gzip
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import cool_bench as cb  # noqa: E402

SAMPLE = ROOT / "service" / "static" / "samples" / "move-closer.jpg"


def test_sha_is_bit_exact_and_sensitive():
    a = {"x": np.arange(5, dtype=np.float64), "y": [1.5, "s", None]}
    b = {"x": np.arange(5, dtype=np.float64), "y": [1.5, "s", None]}
    assert cb.sha(a) == cb.sha(b)
    b["x"][3] = np.nextafter(3.0, 4.0)  # one ulp
    assert cb.sha(a) != cb.sha(b)
    assert cb.sha(np.zeros((2, 3), np.uint8)) != cb.sha(np.zeros((3, 2), np.uint8))


def test_flatten_hex_and_exclusions():
    res = {"ok": True, "timing_ms": {"total": 1.0}, "cracks": [{"width_mm": 0.25, "id": "A", "n": 3}],
           "polyline_px": [[1.0, 2.0]]}
    f = cb.flatten(res)
    assert f["cracks.0.width_mm"] == (0.25).hex()
    assert f["cracks.0.n"] == "3" and f["ok"] == "True"
    assert not any(k.startswith("timing_ms") for k in f)
    assert f["polyline_px"].startswith("sha:")


def test_boot_ratio_recovers_known_speedup():
    rng = np.random.default_rng(0)
    A = [rng.normal(100, 5, 4) for _ in range(30)]
    B = [a / 2.0 for a in A]
    pt, lo, hi = cb.boot_ratio(A, B, np.mean, n_boot=200)
    assert pt == pytest.approx(2.0) and lo <= 2.0 + 1e-9 and hi >= 2.0 - 1e-9
    same = cb.boot_ratio(A, A, np.mean, n_boot=100)
    assert same == (1.0, 1.0, 1.0)


@pytest.mark.skipif(not hasattr(cv2, "ximgproc"), reason="needs opencv-contrib for the native reference")
def test_thinning_shim_is_bit_exact_with_ximgproc():
    rng = np.random.default_rng(3)
    for k in range(25):
        h, w = int(rng.integers(12, 160)), int(rng.integers(12, 260))
        m = np.zeros((h, w), np.uint8)
        for _ in range(int(rng.integers(1, 4))):
            pts = np.cumsum(rng.normal(0, 6, (20, 2)), 0) + [w / 2, h / 2]
            cv2.polylines(m, [pts.astype(np.int32).reshape(-1, 1, 2)], False, 255, int(rng.integers(1, 9)))
        if k % 3 == 0:
            m |= (rng.random((h, w)) < 0.25).astype(np.uint8) * 255
        if k % 5 == 0:
            m[0, :] = 255
            m[:, 0] = 255
        assert np.array_equal(cb.thinning_zs(m), cv2.ximgproc.thinning(m)), k


def test_cv_proxy_times_functions_and_passes_through_constants():
    rec = cb.Recorder()
    rec.on = True
    px = cb.CvProxy(cv2, "", rec)
    assert px.INTER_AREA == cv2.INTER_AREA
    assert px.error is cv2.error
    out = px.resize(np.zeros((8, 8), np.uint8), (4, 4))
    assert out.shape == (4, 4)
    assert "cv2.resize" in rec.ms and rec.ms["cv2.resize"][1] == 1 and rec.calls[0].startswith("cv2.resize:")


def _doc(label, widths, m=None, calls=None):
    inv = {"widths": widths, "m_scalars": m or {n: [] for n in widths}, "calls": calls or {n: ["cv2.resize:aa"] for n in widths},
           "public_sha": {}, "decode_sha": {n: "x" for n in widths}}
    doc = {"label": label, "headline": {"intra_run_deterministic": True},
           "invariance": {"canonical_sha256": cb.canonical_sha(widths)}}
    return doc, inv


def test_invariance_verdicts():
    w = {"i1": {"cracks.0.width_mm": (0.5).hex(), "cracks.0.certified": "True", "gate.certified": "True"}}
    da, ia = _doc("a", w)
    db, ib = _doc("b", json.loads(json.dumps(w)))
    rep = cb.invariance_report(da, ia, db, ib)
    assert rep["identical"] and rep["dw_max_mm"] == 0 and not rep["cert_flips"]
    assert cb.verdict_text(rep).startswith("BITWISE IDENTICAL")
    w2 = json.loads(json.dumps(w))
    w2["i1"]["cracks.0.width_mm"] = (0.5001).hex()
    w2["i1"]["cracks.0.certified"] = "False"
    db2, ib2 = _doc("b", w2, calls={"i1": ["cv2.resize:bb"]})
    rep2 = cb.invariance_report(da, ia, db2, ib2)
    assert not rep2["identical"]
    assert rep2["dw_max_mm"] == pytest.approx(1e-4, rel=1e-3)
    assert len(rep2["cert_flips"]) == 1 and rep2["first_divergence"][2] == "cv2.resize"
    assert "NOT bitwise" in cb.verdict_text(rep2)


def test_run_and_compare_end_to_end(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    shutil.copy(SAMPLE, d / "s1.jpg")
    out = tmp_path / "out"
    for label in ("a", "b"):
        rc = cb.main(["run", "--label", label, "--out", str(out), "--input", f"samples={d}", "--reps", "2", "--warmup", "1",
                      "--micro", "--micro-scale", "0.25", "--trace-reps", "1", "--thinning", "shim"])
        assert rc == 0
    doc = json.loads((out / "a.bench.json").read_text())
    pi = doc["headline"]["per_image"]["samples/s1.jpg"]
    assert set(pi) == set(cb.STAGES) and len(pi["e2e"]) == 2
    assert doc["thinning"] == "shim" and doc["invariance"]["n_inputs"] == 1
    assert "amdahl" in doc and doc["amdahl"]["cv2_ms"][0] > 0
    assert (out / "a.build_info.txt").exists()
    with gzip.open(out / "a.inv.json.gz", "rt") as f:
        assert "widths" in json.load(f)
    # two runs of the same build on the same input must be bitwise identical
    rc = cb.main(["compare", str(out / "a.bench.json"), str(out / "b.bench.json"), "--boot", "50",
                  "--json", str(tmp_path / "c.json"), "--md", str(tmp_path / "c.md")])
    assert rc == 0
    c = json.loads((tmp_path / "c.json").read_text())
    assert c["invariance"]["identical"] is True
    assert (tmp_path / "c.md").read_text().startswith("### a  vs  b")


def test_install_thinning_shim_forwards_everything_else():
    import types as _t
    import cool_compat as cc
    fake = _t.SimpleNamespace(cv2=cv2)
    assert cc.install_thinning(fake, "shim") == "shim"
    px = fake.cv2
    assert px.INTER_AREA == cv2.INTER_AREA and px.resize is cv2.resize
    m = np.zeros((20, 20), np.uint8)
    m[5:15, 3:17] = 255
    assert np.array_equal(px.ximgproc.thinning(m), cc.thinning_zs(m))


def test_profile_classifier():
    import cool_profile as cp
    assert cp.classify("~", "<resize>") == "cv2"
    assert cp.classify("~", "<method 'detectBoard' of 'cv2.aruco.CharucoDetector' objects>") == "cv2"
    assert cp.classify("~", "<method 'reduce' of 'numpy.ufunc' objects>") == "numpy"
    assert cp.classify("~", "<built-in method builtins.len>") == "builtin"
    assert cp.classify("src/prohori/measure.py", "_measure_roi") == "python"


def test_variants_smoke_and_baseline_exactness():
    import cool_variants as cv
    cases = cv.build_cases(0.25)
    groups = {}
    for g, name, desc, fn, reps in cases:
        groups.setdefault(g, []).append((name, fn))
    assert len(groups) >= 10
    # the pipeline's own call is first in each group and a variant that is the same call must hash the same
    name, fn = groups["resize 12MP grey x0.5"][0]
    assert cb.sha(fn(), 16) == cb.sha(fn(), 16)
