"""Synthetic photoreal crack-on-wall generator with exact millimetre ground truth (replaces field capture).

    python -m prohori.synth --n 500 --out data/synth/v1 [--seed 0] [--workers 2] [--size 4096x3072]

What one render contains (everything on ONE plane, in millimetres, board frame = measure.py's board frame):

* a wall texture (CC0 ambientCG concrete / plaster photographs, 2K, assumed physical tile size 0.3-0.9 m, extended
  below its native resolution with power-law fractal grain + pores so that 10-20 px/mm views are not blurry upsamples);
* a real crack: the centreline graph and the *relative* width profile are taken from a real ground-truth mask of
  Crack500 / DeepCrack / CFD / CrackTree200 / CrackSeg9k (train splits only), scaled to a physical length, with a
  target median width drawn log-uniformly from 0.2-3.0 mm and re-rasterised as a swept disc with EXACT per-station
  radius, so ground-truth width w(s) in mm is known by construction (no mask-edge ambiguity);
* the printed 7x5 ChArUco board (20 mm squares, board.make_board()) on a white paper sheet next to the crack,
  coplanar with it, with the exact pose and the 24 inner-corner pixel positions in the ground truth;
* a camera: random perspective pose (obliquity, roll, distance -> px/mm), radial lens distortion, shading gradient,
  cast shadow, specular glare, optical Gaussian PSF, motion blur, Poisson-Gaussian sensor noise (linear light),
  sRGB tone curve, ISP unsharp sharpening, JPEG compression.

Everything is seeded: ``render(seed)`` is a pure function of (seed, config).  Each image is written with a JSON
file holding the ground truth (pose, intrinsics, distortion, board corners, per-station crack widths, nuisance
parameters).  The photometric parameter ranges are calibrated against the real panel photos in data/raw
(eval/synth_validation.py, eval/results/synth_validation.md).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .board import MARKER_MM, SQUARE_MM, SQUARES_X, SQUARES_Y, make_board

ROOT = Path(__file__).resolve().parents[2]
DATASETS = Path(os.environ.get("PROHORI_DATASETS", ROOT / "data" / "datasets"))
TEX_DIR = DATASETS / "textures_ambientcg"

BOARD_W, BOARD_H = SQUARES_X * SQUARE_MM, SQUARES_Y * SQUARE_MM   # 140 x 100 mm
PAPER_MARGIN = 8.0                                                 # white paper around the board, mm

# --------------------------------------------------------------------------------------- configuration


@dataclass
class SynthConfig:
    width: int = 4096
    height: int = 3072
    ppm_range: tuple = (11.0, 24.0)        # requested px/mm at the layout centre (limited further by framing); real panel photos: 12-20
    crack_width_mm: tuple = (0.2, 3.0)    # log-uniform target median width (panel specimens: 0.3-3.0 mm)
    crack_extent_mm: tuple = (35.0, 110.0)   # upper bound is reduced when the requested px/mm leaves less field of view
    tilt_deg_max: float = 50.0            # obliquity; sampled as |N(0, 17)| clipped
    tilt_sigma_deg: float = 17.0
    roll_deg_range: tuple = (-180.0, 180.0)
    f_rel: tuple = (0.74, 0.86)           # focal length / image width (phone main camera ~0.72-0.85)
    dist_k1_sigma: float = 0.012
    dist_k2_sigma: float = 0.004
    p_motion: float = 0.35
    motion_len_px: tuple = (1.5, 9.0)
    psf_sigma_px: tuple = (0.55, 1.5)     # optical + pixel-aperture blur, 1-sigma, px
    p_defocus: float = 0.2                # extra defocus blur (added in quadrature)
    defocus_sigma_px: tuple = (1.5, 4.0)
    p_glare: float = 0.35
    p_shadow: float = 0.2
    noise_a: tuple = (1.5e-4, 1.8e-3)     # shot-noise slope (variance = a * I + b) in linear units, I in [0, 1]
    noise_b: tuple = (4.0e-6, 6.0e-5)     # read-noise variance
    sharpen_amount: tuple = (0.0, 0.45)
    jpeg_quality: tuple = (78, 95)
    paper_albedo: tuple = (0.70, 0.86)
    ink_ratio: tuple = (0.012, 0.075)      # toner albedo / paper albedo
    paper_exposure_srgb: tuple = (160, 192)   # target 8-bit level of white paper under mean illumination
    ss_ppm: float = 32.0                  # crack supersampling resolution px/mm
    tex_tile_mm: tuple = (300.0, 900.0)   # assumed physical size of the 2K ambientCG tile
    crack_sources: tuple = ("crack500", "deepcrack", "cfd", "cracktree200", "crackseg9k")


# --------------------------------------------------------------------------------------- assets

_tex_cache: dict = {}
_mask_cache: dict = {}


# Textures excluded after visual inspection of the contact sheet: slab joints / planks / moss / polka dots would act as
# crack-like or non-wall distractors that no real crack photo of plaster or concrete contains by construction.
TEX_EXCLUDE = {"Concrete007", "Concrete008", "Concrete010", "Concrete026", "Concrete045", "PaintedPlaster002"}


def list_textures() -> list[Path]:
    return [p for p in sorted(TEX_DIR.glob("*_Color.jpg")) if p.name.split("_")[0] not in TEX_EXCLUDE]


def srgb_to_lin(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0).astype(np.float32)
    hi = 1.055 * cv2.pow(np.maximum(x, 0.0031308), 1 / 2.4) - 0.055
    return np.where(x <= 0.0031308, 12.92 * x, hi).astype(np.float32)


def load_texture(path: Path) -> np.ndarray:
    """Linear-light RGB float32 (H, W, 3), mean luminance normalised to 1 (scaled later by the albedo)."""
    k = str(path)
    if k not in _tex_cache:
        if len(_tex_cache) > 6:
            _tex_cache.clear()
        im = cv2.imread(k, cv2.IMREAD_COLOR)[:, :, ::-1].astype(np.float32) / 255.0
        lin = srgb_to_lin(im)
        lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        _tex_cache[k] = lin / max(float(lum.mean()), 1e-6)
    return _tex_cache[k]


def _crack_mask_entries(sources) -> list[tuple[str, Path, Path]]:
    """(source, image path, mask path) of real crack ground-truth masks (train splits only)."""
    out: list[tuple[str, Path, Path]] = []
    if "crack500" in sources and (DATASETS / "crack500" / "train.txt").exists():
        for line in (DATASETS / "crack500" / "train.txt").read_text().splitlines():
            p = line.split()
            if len(p) >= 2:
                out.append(("crack500", DATASETS / "crack500" / p[0], DATASETS / "crack500" / p[1]))
    if "deepcrack" in sources and (DATASETS / "deepcrack" / "train_lab").exists():
        for m in sorted((DATASETS / "deepcrack" / "train_lab").glob("*.png")):
            out.append(("deepcrack", m, m))
    if "cfd" in sources and (DATASETS / "cfd" / "seg_gt").exists():
        for m in sorted((DATASETS / "cfd" / "seg_gt").glob("*.png")):
            out.append(("cfd", m, m))
    if "cracktree200" in sources and (DATASETS / "cracktree200" / "cracktree200_gt").exists():
        for m in sorted((DATASETS / "cracktree200" / "cracktree200_gt").glob("*.png")):
            out.append(("cracktree200", m, m))
    if "crackseg9k" in sources and (DATASETS / "crackseg9k" / "Final-Dataset-Vol1" / "Final_Masks" / "train.txt").exists():
        base = DATASETS / "crackseg9k" / "Final-Dataset-Vol1" / "Final_Masks"
        for n in (base / "train.txt").read_text().splitlines():
            s = n.strip()
            if s.startswith(("Rissbilder", "Volker", "GAPS", "cracktree", "Ceramic")):
                out.append(("crackseg9k", base / "Masks" / (Path(s.split()[0]).stem + ".png"), base / "Masks" / (Path(s.split()[0]).stem + ".png")))
    return out


_entries_cache: dict = {}


def crack_mask_entries(sources) -> list:
    k = tuple(sources)
    if k not in _entries_cache:
        _entries_cache[k] = _crack_mask_entries(sources)
    return _entries_cache[k]


# --------------------------------------------------------------------------------------- crack geometry


@dataclass
class CrackGraph:
    pts: np.ndarray        # (N, 2) mm, plane coordinates (before placement), smoothed centreline nodes
    w_mm: np.ndarray       # (N,) exact width per node, mm (= 2 * swept radius)
    dep: np.ndarray        # (N,) depth/attenuation in [0, 1] (1 = black)
    edges: np.ndarray      # (E, 2) node index pairs
    source: str
    mask_id: str


def _graph_smoother(n: int, edges: np.ndarray):
    from scipy.sparse import coo_matrix, identity
    r = np.concatenate([edges[:, 0], edges[:, 1]])
    c = np.concatenate([edges[:, 1], edges[:, 0]])
    A = coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.maximum(np.asarray(A.sum(axis=1)).ravel(), 1.0)
    from scipy.sparse import diags
    Pm = diags(1.0 / deg) @ A
    return 0.5 * (identity(n) + Pm)           # lazy random walk: x <- (x + mean of neighbours) / 2


def _smooth(M, x: np.ndarray, iters: int) -> np.ndarray:
    for _ in range(int(iters)):
        x = M @ x
    return x


def crack_from_mask(mask: np.ndarray, rng: np.random.Generator, cfg: SynthConfig, source: str, mask_id: str,
                    extent_range: tuple | None = None):
    """Build a CrackGraph (mm) from a real binary crack mask.  Returns None if the mask is unusable."""
    m = (mask > 127).astype(np.uint8) if mask.dtype != bool else mask.astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n < 2:
        return None
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[k]
    if math.hypot(w, h) < 90 or area < 200:
        return None
    comp = (lab[y:y + h, x:x + w] == k).astype(np.uint8)
    pad = 6
    comp = cv2.copyMakeBorder(comp, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    # 2x smooth upsample -> threshold -> thin: removes staircase noise of the pixel labels
    up = cv2.resize(comp.astype(np.float32), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    up = cv2.GaussianBlur(up, (0, 0), 1.6) > 0.5
    upu = up.astype(np.uint8) * 255
    sk = cv2.ximgproc.thinning(upu) > 0
    ys, xs = np.nonzero(sk)
    N = len(ys)
    if N < 120 or N > 20000:
        return None
    dt = cv2.distanceTransform(upu, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    r_px = dt[ys, xs] / 2.0 * 1.0                     # radius in ORIGINAL mask px (upsample factor 2)
    pos = np.stack([xs, ys], 1).astype(np.float64) / 2.0
    idx = -np.ones(sk.shape, np.int64)
    idx[ys, xs] = np.arange(N)
    es = []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 < sk.shape[0]) & (x2 >= 0) & (x2 < sk.shape[1])
        j = np.full(N, -1)
        j[ok] = idx[y2[ok], x2[ok]]
        sel = j >= 0
        es.append(np.stack([np.nonzero(sel)[0], j[sel]], 1))
    edges = np.concatenate(es, 0)
    if len(edges) < 50:
        return None
    # physical scale: bbox diagonal -> target extent in mm
    extent = float(rng.uniform(*(extent_range or cfg.crack_extent_mm)))
    diag_px = float(np.hypot(*np.ptp(pos, axis=0)))
    lam = extent / max(diag_px, 1.0)                # mm per original mask px
    step_mm = 0.5 * lam                             # skeleton node spacing after 2x upsampling
    M = _graph_smoother(N, edges)
    # centreline smoothing (~0.6 mm) so that pixel staircases vanish
    pos_s = np.stack([_smooth(M, pos[:, 0], max(1, int((0.6 / step_mm) ** 2 / 2))),
                      _smooth(M, pos[:, 1], max(1, int((0.6 / step_mm) ** 2 / 2)))], 1)
    # relative width profile (real), smoothed over ~3 mm
    rel = r_px / max(float(np.median(r_px)), 1e-6)
    rel = _smooth(M, rel, max(1, int((3.0 / step_mm) ** 2 / 2)))
    rel = np.clip(rel, 0.35, 2.3)
    wmed = float(np.exp(rng.uniform(math.log(cfg.crack_width_mm[0]), math.log(cfg.crack_width_mm[1]))))
    # edge roughness / along-crack width noise at two scales (0.4 mm and 2 mm), unit std each
    def fbm(sig_mm):
        z = rng.standard_normal(N)
        z = _smooth(M, z, max(1, int((sig_mm / step_mm) ** 2 / 2)))
        return (z - z.mean()) / max(z.std(), 1e-9)
    rough = np.exp(0.10 * fbm(0.4) + 0.16 * fbm(2.0))
    w = np.clip(wmed * rel * rough, 0.06, 9.0)
    # interior darkness (1 - albedo ratio): thin cracks are less dark, plus slow variation
    dep = np.clip(0.50 + 0.43 * (1 - np.exp(-w / 0.45)) + 0.10 * fbm(4.0), 0.30, 0.98)
    pts = (pos_s - pos_s.mean(0)) * lam
    return CrackGraph(pts, w, dep, edges, source, mask_id)


def pick_crack(rng: np.random.Generator, cfg: SynthConfig, extent_range: tuple | None = None) -> CrackGraph:
    ents = crack_mask_entries(cfg.crack_sources)
    if not ents:
        raise RuntimeError("no crack masks found under data/datasets (run the dataset download first)")
    for _ in range(200):
        src, ip, mp = ents[int(rng.integers(len(ents)))]
        m = cv2.imread(str(mp), cv2.IMREAD_UNCHANGED)
        if m is None:
            continue
        if m.ndim == 3:
            m = m[:, :, 0]
        g = crack_from_mask(m > 127, rng, cfg, src, mp.name, extent_range)
        if g is not None:
            return g
    raise RuntimeError("could not find a usable crack mask")


def rotate_graph(g: CrackGraph, ang: float, flip: bool) -> np.ndarray:
    p = g.pts.copy()
    if flip:
        p[:, 0] *= -1
    c, s = math.cos(ang), math.sin(ang)
    return p @ np.array([[c, s], [-s, c]])


def rasterise_crack(pts_mm: np.ndarray, g: CrackGraph, ss_ppm: float):
    """Exact swept-disc rasterisation at ss_ppm px/mm.  Returns (coverage uint8 at ss, origin_mm (x0, y0)).

    Disc coverage is the signed-distance box-filter approximation clip(r - d + 0.5, 0, 1) evaluated at pixel
    centres (cv2.circle fills are biased by about +0.5 px of radius, which would put +0.03 mm of error into the
    ground-truth width of a 0.15 mm crack); the union of discs along the graph is taken by pixel-wise maximum.
    The interior attenuation ("depth") of the nearest node is stored in the same pass."""
    r = g.w_mm / 2.0
    lo = (pts_mm - r[:, None]).min(0) - 1.5
    hi = (pts_mm + r[:, None]).max(0) + 1.5
    W, H = (np.ceil((hi - lo) * ss_ppm)).astype(int)
    alpha = np.zeros((H, W), np.uint8)
    dep = np.zeros((H, W), np.uint8)
    P = (pts_mm - lo) * ss_ppm
    R = r * ss_ppm
    e = g.edges
    d = np.hypot(*(P[e[:, 0]] - P[e[:, 1]]).T)
    for (i, j), dd in zip(e, d):
        n = max(1, int(math.ceil(dd / 1.0)))
        for t in np.linspace(0.0, 1.0, n + 1):
            cx = P[i, 0] * (1 - t) + P[j, 0] * t
            cy = P[i, 1] * (1 - t) + P[j, 1] * t
            rr = R[i] * (1 - t) + R[j] * t
            x0, x1 = max(0, int(cx - rr - 2)), min(W, int(cx + rr + 3))
            y0, y1 = max(0, int(cy - rr - 2)), min(H, int(cy + rr + 3))
            if x1 <= x0 or y1 <= y0:
                continue
            yy = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
            xx = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            cov = np.clip(rr - dist + 0.5, 0.0, 1.0)
            patch = alpha[y0:y1, x0:x1]
            np.maximum(patch, (cov * 255.0 + 0.5).astype(np.uint8), out=patch)
            inside = dist <= rr + 1.0
            dv = int(round(255 * (g.dep[i] * (1 - t) + g.dep[j] * t)))
            dpatch = dep[y0:y1, x0:x1]
            dpatch[inside] = dv
    cov8 = (alpha.astype(np.uint16) * dep.astype(np.uint16) // 255).astype(np.uint8)
    return cov8, lo


# --------------------------------------------------------------------------------------- camera geometry


def look_at_pose(centre_xy: np.ndarray, dist_mm: float, tilt: float, azim: float, roll: float):
    """Camera rotation R (world->cam, OpenCV: x right, y down, z forward) and centre C (mm).  Plane z = 0, board frame
    (x right, y down as printed, z into the wall), so the camera sits at z < 0 and the board is seen un-mirrored."""
    C = np.array([centre_xy[0] + dist_mm * math.sin(tilt) * math.cos(azim),
                  centre_xy[1] + dist_mm * math.sin(tilt) * math.sin(azim),
                  -dist_mm * math.cos(tilt)])      # board frame: z points INTO the wall (OpenCV board convention),
    target = np.array([centre_xy[0], centre_xy[1], 0.0])
    z = target - C
    z /= np.linalg.norm(z)
    up = np.array([math.cos(roll), math.sin(roll), 0.0])     # plane direction that appears "up" in the image
    yv = -(up - (up @ z) * z)
    if np.linalg.norm(yv) < 1e-6:
        yv = np.array([0.0, 1.0, 0.0])
    y = yv / np.linalg.norm(yv)
    x = np.cross(y, z)
    R = np.stack([x, y, z])
    return R, C


def project(R, C, K, dist, X: np.ndarray) -> np.ndarray:
    """Plane points (N, 2) mm (z = 0) -> distorted pixel coordinates (N, 2)."""
    P = np.hstack([X, np.zeros((len(X), 1))]) - C
    pc = P @ R.T
    xn, yn = pc[:, 0] / pc[:, 2], pc[:, 1] / pc[:, 2]
    r2 = xn ** 2 + yn ** 2
    s = 1 + dist[0] * r2 + dist[1] * r2 ** 2
    return np.stack([K[0, 0] * xn * s + K[0, 2], K[1, 1] * yn * s + K[1, 2]], 1)


def _undistort_norm(K, dist, U, V):
    """Pixel -> undistorted normalised image coordinates (fixed-point inversion of the radial model)."""
    xd, yd = (U - K[0, 2]) / K[0, 0], (V - K[1, 2]) / K[1, 1]
    xu, yu = xd.copy(), yd.copy()
    for _ in range(14):
        r2 = xu ** 2 + yu ** 2
        s = 1 + dist[0] * r2 + dist[1] * r2 ** 2
        xu, yu = xd / s, yd / s
    return xu, yu


def _plane_from_norm(R, C, xu, yu):
    """Intersect the rays through undistorted normalised coordinates with the plane z = 0 (board mm)."""
    ray = np.stack([xu, yu, np.ones_like(xu)], -1) @ R
    t = -C[2] / ray[..., 2]
    return C[0] + t * ray[..., 0], C[1] + t * ray[..., 1]


def _pixel_to_plane_exact(R, C, K, dist, U, V):
    xu, yu = _undistort_norm(K, dist, U, V)
    return _plane_from_norm(R, C, xu, yu)


def plane_map(R, C, K, dist, W: int, H: int, r0: int = 0, r1: int | None = None, cell: int = 32):
    """Float32 maps (X, Y) in mm of the plane point seen by each pixel centre, rows r0..r1.

    The undistorted normalised coordinates (smooth and almost linear in the pixel position) are evaluated on a coarse
    grid with `cell` px spacing and a two-cell margin and upsampled with cv2.resize (float linear; INTER_CUBIC has a 5 % ripple on a linear ramp); the exact projective
    intersection with the plane is then done per pixel.  (Interpolating X, Y directly is wrong by ~1 mm at 30 deg tilt
    because the plane map is projective; cv2.remap must not be used either: it quantises weights to 1/32.)"""
    r1 = H if r1 is None else r1
    pad = 2
    kx = W // cell + 1 + 2 * pad
    ky = H // cell + 1 + 2 * pad
    u = (np.arange(kx) - pad + 0.5) * cell - 0.5          # cv2.resize convention: dst = (src + 0.5) * cell - 0.5
    v = (np.arange(ky) - pad + 0.5) * cell - 0.5
    U, V = np.meshgrid(u, v)
    xu, yu = _undistort_norm(K, dist, U, V)
    xf = cv2.resize(xu.astype(np.float32), (kx * cell, ky * cell), interpolation=cv2.INTER_LINEAR)
    yf = cv2.resize(yu.astype(np.float32), (kx * cell, ky * cell), interpolation=cv2.INTER_LINEAR)
    sl = (slice(pad * cell + r0, pad * cell + r1), slice(pad * cell, pad * cell + W))
    X, Y = _plane_from_norm(R, C, xf[sl].astype(np.float64), yf[sl].astype(np.float64))
    return X.astype(np.float32), Y.astype(np.float32)


# --------------------------------------------------------------------------------------- photometrics


def _fbm_noise(shape, sigmas_px, amps, rng):
    h, w = shape
    out = np.zeros(shape, np.float32)
    for s, a in zip(sigmas_px, amps):
        if s < 0.35:
            continue
        f = max(1, int(s // 3))                      # generate at reduced resolution for large sigma
        z = rng.standard_normal((h // f + 2, w // f + 2), dtype=np.float32)
        z = cv2.GaussianBlur(z, (0, 0), s / f)
        z = cv2.resize(z, (w, h), interpolation=cv2.INTER_LINEAR if f > 1 else cv2.INTER_NEAREST)
        out += a * z / max(float(z.std()), 1e-6)
    return out


def _motion_kernel(length: float, angle: float) -> np.ndarray:
    n = int(2 * math.ceil(length) + 3) | 1
    k = np.zeros((n, n), np.float32)
    c = n // 2
    dx, dy = math.cos(angle) * length / 2, math.sin(angle) * length / 2
    cv2.line(k, (int(round((c - dx) * 16)), int(round((c - dy) * 16))), (int(round((c + dx) * 16)), int(round((c + dy) * 16))),
             1.0, 1, cv2.LINE_AA, 4)
    return k / k.sum()


# --------------------------------------------------------------------------------------- render

STRIP_ROWS = 512
HALO_ROWS = 32


def render(seed: int, cfg: SynthConfig | None = None, texture: Path | None = None):
    """Render one image.  Returns (jpeg_bytes, image_bgr_uint8, gt dict).

    The image is built in horizontal strips (with halo rows for the blur kernels) so that peak memory stays near
    250 MB at 12 MP; all random draws that affect geometry are made before the strip loop and strip-local noise uses
    per-strip generators, so the output is a pure function of (seed, cfg)."""
    cfg = cfg or SynthConfig()
    rng = np.random.default_rng([seed, 7919])
    W, H = cfg.width, cfg.height
    gt: dict = {"seed": int(seed), "image_w": W, "image_h": H}

    # ---------------- scene layout (mm, board frame)
    ppm_req = float(np.exp(rng.uniform(math.log(cfg.ppm_range[0]), math.log(cfg.ppm_range[1]))))
    # field of view at ppm_req leaves room for the crack next to the 156 mm paper sheet: cap the crack extent
    ext_hi = float(np.clip(0.9 * max(W, H) / ppm_req - (BOARD_W + 2 * PAPER_MARGIN) - 30.0, cfg.crack_extent_mm[0], cfg.crack_extent_mm[1]))
    g = pick_crack(rng, cfg, (cfg.crack_extent_mm[0], ext_hi))
    ang = float(rng.uniform(0, 2 * math.pi))
    flip = bool(rng.integers(2))
    cp = rotate_graph(g, ang, flip)
    c_lo, c_hi = cp.min(0) - g.w_mm.max() / 2, cp.max(0) + g.w_mm.max() / 2
    paper = np.array([-PAPER_MARGIN, -PAPER_MARGIN, BOARD_W + PAPER_MARGIN, BOARD_H + PAPER_MARGIN])
    side = str(rng.choice(["right", "left", "below", "above"]))
    gap = float(rng.uniform(6.0, 25.0))
    if side == "right":
        off = np.array([paper[2] + gap - c_lo[0], BOARD_H / 2 + rng.uniform(-30, 30) - (c_lo[1] + c_hi[1]) / 2])
    elif side == "left":
        off = np.array([paper[0] - gap - c_hi[0], BOARD_H / 2 + rng.uniform(-30, 30) - (c_lo[1] + c_hi[1]) / 2])
    elif side == "below":
        off = np.array([BOARD_W / 2 + rng.uniform(-30, 30) - (c_lo[0] + c_hi[0]) / 2, paper[3] + gap - c_lo[1]])
    else:
        off = np.array([BOARD_W / 2 + rng.uniform(-30, 30) - (c_lo[0] + c_hi[0]) / 2, paper[1] - gap - c_hi[1]])
    cp = cp + off
    lay_lo = np.minimum(paper[:2], cp.min(0) - 2)
    lay_hi = np.maximum(paper[2:], cp.max(0) + 2)
    centre = (lay_lo + lay_hi) / 2
    corners_lay = np.array([[lay_lo[0], lay_lo[1]], [lay_hi[0], lay_lo[1]], [lay_hi[0], lay_hi[1]], [lay_lo[0], lay_hi[1]]])

    # ---------------- camera
    fpx = float(rng.uniform(*cfg.f_rel)) * W
    K = np.array([[fpx, 0, (W - 1) / 2], [0, fpx, (H - 1) / 2], [0, 0, 1.0]])
    dist = np.array([rng.normal(0, cfg.dist_k1_sigma), rng.normal(0, cfg.dist_k2_sigma)])
    tilt = math.radians(min(abs(rng.normal(0, cfg.tilt_sigma_deg)), cfg.tilt_deg_max))
    azim = float(rng.uniform(0, 2 * math.pi))
    roll = math.radians(float(rng.uniform(*cfg.roll_deg_range)))
    dist_mm = fpx / ppm_req
    for _ in range(80):                       # move away until the whole layout fits with a 3 % margin
        R, C = look_at_pose(centre, dist_mm, tilt, azim, roll)
        px = project(R, C, K, dist, corners_lay)
        mx, my = 0.03 * W, 0.03 * H
        if px[:, 0].min() >= mx and px[:, 0].max() <= W - 1 - mx and px[:, 1].min() >= my and px[:, 1].max() <= H - 1 - my:
            break
        dist_mm *= 1.04

    def local_ppm(p):
        e = 0.5
        a = project(R, C, K, dist, np.array([p + [e, 0], p - [e, 0], p + [0, e], p - [0, e]], float))
        J = np.stack([(a[0] - a[1]) / (2 * e), (a[2] - a[3]) / (2 * e)], 1)
        return float(math.sqrt(abs(np.linalg.det(J))))
    ppm_board = local_ppm(np.array([BOARD_W / 2, BOARD_H / 2]))
    ppm_crack = local_ppm(cp.mean(0))
    ppm_max = max(local_ppm(c) for c in corners_lay)
    nz = R[:, 2]
    obliq = math.degrees(math.acos(min(1.0, abs(nz[2]) / np.linalg.norm(nz))))

    # ---------------- layers (small, plane-referenced)
    P_l = float(np.clip(1.15 * ppm_max, 6.0, 40.0))
    Pb = int(max(4, math.ceil(P_l)))
    bimg = make_board().generateImage((int(BOARD_W * Pb), int(BOARD_H * Pb)), marginSize=0, borderBits=1)
    # anti-alias: the layer is resampled without a pre-filter (cv2.remap), so blur it by ~half the local minification
    ppm_min_board = min(local_ppm(np.array(c, float)) for c in ([0, 0], [BOARD_W, 0], [0, BOARD_H], [BOARD_W, BOARD_H]))
    sig_b = math.hypot(max(0.5, 0.03 * Pb), 0.45 * max(Pb / ppm_min_board - 1.0, 0.0) * 1.5)      # toner spread + AA
    bimg = cv2.GaussianBlur(bimg.astype(np.float32) / 255.0, (0, 0), sig_b)
    cov_ss, lo = rasterise_crack(cp, g, cfg.ss_ppm)
    Pc = float(np.clip(1.15 * ppm_max, 6.0, cfg.ss_ppm))
    cw, ch = max(1, int(round(cov_ss.shape[1] * Pc / cfg.ss_ppm))), max(1, int(round(cov_ss.shape[0] * Pc / cfg.ss_ppm)))
    Pc_x, Pc_y = cw / (cov_ss.shape[1] / cfg.ss_ppm), ch / (cov_ss.shape[0] / cfg.ss_ppm)
    cov = cv2.resize(cov_ss, (cw, ch), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    del cov_ss
    ratio_c = Pc / max(min(local_ppm(c) for c in corners_lay), 1e-6)
    if ratio_c > 1.05:
        cov = cv2.GaussianBlur(cov, (0, 0), 0.45 * (ratio_c - 1.0) * 1.5)
    texs = list_textures()
    if not texs:
        raise RuntimeError(f"no textures in {TEX_DIR}")
    tpath = texture or texs[int(rng.integers(len(texs)))]
    tex = load_texture(tpath)
    th, tw = tex.shape[:2]
    tile_mm = float(rng.uniform(*cfg.tex_tile_mm))
    t_off = rng.uniform(0, tile_mm, 2)
    tflip = bool(rng.integers(2))
    is_plaster = "Plaster" in tpath.name
    albedo = float(rng.uniform(0.40, 0.68) if is_plaster else rng.uniform(0.18, 0.50))
    tint = rng.normal(1.0, 0.025, 3).astype(np.float32)
    amps = np.array([0.075, 0.07, 0.06]) * (0.8 if is_plaster else 1.0)
    sig = np.array([0.40, 0.20, 0.10]) * ppm_board
    # pores (global list): x, y (px), radius (px), depth
    n_pores = int(rng.uniform(0.0, 1.2) * W * H / (ppm_board ** 2) / 100.0)
    pores = np.stack([rng.uniform(0, W, n_pores), rng.uniform(0, H, n_pores),
                      np.exp(rng.uniform(math.log(0.12), math.log(0.7), n_pores)) * ppm_board,
                      rng.uniform(0.25, 0.8, n_pores)], 1) if n_pores else np.zeros((0, 4))
    rho_paper = float(rng.uniform(*cfg.paper_albedo))
    ink = float(rng.uniform(*cfg.ink_ratio))
    # illumination
    gdir = rng.uniform(0, 2 * math.pi)
    gmag = rng.uniform(0.0, 0.35)
    lowE = cv2.resize(np.exp(0.03 * rng.standard_normal((12, 16))).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    shadow = None
    if rng.random() < cfg.p_shadow:
        shadow = {"a": float(rng.uniform(0, 2 * math.pi)), "d0": float(rng.uniform(-0.3, 0.3) * W),
                  "penumbra_px": float(rng.uniform(20, 150)), "depth": float(rng.uniform(0.25, 0.55))}
    glare = None
    if rng.random() < cfg.p_glare:
        glare = {"cx": float(rng.uniform(0.15, 0.85) * W), "cy": float(rng.uniform(0.15, 0.85) * H),
                 "sx": float(rng.uniform(150, 900)), "sy": float(rng.uniform(150, 900)), "th": float(rng.uniform(0, math.pi)),
                 "amp": float(np.exp(rng.uniform(math.log(0.12), math.log(1.4))))}
    wb = rng.normal(1.0, 0.04, 3).astype(np.float32)
    tgt = float(rng.uniform(*cfg.paper_exposure_srgb)) / 255.0
    exposure = float(srgb_to_lin(np.array([tgt], np.float32))[0]) / rho_paper
    sig_psf = float(rng.uniform(*cfg.psf_sigma_px))
    defocus = None
    if rng.random() < cfg.p_defocus:
        defocus = float(rng.uniform(*cfg.defocus_sigma_px))
        sig_psf = float(math.hypot(sig_psf, defocus))
    motion = None
    if rng.random() < cfg.p_motion:
        motion = {"len_px": float(rng.uniform(*cfg.motion_len_px)), "angle_rad": float(rng.uniform(0, math.pi))}
    na = float(np.exp(rng.uniform(math.log(cfg.noise_a[0]), math.log(cfg.noise_a[1]))))
    nb = float(np.exp(rng.uniform(math.log(cfg.noise_b[0]), math.log(cfg.noise_b[1]))))
    sharp = float(rng.uniform(*cfg.sharpen_amount))
    q = int(rng.integers(cfg.jpeg_quality[0], cfg.jpeg_quality[1] + 1))
    mk = _motion_kernel(motion["len_px"], motion["angle_rad"]) if motion else None

    # ---------------- strip loop
    out = np.zeros((H, W, 3), np.uint8)
    for k, r0 in enumerate(range(0, H, STRIP_ROWS)):
        r1 = min(H, r0 + STRIP_ROWS)
        a0, a1 = max(0, r0 - HALO_ROWS), min(H, r1 + HALO_ROWS)
        h_ = a1 - a0
        srng = np.random.default_rng([seed, 31, k])
        Xm, Ym = plane_map(R, C, K, dist, W, H, a0, a1)
        # board / paper
        B = cv2.remap(bimg, (Xm * Pb - 0.5).astype(np.float32), (Ym * Pb - 0.5).astype(np.float32), cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_CONSTANT, borderValue=1.0)
        B = np.where((Xm >= 0) & (Xm < BOARD_W) & (Ym >= 0) & (Ym < BOARD_H), B, 1.0).astype(np.float32)
        soft = 0.15
        pa = (np.clip((Xm - paper[0]) / soft + 0.5, 0, 1) * np.clip((paper[2] - Xm) / soft + 0.5, 0, 1) *
              np.clip((Ym - paper[1]) / soft + 0.5, 0, 1) * np.clip((paper[3] - Ym) / soft + 0.5, 0, 1)).astype(np.float32)
        Cm = cv2.remap(cov, ((Xm - lo[0]) * Pc_x - 0.5).astype(np.float32), ((Ym - lo[1]) * Pc_y - 0.5).astype(np.float32),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)
        # wall texture
        tx = (((Xm + t_off[0]) / tile_mm) * tw - 0.5).astype(np.float32)
        ty = (((Ym + t_off[1]) / tile_mm) * th - 0.5).astype(np.float32)
        if tflip:
            tx, ty = ty, tx
        T = cv2.remap(tex, tx, ty, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        del tx, ty, Xm, Ym
        T *= (albedo * tint)[None, None, :]
        gn = _fbm_noise((h_, W), sig, amps, srng)
        T *= np.exp(gn)[:, :, None]
        del gn
        if len(pores):
            sel = pores[(pores[:, 1] > a0 - 8 * ppm_board) & (pores[:, 1] < a1 + 8 * ppm_board)]
            if len(sel):
                pl = np.zeros((h_, W), np.float32)
                for x_, y_, r_, d_ in sel:
                    cv2.circle(pl, (int(x_ * 8), int((y_ - a0) * 8)), max(1, int(r_ * 8)), float(d_), -1, cv2.LINE_8, 3)
                pl = cv2.GaussianBlur(pl, (0, 0), 0.6)
                T *= (1 - pl)[:, :, None]
        np.clip(T, 0.003, 0.95, out=T)
        T *= (1 - Cm)[:, :, None]                                     # the crack darkens the wall only
        paper_alb = rho_paper * (ink + (1 - ink) * B)
        paper_alb *= (1 + 0.004 * _fbm_noise((h_, W), [1.0], [1.0], srng))
        A = T * (1 - pa)[:, :, None]
        A += (paper_alb * pa)[:, :, None]
        del T, B, pa, Cm, paper_alb
        # illumination (analytic in image coordinates, consistent across strips)
        yy = np.arange(a0, a1, dtype=np.float32)[:, None]
        xx = np.arange(W, dtype=np.float32)[None, :]
        E = 1.0 + gmag * 2 * ((xx / W - 0.5) * math.cos(gdir) + (yy / H - 0.5) * math.sin(gdir))
        E = E * lowE[a0:a1]
        if shadow:
            sd = (xx - W / 2) * math.cos(shadow["a"]) + (yy - H / 2) * math.sin(shadow["a"]) - shadow["d0"]
            E = E * (1 - shadow["depth"] / (1 + np.exp(-sd / shadow["penumbra_px"])))
        E = (E * exposure).astype(np.float32)
        A *= E[:, :, None]
        A *= wb[None, None, :]
        if glare:
            dx, dy = xx - glare["cx"], yy - glare["cy"]
            u = dx * math.cos(glare["th"]) + dy * math.sin(glare["th"])
            v = -dx * math.sin(glare["th"]) + dy * math.cos(glare["th"])
            Gl = glare["amp"] * exposure * rho_paper * np.exp(-0.5 * ((u / glare["sx"]) ** 2 + (v / glare["sy"]) ** 2))
            A += Gl.astype(np.float32)[:, :, None]
        L = cv2.GaussianBlur(A, (0, 0), sig_psf)
        del A, E
        if mk is not None:
            L = cv2.filter2D(L, -1, mk, borderType=cv2.BORDER_REFLECT)
        noise = srng.standard_normal(L.shape, dtype=np.float32)
        noise = cv2.GaussianBlur(noise, (0, 0), 0.55)
        noise /= max(float(noise.std()), 1e-6)
        np.clip(L, 0, None, out=L)
        L += noise * np.sqrt(na * L + nb)
        del noise
        np.clip(L, 0, 1, out=L)
        S = lin_to_srgb(L)
        del L
        if sharp > 0.02:
            bl = cv2.GaussianBlur(S, (0, 0), 1.2)
            S = np.clip(S + sharp * (S - bl), 0, 1)
            del bl
        out[r0:r1] = np.clip(np.round(S[r0 - a0:r1 - a0, :, ::-1] * 255.0), 0, 255).astype(np.uint8)
    img = out
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])

    # ---------------- ground truth
    bc = make_board().getChessboardCorners()[:, :2]
    bc_px = project(R, C, K, dist, bc.astype(np.float64))
    stations_px = project(R, C, K, dist, cp)
    sel = np.arange(len(cp))[:: max(1, len(cp) // 400)]
    rvec, _ = cv2.Rodrigues(R)
    gt.update({
        "jpeg_quality": q,
        "camera": {"K": K.tolist(), "dist_k1k2": dist.tolist(), "rvec": rvec.ravel().tolist(),
                   "tvec_mm": (-R @ C).tolist(), "centre_mm": C.tolist(), "obliquity_deg": obliq,
                   "tilt_deg": math.degrees(tilt), "roll_deg": math.degrees(roll)},
        "scale": {"ppm_board": ppm_board, "ppm_crack": ppm_crack, "ppm_requested": ppm_req, "ppm_max": ppm_max},
        "board": {"corners_mm": bc.tolist(), "corners_px": bc_px.tolist(), "paper_mm": paper.tolist(),
                  "squares": [SQUARES_X, SQUARES_Y], "square_mm": SQUARE_MM, "marker_mm": MARKER_MM},
        "crack": {"source": g.source, "mask_id": g.mask_id, "side": side, "gap_mm": gap,
                  "width_median_mm": float(np.median(g.w_mm)), "width_mean_mm": float(g.w_mm.mean()),
                  "width_p10_mm": float(np.percentile(g.w_mm, 10)), "width_p90_mm": float(np.percentile(g.w_mm, 90)),
                  "n_nodes": int(len(cp)), "length_mm": _crack_len(cp, g),
                  "stations_mm": [[round(float(cp[i, 0]), 3), round(float(cp[i, 1]), 3), round(float(g.w_mm[i]), 4)] for i in sel],
                  "stations_px": [[round(float(stations_px[i, 0]), 2), round(float(stations_px[i, 1]), 2)] for i in sel]},
        "photometric": {"texture": tpath.name, "tile_mm": tile_mm, "albedo": albedo, "paper_albedo": rho_paper,
                        "ink_ratio": ink, "exposure": exposure, "psf_sigma_px": sig_psf, "defocus_sigma_px": defocus, "motion": motion,
                        "noise_a": na, "noise_b": nb, "sharpen": sharp, "glare": glare, "shadow": shadow,
                        "shading_gradient": gmag, "paper_target_srgb": tgt * 255, "wb": wb.tolist(),
                        "n_pores": int(n_pores)},
        "config": asdict(cfg),
    })
    return bytes(buf), img, gt


def _crack_len(cp, g) -> float:
    """Approximate centreline length (mm): total edge length / 2 (8-neighbour graph double counts diagonals)."""
    e = g.edges
    L = np.hypot(*(cp[e[:, 0]] - cp[e[:, 1]]).T)
    return float(L.sum() / 2.6)


def _job(args):
    i, seed, out, cfg_d = args
    cfg = SynthConfig(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in cfg_d.items()})
    name = f"synth_{i:05d}"
    t0 = time.time()
    try:
        buf, _, gt = render(seed, cfg)
    except Exception as e:                                    # keep the batch going; record the failure
        return name, f"FAILED {type(e).__name__}: {e}"
    gt["name"] = name
    (Path(out) / f"{name}.jpg").write_bytes(buf)
    (Path(out) / f"{name}.json").write_text(json.dumps(gt))
    return name, f"{time.time() - t0:.1f}s"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate synthetic crack photos with exact ground truth.")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--out", default="data/synth/v1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--size", default="4096x3072")
    ap.add_argument("--start", type=int, default=0, help="first image index (resume)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    w, h = (int(x) for x in a.size.lower().split("x"))
    cfg = SynthConfig(width=w, height=h)
    cfg_d = asdict(cfg)
    jobs = [(i, a.seed * 1_000_003 + i, str(out), cfg_d) for i in range(a.start, a.start + a.n)
            if not (out / f"synth_{i:05d}.json").exists()]
    (out / "config.json").write_text(json.dumps({"seed": a.seed, "n": a.n, "config": cfg_d}, indent=1))
    t0 = time.time()
    if a.workers <= 1:
        for j in jobs:
            print(*_job(j), flush=True)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for k, (name, msg) in enumerate(ex.map(_job, jobs)):
                print(f"[{k + 1}/{len(jobs)}] {name} {msg}", flush=True)
    print(f"done in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
