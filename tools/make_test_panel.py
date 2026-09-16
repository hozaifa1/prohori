"""Printable ground-truth test panel: ChArUco board plus synthetic cracks of known width on one sheet.

Board and cracks share one sheet of paper, so they are exactly coplanar, and every crack width is
known by construction. Geometry is saved in the board frame (mm) for evaluation.
"""
import json
import sys
from pathlib import Path

import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori.board import SQUARE_MM, SQUARES_X, SQUARES_Y  # noqa: E402

WIDTHS_MM = [0.30, 0.40, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00]
PAGE_W, PAGE_H = 210.0, 297.0
BOARD_X, BOARD_Y = 35.0, 22.0  # board top-left on the page, mm from page top-left
BOARD_W, BOARD_H = SQUARES_X * SQUARE_MM, SQUARES_Y * SQUARE_MM


def crack_path(rng, x0, y0, length):
    """Tortuous crack-like polyline: a smoothed random walk heading along +x."""
    n = 60
    heading = rng.normal(0, 0.05, n).cumsum()
    heading -= heading.mean()
    step = length / n
    xs, ys = [x0], [y0]
    for h in heading:
        xs.append(xs[-1] + step * np.cos(h))
        ys.append(ys[-1] + step * np.sin(h) + rng.normal(0, 0.12))
    return np.column_stack([xs, ys])


rng = np.random.default_rng(20260917)
specimens = []
for i, w in enumerate(WIDTHS_MM):
    col, row = i % 2, i // 2
    x0 = 20.0 + col * 90.0
    y0 = BOARD_Y + BOARD_H + 32.0 + row * 34.0
    pts = crack_path(rng, x0, y0, 75.0)
    specimens.append({"id": f"C{i + 1}", "width_mm": w,
                      "label_page_mm": [x0, y0 - 9.0],
                      "polyline_board_mm": (pts - [BOARD_X, BOARD_Y]).round(4).tolist()})

out = ROOT / "data" / "print"
board_png = out / "charuco_7x5_20mm.png"
if not board_png.exists():
    sys.exit("run tools/make_board.py first")

pdf = out / "PRINT_ME_test_panel_A4.pdf"
c = canvas.Canvas(str(pdf), pagesize=A4)
Y = lambda y_mm: (PAGE_H - y_mm) * mm  # page-top-down mm -> PDF points
c.setFont("Helvetica-Bold", 11)
c.drawString(20 * mm, Y(12), "PROHORI ground-truth test panel  -  print at 100% / Actual size, matte paper")
c.drawImage(ImageReader(str(board_png)), BOARD_X * mm, Y(BOARD_Y + BOARD_H),
            width=BOARD_W * mm, height=BOARD_H * mm)
c.setLineCap(1)
c.setLineJoin(1)
for s in specimens:
    c.setFont("Helvetica", 8)
    c.drawString(s["label_page_mm"][0] * mm, Y(s["label_page_mm"][1]), f'{s["id"]}  {s["width_mm"]:.2f} mm')
    c.setLineWidth(s["width_mm"] * mm)
    p = c.beginPath()
    pts = np.array(s["polyline_board_mm"]) + [BOARD_X, BOARD_Y]
    p.moveTo(pts[0][0] * mm, Y(pts[0][1]))
    for x, y in pts[1:]:
        p.lineTo(x * mm, Y(y))
    c.drawPath(p, stroke=1, fill=0)
# 100 mm scale bar at the bottom.
c.setLineWidth(0.3 * mm)
c.line(20 * mm, Y(285), 120 * mm, Y(285))
for k in range(11):
    c.line((20 + 10 * k) * mm, Y(285), (20 + 10 * k) * mm, Y(285 - (3 if k % 5 == 0 else 1.5)))
c.setFont("Helvetica", 8)
c.drawString(125 * mm, Y(286), "100 mm scale check")
c.save()

gt = {"board": {"squares": [SQUARES_X, SQUARES_Y], "square_mm": SQUARE_MM, "page_offset_mm": [BOARD_X, BOARD_Y]},
      "specimens": specimens}
(out / "test_panel_ground_truth.json").write_text(json.dumps(gt, indent=1))
print("wrote", pdf)
