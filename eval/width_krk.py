"""krkCMd leg of the width-estimator evaluation (eval/width_eval.py).

krkCMd (Jakubowski & Tomczak, Sci. Data 2025, M1) holds 19,098 grey-level profiles at 252 px/mm with an operator
width (`MANwidth` = the black core between the steepest-gradient points, bevelled crack-mouth shading excluded).
This module runs the REAL ``measure._measure_roi`` (not the 1-D reduction in widthbench) on a profile turned into a
short straight crack image, at simulated phone resolutions (widthbench.simulate_lowres: Gaussian PSF 0.75 px, box
integration at a random sub-pixel phase, shot + read noise, 8 bit).  Split = widthbench's alternate specimen images
(even clusters = calibration = TUNE, odd = TEST); crack-present profiles only.

Reported per width bin (default: the gate bin 0.30-0.50 mm):
  added_<ppm>   |w(ppm) - w(reference)| where the reference is the SAME estimator on a clean 40 px/mm version of the
                profile (no PSF, no noise).  The convention cancels, so this is the resolution cost only.
  core_<ppm>    error of the black-core estimator against MANwidth (operator convention)
  full_<ppm>    error of the headline (full-stroke) estimator against MANwidth (convention gap included, NOT an accuracy)
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori import measure  # noqa: E402
from prohori import widthbench as wb  # noqa: E402

RUN = ROOT / "eval" / "runs" / "width_autoresearch"
DATA = ROOT / "data" / "datasets" / "krkcmd"
PPMS = (10.0, 15.0, 20.0)
REF_PPM = 40.0
PSF = 0.75
GATE_BIN = (0.30, 0.50)
LEN_MM, PAD_MM = 14.0, 4.0


def load_split():
    p = wb.load_krkcmd(DATA)
    cl = p.cluster
    uc = np.unique(cl)
    cal = set(uc[::2])
    is_cal = np.array([c in cal for c in cl])
    return p, is_cal


def make_set(which: str, n_gate: int = 600, n_other: int = 400, seed: int = 0) -> dict:
    """Profiles + simulated versions for the TUNE (calibration half, subsampled) or TEST (odd half, all) set. Cached."""
    f = RUN / f"krk_{which}_{n_gate}_{n_other}.npz"
    if f.exists():
        z = np.load(f, allow_pickle=False)
        return {k: z[k] for k in z.files}
    p, is_cal = load_split()
    sel = (is_cal if which == "tune" else ~is_cal) & (p.man > 0)
    idx = np.nonzero(sel)[0]
    rng = np.random.default_rng(seed)
    if which == "tune":
        man = p.man[idx] / 1000.0
        g = idx[(man >= GATE_BIN[0]) & (man < GATE_BIN[1])]
        o = idx[~((man >= GATE_BIN[0]) & (man < GATE_BIN[1]))]
        idx = np.sort(np.concatenate([rng.choice(g, min(n_gate, len(g)), replace=False),
                                      rng.choice(o, min(n_other, len(o)), replace=False)]))
    X = p.X[idx]
    native_sigma = wb.native_edge_sigma_mm(p)
    out = {"idx": idx, "man_mm": p.man[idx] / 1000.0, "cluster": p.cluster[idx], "native_sigma_mm": np.array(native_sigma),
           "native": X}
    mdl = wb.SimModel(psf_sigma_px=PSF)
    for ppm in PPMS:
        out[f"sim_{ppm:g}"] = wb.simulate_lowres(X, ppm, mdl, np.random.default_rng(seed + int(ppm) + 1))
    clean = wb.SimModel(psf_sigma_px=0.0, noise=False, random_phase=False)
    out["ref"] = wb.simulate_lowres(X, REF_PPM, clean, np.random.default_rng(seed))
    np.savez(f, **out)
    return out


def profile_to_rp(P: np.ndarray, ppm: float, length_mm: float = LEN_MM, pad_mm: float = PAD_MM):
    """ROI pack of a straight vertical crack built from a 1-D profile sampled at `ppm` (as measure._extract_roi would
    deliver it: cubic resample to S = clip(ceil(ppm), 12, 40) px/mm; above 40 px/mm the profile is used as is), plus
    the seed x position.  Edge-replicated padding."""
    P = np.asarray(P, np.float32)
    S = float(ppm) if ppm > wb.PIPELINE_MAX_S else float(np.clip(math.ceil(ppm), 12, wb.PIPELINE_MAX_S))
    if abs(S - ppm) > 1e-9:
        Wn = int(round(len(P) * S / ppm))
        P = cv2.resize(P.reshape(1, -1), (Wn, 1), interpolation=cv2.INTER_CUBIC)[0]
        if ppm <= wb.PIPELINE_MAX_S:
            P = np.clip(np.round(P), 0, 255)
    pad = int(round(pad_mm * S))
    rows = int(round(length_mm * S))
    line = np.pad(P, pad, mode="edge")
    roi = np.clip(np.round(np.tile(line, (rows, 1))), 0, 255).astype(np.uint8)
    D = wb.srgb_to_lin(P)
    D = D.max() - D
    c0 = len(P) // 2
    hw = int(0.5 * S)
    lo_, hi_ = max(0, c0 - hw), min(len(P), c0 + hw + 1)
    Ds = cv2.GaussianBlur(D.astype(np.float32).reshape(1, -1), (0, 0), 0.1 * S).ravel()[lo_:hi_]
    top = np.nonzero(Ds >= Ds.max() - 0.01 * max(Ds.max(), 1e-9))[0]
    xs = (pad + lo_ + float(np.median(top))) / S
    seed_b = np.array([[xs, 0.1 * length_mm], [xs, 0.9 * length_mm]])
    return {"roi": roi, "val": np.ones(roi.shape, bool), "lo": np.zeros(2), "S": S, "seed_b": seed_b, "corridor_mm": 3.0}


KEYS = ("full", "core", "fwhm", "dt", "ink")


def width_one(P, ppm, sigma_mm, cfg=None, ink_dark=0.0):
    rp = profile_to_rp(P, ppm)
    m = measure._measure_roi(rp, ink_dark, sigma_mm, None, cfg)
    if m is None:
        return [np.nan] * len(KEYS)
    return [m["profile_mm"], m.get("core_mm", np.nan), m["fwhm_mm"], m["dt_mm"], m["profile_ink_mm"]]


def _chunk(args):
    Y, ppm, sigma_mm, cfg = args
    return np.array([width_one(y, ppm, sigma_mm, cfg) for y in Y], float)


def predict(Y: np.ndarray, ppm: float, sigma_mm: float, cfg=None, workers: int = 3, chunk: int = 250) -> np.ndarray:
    parts = [(Y[i:i + chunk], ppm, sigma_mm, cfg) for i in range(0, len(Y), chunk)]
    if workers > 1 and len(parts) > 1:
        with ProcessPoolExecutor(workers) as ex:
            res = list(ex.map(_chunk, parts))
    else:
        res = [_chunk(a) for a in parts]
    return np.vstack(res)


def run(cfg: dict | None, which: str = "tune", workers: int = 3, ppms=PPMS) -> dict:
    st = make_set(which)
    nat_sig = float(st["native_sigma_mm"])
    man = st["man_mm"]
    out = {"man": man, "cluster": st["cluster"]}
    # reference: same estimator on a clean 40 px/mm version (sigma = native specimen/scanner softness + pixel footprint)
    out["ref"] = predict(st["ref"], REF_PPM, wb.sigma_mm_total(0.0, REF_PPM, nat_sig), cfg, workers)
    for ppm in ppms:
        out[f"p{ppm:g}"] = predict(st[f"sim_{ppm:g}"], ppm, wb.sigma_mm_total(PSF, ppm, nat_sig), cfg, workers)
    return out


def metrics(out: dict, ppm: float = 15.0, lo: float = GATE_BIN[0], hi: float = GATE_BIN[1]) -> dict:
    man = out["man"]
    sel = (man >= lo) & (man < hi)
    P, R = out[f"p{ppm:g}"], out["ref"]
    k = {n: i for i, n in enumerate(KEYS)}
    res = {}
    for nm in ("full", "fwhm", "core"):
        i = k[nm]
        ok = sel & np.isfinite(P[:, i]) & np.isfinite(R[:, i])
        add = np.abs(P[ok, i] - R[ok, i])
        res[f"added_{nm}"] = float(add.mean()) if ok.any() else np.nan
        res[f"added_{nm}_p95"] = float(np.percentile(add, 95)) if ok.any() else np.nan
        ok2 = sel & np.isfinite(P[:, i])
        e = P[ok2, i] - man[ok2]
        res[f"vsman_{nm}_mae"] = float(np.abs(e).mean()) if ok2.any() else np.nan
        res[f"vsman_{nm}_bias"] = float(e.mean()) if ok2.any() else np.nan
        res[f"ok_{nm}"] = float(ok2.sum() / max(sel.sum(), 1))
    # all-profile RMSE of the core convention vs MAN (crack-present), refusals excluded
    i = k["core"]
    okc = np.isfinite(P[:, i])
    res["core_rmse_all"] = float(np.sqrt(np.mean((P[okc, i] - man[okc]) ** 2))) if okc.any() else np.nan
    res["n_gate_bin"] = int(sel.sum())
    return res
