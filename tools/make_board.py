"""Render the ChArUco board to an A4 PDF at exact physical size, with a print-scale check bar."""
import sys
from pathlib import Path

import cv2
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prohori.board import MARKER_MM, SQUARE_MM, SQUARES_X, SQUARES_Y, make_board  # noqa: E402

DPI = 600
out_dir = Path(__file__).resolve().parents[1] / "data" / "print"
out_dir.mkdir(parents=True, exist_ok=True)

board = make_board()
w_mm, h_mm = SQUARES_X * SQUARE_MM, SQUARES_Y * SQUARE_MM
px = lambda v: int(round(v / 25.4 * DPI))
img = board.generateImage((px(w_mm), px(h_mm)), marginSize=0, borderBits=1)
png = out_dir / "charuco_7x5_20mm.png"
cv2.imwrite(str(png), img)

# Round-trip check: the rendered board must be fully detected.
det = cv2.aruco.CharucoDetector(board)
small = cv2.resize(img, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
small = cv2.copyMakeBorder(small, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
corners, ids, _, _ = det.detectBoard(small)
n = 0 if ids is None else len(ids)
expected = (SQUARES_X - 1) * (SQUARES_Y - 1)
print(f"round-trip: {n}/{expected} ChArUco corners detected")
assert n == expected

pdf = out_dir / "PRINT_ME_charuco_A4.pdf"
c = canvas.Canvas(str(pdf), pagesize=A4)
pw, ph = A4
x0, y0 = (pw - w_mm * mm) / 2, ph - 40 * mm - h_mm * mm
c.drawImage(ImageReader(str(png)), x0, y0, width=w_mm * mm, height=h_mm * mm)
c.setFont("Helvetica-Bold", 14)
c.drawString(20 * mm, ph - 20 * mm, "PROHORI reference board  -  print at 100% / 'Actual size'")
c.setFont("Helvetica", 10)
c.drawString(20 * mm, ph - 27 * mm,
             f"ChArUco {SQUARES_X}x{SQUARES_Y}, square {SQUARE_MM:.0f} mm, marker {MARKER_MM:.0f} mm, DICT_5X5_100")
# 100 mm scale-check bar with 10 mm ticks.
bx, by = 20 * mm, y0 - 25 * mm
c.setLineWidth(1)
c.line(bx, by, bx + 100 * mm, by)
for i in range(11):
    t = 4 * mm if i % 5 == 0 else 2 * mm
    c.line(bx + i * 10 * mm, by, bx + i * 10 * mm, by + t)
c.drawString(bx, by - 6 * mm, "Scale check: this bar must measure exactly 100 mm with a ruler.")
c.drawString(bx, by - 12 * mm, "Also check: one board square = 20.0 mm. If not, reprint with scaling OFF.")
c.drawString(bx, by - 24 * mm, "Glue flat onto stiff cardboard. Do not bend, laminate glossy, or fold.")
c.drawString(bx, by - 30 * mm, "Write the ruler-measured 100 mm bar length here: ________ mm")
c.save()
print("wrote", pdf)
