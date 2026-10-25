#!/usr/bin/env python3
"""Which OpenCV flags / variants are fastest for PROHORI's hot calls on THIS OpenCV build?

For each hot call of the pipeline (resize, warpPerspective, remap, GaussianBlur, medianBlur, erode/dilate,
distanceTransform, connectedComponents, cvtColor/imdecode) it times the call as the pipeline makes it (baseline) and
alternative formulations of the same job, on build-independent synthetic data at the pipeline's sizes, and fingerprints
the output so each variant is marked bit-exact (or not) against the baseline of its group on the same build.  Run it
once per OpenCV build (single thread by default) and diff the JSONs:

  python eval/cool_variants.py run --label cool --out DIR            # writes DIR/<label>.variants.json
  python eval/cool_variants.py compare A.variants.json B.variants.json [--md OUT.md]

Not part of the measurement; no PROHORI code is used except the shim switch.
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
import cool_bench as cb  # noqa: E402


def build_cases(scale: float = 1.0):
    sc = cb._synth_scene(scale)
    grey, bgr, can, cmask, roi, mroi = (sc[k] for k in ("grey", "bgr", "canvas", "cmask", "roi", "mroi"))
    H, W = grey.shape
    Hc, Wc = can.shape
    Hr, Wr = roi.shape
    Hm = np.array([[1.02, 0.03, 12.0], [-0.02, 0.98, 20.0], [2e-6, 1e-6, 1.0]])
    small = cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_NEAREST)
    # remap tables equivalent to the warps (inverse mapping: dst -> src), built with numpy
    def maps_for(Hh, size, src_shape):
        w, h = size
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
        Hi = np.linalg.inv(Hh)
        den = Hi[2, 0] * xs + Hi[2, 1] * ys + Hi[2, 2]
        mx = ((Hi[0, 0] * xs + Hi[0, 1] * ys + Hi[0, 2]) / den).astype(np.float32)
        my = ((Hi[1, 0] * xs + Hi[1, 1] * ys + Hi[1, 2]) / den).astype(np.float32)
        return mx, my
    mx_c, my_c = maps_for(Hm, (Wc, Hc), small.shape)
    m16a, m16b = cv2.convertMaps(mx_c, my_c, cv2.CV_16SC2)
    mx_r, my_r = maps_for(Hm, (Wr, Hr), grey.shape)
    Haff = np.array([[1.02, 0.03, 12.0], [-0.02, 0.98, 20.0]])
    g = np.float32
    n = 5  # repeats (the first call is a warm-up)
    f32 = roi.astype(np.float32) / 255.0
    k7 = np.ones((7, 7), np.uint8)
    kgau = cv2.getGaussianKernel(5, 0.7)
    ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    small_mask = cmask
    C = []  # (group, name, desc, fn, repeats)

    def add(group, name, desc, fn, reps=n):
        C.append((group, name, desc, fn, reps))

    # --- group: downscale the 12 MP grey frame by 0.3 (board detection input is 2000 px max side; locator ~0.3)
    gname = "resize 12MP grey x0.3"
    add(gname, "AREA (as pipeline)", "cv2.resize INTER_AREA", lambda: cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_AREA))
    add(gname, "LINEAR", "INTER_LINEAR (aliases; not equal)", lambda: cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_LINEAR))
    add(gname, "LINEAR_EXACT", "INTER_LINEAR_EXACT", lambda: cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_LINEAR_EXACT))
    add(gname, "NEAREST", "INTER_NEAREST", lambda: cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_NEAREST))
    gname = "resize 12MP grey x0.5"
    add(gname, "AREA (as pipeline)", "INTER_AREA", lambda: cv2.resize(grey, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
    add(gname, "pyrDown", "cv2.pyrDown (5x5 Gaussian, not equal)", lambda: cv2.pyrDown(grey))
    add(gname, "LINEAR", "INTER_LINEAR (2x2 average at exactly 0.5)", lambda: cv2.resize(grey, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR))
    add(gname, "LINEAR_EXACT", "INTER_LINEAR_EXACT", lambda: cv2.resize(grey, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_LINEAR_EXACT))
    # --- group: rectified canvas warp (small grey -> canvas)
    gname = "warp small grey -> canvas"
    add(gname, "warpPerspective LINEAR (as pipeline)", "cv2.warpPerspective INTER_LINEAR", lambda: cv2.warpPerspective(small, Hm, (Wc, Hc), flags=cv2.INTER_LINEAR))
    add(gname, "remap f32 maps LINEAR", "cv2.remap, CV_32FC1 maps (maps precomputed)", lambda: cv2.remap(small, mx_c, my_c, cv2.INTER_LINEAR))
    add(gname, "remap 16SC2 maps LINEAR", "cv2.remap, fixed-point CV_16SC2+CV_16UC1 maps (precomputed)", lambda: cv2.remap(small, m16a, m16b, cv2.INTER_LINEAR))
    add(gname, "warpPerspective NEAREST", "INTER_NEAREST", lambda: cv2.warpPerspective(small, Hm, (Wc, Hc), flags=cv2.INTER_NEAREST))
    add(gname, "warpAffine LINEAR (affine approx)", "cv2.warpAffine INTER_LINEAR with the affine part of H", lambda: cv2.warpAffine(small, Haff, (Wc, Hc), flags=cv2.INTER_LINEAR))
    # --- group: full-resolution ROI warp (12 MP grey -> 2000x500), the 'extract ROI' cost
    gname = "warp 12MP grey -> ROI"
    add(gname, "warpPerspective CUBIC (as pipeline)", "INTER_CUBIC, BORDER_CONSTANT",
        lambda: cv2.warpPerspective(grey, Hm, (Wr, Hr), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0), 4)
    add(gname, "warpPerspective LINEAR", "INTER_LINEAR", lambda: cv2.warpPerspective(grey, Hm, (Wr, Hr), flags=cv2.INTER_LINEAR), 4)
    add(gname, "remap f32 CUBIC", "cv2.remap CUBIC, f32 maps (precomputed)", lambda: cv2.remap(grey, mx_r, my_r, cv2.INTER_CUBIC), 4)
    add(gname, "remap f32 LINEAR", "cv2.remap LINEAR, f32 maps", lambda: cv2.remap(grey, mx_r, my_r, cv2.INTER_LINEAR), 4)
    add(gname, "crop then warpPerspective CUBIC", "warp only the source bounding box (same pixels, smaller source)",
        lambda: cv2.warpPerspective(grey[: H // 2 + 200, : W // 2 + 200], Hm, (Wr, Hr), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0), 4)
    gname = "warp validity mask (12MP ones -> ROI)"
    add(gname, "warpPerspective NEAREST of full ones (as pipeline)", "np.full(12MP) warped NEAREST",
        lambda: cv2.warpPerspective(np.full(grey.shape, 255, np.uint8), Hm, (Wr, Hr), flags=cv2.INTER_NEAREST), 4)
    # --- group: smoothing
    gname = "GaussianBlur u8 sigma 0.7 (canvas)"
    add(gname, "GaussianBlur (as pipeline)", "ksize (0,0), sigma 0.7", lambda: cv2.GaussianBlur(can, (0, 0), 0.7))
    add(gname, "sepFilter2D k=5", "explicit 5-tap kernel", lambda: cv2.sepFilter2D(can, -1, kgau, kgau))
    add(gname, "filter2D 5x5", "2-D kernel", lambda: cv2.filter2D(can, -1, kgau @ kgau.T))
    add(gname, "GaussianBlur ksize 5", "explicit ksize (5,5)", lambda: cv2.GaussianBlur(can, (5, 5), 0.7))
    gname = "GaussianBlur f32 sigma 4 (ROI darkness)"
    add(gname, "GaussianBlur f32 (as pipeline)", "sigma 4, f32", lambda: cv2.GaussianBlur(f32, (0, 0), 4.0))
    add(gname, "GaussianBlur on u8 then convert", "blur the uint8 ROI (not equal)", lambda: cv2.GaussianBlur(roi, (0, 0), 4.0).astype(g) / 255.0)
    add(gname, "sepFilter2D f32", "same kernel via sepFilter2D", lambda: (lambda k: cv2.sepFilter2D(f32, -1, k, k))(cv2.getGaussianKernel(2 * int(4 * 4.0 + 0.5) + 1, 4.0)))
    gname = "medianBlur k=15 (background map, 1/4 res)"
    q = can[::4, ::4].copy()
    add(gname, "medianBlur (as pipeline)", "cv2.medianBlur k=15 on u8", lambda: cv2.medianBlur(q, 15))
    add(gname, "medianBlur k=13", "k=13 (different kernel, speed only)", lambda: cv2.medianBlur(q, 13))
    gname = "erode 7x7 u8 (canvas validity)"
    add(gname, "erode ones(7,7) (as pipeline)", "np.ones((7,7)) kernel", lambda: cv2.erode(cmask, k7))
    add(gname, "erode getStructuringElement RECT", "same kernel, MORPH_RECT", lambda: cv2.erode(cmask, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))))
    add(gname, "erode 3x3 x3 iterations", "iterated 3x3 (equal for a rectangle)", lambda: cv2.erode(cmask, np.ones((3, 3), np.uint8), iterations=3))
    gname = "dilate f32 RECT (ROI peak map)"
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
    add(gname, "dilate RECT 17 (as pipeline)", "kernel 17x17", lambda: cv2.dilate(f32, ker))
    add(gname, "dilate 3x3 iterations 8", "iterated 3x3 (equal for RECT: 2*8+1=17)", lambda: cv2.dilate(f32, np.ones((3, 3), np.uint8), iterations=8))
    add(gname, "dilate separable 1x17 then 17x1", "two 1-D passes (equal)", lambda: cv2.dilate(cv2.dilate(f32, np.ones((1, 17), np.uint8)), np.ones((17, 1), np.uint8)))
    # --- group: distance transform and components
    crop = cv2.copyMakeBorder(mroi[max(0, Hr // 2 - 100):Hr // 2 + 100, 60:Wr - 60].copy(), 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    gname = "distanceTransform (crack mask)"
    add(gname, "DIST_L2 PRECISE (as pipeline)", "DIST_L2, DIST_MASK_PRECISE", lambda: cv2.distanceTransform(crop, cv2.DIST_L2, cv2.DIST_MASK_PRECISE))
    add(gname, "DIST_L2 mask 5", "DIST_MASK_5 (approximation)", lambda: cv2.distanceTransform(crop, cv2.DIST_L2, 5))
    add(gname, "DIST_L2 mask 3", "DIST_MASK_3 (approximation)", lambda: cv2.distanceTransform(crop, cv2.DIST_L2, 3))
    gname = "connectedComponentsWithStats (canvas)"
    add(gname, "default conn8 (as pipeline)", "connectivity=8, default algorithm", lambda: cv2.connectedComponentsWithStats(small_mask, connectivity=8))
    add(gname, "BBDT conn8", "CCL_BBDT", lambda: cv2.connectedComponentsWithStatsWithAlgorithm(small_mask, 8, cv2.CV_32S, cv2.CCL_BBDT))
    add(gname, "WU conn8", "CCL_WU", lambda: cv2.connectedComponentsWithStatsWithAlgorithm(small_mask, 8, cv2.CV_32S, cv2.CCL_WU))
    add(gname, "SPAGHETTI conn8", "CCL_SPAGHETTI", lambda: cv2.connectedComponentsWithStatsWithAlgorithm(small_mask, 8, cv2.CV_32S, cv2.CCL_SPAGHETTI))
    add(gname, "default conn4", "connectivity=4", lambda: cv2.connectedComponentsWithStats(small_mask, connectivity=4))
    # --- group: colour / decode
    ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    gname = "decode + grey (12MP JPEG)"
    add(gname, "imdecode COLOR + cvtColor (as service+pipeline)", "imdecode BGR then BGR2GRAY",
        lambda: cv2.cvtColor(cv2.imdecode(jpg, cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY), 3)
    add(gname, "imdecode GRAYSCALE", "libjpeg grey decode (not equal to cvtColor)", lambda: cv2.imdecode(jpg, cv2.IMREAD_GRAYSCALE), 3)
    add(gname, "imdecode REDUCED_GRAYSCALE_2", "decode at 1/2 size", lambda: cv2.imdecode(jpg, cv2.IMREAD_REDUCED_GRAYSCALE_2), 3)
    add(gname, "cvtColor only", "BGR2GRAY on decoded frame", lambda: cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    return C


def cmd_run(a) -> int:
    from prohori import measure
    cv2.setNumThreads(a.threads)
    cb.install_thinning(measure, "auto")
    out = {"label": a.label, "cv2": cv2.__version__, "cv2_file": cv2.__file__, "threads": a.threads, "groups": {}}
    base_sha: dict[str, str] = {}
    for group, name, desc, fn, reps in build_cases(a.scale):
        try:
            o = fn()
            fn()
            ts = []
            for _ in range(reps):
                t = time.perf_counter_ns()
                fn()
                ts.append((time.perf_counter_ns() - t) / 1e6)
            sh = cb.sha(o, 16)
            base_sha.setdefault(group, sh)  # first case of a group is the pipeline's own call
            out["groups"].setdefault(group, {})[name] = {"desc": desc, "p50_ms": cb.pct(ts, 50), "min_ms": min(ts),
                                                         "sha": sh, "exact_vs_baseline": sh == base_sha[group]}
        except Exception as e:  # a variant that does not exist / fails on this build is data
            out["groups"].setdefault(group, {})[name] = {"desc": desc, "error": f"{type(e).__name__}: {str(e)[:100]}"}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / f"{a.label}.variants.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"[{a.label}] variants done: {sum(len(v) for v in out['groups'].values())} cases")
    return 0


def cmd_compare(a) -> int:
    A = json.loads(Path(a.a).read_text())
    B = json.loads(Path(a.b).read_text())
    L = [f"### Variant timings, {A['label']} (cv2 {A['cv2']}) vs {B['label']} (cv2 {B['cv2']}), {A['threads']} thread(s), median ms",
         "", f"x = {A['label']} ms / {B['label']} ms for the same variant (>1: {B['label']} faster).  'vs base' = speed relative to the "
         f"group's first row (the pipeline's own call) on the SAME build; exact = output bytes identical to that base on that build.", "",
         f"| group | variant | {A['label']} ms | {B['label']} ms | x | {A['label']} vs base | {B['label']} vs base | exact ({A['label']}/{B['label']}) |",
         "|---|---|---:|---:|---:|---:|---:|---|"]
    best = []
    for g, vs in A["groups"].items():
        base_a = next(iter(vs.values())).get("p50_ms")
        base_b = next(iter(B["groups"].get(g, {}).values()), {}).get("p50_ms")
        for nme, ra in vs.items():
            rb = B["groups"].get(g, {}).get(nme)
            if not rb or "p50_ms" not in ra or "p50_ms" not in rb:
                L.append(f"| {g} | {nme} | {ra.get('p50_ms', 'ERR')} | {(rb or {}).get('p50_ms', 'ERR')} | | | | |")
                continue
            L.append(f"| {g} | {nme} | {ra['p50_ms']:.3f} | {rb['p50_ms']:.3f} | {ra['p50_ms'] / rb['p50_ms']:.2f} | "
                     f"{base_a / ra['p50_ms']:.2f} | {base_b / rb['p50_ms']:.2f} | "
                     f"{'yes' if ra['exact_vs_baseline'] else 'no'}/{'yes' if rb['exact_vs_baseline'] else 'no'} |")
        # best EXACT alternative on B (COOL)
        ex = [(r["p50_ms"], n) for n, r in B["groups"].get(g, {}).items() if "p50_ms" in r and r["exact_vs_baseline"]]
        if ex:
            best.append((g, min(ex), next(iter(B["groups"][g].values()))["p50_ms"]))
    L += ["", f"Fastest bit-exact formulation on {B['label']} per group (vs the pipeline's own call):", ""]
    L += [f"- {g}: {n} {t:.3f} ms (pipeline call {base:.3f} ms, {base / t:.2f}x)" for g, (t, n), base in best]
    txt = "\n".join(L)
    print(txt)
    if a.md:
        Path(a.md).write_text(txt + "\n", encoding="utf-8")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--threads", type=int, default=1)
    r.add_argument("--scale", type=float, default=1.0)
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--md")
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
