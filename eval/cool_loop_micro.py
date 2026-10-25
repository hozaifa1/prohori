#!/usr/bin/env python3
"""Micro-experiments of the COOL optimisation loop on the REAL inputs of the pipeline (masks, frames captured while
prohori.measure.analyze runs on a few panel photos).  Run from a full checkout:  python eval/cool_loop_micro.py --input raw=DIR --out FILE

  thin    Zhang-Suen thinning on the masks the pipeline actually thins: the old numpy shim (eval/cool_compat.thinning_zs), the
          in-tree sparse incremental `measure._thin`, and a DENSE re-expression with OpenCV kernels (filter2D neighbour code +
          LUT per sub-iteration), all checked bit-identical.
  resize  the two big INTER_AREA down-scales of a 12 MP photo and the cheaper candidates (direct vs exact 2x AREA first).
  warp    the rectified-canvas warpPerspective INTER_LINEAR against remap with fixed-point / float maps.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import cool_bench as cb  # noqa: E402
from cool_compat import thinning_zs  # noqa: E402


def bench(fn, n=None, min_s=0.4):
    fn()
    ts = []
    t_end = time.perf_counter() + min_s
    while len(ts) < (n or 5) or time.perf_counter() < t_end:
        t = time.perf_counter_ns()
        fn()
        ts.append((time.perf_counter_ns() - t) / 1e6)
        if n and len(ts) >= n:
            break
    return float(np.median(ts))


_LUT8 = None


def thin_dense(img: np.ndarray) -> np.ndarray:
    """Zhang-Suen with OpenCV kernels on the whole bounding box: per sub-iteration filter2D (neighbour code) + LUT + masked clear."""
    from prohori import measure as M
    global _LUT8
    if _LUT8 is None:
        _LUT8 = [(l.astype(np.uint8) * 255).reshape(256, 1) for l in M._zs_luts()]
    h, w = img.shape
    a = (img == 255).astype(np.uint8)
    if h < 3 or w < 3:
        return a * 255
    inner = np.zeros_like(a)
    inner[1:-1, 1:-1] = 1
    ker = M._zs_kernel()
    while True:
        removed = False
        for it in (0, 1):
            code = cv2.filter2D(a, cv2.CV_8U, ker, borderType=cv2.BORDER_CONSTANT)
            kill = cv2.LUT(code, _LUT8[it])
            kill = cv2.bitwise_and(kill, kill, mask=cv2.bitwise_and(a, inner))
            if cv2.countNonZero(kill):
                a[kill > 0] = 0
                removed = True
        if not removed:
            break
    return a * 255


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--threads", type=int, default=1)
    a = ap.parse_args(argv)
    from prohori import measure as M
    cv2.setNumThreads(a.threads)
    inputs = cb.collect_inputs(a.input, 1)[:: max(1, 29 // a.frames)][: a.frames]
    masks, grey0 = [], None
    orig = M._thin

    def rec(img):
        masks.append(img.copy())
        return orig(img)
    M._thin = rec
    for n, p in inputs:
        im = cv2.imdecode(np.frombuffer(p.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
        if grey0 is None:
            grey0 = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        M.analyze(im)
    M._thin = orig
    out = {"cv2": cv2.__version__, "threads": cv2.getNumThreads(), "n_masks": len(masks),
           "mask_px_median": int(np.median([m.size for m in masks])),
           "mask_fg_median": int(np.median([int((m > 0).sum()) for m in masks]))}
    # ---- thinning
    t = {}
    ref = [thinning_zs(m) for m in masks]
    for name, f in (("numpy_shim_old", thinning_zs), ("sparse_incremental_in_tree", M._thin), ("dense_filter2D_LUT", thin_dense)):
        res = [f(m) for m in masks]
        exact = all(np.array_equal(r, q) for r, q in zip(ref, res))
        ms = [bench(lambda m=m: f(m), n=5, min_s=0.05) for m in masks]
        t[name] = {"exact_vs_shim": bool(exact), "mean_ms_per_mask": float(np.mean(ms)), "total_ms": float(np.sum(ms))}
    out["thin"] = t
    # ---- resize
    g = grey0
    r = {}
    r["AREA_s0.488 (detect input)"] = bench(lambda: cv2.resize(g, None, fx=0.488, fy=0.488, interpolation=cv2.INTER_AREA))
    r["AREA_s0.30 (locator canvas)"] = bench(lambda: cv2.resize(g, None, fx=0.30, fy=0.30, interpolation=cv2.INTER_AREA))
    half = cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    r["AREA_x0.5 (exact 2x)"] = bench(lambda: cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
    r["x0.5 then AREA to 2000 side"] = bench(lambda: cv2.resize(cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), (2000, int(round(2000 * g.shape[0] / g.shape[1]))), interpolation=cv2.INTER_AREA))
    r["x0.5 then AREA to 0.30"] = bench(lambda: cv2.resize(cv2.resize(g, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA))
    r["AREA half->0.6 only (given half)"] = bench(lambda: cv2.resize(half, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA))
    r["AREA half->0.976 only (given half)"] = bench(lambda: cv2.resize(half, (2000, int(round(2000 * g.shape[0] / g.shape[1]))), interpolation=cv2.INTER_AREA))
    out["resize_ms"] = r
    # ---- _bg_map stage by stage (called 5-6 times per frame; 0.74x on COOL in the report)
    rng = np.random.default_rng(3)
    Hr, Wr, Sx = 500, 2000, 20.0
    lin = (0.6 + 0.2 * rng.random((Hr, Wr))).astype(np.float32)
    q = 4
    kq = M._odd(int(6.0 * Sx) / q)
    b = {}
    b["total _bg_map(2000x500)"] = bench(lambda: M._bg_map(lin, int(6.0 * Sx)))
    sm = cv2.resize(lin, (Wr // q, Hr // q), interpolation=cv2.INTER_AREA)
    b["resize AREA f32 /4"] = bench(lambda: cv2.resize(lin, (Wr // q, Hr // q), interpolation=cv2.INTER_AREA))
    top = max(float(sm.max()), 1e-6)
    m8 = np.clip(sm / top * 255.0, 0, 255).astype(np.uint8)
    b["max+clip+astype u8"] = bench(lambda: np.clip(sm / max(float(sm.max()), 1e-6) * 255.0, 0, 255).astype(np.uint8))
    b["medianBlur u8 k=%d" % kq] = bench(lambda: cv2.medianBlur(m8, kq))
    md = cv2.medianBlur(m8, kq).astype(np.float32) * (top / 255.0)
    b["astype f32 * scale"] = bench(lambda: cv2.medianBlur(m8, kq).astype(np.float32) * (top / 255.0)) - b["medianBlur u8 k=%d" % kq]
    b["GaussianBlur f32 sigma=k/3"] = bench(lambda: cv2.GaussianBlur(md, (0, 0), kq / 3.0))
    gb = cv2.GaussianBlur(md, (0, 0), kq / 3.0)
    b["resize LINEAR f32 up x4"] = bench(lambda: cv2.resize(gb, (Wr, Hr), interpolation=cv2.INTER_LINEAR))
    out["bg_map_ms"] = b
    # ---- warp
    small = cv2.resize(g, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_AREA)
    Wc, Hc = 1273, 1800
    Hm = np.array([[3.2, 0.05, 40.0], [-0.04, 3.1, 60.0], [1e-5, 2e-5, 1.0]])
    w = {}
    w["warpPerspective LINEAR"] = bench(lambda: cv2.warpPerspective(small, Hm, (Wc, Hc), flags=cv2.INTER_LINEAR))
    Hi = np.linalg.inv(Hm)
    xs, ys = np.meshgrid(np.arange(Wc, dtype=np.float64), np.arange(Hc, dtype=np.float64))
    def maps():
        d = Hi[2, 0] * xs + Hi[2, 1] * ys + Hi[2, 2]
        return ((Hi[0, 0] * xs + Hi[0, 1] * ys + Hi[0, 2]) / d).astype(np.float32), ((Hi[1, 0] * xs + Hi[1, 1] * ys + Hi[1, 2]) / d).astype(np.float32)
    mx, my = maps()
    w["map build (numpy, f32)"] = bench(maps, n=3)
    m16 = cv2.convertMaps(mx, my, cv2.CV_16SC2)
    w["remap f32 maps LINEAR"] = bench(lambda: cv2.remap(small, mx, my, cv2.INTER_LINEAR))
    w["remap 16SC2 maps LINEAR"] = bench(lambda: cv2.remap(small, m16[0], m16[1], cv2.INTER_LINEAR))
    w["convertMaps f32->16SC2"] = bench(lambda: cv2.convertMaps(mx, my, cv2.CV_16SC2), n=3)
    a0 = cv2.warpPerspective(small, Hm, (Wc, Hc), flags=cv2.INTER_LINEAR)
    a1 = cv2.remap(small, m16[0], m16[1], cv2.INTER_LINEAR)
    w["LINEAR vs remap16: max |diff| grey levels / share differing"] = [int(np.abs(a0.astype(int) - a1).max()), float((a0 != a1).mean())]
    out["warp_ms"] = w
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
