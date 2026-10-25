#!/usr/bin/env python3
"""Wall-clock timeline of one analyze() call: inclusive start/end of the main sections (all threads), median over frames.
Shows the critical path once parts of the frame run concurrently.  python eval/cool_loop_timeline.py --input raw=DIR [--threads 4]"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import cool_bench as cb  # noqa: E402

SECTIONS = ["_detect_board", "_board_quality", "_edge_sigma", "_locate_cracks", "_match_specimens", "_extract_roi",
            "_measure_roi", "_bg_map", "_thin", "_longest_path", "_noise_sigma"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--reps", type=int, default=2)
    a = ap.parse_args(argv)
    from prohori import measure as M
    cv2.setNumThreads(a.threads)
    ev: list = []
    orig = {n: getattr(M, n) for n in SECTIONS}

    def wrap(n, f):
        def w(*x, **k):
            t0 = time.perf_counter()
            try:
                return f(*x, **k)
            finally:
                ev.append((n, threading.get_ident(), t0, time.perf_counter()))
        return w
    for n in SECTIONS:
        setattr(M, n, wrap(n, orig[n]))
    blobs = cb.load_bytes(cb.collect_inputs(a.input, 1))
    imgs = [cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for b in blobs.values()]
    M.analyze(imgs[0])
    rows: dict[str, list] = {}
    for _ in range(a.reps):
        for im in imgs:
            ev.clear()
            t0 = time.perf_counter()
            res = M.analyze(im)
            tot = time.perf_counter() - t0
            if not res["ok"]:
                continue
            by: dict[str, list] = {}
            for n, tid, s, e in ev:
                by.setdefault(n, []).append((s - t0, e - t0))
            rows.setdefault("TOTAL", []).append((0.0, tot, tot, 1))
            for n, v in by.items():
                s0, e1 = min(x[0] for x in v), max(x[1] for x in v)
                rows.setdefault(n, []).append((s0, e1, sum(x[1] - x[0] for x in v), len(v)))
    print(f"cv2 threads {a.threads}, PROHORI_THREADS={M._n_threads()}, frames {len(rows['TOTAL'])}  (ms, median: first start, last end, sum of calls, calls/frame)")
    for n in ["TOTAL"] + SECTIONS:
        if n in rows:
            arr = np.array(rows[n])
            print(f"{n:18s} start {np.median(arr[:, 0]) * 1e3:7.1f}  end {np.median(arr[:, 1]) * 1e3:7.1f}  busy {np.median(arr[:, 2]) * 1e3:7.1f}  calls {np.median(arr[:, 3]):.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
