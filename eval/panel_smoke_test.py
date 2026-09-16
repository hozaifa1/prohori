"""Smoke test: render the test panel, fake a phone photo, recover px/mm from ChArUco, measure each crack."""
import json
import sys
from pathlib import Path

import cv2
import pymupdf as fitz
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori.board import make_board  # noqa: E402

DPI = 600
page = fitz.open(ROOT / "data/print/PRINT_ME_test_panel_A4.pdf")[0].get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
img = np.frombuffer(page.samples, np.uint8).reshape(page.height, page.width)
gt = json.loads((ROOT / "data/print/test_panel_ground_truth.json").read_text())

# Fake phone capture: mild perspective, downscale to ~16 px/mm, blur, noise.
h, w = img.shape
src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
dst = np.float32([[60, 40], [w - 20, 0], [w - 90, h - 30], [0, h]])
photo = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=255)
photo = cv2.resize(photo, None, fx=16 / (DPI / 25.4), fy=16 / (DPI / 25.4), interpolation=cv2.INTER_AREA)
photo = cv2.GaussianBlur(photo, (0, 0), 0.8)
photo = np.clip(photo + np.random.default_rng(0).normal(0, 3, photo.shape), 0, 255).astype(np.uint8)

board = make_board()
corners, ids, _, _ = cv2.aruco.CharucoDetector(board).detectBoard(photo)
obj = board.getChessboardCorners()[ids.ravel()][:, :2].astype(np.float32)
S = 20.0  # rectified px/mm
H, _ = cv2.findHomography(corners.reshape(-1, 2), obj * S)
off = np.array(gt["board"]["page_offset_mm"])
T = np.array([[1, 0, off[0] * S], [0, 1, off[1] * S], [0, 0, 1]])  # board frame -> page frame
rect = cv2.warpPerspective(photo, T @ H, (int(210 * S), int(297 * S)), borderValue=255)

print(f"corners {len(ids)}/24")
print("id    true_mm  meas_mm  err_mm")
for s in gt["specimens"]:
    pts = (np.array(s["polyline_board_mm"]) + off) * S
    x0, y0 = pts.min(0) - 3 * S
    x1, y1 = pts.max(0) + 3 * S
    roi = rect[int(y0):int(y1), int(x0):int(x1)]
    _, m = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    m = np.uint8(lab == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])) * 255
    dt = cv2.distanceTransform(m, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    sk = cv2.ximgproc.thinning(m) > 0
    wpx = np.median(2 * dt[sk]) - 1.0  # characterised +1 px bias removed
    print(f'{s["id"]:4s}  {s["width_mm"]:6.2f}  {wpx / S:7.3f}  {wpx / S - s["width_mm"]:+.3f}')
