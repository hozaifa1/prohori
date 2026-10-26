"""Compare two Prohori endpoints image by image (used by infra/cool_live.sh verify).

  python infra/cool_compare.py <base-url-A> <base-url-B> [--tol 0.005] [--dir service/static/samples]

POSTs every *.jpg in --dir to /api/measure (form field `image`) on both endpoints and compares, per crack id: gate tier,
certified flag, width_mm (and the other width columns).  Exit 1 if any tier differs or any width differs by more than --tol mm.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys


def post(base: str, path: str) -> dict:
    out = subprocess.run(["curl", "-s", "--max-time", "180", "-F", f"image=@{path}", base.rstrip("/") + "/api/measure"],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": out[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tol", type=float, default=0.005)
    ap.add_argument("--dir", default="service/static/samples")
    args = ap.parse_args()
    worst, bad = 0.0, 0
    for f in sorted(glob.glob(os.path.join(args.dir, "*.jpg"))):
        ra, rb = post(args.a, f), post(args.b, f)
        ma, mb = ra.get("measurement") or {}, rb.get("measurement") or {}
        if not ma or not mb:
            print(f"{os.path.basename(f):22s} NO MEASUREMENT  A={str(ra)[:80]}  B={str(rb)[:80]}")
            bad += 1
            continue
        ca = {c["id"]: c for c in ma.get("cracks") or []}
        cb = {c["id"]: c for c in mb.get("cracks") or []}
        tiers_same = ({k: (v.get("tier"), v.get("certified")) for k, v in ca.items()}
                      == {k: (v.get("tier"), v.get("certified")) for k, v in cb.items()})
        gate_same = (ma.get("gate") or {}).get("tier") == (mb.get("gate") or {}).get("tier")
        dmax = 0.0
        for k in ca.keys() & cb.keys():
            for col in ("width_mm", "uncertainty_mm", "length_mm", "width_blackcore_mm"):
                x, y = ca[k].get(col), cb[k].get(col)
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    dmax = max(dmax, abs(x - y))
        ok = tiers_same and gate_same and ca.keys() == cb.keys() and dmax <= args.tol
        print(f"{os.path.basename(f):22s} cracks {len(ca)}/{len(cb)}  tiers {'same' if tiers_same else 'DIFF'}  "
              f"gate {(ma.get('gate') or {}).get('tier')}/{(mb.get('gate') or {}).get('tier')}  "
              f"max|d| {dmax:.4f} mm  {'OK' if ok else 'FAIL'}")
        worst = max(worst, dmax)
        bad += not ok
    print(f"worst |d| = {worst:.4f} mm over all columns; images failing: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
