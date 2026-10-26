"""Rectified crack crop + grey-level width profile figure for the demo video (script row 2).

Runs the shipped OpenCV pipeline (src/prohori/measure.py) locally on a bundled sample photo, takes the
rectified region of interest of one crack (scale known in px/mm from the board), samples the grey levels
across the crack, and draws: the rectified crop with the sampling lines, and the mean cross profile with the
half-depth width. Output: docs/video/assets/charts/rectified_profile.png (1920x1080).

Usage: python tools/video_rectify.py [sample-id]   (default good-straight)
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import map_coordinates

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import video_common as vc  # noqa: E402
from prohori import measure  # noqa: E402

ROOT = vc.ROOT


def main(sample: str = "good-straight", want_width: float = 1.0):
    fonts = vc.setup_matplotlib()
    from matplotlib import font_manager as fm
    import matplotlib.pyplot as plt

    def fp(k, size):
        return fm.FontProperties(fname=str(fonts[k]), size=size * 0.72)

    img = cv2.imread(str(ROOT / "service" / "static" / "samples" / f"{sample}.jpg"))
    res = measure.analyze(img, panel_mode=False)
    cracks = [c for c in res["cracks"] if c.get("certified")]
    c = min(cracks, key=lambda c: abs(c["width_mm"] - want_width))
    res2 = measure._empty_result()
    ctx = measure._prepare(img, False, res2)
    it = next(i for i in ctx["items"] if i["sd"]["id"] == c["id"])
    rp = it["rp"]
    roi, lo, S = rp["roi"].astype(np.float32), rp["lo"], rp["S"]
    seed = (rp["seed_b"] - lo) * S  # px in roi
    # densify the centreline
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(seed, axis=0).T))]
    t = np.arange(0, d[-1], 0.5)
    P = np.c_[np.interp(t, d, seed[:, 0]), np.interp(t, d, seed[:, 1])]
    tan = np.gradient(cv2.GaussianBlur(P.reshape(-1, 1, 2), (1, 0), 0, sigmaY=3).reshape(-1, 2), axis=0)
    tan /= np.maximum(np.hypot(*tan.T)[:, None], 1e-9)
    nrm = np.c_[-tan[:, 1], tan[:, 0]]
    half = 1.8 * S  # +-1.8 mm across
    off = np.arange(-half, half + 0.5, 0.5)
    X = P[:, 0][:, None] + off[None] * nrm[:, 0][:, None]
    Y = P[:, 1][:, None] + off[None] * nrm[:, 1][:, None]
    prof = map_coordinates(roi, [Y.ravel(), X.ravel()], order=1, mode="nearest").reshape(X.shape)
    mean_p = prof.mean(0)
    xmm = off / S
    base = np.median(np.r_[mean_p[:8], mean_p[-8:]])
    depth = base - mean_p
    k = int(np.argmax(depth))
    halfd = depth[k] / 2
    above = np.where(depth >= halfd)[0]
    x_lo, x_hi = xmm[above[0]], xmm[above[-1]]
    fwhm = x_hi - x_lo

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    fig.text(0.073, 0.93, "STEP 2: RECTIFY, THEN READ THE GREY LEVELS", fontproperties=fp("GeistMono-Medium", 22), color=vc.MUTED)
    fig.text(0.073, 0.865, "Width from the pixels across the crack", fontproperties=fp("Geist-Bold", 54), color=vc.TEXT)
    fig.text(0.073, 0.815, f"Board-rectified crop at {S:.0f} px/mm (a known scale). Each line is one cross-section; the plot is their average.",
             fontproperties=fp("Geist-Regular", 27), color=vc.MUTED)
    # left: crop of the middle ~14 mm of the crack, rotated so the crack runs vertically
    mid = len(P) // 2
    seg = int(7 * S / 0.5)
    sl = slice(max(0, mid - seg), min(len(P), mid + seg))
    ax = fig.add_axes([0.07, 0.12, 0.40, 0.64])
    cx, cy = P[sl, 0].mean(), P[sl, 1].mean()
    ang = np.degrees(np.arctan2(*tan[sl].mean(0)[::-1]))  # crack direction
    Mr = cv2.getRotationMatrix2D((float(cx), float(cy)), ang - 90, 1.0)
    rot = cv2.warpAffine(roi, Mr, (roi.shape[1], roi.shape[0]), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    w_mm, h_mm = 6.0, 14.0
    x0, x1 = int(cx - w_mm / 2 * S), int(cx + w_mm / 2 * S)
    y0, y1 = int(cy - h_mm / 2 * S), int(cy + h_mm / 2 * S)
    crop = rot[max(0, y0):y1, max(0, x0):x1]
    ax.imshow(crop, cmap="gray", vmin=np.percentile(crop, 1), vmax=np.percentile(crop, 99), extent=[-w_mm / 2, w_mm / 2, h_mm / 2, -h_mm / 2], interpolation="lanczos")
    # sampling lines
    for yy in np.linspace(-h_mm / 2 + 1.2, h_mm / 2 - 1.2, 9):
        ax.plot([-1.8, 1.8], [yy, yy], color=vc.AMBER, lw=2, alpha=.85)
    ax.set_xlabel("mm across", fontproperties=fp("Geist-SemiBold", 24), color=vc.MUTED)
    ax.set_ylabel("mm along", fontproperties=fp("Geist-SemiBold", 24), color=vc.MUTED)
    for tl in ax.get_xticklabels() + ax.get_yticklabels():
        tl.set_fontproperties(fp("GeistMono-Medium", 20))
    for s in ax.spines.values():
        s.set_color(vc.LINE)
    # right: profile
    ax2 = fig.add_axes([0.56, 0.12, 0.40, 0.64])
    ax2.plot(xmm, mean_p / 255 if roi.max() > 1.5 else mean_p, color=vc.TEXT, lw=4)
    scale = 255 if roi.max() > 1.5 else 1
    ax2.axhline((base - halfd) / scale, color=vc.MUTED, lw=2, ls="--")
    ax2.axvspan(x_lo, x_hi, color=vc.AMBER, alpha=.25)
    ax2.annotate("", xy=(x_lo, (base - halfd) / scale), xytext=(x_hi, (base - halfd) / scale),
                 arrowprops=dict(arrowstyle="<->", color=vc.AMBER, lw=3.5))
    ax2.text((x_lo + x_hi) / 2, (base - depth[k] * 0.12) / scale, f"{fwhm:.2f} mm", ha="center", va="top",
             fontproperties=fp("Geist-Bold", 44), color=vc.AMBER)
    ax2.text(x_hi + 0.15, (base - halfd) / scale + 0.012, "half depth", fontproperties=fp("GeistMono-Medium", 22), color=vc.MUTED)
    ax2.set_xlabel("mm across the crack", fontproperties=fp("Geist-SemiBold", 24), color=vc.MUTED)
    ax2.set_ylabel("grey level (average of all cross-sections)", fontproperties=fp("Geist-SemiBold", 24), color=vc.MUTED)
    for tl in ax2.get_xticklabels() + ax2.get_yticklabels():
        tl.set_fontproperties(fp("GeistMono-Medium", 20))
    ax2.grid(color=vc.LINE, lw=1.2)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    fig.text(0.073, 0.035, f"Crack {c['id']} of {sample}.jpg  |  pipeline reports {c['width_mm']:.2f} mm (90% range {c['interval_mm'][0]:.2f} to {c['interval_mm'][1]:.2f})  |  a simple half-depth read of the averaged profile is shown here",
             fontproperties=fp("GeistMono-Medium", 17), color=vc.MUTED)
    out = vc.ASSETS / "charts" / "rectified_profile.png"
    fig.savefig(out, dpi=100)
    print("wrote", out, "fwhm", round(fwhm, 3), "reported", c["width_mm"], "S", S)


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["good-straight"]))
