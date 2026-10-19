"""Batch-measure the real phone photos of the printed test panel (data/raw/*.jpg).

Writes
  eval/results/panel_photos_<date>.csv   one row per photo x crack (photos with no result get one empty row)
  eval/results/panel_photos_<date>.md    summary: detection rate, error tables, timing, best overlays
  data/processed/<photo>_overlay.jpg     annotated overlays (local only, git-ignored)

Usage: python eval/run_panel_photos.py [--raw data/raw] [--tag 2026-10-19]
"""
import argparse
import csv
import json
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori import measure  # noqa: E402

EST = ["dt", "profile_core", "profile_ink", "fwhm"]
COLS = ["file", "crack", "locator", "true_mm", "final_mm", "uncertainty_mm", "err_final_mm",
        "dt_mm", "profile_core_mm", "profile_ink_mm", "fwhm_mm",
        "err_dt_mm", "err_profile_core_mm", "err_profile_ink_mm", "err_fwhm_mm",
        "px_per_mm", "corners", "obliquity_deg", "blur_var", "blur_sigma_mm", "glare_frac", "certified", "reasons",
        "total_ms"]


def mae(v):
    return float(np.mean(np.abs(v))) if len(v) else float("nan")


def fmt(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data/raw"))
    ap.add_argument("--tag", default="2026-10-19")
    ap.add_argument("--out", default=str(ROOT / "eval/results"))
    ap.add_argument("--no-overlay", action="store_true")
    a = ap.parse_args()

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = ROOT / "data/processed"
    proc.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(a.raw).glob("*.jpg"))

    rows, per_photo = [], []
    for f in files:
        img = cv2.imread(str(f))  # applies EXIF orientation, same as the service will
        if img is None:
            print("unreadable", f.name)
            continue
        r = measure.analyze(img, panel_mode=True)
        json.dumps(r)  # must be serialisable
        o, g = r["observation"], r["gate"]
        base = {"file": f.name, "px_per_mm": o["px_per_mm"], "corners": o["corners"], "obliquity_deg": o["obliquity_deg"],
                "blur_var": o["blur_var"], "blur_sigma_mm": o.get("blur_sigma_mm", ""), "glare_frac": o["glare_frac"],
                "certified": int(g["certified"]), "reasons": "|".join(g["reasons"]), "total_ms": r["timing_ms"]["total"]}
        if not r["cracks"]:
            rows.append({**base, "crack": "", "locator": r["error"] or ""})
        for c in r["cracks"]:
            e = c["estimators"]
            t = c["true_width_mm"]
            row = {**base, "crack": c["id"], "locator": c["locator"], "true_mm": t, "final_mm": c["width_mm"],
                   "uncertainty_mm": c["uncertainty_mm"], "err_final_mm": round(c["width_mm"] - t, 4),
                   "dt_mm": e["dt"], "profile_core_mm": e["profile_core"], "profile_ink_mm": e["profile_ink"],
                   "fwhm_mm": e["fwhm"]}
            for k in EST:
                row[f"err_{k}_mm" if k != "dt" else "err_dt_mm"] = round(e[k] - t, 4)
            rows.append(row)
        per_photo.append((f.name, r))
        if not a.no_overlay:
            cv2.imwrite(str(proc / f"{f.stem}_overlay.jpg"), measure.draw_overlay(img, r), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(f"{f.name}: corners={o['corners']} cracks={len(r['cracks'])} cert={g['certified']} "
              f"{g['reasons']} {r['timing_ms']['total']:.0f} ms", flush=True)

    csv_path = out_dir / f"panel_photos_{a.tag}.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---------------------------------------------------------------- summary
    n = len(per_photo)
    found = sum(1 for _, r in per_photo if r["observation"]["corners"] >= measure.MIN_CORNERS and r["error"] != "board_not_found")
    measured = [r for _, r in per_photo if r["cracks"]]
    meas_rows = [r for r in rows if r.get("crack")]
    gt_rows = [r for r in meas_rows if r["locator"] == "gt_roi"]
    cert_rows = [r for r in meas_rows if r["certified"]]
    unc_rows = [r for r in meas_rows if not r["certified"]]

    def errs(rs, key="err_final_mm"):
        return [r[key] for r in rs if r.get(key) not in (None, "")]

    L = []
    L.append(f"# Panel photo results ({a.tag})\n")
    L.append(f"Photos: {n}.  Board found (>= {measure.MIN_CORNERS} corners, valid homography): **{found}/{n}** "
             f"({100 * found / n:.0f} %).  At least one crack measured: **{len(measured)}/{n}**.  "
             f"Crack measurements: {len(meas_rows)} (of which {len(gt_rows)} via `gt_roi` fallback).\n")
    L.append("Gate thresholds: corners >= %d, px/mm >= %.0f, blur_var >= %.0f, obliquity <= %.0f deg, glare <= %.2f.  "
             "Final width = blended profile estimator (see `measure.py`), global bias correction = %.3f mm, "
             "INK_RATIO = %.2f.\n" % (measure.GATE_MIN_CORNERS, measure.GATE_MIN_PX_PER_MM, measure.GATE_MIN_BLUR_VAR,
                                       measure.GATE_MAX_OBLIQUITY_DEG, measure.GATE_MAX_GLARE, measure.WIDTH_BIAS_MM,
                                       measure.INK_RATIO))

    L.append("## Estimators (all measurements)\n")
    L.append("| estimator | MAE mm | mean signed err mm | RMSE mm |")
    L.append("|---|---|---|---|")
    for key, name in [("err_final_mm", "FINAL (blended)"), ("err_dt_mm", "dt (2*DT-1px, half-max mask)"),
                      ("err_profile_core_mm", "profile / own plateau"), ("err_profile_ink_mm", "profile / board ink"),
                      ("err_fwhm_mm", "FWHM")]:
        e = errs(meas_rows, key)
        L.append(f"| {name} | {fmt(mae(e))} | {fmt(float(np.mean(e)) if e else None)} | "
                 f"{fmt(float(np.sqrt(np.mean(np.square(e)))) if e else None)} |")

    L.append("\n## Per nominal width (final estimator; all / certified only)\n")
    L.append("| nominal mm | n | mean signed err | MAE | n cert | mean signed err cert | MAE cert | mean u | within 1u (cert) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for wn in sorted({r["true_mm"] for r in meas_rows}):
        rs = [r for r in meas_rows if r["true_mm"] == wn]
        rc = [r for r in rs if r["certified"]]
        e, ec = errs(rs), errs(rc)
        within = np.mean([abs(r["err_final_mm"]) <= r["uncertainty_mm"] for r in rc]) if rc else float("nan")
        L.append(f"| {wn:.2f} | {len(rs)} | {fmt(float(np.mean(e)))} | {fmt(mae(e))} | {len(rc)} | "
                 f"{fmt(float(np.mean(ec)) if ec else None)} | {fmt(mae(ec))} | "
                 f"{fmt(float(np.mean([r['uncertainty_mm'] for r in rs])))} | {fmt(float(within), 2)} |")

    L.append("\n## Certified vs uncertified (final estimator)\n")
    L.append("| group | photos | measurements | MAE mm | mean signed err | rel. MAE |")
    L.append("|---|---|---|---|---|---|")
    for name, rs in [("certified", cert_rows), ("uncertified", unc_rows),
                     ("certified, width >= 0.5 mm", [r for r in cert_rows if r["true_mm"] >= 0.5]),
                     ("certified, width < 0.5 mm", [r for r in cert_rows if r["true_mm"] < 0.5])]:
        e = errs(rs)
        rel = float(np.mean([abs(r["err_final_mm"]) / r["true_mm"] for r in rs])) if rs else float("nan")
        L.append(f"| {name} | {len({r['file'] for r in rs})} | {len(rs)} | {fmt(mae(e))} | "
                 f"{fmt(float(np.mean(e)) if e else None)} | {fmt(rel * 100, 1)} % |")

    L.append("\n## Gate reasons\n")
    cnt = defaultdict(int)
    for _, r in per_photo:
        if r["gate"]["certified"]:
            cnt["certified"] += 1
        for x in r["gate"]["reasons"]:
            cnt[x] += 1
    L.append(", ".join(f"`{k}`: {v}" for k, v in sorted(cnt.items())) + "\n")

    tt = [r["timing_ms"]["total"] for _, r in per_photo if r["observation"]["corners"] >= measure.MIN_CORNERS]
    ta = [r["timing_ms"]["total"] for _, r in per_photo]
    L.append("## Timing (ms, 12 MP images)\n")
    L.append(f"All photos: median {st.median(ta):.0f}, max {max(ta):.0f}.  Photos with a board: median {st.median(tt):.0f}, "
             f"mean {st.mean(tt):.0f}, max {max(tt):.0f}.  Stage medians (board photos): "
             f"detect {st.median([r['timing_ms']['detect'] for _, r in per_photo if r['cracks']]):.0f}, "
             f"rectify {st.median([r['timing_ms']['rectify'] for _, r in per_photo if r['cracks']]):.0f}, "
             f"measure {st.median([r['timing_ms']['measure'] for _, r in per_photo if r['cracks']]):.0f}.\n")

    # cleanest overlays: certified, all 8 cracks measured, lowest MAE
    cand = []
    for name, r in per_photo:
        if r["gate"]["certified"] and len(r["cracks"]) >= 7 and all(c["locator"] == "generic" for c in r["cracks"]):
            e = [abs(c["width_mm"] - c["true_width_mm"]) / c["true_width_mm"] for c in r["cracks"]]
            cand.append((float(np.mean(e)), name, len(r["cracks"])))
    cand.sort()
    L.append("## Cleanest overlays (certified, >= 7 generic cracks, lowest mean relative error)\n")
    for e, name, k in cand[:6]:
        L.append(f"- `{name}`: {k} cracks, mean relative error {100 * e:.1f} %  ->  `data/processed/{Path(name).stem}_overlay.jpg`")

    L.append("\n## Per photo\n")
    L.append("| photo | corners | px/mm | obliq | blur_var | sigma mm | glare | cracks | certified | reasons | ms |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, r in per_photo:
        o = r["observation"]
        L.append(f"| {name} | {o['corners']} | {o['px_per_mm']} | {o['obliquity_deg']} | {o['blur_var']} | "
                 f"{o.get('blur_sigma_mm', '')} | {o['glare_frac']} | {len(r['cracks'])} | "
                 f"{'yes' if r['gate']['certified'] else 'no'} | {','.join(r['gate']['reasons'])} | {r['timing_ms']['total']:.0f} |")
    (out_dir / f"panel_photos_{a.tag}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nwrote {csv_path} and .md")


if __name__ == "__main__":
    main()
