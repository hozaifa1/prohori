#!/usr/bin/env python3
"""COOL (Cloud Optimized OpenCV) benchmark and accuracy-invariance harness for the PROHORI measurement workload.

What it does (one OpenCV build per invocation; the OpenCV that is imported is whatever `python` resolves, so the
same script runs under COOL, stock pip wheels and a self-built OpenCV):

  run      time prohori.measure.analyze on every input (decode + board detect + rectify/locate + width estimation +
           package/gate), per stage, with warm-up and repetitions; sweep cv2.setNumThreads and process-level
           parallelism (WxT configs) for throughput; microbench the exact OpenCV calls the pipeline uses; run one
           instrumented "trace" pass that times every cv2 function the pipeline calls and fingerprints every output
           (sha1 of the bytes) so a numeric difference between builds can be pinned to the first OpenCV call that
           differs; dump every number of every result as float64 hex (accuracy invariance).
  compare  A.bench.json B.bench.json: per-stage speedups A/B with bootstrap 95 % CIs, microbench and per-function
           tables, thread/worker sweep, and the invariance verdict (bitwise identical, or max |dw| in mm and which
           inputs / cracks differ).
  env      print the environment record only.

Nothing here edits src/prohori/measure.py: the fine-grained instrumentation replaces module attributes at run time
(`measure.cv2` by a timing proxy, selected private functions by timing wrappers) during the trace pass only.  The
headline timings come from the un-instrumented pass.

Usage (from the repo root; see research/COOL_NOTES.md for the full protocol):
  python eval/cool_bench.py run --label cool_c8g.xlarge --out DIR --input raw=data/raw --input samples=DIR2 \
      --input synth=DIR3 --reps 5 --sweep 1x1,1x2,1x4,2x1,4x1 --micro
  python eval/cool_bench.py compare DIR/pip.bench.json DIR/cool.bench.json
"""
from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import math
import multiprocessing as mp
import os
import platform
import re
import subprocess
import sys
import time
import types
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

SCHEMA = 2
STAGES = ["decode", "detect", "rectify", "measure", "other", "analyze", "e2e"]
STAGE_DOC = {
    "decode": "cv2.imdecode of the JPEG (the service does this before analyze)",
    "detect": "ChArUco detection (resize, aruco, cornerSubPix, findHomography), pose, board blur",
    "rectify": "page rectification (warpPerspective), glare/ink level, crack locator (blur, bg map, morphology, "
               "connected components, thinning)",
    "measure": "specimen matching, edge sigma, full-resolution ROI warps, profile/width estimators",
    "other": "packaging and gate (analyze total minus the three stages above)",
    "analyze": "measure.analyze() wall time as seen by the caller",
    "e2e": "decode + analyze",
}
# python-level functions of prohori.measure wrapped (inclusive timings) in the trace pass
PY_WRAP = ["_detect_board", "_pose_obliquity", "_noise_sigma", "_locate_cracks", "_bg_map", "_match_specimens",
           "_edge_sigma", "_extract_roi", "_measure_roi", "_station_widths", "_black_core", "_fit_bar_widths",
           "_uncertainty", "_longest_path", "_smooth_resample", "_fwhm"]
LEAF_SHA_ONLY = ("polyline_px", "corners_px")  # large arrays: fingerprinted, not dumped as hex


# the ximgproc.thinning shim lives in eval/cool_compat.py (reusable by the live COOL service)
from cool_compat import ShimCv2, install_thinning, thinning_zs  # noqa: E402,F401

# --------------------------------------------------------------------------------------------- environment

def _sh(cmd: str, timeout: float = 10.0) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception as e:  # pragma: no cover - best effort
        return f"<{type(e).__name__}>"


def _imds(path: str) -> str | None:
    """EC2 IMDSv2 lookup (None off-EC2)."""
    import urllib.request
    try:
        rq = urllib.request.Request("http://169.254.169.254/latest/api/token", method="PUT",
                                    headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"})
        tok = urllib.request.urlopen(rq, timeout=1.5).read().decode()
        rq = urllib.request.Request("http://169.254.169.254/latest/meta-data/" + path,
                                    headers={"X-aws-ec2-metadata-token": tok})
        return urllib.request.urlopen(rq, timeout=1.5).read().decode().strip()
    except Exception:
        return None


def capture_env() -> dict:
    maps = ""
    try:
        maps = Path("/proc/self/maps").read_text()
    except Exception:
        pass
    libs = sorted({m.group(1) for m in re.finditer(r"(\S+\.so[^\s]*)", maps) if
                   re.search(r"kleidi|cool|opencv|cv2|ipp|openblas|tbb|jpeg|png|tiff|webp", m.group(1), re.I)})
    cool = {}
    for pat in ("/opt/cool/VERSION*", "/opt/cool/version*", "/opt/cool/*.txt", "/opt/cool/*.md", "/opt/cool/README*",
                "/opt/cool/*.json", "/opt/cool/*.cfg"):
        for f in glob.glob(pat):
            try:
                cool[f] = Path(f).read_text(errors="replace")[:4000]
            except Exception:
                pass
    cool_ls = _sh("ls -la /opt/cool 2>/dev/null | head -50")
    pipf = _sh(f'"{sys.executable}" -m pip freeze 2>/dev/null | head -60', 30)
    return {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version, "python_exe": sys.executable, "platform": platform.platform(),
        "machine": platform.machine(), "kernel": platform.release(),
        "cv2_version": cv2.__version__, "cv2_file": cv2.__file__, "numpy": np.__version__,
        "cv2_num_threads_default": cv2.getNumThreads(), "cv2_num_cpus": cv2.getNumberOfCPUs(),
        "cv2_use_optimized": bool(cv2.useOptimized()), "cpu_features_line": cv2.getCPUFeaturesLine(),
        "cv2_build_information": cv2.getBuildInformation(),
        "mapped_libs": libs, "lscpu": _sh("lscpu"), "os_release": _sh("cat /etc/os-release"),
        "meminfo_total": _sh("grep MemTotal /proc/meminfo"),
        "imds": {k: _imds(k) for k in ("instance-type", "ami-id", "instance-id", "placement/availability-zone")},
        "cool_files": cool, "opt_cool_ls": cool_ls, "pip_freeze": pipf,
        "env_vars": {k: v for k, v in os.environ.items() if k.startswith(("OPENCV", "OMP_", "KLEIDI", "COOL"))},
        "git_head": _sh(f'git -C "{ROOT}" rev-parse HEAD'),
    }


# --------------------------------------------------------------------------------------------- inputs

def collect_inputs(specs: list[str], stride: int = 1) -> list[tuple[str, Path]]:
    """specs: ["kind=DIR", ...] -> sorted [(kind/filename, path)], every `stride`-th file of each kind."""
    out = []
    for sp in specs:
        kind, _, d = sp.partition("=")
        files = sorted(Path(d).glob("*.jpg")) + sorted(Path(d).glob("*.png"))
        out += [(f"{kind}/{f.name}", f) for f in files[::stride]]
    return out


def manifest(inputs: list[tuple[str, Path]]) -> dict:
    return {n: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for n, p in inputs}


# --------------------------------------------------------------------------------------------- fingerprints

def fhex(v) -> str:
    return float(v).hex()


def hobj(o, h) -> None:
    """Feed a nested result (arrays, scalars, containers) into hash h, bit-exactly."""
    if isinstance(o, np.ndarray):
        h.update(f"{o.dtype}{o.shape}".encode())
        h.update(np.ascontiguousarray(o).tobytes())
    elif isinstance(o, (list, tuple)):
        h.update(b"[")
        for x in o:
            hobj(x, h)
    elif isinstance(o, dict):
        h.update(b"{")
        for k in sorted(o, key=str):
            h.update(str(k).encode())
            hobj(o[k], h)
    elif isinstance(o, (float, np.floating)):
        h.update(float(o).hex().encode())
    elif isinstance(o, (bool, int, np.integer, str, type(None))):
        h.update(repr(o).encode())
    else:
        h.update(type(o).__name__.encode())


def sha(o, n: int = 10) -> str:
    h = hashlib.sha1()
    hobj(o, h)
    return h.hexdigest()[:n]


def flatten(res: dict, prefix: str = "") -> dict:
    """Every leaf of a result (except timing_ms) as a string: float64 -> hex, ints/strings/bools -> repr; the big
    pixel arrays (LEAF_SHA_ONLY) become a single fingerprint."""
    out: dict[str, str] = {}

    def rec(o, p):
        if isinstance(o, dict):
            for k in sorted(o):
                if p == "" and k == "timing_ms":
                    continue
                if k in LEAF_SHA_ONLY:
                    out[f"{p}{k}"] = "sha:" + sha(o[k], 16)
                else:
                    rec(o[k], f"{p}{k}.")
        elif isinstance(o, (list, tuple)):
            for i, x in enumerate(o):
                rec(x, f"{p}{i}.")
        elif isinstance(o, (float, np.floating)):
            out[p[:-1]] = fhex(o)
        elif isinstance(o, (bool, np.bool_)):
            out[p[:-1]] = repr(bool(o))
        elif isinstance(o, (int, np.integer)):
            out[p[:-1]] = repr(int(o))
        else:
            out[p[:-1]] = repr(o)
    rec(res, prefix)
    return out


def canonical_sha(flat_by_input: dict) -> str:
    return hashlib.sha256(json.dumps(flat_by_input, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# --------------------------------------------------------------------------------------------- statistics

def pct(a, q) -> float:
    a = np.asarray(a, float)
    return float(np.percentile(a, q)) if a.size else float("nan")


def summarize(a) -> dict:
    a = np.asarray(a, float)
    return {"n": int(a.size), "mean": float(a.mean()), "p50": pct(a, 50), "p95": pct(a, 95), "min": float(a.min()),
            "max": float(a.max())}


def boot_ratio(A: list, B: list, stat, n_boot: int = 2000, seed: int = 12345):
    """Paired image-cluster bootstrap of stat(A pooled)/stat(B pooled).  A, B: lists (per image) of 1-D arrays."""
    nA = len(A)
    pa = stat(np.concatenate(A))
    pb = stat(np.concatenate(B))
    point = pa / pb
    rng = np.random.default_rng(seed)
    r = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, nA, nA)
        r[i] = stat(np.concatenate([A[j] for j in idx])) / stat(np.concatenate([B[j] for j in idx]))
    return point, float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


# --------------------------------------------------------------------------------------------- timed passes

def load_bytes(inputs) -> dict:
    return {n: p.read_bytes() for n, p in inputs}


def one_frame(measure, raw: bytes) -> tuple[dict, dict]:
    """decode + analyze one frame; returns (timings_ms, result)."""
    t0 = time.perf_counter_ns()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    t1 = time.perf_counter_ns()
    res = measure.analyze(img)
    t2 = time.perf_counter_ns()
    tm = res["timing_ms"]
    an = (t2 - t1) / 1e6
    rec = {"decode": (t1 - t0) / 1e6, "detect": tm["detect"], "rectify": tm["rectify"], "measure": tm["measure"],
           "analyze": an}
    rec["other"] = max(0.0, an - rec["detect"] - rec["rectify"] - rec["measure"])
    rec["e2e"] = rec["decode"] + an
    return rec, res


def timed_passes(measure, blobs: dict, reps: int, warmup: int, want_public: bool = True):
    names = list(blobs)
    for _ in range(warmup):
        for n in names:
            one_frame(measure, blobs[n])
    per = {n: {s: [] for s in STAGES} for n in names}
    pub: dict[str, set] = {n: set() for n in names}
    first_res: dict[str, dict] = {}
    meta = {}
    wall0 = time.perf_counter()
    for r in range(reps):
        for n in names:
            rec, res = one_frame(measure, blobs[n])
            for s in STAGES:
                per[n][s].append(rec[s])
            if want_public:
                pub[n].add(sha({k: v for k, v in res.items() if k != "timing_ms"}, 16))
                if r == 0:
                    first_res[n] = res
                    meta[n] = {"ok": bool(res["ok"]), "n_cracks": len(res["cracks"]),
                               "certified": bool(res["gate"].get("certified", False)), "error": res.get("error")}
    wall = time.perf_counter() - wall0
    return per, pub, first_res, meta, wall


# ---- process-level parallelism ("WxT" configs)

_W: dict = {}


def _winit(threads: int, paths: dict, thin: str = "auto", ccl: str = "default"):
    import cv2 as _cv
    _cv.setNumThreads(threads)
    from prohori import measure as _m
    install_thinning(_m, thin, ccl)
    _W["m"] = _m
    _W["blobs"] = {n: Path(p).read_bytes() for n, p in paths.items()}


def _wtask(name: str):
    rec, _ = one_frame(_W["m"], _W["blobs"][name])
    return name, rec


def run_config(spec: str, inputs, reps: int, warm_names: list[str], thin: str = "auto", ccl: str = "default") -> dict:
    """spec 'WxT': W worker processes, each with cv2.setNumThreads(T).  Returns throughput and per-frame latency."""
    W, T = (int(x) for x in spec.split("x"))
    paths = {n: str(p) for n, p in inputs}
    names = [n for n, _ in inputs]
    from concurrent.futures import ProcessPoolExecutor
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(W, mp_context=ctx, initializer=_winit, initargs=(T, paths, thin, ccl)) as pool:
        list(pool.map(_wtask, warm_names * max(1, 2 * W), chunksize=1))  # warm every worker (raises if a worker crashes)
        list(pool.map(_wtask, names, chunksize=1))                       # one full warm pass
        tasks = names * reps
        t0 = time.perf_counter()
        out = list(pool.map(_wtask, tasks, chunksize=1))
        wall = time.perf_counter() - t0
    per_img: dict[str, list] = {}
    for n, rec in out:
        per_img.setdefault(n, []).append(rec["e2e"])
    e2e = np.array([rec["e2e"] for _, rec in out])
    an = np.array([rec["analyze"] for _, rec in out])
    return {"spec": spec, "workers": W, "threads": T, "frames": len(tasks), "wall_s": wall, "fps": len(tasks) / wall,
            "e2e_ms": summarize(e2e), "analyze_ms": summarize(an), "per_image_e2e_ms": per_img}


# --------------------------------------------------------------------------------------------- trace pass

class Recorder:
    def __init__(self):
        self.ms: dict[str, list] = {}
        self.calls: list[str] = []
        self.m_scalars: list[dict] = []
        self.on = False

    def add(self, name: str, dt_ms: float, out, call_name: str | None = None) -> None:
        e = self.ms.setdefault(name, [0.0, 0])
        e[0] += dt_ms
        e[1] += 1
        self.calls.append(f"{call_name or name}:{sha(out, 8)}")

    def reset(self):
        self.ms, self.calls, self.m_scalars = {}, [], []


class CvProxy:
    """Stands in for the `cv2` module inside prohori.measure: every OpenCV function call is timed (exclusive of the
    fingerprinting) and its output fingerprinted.  Constants and classes pass straight through."""

    def __init__(self, mod, prefix: str, rec: Recorder):
        object.__setattr__(self, "_mod", mod)
        object.__setattr__(self, "_prefix", prefix)
        object.__setattr__(self, "_rec", rec)
        object.__setattr__(self, "_cache", {})

    def __getattr__(self, name):
        c = self._cache
        if name in c:
            return c[name]
        obj = getattr(self._mod, name)
        full = self._prefix + name
        if isinstance(obj, types.ModuleType):
            val = CvProxy(obj, full + ".", self._rec)
        elif isinstance(obj, type) or not callable(obj):
            val = obj
        else:
            rec = self._rec
            nm = "py.thinning_shim" if getattr(obj, "_is_py_shim", False) else "cv2." + full

            def wrapper(*a, _o=obj, _n=nm, _c="cv2." + full, **k):
                t = time.perf_counter_ns()
                out = _o(*a, **k)
                dt = (time.perf_counter_ns() - t) / 1e6
                if rec.on:
                    rec.add(_n, dt, out, _c)
                return out
            val = wrapper
        c[name] = val
        return val


class DetProxy:
    """Times CharucoDetector.detectBoard (a method of a class, invisible to CvProxy) and fingerprints its output."""

    def __init__(self, det, rec: Recorder):
        self._det, self._rec = det, rec

    def detectBoard(self, *a, **k):
        t = time.perf_counter_ns()
        out = self._det.detectBoard(*a, **k)
        dt = (time.perf_counter_ns() - t) / 1e6
        if self._rec.on:
            self._rec.add("cv2.aruco.CharucoDetector.detectBoard", dt, out)
        return out


def _scalars(m: dict) -> dict:
    """Unrounded scalars of the internal per-crack measurement dict (hex), arrays by fingerprint + extremes."""
    o = {}
    for k, v in m.items():
        if isinstance(v, (float, np.floating)):
            o[k] = fhex(v)
        elif isinstance(v, (int, np.integer)) and not isinstance(v, bool):
            o[k] = repr(int(v))
        elif isinstance(v, dict) and k == "quality":
            o.update({f"quality.{a}": fhex(b) if isinstance(b, (float, np.floating)) else repr(b)
                      for a, b in v.items()})
    lm = np.asarray(m["local_mm"], float)
    o["local_mm.sha"] = sha(lm, 16)
    o["local_mm.n"] = repr(int(lm.size))
    o["local_mm.min"], o["local_mm.max"], o["local_mm.sum"] = fhex(lm.min()), fhex(lm.max()), fhex(lm.sum())
    o["poly_b.sha"] = sha(m["poly_b"], 16)
    return o


def trace_pass(measure, blobs: dict, reps: int = 2) -> dict:
    """Instrumented pass: per-image per-function time and output fingerprints, plus every public result."""
    rec = Recorder()
    orig_cv2 = measure.cv2
    orig_py = {n: getattr(measure, n) for n in PY_WRAP}
    orig_assess = measure._gate.assess
    measure.cv2 = CvProxy(orig_cv2, "", rec)
    orig_det = measure._detector()
    measure._cache["det"] = DetProxy(orig_det, rec)

    def wrap_py(name, fn):
        def w(*a, **k):
            t = time.perf_counter_ns()
            out = fn(*a, **k)
            dt = (time.perf_counter_ns() - t) / 1e6
            if rec.on:
                rec.add("py." + name, dt, out)
                if name == "_measure_roi" and out is not None:
                    rec.m_scalars.append(_scalars(out))
            return out
        return w

    def assess(*a, **k):
        t = time.perf_counter_ns()
        out = orig_assess(*a, **k)
        dt = (time.perf_counter_ns() - t) / 1e6
        if rec.on:
            rec.add("py.gate.assess", dt, out)
        return out

    for n in PY_WRAP:
        setattr(measure, n, wrap_py(n, orig_py[n]))
    measure._gate.assess = assess
    out = {"ms": {}, "calls": {}, "widths": {}, "m_scalars": {}, "public_sha": {}, "analyze_ms": {}}
    try:
        for r in range(reps):
            for n, raw in blobs.items():
                img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                if r == 0:
                    out["decode_sha"] = out.get("decode_sha", {})
                    out["decode_sha"][n] = sha(img, 16)
                rec.reset()
                rec.on = True
                t_a = time.perf_counter_ns()
                res = measure.analyze(img)
                t_b = time.perf_counter_ns()
                rec.on = False
                out["analyze_ms"].setdefault(n, []).append((t_b - t_a) / 1e6)
                if r == 0:
                    pub = {k: v for k, v in res.items() if k != "timing_ms"}
                    out["widths"][n] = flatten(pub)
                    out["public_sha"][n] = sha(pub, 16)
                    out["calls"][n] = list(rec.calls)
                    out["m_scalars"][n] = list(rec.m_scalars)
                out["ms"].setdefault(n, []).append({k: v[:] for k, v in rec.ms.items()})
    finally:
        measure._cache["det"] = orig_det
        measure.cv2 = orig_cv2
        for n, f in orig_py.items():
            setattr(measure, n, f)
        measure._gate.assess = orig_assess
    return out


def amdahl(tr: dict) -> dict:
    """Share of analyze() wall time (trace pass) spent inside OpenCV calls vs Python/numpy, per rep.
    cv2 calls are leaves (no timed cv2 call is made from inside another timed cv2 call), so their times add up."""
    reps = len(next(iter(tr["ms"].values())))
    out = {"analyze_ms": [], "cv2_ms": [], "other_ms": []}
    for r in range(reps):
        tot_a = sum(tr["analyze_ms"][n][r] for n in tr["ms"])
        cv = 0.0
        for n, lst in tr["ms"].items():
            cv += sum(ms for f, (ms, c) in lst[r].items() if f.startswith("cv2."))
        out["analyze_ms"].append(tot_a)
        out["cv2_ms"].append(cv)
        out["other_ms"].append(tot_a - cv)
    return out


def profile_summary(tr: dict) -> dict:
    """{function: {'ms': [per-rep total over all images], 'calls': n per rep}}"""
    reps = len(next(iter(tr["ms"].values())))
    agg: dict[str, dict] = {}
    for r in range(reps):
        tot: dict[str, list] = {}
        for n, lst in tr["ms"].items():
            for f, (ms, c) in lst[r].items():
                e = tot.setdefault(f, [0.0, 0])
                e[0] += ms
                e[1] += c
        for f, (ms, c) in tot.items():
            a = agg.setdefault(f, {"ms": [], "calls": c})
            a["ms"].append(ms)
    return agg


# --------------------------------------------------------------------------------------------- microbench

def _synth_scene(scale: float = 1.0):
    """Deterministic, build-independent inputs at the sizes the pipeline uses (12 MP phone photo => rectified canvas
    and tight full-resolution ROIs).  Everything is generated with numpy only."""
    rng = np.random.default_rng(20261025)
    H, W = int(3072 * scale), int(4096 * scale)
    yy, xx = np.mgrid[0:H, 0:W]
    base = 190 + 25 * np.sin(xx / 700.0) * np.cos(yy / 900.0) + rng.normal(0, 2.5, (H, W))
    grey = np.clip(base, 0, 255).astype(np.uint8)
    bgr = np.stack([grey, np.clip(grey.astype(int) - 6, 0, 255).astype(np.uint8),
                    np.clip(grey.astype(int) - 14, 0, 255).astype(np.uint8)], -1)
    # canvas-sized rectified page (S ~ 6 px/mm => 1273 x 1800)
    Hc, Wc = int(1800 * scale), int(1273 * scale)
    can = np.clip(200 + 12 * np.sin(np.mgrid[0:Hc, 0:Wc][1] / 90.0) + rng.normal(0, 3, (Hc, Wc)), 0, 255).astype(np.uint8)
    # crack-like mask: sine path 3-5 px wide on the canvas, and a thicker one on the ROI
    mask = np.zeros((Hc, Wc), np.uint8)
    for x in range(40, Wc - 40):
        y = int(Hc * 0.5 + 120 * math.sin(x / 150.0))
        mask[y - 2:y + 3, x] = 255
    # ROI (S ~ 20 px/mm, 100 mm x 6 mm corridor => 2000 x 120 would be small; use 2000 x 500 incl. margin)
    Hr, Wr = int(500 * scale), int(2000 * scale)
    roi = np.clip(180 + rng.normal(0, 4, (Hr, Wr)), 0, 255).astype(np.uint8)
    xs = np.arange(60, Wr - 60)
    ys = (Hr / 2 + 40 * np.sin(xs / 200.0)).astype(int)
    for dy in range(-6, 7):
        roi[np.clip(ys + dy, 0, Hr - 1), xs] = 40
    roi = cv2.GaussianBlur(roi, (0, 0), 2.0) if False else roi  # blur omitted: keep input build independent
    mroi = (roi < 100).astype(np.uint8) * 255
    return {"grey": grey, "bgr": bgr, "canvas": can, "cmask": mask, "roi": roi, "mroi": mroi,
            "linf": (roi.astype(np.float32) / 255.0)}


def micro_cases(scale: float = 1.0, real_jpeg: bytes | None = None):
    """[(name, size description, callable(), repeat count)]; each callable returns the output to fingerprint."""
    from prohori import measure as M
    s = _synth_scene(scale)
    grey, bgr, can, cmask, roi, mroi, linf = (s[k] for k in ("grey", "bgr", "canvas", "cmask", "roi", "mroi", "linf"))
    H, W = grey.shape
    Hc, Wc = can.shape
    Hr, Wr = roi.shape
    Hm = np.array([[1.02, 0.03, 12.0], [-0.02, 0.98, 20.0], [2e-6, 1e-6, 1.0]])
    small = cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_NEAREST)  # build-independent enough; hashed
    D = linf.astype(np.float32)
    kk = M._odd(0.8 * 20)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (kk, kk))
    ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (M._odd(3), M._odd(3)))
    n_st, nt = 220, 71
    mx = (np.linspace(100, Wr - 100, n_st)[:, None] + 0 * np.linspace(0, 1, nt)[None, :]).astype(np.float32)
    my = (Hr / 2 + np.linspace(-20, 20, nt)[None, :] + 0 * np.linspace(0, 1, n_st)[:, None]).astype(np.float32)
    crop = (mroi[max(0, Hr // 2 - 100):Hr // 2 + 100, 60:Wr - 60]).copy()
    crop = cv2.copyMakeBorder(crop, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    pts_b = np.array([[x, y] for x in range(0, 140, 5) for y in (0, 20, 40, 60)], float)
    pts_i = np.stack([pts_b[:, 0] * 8.1 + 400 + 0.01 * pts_b[:, 1] * pts_b[:, 0], pts_b[:, 1] * 8.1 + 300], 1)
    cases = [
        ("imdecode_jpeg_12MP", f"{W}x{H}", (lambda: cv2.imdecode(np.frombuffer(real_jpeg, np.uint8), cv2.IMREAD_COLOR))
         if real_jpeg else (lambda: cv2.imdecode(cv2.imencode('.jpg', bgr[::4, ::4])[1], cv2.IMREAD_COLOR)), 3),
        ("cvtColor_BGR2GRAY", f"{W}x{H}x3", lambda: cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 6),
        ("resize_AREA_grey_x0.5", f"{W}x{H}", lambda: cv2.resize(grey, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), 6),
        ("resize_AREA_grey_x0.3", f"{W}x{H}", lambda: cv2.resize(grey, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_AREA), 6),
        ("resize_LINEAR_f32_up", f"{Wc // 4}x{Hc // 4}->{Wc}x{Hc}", lambda: cv2.resize(D[:Hc // 4, :Wc // 4], (Wc, Hc), interpolation=cv2.INTER_LINEAR), 10),
        ("warpPerspective_LINEAR_u8", f"{small.shape[1]}x{small.shape[0]}->{Wc}x{Hc}", lambda: cv2.warpPerspective(small, Hm, (Wc, Hc), flags=cv2.INTER_LINEAR), 10),
        ("warpPerspective_NEAREST_u8", f"{small.shape[1]}x{small.shape[0]}->{Wc}x{Hc}", lambda: cv2.warpPerspective(np.full(small.shape, 255, np.uint8), Hm, (Wc, Hc), flags=cv2.INTER_NEAREST), 10),
        ("warpPerspective_CUBIC_u8_ROI", f"{W}x{H}->{Wr}x{Hr}", lambda: cv2.warpPerspective(grey, Hm, (Wr, Hr), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0), 6),
        ("warpPerspective_NEAREST_u8_ROI_valid", f"{W}x{H}->{Wr}x{Hr}", lambda: cv2.warpPerspective(np.full(grey.shape, 255, np.uint8), Hm, (Wr, Hr), flags=cv2.INTER_NEAREST), 6),
        ("erode_7x7_u8", f"{Wc}x{Hc}", lambda: cv2.erode(cmask, np.ones((7, 7), np.uint8)), 10),
        ("erode_5x5_u8_ROI", f"{Wr}x{Hr}", lambda: cv2.erode(mroi, np.ones((5, 5), np.uint8)), 10),
        ("GaussianBlur_u8_sigma0.7", f"{Wc}x{Hc}", lambda: cv2.GaussianBlur(can, (0, 0), 0.7), 10),
        ("GaussianBlur_f32_sigma4", f"{Wr}x{Hr}", lambda: cv2.GaussianBlur(D, (0, 0), 4.0), 8),
        ("GaussianBlur_f32_sigma3_sigmaY0", f"{nt}x{n_st}", lambda: cv2.GaussianBlur(D[:n_st, :nt], (0, 0), sigmaX=3.0, sigmaY=0), 40),
        ("dilate_f32_rect", f"{Wr}x{Hr} k={kk}", lambda: cv2.dilate(D, ker), 6),
        ("medianBlur_u8_k15", f"{Wc // 4}x{Hc // 4}", lambda: cv2.medianBlur(can[::4, ::4].copy(), 15), 10),
        ("morphologyEx_close_ellipse", f"{Wc}x{Hc}", lambda: cv2.morphologyEx(cmask, cv2.MORPH_CLOSE, ell), 10),
        ("connectedComponentsWithStats", f"{Wc}x{Hc}", lambda: cv2.connectedComponentsWithStats(cmask, connectivity=8), 10),
        ("ximgproc_thinning", f"{crop.shape[1]}x{crop.shape[0]}", lambda: M.cv2.ximgproc.thinning(crop), 6),
        ("distanceTransform_L2_precise", f"{crop.shape[1]}x{crop.shape[0]}", lambda: cv2.distanceTransform(crop, cv2.DIST_L2, cv2.DIST_MASK_PRECISE), 6),
        ("remap_f32_LINEAR_profiles", f"{nt}x{n_st} from {Wr}x{Hr}", lambda: cv2.remap(D, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), 40),
        ("findContours_CCOMP", f"{crop.shape[1]}x{crop.shape[0]}", lambda: cv2.findContours(crop, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE), 20),
        ("Laplacian_f32", f"{Wc}x{Hc}", lambda: cv2.Laplacian(can, cv2.CV_32F), 10),
        ("findHomography_RANSAC", f"{len(pts_b)} pts", lambda: cv2.findHomography(pts_b, pts_i, cv2.RANSAC, 0.6), 100),
        ("pipeline_bg_map_f32", f"{Wr}x{Hr}", lambda: M._bg_map(D, int(6.0 * 20)), 4),
    ]
    return cases, s


def micro_detect_case(real_jpeg: bytes):
    from prohori import measure as M
    grey = cv2.cvtColor(cv2.imdecode(np.frombuffer(real_jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)
    return ("pipeline_detect_board", f"{grey.shape[1]}x{grey.shape[0]} (real photo)", lambda: M._detect_board(grey), 4)


def micro_isolated(real_path, scale: float, threads: int, thin: str) -> dict:
    """Run every microbench case in its own child process at `threads` threads; a crashing case is recorded as an error."""
    names = [c[0] for c in micro_cases(scale, None)[0]] + (["pipeline_detect_board"] if real_path else [])
    out = {}
    for n in names:
        cmd = [sys.executable, str(Path(__file__).resolve()), "microcase", "--case", n, "--threads", str(threads),
               "--scale", str(scale), "--thinning", thin] + (["--jpeg", str(real_path)] if real_path else [])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and r.stdout.strip():
                out[n] = json.loads(r.stdout.strip().splitlines()[-1])
            else:
                tail = (r.stderr.strip().splitlines() or ["?"])[-1][:200]
                out[n] = {"size": "?", "error": f"child rc={r.returncode} (crash): {tail}"}
        except Exception as e:
            out[n] = {"size": "?", "error": f"{type(e).__name__}: {e}"}
    return out


def cmd_microcase(a) -> int:
    from prohori import measure
    install_thinning(measure, a.thinning)
    cv2.setNumThreads(a.threads)
    real = Path(a.jpeg).read_bytes() if a.jpeg else None
    cases, _ = micro_cases(a.scale, real)
    if real:
        cases.append(micro_detect_case(real))
    for name, size, fn, rep in cases:
        if name != a.case:
            continue
        o = fn()
        fn()
        ts = []
        for _ in range(rep):
            t = time.perf_counter_ns()
            fn()
            ts.append((time.perf_counter_ns() - t) / 1e6)
        print(json.dumps({"size": size, "ms": ts, "p50": pct(ts, 50), "min": float(min(ts)), "out_sha": sha(o, 16)}))
        return 0
    return 3


def run_micro(real_jpeg: bytes | None, scale: float, threads_list: list[int]) -> dict:
    out = {}
    cases, scene = micro_cases(scale, real_jpeg)
    if real_jpeg:
        cases.append(micro_detect_case(real_jpeg))
    inp_sha = {k: sha(v, 12) for k, v in scene.items()}
    for T in threads_list:
        cv2.setNumThreads(T)
        res = {}
        for name, size, fn, rep in cases:
            try:
                o = fn()  # warm + output fingerprint
                fn()
                ts = []
                for _ in range(rep):
                    t = time.perf_counter_ns()
                    fn()
                    ts.append((time.perf_counter_ns() - t) / 1e6)
                res[name] = {"size": size, "ms": ts, "p50": pct(ts, 50), "min": float(min(ts)), "out_sha": sha(o, 16)}
            except Exception as e:
                res[name] = {"size": size, "error": f"{type(e).__name__}: {e}"}
        out[str(T)] = res
    out["input_sha"] = inp_sha
    return out


# --------------------------------------------------------------------------------------------- run

def cmd_run(a) -> int:
    from prohori import measure
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = collect_inputs(a.input, a.stride)
    if not inputs:
        print("no inputs", file=sys.stderr)
        return 2
    sweep_inputs = inputs[::a.sweep_stride]
    env = capture_env()
    dry = env["machine"] not in ("aarch64", "arm64")
    print(f"[{a.label}] cv2 {env['cv2_version']} from {env['cv2_file']}  threads={env['cv2_num_threads_default']} "
          f"inputs={len(inputs)} {'(DRY RUN, not Graviton)' if dry else ''}", flush=True)
    thin_used = install_thinning(measure, a.thinning, a.ccl)
    print(f"[{a.label}] ximgproc.thinning: {thin_used}", flush=True)
    if a.threads:
        cv2.setNumThreads(a.threads)
    head_threads = cv2.getNumThreads()
    blobs = load_bytes(inputs)
    doc = {"schema": SCHEMA, "thinning": thin_used, "ccl": a.ccl, "label": a.label, "dry_run": dry, "env": env, "inputs": manifest(inputs),
           "protocol": {"reps": a.reps, "warmup": a.warmup, "stride": a.stride, "sweep": a.sweep,
                        "sweep_reps": a.sweep_reps, "sweep_stride": a.sweep_stride, "trace_reps": a.trace_reps,
                        "micro": a.micro, "stage_doc": STAGE_DOC}}
    # --- headline: un-instrumented, default threads
    t0 = time.time()
    per, pub, first, meta, wall = timed_passes(measure, blobs, a.reps, a.warmup)
    print(f"[{a.label}] headline: {len(blobs)} frames x {a.reps} reps in {wall:.1f}s "
          f"({len(blobs) * a.reps / wall:.2f} fps in-process)", flush=True)
    doc["headline"] = {"threads": head_threads, "per_image": per, "frames": len(blobs) * a.reps, "wall_s": wall,
                       "fps": len(blobs) * a.reps / wall, "meta": meta,
                       "public_sha_per_rep": {n: sorted(s) for n, s in pub.items()},
                       "intra_run_deterministic": all(len(s) == 1 for s in pub.values())}
    # --- sweep of WxT configs
    doc["sweep"] = {}
    for spec in [s for s in a.sweep.split(",") if s]:
        t = time.time()
        try:
            r = run_config(spec, sweep_inputs, a.sweep_reps, [sweep_inputs[0][0]], a.thinning, a.ccl)
        except Exception as e:  # keep going: a failed config is data
            r = {"spec": spec, "error": f"{type(e).__name__}: {e}"}
        doc["sweep"][spec] = r
        if "fps" in r:
            print(f"[{a.label}] sweep {spec}: {r['fps']:.2f} fps  e2e p50 {r['e2e_ms']['p50']:.0f} ms "
                  f"p95 {r['e2e_ms']['p95']:.0f} ms  ({time.time() - t:.0f}s)", flush=True)
        else:
            print(f"[{a.label}] sweep {spec}: FAILED {r['error']}", flush=True)
    cv2.setNumThreads(head_threads)
    # --- microbench: single thread in process; more threads one case per child process (a crash is a result, not an abort)
    if a.micro:
        real_path = next((p for n, p in inputs if n.startswith(("raw/", "real/"))), None)
        real = real_path.read_bytes() if real_path else None
        doc["micro"] = run_micro(real, a.micro_scale, [1])
        nthr = env["cv2_num_threads_default"]
        if a.micro_mt and nthr > 1:
            doc["micro"][str(nthr)] = micro_isolated(real_path, a.micro_scale, nthr, doc["thinning"])
        cv2.setNumThreads(head_threads)  # run_micro leaves the last thread count set
        print(f"[{a.label}] micro done", flush=True)
    # --- trace pass (per-function timing + fingerprints + hex dump)
    tr_blobs = {n: blobs[n] for n, _ in inputs[::a.trace_stride]} if a.trace_reps else {}
    if tr_blobs:
        tr = trace_pass(measure, tr_blobs, a.trace_reps)
        doc["profile"] = profile_summary(tr)
        doc["amdahl"] = amdahl(tr)
        doc["profile_images"] = len(tr_blobs)
        print(f"[{a.label}] trace done ({len(tr_blobs)} images)", flush=True)
        inv = {"widths": tr["widths"], "m_scalars": tr["m_scalars"], "calls": tr["calls"],
               "public_sha": tr["public_sha"], "decode_sha": tr["decode_sha"]}
        # the full-resolution dump always covers ALL inputs: public results from the headline pass
        for n, res in first.items():
            if n not in inv["widths"]:
                pub_res = {k: v for k, v in res.items() if k != "timing_ms"}
                inv["widths"][n] = flatten(pub_res)
                inv["public_sha"][n] = sha(pub_res, 16)
        doc["invariance"] = {"canonical_sha256": canonical_sha(inv["widths"]), "n_inputs": len(inv["widths"]),
                             "m_sha256": canonical_sha(inv["m_scalars"]),
                             "calls_sha256": canonical_sha({k: v for k, v in inv["calls"].items()})}
        with gzip.open(out / f"{a.label}.inv.json.gz", "wt", encoding="utf-8") as f:
            json.dump(inv, f, separators=(",", ":"), sort_keys=True)
    (out / f"{a.label}.bench.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    (out / f"{a.label}.build_info.txt").write_text(env["cv2_build_information"], encoding="utf-8")
    (out / f"{a.label}.env.json").write_text(json.dumps({k: v for k, v in env.items() if k != "cv2_build_information"},
                                                         indent=1), encoding="utf-8")
    print(f"[{a.label}] done in {time.time() - t0:.0f}s -> {out}", flush=True)
    return 0


# --------------------------------------------------------------------------------------------- compare

def _load(p: str):
    doc = json.loads(Path(p).read_text(encoding="utf-8"))
    inv = None
    ip = Path(p).with_name(Path(p).name.replace(".bench.json", ".inv.json.gz"))
    if ip.exists():
        with gzip.open(ip, "rt", encoding="utf-8") as f:
            inv = json.load(f)
    return doc, inv


def stage_table(da: dict, db: dict, n_boot: int = 2000) -> list[dict]:
    """Rows: per stage, A and B p50/p95/mean (ms, pooled over image x rep) and speedup A/B with 95 % CIs."""
    pa, pb = da["headline"]["per_image"], db["headline"]["per_image"]
    names = [n for n in pa if n in pb]
    rows = []
    for s in STAGES:
        A = [np.asarray(pa[n][s], float) for n in names]
        B = [np.asarray(pb[n][s], float) for n in names]
        row = {"stage": s, "n_images": len(names)}
        for tag, X in (("a", A), ("b", B)):
            allv = np.concatenate(X)
            row[f"{tag}_mean"], row[f"{tag}_p50"], row[f"{tag}_p95"] = float(allv.mean()), pct(allv, 50), pct(allv, 95)
        for nm, st in (("mean", np.mean), ("p50", lambda v: np.percentile(v, 50)), ("p95", lambda v: np.percentile(v, 95))):
            pt, lo, hi = boot_ratio(A, B, st, n_boot)
            row[f"x_{nm}"], row[f"x_{nm}_lo"], row[f"x_{nm}_hi"] = pt, lo, hi
        rows.append(row)
    return rows


def _fnum(v):
    """float64 from a hex dump leaf, None for fingerprints / ints / strings."""
    if isinstance(v, str) and (v.startswith(("0x", "-0x")) or v in ("nan", "inf", "-inf")):
        return float.fromhex(v) if v.startswith(("0x", "-0x")) else float(v)
    return None


MM_ESTIMATORS = ("dt", "profile_core", "profile_ink", "fwhm", "profile")


def is_mm_field(k: str) -> bool:
    """Fields whose unit is mm: *_mm and the width estimator columns (not the dimensionless wt_core / q_core)."""
    return k.endswith("_mm") or any(k.endswith(f".estimators.{e}") for e in MM_ESTIMATORS)


def _rekey(flat: dict) -> dict:
    """Index-based crack keys (cracks.3.width_mm) -> id-based (cracks.S4.width_mm), so builds that find a different
    number of cracks in one frame are still compared crack by crack."""
    ids = {k.split(".")[1]: v.strip("'") for k, v in flat.items()
           if k.startswith("cracks.") and k.endswith(".id") and k.count(".") == 2}
    out = {}
    for k, v in flat.items():
        if k.startswith("cracks."):
            _, i, rest = k.split(".", 2)
            k = f"cracks.{ids.get(i, i)}.{rest}"
        out[k] = v
    return out


def _rekey_all(widths: dict) -> dict:
    return {n: _rekey(f) for n, f in widths.items()}


def flip_details(wa: dict, wb: dict, flips: list) -> list[dict]:
    """For every crack whose certification flipped: the gate score (risk_ratio = predicted |error|/tolerance) in each
    build against the certification threshold exp(theta), the reasons, and the width."""
    try:
        from prohori import gate as _g
        P = _g.load_params()
    except Exception:
        P = None
    out = []
    for n, k, va, vb in flips:
        if not k.endswith(".certified") or not k.startswith("cracks."):
            continue
        base = k[:-len("certified")]
        lvl = (wa[n].get("gate.level") or "").strip("'")
        thr = None
        if P is not None and lvl in P.get("levels", {}):
            thr = float(np.exp(P["levels"][lvl]["theta"]))
        rs = lambda w: sorted(v.strip("'") for kk, v in w[n].items() if kk.startswith(base + "reasons."))
        out.append({"input": n, "crack": k.split(".")[1], "certified": [va, vb],
                    "risk_ratio": [_fnum(wa[n].get(base + "risk_ratio")), _fnum(wb[n].get(base + "risk_ratio"))],
                    "threshold": thr, "level": lvl, "reasons": [rs(wa), rs(wb)],
                    "width_mm": [_fnum(wa[n].get(base + "width_mm")), _fnum(wb[n].get(base + "width_mm"))]})
    return out


def truth_errors(wa: dict, wb: dict, names: list[str]) -> dict:
    """Width error against the printed ground truth (cracks that carry true_width_mm), for both builds, so a
    difference between builds can be judged against the measurement error itself."""
    ea, eb, ca, cb_ = [], [], 0, 0
    for n in names:
        fa, fb = wa[n], wb[n]
        for k in fa:
            if not k.endswith(".width_mm") or k.endswith(".true_width_mm"):
                continue
            kt = k[:-len("width_mm")] + "true_width_mm"
            t = _fnum(fa.get(kt))
            if t is None or k not in fb:
                continue
            x, y = _fnum(fa[k]), _fnum(fb[k])
            if x is None or y is None:
                continue
            ea.append(x - t)
            eb.append(y - t)
            kc = k[:-len("width_mm")] + "certified"
            ca += fa.get(kc) == "True"
            cb_ += fb.get(kc) == "True"
    if not ea:
        return {}
    ea, eb = np.array(ea), np.array(eb)
    d = np.abs(eb) - np.abs(ea)
    rng = np.random.default_rng(7)
    bm = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    st = lambda e: {"mean_abs": float(np.abs(e).mean()), "median_abs": float(np.median(np.abs(e))),
                    "p95_abs": float(np.percentile(np.abs(e), 95)), "bias": float(e.mean())}
    return {"n": int(len(ea)), "a": st(ea), "b": st(eb), "certified": [int(ca), int(cb_)],
            "mean_abs_err_b_minus_a": float(d.mean()),
            "ci95": [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))]}


def invariance_report(da, ia, db, ib, tol_mm: float = 0.0) -> dict:
    """Verdict on numerical identity between two runs (A, B)."""
    rep = {"available": ia is not None and ib is not None}
    if not rep["available"]:
        return rep
    wa, wb = _rekey_all(ia["widths"]), _rekey_all(ib["widths"])
    names = sorted(set(wa) & set(wb))
    rep["n_inputs"] = len(names)
    rep["canonical_sha256"] = [da["invariance"]["canonical_sha256"], db["invariance"]["canonical_sha256"]]
    rep["identical"] = all(wa[n] == wb[n] for n in names) and set(wa) == set(wb)
    diffs, max_mm, max_any, max_w = [], 0.0, 0.0, 0.0
    ncols = 0
    for n in names:
        fa, fb = wa[n], wb[n]
        for k in sorted(set(fa) | set(fb)):
            ncols += 1
            va, vb = fa.get(k), fb.get(k)
            if va == vb:
                continue
            fa_, fb_ = _fnum(va), _fnum(vb)
            d = abs(fa_ - fb_) if fa_ is not None and fb_ is not None else None
            diffs.append((n, k, va, vb, d))
            if d is not None and not math.isnan(d):
                max_any = max(max_any, d)
                if is_mm_field(k):
                    max_mm = max(max_mm, d)
                    if k.endswith(".width_mm"):
                        max_w = max(max_w, d)
    wd, flips, struct = [], [], []
    for n in names:
        fa, fb = wa[n], wb[n]
        for k in fa:
            if k.endswith(".width_mm") and k in fb:
                x, y = _fnum(fa[k]), _fnum(fb[k])
                if x is not None and y is not None:
                    wd.append(abs(x - y))
            if k.endswith(".certified") and fa[k] != fb.get(k):
                flips.append((n, k, fa[k], fb.get(k)))
        if set(fa) != set(fb):
            ids = lambda f: {k.split(".")[1] for k in f if k.startswith("cracks.") and k.endswith(".id") and k.count(".") == 2}
            only_a, only_b = sorted(ids(fa) - ids(fb)), sorted(ids(fb) - ids(fa))
            if only_a or only_b:
                struct.append({"input": n, "cracks_only_in_a": only_a, "cracks_only_in_b": only_b})
    wd = np.array(wd) if wd else np.zeros(1)
    rep["n_cracks_compared"] = int(len(wd))
    rep["dw_max_mm"], rep["dw_p99_mm"], rep["dw_mean_mm"] = float(wd.max()), float(np.percentile(wd, 99)), float(wd.mean())
    rep["n_cracks_dw_nonzero"] = int((wd > 0).sum())
    rep["cert_flips"] = flips
    rep["crack_set_diffs"] = struct
    rep["truth"] = truth_errors(wa, wb, names)
    rep["flip_detail"] = flip_details(wa, wb, flips)
    rep["n_leaves_compared"] = ncols
    rep["n_leaf_diffs"] = len(diffs)
    rep["max_abs_diff_any"] = max_any
    rep["max_abs_diff_mm"] = max_mm
    rep["max_abs_width_mm"] = max_w
    rep["differing_inputs"] = sorted({d[0] for d in diffs})
    rep["worst"] = [list(d) for d in sorted(diffs, key=lambda d: -(d[4] or 0))[:10]]
    # unrounded internal measurement scalars (before the 4-decimal rounding of the public result)
    ma, mb = ia["m_scalars"], ib["m_scalars"]
    mm = 0.0
    mdiff = 0
    for n in sorted(set(ma) & set(mb)):
        for la, lb in zip(ma[n], mb[n]):
            for k in set(la) | set(lb):
                if la.get(k) != lb.get(k):
                    mdiff += 1
                    x, y = _fnum(la.get(k)), _fnum(lb.get(k))
                    if x is not None and y is not None and not math.isnan(x - y):
                        mm = max(mm, abs(x - y))
        if len(ma[n]) != len(mb[n]):
            mdiff += 1
    rep["internal_scalar_diffs"] = mdiff
    rep["internal_max_abs_diff"] = mm
    # OpenCV call fingerprints: which function first differs
    ca, cb = ia["calls"], ib["calls"]
    per_fn: dict[str, list] = {}
    first = None
    for n in sorted(set(ca) & set(cb)):
        la, lb = ca[n], cb[n]
        if len(la) != len(lb):
            per_fn.setdefault("<call sequence length>", [0, 0])[0] += 1
        for i, (x, y) in enumerate(zip(la, lb)):
            f = x.split(":")[0]
            e = per_fn.setdefault(f, [0, 0])
            e[1] += 1
            if x != y:
                e[0] += 1
                if first is None:
                    first = (n, i, f)
    rep["call_diffs"] = {f: v for f, v in per_fn.items() if v[0]}
    rep["call_totals"] = {f: v[1] for f, v in per_fn.items()}
    rep["first_divergence"] = first
    rep["decode_identical"] = ia.get("decode_sha") == ib.get("decode_sha")
    rep["deterministic_within_run"] = [da["headline"]["intra_run_deterministic"], db["headline"]["intra_run_deterministic"]]
    return rep


def verdict_text(rep: dict) -> str:
    if not rep.get("available"):
        return "invariance data missing"
    if rep["identical"]:
        return (f"BITWISE IDENTICAL: all {rep['n_leaves_compared']} numeric/string leaves of {rep['n_inputs']} results "
                f"(every crack width and estimator column, gate outputs, board corners) match as float64 hex; "
                f"max |dw| = 0 mm.")
    return (f"NOT bitwise identical: {rep['n_leaf_diffs']} of {rep['n_leaves_compared']} leaves differ in "
            f"{len(rep['differing_inputs'])} of {rep['n_inputs']} inputs; max |dw| of the reported crack width_mm = "
            f"{rep['max_abs_width_mm']:.3e} mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) "
            f"{rep['max_abs_diff_mm']:.3e} mm, over all numeric fields {rep['max_abs_diff_any']:.3e}.")


def micro_rows(da: dict, db: dict) -> list[dict]:
    rows = []
    if "micro" not in da or "micro" not in db:
        return rows
    for T in sorted([k for k in da["micro"] if k.isdigit()], key=int):
        if T not in db["micro"]:
            continue
        for name, ra in da["micro"][T].items():
            rb = db["micro"][T].get(name)
            if not rb or "ms" not in ra or "ms" not in rb:
                if rb and ("error" in ra or "error" in rb):
                    rows.append({"threads": int(T), "name": name, "size": ra.get("size", "?"), "a_ms": float("nan"),
                                 "b_ms": float("nan"), "x": float("nan"), "bit_exact": False,
                                 "error": f"A: {ra.get('error', 'ok')}; B: {rb.get('error', 'ok')}"})
                continue
            rows.append({"threads": int(T), "name": name, "size": ra["size"], "a_ms": ra["p50"], "b_ms": rb["p50"],
                         "x": ra["p50"] / rb["p50"], "bit_exact": ra["out_sha"] == rb["out_sha"]})
    return rows


def profile_rows(da: dict, db: dict) -> list[dict]:
    rows = []
    for f, ea in da.get("profile", {}).items():
        eb = db.get("profile", {}).get(f)
        if not eb:
            continue
        a, b = float(np.median(ea["ms"])), float(np.median(eb["ms"]))
        rows.append({"fn": f, "calls": ea["calls"], "a_ms": a, "b_ms": b, "x": a / b if b > 0 else float("nan")})
    return sorted(rows, key=lambda r: -r["a_ms"])


def _traced_names(doc: dict) -> list[str]:
    """Names of the frames the trace pass covered (every k-th input; k inferred from the count)."""
    names = list(doc["inputs"])
    n = doc.get("profile_images", len(names))
    k = 1
    while len(names[::k]) > n:
        k += 1
    return names[::k]


def amdahl_rows(da: dict, db: dict) -> dict:
    """Where the time goes: OpenCV-call time (timed inside the trace pass, per call, outside the fingerprinting) against
    the UN-instrumented analyze() time of the same frames from the headline run.  The trace pass's own analyze total
    is not used: it includes the cost of hashing every output."""
    if "amdahl" not in da or "amdahl" not in db:
        return {}

    def side(d):
        names = _traced_names(d)
        per = d["headline"]["per_image"]
        head = float(sum(np.mean(per[n]["analyze"]) for n in names if n in per))  # ms, all traced frames, un-instrumented
        cv = float(np.median(d["amdahl"]["cv2_ms"]))
        return head, cv, head - cv, len(names)
    ha, ca, oa, na = side(da)
    hb, cb_, ob, nb = side(db)
    out = {"frames": [na, nb], "a_analyze_ms": ha, "b_analyze_ms": hb, "a_cv2_ms": ca, "b_cv2_ms": cb_, "a_other_ms": oa,
           "b_other_ms": ob, "a_cv2_share": ca / ha, "b_cv2_share": cb_ / hb, "x_cv2": ca / cb_, "x_other": oa / ob,
           "x_analyze_traced": ha / hb}
    out["x_predicted_from_cv2"] = 1.0 / ((1 - out["a_cv2_share"]) + out["a_cv2_share"] / out["x_cv2"])
    out["x_if_cv2_twice_as_fast"] = 1.0 / ((1 - out["a_cv2_share"]) + out["a_cv2_share"] / 2.0)
    return out


def sweep_rows(da: dict, db: dict) -> list[dict]:
    rows = []
    for spec, ra in da.get("sweep", {}).items():
        rb = db.get("sweep", {}).get(spec)
        if not rb or "fps" not in ra or "fps" not in rb:
            continue
        rows.append({"spec": spec, "a_fps": ra["fps"], "b_fps": rb["fps"], "x_fps": rb["fps"] / ra["fps"],
                     "a_p50": ra["e2e_ms"]["p50"], "b_p50": rb["e2e_ms"]["p50"], "a_p95": ra["e2e_ms"]["p95"],
                     "b_p95": rb["e2e_ms"]["p95"]})
    return rows


def render_compare(la: str, lb: str, st, mi, pr, sw, rep, md: bool, am: dict | None = None) -> str:
    L = []
    L.append(f"### {la}  vs  {lb}   (speedup = {la} time / {lb} time; >1 means {lb} is faster)")
    L.append("")
    L.append("| stage | " + la + " p50 ms | " + lb + " p50 ms | " + la + " p95 ms | " + lb + " p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |")
    L.append("|---|---:|---:|---:|---:|---|---|---|")
    for r in st:
        f = lambda k: f"{r['x_' + k]:.3f} [{r['x_' + k + '_lo']:.3f}, {r['x_' + k + '_hi']:.3f}]"
        L.append(f"| {r['stage']} | {r['a_p50']:.1f} | {r['b_p50']:.1f} | {r['a_p95']:.1f} | {r['b_p95']:.1f} | "
                 f"{f('mean')} | {f('p50')} | {f('p95')} |")
    if am:
        L += ["", "Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):", "",
              f"| | {la} | {lb} | speedup {la}/{lb} |", "|---|---:|---:|---:|",
              f"| time inside OpenCV calls (ms, all frames) | {am['a_cv2_ms']:.0f} | {am['b_cv2_ms']:.0f} | {am['x_cv2']:.3f} |",
              f"| time in Python/numpy and the rest (analyze minus OpenCV, ms) | {am['a_other_ms']:.0f} | {am['b_other_ms']:.0f} | {am['x_other']:.3f} |",
              f"| analyze total (ms) | {am['a_analyze_ms']:.0f} | {am['b_analyze_ms']:.0f} | {am['x_analyze_traced']:.3f} |",
              f"| OpenCV share of analyze | {am['a_cv2_share'] * 100:.1f} % | {am['b_cv2_share'] * 100:.1f} % | |", "",
              f"Amdahl check: a {am['x_cv2']:.2f}x speedup of a {am['a_cv2_share'] * 100:.0f} % OpenCV share predicts "
              f"{am['x_predicted_from_cv2']:.3f}x end to end; even a 2x faster OpenCV would give only {am['x_if_cv2_twice_as_fast']:.2f}x."]
    if sw:
        L += ["", "Throughput / latency sweep (WxT = worker processes x cv2 threads each):", "",
              f"| config | {la} fps | {lb} fps | x fps | {la} e2e p50/p95 ms | {lb} e2e p50/p95 ms |",
              "|---|---:|---:|---:|---|---|"]
        for r in sw:
            L.append(f"| {r['spec']} | {r['a_fps']:.2f} | {r['b_fps']:.2f} | {r['x_fps']:.3f} | "
                     f"{r['a_p50']:.0f}/{r['a_p95']:.0f} | {r['b_p50']:.0f}/{r['b_p95']:.0f} |")
    if mi:
        L += ["", "Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):", "",
              f"| threads | call | size | {la} ms | {lb} ms | x | bit-exact |", "|---:|---|---|---:|---:|---:|---|"]
        for r in mi:
            if "error" in r:
                L.append(f"| {r['threads']} | {r['name']} | {r['size']} | - | - | - | FAILED: {r['error'][:110]} |")
                continue
            L.append(f"| {r['threads']} | {r['name']} | {r['size']} | {r['a_ms']:.3f} | {r['b_ms']:.3f} | {r['x']:.2f} | "
                     f"{'yes' if r['bit_exact'] else 'NO'} |")
    if pr:
        L += ["", "Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, "
                  "so use ratios only; py.* rows are inclusive):", "",
              f"| function | calls | {la} ms | {lb} ms | x |", "|---|---:|---:|---:|---:|"]
        for r in pr[:40]:
            L.append(f"| {r['fn']} | {r['calls']} | {r['a_ms']:.1f} | {r['b_ms']:.1f} | {r['x']:.2f} |")
    cv = [r for r in pr if r["fn"].startswith("cv2.")][:5]
    if cv:
        L += ["", f"Top 5 OpenCV calls by time in {la} (per-call speedup {la}/{lb}):", ""]
        L += [f"- {r['fn']}: {r['a_ms']:.0f} ms -> {r['b_ms']:.0f} ms over {r['calls']} calls, {r['x']:.2f}x" for r in cv]
    L += ["", "Accuracy invariance: " + verdict_text(rep)]
    if rep.get("available"):
        L.append(f"- crack width differences over {rep['n_cracks_compared']} cracks: max {rep['dw_max_mm']:.3e} mm, "
                 f"P99 {rep['dw_p99_mm']:.3e} mm, mean {rep['dw_mean_mm']:.3e} mm ({rep['n_cracks_dw_nonzero']} cracks differ "
                 f"at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): {len(rep['cert_flips'])}; "
                 f"frames where the set of detected cracks differs: {len(rep['crack_set_diffs'])} {rep['crack_set_diffs'][:4]}; U_ref = 0.009 mm.")
        for fd in rep.get("flip_detail", []):
            rr = fd["risk_ratio"]
            L.append(f"- certification flip {fd['input']} crack {fd['crack']}: certified {fd['certified'][0]} -> {fd['certified'][1]}, "
                     f"risk_ratio {rr[0]:.4f} -> {rr[1]:.4f} vs threshold "
                     f"{fd['threshold'] if fd['threshold'] is None else round(fd['threshold'], 4)} (level {fd['level']}); "
                     f"reasons {fd['reasons'][0]} -> {fd['reasons'][1]}; width {fd['width_mm'][0]} -> {fd['width_mm'][1]} mm")
        tr = rep.get("truth")
        if tr:
            L.append(f"- error vs printed ground truth over {tr['n']} cracks with a known width: {la} mean |e| "
                     f"{tr['a']['mean_abs']:.4f} mm (median {tr['a']['median_abs']:.4f}, P95 {tr['a']['p95_abs']:.4f}, bias "
                     f"{tr['a']['bias']:+.4f}); {lb} mean |e| {tr['b']['mean_abs']:.4f} mm (median {tr['b']['median_abs']:.4f}, "
                     f"P95 {tr['b']['p95_abs']:.4f}, bias {tr['b']['bias']:+.4f}); paired mean(|e_{lb}| - |e_{la}|) = "
                     f"{tr['mean_abs_err_b_minus_a']:+.5f} mm [95% CI {tr['ci95'][0]:+.5f}, {tr['ci95'][1]:+.5f}]; "
                     f"cracks certified {tr['certified'][0]} vs {tr['certified'][1]}")
        L.append(f"- canonical sha256: {la} {rep['canonical_sha256'][0][:16]}..., {lb} {rep['canonical_sha256'][1][:16]}...")
        L.append(f"- unrounded internal measurement scalars differing: {rep['internal_scalar_diffs']} "
                 f"(max |d| {rep['internal_max_abs_diff']:.3e})")
        L.append(f"- JPEG decode output identical: {rep['decode_identical']}; "
                 f"intra-run determinism (A, B): {rep['deterministic_within_run']}")
        if rep["call_diffs"]:
            L.append("- OpenCV calls whose output bytes differ (differing / total calls): " +
                     ", ".join(f"{f} {v[0]}/{rep['call_totals'].get(f, '?')}" for f, v in sorted(rep["call_diffs"].items())))
            L.append(f"- first divergence (input, call index, function): {rep['first_divergence']}")
        else:
            L.append("- every OpenCV function output in the pipeline is byte-identical across the two builds")
        if rep["worst"]:
            L.append("- worst leaf differences (input, field, A, B, |d|): " + "; ".join(str(w) for w in rep["worst"][:5]))
    return "\n".join(L)


def cmd_compare(a) -> int:
    da, ia = _load(a.a)
    db, ib = _load(a.b)
    st = stage_table(da, db, a.boot)
    mi, pr, sw = micro_rows(da, db), profile_rows(da, db), sweep_rows(da, db)
    am = amdahl_rows(da, db)
    rep = invariance_report(da, ia, db, ib)
    txt = render_compare(da["label"], db["label"], st, mi, pr, sw, rep, True, am)
    print(txt)
    if a.json:
        Path(a.json).write_text(json.dumps({"stages": st, "micro": mi, "profile": pr, "sweep": sw, "amdahl": am, "invariance": rep,
                                            "a": da["label"], "b": db["label"]}, indent=1, default=str), encoding="utf-8")
    if a.md:
        Path(a.md).write_text(txt + "\n", encoding="utf-8")
    return 0


def cmd_env(a) -> int:
    e = capture_env()
    e["cv2_build_information"] = e["cv2_build_information"][:400] + "..."
    print(json.dumps(e, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--input", action="append", required=True, help="kind=DIR (jpg/png); repeatable")
    r.add_argument("--stride", type=int, default=1, help="use every k-th file of each input dir")
    r.add_argument("--reps", type=int, default=5)
    r.add_argument("--warmup", type=int, default=1)
    r.add_argument("--sweep", default="", help="comma list of WxT configs, e.g. 1x1,1x2,1x4,2x1,4x1")
    r.add_argument("--sweep-reps", type=int, default=2)
    r.add_argument("--sweep-stride", type=int, default=1, help="sweep over every k-th input")
    r.add_argument("--threads", type=int, default=0, help="cv2.setNumThreads for the headline / trace / micro (0 = default)")
    r.add_argument("--micro", action="store_true")
    r.add_argument("--ccl", choices=["default", "bbdt"], default="default",
                   help="connected-components algorithm: bbdt avoids the COOL multithread heap corruption (labels/stats identical)")
    r.add_argument("--thinning", choices=["auto", "native", "shim"], default="auto",
                   help="cv2.ximgproc.thinning: native (needs contrib), shim (numpy Zhang-Suen, bit-exact), auto")
    r.add_argument("--micro-mt", action="store_true", help="also microbench at the default thread count, one case per child process")
    r.add_argument("--micro-scale", type=float, default=1.0)
    r.add_argument("--trace-reps", type=int, default=2, help="0 disables the trace pass (and the invariance dump)")
    r.add_argument("--trace-stride", type=int, default=1)
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--boot", type=int, default=2000)
    c.add_argument("--json")
    c.add_argument("--md")
    c.set_defaults(fn=cmd_compare)
    m = sub.add_parser("microcase")
    m.add_argument("--case", required=True)
    m.add_argument("--threads", type=int, default=1)
    m.add_argument("--scale", type=float, default=1.0)
    m.add_argument("--jpeg")
    m.add_argument("--thinning", default="auto")
    m.set_defaults(fn=cmd_microcase)
    e = sub.add_parser("env")
    e.set_defaults(fn=cmd_env)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
