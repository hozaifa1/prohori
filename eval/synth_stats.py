"""Image statistics used to compare synthetic renders with the real panel photos (shared by the calibration helper
and eval/synth_validation.py).

For every image we record
  * the observation vector of measure.analyze (panel_mode=False, so real and synthetic photos go through the identical
    code path): corners, blur_var, px_per_mm (board), glare_frac, blur_sigma_mm, obliquity_deg, reproj_px;
  * statistics of the rectified ChArUco board (12 px/mm), which both image sets contain with the same printed geometry:
    paper-white and toner-black level (8-bit, sRGB luminance), black/white ratio in linear light, noise sigma of the
    white and black fields (high-pass residual, 8-bit), sharpness proxies;
  * global statistics: saturated fraction, JPEG bytes per megapixel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prohori import measure  # noqa: E402
from prohori.board import SQUARES_X, SQUARES_Y, SQUARE_MM, make_board  # noqa: E402

BW, BH = SQUARES_X * SQUARE_MM, SQUARES_Y * SQUARE_MM
_det = None


def _detector():
    global _det
    if _det is None:
        cp = cv2.aruco.CharucoParameters()
        cp.minMarkers = 1
        _det = cv2.aruco.CharucoDetector(make_board(), cp, cv2.aruco.DetectorParameters())
    return _det


def board_homography(grey: np.ndarray):
    """Image -> board-mm homography from a ChArUco detection on a <=2000 px copy; (H, n_corners) or (None, 0)."""
    h, w = grey.shape
    s = min(1.0, 2000.0 / max(h, w))
    small = cv2.resize(grey, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else grey
    corners, ids, _, _ = _detector().detectBoard(small)
    if ids is None or len(ids) < 6:
        return None, 0
    c = corners.reshape(-1, 2).astype(np.float64) / s
    bd = make_board().getChessboardCorners()[ids.ravel()][:, :2].astype(np.float64)
    H, inl = cv2.findHomography(c, bd, cv2.RANSAC, 1.0)
    return H, int(len(ids))


def rectified_board(img_bgr: np.ndarray, ppm: float = 12.0):
    """(grey 8-bit crop of the board at ppm px/mm, colour crop) or (None, None)."""
    grey = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    H, n = board_homography(grey)
    if H is None:
        return None, None
    A = np.array([[ppm, 0, 0], [0, ppm, 0], [0, 0, 1.0]]) @ H
    W_, H_ = int(round(BW * ppm)), int(round(BH * ppm))
    g = cv2.warpPerspective(grey, A, (W_, H_), flags=cv2.INTER_AREA if False else cv2.INTER_LINEAR)
    c = cv2.warpPerspective(img_bgr, A, (W_, H_), flags=cv2.INTER_LINEAR)
    return g, c


def _lin(x):
    v = x.astype(np.float32) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def board_stats(img_bgr: np.ndarray, ppm: float = 12.0) -> dict:
    g, c = rectified_board(img_bgr, ppm)
    nan = float("nan")
    out = {"white_level": nan, "black_level": nan, "black_white_ratio": nan, "noise_white": nan, "noise_black": nan,
           "noise_white_chroma": nan, "contrast_michelson": nan, "white_uniformity": nan}
    if g is None:
        return out
    # interior of the board only (drop the outer 3 mm: border pixels belong to the paper / wall)
    m = int(3 * ppm)
    gi = g[m:-m, m:-m]
    t, _ = cv2.threshold(gi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    white = (gi > t).astype(np.uint8)
    black = (gi <= t).astype(np.uint8)
    k = np.ones((int(1.6 * ppm) | 1,) * 2, np.uint8)
    we, be = cv2.erode(white, k) > 0, cv2.erode(black, k) > 0
    if we.sum() < 500 or be.sum() < 500:
        return out
    wl, bl = float(np.median(gi[we])), float(np.median(gi[be]))
    out["white_level"], out["black_level"] = wl, bl
    out["black_white_ratio"] = float(_lin(np.array([bl]))[0] / max(_lin(np.array([wl]))[0], 1e-6))
    out["contrast_michelson"] = (wl - bl) / (wl + bl)
    hp = gi.astype(np.float32) - cv2.GaussianBlur(gi.astype(np.float32), (0, 0), 4.0)
    out["noise_white"] = float(hp[we].std())
    out["noise_black"] = float(hp[be].std())
    ci = c[m:-m, m:-m].astype(np.float32)
    ch = ci[:, :, 0] - ci[:, :, 2]                                    # B - R chroma noise proxy
    chp = ch - cv2.GaussianBlur(ch, (0, 0), 4.0)
    out["noise_white_chroma"] = float(chp[we].std())
    # white-field low-frequency uniformity: relative spread of the block means
    blk = cv2.resize(cv2.GaussianBlur(gi.astype(np.float32), (0, 0), 6), (12, 8), interpolation=cv2.INTER_AREA)
    wm = cv2.resize(we.astype(np.float32), (12, 8), interpolation=cv2.INTER_AREA) > 0.6
    out["white_uniformity"] = float(blk[wm].std() / max(blk[wm].mean(), 1e-6)) if wm.sum() > 4 else nan
    return out


def image_stats(img_bgr: np.ndarray, nbytes: int | None = None) -> dict:
    res = measure.analyze(img_bgr, panel_mode=False)
    o = res["observation"]
    row = {"corners": o["corners"], "blur_var": o["blur_var"], "px_per_mm": o.get("ppm_board", o["px_per_mm"]),
           "glare_frac": o["glare_frac"], "blur_sigma_mm": o.get("blur_sigma_mm", float("nan")),
           "obliquity_deg": o["obliquity_deg"], "reproj_px": o["reproj_px"] if o["reproj_px"] is not None else float("nan"),
           "board_found": int(o["corners"] >= 6 and res.get("error") not in ("board_not_found", "board_degenerate", "homography_failed")),
           "sat_frac": float((img_bgr >= 250).all(axis=2).mean()),
           "mean_grey": float(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).mean())}
    if nbytes is not None:
        row["jpeg_bytes_per_mpx"] = nbytes / (img_bgr.shape[0] * img_bgr.shape[1] / 1e6)
    row.update(board_stats(img_bgr))
    row["blur_sigma_px"] = row["blur_sigma_mm"] * row["px_per_mm"]
    return row, res
