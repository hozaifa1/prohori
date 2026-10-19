"""Open crack-width benchmark on krkCMd (Jakubowski & Tomczak, Sci. Data 2025) + empirical px/mm gate curve.

What this module does (see research/WIDTHBENCH_NOTES.md for the citations and reasoning):

1. ``load_krkcmd``      read the Zenodo table (19,098 grey-level profiles of 501 px at 3.96875 um/px, operator reference
                        width ``MANwidth`` in um, plus the shipped DLM and AED benchmark predictions).
2. ``aed_vba``          faithful Python port of the authors' VBA analytic edge detector, used to check that we
                        understand (and can reproduce) the published AED baseline column.
3. ``simulate_lowres``  degrade the 252 px/mm profiles to a phone-like sampling density: exposure normalisation,
                        Gaussian PSF, exact box integration over the output pixel at a random sub-pixel phase,
                        shot + read noise in linear light, sRGB encode, 8-bit quantisation.
4. ``profile_widths``   1-D reduction of the estimators in ``prohori.measure`` (distance transform, FWHM, profile
                        integral with the crack's own contrast, profile integral with a board-ink reference, and the
                        final blend).  It re-implements the arithmetic of ``measure._measure_one`` for a perfectly
                        straight crack and calls ``measure._fwhm`` / ``measure.INK_RATIO`` directly.
5. ``pipeline_width``   thin adapter that feeds the *unmodified* ``measure._measure_one`` with a synthetic straight
                        crack image built from the profile.  Used to prove the 1-D reduction is faithful.
6. metrics / bootstrap / gate derivation (``bin_metrics``, ``gate_from_curve``).

``measure.py`` is imported read-only and never edited.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import measure as _measure

# ----------------------------------------------------------------------------- constants

DPI = 6400
UM_PER_PX = 25400.0 / DPI                 # 3.96875 um / px (scanner pixel pitch, Sci. Data 2025 Methods)
NATIVE_PX_PER_MM = 1000.0 / UM_PER_PX     # 251.97 px / mm
PROFILE_LEN = 501
OPERATOR_RMS_UM = 16.6                    # inter-operator RMS, 5 operators (Sci. Data 2025, Table 4)
PIPELINE_MAX_S = 40.0                     # measure._measure_one clamps its working resolution to [12, 40] px/mm

#: width bins in mm, [lo, hi) on the operator reference
WIDTH_BINS = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.5), (0.5, 0.9)]
#: pooled bins used for the certification criterion
POOLED_BINS = {
    "<0.5mm": (0.0, 0.5),          # METRICS 1a/1b literal bin (crack present: w_ref > 0)
    ">=0.5mm": (0.5, 10.0),
    "0.30-0.50mm": (0.3, 0.5),     # the regime the product claims (panel specimens C1-C3)
    "crack>0": (0.0, 10.0),
}

#: METRICS 1a "Target" tier for thin cracks, plus the 1b px-equivalent bound
TARGET = dict(mae_mm=0.05, p95_mm=0.10, abs_bias_mm=0.02, ratio_dev=0.05, cov=0.12)


# ----------------------------------------------------------------------------- data

@dataclass
class Profiles:
    X: np.ndarray            # (n, 501) float32 brightness 0..255
    man: np.ndarray          # um, operator reference
    dlm: np.ndarray          # um, shipped CNN metasensor prediction
    aed: np.ndarray          # um, shipped analytic-edge-detector prediction
    series: np.ndarray
    image: np.ndarray
    gridline: np.ndarray
    stage: np.ndarray
    names: np.ndarray = field(default=None)

    def __len__(self):
        return len(self.man)

    @property
    def cluster(self) -> np.ndarray:
        """Capture-session id = (series, image): profiles of one scanned specimen face are correlated."""
        return np.array([f"{s}|{i}" for s, i in zip(self.series, self.image)])

    def subset(self, idx) -> "Profiles":
        return Profiles(self.X[idx], self.man[idx], self.dlm[idx], self.aed[idx], self.series[idx], self.image[idx],
                        self.gridline[idx], self.stage[idx], None if self.names is None else self.names[idx])


def load_krkcmd(path: str | Path, use_cache: bool = True) -> Profiles:
    """Load krkCMd_table.csv (or a directory containing it).  A float32 .npz cache is written next to it."""
    path = Path(path)
    table = path if path.suffix == ".csv" else path / "krkCMd_table.csv"
    cache = table.with_suffix(".cache.npz")
    if use_cache and cache.exists() and cache.stat().st_mtime >= table.stat().st_mtime:
        z = np.load(cache, allow_pickle=False)
        return Profiles(z["X"], z["man"], z["dlm"], z["aed"], z["series"], z["image"], z["gridline"], z["stage"],
                        z["names"])
    rows_X, man, dlm, aed, series, image, grid, stage, names = [], [], [], [], [], [], [], [], []
    with open(table, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        header = next(rd)
        if len(header) != 510 or header[6] != "x1" or header[506] != "x501" or header[507] != "MANwidth":
            raise ValueError("unexpected krkCMd table layout")
        for r in rd:
            names.append(r[1]); series.append(r[2]); image.append(int(r[3])); grid.append(r[4]); stage.append(int(r[5]))
            rows_X.append(np.asarray(r[6:507], dtype=np.float32))
            man.append(float(r[507])); dlm.append(float(r[508])); aed.append(float(r[509]))
    p = Profiles(np.vstack(rows_X), np.array(man), np.array(dlm), np.array(aed), np.array(series), np.array(image),
                 np.array(grid), np.array(stage), np.array(names))
    if use_cache:
        try:
            np.savez(cache, X=p.X, man=p.man, dlm=p.dlm, aed=p.aed, series=p.series, image=p.image,
                     gridline=p.gridline, stage=p.stage, names=p.names)
        except OSError:
            pass
    return p


# ----------------------------------------------------------------------------- AED (port of CrackWidthAED_VBA)

def _cell(p: Profiles, r: int, col: int) -> float:
    """Spreadsheet cell (row r, 1-based column) of the krkCMd sheet: 7..507 profile, 508 MAN, 509 DLM, else empty."""
    if 7 <= col <= 507:
        return float(p.X[r, col - 7])
    if col == 508:
        return float(p.man[r])
    if col == 509:
        return float(p.dlm[r])
    return 0.0


def aed_vba(p: Profiles, k: int = 6, resolution: float = DPI, accuracy: float = 5.0, step: int = 10,
            brightness_increment: float = 5.0) -> np.ndarray:
    """Port of ``CrackWidthAED_VBA.txt`` (Zenodo krkCMd_scripts.zip).  Returns widths in um.

    The sheet has 510 columns: col 6 = Stage, cols 7..507 = the profile, 508 = MAN, 509 = DLM, 510 = result.  VBA reads
    cells outside the profile (``j + step`` near col 507); we reproduce that by padding with MAN/DLM then zeros
    (empty cells).  Rows come in stacks of ``k`` stages; stage-1 rows derive ``j_upper/j_lower`` that the later-stage
    rows reuse (VBA module-level state).  Two ``<> Null`` conditions in the VBA are always Null (= False) and are
    therefore dropped, exactly as VBA evaluates them.
    """
    n = len(p)
    out = np.zeros(n)
    um = 25.4 / resolution * 1000.0
    c = np.zeros(640)
    j_upper = j_lower = 0
    for r in range(n):
        c[:] = 0.0
        c[6] = p.stage[r]
        c[7:508] = p.X[r]
        c[508] = p.man[r]
        c[509] = p.dlm[r]
        if r % k == 0:
            mn = c[7:508].min()
            j = 7
            while c[j] != mn:
                j += 1
            while c[j - 1] - mn <= accuracy and j > 7:
                j -= 1
            y_upper = j
            while c[j + 1] - mn <= accuracy and j < 507:
                j += 1
            y_lower = j
            out[r] = (y_lower - y_upper + 1) * um
            d_up = c[y_upper - step - 1] - c[y_upper - 1]
            j_upper = y_upper - 1
            guard = 0
            while not (d_up <= brightness_increment or j_upper - step == 2) and guard < 600:
                if j_upper - step < 1:
                    break
                d_up = c[j_upper - step] - c[j_upper]
                j_upper -= 1
                guard += 1
            ext = c[max(j_upper - step, 1):j_upper + 1].max()
            while c[j_upper] != ext and j_upper > 7:
                j_upper -= 1
            d_lo = c[y_lower + step] - c[y_lower]
            j_lower = y_lower + 1
            guard = 0
            while not (d_lo <= brightness_increment or j_lower + step == 507) and guard < 600:
                if j_lower + step >= 630:
                    break
                d_lo = c[j_lower + step] - c[j_lower]
                j_lower += 1
                guard += 1
            ext = c[j_lower:j_lower + step + 1].max()
            while c[j_lower] != ext and j_lower < 507:
                j_lower += 1
        else:
            lpe = 0
            pts: list[float] = []
            half = step // 2
            for jj in range(j_upper, j_lower + 1):
                prev = lpe
                if c[jj + half] - c[jj] <= 0 and c[jj + half + 1] - c[jj + 1] > 0:
                    lpe += 1
                    if lpe - prev > 0:
                        pts.append(c[jj:jj + half + 1].min())
                if c[jj + half] - c[jj] >= 0 and c[jj + half] - c[jj + 1] < 0:
                    lpe += 1
                    if lpe - prev > 0:
                        pts.append(c[jj:jj + half + 2].max())
            seg = c[j_upper:j_lower + 1]
            min_inner = seg.min()
            j = j_upper
            while c[j] != min_inner:
                j += 1
            while c[j - 1] - min_inner <= accuracy and j - 2 >= j_upper:
                j -= 1
            yu = j
            while c[j + 1] - min_inner <= accuracy and j + 2 <= j_lower:
                j += 1
            yl = j
            # stage-1 row of this stack
            r1 = r - (r % k)
            m1u = _cell(p, r1, j_upper)
            m1l = _cell(p, r1, j_lower)
            mu, ml = c[j_upper], c[j_lower]
            avg = seg.mean()
            cw0 = False
            if lpe == 0 and c[yu] >= m1u and c[yl] >= m1l:
                cw0 = True
            elif lpe == 0 and (c[yu] < m1u or c[yl] < m1l) and avg > (m1u + m1l) / 2:
                cw0 = True
            elif lpe >= 1 and avg > (mu + ml) / 2 and (max(pts) - min(pts)) < 100:
                cw0 = True
            else:
                if lpe == 0:
                    min_inner = 0.0  # WorksheetFunction.Min over an all-Empty array
                j = j_upper
                guard = 0
                while c[j] != min_inner and guard < 700:
                    j += 1
                    guard += 1
                while c[j - 1] - min_inner <= accuracy and j - 2 >= j_upper:
                    j -= 1
                yu = j
                while c[j + 1] - min_inner <= accuracy and j + 2 <= j_lower:
                    j += 1
                yl = j
            out[r] = 0.0 if cw0 else (yl - yu + 1) * um
    return out


# ----------------------------------------------------------------------------- colour / photometry helpers

def srgb_to_lin(v255: np.ndarray) -> np.ndarray:
    v = np.asarray(v255, np.float64) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def lin_to_srgb255(lin: np.ndarray) -> np.ndarray:
    l = np.clip(lin, 0.0, 1.0)
    return 255.0 * np.where(l <= 0.0031308, 12.92 * l, 1.055 * np.power(l, 1 / 2.4) - 0.055)


@dataclass(frozen=True)
class SimModel:
    """Phone-like degradation of a 252 px/mm scan profile (all in linear light until the final encode).

    psf_sigma_px   Gaussian optical PSF sigma in *output* pixels (METRICS 1b: 0.5-1.0 px)
    full_well_e    electrons at linear value 1.0 (shot noise = Poisson(lin * full_well_e)); 4000 e- is a small phone
                   pixel at ISO-ish ~100-200 once exposure is normalised to 0.75 of full scale
    read_e         read noise, e- rms
    exposure       linear level the profile's bright background (98th percentile) is scaled to (camera auto-exposure)
    random_phase   the sampling grid is offset by U(0, 1) output pixels per profile (no free alignment luck)
    """
    psf_sigma_px: float = 0.75
    full_well_e: float = 4000.0
    read_e: float = 3.0
    exposure: float = 0.75
    random_phase: bool = True
    noise: bool = True


def normalise_exposure(lin: np.ndarray, target: float) -> np.ndarray:
    ref = np.percentile(lin, 98, axis=-1, keepdims=True)
    return np.clip(lin * (target / np.maximum(ref, 1e-3)), 0.0, 1.0)


def simulate_lowres(X: np.ndarray, ppm: float, model: SimModel = SimModel(), rng: np.random.Generator | None = None,
                    native_ppm: float = NATIVE_PX_PER_MM, margin_mm: float = 0.0) -> np.ndarray:
    """Degrade profiles ``X`` (n, W) sampled at ``native_ppm`` to ``ppm`` px/mm.  Returns float32 8-bit-valued (n, M).

    Order: sRGB -> linear, exposure normalisation, Gaussian PSF (sigma = psf_sigma_px output pixels, applied on the
    native grid), exact area integration over each output pixel (pitch p = native_ppm/ppm native pixels) via a
    cumulative sum at a random sub-pixel phase, Poisson shot noise + Gaussian read noise, sRGB encode, round to 8 bit.
    """
    if rng is None:
        rng = np.random.default_rng(0)
    X = np.asarray(X, np.float64)
    n, W = X.shape
    p = native_ppm / ppm
    lin = normalise_exposure(srgb_to_lin(X), model.exposure)
    sig = model.psf_sigma_px * p
    if sig > 0.05:
        r = int(math.ceil(4 * sig))
        xs = np.arange(-r, r + 1)
        ker = np.exp(-0.5 * (xs / sig) ** 2)
        ker /= ker.sum()
        lin = cv2.filter2D(lin.astype(np.float32), -1, ker.reshape(1, -1).astype(np.float32),
                           borderType=cv2.BORDER_REPLICATE).astype(np.float64)
    m = int(math.floor((W - p) / p))          # leave one pixel of slack for the random phase
    m -= (m + 1) % 2                          # odd count so there is a centre pixel
    cs = np.concatenate([np.zeros((n, 1)), np.cumsum(lin, axis=1)], axis=1)
    u = rng.random(n) if model.random_phase else np.full(n, 0.5)
    start = (W - m * p) / 2.0 + (u - 0.5) * p
    pos = start[:, None] + p * np.arange(m + 1)[None, :]
    i0 = np.clip(np.floor(pos).astype(int), 0, W - 1)
    fr = pos - i0
    rows = np.arange(n)[:, None]
    C = cs[rows, i0] * (1 - fr) + cs[rows, np.minimum(i0 + 1, W)] * fr
    out = (C[:, 1:] - C[:, :-1]) / p
    if model.noise:
        e = np.maximum(out, 0.0) * model.full_well_e
        e = rng.poisson(e).astype(np.float64) + rng.normal(0.0, model.read_e, e.shape)
        out = e / model.full_well_e
    return np.round(lin_to_srgb255(out)).astype(np.float32)


# ----------------------------------------------------------------------------- 1-D reduction of measure.py estimators

def _odd(n: float, lo: int = 3) -> int:
    n = max(int(round(n)), lo)
    return n if n % 2 else n + 1


def _blur1d(v: np.ndarray, sigma: float) -> np.ndarray:
    """Same as cv2.GaussianBlur(sigmaX=sigma) on an image of identical rows (BORDER_REFLECT_101 in x)."""
    a = np.tile(np.asarray(v, np.float32).reshape(1, -1), (5, 1))
    return cv2.GaussianBlur(a, (0, 0), sigmaX=float(sigma), sigmaY=0.0)[2].astype(np.float64)


def _runs(mask: np.ndarray):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1))


KEYS = ("dt", "fwhm", "core", "ink", "blend")


def profile_widths(P: np.ndarray, ppm: float, sigma_mm: float, ink_dark: float | None = None,
                   bg_mode: str = "local", band_mm: float = 0.2) -> dict:
    """Width (mm) of the crack crossing the middle of profile ``P`` (1-D, 8-bit-valued) by each ``measure.py`` estimator.

    Mirrors ``measure._measure_one`` for a straight crack: working resolution S (cubic resample, S = clip(ceil(ppm),
    12, 40); above 40 px/mm the profile is used as is), darkness D = background - linear intensity, half-peak mask ->
    run containing the seed -> ``2*DT - 1`` -> dt; then the sampled profile in +-R mm (R = max(1.2, dt/2 + 1)), area,
    Dcore, ink / core / FWHM widths and the blend.

    ``bg_mode``
      "global"  background = running max over 6 mm (what ``_measure_one`` does).  On a 2 mm krkCMd window this is the
                brightest pixel of the window, which is wrong when the concrete is heterogeneous (aggregates), so it
                over-reads massively.  Kept to document that limitation.
      "local"   background = straight line between the medians of the two outer ``band_mm`` of the window (the same
                two-band ramp ``_measure_one`` already uses for its profile integral), beyond the window = that ramp.
                This is the estimator-level benchmark used for the headline numbers.

    Returns a dict with keys ``dt, fwhm, core, ink, blend`` (mm; NaN when the real pipeline would return None) and ``S``.
    """
    nan = {k: float("nan") for k in KEYS}
    P = np.asarray(P, np.float32)
    S = float(ppm) if ppm > PIPELINE_MAX_S else float(np.clip(math.ceil(ppm), 12, PIPELINE_MAX_S))
    nan["S"] = S
    if abs(S - ppm) > 1e-9:
        Wn = int(round(len(P) * S / ppm))
        Pr = cv2.resize(P.reshape(1, -1), (Wn, 1), interpolation=cv2.INTER_CUBIC)[0]
        if ppm <= PIPELINE_MAX_S:  # the pipeline warps an 8-bit image
            Pr = np.clip(np.round(Pr), 0, 255)
    else:
        Pr = P
    lin = srgb_to_lin(Pr)
    W0 = len(lin)
    xs0 = np.arange(W0)
    if bg_mode == "local":
        bw = max(3, int(band_mm * S))
        bgL0, bgR0 = float(np.median(lin[:bw])), float(np.median(lin[-bw:]))
        xl, xr = (bw - 1) / 2.0, W0 - 1 - (bw - 1) / 2.0

        def bg_at(x):
            return np.interp(x, [xl, xr], [bgL0, bgR0])  # constant outside [xl, xr]
        D0 = bg_at(xs0) - lin
    else:
        bg_at = None
        D0 = lin.max() - lin
    # coarse seed (what the locator provides): centre of the strongest dark region within +-0.5 mm of the middle
    c0 = W0 // 2
    hw = int(0.5 * S)
    lo, hi = max(0, c0 - hw), min(W0, c0 + hw + 1)
    win = _blur1d(D0, 0.1 * S)[lo:hi]
    top = np.nonzero(win >= win.max() - 0.01 * max(win.max(), 1e-9))[0]
    seed = lo + int(np.median(top))
    if bg_mode == "local":
        D = D0
    else:
        # _measure_one works in an ROI = seed +- (corridor 3 mm + margin 1 mm), edge-replicated beyond the data, with
        # the paper level taken from measure._bg_map (6 mm running max, 1/4-res, smoothed)
        half = int(round(4.0 * S))
        roi = np.interp(seed + np.arange(-half, half + 1), xs0, lin)
        bgm = _measure._bg_map(np.tile(roi.astype(np.float32), (16, 1)), int(6.0 * S))[8].astype(np.float64)
        lin = roi
        D = bgm - roi
        seed = half
    W = len(lin)
    xs_all = np.arange(W)
    Dsm = _blur1d(D, 0.15 * S)
    kk = _odd(0.8 * S)
    h = kk // 2
    Dpk = float(Dsm[max(0, seed - h):seed + h + 1].max())
    if Dpk <= 0.06:
        return nan
    corr = np.abs(np.arange(W) - seed) <= 3.0 * S
    mask = (Dsm > 0.5 * Dpk) & corr
    runs = _runs(mask)
    if not runs:
        return nan
    hit = [r for r in runs if r[0] <= seed <= r[1]]
    a, b = hit[0] if hit else max(runs, key=lambda r: r[1] - r[0])
    nrun = b - a + 1
    w_dt_px = float(nrun if nrun % 2 else nrun - 1)  # 2*DT_max - 1 of a straight band of nrun pixels
    w_dt_mm = w_dt_px / S
    xsk = (a + b) // 2
    if w_dt_px < 1:
        return nan
    R = max(1.2, w_dt_mm / 2 + 1.0)
    nt = int(2 * R * S) | 1
    t = np.linspace(-R, R, nt) * S
    pos = xsk + t
    if bg_mode == "local":
        prof = np.interp(pos, xs_all, lin, left=float(bg_at(pos[0])), right=float(bg_at(pos[-1])))
        # outside the window the background itself is the signal: darkness 0 there
        outside = (pos < 0) | (pos > W - 1)
        prof = np.where(outside, bg_at(pos), prof)
        bgp = bg_at(pos)
    else:
        prof = np.interp(pos, xs_all, lin)  # linear interpolation, replicate border (cv2.remap equivalent)
        band = max(2, int(0.5 * S))
        bgL, bgR = np.median(prof[:band]), np.median(prof[-band:])
        ramp = np.linspace(0, 1, nt)
        bgp = bgL * (1 - ramp) + bgR * ramp
    Dp = bgp - prof
    area = Dp.sum() / S
    if bgp[nt // 2] <= 0.05:
        return nan
    Dsmooth = _blur1d(Dp, 0.12 * S)
    Dcore = float(Dsmooth.max())
    bgmed = float(bgp[nt // 2])
    Dink = (bgmed - ink_dark) if ink_dark is not None else Dcore
    Dink = max(Dink, 1e-3)
    w_core = area / max(Dcore, 1e-3)
    w_ink = area / (_measure.INK_RATIO * Dink)
    w_fwhm = float(_measure._fwhm(Dsmooth.reshape(1, -1), S)[0])
    out = {"dt": w_dt_mm, "core": float(w_core), "ink": float(w_ink), "fwhm": w_fwhm, "S": S}
    if not np.isfinite(w_fwhm):
        out["blend"] = float("nan")  # real pipeline returns None -> refusal
        return out
    d = w_ink / max(sigma_mm, 0.05)
    q = Dcore / Dink
    wt = float(np.clip((d - 5.0) / 6.0, 0.0, 1.0) * np.clip((q - 0.5) / 0.1, 0.0, 1.0))
    out["blend"] = float((1 - wt) * w_ink + wt * w_fwhm)
    return out


CAND_KEYS = ("area", "frac")


def candidate_widths(P: np.ndarray, ppm: float, sigma_mm: float, depth_frac: float = 0.5, margin_k: float = 2.0,
                     frac_level: float = 0.15, black: float = 0.0, band_mm: float = 0.2) -> dict:
    """Two scale-aware profile estimators that are NOT in measure.py (candidates; reported separately).

    ``area``  windowed area-conserving width.  Crack extent = region around the seed where the lightly smoothed
              darkness exceeds ``depth_frac`` of its peak, widened by ``margin_k`` blur sigmas (so the PSF wings are
              integrated), background = line through the medians of the 0.05 mm bands just outside that window,
              width = integral of (bg - I_lin) / (bg - black).  The window follows the crack, unlike measure.py's
              fixed +-1.2 mm window, so surface texture is not integrated.  ``black`` = linear level of an opaque
              crack interior (0.0, the scanner black point, the analogue of the board's printed black).
    ``frac``  sub-pixel width of the dark region at ``frac_level`` of the way from the profile minimum to the local
              background (encoded grey values), found by linear interpolation of the crossings.
    """
    P = np.asarray(P, np.float64)
    out = {k: float("nan") for k in CAND_KEYS}
    lin = srgb_to_lin(P)
    W = len(lin)
    xs = np.arange(W)
    bw = max(3, int(band_mm * ppm))
    bgl, bgr = np.median(lin[:bw]), np.median(lin[-bw:])
    bg = np.interp(xs, [bw / 2.0, W - bw / 2.0], [bgl, bgr])
    D = bg - lin
    Ds = _blur1d(D, max(0.8, 0.01 * ppm))
    c0 = W // 2
    hw = int(0.5 * ppm)
    lo, hi = max(0, c0 - hw), min(W, c0 + hw + 1)
    seed = lo + int(np.argmax(Ds[lo:hi]))
    pk = Ds[seed]
    if pk > 0.03:
        m = Ds > depth_frac * pk
        a = seed
        while a > 0 and m[a - 1]:
            a -= 1
        b = seed
        while b < W - 1 and m[b + 1]:
            b += 1
        mg = margin_k * sigma_mm * ppm
        A, B = int(max(0, math.floor(a - mg))), int(min(W - 1, math.ceil(b + mg)))
        bwid = max(3, int(0.05 * ppm))
        l0, r1 = max(0, A - bwid), min(W, B + 1 + bwid)
        if A - l0 >= 1 and r1 - (B + 1) >= 1:
            bgw = np.interp(xs, [(l0 + A) / 2.0, (B + r1) / 2.0], [np.median(lin[l0:A]), np.median(lin[B + 1:r1])])
        else:
            bgw = bg
        area = float((bgw[A:B + 1] - lin[A:B + 1]).sum()) / ppm
        C = float(np.median(bgw[A:B + 1])) - black
        if C > 1e-3:
            out["area"] = area / C
    # frac: encoded grey values
    sm = P
    bgE = 0.5 * (np.median(P[:bw]) + np.median(P[-bw:]))
    i0 = lo + int(np.argmin(_blur1d(P, max(0.5, 0.02 * ppm))[lo:hi]))
    mn = float(sm[max(0, i0 - 2):i0 + 3].min())
    lev = mn + frac_level * (bgE - mn)
    if bgE - mn > 10:
        a = i0
        while a > 0 and sm[a - 1] < lev:
            a -= 1
        b = i0
        while b < W - 1 and sm[b + 1] < lev:
            b += 1
        if a > 0 and b < W - 1:
            xa = (a - 1) + (lev - sm[a - 1]) / (sm[a] - sm[a - 1]) if sm[a] != sm[a - 1] else a - 0.5
            xb = (b + 1) - (lev - sm[b + 1]) / (sm[b] - sm[b + 1]) if sm[b] != sm[b + 1] else b + 0.5
            out["frac"] = max(xb - xa, 0.0) / ppm
    return out


# ----------------------------------------------------------------------------- adapter around the real measure._measure_one

def pipeline_width(P: np.ndarray, ppm: float, sigma_mm: float, ink_dark: float | None = None,
                   length_mm: float = 24.0, pad_mm: float = 5.0) -> dict:
    """Run the *unmodified* ``measure._measure_one`` on a straight synthetic crack built from profile ``P``.

    The profile (sampled at ``ppm``) is replicated down ``length_mm`` rows and padded with its edge values by
    ``pad_mm`` each side, identity-scaled homography (image px / ppm = board mm), and a vertical seed polyline through
    the dark region closest to the middle.  Returns the dict of ``_measure_one`` (or ``{}`` if it returns None).
    """
    P = np.asarray(P, np.float32)
    pad = int(round(pad_mm * ppm))
    rows = int(round(length_mm * ppm))
    line = np.pad(P, pad, mode="edge")
    grey = np.clip(np.round(np.tile(line, (rows, 1))), 0, 255).astype(np.uint8)
    D = srgb_to_lin(P)
    D = D.max() - D
    c0 = len(P) // 2
    hw = int(0.5 * ppm)
    lo, hi = max(0, c0 - hw), min(len(P), c0 + hw + 1)
    Ds = cv2.GaussianBlur(D.astype(np.float32).reshape(1, -1), (0, 0), 0.1 * ppm).ravel()[lo:hi]
    top = np.nonzero(Ds >= Ds.max() - 0.01 * max(Ds.max(), 1e-9))[0]
    xs = (pad + lo + float(np.median(top))) / ppm
    seed_b = np.array([[xs, 0.3 * length_mm], [xs, 0.7 * length_mm]])
    H = np.array([[1.0 / ppm, 0, 0], [0, 1.0 / ppm, 0], [0, 0, 1.0]])
    res = _measure._measure_one(grey, H, seed_b, float(ppm), ink_dark, float(sigma_mm))
    return res or {}


# ----------------------------------------------------------------------------- blur bookkeeping

def sigma_mm_total(psf_sigma_px: float, ppm: float, native_sigma_mm: float) -> float:
    """Total blur sigma (mm) the board-edge fit would report: PSF + pixel footprint (box, 1/sqrt(12) px) + the
    specimen/scanner edge softness already in the profiles (``native_sigma_mm``), added in quadrature."""
    return math.sqrt((psf_sigma_px ** 2 + 1.0 / 12.0) / ppm ** 2 + native_sigma_mm ** 2)


def native_edge_sigma_mm(p: Profiles, min_width_um: float = 150.0, n: int = 2000, seed: int = 0) -> float:
    """Median Gaussian-equivalent edge sigma (mm) of wide cracks: sigma = depth / (sqrt(2 pi) * max |gradient|)."""
    rng = np.random.default_rng(seed)
    idx = np.nonzero(p.man >= min_width_um)[0]
    idx = rng.choice(idx, size=min(n, len(idx)), replace=False)
    sig = []
    for i in idx:
        x = p.X[i].astype(np.float64)
        g = np.gradient(_blur1d(x, 2.0))
        depth = np.percentile(x, 90) - x.min()
        gm = np.abs(g).max()
        if gm > 0 and depth > 20:
            sig.append(depth / (math.sqrt(2 * math.pi) * gm))
    return float(np.median(sig)) * UM_PER_PX / 1000.0 if sig else 0.02


# ----------------------------------------------------------------------------- metrics

def _stats(err: np.ndarray, ref: np.ndarray, pred: np.ndarray) -> dict:
    ae = np.abs(err)
    pos = ref > 1e-9  # ratio / MRE are undefined for a zero reference (e.g. the native estimate of an unseen crack)
    if pos.any():
        ratio = pred[pos] / ref[pos]
        rm = float(ratio.mean())
        cov = float(ratio.std() / rm) if rm else float("nan")
        mre = float((ae[pos] / ref[pos]).mean())
    else:
        rm = cov = mre = float("nan")
    return dict(n=int(len(err)), bias=float(err.mean()), mae=float(ae.mean()), rmse=float(np.sqrt((err ** 2).mean())),
                p95=float(np.percentile(ae, 95)), ratio=rm, cov=cov, mre=mre)


def bin_metrics(pred_mm: np.ndarray, ref_mm: np.ndarray, lo: float, hi: float, idx: np.ndarray | None = None,
                bin_by: np.ndarray | None = None) -> dict:
    """Error statistics (mm) for references in [lo, hi), crack-present (ref > 0).  Failures (NaN) are excluded from the
    error statistics and reported as ``ok`` = fraction of profiles in the bin that produced a width.

    ``bin_by``: array used to assign profiles to bins instead of ``ref_mm`` (e.g. the operator width when ``ref_mm``
    is the same estimator's native-resolution output, for resolution-added error)."""
    key = ref_mm if bin_by is None else bin_by
    sel = (key >= max(lo, 1e-9)) & (key < hi)
    if idx is not None:
        sel &= idx
    nb = int(sel.sum())
    if nb == 0:
        return dict(n=0, ok=float("nan"))
    ok = sel & np.isfinite(pred_mm) & np.isfinite(ref_mm)
    if ok.sum() == 0:
        return dict(n=0, ok=0.0, n_bin=nb)
    s = _stats(pred_mm[ok] - ref_mm[ok], ref_mm[ok], pred_mm[ok])
    s["ok"] = float(ok.sum() / nb)
    s["n_bin"] = nb
    return s


def cluster_bootstrap(pred_mm, ref_mm, clusters, lo, hi, stat="mae", n_boot=300, seed=0, bin_by=None) -> tuple[float, float]:
    """95 % percentile bootstrap CI of ``stat`` ("mae", "bias" or "p95") over capture sessions (clusters), not over
    profiles (METRICS 0.4).  ``bin_by`` as in :func:`bin_metrics`."""
    key = ref_mm if bin_by is None else bin_by
    sel = (key >= max(lo, 1e-9)) & (key < hi) & np.isfinite(pred_mm) & np.isfinite(ref_mm)
    if sel.sum() < 5:
        return float("nan"), float("nan")
    err = (pred_mm - ref_mm)[sel]
    uniq, inv = np.unique(clusters[sel], return_inverse=True)
    k = len(uniq)
    cnt = np.bincount(inv, minlength=k).astype(float)
    sums = {"mae": np.bincount(inv, np.abs(err), k), "bias": np.bincount(inv, err, k)}
    members = [np.nonzero(inv == c)[0] for c in range(k)] if stat == "p95" else None
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        draw = rng.integers(0, k, k)
        if stat in sums:
            w = np.bincount(draw, minlength=k).astype(float)
            den = (w * cnt).sum()
            if den:
                vals.append((w * sums[stat]).sum() / den)
        else:
            ii = np.concatenate([members[c] for c in draw])
            vals.append(np.percentile(np.abs(err[ii]), 95))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def passes_target(s: dict, target: dict = TARGET) -> dict:
    """Which parts of the METRICS 1a 'Target' tier hold for a bin-stats dict (thin-crack row + overall row)."""
    if not s or s.get("n", 0) < 5:
        return dict(mae=False, p95=False, bias=False, ratio=False, cov=False, all=False)
    r = dict(mae=s["mae"] <= target["mae_mm"], p95=s["p95"] <= target["p95_mm"],
             bias=abs(s["bias"]) <= target["abs_bias_mm"], ratio=abs(s["ratio"] - 1) <= target["ratio_dev"],
             cov=s["cov"] <= target["cov"])
    r["all"] = all(r.values())
    return r


def gate_from_curve(ppm_list, ok_flags) -> float | None:
    """Lowest ppm such that it and *every higher* ppm in the sweep pass (a gate must be monotone to be a gate)."""
    pairs = sorted(zip(ppm_list, ok_flags))
    gate = None
    for ppm, ok in reversed(pairs):
        if ok:
            gate = ppm
        else:
            break
    return gate


# ----------------------------------------------------------------------------- sweep over resolutions

#: estimator column names: loc_* = measure.py arithmetic with local background (headline), glob_* = as-is background
#: (running max, faithful to _measure_one), cand_* = scale-aware candidates not in measure.py
def estimator_names(include_global: bool = True) -> list[str]:
    names = [f"loc_{k}" for k in KEYS]
    if include_global:
        names += [f"glob_{k}" for k in KEYS]
    return names + [f"cand_{k}" for k in CAND_KEYS]


def _predict_chunk(args):
    X, ppm, psf_sigma_px, native_sigma_mm, include_global, ink_dark, seed, model = args
    native = ppm is None
    if native:  # same exposure normalisation as the degraded versions; no PSF, no noise, no resampling
        Y = lin_to_srgb255(normalise_exposure(srgb_to_lin(X), model.exposure)).astype(np.float32)
        use_ppm = NATIVE_PX_PER_MM
        sm = native_sigma_mm
    else:
        Y = simulate_lowres(X, ppm, model, np.random.default_rng(seed))
        use_ppm = ppm
        sm = sigma_mm_total(model.psf_sigma_px, ppm, native_sigma_mm)
    names = estimator_names(include_global)
    out = {k: np.full(len(Y), np.nan) for k in names}
    for i, y in enumerate(Y):
        r = profile_widths(y, use_ppm, sm, ink_dark=ink_dark, bg_mode="local")
        for k in KEYS:
            out[f"loc_{k}"][i] = r[k]
        if include_global:
            r = profile_widths(y, use_ppm, sm, ink_dark=ink_dark, bg_mode="global")
            for k in KEYS:
                out[f"glob_{k}"][i] = r[k]
        c = candidate_widths(y, use_ppm, sm)
        for k in CAND_KEYS:
            out[f"cand_{k}"][i] = c[k]
    return out


def predict_all(X: np.ndarray, ppm: float | None, native_sigma_mm: float, model: SimModel = SimModel(),
                include_global: bool = True, ink_dark: float | None = 0.0, seed: int = 0, workers: int = 1,
                chunk: int = 500) -> dict:
    """Widths (mm) from every estimator for every profile at ``ppm`` (``None`` = native 252 px/mm, no degradation).

    Deterministic for a given ``seed`` regardless of ``workers`` (each chunk has its own seeded generator).
    ``ink_dark`` is the linear level of the board's printed black (the reference for the ink estimator); 0.0 = the
    scanner black point, since the cracks' dark cores saturate at grey 0 in the scans.
    """
    chunks = [(X[i:i + chunk], ppm, model.psf_sigma_px, native_sigma_mm, include_global, ink_dark,
               (seed * 1_000_003 + int((ppm or 0) * 100) * 7919 + i), model) for i in range(0, len(X), chunk)]
    if workers > 1 and len(chunks) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(_predict_chunk, chunks))
    else:
        parts = [_predict_chunk(c) for c in chunks]
    return {k: np.concatenate([p_[k] for p_ in parts]) for k in parts[0]}


def fit_linear(pred: np.ndarray, ref: np.ndarray, sel: np.ndarray) -> tuple[float, float]:
    """Least-squares ref = a * pred + b on the selected finite profiles (the calibration a panel would give)."""
    ok = sel & np.isfinite(pred)
    A = np.vstack([pred[ok], np.ones(ok.sum())]).T
    a, b = np.linalg.lstsq(A, ref[ok], rcond=None)[0]
    return float(a), float(b)
