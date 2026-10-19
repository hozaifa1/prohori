"""Crack-width measurement against a ChArUco reference board.

Public interface
----------------
analyze(image_bgr, panel_mode=True) -> dict      (JSON-serialisable result, never raises)
draw_overlay(image_bgr, result)    -> np.ndarray (annotated BGR image, max side ~1600 px)

Pipeline
--------
1. Detect the ChArUco board on a downscaled grey copy, refine corners at full resolution,
   fit a homography image -> board millimetres (RANSAC) and a pose (solvePnP) for obliquity.
2. Rectify the page (board frame, mm) at a low "locator" resolution and find dark, thin,
   elongated connected components (generic crack locator).  In panel mode, components are
   matched to the printed ground-truth specimens C1..C8 by distance to their centrelines.
   A specimen the locator misses may be measured from its ground-truth ROI ("locator":
   "gt_roi").
3. Rectify a tight ROI around every located crack at full resolution (S >= native px/mm),
   threshold at half-maximum darkness, skeletonise, and estimate the width two ways:
     dt      median(2*DT on the skeleton) - 1 px      (distance-transform estimator)
     profile sub-pixel integral of the (linear-light) darkness profile perpendicular to the
             skeleton, divided by the crack's reference darkness (area-conserving, so it is
             far less biased than a threshold for cracks near the blur scale)
"""
from __future__ import annotations

import json
import math
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from .board import MARKER_MM, SQUARE_MM, SQUARES_X, SQUARES_Y, make_board

# ----------------------------------------------------------------------------- constants

CORNERS_TOTAL = (SQUARES_X - 1) * (SQUARES_Y - 1)  # 24
BOARD_W_MM = SQUARES_X * SQUARE_MM  # 140
BOARD_H_MM = SQUARES_Y * SQUARE_MM  # 100
DETECT_MAX_SIDE = 2000
MIN_CORNERS = 6

# Gate thresholds (see eval/results summary for how blur was calibrated).
GATE_MIN_CORNERS = 8
GATE_MIN_PX_PER_MM = 8.0
GATE_MIN_BLUR_VAR = 150.0
GATE_MAX_OBLIQUITY_DEG = 45.0
GATE_MAX_GLARE = 0.05

# Global width bias correction (mm), subtracted from the profile estimator. Set from the
# real-photo calibration documented in eval/results/*.md.  0.0 = none.
WIDTH_BIAS_MM = 0.0

# Uncertainty model constants (see _uncertainty docstring).
INK_RATIO = 0.90  # crack-toner darkness / board-black darkness for thin printed strokes (calibrated, see summary)
EDGE_SIGMA_PX = 0.4  # 1-sigma edge localisation per side, in native pixels

_GT_PATH = Path(__file__).resolve().parents[2] / "data" / "print" / "test_panel_ground_truth.json"

_cache: dict = {}


def _board():
    if "board" not in _cache:
        _cache["board"] = make_board()
    return _cache["board"]


def _detector():
    if "det" not in _cache:
        cp = cv2.aruco.CharucoParameters()
        cp.minMarkers = 1
        _cache["det"] = cv2.aruco.CharucoDetector(_board(), cp, cv2.aruco.DetectorParameters())
    return _cache["det"]


def _gt():
    """Ground-truth specimens: list of dict(id, width_mm, poly (page mm, Nx2), dense). None if unavailable."""
    if "gt" not in _cache:
        try:
            g = json.loads(_GT_PATH.read_text())
            off = np.array(g["board"]["page_offset_mm"], float)
            specs = []
            for s in g["specimens"]:
                poly_b = np.array(s["polyline_board_mm"], float)  # board mm
                dense = _densify(poly_b, 0.25)
                specs.append({"id": s["id"], "width_mm": float(s["width_mm"]), "poly_b": poly_b, "dense_b": dense})
            _cache["gt"] = {"page_off": off, "specs": specs}
        except Exception:
            _cache["gt"] = None
    return _cache["gt"]


# ----------------------------------------------------------------------------- small helpers

def _densify(poly: np.ndarray, step: float) -> np.ndarray:
    seg = np.hypot(*np.diff(poly, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] <= 0:
        return poly.copy()
    t = np.arange(0, s[-1], step)
    return np.stack([np.interp(t, s, poly[:, 0]), np.interp(t, s, poly[:, 1])], 1)


def _apply_h(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    p = np.asarray(pts, float).reshape(-1, 2)
    q = np.hstack([p, np.ones((len(p), 1))]) @ H.T
    return q[:, :2] / q[:, 2:3]


def _local_scale(Hinv_board2img: np.ndarray, pt_board: np.ndarray) -> float:
    """Native px per mm at a board point: sqrt|det J| of the board->image homography."""
    h = Hinv_board2img
    x, y = float(pt_board[0]), float(pt_board[1])
    w = h[2, 0] * x + h[2, 1] * y + h[2, 2]
    u = h[0, 0] * x + h[0, 1] * y + h[0, 2]
    v = h[1, 0] * x + h[1, 1] * y + h[1, 2]
    dudx = (h[0, 0] * w - u * h[2, 0]) / w**2
    dudy = (h[0, 1] * w - u * h[2, 1]) / w**2
    dvdx = (h[1, 0] * w - v * h[2, 0]) / w**2
    dvdy = (h[1, 1] * w - v * h[2, 1]) / w**2
    det = abs(dudx * dvdy - dudy * dvdx)
    return float(math.sqrt(det)) if det > 0 else 0.0


_SRGB_LUT = None


def _lin_lut():
    global _SRGB_LUT
    if _SRGB_LUT is None:
        v = np.arange(256) / 255.0
        _SRGB_LUT = np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4).astype(np.float32)
    return _SRGB_LUT


def _odd(n: float, lo: int = 3) -> int:
    n = int(round(n))
    n = max(n, lo)
    return n if n % 2 else n + 1


def _empty_result(w: int = 0, h: int = 0) -> dict:
    return {
        "ok": False,
        "observation": {
            "corners": 0, "corners_total": CORNERS_TOTAL, "blur_var": 0.0, "px_per_mm": 0.0,
            "obliquity_deg": 0.0, "glare_frac": 0.0, "crack_px_extent": 0, "image_w": int(w), "image_h": int(h),
            "reproj_px": None,
        },
        "gate": {"certified": False, "reasons": []},
        "cracks": [],
        "timing_ms": {"detect": 0.0, "rectify": 0.0, "measure": 0.0, "total": 0.0},
        "error": None,
    }


# ----------------------------------------------------------------------------- detection

def _detect_board(grey: np.ndarray):
    """Return (corners_px Nx2 float64 at full res, ids N) or (None, None)."""
    h, w = grey.shape
    s = min(1.0, DETECT_MAX_SIDE / max(h, w))
    small = cv2.resize(grey, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else grey
    corners, ids, _, _ = _detector().detectBoard(small)
    if ids is None or len(ids) < 4:
        return None, None
    c = corners.reshape(-1, 2).astype(np.float64) / s
    ids = ids.ravel().astype(int)
    # Sub-pixel refinement at full resolution. Window scaled to the local square size.
    bd = _board().getChessboardCorners()[ids][:, :2]
    if len(ids) >= 4:
        H0, _ = cv2.findHomography(bd, c, cv2.RANSAC, 3.0)
        if H0 is not None:
            ppm = _local_scale(H0, np.array([BOARD_W_MM / 2, BOARD_H_MM / 2]))
            win = int(np.clip(0.10 * ppm * SQUARE_MM, 3, 11))
            c32 = c.astype(np.float32).reshape(-1, 1, 2)
            try:
                r = c32.copy()
                cv2.cornerSubPix(grey, r, (win, win), (-1, -1),
                                 (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 30, 0.01))
                shift = np.hypot(*(r - c32).reshape(-1, 2).T)
                ok = shift < max(2.0, 0.3 * win)
                c = np.where(ok[:, None], r.reshape(-1, 2), c)
            except cv2.error:
                pass
    return c, ids


def _pose_obliquity(corners: np.ndarray, ids: np.ndarray, w: int, h: int) -> float:
    """Angle (deg) between the camera axis and the board normal, from solvePnP with approximate intrinsics."""
    try:
        f = 0.78 * max(w, h)
        K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], float)
        obj = _board().getChessboardCorners()[ids].astype(np.float64)
        ok, rvec, tvec = cv2.solvePnP(obj, corners.reshape(-1, 1, 2), K, None, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            return 0.0
        R, _ = cv2.Rodrigues(rvec)
        n = R[:, 2]
        return float(math.degrees(math.acos(min(1.0, abs(n[2]) / (np.linalg.norm(n) + 1e-12)))))
    except Exception:
        return 0.0


# ----------------------------------------------------------------------------- skeleton paths

def _longest_path(sk: np.ndarray) -> np.ndarray:
    """Ordered (x, y) pixel path along the longest geodesic of a thin (skeleton) mask; spurs are dropped."""
    ys, xs = np.nonzero(sk)
    n = len(ys)
    if n == 0:
        return np.zeros((0, 2))
    if n == 1:
        return np.array([[xs[0], ys[0]]], float)
    idx = -np.ones(sk.shape, np.int32)
    idx[ys, xs] = np.arange(n)
    nbrs = [[] for _ in range(n)]
    hh, ww = sk.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            y2, x2 = ys + dy, xs + dx
            m = (y2 >= 0) & (y2 < hh) & (x2 >= 0) & (x2 < ww)
            j = np.full(n, -1, np.int32)
            j[m] = idx[y2[m], x2[m]]
            for i in np.nonzero(j >= 0)[0]:
                nbrs[i].append(int(j[i]))

    def bfs(src):
        dist = {src: 0}
        par = {src: -1}
        dq = deque([src])
        last = src
        while dq:
            u = dq.popleft()
            last = u
            for v in nbrs[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    par[v] = u
                    dq.append(v)
        return last, par

    a, _ = bfs(0)
    b, par = bfs(a)
    path = []
    u = b
    while u != -1:
        path.append(u)
        u = par[u]
    path = np.array(path[::-1])
    return np.stack([xs[path], ys[path]], 1).astype(float)


def _smooth_resample(path: np.ndarray, win_px: int, step_px: float) -> np.ndarray:
    """Moving-average smooth an ordered path (endpoints preserved by reflection) and resample at arc-length step."""
    if len(path) < 3:
        return path
    k = max(1, min(win_px // 2, len(path) // 2 - 1))
    if k >= 1:
        pre = 2 * path[0] - path[k:0:-1]
        post = 2 * path[-1] - path[-2:-k - 2:-1]
        padded = np.vstack([pre, path, post])
        ker = np.ones(2 * k + 1) / (2 * k + 1)
        sm = np.stack([np.convolve(padded[:, d], ker, mode="valid") for d in range(2)], 1)
    else:
        sm = path
    seg = np.hypot(*np.diff(sm, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < step_px:
        return sm
    t = np.arange(0, s[-1], step_px)
    return np.stack([np.interp(t, s, sm[:, 0]), np.interp(t, s, sm[:, 1])], 1)


# ----------------------------------------------------------------------------- crack locator

def _locate_cracks(canvas: np.ndarray, valid: np.ndarray, S: float, origin: np.ndarray, panel_mode: bool,
                   board_excl: np.ndarray | None):
    """Generic locator on a rectified low-res canvas.

    canvas: uint8 grey, valid: bool mask, S: px/mm, origin: board-mm of canvas pixel (0,0).
    Returns (list of dict(skel_b: Nx2 board-mm ordered path, locator)), dark-mask (for debugging).
    """
    g = cv2.GaussianBlur(canvas, (0, 0), 0.7)
    fill = int(np.median(g[valid])) if valid.any() else 200
    g = np.where(valid, g, fill).astype(np.uint8)
    bg = _bg_map(g.astype(np.float32), int(8 * S))
    gf = g.astype(np.float32)
    dark = (bg - gf) / np.maximum(bg, 1.0)
    m = (dark > 0.12) & valid
    if board_excl is not None:
        m &= ~board_excl
    m = m.astype(np.uint8) * 255
    kc = _odd(0.5 * S)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    comps = []
    min_len_mm = 12.0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if math.hypot(w, h) < min_len_mm * S:
            continue
        crop = (lab[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        pad = cv2.copyMakeBorder(crop, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
        sk = cv2.ximgproc.thinning(pad) > 0
        path = _longest_path(sk)
        if len(path) < 3:
            continue
        path = path - 2 + np.array([x, y])
        length_mm = float(np.hypot(*np.diff(path, axis=0).T).sum() / S)
        mean_w_mm = area / max(len(path), 1) / S
        if length_mm < min_len_mm:
            continue
        pts_b = path / S + origin
        comps.append({"path_b": pts_b, "length_mm": length_mm, "mean_w_mm": mean_w_mm, "area": float(area),
                      "bbox": (x, y, w, h), "label": i})
    return comps, lab


def _match_once(comps, dense, tol_mm, min_frac):
    assigned: dict[int, list] = {}
    for c in comps:
        P = c["path_b"][::4]
        best, bf = -1, 0.0
        for j, D in enumerate(dense):
            d2 = ((P[:, None, :] - D[None, ::8, :]) ** 2).sum(-1).min(1)
            f = float((d2 < tol_mm**2).mean())
            if f > bf:
                best, bf = j, f
        if best >= 0 and bf >= min_frac:
            assigned.setdefault(best, []).append(c)
    return assigned


def _fit_affine(assigned, dense):
    """Least-squares affine map (2x3) taking the ground-truth polylines onto the located components."""
    src, dst = [], []
    for j, cs in assigned.items():
        D = dense[j]
        for c in cs:
            P = c["path_b"][::8]
            idx = np.argmin(((P[:, None, :] - D[None, :, :]) ** 2).sum(-1), axis=1)
            src.append(D[idx])
            dst.append(P)
    src, dst = np.vstack(src), np.vstack(dst)
    centred = src - src.mean(0)
    rows_ok = np.linalg.matrix_rank(centred, tol=1.0) == 2 and len(assigned) >= 4 and np.ptp(src[:, 1]) > 30
    if rows_ok:
        X = np.hstack([src, np.ones((len(src), 1))])
        Mt, *_ = np.linalg.lstsq(X, dst, rcond=None)
        M = Mt.T
        lin = M[:, :2]
        if abs(np.linalg.det(lin) - 1) < 0.2 and np.hypot(*(M[:, 2])) < 400:
            return M
    shift = np.median(dst - src, axis=0)
    return np.hstack([np.eye(2), shift[:, None]])


def _match_specimens(comps, gt, tol_mm=6.0, min_frac=0.5):
    """Assign located components to ground-truth specimens by centreline distance.

    A homography fitted on the board alone drifts by several mm (up to ~10 mm on oblique photos) at the far side of
    the page (lens distortion / extrapolation), so matching is iterative: a generous first pass, an affine fit of the
    ground truth onto the matched components, then a tighter re-match with the corrected ground truth.
    Returns (assigned {spec_idx: [comp, ...]}, corrected dense polylines per specimen).
    """
    dense = [s["dense_b"] for s in gt["specs"]]
    asg = _match_once(comps, dense, tol_mm, min_frac)
    cur = dense
    for _ in range(2):
        if not asg:
            break
        M = _fit_affine(asg, cur)
        cur = [d @ M[:, :2].T + M[:, 2] for d in cur]
        asg2 = _match_once(comps, cur, 4.0, 0.6)
        if len(asg2) >= len(asg):
            asg = asg2
    return asg, cur


def _bg_map(lin: np.ndarray, win_px: int) -> np.ndarray:
    """Paper-level map: running max over ~win_px then smoothed, computed at 1/4 resolution for speed."""
    h, w = lin.shape
    q = 4
    sm = cv2.resize(lin, (max(1, w // q), max(1, h // q)), interpolation=cv2.INTER_AREA)
    k = _odd(win_px / q)
    sm = cv2.dilate(sm, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    sm = cv2.GaussianBlur(sm, (0, 0), k / 3.0)
    return cv2.resize(sm, (w, h), interpolation=cv2.INTER_LINEAR)


def _fwhm(Dp: np.ndarray, S: float) -> np.ndarray:
    """Sub-pixel full width at half maximum (mm) of each darkness profile (rows), NaN if not found."""
    n, nt = Dp.shape
    out = np.full(n, np.nan)
    c = nt // 2
    r = int(1.0 * S)
    for i in range(n):
        p = Dp[i]
        lo_i, hi_i = max(0, c - r), min(nt, c + r + 1)
        k = lo_i + int(np.argmax(p[lo_i:hi_i]))
        pk = p[k]
        if pk <= 0:
            continue
        half = 0.5 * pk
        a = k
        while a > 0 and p[a] > half:
            a -= 1
        b = k
        while b < nt - 1 and p[b] > half:
            b += 1
        if p[a] > half or p[b] > half:
            continue  # profile never drops below half max: not a clean crack profile
        xl = a + (half - p[a]) / (p[a + 1] - p[a]) if p[a + 1] != p[a] else a
        xr = b - 1 + (p[b - 1] - half) / (p[b - 1] - p[b]) if p[b - 1] != p[b] else b
        out[i] = (xr - xl) / S
    return out


def _measure_one(grey_full: np.ndarray, H_img2board: np.ndarray, seed_b: np.ndarray, ppm: float,
                 ink_dark: float | None, sigma_mm: float, corridor_mm: float = 3.0, cap_px: int = 4200):
    """Measure one crack at full resolution.

    seed_b: Nx2 coarse centreline in board mm.  ppm: native px/mm near the crack.
    sigma_mm: optical blur (1-sigma, mm) estimated from the board edges.
    Returns dict or None.
    """
    margin = corridor_mm + 1.0
    lo = seed_b.min(0) - margin
    hi = seed_b.max(0) + margin
    S = float(np.clip(math.ceil(ppm), 12, 40))
    ext = max(hi - lo)
    if ext * S > cap_px:
        S = cap_px / ext
    Wd, Hd = int(math.ceil((hi[0] - lo[0]) * S)), int(math.ceil((hi[1] - lo[1]) * S))
    if Wd < 20 or Hd < 20:
        return None
    Hm = np.array([[S, 0, -lo[0] * S], [0, S, -lo[1] * S], [0, 0, 1]]) @ H_img2board
    roi = cv2.warpPerspective(grey_full, Hm, (Wd, Hd), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                              borderValue=0)
    val = cv2.warpPerspective(np.full(grey_full.shape, 255, np.uint8), Hm, (Wd, Hd), flags=cv2.INTER_NEAREST)
    val = cv2.erode(val, np.ones((5, 5), np.uint8)) > 0
    lin = _lin_lut()[roi]

    seed_px = (seed_b - lo) * S
    corr = np.zeros((Hd, Wd), np.uint8)
    cv2.polylines(corr, [np.round(seed_px).astype(np.int32).reshape(-1, 1, 2)], False, 255,
                  thickness=int(round(2 * corridor_mm * S)))
    corr_b = corr > 0
    fillv = float(np.median(lin[val])) if val.any() else 0.8
    linf = np.where(val, lin, fillv).astype(np.float32)
    bgm = _bg_map(linf, int(6.0 * S))
    D = bgm - linf  # darkness, linear light
    Dsm = cv2.GaussianBlur(D, (0, 0), 0.15 * S)
    kk = _odd(0.8 * S)
    dil = cv2.dilate(Dsm, cv2.getStructuringElement(cv2.MORPH_RECT, (kk, kk)))
    sp = np.round(seed_px).astype(int)
    sp[:, 0] = np.clip(sp[:, 0], 0, Wd - 1)
    sp[:, 1] = np.clip(sp[:, 1], 0, Hd - 1)
    peaks = dil[sp[:, 1], sp[:, 0]]
    Dpk = float(np.median(peaks))
    if Dpk <= 0.06 or float((peaks > 0.5 * Dpk).mean()) < 0.6:
        return None  # nothing crack-like under the seed polyline
    mask = ((Dsm > 0.5 * Dpk) & corr_b & val).astype(np.uint8) * 255
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        return None
    ov = np.bincount(lab[sp[:, 1], sp[:, 0]], minlength=n)
    ov[0] = 0
    k_best = int(np.argmax(ov)) if ov.max() > 0 else 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh = stats[k_best, :4]
    m = (lab[y:y + bh, x:x + bw] == k_best).astype(np.uint8) * 255
    m = cv2.copyMakeBorder(m, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    dt = cv2.distanceTransform(m, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    sk = cv2.ximgproc.thinning(m) > 0
    path = _longest_path(sk)
    if len(path) < int(6 * S):
        return None
    trim = int(1.5 * S)
    core = path[trim:-trim] if len(path) > 4 * trim else path
    ci = np.round(core).astype(int)
    w_dt_px = 2.0 * dt[ci[:, 1], ci[:, 0]] - 1.0
    w_dt_mm = float(np.median(w_dt_px) / S)
    path = path - 2 + np.array([x, y])  # back to ROI pixel coords

    # ---- profile-integral estimator
    sm = _smooth_resample(path, win_px=int(1.2 * S), step_px=0.5 * S)
    if len(sm) < 5:
        return None
    tang = np.gradient(sm, axis=0)
    tang = tang / np.maximum(np.hypot(tang[:, 0], tang[:, 1])[:, None], 1e-9)
    nor = np.stack([-tang[:, 1], tang[:, 0]], 1)
    R = max(1.2, w_dt_mm / 2 + 1.0)  # mm
    nt = int(2 * R * S) | 1
    t = np.linspace(-R, R, nt) * S
    # path coords are pixel indices (integer = pixel centre), the same convention cv2.remap uses
    mx = (sm[:, 0:1] + t[None, :] * nor[:, 0:1]).astype(np.float32)
    my = (sm[:, 1:2] + t[None, :] * nor[:, 1:2]).astype(np.float32)
    prof = cv2.remap(linf, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    pv = cv2.remap(val.astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    band = max(2, int(0.5 * S))
    bgL = np.median(prof[:, :band], axis=1)
    bgR = np.median(prof[:, -band:], axis=1)
    ramp = np.linspace(0, 1, nt)[None, :]
    bgp = bgL[:, None] * (1 - ramp) + bgR[:, None] * ramp
    Dp = bgp - prof
    area = Dp.sum(axis=1) / S  # linear-intensity * mm
    bg_c = bgp[:, nt // 2]
    good = pv.all(axis=1) & (bg_c > 0.05)
    e = 3  # 1.5 mm at 0.5 mm steps
    if len(good) > 2 * e + 4:
        good[:e] = False
        good[-e:] = False
    if good.sum() < 4:
        return None
    Dsmooth = cv2.GaussianBlur(Dp.astype(np.float32), (0, 0), sigmaX=0.12 * S, sigmaY=0)
    peak_i = Dsmooth.max(axis=1)
    Dcore = float(np.percentile(peak_i[good], 80))
    bgmed = float(np.median(bg_c[good]))
    Dink = (bgmed - ink_dark) if ink_dark is not None else Dcore
    Dink = max(Dink, 1e-3)
    w_core_i = area[good] / max(Dcore, 1e-3)
    w_ink_i = area[good] / (INK_RATIO * Dink)
    w_fwhm_i = _fwhm(Dsmooth[good], S)
    ok_f = np.isfinite(w_fwhm_i)
    if ok_f.sum() < 4:
        return None
    # Blend: thin cracks (width < ~5-11 blur sigmas, or whose peak darkness q = core/board-ink is well below the
    # printed-ink level, i.e. blur-limited) have a blur-limited peak, so their full-width-at-half-max is
    # inflated; use the area-conserving board-ink reference there.  Wide cracks: edge-based FWHM (independent of the
    # crack's own ink darkness, which on the printed panel varies with stroke width).
    d = float(np.median(w_ink_i)) / max(sigma_mm, 0.05)
    q = Dcore / Dink
    wt = float(np.clip((d - 5.0) / 6.0, 0.0, 1.0) * np.clip((q - 0.5) / 0.1, 0.0, 1.0))
    w_i = (1 - wt) * w_ink_i[ok_f] + wt * w_fwhm_i[ok_f]

    poly_b = sm / S + lo
    length_mm = float(np.hypot(*np.diff(poly_b, axis=0).T).sum())
    return {
        "S": S, "poly_b": poly_b, "length_mm": length_mm, "dt_mm": w_dt_mm,
        "profile_core_mm": float(np.median(w_core_i)), "profile_ink_mm": float(np.median(w_ink_i)),
        "fwhm_mm": float(np.nanmedian(w_fwhm_i)),
        "profile_mm": float(np.median(w_i)), "local_mm": w_i, "wt_core": wt,
        "Dcore": Dcore, "Dink": Dink, "q_core": Dcore / Dink, "n_prof": int(good.sum()),
    }


def _edge_sigma(grey: np.ndarray, H_img2board: np.ndarray, ppm: float) -> float:
    """Optical blur (Gaussian sigma, mm) from the board's black/white square edges.

    The board is rectified so its edges are axis-aligned; the edge spread function of every square edge is
    averaged along the edge, differentiated, and its second moment taken.  Median over edges."""
    S = float(np.clip(ppm, 6, 16))
    W, Hh = int(round((BOARD_W_MM + 4) * S)), int(round((BOARD_H_MM + 4) * S))
    Hm = np.array([[S, 0, 2 * S], [0, S, 2 * S], [0, 0, 1]]) @ H_img2board
    img = cv2.warpPerspective(grey, Hm, (W, Hh), flags=cv2.INTER_LINEAR).astype(np.float32)
    val = cv2.warpPerspective(np.full(grey.shape, 255, np.uint8), Hm, (W, Hh), flags=cv2.INTER_NEAREST) > 0
    half = 1.2
    hw = int(half * S)
    sigs = []

    def esf_sigma(prof: np.ndarray):
        if prof.max() - prof.min() < 40:
            return None
        lsf = np.abs(np.diff(prof))
        lsf = np.clip(lsf - 0.05 * lsf.max(), 0, None)
        tot = lsf.sum()
        if tot <= 0:
            return None
        xs = np.arange(len(lsf)) + 0.5
        mu = (lsf * xs).sum() / tot
        v = (lsf * (xs - mu) ** 2).sum() / tot
        return math.sqrt(max(v, 0.0)) / S

    for j in range(SQUARES_Y):
        for k in range(1, SQUARES_X):
            # vertical edge at x = 20k, rows y in [20j+4, 20j+16]
            xa, xb = int(round((2 + k * SQUARE_MM) * S)) - hw, int(round((2 + k * SQUARE_MM) * S)) + hw
            ya, yb = int(round((2 + j * SQUARE_MM + 4) * S)), int(round((2 + j * SQUARE_MM + 16) * S))
            if xa < 0 or xb > W or ya < 0 or yb > Hh or not val[ya:yb, xa:xb].all():
                continue
            sg = esf_sigma(img[ya:yb, xa:xb].mean(axis=0))
            if sg is not None:
                sigs.append(sg)
    for j in range(1, SQUARES_Y):
        for k in range(SQUARES_X):
            ya, yb = int(round((2 + j * SQUARE_MM) * S)) - hw, int(round((2 + j * SQUARE_MM) * S)) + hw
            xa, xb = int(round((2 + k * SQUARE_MM + 4) * S)), int(round((2 + k * SQUARE_MM + 16) * S))
            if xa < 0 or xb > W or ya < 0 or yb > Hh or not val[ya:yb, xa:xb].all():
                continue
            sg = esf_sigma(img[ya:yb, xa:xb].mean(axis=1))
            if sg is not None:
                sigs.append(sg)
    return float(np.median(sigs)) if len(sigs) >= 3 else 0.2


def _uncertainty(local_widths_mm: np.ndarray, ppm: float, width_mm: float, sigma_mm: float,
                 wt_edge: float = 1.0) -> float:
    """1-sigma width uncertainty in mm, combining five independent terms in quadrature:

      u_edge   = sqrt(2) * EDGE_SIGMA_PX / px_per_mm     edge localisation, EDGE_SIGMA_PX native px per side
      u_spread = IQR(local width along the crack) / 1.349   robust sigma of the along-crack width variation
      u_blur   = 0.5 * sigma_mm                            residual blur / PSF-model error (sigma from board edges)
      u_scale  = 0.01 * width_mm                           1 % board-homography scale error (lens distortion drift
                                                           between the board and the crack, measured 0-2 %)
      u_ref    = 0.2 * (1 - wt_edge) * width_mm            when the width comes from the board-ink reference rather
                                                           than the crack's own edges (thin / blur-limited cracks),
                                                           the toner-darkness assumption is good to ~20 %
    """
    u_edge = math.sqrt(2.0) * EDGE_SIGMA_PX / max(ppm, 1e-6)
    if local_widths_mm is not None and len(local_widths_mm) >= 4:
        q1, q3 = np.percentile(local_widths_mm, [25, 75])
        u_spread = float(q3 - q1) / 1.349
    else:
        u_spread = 0.0
    return float(math.sqrt(u_edge**2 + u_spread**2 + (0.5 * sigma_mm) ** 2 + (0.01 * width_mm) ** 2 + (0.2 * (1 - wt_edge) * width_mm) ** 2))


def _decimate(poly: np.ndarray, n: int = 60) -> list:
    if len(poly) <= n:
        idx = np.arange(len(poly))
    else:
        idx = np.unique(np.round(np.linspace(0, len(poly) - 1, n)).astype(int))
    return [[round(float(poly[i, 0]), 1), round(float(poly[i, 1]), 1)] for i in idx]


# ----------------------------------------------------------------------------- main entry

def analyze(image_bgr: np.ndarray, *, panel_mode: bool = True) -> dict:
    t_start = time.perf_counter()
    res = _empty_result()
    try:
        _analyze(image_bgr, panel_mode, res, t_start)
    except Exception as e:  # never raise on bad input
        res["ok"] = False
        res["error"] = f"{type(e).__name__}: {e}"
    res["timing_ms"]["total"] = round((time.perf_counter() - t_start) * 1000, 1)
    return res


def _analyze(img: np.ndarray, panel_mode: bool, res: dict, t0: float):
    if img is None or not isinstance(img, np.ndarray) or img.ndim not in (2, 3) or img.size == 0:
        res["error"] = "invalid_image"
        res["gate"]["reasons"] = ["invalid_image"]
        return
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    if img.dtype != np.uint8:
        img = cv2.normalize(img.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    grey = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = grey.shape
    obs = res["observation"]
    obs["image_w"], obs["image_h"] = int(w), int(h)
    reasons: list[str] = []

    # ---------------- detect
    t = time.perf_counter()
    corners, ids = _detect_board(grey)
    obs["corners"] = 0 if ids is None else int(len(ids))
    if ids is not None:
        cols = ids % (SQUARES_X - 1)
        rows = ids // (SQUARES_X - 1)
        degenerate = len(np.unique(cols)) < 2 or len(np.unique(rows)) < 2
    else:
        degenerate = True
    if corners is None or len(ids) < MIN_CORNERS or degenerate:
        obs["blur_var"] = float(cv2.Laplacian(cv2.resize(grey, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA),
                                              cv2.CV_32F).var())
        res["timing_ms"]["detect"] = round((time.perf_counter() - t) * 1000, 1)
        res["gate"]["reasons"] = ["too_few_corners"]
        res["error"] = "board_degenerate" if (ids is not None and len(ids) >= MIN_CORNERS) else "board_not_found"
        return
    bd = _board().getChessboardCorners()[ids][:, :2].astype(np.float64)
    H, inl = cv2.findHomography(corners, bd, cv2.RANSAC, 0.6)
    if H is None:
        res["gate"]["reasons"] = ["too_few_corners"]
        res["error"] = "homography_failed"
        res["timing_ms"]["detect"] = round((time.perf_counter() - t) * 1000, 1)
        return
    inl = inl.ravel().astype(bool)
    if inl.sum() < MIN_CORNERS:
        res["gate"]["reasons"] = ["too_few_corners"]
        res["error"] = "homography_failed"
        obs["corners"] = int(inl.sum())
        res["timing_ms"]["detect"] = round((time.perf_counter() - t) * 1000, 1)
        return
    corners, ids, bd = corners[inl], ids[inl], bd[inl]
    obs["corners"] = int(len(ids))
    H, _ = cv2.findHomography(corners, bd, 0)
    Hinv = np.linalg.inv(H)
    reproj = float(np.sqrt(((_apply_h(Hinv, bd) - corners) ** 2).sum(1).mean()))
    obs["reproj_px"] = round(reproj, 3)
    obs["corners_px"] = [[round(float(a), 1), round(float(b), 1)] for a, b in corners]
    obs["obliquity_deg"] = round(_pose_obliquity(corners, ids, w, h), 2)
    ppm_board = _local_scale(Hinv, np.array([BOARD_W_MM / 2, BOARD_H_MM / 2]))
    res["timing_ms"]["detect"] = round((time.perf_counter() - t) * 1000, 1)

    # blur variance on the board region (native res)
    quad = _apply_h(Hinv, np.array([[0, 0], [BOARD_W_MM, 0], [BOARD_W_MM, BOARD_H_MM], [0, BOARD_H_MM]], float))
    x0, y0 = np.maximum(np.floor(quad.min(0)).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(quad.max(0)).astype(int), [w, h])
    obs["blur_var"] = 0.0
    if x1 - x0 > 16 and y1 - y0 > 16:
        crop = grey[y0:y1, x0:x1]
        lap = cv2.Laplacian(crop, cv2.CV_32F)
        mk = np.zeros(crop.shape, np.uint8)
        cv2.fillConvexPoly(mk, np.round(quad - [x0, y0]).astype(np.int32), 255)
        mk = cv2.erode(mk, np.ones((5, 5), np.uint8)) > 0
        if mk.sum() > 100:
            obs["blur_var"] = round(float(lap[mk].var()), 1)

    # ---------------- rectify page / region at locator resolution
    t = time.perf_counter()
    gt = _gt() if panel_mode else None
    if panel_mode and gt is not None:
        off = gt["page_off"]
        region = np.array([-off[0], -off[1], 210 - off[0], 297 - off[1]])
    else:
        fp = _apply_h(H, np.array([[0, 0], [w, 0], [w, h], [0, h]], float))
        region = np.array([*np.clip(fp.min(0), -500, 500), *np.clip(fp.max(0), -500, 700)])
    S_loc = float(np.clip(0.8 * ppm_board, 3.0, 8.0))
    ext = max(region[2] - region[0], region[3] - region[1])
    S_loc = min(S_loc, 1800.0 / ext)
    f = min(1.0, S_loc / max(ppm_board, 1e-6))
    small = cv2.resize(grey, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 0.7 else grey
    f = small.shape[1] / w
    D0 = np.diag([f, f, 1.0])
    origin = region[:2]
    Wc, Hc = int(round((region[2] - region[0]) * S_loc)), int(round((region[3] - region[1]) * S_loc))
    A = np.array([[S_loc, 0, -origin[0] * S_loc], [0, S_loc, -origin[1] * S_loc], [0, 0, 1]])
    Hloc = A @ H @ np.linalg.inv(D0)
    canvas = cv2.warpPerspective(small, Hloc, (Wc, Hc), flags=cv2.INTER_LINEAR)
    valid = cv2.warpPerspective(np.full(small.shape, 255, np.uint8), Hloc, (Wc, Hc), flags=cv2.INTER_NEAREST)
    valid = cv2.erode(valid, np.ones((7, 7), np.uint8)) > 0
    # board exclusion rectangle (+4 mm)
    excl = np.zeros((Hc, Wc), np.uint8)
    bx0, by0 = (np.array([-4.0, -4.0]) - origin) * S_loc
    bx1, by1 = (np.array([BOARD_W_MM + 4, BOARD_H_MM + 4]) - origin) * S_loc
    cv2.rectangle(excl, (int(bx0), int(by0)), (int(bx1), int(by1)), 255, -1)
    excl = excl > 0

    # glare on page region: near-saturated fraction of valid, non-board pixels (page paper)
    pg = valid & ~excl
    obs["glare_frac"] = round(float((canvas[pg] >= 250).mean()), 4) if pg.sum() > 1000 else 0.0

    # ink level (linear light) from the black board squares: median of central parts of black squares
    ink_dark = None
    try:
        lut = _lin_lut()
        vals = []
        for j in range(SQUARES_Y):
            for i in range(SQUARES_X):
                if (i + j) % 2 == 0:
                    cx, cy = (i + 0.5) * SQUARE_MM, (j + 0.5) * SQUARE_MM
                    xa, ya = (np.array([cx - 5, cy - 5]) - origin) * S_loc
                    xb, yb = (np.array([cx + 5, cy + 5]) - origin) * S_loc
                    xa, ya, xb, yb = int(xa), int(ya), int(xb), int(yb)
                    if xa < 0 or ya < 0 or xb > Wc or yb > Hc:
                        continue
                    if not valid[ya:yb, xa:xb].all():
                        continue
                    vals.append(float(np.median(lut[canvas[ya:yb, xa:xb]])))
        if vals:
            ink_dark = float(np.median(vals))
    except Exception:
        ink_dark = None

    comps, _ = _locate_cracks(canvas, valid, S_loc, origin, panel_mode, excl)
    res["timing_ms"]["rectify"] = round((time.perf_counter() - t) * 1000, 1)

    # ---------------- assemble seeds
    t = time.perf_counter()
    seeds = []  # dict(id, true, seed_b, locator)
    if panel_mode and gt is not None:
        assigned, dense_fix = _match_specimens(comps, gt)
        for j, s in enumerate(gt["specs"]):
            if j in assigned:
                seeds.append({"id": s["id"], "true": s["width_mm"], "seed_b": _densify_sorted(assigned[j]),
                              "locator": "generic", "spec": j, "corridor": 3.0})
            else:
                # GT ROI fallback (ground truth corrected by the fit) if nearly all of the polyline is on-canvas
                P = dense_fix[j]
                px = np.round((P - origin) * S_loc).astype(int)
                inside = (px[:, 0] >= 0) & (px[:, 0] < Wc) & (px[:, 1] >= 0) & (px[:, 1] < Hc)
                if inside.mean() > 0.9 and valid[px[inside, 1], px[inside, 0]].mean() > 0.9:
                    seeds.append({"id": s["id"], "true": s["width_mm"], "seed_b": P[::4], "locator": "gt_roi",
                                  "spec": j, "corridor": 4.5})
    else:
        keep = [c for c in comps if c["mean_w_mm"] <= 6.0]
        for k, c in enumerate(sorted(keep, key=lambda c: -c["length_mm"])[:8]):
            seeds.append({"id": f"K{k + 1}", "true": None, "seed_b": c["path_b"][::2], "locator": "generic",
                          "spec": None, "corridor": 3.0})

    sigma_mm = _edge_sigma(grey, H, ppm_board)
    obs["blur_sigma_mm"] = round(sigma_mm, 3)
    cracks = []
    for sd in seeds:
        pm = _local_scale(Hinv, sd["seed_b"].mean(0))
        if pm <= 0:
            continue
        # skip seeds whose region is off-image
        ip = _apply_h(Hinv, sd["seed_b"])
        if ((ip[:, 0] < 0) | (ip[:, 0] >= w) | (ip[:, 1] < 0) | (ip[:, 1] >= h)).mean() > 0.2:
            continue
        m = _measure_one(grey, H, sd["seed_b"], pm, ink_dark, sigma_mm, sd["corridor"])
        if m is None or not (0.1 < m["profile_mm"] < 8.0):
            continue
        cracks.append({"sd": sd, "m": m, "ppm": pm})
    res["timing_ms"]["measure"] = round((time.perf_counter() - t) * 1000, 1)

    # ---------------- package
    out = []
    ppms = []
    ext_px = 0.0
    for c in cracks:
        sd, m, pm = c["sd"], c["m"], c["ppm"]
        poly_img = _apply_h(Hinv, m["poly_b"])
        ext_px += float(np.hypot(*np.diff(poly_img, axis=0).T).sum())
        ppms.append(pm)
        width = m["profile_mm"]  # chosen estimator (see summary)
        entry = {
            "id": sd["id"],
            "width_mm": round(float(width - WIDTH_BIAS_MM), 4),
            "uncertainty_mm": round(_uncertainty(m["local_mm"], pm, width, sigma_mm, m["wt_core"]), 4),
            "true_width_mm": sd["true"],
            "length_mm": round(m["length_mm"], 1),
            "polyline_px": _decimate(poly_img),
            "locator": sd["locator"],
            "estimators": {"dt": round(m["dt_mm"], 4), "profile_core": round(m["profile_core_mm"], 4),
                           "profile_ink": round(m["profile_ink_mm"], 4), "fwhm": round(m["fwhm_mm"], 4),
                           "profile": round(m["profile_mm"], 4),
                           "wt_core": round(m["wt_core"], 3), "q_core": round(m["q_core"], 3)},
            "px_per_mm": round(pm, 2),
        }
        out.append(entry)
    res["cracks"] = out
    obs["crack_px_extent"] = int(round(ext_px))
    obs["px_per_mm"] = round(float(np.median(ppms)) if ppms else ppm_board, 2)
    obs["ppm_board"] = round(ppm_board, 2)

    # ---------------- gate
    if obs["corners"] < GATE_MIN_CORNERS:
        reasons.append("too_few_corners")
    if obs["px_per_mm"] < GATE_MIN_PX_PER_MM:
        reasons.append("low_resolution")
    if obs["blur_var"] < GATE_MIN_BLUR_VAR:
        reasons.append("blurry")
    if obs["obliquity_deg"] > GATE_MAX_OBLIQUITY_DEG:
        reasons.append("oblique")
    if obs["glare_frac"] > GATE_MAX_GLARE:
        reasons.append("glare")
    res["gate"] = {"certified": len(reasons) == 0 and len(out) > 0, "reasons": reasons}
    res["ok"] = len(out) > 0
    if not out:
        res["error"] = "no_cracks_measured"


def _densify_sorted(cs):
    """Combine the paths of several components matched to one specimen into one left-to-right seed polyline."""
    paths = [c["path_b"] for c in cs]
    pts = np.vstack(paths)
    order = np.argsort(pts[:, 0])
    return pts[order][::2]


# ----------------------------------------------------------------------------- overlay

_PALETTE = [(60, 180, 75), (25, 25, 230), (0, 130, 255), (200, 130, 0), (180, 30, 145),
            (240, 240, 70), (230, 50, 240), (50, 230, 230)]


def _text(img, s, org, scale, color, thick=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def _label(img, lines, anchor, scale, color, placed):
    """Draw a small boxed multi-line label near `anchor`, trying several offsets to avoid overlapping `placed`."""
    th = max(1, int(round(scale * 2)))
    sizes = [cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, th)[0] for t in lines]
    bw = max(s[0] for s in sizes) + 18
    lh = max(s[1] for s in sizes) + 8
    bh = lh * len(lines) + 4
    H, W = img.shape[:2]
    ax, ay = anchor
    cands = [(12, -bh - 8), (12, 8), (-bw - 12, -bh - 8), (-bw - 12, 8), (12, -bh // 2), (-bw - 12, -bh // 2),
             (-bw // 2, -bh - 14), (-bw // 2, 14)]
    best = None
    for dx, dy in cands:
        x0 = int(np.clip(ax + dx, 2, W - bw - 2))
        y0 = int(np.clip(ay + dy, 70, H - bh - 2))
        hit = any(not (x0 + bw < px0 or px0 + pw < x0 or y0 + bh < py0 or py0 + ph < y0) for px0, py0, pw, ph in placed)
        if not hit:
            best = (x0, y0)
            break
        if best is None:
            best = (x0, y0)
    x0, y0 = best
    placed.append((x0, y0, bw, bh))
    ov = img.copy()
    cv2.rectangle(ov, (x0, y0), (x0 + bw, y0 + bh), (20, 20, 20), -1)
    cv2.addWeighted(ov, 0.72, img, 0.28, 0, img)
    cv2.rectangle(img, (x0, y0), (x0 + bw, y0 + bh), color, 1)
    for i, t in enumerate(lines):
        cv2.putText(img, t, (x0 + 5, y0 + lh * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), th, cv2.LINE_AA)


def draw_overlay(image_bgr: np.ndarray, result: dict) -> np.ndarray:
    """Annotated copy of the image (BGR, max side ~1600 px): corners, crack polylines, labels, header."""
    img = image_bgr
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    img = img[:, :, :3].copy()
    h, w = img.shape[:2]
    s = min(1.0, 1600.0 / max(h, w))
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    obs = result.get("observation", {})
    fs = max(0.5, 0.55 * img.shape[1] / 1000)
    th = max(1, int(round(fs * 1.8)))
    for c in obs.get("corners_px", []) or []:
        cv2.circle(img, (int(c[0] * s), int(c[1] * s)), 5, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(img, (int(c[0] * s), int(c[1] * s)), 3, (0, 255, 255), -1, cv2.LINE_AA)
    placed: list = []
    cracks = result.get("cracks", [])
    for k, c in enumerate(cracks):  # polylines first so no later line crosses an earlier label
        col = _PALETTE[k % len(_PALETTE)]
        pl = np.array(c["polyline_px"], float) * s
        if len(pl) >= 2:
            cv2.polylines(img, [np.round(pl).astype(np.int32).reshape(-1, 1, 2)], False, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.polylines(img, [np.round(pl).astype(np.int32).reshape(-1, 1, 2)], False, col, 2, cv2.LINE_AA)
    for k, c in enumerate(cracks):
        col = _PALETTE[k % len(_PALETTE)]
        pl = np.array(c["polyline_px"], float) * s
        lines = [f'{c["id"]} {c["width_mm"]:.2f}+/-{c["uncertainty_mm"]:.2f} mm']
        if c.get("true_width_mm") is not None:
            lines.append(f'true {c["true_width_mm"]:.2f} mm')
        if len(pl):
            _label(img, lines, tuple(pl[len(pl) // 2]), fs * 0.75, col, placed)
    cert = result.get("gate", {}).get("certified", False)
    reasons = ",".join(result.get("gate", {}).get("reasons", []))
    head1 = (f'{obs.get("px_per_mm", 0):.1f} px/mm | corners {obs.get("corners", 0)}/{obs.get("corners_total", 24)} | '
             f'obliq {obs.get("obliquity_deg", 0):.0f} deg | blur {obs.get("blur_var", 0):.0f}')
    head2 = "CERTIFIED: yes" if cert else f"CERTIFIED: no ({reasons})"
    cv2.rectangle(img, (0, 0), (img.shape[1], int(fs * 80)), (0, 0, 0), -1)
    cv2.putText(img, head1, (8, int(fs * 30)), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), th, cv2.LINE_AA)
    cv2.putText(img, head2, (8, int(fs * 66)), cv2.FONT_HERSHEY_SIMPLEX, fs, (80, 255, 80) if cert else (80, 80, 255), th,
                cv2.LINE_AA)
    if result.get("error"):
        _text(img, str(result["error"]), (8, int(fs * 110)), fs, (80, 80, 255), th)
    return img
