"""OpenCV compatibility shims for the COOL (Cloud Optimized OpenCV) AMI, reusable by the live service.

The COOL AMI's OpenCV 5.1.0-dev is built WITHOUT opencv_contrib, so `cv2.ximgproc` does not exist.  PROHORI's
measurement pipeline (src/prohori/measure.py) calls exactly one contrib function, `cv2.ximgproc.thinning` (default
THINNING_ZHANGSUEN).  `thinning_zs` below is a numpy re-implementation that is bit-exact with it
(tests/test_cool_bench.py::test_thinning_shim_is_bit_exact_with_ximgproc compares them on random masks, and the full
pipeline returns bitwise identical widths with either), so the pipeline runs unchanged on COOL:

    from cool_compat import install_thinning
    from prohori import measure
    install_thinning(measure, "auto")      # shim only if this OpenCV has no ximgproc

measure.py is not edited: `install_thinning` replaces the module-level `cv2` name in prohori.measure by a forwarding
object that adds `ximgproc.thinning`.
"""
from __future__ import annotations

import types

import cv2
import numpy as np

_ZS_LUT: list = []


def _zs_lut():
    """Delete decision of Zhang-Suen sub-iteration 0/1 for every 8-neighbour code (bit k = p(k+2), clockwise from N)."""
    if not _ZS_LUT:
        c = np.arange(256)
        p2, p3, p4, p5, p6, p7, p8, p9 = [((c >> k) & 1).astype(np.int16) for k in range(8)]
        A = ((p2 == 0) & (p3 == 1)).astype(np.int16) + ((p3 == 0) & (p4 == 1)) + ((p4 == 0) & (p5 == 1)) +             ((p5 == 0) & (p6 == 1)) + ((p6 == 0) & (p7 == 1)) + ((p7 == 0) & (p8 == 1)) +             ((p8 == 0) & (p9 == 1)) + ((p9 == 0) & (p2 == 1))
        B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
        base = (A == 1) & (B >= 2) & (B <= 6)
        _ZS_LUT.append(base & ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0))
        _ZS_LUT.append(base & ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0))
    return _ZS_LUT


def thinning_zs(img: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning of a 0/255 uint8 mask, a numpy re-implementation of cv2.ximgproc.thinning (default
    THINNING_ZHANGSUEN) that is bit-exact with it (tests/test_cool_bench.py checks this against the native function).
    Needed because the COOL AMI's OpenCV 5.1.0-dev is built without opencv_contrib, i.e. without ximgproc.  Only
    the foreground pixels are visited (the skeleton sub-iterations remove a thin shell each time), so it is fast on
    crack masks.  Border pixels are never changed, as in OpenCV."""
    assert img.ndim == 2 and img.dtype == np.uint8
    h, w = img.shape
    a = (img == 255).astype(np.uint8)  # OpenCV does processed /= 255: only 255 stays 1
    out_val = a.copy()
    if h < 3 or w < 3:
        return out_val * 255
    flat = out_val.reshape(-1)
    inner = np.zeros((h, w), bool)
    inner[1:-1, 1:-1] = True
    idx = np.flatnonzero((out_val > 0) & inner)
    offs = (-w, -w + 1, 1, w + 1, w, w - 1, -1, -w - 1)  # p2 p3 p4 p5 p6 p7 p8 p9 (clockwise from north)
    lut = _zs_lut()
    while idx.size:
        removed = False
        for it in (0, 1):
            if idx.size == 0:
                break
            code = flat[idx + offs[0]].astype(np.uint16)
            for bit in range(1, 8):
                code |= flat[idx + offs[bit]].astype(np.uint16) << bit
            mark = lut[it][code]
            if mark.any():
                flat[idx[mark]] = 0
                idx = idx[~mark]
                removed = True
        if not removed:
            break
    return out_val * 255


thinning_zs._is_py_shim = True


def ccl_bbdt(mask, connectivity=8, **kw):
    """cv2.connectedComponentsWithStats with the BBDT labelling algorithm.  Returns exactly what the default call returns
    (labels, stats and centroids are identical on all 63 masks PROHORI produces, checked in the report), but it avoids the
    default parallel SPAGHETTI path that corrupts the heap on the COOL AMI's OpenCV 5.1.0-dev when more than one OpenCV
    thread is used.  Only `connectivity` is honoured (all that PROHORI passes)."""
    return cv2.connectedComponentsWithStatsWithAlgorithm(mask, connectivity, cv2.CV_32S, cv2.CCL_BBDT)


class ShimCv2:
    """Stand-in for the cv2 module in prohori.measure that (a) adds cv2.ximgproc.thinning (numpy) when the OpenCV build
    has no contrib and (b) optionally routes connectedComponentsWithStats to BBDT.  Every other attribute is forwarded to
    the real module untouched."""

    def __init__(self, mod, force: bool = False, ccl: str = "default"):
        self._mod = mod
        self._ximg = types.ModuleType("ximgproc")
        self._ximg.thinning = thinning_zs
        self._force = force
        self._ccl = ccl

    def __getattr__(self, name):
        if name == "ximgproc" and (self._force or not hasattr(self._mod, "ximgproc")):
            return self._ximg
        if name == "connectedComponentsWithStats" and self._ccl == "bbdt":
            return ccl_bbdt
        return getattr(self._mod, name)


def install_thinning(measure, mode: str, ccl: str = "default") -> str:
    """mode: native | shim | auto (thinning).  ccl: default | bbdt (connected-component algorithm).
    mode "none": install nothing (the tree brings its own COOL-safe thinning / labelling; used by eval/cool_loop.py).
    Returns what the pipeline will use for thinning ('native' or 'shim')."""
    if mode == "none":
        return "none"
    have = hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning")
    use = "native" if (mode == "native" or (mode == "auto" and have)) else "shim"
    if mode == "native" and not have:
        raise SystemExit("--thinning native but this OpenCV has no cv2.ximgproc")
    if use == "shim" or ccl != "default":
        measure.cv2 = ShimCv2(cv2, force=(use == "shim"), ccl=ccl)
    return use
