#!/usr/bin/env python3
"""Harness of the COOL developer-agent optimisation loop (eval/results/cool_agentloop/).

One invocation measures ONE source tree (the tree this file lives in: ROOT/src is what gets imported, so every variant is
a full checkout and the spawn-based worker processes see the same code) on whatever OpenCV `python` resolves to
(COOL, stock pip wheel, ...):

  run      latency per stage (decode, detect, rectify, measure, other, analyze, e2e) over the 85 benchmark frames at a fixed
           OpenCV thread count, optional WxT throughput sweep, optional cProfile pass (top functions by self time, tagged
           cv2 / numpy / python), and a bit-exact dump of every number of every result (the accuracy-invariance record).
  compare  REF.dump NEW.dump: the guard rails.  For the 29 panel photos (input kind "raw"): max |dw| over every crack width,
           tier flips per crack, and bitwise identity of the whole result; for all 85 frames: bitwise identity.

--compat describes what the tree needs from the harness: "none" = the tree is self-sufficient on this OpenCV (the optimised
tree), "thin" = baseline HEAD tree: add the numpy Zhang-Suen ximgproc.thinning shim when the OpenCV has no contrib,
"thin+bbdt" = also route connectedComponentsWithStats to CCL_BBDT (what the baseline needs to run at >= 2 threads on COOL).
"""
from __future__ import annotations

import argparse
import cProfile
import gzip
import json
import pstats
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import cool_bench as cb  # noqa: E402
from cool_compat import install_thinning  # noqa: E402
from cool_profile import classify  # noqa: E402

SCHEMA = 1


def _compat(measure, mode: str):
    if mode == "none":
        return "none"
    if mode == "thin":
        return install_thinning(measure, "auto", "default")
    if mode == "thin+bbdt":
        return install_thinning(measure, "auto", "bbdt")
    raise SystemExit(f"unknown --compat {mode}")


def _sweep_compat(mode: str) -> tuple[str, str]:
    """(thinning mode, ccl mode) in the vocabulary of cool_bench.run_config / cool_compat.install_thinning."""
    return {"none": ("none", "default"), "thin": ("auto", "default"), "thin+bbdt": ("auto", "bbdt")}[mode]


def pooled(per: dict, stage: str) -> dict:
    v = np.concatenate([np.asarray(per[n][stage], float) for n in per])
    return {"n": int(v.size), "p50": cb.pct(v, 50), "p95": cb.pct(v, 95), "mean": float(v.mean()), "min": float(v.min())}


def profile_pass(measure, imgs: dict, top: int = 30) -> dict:
    pr = cProfile.Profile()
    pr.enable()
    for im in imgs.values():
        measure.analyze(im)
    pr.disable()
    st = pstats.Stats(pr)
    total = st.total_tt
    rows = []
    for (fn, ln, name), (cc, nc, tt, ct, callers) in st.stats.items():
        kind = classify(fn, name)
        short = fn.replace("\\", "/")
        short = short.split("/src/")[-1].split("site-packages/")[-1] if fn != "~" else "~"
        rows.append({"kind": kind, "function": name, "where": f"{short}:{ln}" if fn != "~" else "", "calls": nc,
                     "self_s": tt, "cum_s": ct})
    rows.sort(key=lambda r: -r["self_s"])
    by = {}
    for r in rows:
        by[r["kind"]] = by.get(r["kind"], 0.0) + r["self_s"]
    n = len(imgs)
    return {"frames": n, "total_s": total, "share_by_kind": {k: v / total for k, v in by.items()},
            "top": [{**r, "ms_per_frame": r["self_s"] / n * 1000, "share": r["self_s"] / total} for r in rows[:top]]}


def cmd_run(a) -> int:
    from prohori import measure
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = cb.collect_inputs(a.input, a.stride)
    if not inputs:
        print("no inputs", file=sys.stderr)
        return 2
    if a.threads:
        cv2.setNumThreads(a.threads)
    used = _compat(measure, a.compat)
    env = cb.capture_env()
    env.pop("cv2_build_information", None)
    env.pop("pip_freeze", None)
    env["cv2_threads_set"] = cv2.getNumThreads()
    print(f"[{a.label}] cv2 {cv2.__version__} {cv2.__file__} threads={cv2.getNumThreads()} compat={a.compat}({used}) "
          f"frames={len(inputs)} src={ROOT}", flush=True)
    blobs = cb.load_bytes(inputs)
    per, pub, first, meta, wall = cb.timed_passes(measure, blobs, a.reps, a.warmup)
    stages = {s: pooled(per, s) for s in cb.STAGES}
    print(f"[{a.label}] e2e p50 {stages['e2e']['p50']:.1f} ms  p95 {stages['e2e']['p95']:.1f}  mean {stages['e2e']['mean']:.1f}  "
          f"analyze p50 {stages['analyze']['p50']:.1f}  ({wall:.0f}s)", flush=True)
    doc = {"schema": SCHEMA, "label": a.label, "compat": a.compat, "thinning_used": used,
           "src_git": cb._sh(f'git -C "{ROOT}" rev-parse --short HEAD'), "env": env, "threads": cv2.getNumThreads(),
           "protocol": {"reps": a.reps, "warmup": a.warmup, "stride": a.stride, "inputs": [n for n, _ in inputs]},
           "stages": stages, "per_image": per, "meta": meta, "wall_s": wall, "fps_inproc": len(blobs) * a.reps / wall,
           "deterministic": all(len(s) == 1 for s in pub.values())}
    dump = {n: cb.flatten({k: v for k, v in res.items() if k != "timing_ms"}) for n, res in first.items()}
    with gzip.open(out / f"{a.label}.dump.json.gz", "wt", encoding="utf-8") as f:
        json.dump(dump, f, separators=(",", ":"), sort_keys=True)
    if a.profile:
        imgs = {n: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for n, b in blobs.items()}
        measure.analyze(next(iter(imgs.values())))
        doc["profile"] = profile_pass(measure, imgs, a.profile_top)
        sh = doc["profile"]["share_by_kind"]
        print(f"[{a.label}] profile (cProfile): " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in sorted(sh.items(), key=lambda kv: -kv[1])), flush=True)
        for r in doc["profile"]["top"][:8]:
            print(f"    {r['ms_per_frame']:7.2f} ms/frame {r['share'] * 100:5.1f}%  {r['kind']:6s} {r['function'][:44]} {r['where']}", flush=True)
    if a.sweep:
        doc["sweep"] = {}
        thin, ccl = _sweep_compat(a.compat)
        sw_inputs = inputs[::a.sweep_stride]
        for spec in [s for s in a.sweep.split(",") if s]:
            try:
                r = cb.run_config(spec, sw_inputs, a.sweep_reps, [sw_inputs[0][0]], thin, ccl)
            except Exception as e:  # a failed config is data
                r = {"spec": spec, "error": f"{type(e).__name__}: {e}"}
            doc["sweep"][spec] = r
            if "fps" in r:
                print(f"[{a.label}] sweep {spec}: {r['fps']:.2f} fps  e2e p50 {r['e2e_ms']['p50']:.0f} p95 {r['e2e_ms']['p95']:.0f} ms", flush=True)
            else:
                print(f"[{a.label}] sweep {spec}: FAILED {r['error']}", flush=True)
    (out / f"{a.label}.loop.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return 0


# --------------------------------------------------------------------------------------------- compare

def load_dump(p: str) -> dict:
    p = Path(p)
    if p.name.endswith(".loop.json"):
        p = p.with_name(p.name.replace(".loop.json", ".dump.json.gz"))
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def compare_dumps(ref: dict, new: dict, tol_mm: float = 0.005) -> dict:
    """Guard-rail verdict.  Panel photos = inputs named raw/*."""
    R, N = cb._rekey_all(ref), cb._rekey_all(new)
    names = sorted(set(R) & set(N))
    panel = [n for n in names if n.startswith("raw/")]
    out = {"n_inputs": len(names), "n_panel": len(panel), "bitwise_identical_all": all(R[n] == N[n] for n in names)
           and set(R) == set(N), "bitwise_identical_panel": all(R[n] == N[n] for n in panel)}
    out["n_frames_differing"] = sum(R[n] != N[n] for n in names)
    max_w = max_mm = 0.0
    n_cr = n_flip = n_cert_flip = n_missing = 0
    worst = None
    for n in panel:
        fa, fb = R[n], N[n]
        ids = sorted({k.split(".")[1] for k in fa if k.startswith("cracks.")} | {k.split(".")[1] for k in fb if k.startswith("cracks.")})
        for cid in ids:
            n_cr += 1
            kw = f"cracks.{cid}.width_mm"
            if kw not in fa or kw not in fb:
                n_missing += 1
                continue
            if fa.get(f"cracks.{cid}.tier") != fb.get(f"cracks.{cid}.tier"):
                n_flip += 1
            if fa.get(f"cracks.{cid}.certified") != fb.get(f"cracks.{cid}.certified"):
                n_cert_flip += 1
            dw = abs(cb._fnum(fa[kw]) - cb._fnum(fb[kw]))
            if dw > max_w:
                max_w, worst = dw, f"{n}:{cid}"
        for k, va in fa.items():
            if cb.is_mm_field(k) and k in fb:
                x, y = cb._fnum(va), cb._fnum(fb[k])
                if x is not None and y is not None:
                    max_mm = max(max_mm, abs(x - y))
    out.update({"panel_cracks": n_cr, "panel_cracks_missing_in_one": n_missing, "tier_flips": n_flip, "certified_flips": n_cert_flip,
                "max_abs_dw_mm": max_w, "max_abs_dmm_any_field": max_mm, "worst": worst, "tol_mm": tol_mm})
    out["pass"] = bool(n_missing == 0 and n_flip == 0 and max_w <= tol_mm)
    return out


def cmd_compare(a) -> int:
    rep = compare_dumps(load_dump(a.ref), load_dump(a.new), a.tol)
    print(json.dumps(rep, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return 0 if rep["pass"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--input", action="append", required=True, help="kind=DIR (raw= panel photos, samples=, synth=)")
    r.add_argument("--stride", type=int, default=1)
    r.add_argument("--threads", type=int, default=1)
    r.add_argument("--reps", type=int, default=5)
    r.add_argument("--warmup", type=int, default=1)
    r.add_argument("--compat", default="none", choices=["none", "thin", "thin+bbdt"])
    r.add_argument("--profile", action="store_true")
    r.add_argument("--profile-top", type=int, default=30)
    r.add_argument("--sweep", default="")
    r.add_argument("--sweep-stride", type=int, default=2)
    r.add_argument("--sweep-reps", type=int, default=2)
    r.set_defaults(fn=cmd_run)
    c = sp.add_parser("compare")
    c.add_argument("ref")
    c.add_argument("new")
    c.add_argument("--tol", type=float, default=0.005)
    c.add_argument("--json", default="")
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
