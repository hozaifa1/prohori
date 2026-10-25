#!/usr/bin/env python3
"""cProfile of prohori.measure.analyze over the benchmark inputs: where does the time go, cv2 vs Python/numpy?

Single OpenCV thread (the configuration COOL can run), numpy Zhang-Suen thinning shim if the build has no ximgproc.
Writes <out>.json and <out>.md: top functions by self time, tagged cv2 / numpy / python, with file:line for PROHORI
functions, plus totals.  cProfile adds per-call overhead (about 1.3-2x on call-heavy code), so use the SHARES, not
the absolute milliseconds; eval/cool_bench.py's headline timings are the un-instrumented numbers.

  python eval/cool_profile.py --out OUT --input raw=DIR --input samples=DIR --input synth=DIR [--top 15] [--passes 1]
"""
from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import re
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import cool_bench as cb  # noqa: E402
from cool_compat import install_thinning  # noqa: E402


def classify(filename: str, funcname: str) -> str:
    """cProfile prints OpenCV functions as bare '<resize>' and methods as "<method 'x' of 'cv2...' objects>"."""
    if filename == "~":
        if "cv2" in funcname:
            return "cv2"
        if "numpy" in funcname or "ndarray" in funcname:
            return "numpy"
        if re.fullmatch(r"<[A-Za-z_]\w*>", funcname):
            return "cv2"
        return "builtin"
    return "numpy" if "numpy" in filename else "python"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--thinning", default="auto", choices=["auto", "native", "shim"])
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    from prohori import measure
    cv2.setNumThreads(a.threads)
    used = install_thinning(measure, a.thinning)
    inputs = cb.collect_inputs(a.input, a.stride)
    blobs = {n: p.read_bytes() for n, p in inputs}
    imgs = {n: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for n, b in blobs.items()}
    measure.analyze(next(iter(imgs.values())))  # warm caches
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(a.passes):
        for n, im in imgs.items():
            measure.analyze(im)
    pr.disable()
    st = pstats.Stats(pr)
    total = st.total_tt
    rows = []
    for (fn, ln, name), (cc, nc, tt, ct, callers) in st.stats.items():
        kind = classify(fn, name)
        short = fn.replace("\\", "/")
        short = short.split("/Prohori/")[-1].split("site-packages/")[-1] if fn != "~" else "~"
        rows.append({"kind": kind, "function": name, "where": f"{short}:{ln}" if fn != "~" else "", "calls": nc,
                     "self_s": tt, "cum_s": ct})
    rows.sort(key=lambda r: -r["self_s"])
    tot_by = {}
    for r in rows:
        tot_by[r["kind"]] = tot_by.get(r["kind"], 0.0) + r["self_s"]
    frames = len(imgs) * a.passes
    doc = {"label": a.label, "cv2": cv2.__version__, "cv2_file": cv2.__file__, "threads": a.threads, "thinning": used,
           "frames": frames, "total_profiled_s": total, "self_s_by_kind": tot_by,
           "share_by_kind": {k: v / total for k, v in tot_by.items()}, "top": rows[:60]}
    Path(a.out + ".json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    L = [f"### cProfile of analyze(), {frames} frames, {a.threads} OpenCV thread(s), cv2 {cv2.__version__}, thinning={used}",
         "", f"profiled total {total:.1f} s ({total / frames * 1000:.0f} ms/frame under cProfile).  Self-time share by kind: " +
         ", ".join(f"{k} {v / total * 100:.1f} %" for k, v in sorted(tot_by.items(), key=lambda kv: -kv[1])), "",
         f"| # | kind | function | file:line | calls | self ms/frame | share |", "|---:|---|---|---|---:|---:|---:|"]
    for i, r in enumerate(rows[:a.top], 1):
        L.append(f"| {i} | {r['kind']} | `{r['function']}` | {r['where']} | {r['calls']} | {r['self_s'] / frames * 1000:.2f} | "
                 f"{r['self_s'] / total * 100:.1f} % |")
    for kind in ("cv2", "python"):
        L += ["", f"Top {kind} entries:", "", "| function | file:line | calls | self ms/frame | share |", "|---|---|---:|---:|---:|"]
        for r in [r for r in rows if r["kind"] == kind][:10]:
            L.append(f"| `{r['function']}` | {r['where']} | {r['calls']} | {r['self_s'] / frames * 1000:.2f} | {r['self_s'] / total * 100:.1f} % |")
    Path(a.out + ".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
