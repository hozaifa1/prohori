"""Crack-width estimator evaluation harness (TickTick D18, part 1).

One harness scores a ``prohori.measure`` variant (a CFG override) on three independent sources of ground truth, with the
splits frozen BEFORE any tuning (``eval/runs/width_autoresearch/split.json``):

  panel   the real phone photos of the printed test panel (data/raw, truth = data/print/test_panel_ground_truth.json,
          i.e. the FULL printed stroke width, toner spread not corrected).  Split by photo group (burst frames of one
          scene stay together), about 60 / 40, fixed seed.
  synth   exact per-station widths of the photoreal renders (data/synth/v1), split by render id, 60 / 40.  Matching of a
          measured crack to the ground-truth crack follows eval/synth_validation.py.
  krk     krkCMd profiles through widthbench / measure._measure_roi (eval/width_krk.py): calibration / test halves are
          widthbench's own (alternate specimen images).

Because only the estimator changes between variants, board detection, rectification, the locator, specimen matching and
the ROI extraction are done once and cached (``measure._prepare``; pickles in eval/runs/width_autoresearch/cache).  A
variant then costs ``measure._finish`` only: the width estimator, packaging and the (frozen) certification gate.

Usage
    python eval/width_eval.py build [--workers 3]          # one-off: cache + split (no widths are looked at)
    python eval/width_eval.py run --name NAME [--cfg JSON] # TUNE metrics of a variant (never touches the test split)
    python eval/width_eval.py final                        # the one held-out TEST evaluation + report + figures

Metrics (METRICS section 1a): bias, MAE, P95, ratio, COV, MRE per width bin (< 0.5 mm, >= 0.5 mm, all), for all
measurements and for the ones the (frozen) gate certifies.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
from prohori import measure, synth  # noqa: E402

RUN = ROOT / "eval" / "runs" / "width_autoresearch"
CACHE = RUN / "cache"
SPLIT = RUN / "split.json"
RES = ROOT / "eval" / "results"
SYNTH_DIR = ROOT / "data" / "synth" / "v1"
RAW_DIR = ROOT / "data" / "raw"
SPLIT_SEED = 20261024
TUNE_FRAC = 0.6
MATCH_TOL_MM = 2.5


# ----------------------------------------------------------------------------- cache build

def _panel_group(name: str) -> str:
    """Burst frames of one scene share a group (IMG..._BURST000_COVER.jpg, IMG..._BURST001.jpg)."""
    return name.split("_BURST")[0].replace(".jpg", "")


def _build_panel(path: str):
    img = cv2.imread(path)  # applies EXIF orientation, as the service does
    res = measure._empty_result()
    ctx = None
    t = time.time()
    try:
        ctx = measure._prepare(img, True, res)
    except Exception as e:  # pragma: no cover
        res["error"] = f"{type(e).__name__}: {e}"
    name = Path(path).name
    out = {"name": name, "group": _panel_group(name), "res": res, "ctx": ctx, "prep_s": time.time() - t}
    with open(CACHE / f"panel_{Path(path).stem}.pkl", "wb") as f:
        pickle.dump(out, f, protocol=4)
    return name, 0 if ctx is None else len(ctx["items"])


def _build_synth(name: str):
    from scipy.spatial import cKDTree
    d = SYNTH_DIR
    gt = json.loads((d / f"{name}.json").read_text())
    img = cv2.imdecode(np.frombuffer((d / f"{name}.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    res = measure._empty_result()
    t = time.time()
    ctx = None
    try:
        ctx = measure._prepare(img, False, res)
    except Exception as e:  # pragma: no cover
        res["error"] = f"{type(e).__name__}: {e}"
    best = None
    n_false = 0
    if ctx is not None:
        cam = gt["camera"]
        R, _ = cv2.Rodrigues(np.array(cam["rvec"], float))
        C = np.array(cam["centre_mm"], float)
        K = np.array(cam["K"], float)
        dist = np.array(cam["dist_k1k2"], float)
        st = np.array(gt["crack"]["stations_mm"], float)
        tree = cKDTree(st[:, :2])
        ppms = [it["pm"] for it in ctx["items"]]
        for it in ctx["items"]:
            ip = measure._apply_h(ctx["Hinv"], it["sd"]["seed_b"])
            X, Y = synth._pixel_to_plane_exact(R, C, K, dist, ip[:, 0], ip[:, 1])
            dd, idx = tree.query(np.stack([X, Y], 1))
            near = dd < MATCH_TOL_MM
            if float(near.mean()) >= 0.5:
                m = {"frac": float(near.mean()), "gt_width": float(np.median(st[idx[near], 2])),
                     "n_gt": int(len(np.unique(idx[near])))}
                it["match"] = m
                if best is None or m["n_gt"] > best["match"]["n_gt"]:
                    best = it
            else:
                n_false += 1
        # one matched crack per render (the one covering most ground-truth stations), as in synth_validation.py
        ctx["items"] = [best] if best is not None else []
        res["observation"]["px_per_mm"] = round(float(np.median(ppms)) if ppms else ctx["ppm_board"], 2)
    g = gt
    meta = {"gt_ppm_crack": g["scale"]["ppm_crack"], "gt_obliquity": g["camera"]["obliquity_deg"],
            "psf_sigma_px": g["photometric"]["psf_sigma_px"], "gt_width_median": g["crack"]["width_median_mm"],
            "has_glare": g["photometric"]["glare"] is not None, "has_shadow": g["photometric"]["shadow"] is not None,
            "has_motion": g["photometric"]["motion"] is not None, "texture": g["photometric"]["texture"],
            "ink_ratio_board": g["photometric"]["ink_ratio"]}
    out = {"name": name, "group": name, "res": res, "ctx": ctx, "meta": meta, "n_false": n_false,
           "prep_s": time.time() - t}
    with open(CACHE / f"synth_{name}.pkl", "wb") as f:
        pickle.dump(out, f, protocol=4)
    return name, 0 if ctx is None else len(ctx["items"])


def build(workers: int = 3, only: str | None = None, n_synth: int | None = None):
    CACHE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if only in (None, "panel"):
        files = sorted(str(p) for p in RAW_DIR.glob("*.jpg"))
        with ProcessPoolExecutor(workers) as ex:
            for name, n in ex.map(_build_panel, files):
                print("panel", name, n, flush=True)
    if only in (None, "synth"):
        names = sorted(p.stem for p in SYNTH_DIR.glob("synth_*.json"))
        if n_synth:
            names = names[:n_synth]
        with ProcessPoolExecutor(workers) as ex:
            for i, (name, n) in enumerate(ex.map(_build_synth, names, chunksize=2)):
                if i % 25 == 0:
                    print("synth", name, n, f"{time.time() - t0:.0f}s", flush=True)
    print(f"cache built in {time.time() - t0:.0f}s")


def make_split(force: bool = False) -> dict:
    """Freeze tune / test splits.  Only board detection status (not widths or errors) is looked at.

    panel: the usable photo GROUPS (board found and at least one crack ROI) are shuffled with a fixed seed; the first 60 %
           (rounded up) are TUNE, the rest TEST.  Unusable photos (no board) are listed for completeness.
    synth: render ids shuffled with the same seed, 60 % TUNE.
    krk:   widthbench's alternate-specimen-image halves (cluster = series|image; even-indexed unique clusters = calibration)."""
    if SPLIT.exists() and not force:
        return json.loads(SPLIT.read_text())
    rng = np.random.default_rng(SPLIT_SEED)
    groups: dict[str, list[str]] = {}
    unusable = []
    for p in sorted(CACHE.glob("panel_*.pkl")):
        d = pickle.load(open(p, "rb"))
        if d["ctx"] is not None and len(d["ctx"]["items"]) > 0:
            groups.setdefault(d["group"], []).append(d["name"])
        else:
            unusable.append(d["name"])
    gl = sorted(groups)
    perm = rng.permutation(len(gl))
    n_tune = int(np.ceil(TUNE_FRAC * len(gl)))
    tune_g = sorted(gl[i] for i in perm[:n_tune])
    test_g = sorted(gl[i] for i in perm[n_tune:])
    sn = sorted(p.stem for p in SYNTH_DIR.glob("synth_*.json"))
    perm = rng.permutation(len(sn))
    n_st = int(round(TUNE_FRAC * len(sn)))
    sp = {"seed": SPLIT_SEED, "tune_frac": TUNE_FRAC,
          "panel": {"tune_groups": tune_g, "test_groups": test_g,
                    "tune_files": sorted(f for g in tune_g for f in groups[g]),
                    "test_files": sorted(f for g in test_g for f in groups[g]), "unusable_files": sorted(unusable)},
          "synth": {"tune": sorted(sn[i] for i in perm[:n_st]), "test": sorted(sn[i] for i in perm[n_st:])},
          "krk": {"rule": "widthbench halves: unique (series|image) clusters sorted, even index = calibration (TUNE), "
                          "odd index = TEST; crack-present profiles only"}}
    SPLIT.write_text(json.dumps(sp, indent=1))
    return sp


# ----------------------------------------------------------------------------- evaluation of a variant

def _eval_one(args):
    path, cfg = args
    d = pickle.load(open(path, "rb"))
    ctx = d["ctx"]
    if ctx is None or not ctx["items"]:
        return []
    res = copy.deepcopy(d["res"])
    measure._finish(ctx, res, True, False, None, None, cfg)
    obs = res["observation"]
    gate_state = res["gate"]
    rows = []
    items = {it["sd"]["id"]: it for it in ctx["items"]}
    for c in res["cracks"]:
        it = items[c["id"]]
        e = c["estimators"]
        q = c["quality"]
        row = {"file": d["name"], "group": d["group"], "id": c["id"], "width_mm": c["width_mm"],
               "certified": bool(c.get("certified", False)), "ppm": c["px_per_mm"], "sigma_mm": obs.get("blur_sigma_mm"),
               "obliq": obs.get("obliquity_deg"), "blur_var": obs.get("blur_var"), "corners": obs.get("corners"),
               "u_model": c["uncertainty_model_mm"], "interval_lo": c.get("interval_mm", [np.nan, np.nan])[0],
               "interval_hi": c.get("interval_mm", [np.nan, np.nan])[1], "locator": c["locator"],
               "q_core": q.get("q_core"), "spread_rel": q.get("spread_rel"),
               "est_dt": e["dt"], "est_core": e["profile_core"], "est_ink": e["profile_ink"], "est_fwhm": e["fwhm"],
               "wt": e["wt_core"], "core_mm": np.nan if c.get("width_blackcore_mm") is None else c["width_blackcore_mm"],
               "full_mm": c["width_mm"]}
        if "match" in it:
            row["true"] = it["match"]["gt_width"]
            row["n_gt"] = it["match"]["n_gt"]
            row.update({k: d["meta"][k] for k in ("gt_ppm_crack", "gt_obliquity", "psf_sigma_px", "has_glare",
                                                  "has_shadow", "has_motion")})
        else:
            row["true"] = c["true_width_mm"]
        rows.append(row)
    # coverage bookkeeping: expected = number of items in the cache for the image
    for r in rows:
        r["n_items"] = len(ctx["items"])
    return rows, len(ctx["items"]), len(rows)


def run_variant(cfg: dict | None, kind: str, files: list[str], workers: int = 3) -> tuple[pd.DataFrame, int, int]:
    """Rows (one per measured crack) of a variant over the given cache pickles; plus (expected, measured) counts."""
    paths = [str(CACHE / f"{kind}_{Path(f).stem}.pkl") for f in files]
    paths = [p for p in paths if os.path.exists(p)]
    rows, exp, got = [], 0, 0
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            outs = list(ex.map(_eval_one, [(p, cfg) for p in paths], chunksize=2))
    else:
        outs = [_eval_one((p, cfg)) for p in paths]
    for o in outs:
        if o:
            r, e, g = o
            rows += r
            exp += e
            got += g
    return pd.DataFrame(rows), exp, got


# ----------------------------------------------------------------------------- metrics

def stats(err: np.ndarray, true: np.ndarray) -> dict:
    err = np.asarray(err, float)
    true = np.asarray(true, float)
    n = len(err)
    if n == 0:
        return {"n": 0}
    ratio = (true + err) / true
    return {"n": n, "bias": float(err.mean()), "MAE": float(np.abs(err).mean()),
            "P95": float(np.percentile(np.abs(err), 95)), "ratio": float(ratio.mean()),
            "COV": float(ratio.std() / ratio.mean()) if n > 1 else float("nan"),
            "MRE": float((np.abs(err) / true).mean()), "RMSE": float(np.sqrt((err ** 2).mean()))}


def bin_stats(df: pd.DataFrame, col: str = "width_mm") -> dict:
    """{subset: stats} for subsets all / <0.5 / >=0.5 x (all gate states, certified only)."""
    out = {}
    for gname, g in (("all", df), ("cert", df[df.certified] if len(df) else df)):
        for bname, sel in (("all", lambda x: x), ("lt05", lambda x: x[x.true < 0.5]), ("ge05", lambda x: x[x.true >= 0.5])):
            s = sel(g)
            out[f"{gname}/{bname}"] = stats((s[col] - s.true).values, s.true.values) if len(s) else {"n": 0}
    return out


def per_nominal(df: pd.DataFrame, col: str = "width_mm") -> pd.DataFrame:
    rows = []
    for t, g in df.groupby(df.true.round(3)):
        s = stats((g[col] - g.true).values, g.true.values)
        gc = g[g.certified]
        sc = stats((gc[col] - gc.true).values, gc.true.values) if len(gc) else {"n": 0}
        rows.append({"true": t, **s, "n_cert": sc["n"], "MAE_cert": sc.get("MAE", np.nan), "bias_cert": sc.get("bias", np.nan)})
    return pd.DataFrame(rows)


SYNTH_MAX_W = 3.0  # the product range ends at the panel's widest specimen (C8 = 3.0 mm); wider synthetic cracks are
#                    out of scope and a single locator failure there (error ~1 mm) would dominate the objective


def summarize(panel: pd.DataFrame, synth_: pd.DataFrame, cov: dict) -> dict:
    """Flat dict of tune-time metrics + the objective J = mean(panel MAE, synth MAE), all measured cracks, synthetic
    references <= 3.0 mm."""
    S = {}
    synth_ = synth_[synth_.true <= SYNTH_MAX_W] if len(synth_) else synth_
    for nm, df in (("panel", panel), ("synth", synth_)):
        b = bin_stats(df) if len(df) else {}
        for sub, st in b.items():
            for k in ("n", "bias", "MAE", "P95", "ratio", "COV", "MRE"):
                if k in st:
                    S[f"{nm}.{sub}.{k}"] = st[k]
    S["cov.panel"] = cov["panel"]
    S["cov.synth"] = cov["synth"]
    S["J"] = 0.5 * S["panel.all/all.MAE"] + 0.5 * S["synth.all/all.MAE"]
    return S


def evaluate(cfg: dict | None, which: str = "tune", workers: int = 3, with_krk: bool = True, krk_cache=None) -> dict:
    sp = make_split()
    pf = sp["panel"][f"{which}_files"]
    sf = [f + ".jpg" for f in sp["synth"][which]]
    p, pe, pg = run_variant(cfg, "panel", pf, workers)
    s, se, sg = run_variant(cfg, "synth", sf, workers)
    cov = {"panel": pg / max(pe, 1), "synth": sg / max(1, sum(1 for f in sf if os.path.exists(CACHE / f"synth_{Path(f).stem}.pkl")))}
    out = {"panel": p, "synth": s, "S": summarize(p, s, cov)}
    return out



# ----------------------------------------------------------------------------- autoresearch step (tune data only)

LOG = RUN / "log.tsv"
BEST = RUN / "best.json"
LOG_COLS = ["iter", "name", "change", "cfg_delta", "J", "panel_MAE", "synth_MAE", "panel_lt05_MAE", "synth_lt05_MAE",
            "panel_ge05_MAE", "synth_ge05_MAE", "panel_cert_MAE", "krk_added_full15", "krk_added_fwhm15",
            "krk_core_vsman15", "cov_panel", "cov_synth", "kept", "reason"]
MIN_GAIN = 0.002   # relative improvement of J needed to keep a change
GUARD_TOL = 0.10   # METRICS-level guard: no <0.5 mm metric may degrade by more than 10 %
GUARD_ABS = 0.002  # mm; slack so that a 10 % rule does not trip on numbers that are already ~0


def tune_eval(cfg: dict | None, workers: int = 3, with_krk: bool = True) -> tuple[dict, dict, dict]:
    ev = evaluate(cfg, "tune", workers)
    k = {}
    if with_krk:
        import width_krk
        k = width_krk.metrics(width_krk.run(cfg, "tune", workers, ppms=(15.0,)), 15.0)
    return ev["S"], k, ev


def guard_violations(S: dict, k: dict, ref_S: dict, ref_k: dict, krk_tol: float) -> list[str]:
    bad = []
    for ds in ("panel", "synth"):
        for m in ("MAE", "MRE", "P95", "bias"):
            key = f"{ds}.all/lt05.{m}"
            if key not in S or key not in ref_S:
                continue
            new, old = abs(S[key]), abs(ref_S[key])
            if new > old * (1 + GUARD_TOL) + (GUARD_ABS if m != "MRE" else 0.002):
                bad.append(f"{key} {old:.4f}->{new:.4f}")
    if k and ref_k and k["added_full"] > ref_k["added_full"] * (1 + krk_tol):
        bad.append(f"krk.added_full15 {ref_k['added_full']:.4f}->{k['added_full']:.4f}")
    if ref_S["cov.panel"] - S["cov.panel"] > 0.02:
        bad.append("cov.panel")
    if ref_S["cov.synth"] - S["cov.synth"] > 0.03:
        bad.append("cov.synth")
    return bad


def log_row(row: dict):
    new = not LOG.exists()
    with open(LOG, "a", encoding="utf-8") as f:
        if new:
            f.write("\t".join(LOG_COLS) + "\n")
        f.write("\t".join(str(row.get(c, "")) for c in LOG_COLS) + "\n")


def step(name: str, desc: str, delta: dict, workers: int = 3, force_keep: bool = False):
    """One autoresearch iteration: evaluate best_cfg + delta on TUNE data, keep or discard, log."""
    RUN.mkdir(parents=True, exist_ok=True)
    if not BEST.exists():  # iteration 0 = the legacy estimator
        S0, k0, _ = tune_eval({}, workers)
        BEST.write_text(json.dumps({"iter": 0, "cfg": {}, "S": S0, "krk": k0, "base_S": S0, "base_krk": k0}, indent=1))
        log_row(_row(0, "baseline", "legacy estimator (LEGACY_CFG)", {}, S0, k0, True, "baseline"))
    b = json.loads(BEST.read_text())
    cfg = {**b["cfg"], **delta}
    t = time.time()
    try:
        S, k, _ = tune_eval(cfg, workers)
    except Exception as e:  # a crashing variant is logged and discarded
        log_row({"iter": _next_iter(), "name": name, "change": desc, "cfg_delta": json.dumps(delta), "kept": False,
                 "reason": f"crash {type(e).__name__}: {e}"})
        raise
    bad = guard_violations(S, k, b["S"], b["krk"], 0.02)
    bad_base = guard_violations(S, k, b["base_S"], b["base_krk"], 0.0)
    gain = (b["S"]["J"] - S["J"]) / b["S"]["J"]
    kept = gain >= MIN_GAIN and not bad and not bad_base
    if force_keep:
        kept = True
    reason = f"dJ={gain * 100:+.2f}%"
    if bad:
        reason += "; guard(prev): " + "; ".join(bad)
    if bad_base:
        reason += "; guard(base): " + "; ".join(bad_base)
    reason += f"; {time.time() - t:.0f}s"
    it = _next_iter()
    log_row(_row(it, name, desc, delta, S, k, kept, reason))
    if kept:
        b.update({"iter": it, "cfg": cfg, "S": S, "krk": k})
        BEST.write_text(json.dumps(b, indent=1))
    print(f"iter {it} {name}: J {b['S']['J'] if not kept else S['J']:.5f} (candidate {S['J']:.5f}, {gain * 100:+.2f}%) "
          f"panel {S['panel.all/all.MAE']:.4f} synth {S['synth.all/all.MAE']:.4f} "
          f"lt05 {S['panel.all/lt05.MAE']:.4f}/{S['synth.all/lt05.MAE']:.4f} krk_added {k.get('added_full', float('nan')):.4f} "
          f"-> {'KEEP' if kept else 'DISCARD'}  {reason}")
    return kept


def _next_iter() -> int:
    if not LOG.exists():
        return 1
    return int(LOG.read_text(encoding="utf-8").strip().splitlines()[-1].split(chr(9))[0]) + 1


def _row(it, name, desc, delta, S, k, kept, reason):
    return {"iter": it, "name": name, "change": desc, "cfg_delta": json.dumps(delta), "J": round(S["J"], 5),
            "panel_MAE": round(S["panel.all/all.MAE"], 4), "synth_MAE": round(S["synth.all/all.MAE"], 4),
            "panel_lt05_MAE": round(S["panel.all/lt05.MAE"], 4), "synth_lt05_MAE": round(S["synth.all/lt05.MAE"], 4),
            "panel_ge05_MAE": round(S["panel.all/ge05.MAE"], 4), "synth_ge05_MAE": round(S["synth.all/ge05.MAE"], 4),
            "panel_cert_MAE": round(S.get("panel.cert/all.MAE", float("nan")), 4),
            "krk_added_full15": round(k.get("added_full", float("nan")), 4),
            "krk_added_fwhm15": round(k.get("added_fwhm", float("nan")), 4),
            "krk_core_vsman15": round(k.get("vsman_core_mae", float("nan")), 4),
            "cov_panel": round(S["cov.panel"], 3), "cov_synth": round(S["cov.synth"], 3), "kept": int(kept), "reason": reason}


def fmt(x, nd=3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{x:.{nd}f}" if isinstance(x, (float, np.floating)) else str(x)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--workers", type=int, default=3)
    b.add_argument("--only", choices=["panel", "synth"])
    b.add_argument("--n-synth", type=int)
    r = sub.add_parser("run")
    r.add_argument("--name", default="adhoc")
    r.add_argument("--cfg", default="{}")
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--which", default="tune", choices=["tune"])  # the test split is only reachable through `final`
    sub.add_parser("split")
    st = sub.add_parser("step")
    st.add_argument("--name", required=True)
    st.add_argument("--desc", default="")
    st.add_argument("--cfg", default="{}")
    st.add_argument("--workers", type=int, default=3)
    st.add_argument("--force-keep", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.workers, a.only, a.n_synth)
    elif a.cmd == "split":
        sp = make_split()
        print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in sp["panel"].items()}, indent=1))
        print({k: len(v) for k, v in sp["synth"].items()})
    elif a.cmd == "step":
        step(a.name, a.desc, json.loads(a.cfg), a.workers, a.force_keep)
    elif a.cmd == "run":
        t = time.time()
        ev = evaluate(json.loads(a.cfg) or None, a.which, a.workers)
        print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in ev["S"].items()}, indent=1))
        print(f"{time.time() - t:.1f}s")


if __name__ == "__main__":
    main()
