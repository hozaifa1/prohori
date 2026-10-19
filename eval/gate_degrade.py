"""Controlled degradations of the real test-panel photos, each keeping the known true crack widths.

Physical order of the model (what a worse capture would do to the same printed panel):

  1. extra perspective tilt   plane homography K R K^-1 (camera turned by theta about an axis in the image plane,
                              translated so the board centre stays put), cubic resampling
  2. lower native resolution  INTER_AREA downscale by s  (lower px/mm, as if farther away / fewer pixels)
  3. blur                     Gaussian (defocus, sigma px) or linear motion (length px, angle), in output pixels
  4. specular glare           1-3 soft elliptical blobs added in linear light, saturating
  5. sensor noise             signal-dependent Gaussian: sigma(I) = sigma0 * (0.5 + 0.5 I / 255)
  6. JPEG                     re-encode at quality q

Every degradation changes only how the panel is imaged, never the panel, so the printed widths in
data/print/test_panel_ground_truth.json remain the truth for every derived image.  A recipe is a plain dict that is
sampled from `sample_recipe` (the documented calibration distribution) and applied deterministically by `apply_recipe`.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

# Probabilities and ranges of the calibration distribution.  The CRC guarantee in gate_params.json holds for captures
# drawn from this mixture (and exchangeable with it); change it and the gate must be re-fitted.
DIST = {
    "p_tilt": 0.45, "tilt_deg": (5.0, 40.0),
    "p_scale": 0.60, "scale": (0.33, 0.90),                       # log-uniform
    "p_blur": 0.55, "p_blur_motion": 0.35, "blur_sigma_px": (0.6, 4.0), "motion_len_px": (3.0, 22.0),
    "p_glare": 0.35, "glare_blobs": (1, 3), "glare_radius_frac": (0.03, 0.14), "glare_gain": (0.5, 2.0),
    "p_noise": 0.45, "noise_sigma": (1.0, 10.0),                  # log-uniform
    "p_jpeg": 0.50, "jpeg_q": (12, 85),
}

_SRGB2LIN = None


def _lut():
    global _SRGB2LIN
    if _SRGB2LIN is None:
        v = np.arange(256) / 255.0
        _SRGB2LIN = np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4).astype(np.float32)
    return _SRGB2LIN


def _lin2srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _logu(rng, lo, hi):
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def sample_recipe(rng: np.random.Generator) -> dict:
    """Draw one degradation recipe.  Positions of glare blobs are in page millimetres (board frame)."""
    D = DIST
    r: dict = {"tilt": None, "scale": 1.0, "blur": None, "glare": None, "noise": None, "jpeg": None}
    if rng.random() < D["p_tilt"]:
        r["tilt"] = {"deg": float(rng.uniform(*D["tilt_deg"])), "axis_deg": float(rng.uniform(0, 360))}
    if rng.random() < D["p_scale"]:
        r["scale"] = _logu(rng, *D["scale"])
    if rng.random() < D["p_blur"]:
        if rng.random() < D["p_blur_motion"]:
            r["blur"] = {"kind": "motion", "len": float(rng.uniform(*D["motion_len_px"])),
                         "angle_deg": float(rng.uniform(0, 180))}
        else:
            r["blur"] = {"kind": "gauss", "sigma": _logu(rng, *D["blur_sigma_px"])}
    if rng.random() < D["p_glare"]:
        n = int(rng.integers(D["glare_blobs"][0], D["glare_blobs"][1] + 1))
        r["glare"] = [{"x_mm": float(rng.uniform(-35, 175)), "y_mm": float(rng.uniform(-22, 275)),
                       "radius_frac": float(rng.uniform(*D["glare_radius_frac"])),
                       "aspect": float(rng.uniform(0.5, 1.6)), "angle_deg": float(rng.uniform(0, 180)),
                       "gain": float(rng.uniform(*D["glare_gain"]))} for _ in range(n)]
    if rng.random() < D["p_noise"]:
        r["noise"] = {"sigma": _logu(rng, *D["noise_sigma"]), "seed": int(rng.integers(0, 2**31 - 1))}
    if rng.random() < D["p_jpeg"]:
        r["jpeg"] = {"q": int(rng.integers(D["jpeg_q"][0], D["jpeg_q"][1] + 1))}
    return r


def tilt_homography(w: int, h: int, deg: float, axis_deg: float, centre_xy) -> np.ndarray:
    """H = T K R K^-1: turn the camera by `deg` about an in-plane axis, then translate so `centre_xy` stays fixed."""
    f = 0.78 * max(w, h)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], float)
    a = math.radians(axis_deg)
    rvec = np.array([math.cos(a), math.sin(a), 0.0]) * math.radians(deg)
    R, _ = cv2.Rodrigues(rvec)
    Ht = K @ R @ np.linalg.inv(K)
    c = np.array([centre_xy[0], centre_xy[1], 1.0])
    c1 = Ht @ c
    c1 = c1[:2] / c1[2]
    T = np.array([[1, 0, centre_xy[0] - c1[0]], [0, 1, centre_xy[1] - c1[1]], [0, 0, 1]], float)
    return T @ Ht


def _motion_kernel(length: float, angle_deg: float) -> np.ndarray:
    n = int(max(3, round(length))) | 1
    k = np.zeros((n, n), np.float32)
    c = n // 2
    dx, dy = math.cos(math.radians(angle_deg)) * (n - 1) / 2, math.sin(math.radians(angle_deg)) * (n - 1) / 2
    cv2.line(k, (int(round(c - dx)), int(round(c - dy))), (int(round(c + dx)), int(round(c + dy))), 1.0, 1, cv2.LINE_AA)
    return k / k.sum()


def apply_recipe(img: np.ndarray, recipe: dict, H_board2img: np.ndarray, board_centre_px) -> np.ndarray:
    """Apply `recipe` to a BGR uint8 photo.  H_board2img: the source photo's board(mm)->pixel homography (used to place
    glare on the page); board_centre_px: pixel position of the board centre (tilt pivot)."""
    h, w = img.shape[:2]
    M = np.eye(3)
    out = img
    if recipe.get("tilt"):
        Ht = tilt_homography(w, h, recipe["tilt"]["deg"], recipe["tilt"]["axis_deg"], board_centre_px)
        out = cv2.warpPerspective(out, Ht, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        M = Ht @ M
    s = float(recipe.get("scale", 1.0))
    if s < 0.999:
        nw, nh = max(64, int(round(w * s))), max(64, int(round(h * s)))
        out = cv2.resize(out, (nw, nh), interpolation=cv2.INTER_AREA)
        M = np.diag([nw / w, nh / h, 1.0]) @ M
    bl = recipe.get("blur")
    if bl:
        if bl["kind"] == "gauss":
            out = cv2.GaussianBlur(out, (0, 0), bl["sigma"])
        else:
            out = cv2.filter2D(out, -1, _motion_kernel(bl["len"], bl["angle_deg"]), borderType=cv2.BORDER_REPLICATE)
    if recipe.get("glare"):
        oh, ow = out.shape[:2]
        Hp = M @ H_board2img
        wins = []
        for g in recipe["glare"]:
            p = Hp @ np.array([g["x_mm"], g["y_mm"], 1.0])
            cx, cy = p[0] / p[2], p[1] / p[2]
            rad = g["radius_frac"] * min(oh, ow)
            ext = 2.2 * rad * max(math.sqrt(g["aspect"]), 1 / math.sqrt(g["aspect"]))  # exp(-r^3) < 1e-4 beyond ~2.1 rad
            x0, x1 = int(max(0, cx - ext)), int(min(ow, cx + ext + 1))
            y0, y1 = int(max(0, cy - ext)), int(min(oh, cy + ext + 1))
            if x1 > x0 and y1 > y0:
                wins.append((g, cx, cy, rad, x0, x1, y0, y1))
        if wins:
            X0, X1 = min(w_[4] for w_ in wins), max(w_[5] for w_ in wins)
            Y0, Y1 = min(w_[6] for w_ in wins), max(w_[7] for w_ in wins)
            add = np.zeros((Y1 - Y0, X1 - X0), np.float32)
            for g, cx, cy, rad, x0, x1, y0, y1 in wins:
                yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
                ca, sa = math.cos(math.radians(g["angle_deg"])), math.sin(math.radians(g["angle_deg"]))
                u = ((xx - cx) * ca + (yy - cy) * sa) / (rad * math.sqrt(g["aspect"]))
                v = (-(xx - cx) * sa + (yy - cy) * ca) / (rad / math.sqrt(g["aspect"]))
                add[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] += g["gain"] * np.exp(-((u * u + v * v) ** 1.5))  # flat-topped blob
            out = out.copy()
            sub = _lut()[out[Y0:Y1, X0:X1]]
            out[Y0:Y1, X0:X1] = np.clip(_lin2srgb(sub + add[..., None]) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    nz = recipe.get("noise")
    if nz:
        rng = np.random.default_rng(nz["seed"])
        f = out.astype(np.float32)
        sig = nz["sigma"] * (0.5 + 0.5 * f / 255.0)
        out = np.clip(f + rng.standard_normal(f.shape).astype(np.float32) * sig + 0.5, 0, 255).astype(np.uint8)
    jp = recipe.get("jpeg")
    if jp:
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(jp["q"])])
        out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out
