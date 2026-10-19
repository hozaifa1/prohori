"""Batch-measure the real phone photos of the printed test panel (data/raw/*.jpg).

Writes
  eval/results/panel_photos_<date>.csv   one row per photo x crack (photos with no result get one empty row)
  eval/results/panel_photos_<date>.md    summary: detection rate, error tables, timing, best overlays, gate, conformal
                                         interval coverage, and OUT-OF-SAMPLE numbers (leave-one-photo-out re-tuning of
                                         the estimator parameters that were tuned in-sample)
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
from prohori import gate as gate_mod  # noqa: E402
from prohori import measure  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
import gate_lopo  # noqa: E402

EST = ["dt", "profile_core", "profile_ink", "fwhm"]
COLS = ["file", "crack", "locator", "true_mm", "final_mm", "uncertainty_mm", "interval_lo_mm", "interval_hi_mm",
        "covered", "crack_certified", "crack_reasons", "err_final_mm",
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

    rows, per_photo, lopo_recs = [], [], []
    for f in files:
        img = cv2.imread(str(f))  # applies EXIF orientation, same as the service will
        if img is None:
            print("unreadable", f.name)
            continue
        r = measure.analyze(img, panel_mode=True, debug=True)
        lopo_recs.append(gate_lopo.raw_record(f.name, r))
        for c in r["cracks"]:
            c.pop("raw", None)
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
            lo_, hi_ = c.get("interval_mm", [None, None])
            row = {**base, "crack": c["id"], "locator": c["locator"], "true_mm": t, "final_mm": c["width_mm"],
                   "uncertainty_mm": c["uncertainty_mm"], "interval_lo_mm": lo_, "interval_hi_mm": hi_,
                   "covered": int(lo_ <= t <= hi_) if lo_ is not None else "",
                   "crack_certified": int(c.get("certified", False)), "crack_reasons": "|".join(c.get("reasons", [])),
                   "err_final_mm": round(c["width_mm"] - t, 4),
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
    cert_rows = [r for r in meas_rows if r["crack_certified"]]
    unc_rows = [r for r in meas_rows if not r["crack_certified"]]

    def errs(rs, key="err_final_mm"):
        return [r[key] for r in rs if r.get(key) not in (None, "")]

    L = []
    L.append(f"# Panel photo results ({a.tag})\n")
    L.append(f"Photos: {n}.  Board found (>= {measure.MIN_CORNERS} corners, valid homography): **{found}/{n}** "
             f"({100 * found / n:.0f} %).  At least one crack measured: **{len(measured)}/{n}**.  "
             f"Crack measurements: {len(meas_rows)} (of which {len(gt_rows)} via `gt_roi` fallback).\n")
    P = gate_mod.load_params()
    L.append("Gate: %s.  Final width = blended profile estimator (see `measure.py`), global bias correction = %.3f mm, "
             "INK_RATIO = %.2f.  Certification is per crack (`crack_certified`): mask QA and the CRC-calibrated score at "
             "alpha = %s; `uncertainty_mm` is the half-width of the conformal 90 %% interval.\n" % (
                 "fitted CRC gate (gate_params.json)" if P else "LEGACY thresholds (gate_params.json missing)",
                 measure.WIDTH_BIAS_MM, measure.INK_RATIO, P["levels"][P["default_level"]]["alpha"] if P else "n/a"))
    L.append("**Caveat: the estimator parameters (INK_RATIO, blend) were tuned in-sample on these photos, and the gate and "
             "interval were fitted on degradations of these same photos, so every number above the out-of-sample section "
             "is an in-sample number.**\n")

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
    L.append("| nominal mm | n | mean signed err | MAE | n cert | mean signed err cert | MAE cert | mean half-width | inside 90 % interval (cert) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for wn in sorted({r["true_mm"] for r in meas_rows}):
        rs = [r for r in meas_rows if r["true_mm"] == wn]
        rc = [r for r in rs if r["crack_certified"]]
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

    L.append("\n## Gate reasons (capture level: photos)\n")
    cnt = defaultdict(int)
    for _, r in per_photo:
        if r["gate"]["certified"]:
            cnt["certified"] += 1
        for x in r["gate"]["reasons"]:
            cnt[x] += 1
    L.append(", ".join(f"`{k}`: {v}" for k, v in sorted(cnt.items())) + "\n")
    cc = defaultdict(int)
    for r in meas_rows:
        for x in (r["crack_reasons"].split("|") if r["crack_reasons"] else []):
            cc[x] += 1
    L.append("Crack level (flagged measurements): " + (", ".join(f"`{k}`: {v}" for k, v in sorted(cc.items())) or "none") + "\n")

    # ---- conformal interval coverage and wrong rate (in-sample for the gate)
    cov = [r["covered"] for r in meas_rows if r["covered"] != ""]
    L.append("## Conformal 90 % interval on these photos (in-sample: calibrated on degradations of them)\n")
    L.append("| nominal mm | n | covered | certified n | certified covered |")
    L.append("|---|---|---|---|---|")
    for wn in sorted({r["true_mm"] for r in meas_rows}):
        rs = [r for r in meas_rows if r["true_mm"] == wn and r["covered"] != ""]
        rc = [r for r in rs if r["crack_certified"]]
        L.append(f"| {wn:.2f} | {len(rs)} | {fmt(float(np.mean([r['covered'] for r in rs])) if rs else None, 2)} | {len(rc)} | "
                 f"{fmt(float(np.mean([r['covered'] for r in rc])) if rc else None, 2)} |")
    L.append(f"\nAll: {fmt(float(np.mean(cov)) if cov else None, 3)} covered of {len(cov)}.  "
             "For held-out numbers (grouped by source photo) see `gate_report.md`.\n")
    cw = [bool(gate_mod.is_wrong(r["err_final_mm"], r["true_mm"])) and bool(r["crack_certified"]) for r in meas_rows]
    L.append(f"Certified-but-wrong (|err| > max(0.05 mm, 10 %)) on these photos: **{sum(cw)} of {len(cert_rows)} certified** "
             f"({sum(cw)} of {len(meas_rows)} measured) - in-sample.\n")

    # ---- out-of-sample: leave-one-photo-out re-tuning of the estimator parameters
    lo = gate_lopo.lopo(lopo_recs)
    per = lo["per"]
    tr = np.concatenate([x["true"] for x in per])
    wd = np.concatenate([x["w_default"] for x in per])
    wl = np.concatenate([x["w_lopo"] for x in per])
    legm = np.concatenate([[x["legacy"]] * len(x["true"]) for x in per])
    cm = np.concatenate([x["cert"] for x in per])
    L.append("## Out-of-sample estimator accuracy (leave-one-photo-out)\n")
    L.append("Parameters tuned in-sample: `ink_ratio`, blend switch points `d0`, `q0` (grid in `eval/gate_lopo.py`).  "
             "The default column uses the shipped values (tuned on all photos); the LOPO column re-tunes on the sharp, "
             "frontal photos (those passing the legacy hand-set gate) **other than** the photo being measured and applies "
             "the result to it.\n")
    L.append("| subset | n cracks | MAE default (in-sample) | MAE LOPO (out-of-sample) | bias default | bias LOPO |")
    L.append("|---|---|---|---|---|---|")
    for name, m in [("all measured", np.ones(len(tr), bool)), ("legacy-gate photos (the tuning set)", legm),
                    ("not legacy-gate photos", ~legm), ("certified by the fitted gate", cm),
                    ("certified, width < 0.5 mm", cm & (tr < 0.5)), ("certified, width >= 0.5 mm", cm & (tr >= 0.5))]:
        if m.any():
            L.append(f"| {name} | {int(m.sum())} | {fmt(mae(wd[m] - tr[m]))} | {fmt(mae(wl[m] - tr[m]))} | "
                     f"{fmt(float(np.mean(wd[m] - tr[m])))} | {fmt(float(np.mean(wl[m] - tr[m])))} |")
    ch = [(ph, p_) for ph, p_ in lo["chosen"] if p_ is not None]
    L.append("\nShipped: ink_ratio %.2f, d0 %.1f, q0 %.2f.  In-sample grid optimum: ink_ratio %.2f, d0 %.1f, q0 %.2f.  "
             "LOPO choices over %d folds: ink_ratio %s, d0 %s, q0 %s.\n" % (
                 measure.BLEND["ink_ratio"], measure.BLEND["d0"], measure.BLEND["q0"], lo["insample_best"]["ink_ratio"],
                 lo["insample_best"]["d0"], lo["insample_best"]["q0"], len(ch),
                 sorted({float(p_["ink_ratio"]) for _, p_ in ch}), sorted({float(p_["d0"]) for _, p_ in ch}), sorted({float(p_["q0"]) for _, p_ in ch})))
    gs = ROOT / "eval" / "results" / "gate_summary.json"
    if gs.exists():
        S = json.loads(gs.read_text(encoding="utf-8"))
        L.append("Gate out-of-sample (every source photo held out once, whole gate pipeline refitted without it; "
                 "details in `gate_report.md`): " +
                 "; ".join(f"{r[0]}: certified {r[2]}, P(wrong | certified) {r[4]}, 90 % interval coverage {r[7]}"
                           for r in S.get("logo", [])) + "\n")

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
