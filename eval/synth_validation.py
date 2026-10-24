"""Validate the synthetic generator against the real panel photos and measure width error against exact ground truth.

    python eval/synth_validation.py [--n 200] [--dir data/synth/v1] [--workers 3]

Part A  realism: distribution of the observation vector of measure.analyze (corners, px_per_mm, blur_var, glare_frac,
        blur sigma, obliquity) and of simple image statistics (paper-white / toner-black level, black/white ratio,
        noise sigma, edge sharpness, JPEG size) between the renders and the real photos (eval/results/synth_real_stats.csv,
        eval/synth_real_stats.py).  Two-sample Kolmogorov-Smirnov statistic per variable; ECDF figure.
Part B  accuracy: measure.analyze(panel_mode=False) on every render; each measured crack is matched to the ground-truth
        crack (by position in the plane, using the exact camera of the render) and its width compared with the exact
        ground-truth width of the stations it covers.  Reported per METRICS section 0/1a (bias, MAE, P95, ratio, COV,
        MRE per width bin) and per px/mm bin, for certified and all measurements.
Outputs: eval/results/synth_validation.md, synth_validation_rows.csv, synth_validation_obs.png, synth_validation_width.png
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth_stats import ROOT, image_stats  # noqa: E402

from prohori import synth  # noqa: E402

RES = ROOT / "eval" / "results"
MATCH_TOL_MM = 2.5


def _camera(gt):
    cam = gt["camera"]
    R, _ = cv2.Rodrigues(np.array(cam["rvec"], float))
    C = np.array(cam["centre_mm"], float)
    return R, C, np.array(cam["K"], float), np.array(cam["dist_k1k2"], float)


def match_cracks(res: dict, gt: dict) -> list[dict]:
    """Match every measured crack to the ground-truth crack by plane position; returns one dict per measured crack."""
    from scipy.spatial import cKDTree
    st = np.array(gt["crack"]["stations_mm"], float)             # x, y, width
    tree = cKDTree(st[:, :2])
    R, C, K, dist = _camera(gt)
    out = []
    for c in res.get("cracks", []):
        pl = np.array(c["polyline_px"], float)
        if len(pl) < 2:
            continue
        X, Y = synth._pixel_to_plane_exact(R, C, K, dist, pl[:, 0], pl[:, 1])
        d, idx = tree.query(np.stack([X, Y], 1))
        near = d < MATCH_TOL_MM
        frac = float(near.mean())
        row = {"id": c["id"], "width_mm": c["width_mm"], "u_mm": c["uncertainty_mm"], "frac_on_crack": frac,
               "length_mm": c["length_mm"], "matched": frac >= 0.5}
        if row["matched"]:
            row["gt_width_mm"] = float(np.median(st[idx[near], 2]))
            row["n_gt_stations"] = int(len(np.unique(idx[near])))
        out.append(row)
    return out


def one(args):
    name, d = args
    d = Path(d)
    buf = (d / f"{name}.jpg").read_bytes()
    gt = json.loads((d / f"{name}.json").read_text())
    img = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
    t = time.time()
    stats, res = image_stats(img, len(buf))
    stats["analyze_s"] = time.time() - t
    ms = match_cracks(res, gt)
    st = np.array(gt["crack"]["stations_mm"], float)
    row = {"name": name, **stats,
           "gt_ppm_board": gt["scale"]["ppm_board"], "gt_ppm_crack": gt["scale"]["ppm_crack"],
           "gt_obliquity": gt["camera"]["obliquity_deg"], "gt_width_median": gt["crack"]["width_median_mm"],
           "gt_crack_length_mm": gt["crack"]["length_mm"], "texture": gt["photometric"]["texture"],
           "has_glare": gt["photometric"]["glare"] is not None, "has_shadow": gt["photometric"]["shadow"] is not None,
           "has_motion": gt["photometric"]["motion"] is not None, "defocus": gt["photometric"].get("defocus_sigma_px"),
           "psf_sigma_px": gt["photometric"]["psf_sigma_px"], "source": gt["crack"]["source"],
           "certified": bool(res["gate"]["certified"]), "gate_reasons": ",".join(res["gate"]["reasons"]),
           "n_measured": len(ms), "n_matched": int(sum(m["matched"] for m in ms)),
           "n_false": int(sum(not m["matched"] for m in ms)), "error": res.get("error"), "matches": json.dumps(ms)}
    return row


def ecdf(ax, x, label, color):
    x = np.sort(np.asarray(x, float)[np.isfinite(x)])
    if len(x):
        ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", label=f"{label} (n={len(x)})", color=color, lw=1.6)


def width_metrics(df: pd.DataFrame) -> dict:
    e = df.width_mm - df.gt_width_mm
    r = df.width_mm / df.gt_width_mm
    return {"n": len(df), "bias_mm": float(e.mean()), "MAE_mm": float(e.abs().mean()), "P95_mm": float(e.abs().quantile(0.95)),
            "max_abs_mm": float(e.abs().max()), "ratio": float(r.mean()), "COV": float(r.std() / r.mean()) if len(df) > 1 else float("nan"),
            "MRE": float((e.abs() / df.gt_width_mm).mean()),
            "u_mean_mm": float(df.u_mm.mean()), "within_1u": float((e.abs() <= df.u_mm).mean())}


def fmt(x, nd=3):
    if isinstance(x, (float, np.floating)):
        return f"{x:.{nd}f}" if np.isfinite(x) else "n/a"
    return str(x)


def table(rows: list[dict], cols: list[str], nd=3) -> list[str]:
    L = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        L.append("| " + " | ".join(fmt(r.get(c, ""), nd) for c in cols) + " |")
    return L


def main():
    from scipy.stats import ks_2samp
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--dir", default=str(ROOT / "data" / "synth" / "v1"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--reuse", action="store_true", help="reuse eval/results/synth_validation_rows.csv")
    a = ap.parse_args()
    d = Path(a.dir)
    csv = RES / "synth_validation_rows.csv"
    if a.reuse and csv.exists():
        df = pd.read_csv(csv)
    else:
        names = sorted(p.stem for p in d.glob("synth_*.json"))[: a.n]
        with ProcessPoolExecutor(a.workers) as ex:
            rows = list(ex.map(one, [(n, str(d)) for n in names]))
        df = pd.DataFrame(rows)
        df.to_csv(csv, index=False)
    real = pd.read_csv(RES / "synth_real_stats.csv")
    n = len(df)

    # ---------------------------------------------------------------- Part A
    obs_vars = [("corners", "corners found (of 24)", 6), ("px_per_mm", "px/mm at the board", 6), ("blur_var", "blur variance (Laplacian, board)", 6),
                ("blur_sigma_px", "edge blur sigma (px)", 18), ("glare_frac", "glare fraction", 6), ("obliquity_deg", "obliquity (deg)", 6),
                ("white_level", "paper-white level (8-bit)", 18), ("black_level", "toner-black level (8-bit)", 18),
                ("black_white_ratio", "black/white (linear)", 18), ("noise_white", "noise sigma, white (8-bit)", 18),
                ("noise_black", "noise sigma, black (8-bit)", 18), ("jpeg_bytes_per_mpx", "JPEG bytes / Mpx", 0)]
    clean = df[(~df.has_glare) & (~df.has_shadow)]
    cmp_rows = []
    fig, axes = plt_grid(len(obs_vars))
    for ax, (v, title, min_c) in zip(axes, obs_vars):
        r = real[real.corners >= min_c][v].dropna() if min_c else real[v].dropna()
        s = df[df.corners >= min_c][v].dropna() if min_c else df[v].dropna()
        sc = clean[clean.corners >= min_c][v].dropna() if min_c else clean[v].dropna()
        ks = ks_2samp(r, s) if len(r) > 3 and len(s) > 3 else None
        ksc = ks_2samp(r, sc) if len(r) > 3 and len(sc) > 3 else None
        cmp_rows.append({"variable": title, "real_n": len(r), "real_med": r.median(), "real_p10": r.quantile(.1), "real_p90": r.quantile(.9),
                         "synth_n": len(s), "synth_med": s.median(), "synth_p10": s.quantile(.1), "synth_p90": s.quantile(.9),
                         "KS_D": ks.statistic if ks else float("nan"), "KS_p": ks.pvalue if ks else float("nan"),
                         "KS_D_noglare_noshadow": ksc.statistic if ksc else float("nan")})
        ecdf(ax, r, "real photos", "#1b6ca8")
        ecdf(ax, s, "synthetic", "#d9622b")
        ax.set_title(title, fontsize=9)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(RES / "synth_validation_obs.png", dpi=130)

    # ---------------------------------------------------------------- Part B
    ms = []
    for _, r in df.iterrows():
        for m in json.loads(r["matches"]):
            ms.append({**m, "name": r["name"], "certified": r["certified"], "ppm": r["gt_ppm_crack"], "obliq": r["gt_obliquity"],
                       "blur_var": r["blur_var"], "has_glare": r["has_glare"], "psf": r["psf_sigma_px"], "motion": r["has_motion"]})
    M = pd.DataFrame(ms)
    matched = M[M.matched].copy() if len(M) else M
    # one measurement per render: the matched crack with the most ground-truth stations covered
    per_render = matched.sort_values("n_gt_stations", ascending=False).groupby("name").head(1) if len(matched) else matched
    found = df[df.corners >= 6]
    cert = df[df.certified]

    def bins(frame, label, edges, key):
        out = []
        for lo, hi in edges:
            sub = frame[(frame[key] >= lo) & (frame[key] < hi)]
            if len(sub) >= 3:
                out.append({"bin": f"{label} {lo:g}-{hi:g}", **width_metrics(sub)})
        return out

    mpath = ROOT / "src" / "prohori" / "measure.py"
    L = ["# Synthetic generator: realism and width error (D11)", "",
         f"*`src/prohori/measure.py` as of {time.strftime('%Y-%m-%d %H:%M', time.localtime(mpath.stat().st_mtime))} "
         f"(sha1 `{__import__('hashlib').sha1(mpath.read_bytes()).hexdigest()[:10]}`); the gate and width numbers below describe that version.*", "",
         f"Generated by `eval/synth_validation.py` on {n} renders of `{d.relative_to(ROOT) if d.is_relative_to(ROOT) else d}` "
         f"(seeds as in `config.json`) and the {len(real)} real panel photos in `data/raw`. All photos go through the same "
         "`measure.analyze(panel_mode=False)`; the renders contain a printed ChArUco board on a white sheet next to one real-mask "
         "crack on a concrete/plaster texture, so the board is the only region that real and synthetic photos share. Board statistics "
         "are therefore compared on the rectified board (12 px/mm), obs-vector fields on the whole image.", "",
         "## Headline", ""]
    n_cert = int(df.certified.sum())
    L += [f"- Board found (>= 6 corners): **{len(found)}/{n}** renders ({len(found) / n:.0%}); real photos: {int((real.corners >= 6).sum())}/{len(real)}.",
          f"- Certified by the gate of the `measure.analyze` that was installed at run time (see the header; its reasons include the corner / px-per-mm / blur / obliquity / glare thresholds and the mask-quality and width-stability checks): **{n_cert}/{n}** "
          f"({n_cert / n:.0%}).  Reasons among uncertified: " + ", ".join(f"`{k}` {v}" for k, v in
          pd.Series([x for s in df.gate_reasons.fillna("") for x in s.split(",") if x]).value_counts().items()) + ".",
          f"- Renders with a ground-truth crack matched by a measured crack: **{per_render.name.nunique() if len(per_render) else 0}/{n}**; "
          f"measured cracks not on the ground-truth crack (false detections from texture / pores): {int((M.matched == False).sum()) if len(M) else 0} "  # noqa: E712
          f"({(M.matched == False).sum() / max(len(df), 1):.1f} per render)."]  # noqa: E712
    allm = width_metrics(per_render) if len(per_render) else {}
    if allm:
        L += [f"- **Width error, one matched crack per render, all gate states (n = {allm['n']}):** MAE {allm['MAE_mm']:.3f} mm, bias {allm['bias_mm']:+.3f} mm, "
              f"P95 {allm['P95_mm']:.3f} mm, ratio {allm['ratio']:.3f}, COV {allm['COV']:.3f}, MRE {allm['MRE']:.1%}."]
        pc = per_render[per_render.certified]
        if len(pc) > 3:
            c = width_metrics(pc)
            L += [f"- **Certified renders only (n = {c['n']}):** MAE {c['MAE_mm']:.3f} mm, bias {c['bias_mm']:+.3f} mm, P95 {c['P95_mm']:.3f} mm, "
                  f"ratio {c['ratio']:.3f}, COV {c['COV']:.3f}, MRE {c['MRE']:.1%}, fraction within 1 u: {c['within_1u']:.2f}."]
    L += ["", "## Part A. Realism: render vs real photo distributions", "",
          "Real photos with `corners >= 18` supply the board statistics (the 4 photos where the board is partial/blurred are excluded there); "
          "obs-vector rows use every photo with >= 6 corners. `KS D` is the two-sample Kolmogorov-Smirnov distance (0 = identical, 1 = disjoint); "
          "with n ~ 20 real photos only D above ~0.35 is distinguishable from sampling noise (p < 0.05). `KS D clean` drops renders with glare or a cast "
          "shadow (the real panel photos have none, the generator includes them on purpose for the compound-failure experiments).", ""]
    L += table(cmp_rows, ["variable", "real_n", "real_med", "real_p10", "real_p90", "synth_n", "synth_med", "synth_p10", "synth_p90", "KS_D", "KS_p",
                          "KS_D_noglare_noshadow"], 3)
    L += ["", "![observation distributions](synth_validation_obs.png)", "",
          "Known, deliberate differences: (1) the real photos show a full A4 page on a desk, the renders a board plus crack on a wall, so global image "
          "statistics (JPEG bytes/Mpx, saturation) differ by content; (2) glare is absent from the real photos (0.000 in 28/29) but present in "
          f"{df.has_glare.mean():.0%} of renders and a cast shadow in {df.has_shadow.mean():.0%}, to supply the compound failures of METRICS section 3; "
          "(3) `glare_frac` in non-panel mode is computed over the whole image footprint, which for renders is wall, for real photos desk and paper.", "",
          "## Part B. Width error of `measure.analyze` against exact ground truth", "",
          "Each measured crack is placed in the board plane using the *ground-truth* camera of the render and matched to the ground-truth crack "
          f"(>= 50 % of its polyline within {MATCH_TOL_MM} mm of a ground-truth centreline station). The reference is the median exact width of the "
          "stations it covers (the render's width at a station is the diameter of the swept disc, exact by construction; `tests/test_synth.py`). "
          "The measured value is `width_mm` (profile estimator, median over stations). Texture speckle that `measure` reports as extra 'cracks' counts as a "
          "false detection and is excluded from the error statistics.", ""]
    if len(per_render):
        pr = per_render.copy()
        pr["bin"] = np.where(pr.gt_width_mm < 0.5, "< 0.5 mm", ">= 0.5 mm")
        rows = []
        for lab, sub in [("all", pr)] + [(b, g) for b, g in pr.groupby("bin")]:
            rows.append({"subset": f"{lab}", **width_metrics(sub)})
        for lab, sub in [("certified, all", pr[pr.certified])] + [(f"certified, {b}", g[g.certified]) for b, g in pr.groupby("bin")]:
            if len(sub) >= 3:
                rows.append({"subset": lab, **width_metrics(sub)})
        L += ["### By width bin (METRICS 0 rule 2), one matched crack per render", ""]
        L += table(rows, ["subset", "n", "bias_mm", "MAE_mm", "P95_mm", "max_abs_mm", "ratio", "COV", "MRE", "u_mean_mm", "within_1u"])
        L += ["", "Reference tiers (METRICS 1a): Floor <0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %; >=0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %; "
              "overall MAE <= 0.09 mm. Target: MAE <= 0.05 mm, P95 <= 0.10 mm, |bias| <= 0.02 mm.", ""]
        L += ["### By px/mm at the crack (ground-truth scale)", ""]
        L += table(bins(pr, "px/mm", [(0, 10), (10, 13), (13, 16), (16, 30)], "ppm"), ["bin", "n", "bias_mm", "MAE_mm", "P95_mm", "ratio", "COV", "MRE"])
        L += ["", "### By obliquity (deg)", ""]
        L += table(bins(pr, "obliquity", [(0, 10), (10, 25), (25, 40), (40, 90)], "obliq"), ["bin", "n", "bias_mm", "MAE_mm", "P95_mm", "ratio", "COV", "MRE"])
        L += ["", "### By ground-truth width", ""]
        L += table(bins(pr, "w", [(0, 0.3), (0.3, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 10)], "gt_width_mm"), ["bin", "n", "bias_mm", "MAE_mm", "P95_mm", "ratio", "COV", "MRE"])
        L += ["", "### By optical blur (edge sigma of the render, px)", ""]
        L += table(bins(pr, "psf", [(0, 0.8), (0.8, 1.1), (1.1, 1.5), (1.5, 9)], "psf"), ["bin", "n", "bias_mm", "MAE_mm", "P95_mm", "ratio", "COV", "MRE"])
        # ------------------------------------------------ figure
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        f2, (b1, b2, b3) = plt.subplots(1, 3, figsize=(15, 4.4))
        for flag, col, lab in [(False, "#999999", "uncertified"), (True, "#1b6ca8", "certified")]:
            s = pr[pr.certified == flag]
            b1.scatter(s.gt_width_mm, s.width_mm, s=14, color=col, alpha=0.8, label=f"{lab} (n={len(s)})")
        xx = np.array([0.1, 6])
        b1.plot(xx, xx, "k-", lw=0.8)
        b1.plot(xx, xx + 0.05, "k:", lw=0.6)
        b1.plot(xx, xx - 0.05, "k:", lw=0.6)
        b1.set_xscale("log")
        b1.set_yscale("log")
        b1.set_xlabel("ground-truth width (mm)")
        b1.set_ylabel("measured width (mm)")
        b1.set_title("measured vs exact width (dotted: +-0.05 mm)")
        b1.legend(fontsize=8)
        err = pr.width_mm - pr.gt_width_mm
        b2.scatter(pr.ppm, err, s=14, c=np.where(pr.certified, "#1b6ca8", "#999999"))
        b2.axhline(0, color="k", lw=0.8)
        b2.set_xlabel("px/mm at the crack")
        b2.set_ylabel("error (mm)")
        b2.set_title("signed error vs px/mm")
        b3.scatter(pr.gt_width_mm, err / pr.gt_width_mm, s=14, c=np.where(pr.certified, "#1b6ca8", "#999999"))
        b3.axhline(0, color="k", lw=0.8)
        b3.set_xscale("log")
        b3.set_xlabel("ground-truth width (mm)")
        b3.set_ylabel("relative error")
        b3.set_title("relative error vs width")
        for b in (b1, b2, b3):
            b.grid(alpha=0.3)
        f2.tight_layout()
        f2.savefig(RES / "synth_validation_width.png", dpi=130)
        L += ["", "![width error](synth_validation_width.png)", ""]
    L += ["### Where the cracks were lost", ""]
    miss = df[df.n_matched == 0]
    L += [f"- Board found but no ground-truth crack matched: {int((miss.corners >= 6).sum())} renders; board not found: {int((df.corners < 6).sum())} renders.",
          "- Reasons the board was not found or the render was uncertified are in `synth_validation_rows.csv` (columns `error`, `gate_reasons`).", "",
          f"Timing: `measure.analyze` median {df.analyze_s.median():.2f} s per 12.6 MP render.", ""]
    (RES / "synth_validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", RES / "synth_validation.md")


def plt_grid(n):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = 4
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.6 * cols, 2.8 * rows))
    return fig, list(np.ravel(axes))


if __name__ == "__main__":
    main()
