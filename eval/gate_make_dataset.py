"""Build the gate calibration dataset: controlled degradations of the real panel photos with known true widths.

For every source photo with a detectable board, variant 0 is the photo itself and variants 1..N-1 apply a recipe drawn
from `gate_degrade.sample_recipe` (seeded by (SEED, photo, variant), so the whole set is reproducible from the recipes).
Each derived image is measured with measure.analyze(apply_gate=False) and the observation vector, per-crack quality
numbers, measured width, true width and error are stored.

Outputs
  data/gatecal/manifest.jsonl                  one JSON record per derived image (resumable; git-ignored)
  data/gatecal/examples/<photo>_v<k>.jpg       a few degraded images for visual QA (git-ignored)
  data/gatecal/rows.parquet                    one row per crack measurement (git-ignored)
  eval/results/gate_calibration_features.parquet   the same table, the input of eval/gate_fit.py

The shipped estimator configuration (measure.CFG, D18) is the default; --cfg legacy reproduces the 2026-10-19 set with the
files manifest.jsonl / rows.parquet (kept for the old-vs-new comparison); --cfg shipped writes manifest_shipped.jsonl,
rows_shipped.parquet and eval/results/gate_calibration_features.parquet.  Crack polylines (image px) and the board corner
pixels are stored too (needed by the distance-from-board feature).

Usage: python eval/gate_make_dataset.py [--cfg shipped|legacy] [--variants 120] [--workers 6] [--limit-photos N] [--table-only]
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

SEED = 20261019
OUT = ROOT / "data" / "gatecal"
_state: dict = {}
# panel layout: specimen centres 32 / 66 / 100 / 134 mm below the board edge (data/print/test_panel_ground_truth.json)
LAYOUT_DIST_BW = {"C1": 32 / 140, "C2": 32 / 140, "C3": 66 / 140, "C4": 66 / 140, "C5": 100 / 140, "C6": 100 / 140,
                  "C7": 134 / 140, "C8": 134 / 140}


def group_of(path: Path) -> str:
    """Source-photo group id.  Burst frames of one shutter press are one group."""
    stem = path.stem
    return stem.split("_BURST")[0]


def _load(path: str):
    """Load a photo once per worker and find its board->image homography (for glare placement and tilt pivot)."""
    from prohori import measure
    if _state.get("path") == path:
        return _state["img"], _state["H"], _state["centre"]
    img = cv2.imread(path)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids = measure._detect_board(grey)
    if corners is None:
        _state.update(path=path, img=img, H=None, centre=None)
        return img, None, None
    bd = measure._board().getChessboardCorners()[ids][:, :2].astype(np.float64)
    Hb, _ = cv2.findHomography(bd, corners, cv2.RANSAC, 3.0) if len(ids) >= 4 else (None, None)
    if Hb is None:
        _state.update(path=path, img=img, H=None, centre=None)
        return img, None, None
    ctr = measure._apply_h(Hb, np.array([[measure.BOARD_W_MM / 2, measure.BOARD_H_MM / 2]]))[0]
    _state.update(path=path, img=img, H=Hb, centre=ctr)
    return img, Hb, ctr


def _init(cfg_name):
    _state["cfg_name"] = cfg_name


def work(task):
    """task = (path, photo_idx, v, save_example) -> record dict."""
    import gate_degrade as gd
    from prohori import measure
    cv2.setNumThreads(1)
    path, pi, v, save_ex = task
    t0 = time.perf_counter()
    img, Hb, ctr = _load(path)
    rec = {"photo": Path(path).name, "group": group_of(Path(path)), "photo_idx": pi, "v": v}
    if Hb is None:
        rec.update(recipe=None, error="source_board_not_found", observation=None, cracks=[])
        return rec
    if v == 0:
        recipe = {"tilt": None, "scale": 1.0, "blur": None, "glare": None, "noise": None, "jpeg": None}
        deg = img
    else:
        recipe = gd.sample_recipe(np.random.default_rng([SEED, pi, v]))
        deg = gd.apply_recipe(img, recipe, Hb, ctr)
    if save_ex:
        (OUT / "examples").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(OUT / "examples" / f"{Path(path).stem}_v{v}.jpg"), deg, [cv2.IMWRITE_JPEG_QUALITY, 85])
    t1 = time.perf_counter()
    cfg_name = _state.get("cfg_name", "shipped")
    r = measure.analyze(deg, panel_mode=True, apply_gate=False,
                        cfg=measure.LEGACY_CFG if cfg_name == "legacy" else None)
    obs = dict(r["observation"])  # keeps corners_px: the distance-from-board feature is computed from it (gate.raw_features)
    cr = [{k: c[k] for k in ("id", "true_width_mm", "width_mm", "uncertainty_model_mm", "length_mm", "locator",
                             "estimators", "px_per_mm", "quality", "polyline_px")} for c in r["cracks"]]
    rec.update(recipe=recipe, error=r["error"], observation=obs, cracks=cr, shape=list(deg.shape[:2]),
               cfg=cfg_name,
               gen_s=round(t1 - t0, 3), ana_s=round(time.perf_counter() - t1, 3), analyze_ms=r["timing_ms"]["total"])
    return rec


def build_tasks(files, nv, example_photos):
    tasks = []
    for pi, f in enumerate(files):
        for v in range(nv):
            tasks.append((str(f), pi, v, (v in (0, 1, 2, 3, 4, 5)) and (pi in example_photos)))
    return tasks


def flatten(records):
    import pandas as pd
    from prohori import gate
    rows = []
    for r in records:
        rec = r.get("recipe") or {}
        base = {"group": r["group"], "photo": r["photo"], "v": r["v"]}
        if r.get("observation") is None:
            continue
        tl, bl, nz, jp = rec.get("tilt"), rec.get("blur"), rec.get("noise"), rec.get("jpeg")
        base.update({
            "r_tilt_deg": tl["deg"] if tl else 0.0, "r_scale": rec.get("scale", 1.0),
            "r_blur_kind": bl["kind"] if bl else "none",
            "r_blur_sigma_px": bl["sigma"] if bl and bl["kind"] == "gauss" else 0.0,
            "r_motion_len_px": bl["len"] if bl and bl["kind"] == "motion" else 0.0,
            "r_glare_blobs": len(rec["glare"]) if rec.get("glare") else 0,
            "r_noise_sigma": nz["sigma"] if nz else 0.0, "r_jpeg_q": jp["q"] if jp else 100,
            "capture_error": r.get("error") or "",
        })
        obs = r["observation"]
        for k in ("corners", "blur_var", "blur_sigma_mm", "px_per_mm", "ppm_board", "obliquity_deg", "glare_frac",
                  "noise_sigma", "reproj_px", "crack_px_extent", "crack_coverage", "board_found", "image_w", "image_h"):
            base["obs_" + k] = obs.get(k)
        base["n_cracks"] = len(r["cracks"])
        if not r["cracks"]:
            rows.append({**base, "crack": ""})
            continue
        for c in r["cracks"]:
            row = {**base, "crack": c["id"], "locator": c["locator"], "true_mm": c["true_width_mm"],
                   "width_mm": c["width_mm"], "err_mm": round(c["width_mm"] - c["true_width_mm"], 5),
                   "u_model_mm": c["uncertainty_model_mm"], "ppm": c["px_per_mm"], "length_mm": c["length_mm"],
                   # distance from the board edge in board widths: deployable estimate (centroid / farthest vertex, from the
                   # corner pixels and the polyline) and the layout truth of the printed panel (diagnostic only)
                   "dist_bw": gate.board_distance_bw(obs, c), "dist_far_bw": gate.board_distance_bw(obs, c, farthest=True),
                   "dist_layout_bw": LAYOUT_DIST_BW.get(c["id"], float("nan"))}
            for k, val in c["estimators"].items():
                row["est_" + k] = val
            for k, val in c["quality"].items():
                row["q_" + k] = val
            rows.append(row)
    df = pd.DataFrame(rows)
    df["tol_mm"] = gate.tolerance_mm(df["true_mm"].fillna(1.0))
    df["abs_err_mm"] = df["err_mm"].abs()
    df["wrong"] = (df["abs_err_mm"] > df["tol_mm"]).where(df["crack"] != "", None)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data/raw"))
    ap.add_argument("--cfg", choices=["shipped", "legacy"], default="shipped")
    ap.add_argument("--variants", type=int, default=120)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit-photos", type=int, default=0)
    ap.add_argument("--table-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sfx = "" if a.cfg == "legacy" else "_shipped"
    manifest = OUT / f"manifest{sfx}.jsonl"
    files = sorted(Path(a.raw).glob("*.jpg"))
    if a.limit_photos:
        files = files[:a.limit_photos]
    done = set()
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                done.add((d["photo"], d["v"]))
    if not a.table_only:
        tasks = [t for t in build_tasks(files, a.variants, set(range(0, len(files), 4)))
                 if (Path(t[0]).name, t[2]) not in done]
        print(f"{len(files)} photos x {a.variants} variants; {len(tasks)} to run, {len(done)} already done", flush=True)
        t0 = time.time()
        with open(manifest, "a", encoding="utf-8") as fh, mp.Pool(a.workers, initializer=_init, initargs=(a.cfg,)) as pool:
            for i, rec in enumerate(pool.imap(work, tasks, chunksize=1)):
                fh.write(json.dumps(rec) + "\n")
                if i % 50 == 0:
                    fh.flush()
                    el = time.time() - t0
                    print(f"{i + 1}/{len(tasks)}  {el:.0f}s  eta {el / (i + 1) * (len(tasks) - i - 1):.0f}s", flush=True)
    records = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [r for r in records if r.get("observation") is not None]
    print(f"{len(records)} records, {len(ok)} with a source board")
    df = flatten(records)
    df.to_parquet(OUT / f"rows{sfx}.parquet", index=False)
    (ROOT / "eval" / "results").mkdir(parents=True, exist_ok=True)
    if a.cfg == "shipped":
        df.to_parquet(ROOT / "eval" / "results" / "gate_calibration_features.parquet", index=False)
    meas = df[df["crack"] != ""]
    print(f"rows {len(df)}  crack measurements {len(meas)}  groups {df['group'].nunique()}  "
          f"captures {df.groupby(['photo', 'v']).ngroups}")
    print(f"wrong rate overall {meas['wrong'].astype(float).mean():.3f}")


if __name__ == "__main__":
    main()
