"""The COOL-loop fast paths of prohori.measure must reproduce the code they replaced bit for bit.

The reference implementations below are the ones of commit 1c1ac4f (before the loop); the fast versions are checked against
them on random inputs, so a future edit cannot silently change a width."""
import os
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import pytest

from prohori import measure

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "service" / "static" / "samples"


# ----------------------------------------------------------------------------- reference implementations (1c1ac4f)

def ref_longest_path(sk):
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


def ref_fwhm(Dp, S, frac=0.5):
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
        half = frac * pk
        a = k
        while a > 0 and p[a] > half:
            a -= 1
        b = k
        while b < nt - 1 and p[b] > half:
            b += 1
        if p[a] > half or p[b] > half:
            continue
        xl = a + (half - p[a]) / (p[a + 1] - p[a]) if p[a + 1] != p[a] else a
        xr = b - 1 + (p[b - 1] - half) / (p[b - 1] - p[b]) if p[b - 1] != p[b] else b
        out[i] = (xr - xl) / S
    return out


def ref_match_once(comps, dense, tol_mm, min_frac):
    assigned = {}
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


def random_mask(rng, h, w):
    m = np.zeros((h, w), np.uint8)
    for _ in range(int(rng.integers(1, 4))):
        pts = np.cumsum(rng.normal(0, 6, (20, 2)), 0) + [w / 2, h / 2]
        cv2.polylines(m, [pts.astype(np.int32).reshape(-1, 1, 2)], False, 255, int(rng.integers(1, 12)))
    return m


# ----------------------------------------------------------------------------- tests

@pytest.mark.skipif(not hasattr(cv2, "ximgproc"), reason="needs opencv-contrib for the native reference")
def test_thin_is_bit_exact_with_ximgproc():
    rng = np.random.default_rng(3)
    for k in range(120):
        h, w = int(rng.integers(3, 160)), int(rng.integers(3, 260))
        m = random_mask(rng, h, w)
        if k % 3 == 0:
            m |= (rng.random((h, w)) < 0.3).astype(np.uint8) * 255
        if k % 5 == 0:
            m[0, :] = 255
            m[:, -1] = 255
        if k % 7 == 0:
            m = (rng.random((h, w)) < 0.7).astype(np.uint8) * 255
        assert np.array_equal(cv2.ximgproc.thinning(m), measure._thin(m)), k


def test_thin_leaves_a_one_pixel_skeleton_and_the_border():
    m = np.zeros((40, 120), np.uint8)
    cv2.line(m, (5, 20), (110, 22), 255, 7)
    m[:, 0] = 255
    sk = measure._thin(m)
    assert sk[:, 0].all()  # border pixels never change
    inner = sk[1:-1, 1:-1] > 0
    assert 90 < inner.sum() < 130  # a centreline of the 105 px stroke, not the stroke
    assert measure._thin(np.zeros((2, 9), np.uint8)).sum() == 0


def test_cc_stats_equals_default_labelling():
    rng = np.random.default_rng(4)
    for _ in range(10):
        m = random_mask(rng, 150, 220)
        m |= (rng.random(m.shape) < 0.05).astype(np.uint8) * 255
        a = cv2.connectedComponentsWithStats(m, connectivity=8)
        b = measure._cc_stats(m)
        for x, y in zip(a, b):
            assert np.array_equal(x, y) if isinstance(x, np.ndarray) else x == y


def test_longest_path_equals_reference():
    rng = np.random.default_rng(5)
    for _ in range(40):
        sk = measure._thin(random_mask(rng, int(rng.integers(20, 120)), int(rng.integers(20, 200)))) > 0
        assert np.array_equal(ref_longest_path(sk), measure._longest_path(sk))
    one = np.zeros((5, 5), bool)
    one[2, 3] = True
    assert np.array_equal(measure._longest_path(one), [[3.0, 2.0]])
    assert measure._longest_path(np.zeros((5, 5), bool)).shape == (0, 2)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("frac", [0.5, 0.85])
def test_fwhm_equals_reference(dtype, frac):
    rng = np.random.default_rng(6)
    for t in range(60):
        n, nt = int(rng.integers(1, 50)), int(rng.integers(5, 120)) | 1
        x = np.arange(nt) - nt // 2
        P = (rng.uniform(-0.1, 1, (n, 1)) * np.exp(-0.5 * ((x[None] - rng.normal(0, 2, (n, 1))) / rng.uniform(1, 12, (n, 1))) ** 2)
             + rng.normal(0, rng.choice([0, 0.01, 0.1]), (n, nt)))
        if t % 7 == 0:
            P = np.round(P * 20) / 20
        P = P.astype(dtype)
        S = float(rng.uniform(4, 40))
        assert np.array_equal(ref_fwhm(P, S, frac), measure._fwhm(P, S, frac), equal_nan=True)


def test_match_once_equals_reference():
    rng = np.random.default_rng(7)
    dense = [np.stack([np.linspace(10, 180, 400), 20 + 25 * j + 4 * np.sin(np.linspace(0, 6, 400) + j)], 1) for j in range(8)]
    for _ in range(25):
        comps = []
        for _ in range(int(rng.integers(1, 10))):
            j = int(rng.integers(0, 8))
            n = int(rng.integers(8, 300))
            xs = np.sort(rng.uniform(10, 180, n))
            comps.append({"path_b": np.stack([xs, 20 + 25 * j + 4 * np.sin(xs / 28) + rng.normal(0, rng.choice([0.2, 3, 12]), n)], 1)})
        for tol, mf in ((6.0, 0.5), (4.0, 0.6)):
            a, b = ref_match_once(comps, dense, tol, mf), measure._match_once(comps, dense, tol, mf)
            assert a.keys() == b.keys()
            assert all([id(c) for c in a[k]] == [id(c) for c in b[k]] for k in a)


def test_median_u8_equals_numpy_median():
    rng = np.random.default_rng(8)
    lut = measure._lin_lut()
    for n in (1, 2, 3, 10, 11, 5000, 5001):
        img = rng.integers(0, 256, (1, n), dtype=np.uint8)
        mask = rng.random(img.shape) < 0.7
        mask[0, 0] = True
        assert measure._median_u8(img, mask) == float(np.median(img[mask]))
        assert measure._median_u8(img, mask, lut) == float(np.median(lut[img][mask]))
        assert measure._median_u8(img) == float(np.median(img))
    assert measure._median_u8(np.zeros((3, 3), np.uint8), np.zeros((3, 3), bool)) is None


def test_warp_valid_equals_the_nearest_warp():
    h, w = 300, 400
    src = np.zeros((h, w), np.uint8)
    cases = ((np.array([[1.0, 0, 50], [0, 1.0, 40], [0, 0, 1]]), (200, 150)),     # fully inside: shortcut
             (np.array([[1.0, 0, 250], [0, 1.0, 40], [0, 0, 1]]), (200, 150)),    # crosses the edge: real warp
             (np.array([[0.9, 0.2, 30], [-0.1, 1.1, 20], [1e-4, 2e-4, 1]]), (250, 200)))
    for Hm, size in cases:
        for erode in (0, 5):
            ref = cv2.warpPerspective(np.full((h, w), 255, np.uint8), Hm, size, flags=cv2.INTER_NEAREST)
            if erode:
                ref = cv2.erode(ref, np.ones((erode, erode), np.uint8))
            assert np.array_equal(measure._warp_valid(src.shape, Hm, size, erode), ref > 0)


def test_thread_count_does_not_change_the_result():
    img = cv2.imread(str(SAMPLES / "good-straight.jpg"))
    assert img is not None
    old = os.environ.get("PROHORI_THREADS")
    try:
        os.environ["PROHORI_THREADS"] = "1"
        a = measure.analyze(img)
        os.environ["PROHORI_THREADS"] = "4"
        b = measure.analyze(img)
    finally:
        if old is None:
            os.environ.pop("PROHORI_THREADS", None)
        else:
            os.environ["PROHORI_THREADS"] = old
    for r in (a, b):
        r.pop("timing_ms")
    assert a == b


def test_shared_ones_image_is_reused():
    a = measure._ones255((10, 20))
    assert a is measure._ones255((10, 20)) and a.shape == (10, 20) and (a == 255).all()
    assert measure._ones255((11, 20)).shape == (11, 20)
