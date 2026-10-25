#!/usr/bin/env python3
"""Standalone reproducer (cv2 + numpy only, no PROHORI code).

cv2.connectedComponentsWithStats(mask, connectivity=8) on a 1800x1273 uint8 mask aborts the process with a glibc
heap-corruption message when cv2.setNumThreads(n) with n >= 2, on the COOL AMI's OpenCV 5.1.0-dev (c8g.xlarge).

  python cc_repro.py --threads 2 --calls 100 --mask mask_locator_canvas.png     (exit 0 and prints OK, or aborts)
  python cc_repro.py --threads 2 --calls 100                                    (synthetic sine-line mask, same size)
  python cc_repro.py --threads 2 --algo bbdt|wu|spaghetti  --conn 4|8
"""
import argparse
import sys

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--threads", type=int, default=2)
ap.add_argument("--calls", type=int, default=100)
ap.add_argument("--mask", default="")
ap.add_argument("--conn", type=int, default=8)
ap.add_argument("--algo", default="default", choices=["default", "spaghetti", "bbdt", "wu"])
a = ap.parse_args()

cv2.setNumThreads(a.threads)
if a.mask:
    m = cv2.imread(a.mask, cv2.IMREAD_GRAYSCALE)
else:
    h, w = 1800, 1273
    m = np.zeros((h, w), np.uint8)
    for x in range(40, w - 40):
        y = int(h * 0.5 + 120 * np.sin(x / 150.0))
        m[y - 2:y + 3, x] = 255
print(f"cv2 {cv2.__version__} ({cv2.__file__}) threads={cv2.getNumThreads()} mask={m.shape} nonzero={int((m > 0).sum())} "
      f"conn={a.conn} algo={a.algo}", flush=True)
algo = {"spaghetti": cv2.CCL_SPAGHETTI, "bbdt": cv2.CCL_BBDT, "wu": cv2.CCL_WU}.get(a.algo)
for i in range(a.calls):
    if algo is None:
        n, lab, stats, cen = cv2.connectedComponentsWithStats(m, connectivity=a.conn)
    else:
        n, lab, stats, cen = cv2.connectedComponentsWithStatsWithAlgorithm(m, a.conn, cv2.CV_32S, algo)
print("OK components:", n)
sys.exit(0)
