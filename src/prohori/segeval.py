"""Segmentation evaluation for crack masks (METRICS.md section 4b) and the classical-locator wrapper.

Metrics (all reported for the CRACK class, never a 2-class mean; METRICS section 0 rule 3):

* pooled P / R / F1 / crack-IoU from summed TP/FP/FN (S1, S2, S7).  IoU = F1 / (2 - F1) exactly.
* ODS / OIS over a threshold sweep (S1, Eqs. 17-18):
    ODS = F1 of the dataset-pooled P/R at the single best threshold,
    OIS = mean over images of the per-image best-threshold F1 (images with an empty ground truth are skipped).
* clIoU_rho (S10, OmniCrack30k): centreline IoU with positional tolerance radius rho (px).
    S_T, S_P = skeletons of ground truth / prediction, K_rho = disk of radius rho,
    TP_cl = S_T & dilate(S_P, K_rho)      (ground-truth centreline pixels the prediction reaches)
    FN_cl = S_T & ~dilate(S_P, K_rho)
    FP_cl = S_P & ~dilate(S_T, K_rho)     (predicted centreline pixels with no ground truth nearby)
    clIoU = TP_cl / (TP_cl + FP_cl + FN_cl).  Reported at rho = 0, 1, 2, 4 px.
* centreline recall @ rho = TP_cl / |S_T|  (METRICS 4b "Centreline recall @ 2 px").

Skeletons use ``cv2.ximgproc.thinning`` (Zhang-Suen), the same thinning as ``measure.py``.

The module also wraps the classical locator of ``measure.py`` (CLAHE-free background-normalised darkness threshold ->
close -> connected components filtered by length) as :class:`ClassicalLocator`, a function from an arbitrary image to
a crack mask.  ``measure.py`` is NOT modified or required: the locator is re-implemented here (see the class docstring
for the exact differences) and :func:`measure_locator_mask` calls the real ``measure._locate_cracks`` so the two can be
cross-checked (tests/test_segeval.py does this).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import cv2
import numpy as np

# ----------------------------------------------------------------------------- basic counts


def _b(m: np.ndarray) -> np.ndarray:
    return np.asarray(m).astype(bool)


def confusion(pred: np.ndarray, gt: np.ndarray) -> tuple[int, int, int, int]:
    """(tp, fp, fn, tn) pixel counts of two boolean masks."""
    p, g = _b(pred), _b(gt)
    tp = int((p & g).sum())
    fp = int((p & ~g).sum())
    fn = int((~p & g).sum())
    tn = int(p.size - tp - fp - fn)
    return tp, fp, fn, tn


def prf_iou(tp: float, fp: float, fn: float) -> dict:
    """Precision, recall, F1 and crack-class IoU from counts (0 where undefined)."""
    p = tp / (tp + fp) if tp + fp > 0 else 0.0
    r = tp / (tp + fn) if tp + fn > 0 else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn > 0 else 0.0
    iou = tp / (tp + fp + fn) if tp + fp + fn > 0 else 0.0
    return {"precision": p, "recall": r, "f1": f1, "iou": iou}


def iou_from_f1(f1: float) -> float:
    """Crack-class IoU from F1: IoU = F1 / (2 - F1) (METRICS section 0, rule 3)."""
    return f1 / (2.0 - f1) if f1 < 2.0 else 0.0


# ----------------------------------------------------------------------------- centreline metrics


def skeleton(mask: np.ndarray) -> np.ndarray:
    """Boolean skeleton (Zhang-Suen thinning) of a boolean mask."""
    m = _b(mask).astype(np.uint8) * 255
    if not m.any():
        return np.zeros(m.shape, bool)
    return cv2.ximgproc.thinning(m, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN) > 0


def _disk(rho: int) -> np.ndarray | None:
    if rho <= 0:
        return None
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rho + 1, 2 * rho + 1))


def _dilate(m: np.ndarray, rho: int) -> np.ndarray:
    k = _disk(rho)
    if k is None:
        return m
    return cv2.dilate(m.astype(np.uint8), k) > 0


def cl_counts(skel_pred: np.ndarray, skel_gt: np.ndarray, rho: int) -> tuple[int, int, int]:
    """(TP_cl, FP_cl, FN_cl) of two skeletons at tolerance radius rho (see module docstring)."""
    sp, st = _b(skel_pred), _b(skel_gt)
    dp, dt = _dilate(sp, rho), _dilate(st, rho)
    tp = int((st & dp).sum())
    fn = int((st & ~dp).sum())
    fp = int((sp & ~dt).sum())
    return tp, fp, fn


def cl_iou(pred: np.ndarray, gt: np.ndarray, rho: int = 0) -> float:
    """Centreline IoU clIoU_rho of two masks (nan if both skeletons are empty)."""
    tp, fp, fn = cl_counts(skeleton(pred), skeleton(gt), rho)
    return tp / (tp + fp + fn) if tp + fp + fn > 0 else float("nan")


# ----------------------------------------------------------------------------- accumulation over a dataset


@dataclass
class _Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, tp, fp, fn):
        self.tp += tp
        self.fp += fp
        self.fn += fn

    def metrics(self) -> dict:
        return prf_iou(self.tp, self.fp, self.fn)


@dataclass
class SweepAccumulator:
    """Accumulates pooled and per-image statistics for a list of operating points (thresholds).

    ``add(gt, preds)`` takes the ground-truth mask and one predicted mask per threshold.  Everything needed for
    P/R/F1/IoU, ODS, OIS, clIoU_rho and centreline recall at every threshold is kept; only counters, no images.
    """
    thresholds: Sequence[float]
    rhos: Sequence[int] = (0, 1, 2, 4)
    n_images: int = 0
    n_with_crack: int = 0
    pix: list = field(default_factory=list)          # per threshold _Counts (pixel)
    cl: list = field(default_factory=list)           # per threshold {rho: _Counts}
    st_total: list = field(default_factory=list)     # per threshold: |S_T| pooled (for recall)
    img_f1: list = field(default_factory=list)       # per image: array over thresholds (nan if gt empty)
    img_cl: list = field(default_factory=list)       # per image: array [thr, rho] (nan if both empty)

    def __post_init__(self):
        nt = len(self.thresholds)
        self.pix = [_Counts() for _ in range(nt)]
        self.cl = [{r: _Counts() for r in self.rhos} for _ in range(nt)]
        self.st_total = [0] * nt

    def add(self, gt: np.ndarray, preds: Sequence[np.ndarray]) -> None:
        g = _b(gt)
        assert len(preds) == len(self.thresholds)
        self.n_images += 1
        has = bool(g.any())
        self.n_with_crack += int(has)
        st = skeleton(g)
        f1s = np.full(len(preds), np.nan)
        cls = np.full((len(preds), len(self.rhos)), np.nan)
        for i, p in enumerate(preds):
            p = _b(p)
            tp, fp, fn, _ = confusion(p, g)
            self.pix[i].add(tp, fp, fn)
            if has:
                f1s[i] = prf_iou(tp, fp, fn)["f1"]
            sp = skeleton(p)
            for j, r in enumerate(self.rhos):
                ctp, cfp, cfn = cl_counts(sp, st, r)
                self.cl[i][r].add(ctp, cfp, cfn)
                if ctp + cfp + cfn > 0:
                    cls[i, j] = ctp / (ctp + cfp + cfn)
            self.st_total[i] += int(st.sum())
        self.img_f1.append(f1s)
        self.img_cl.append(cls)

    def merge(self, other: "SweepAccumulator") -> "SweepAccumulator":
        """Add another accumulator over the same thresholds/rhos (for multiprocessing)."""
        assert list(self.thresholds) == list(other.thresholds) and list(self.rhos) == list(other.rhos)
        self.n_images += other.n_images
        self.n_with_crack += other.n_with_crack
        for i in range(len(self.thresholds)):
            self.pix[i].add(other.pix[i].tp, other.pix[i].fp, other.pix[i].fn)
            for r in self.rhos:
                c = other.cl[i][r]
                self.cl[i][r].add(c.tp, c.fp, c.fn)
            self.st_total[i] += other.st_total[i]
        self.img_f1 += other.img_f1
        self.img_cl += other.img_cl
        return self

    # ------------------------------------------------------------- summaries
    def at(self, i: int) -> dict:
        """All metrics at threshold index i."""
        m = self.pix[i].metrics()
        out = {"threshold": float(self.thresholds[i]), **m}
        for j, r in enumerate(self.rhos):
            c = self.cl[i][r]
            out[f"clIoU_{r}px"] = c.tp / (c.tp + c.fp + c.fn) if c.tp + c.fp + c.fn else float("nan")
            arr = np.array([a[i, j] for a in self.img_cl])
            out[f"clIoU_{r}px_mean_img"] = float(np.nanmean(arr)) if np.isfinite(arr).any() else float("nan")
            out[f"cl_recall_{r}px"] = c.tp / self.st_total[i] if self.st_total[i] else float("nan")
        return out

    def ods_index(self) -> int:
        return int(np.argmax([c.metrics()["f1"] for c in self.pix]))

    def ods(self) -> float:
        return self.pix[self.ods_index()].metrics()["f1"]

    def ois(self) -> float:
        if not self.img_f1:
            return float("nan")
        a = np.array(self.img_f1)                       # images x thresholds
        a = a[np.isfinite(a).any(axis=1)]
        return float(np.nanmax(a, axis=1).mean()) if len(a) else float("nan")

    def summary(self, default_index: int | None = None) -> dict:
        """Dataset summary: operating point (default threshold), ODS point, ODS/OIS scalars."""
        k = self.ods_index()
        out = {"n_images": self.n_images, "n_images_with_crack": self.n_with_crack,
               "ODS": self.ods(), "ODS_threshold": float(self.thresholds[k]), "OIS": self.ois(),
               "ODS_iou": iou_from_f1(self.ods())}
        out["at_ods"] = self.at(k)
        if default_index is not None:
            out["at_default"] = self.at(default_index)
        return out


def sweep_from_scores(score: np.ndarray, thresholds: Sequence[float]) -> list[np.ndarray]:
    """Binary masks ``score >= t`` for each threshold (use for continuous crack-probability maps)."""
    return [score >= t for t in thresholds]


def evaluate(samples: Iterable, predict_sweep: Callable[[np.ndarray], Sequence[np.ndarray]],
             thresholds: Sequence[float], rhos: Sequence[int] = (0, 1, 2, 4),
             default_index: int | None = None, progress: Callable[[int], None] | None = None) -> dict:
    """Run ``predict_sweep(image_bgr) -> [mask per threshold]`` over ``samples`` (``datasets.Sample``) and summarise."""
    acc = SweepAccumulator(thresholds, rhos)
    for k, s in enumerate(samples):
        acc.add(s.mask, predict_sweep(s.image))
        if progress and (k + 1) % 50 == 0:
            progress(k + 1)
    return acc.summary(default_index)


# ----------------------------------------------------------------------------- classical locator wrapper

# Constants copied from measure._locate_cracks (kept in sync by tests/test_segeval.py).
LOC_BLUR_SIGMA = 0.7
LOC_BG_WIN_MM = 8.0
LOC_DARK_THRESH = 0.12
LOC_CLOSE_MM = 0.5
LOC_MIN_LEN_MM = 12.0
LOC_MAX_MEAN_W_MM = 6.0       # generic (non-panel) mode keeps components with mean width <= 6 mm
LOC_MAX_COMPONENTS = 8        # generic mode measures the 8 longest components


def _odd(n: float, lo: int = 3) -> int:
    n = int(round(n))
    n = max(n, lo)
    return n if n % 2 else n + 1


def _bg_map(lin: np.ndarray, win_px: int) -> np.ndarray:
    """Paper/background-level map: running max over ~win_px then smoothed, computed at 1/4 resolution.
    Identical to ``measure._bg_map``."""
    h, w = lin.shape
    q = 4
    sm = cv2.resize(lin, (max(1, w // q), max(1, h // q)), interpolation=cv2.INTER_AREA)
    k = _odd(win_px / q)
    sm = cv2.dilate(sm, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    sm = cv2.GaussianBlur(sm, (0, 0), k / 3.0)
    return cv2.resize(sm, (w, h), interpolation=cv2.INTER_LINEAR)


def _longest_path_length(sk: np.ndarray) -> tuple[int, float]:
    """(number of nodes, Euclidean length in px) of the longest geodesic of a thin mask (double-sweep BFS, as
    ``measure._longest_path``; ties may be broken differently)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import breadth_first_order
    ys, xs = np.nonzero(sk)
    n = len(ys)
    if n == 0:
        return 0, 0.0
    if n == 1:
        return 1, 0.0
    idx = -np.ones(sk.shape, np.int64)
    idx[ys, xs] = np.arange(n)
    rows, cols = [], []
    hh, ww = sk.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            y2, x2 = ys + dy, xs + dx
            m = (y2 >= 0) & (y2 < hh) & (x2 >= 0) & (x2 < ww)
            j = np.full(n, -1, np.int64)
            j[m] = idx[y2[m], x2[m]]
            ok = j >= 0
            rows.append(np.nonzero(ok)[0])
            cols.append(j[ok])
    r, c = np.concatenate(rows), np.concatenate(cols)
    A = coo_matrix((np.ones(len(r), np.int8), (r, c)), shape=(n, n)).tocsr()
    order, _ = breadth_first_order(A, 0, directed=False, return_predecessors=True)
    a = int(order[-1])
    order, pred = breadth_first_order(A, a, directed=False, return_predecessors=True)
    b = int(order[-1])
    path = [b]
    while pred[path[-1]] >= 0:
        path.append(int(pred[path[-1]]))
    pts = np.stack([xs[path], ys[path]], 1).astype(float)
    length = float(np.hypot(*np.diff(pts, axis=0).T).sum()) if len(pts) > 1 else 0.0
    return len(path), length


class ClassicalLocator:
    """Pixel-domain re-implementation of ``measure._locate_cracks`` for images without a ChArUco board.

    ``measure.py`` rectifies the page to a canvas of S_loc px/mm (3..8 px/mm) and works in millimetres.  A dataset
    image has no board and thus no scale, so the same operations are applied in pixels with a *nominal* ``px_per_mm``
    (default 5.0, the middle of measure's 3..8 range); all mm-valued constants are converted with it:

      1. grey = GaussianBlur(0.7 px)
      2. bg   = running-max background map over int(8 mm * S)         (identical ``_bg_map``)
      3. dark = (bg - grey) / max(bg, 1);  mask = dark > t           (t = 0.12 in measure.py; swept here)
      4. close with an elliptical kernel of odd(0.5 mm * S)
      5. 8-connected components; keep those with bbox diagonal >= 12 mm * S, a thinned longest path of >= 3 nodes and
         path length >= 12 mm; mean width (area / path length) <= 6 mm (generic mode); keep the 8 longest.

    Differences to measure.py (all documented, none changes the algorithm):
      * measure works on a perspective-rectified canvas with a validity mask and excludes the board rectangle; here the
        whole image is valid and there is no board;
      * the longest path is found with scipy's BFS instead of measure's Python BFS (equal up to tie-breaking);
      * measure feeds the surviving seed polylines into a second, full-resolution stage (corridor half-max mask,
        thinning, sub-pixel profile).  That stage measures width, it does not change which pixels are "located",
        so the located component mask is what is scored here.
    ``peak_mask`` (optional) returns the raw threshold mask without the component filters (ablation).
    """

    def __init__(self, px_per_mm: float = 5.0, thresholds: Sequence[float] = (0.12,), max_side: int | None = None):
        self.S = float(px_per_mm)
        self.thresholds = tuple(thresholds)
        self.max_side = max_side

    # darkness map shared across thresholds
    def darkness(self, img_bgr: np.ndarray) -> np.ndarray:
        grey = img_bgr if img_bgr.ndim == 2 else cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(grey, (0, 0), LOC_BLUR_SIGMA)
        gf = g.astype(np.float32)
        bg = _bg_map(gf, int(LOC_BG_WIN_MM * self.S))
        return (bg - gf) / np.maximum(bg, 1.0)

    def components(self, dark: np.ndarray, thr: float,
                   max_mean_w_mm: float | None = LOC_MAX_MEAN_W_MM) -> tuple[np.ndarray, list[dict]]:
        S = self.S
        m = (dark > thr).astype(np.uint8) * 255
        kc = _odd(LOC_CLOSE_MM * S)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc)))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        comps = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if math.hypot(w, h) < LOC_MIN_LEN_MM * S:
                continue
            crop = (lab[y:y + h, x:x + w] == i).astype(np.uint8) * 255
            pad = cv2.copyMakeBorder(crop, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
            sk = cv2.ximgproc.thinning(pad) > 0
            # Exact shortcut: the longest path has <= (skeleton pixels) nodes, so area/n_sk is a lower bound of the
            # mean width measure.py computes; a component already wider than the limit would be dropped anyway.
            if max_mean_w_mm is not None and area / max(int(sk.sum()), 1) / S > max_mean_w_mm:
                continue
            n_nodes, length_px = _longest_path_length(sk)
            if n_nodes < 3:
                continue
            length_mm = length_px / S
            if length_mm < LOC_MIN_LEN_MM:
                continue
            comps.append({"label": i, "length_mm": length_mm, "mean_w_mm": area / max(n_nodes, 1) / S,
                          "area": int(area)})
        return lab, comps

    def _select(self, comps, max_components, max_mean_w_mm):
        if max_mean_w_mm is not None:
            comps = [c for c in comps if c["mean_w_mm"] <= max_mean_w_mm]
        if max_components is not None:
            comps = sorted(comps, key=lambda c: -c["length_mm"])[:max_components]
        return comps

    def masks_from(self, dark: np.ndarray, lab: np.ndarray, comps: list, refine: bool = False,
                   max_components: int | None = LOC_MAX_COMPONENTS,
                   max_mean_w_mm: float | None = LOC_MAX_MEAN_W_MM) -> np.ndarray:
        comps = self._select(comps, max_components, max_mean_w_mm)
        if not comps:
            return np.zeros(dark.shape, bool)
        if not refine:
            return np.isin(lab, [c["label"] for c in comps])
        out = np.zeros(dark.shape, bool)
        for c in comps:
            reg = lab == c["label"]
            pk = float(np.percentile(dark[reg], 90))
            out |= reg & (dark >= 0.5 * pk)
        return out

    def mask_at(self, dark: np.ndarray, thr: float, max_components: int | None = LOC_MAX_COMPONENTS,
                max_mean_w_mm: float | None = LOC_MAX_MEAN_W_MM, refine: bool = False) -> np.ndarray:
        """Located-component mask.  ``refine=True`` additionally keeps, inside each located component, only pixels
        darker than half of that component's 90th-percentile darkness (a pixel-domain stand-in for the half-maximum
        mask that measure.py's second stage thresholds inside the corridor); it is reported as a separate variant."""
        lab, comps = self.components(dark, thr, max_mean_w_mm)
        return self.masks_from(dark, lab, comps, refine, max_components, max_mean_w_mm)

    def peak_mask(self, dark: np.ndarray, thr: float) -> np.ndarray:
        """Raw threshold + close mask without component filters (ablation: 'no length/width filter')."""
        kc = _odd(LOC_CLOSE_MM * self.S)
        m = (dark > thr).astype(np.uint8) * 255
        return cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc))) > 0

    def sweep(self, img_bgr: np.ndarray, variant: str = "locator") -> list[np.ndarray]:
        """One mask per threshold.  variant: 'locator' (components as measure.py), 'refined' (+ half-max inside the
        component), 'raw' (threshold + close only, no component filters)."""
        dark = self.darkness(img_bgr)
        if variant == "raw":
            return [self.peak_mask(dark, t) for t in self.thresholds]
        return [self.mask_at(dark, t, refine=(variant == "refined")) for t in self.thresholds]

    def sweep_variants(self, img_bgr: np.ndarray, variants=("locator", "refined", "raw")) -> dict[str, list[np.ndarray]]:
        """Masks for several variants over all thresholds, sharing the darkness map and connected components."""
        dark = self.darkness(img_bgr)
        out = {v: [] for v in variants}
        for t in self.thresholds:
            if "raw" in variants:
                out["raw"].append(self.peak_mask(dark, t))
            if "locator" in variants or "refined" in variants:
                lab, comps = self.components(dark, t)
                for v in ("locator", "refined"):
                    if v in variants:
                        out[v].append(self.masks_from(dark, lab, comps, refine=(v == "refined")))
        return out

    def __call__(self, img_bgr: np.ndarray, thr: float = LOC_DARK_THRESH) -> np.ndarray:
        """Crack mask (bool, same size as the image) at one threshold."""
        return self.mask_at(self.darkness(img_bgr), thr)


def measure_locator_mask(img_bgr: np.ndarray, px_per_mm: float = 5.0) -> np.ndarray:
    """Mask produced by the REAL ``measure._locate_cracks`` (generic-mode filters) for cross-checking.

    Imports ``prohori.measure`` read-only; the whole image is treated as a valid canvas at ``px_per_mm``."""
    from prohori import measure as M
    grey = img_bgr if img_bgr.ndim == 2 else cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    valid = np.ones(grey.shape, bool)
    comps, lab = M._locate_cracks(grey, valid, float(px_per_mm), np.zeros(2), False, None)
    keep = [c for c in comps if c["mean_w_mm"] <= 6.0]
    keep = sorted(keep, key=lambda c: -c["length_mm"])[:8]
    if not keep:
        return np.zeros(grey.shape, bool)
    return np.isin(lab, [c["label"] for c in keep])
