"""krkCMd open width benchmark + empirical px/mm gate curve  (TickTick D15).

Usage
    python eval/krkcmd_bench.py                       # full run (about 10 min on 8 cores)
    python eval/krkcmd_bench.py --quick               # 2,000-profile smoke run
    python eval/krkcmd_bench.py --data data/datasets/krkcmd --out eval/results --workers 8

Outputs (eval/results/)
    krkcmd_baselines.csv   RMSE/MAE/bias of the shipped AED, our AED port, shipped DLM and our estimators, native
    krkcmd_metrics.csv     long table: estimator x calibration x PSF sigma x px/mm x width bin
    krkcmd_gate.csv        per estimator/calibration/criterion: pass flags per px/mm and the derived gate
    krkcmd_curve.png       error vs px/mm per width bin (final blend and best candidate)
    krkcmd_estimators.png  gate-bin error vs px/mm, all estimators
    krkcmd_report.md       everything above in prose and tables
Data: Zenodo 10.5281/zenodo.11408398 (CC-BY 4.0), see research/WIDTHBENCH_NOTES.md.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori import widthbench as wb  # noqa: E402

HEADLINE = ["loc_blend", "glob_blend", "loc_ink", "loc_core", "loc_fwhm", "loc_dt", "cand_area", "cand_frac"]
LABEL = {
    "loc_blend": "measure.py blend (local bg)", "glob_blend": "measure.py blend (as-is bg)",
    "loc_ink": "profile integral / board-ink", "loc_core": "profile integral / own core",
    "loc_fwhm": "FWHM", "loc_dt": "2*DT-1 (mask)", "cand_area": "candidate: windowed area",
    "cand_frac": "candidate: 15 % depth crossing",
}
GATE_BINS = ["0.30-0.50mm", "<0.5mm"]
BIN_ORDER = [f"{lo:.1f}-{hi:.1f}" for lo, hi in wb.WIDTH_BINS] + list(wb.POOLED_BINS)


def rms(e):
    e = np.asarray(e, float)
    return float(np.sqrt(np.mean(e ** 2))) if len(e) else float("nan")


def fmt(x, nd=1, scale=1.0):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * scale:.{nd}f}"


# ----------------------------------------------------------------------------------------------- baselines

def baselines(p: wb.Profiles, aed_port: np.ndarray, ours: dict) -> list[dict]:
    rows = []
    man = p.man
    cp = man > 0

    def add(name, pred, note=""):
        pred = np.where(np.isfinite(pred), pred, 0.0)  # a refusal / no crack found = 0 um
        e = pred - man
        r = dict(method=name, note=note, n_all=len(man), rmse_all_um=rms(e), mae_all_um=float(np.abs(e).mean()),
                 bias_all_um=float(e.mean()), rmse_crack_um=rms(e[cp]), mae_crack_um=float(np.abs(e[cp]).mean()),
                 bias_crack_um=float(e[cp].mean()),
                 rmse_ge100um=rms(e[man >= 100]), rmse_lt100um=rms(e[(man > 0) & (man < 100)]),
                 rmse_zero_ref_um=rms(e[~cp]))
        for s in range(1, 7):
            k = p.stage == s
            r[f"rmse_stage{s}_um"] = rms(e[k])
        rows.append(r)

    add("AED (shipped CSV column)", p.aed, "published benchmark prediction")
    add("AED (our VBA port)", aed_port, f"exact match to CSV on {np.mean(np.abs(aed_port - p.aed) < 0.01) * 100:.2f} % of rows")
    add("DLM (shipped CSV column)", p.dlm, "CNN trained on this same data; split not published, so in-sample")
    for k, v in ours.items():
        if k in HEADLINE:
            add(f"ours: {LABEL[k]}", v * 1000.0, "native 252 px/mm, crack seeded at profile centre, NaN -> 0")
    return rows


# ----------------------------------------------------------------------------------------------- metrics tables

METRIC_COLS = ["estimator", "calib", "psf_sigma_px", "ppm", "bin", "n", "n_bin", "ok", "bias_mm", "mae_mm", "rmse_mm",
               "p95_mm", "ratio", "cov", "mre", "mae_ci_lo", "mae_ci_hi"]


def metrics_rows(est, calib, psf, ppm, pred, ref, clusters, boot=True, extra_ref_mask=None, bin_by=None):
    rows = []
    for name, (lo, hi) in [(f"{a:.1f}-{b:.1f}", (a, b)) for a, b in wb.WIDTH_BINS] + list(wb.POOLED_BINS.items()):
        s = wb.bin_metrics(pred, ref, lo, hi, extra_ref_mask, bin_by)
        if s.get("n", 0) == 0:
            continue
        ci = (float("nan"), float("nan"))
        if boot and name in GATE_BINS:
            ci = wb.cluster_bootstrap(pred, ref, clusters, lo, hi, "mae", n_boot=200, bin_by=bin_by)
        rows.append(dict(estimator=est, calib=calib, psf_sigma_px=psf, ppm=ppm, bin=name, n=s["n"], n_bin=s["n_bin"],
                         ok=s["ok"], bias_mm=s["bias"], mae_mm=s["mae"], rmse_mm=s["rmse"], p95_mm=s["p95"],
                         ratio=s["ratio"], cov=s["cov"], mre=s["mre"], mae_ci_lo=ci[0], mae_ci_hi=ci[1]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/datasets/krkcmd"))
    ap.add_argument("--out", default=str(ROOT / "eval/results"))
    ap.add_argument("--ppm", default="8,10,12,15,20,25")
    ap.add_argument("--psf", type=float, default=0.75, help="primary PSF sigma, output px (METRICS 1b: 0.5-1.0)")
    ap.add_argument("--sens-psf", default="0.5,1.0")
    ap.add_argument("--sens-n", type=int, default=3000, help="profiles used for the PSF-sensitivity runs")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fidelity", type=int, default=150, help="profiles for the measure._measure_one adapter check (0=skip)")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--replot", action="store_true", help="redraw the PNGs from an existing <tag>_metrics.csv and exit")
    ap.add_argument("--tag", default="krkcmd")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ppms = [float(x) for x in a.ppm.split(",")]
    if a.replot:
        rows = []
        with open(out / f"{a.tag}_metrics.csv", newline="") as f:
            for r in csv.DictReader(f):
                for k in METRIC_COLS[2:]:
                    if k != "bin":
                        r[k] = float(r[k]) if r[k] not in ("", "nan") else float("nan")
                rows.append(r)
        make_plots(rows, out, a.tag, a.psf, ppms)
        return
    t0 = time.time()

    p = wb.load_krkcmd(a.data)
    if a.quick:
        rng = np.random.default_rng(a.seed)
        # keep whole clusters-worth of variety: random subset of profiles
        p = p.subset(np.sort(rng.choice(len(p), 2000, replace=False)))
    print(f"loaded {len(p)} profiles in {time.time() - t0:.1f}s")
    ref_mm = p.man / 1000.0
    cp = p.man > 0
    clusters = p.cluster
    uc = np.unique(clusters)
    cal_clusters = set(uc[::2])
    is_cal = np.array([c in cal_clusters for c in clusters])
    is_test = ~is_cal

    native_sigma = wb.native_edge_sigma_mm(p)
    print(f"native edge sigma {native_sigma * 1000:.1f} um; clusters {len(uc)} (cal {len(cal_clusters)}, test {len(uc) - len(cal_clusters)})")

    # ---- AED port
    if a.quick:
        aed_port = np.full(len(p), np.nan)  # the port needs whole stacks of 6 stages
    else:
        aed_port = wb.aed_vba(p)
    print(f"AED port done {time.time() - t0:.0f}s")

    # ---- native predictions of ours on ALL profiles
    model = wb.SimModel(psf_sigma_px=a.psf)
    P_nat = wb.predict_all(p.X, None, native_sigma, model, include_global=True, seed=a.seed, workers=a.workers)
    print(f"native predictions done {time.time() - t0:.0f}s")

    base_rows = baselines(p, aed_port if not a.quick else p.aed, P_nat)
    with open(out / f"{a.tag}_baselines.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(base_rows[0].keys()))
        w.writeheader()
        w.writerows(base_rows)

    # ---- calibration at native (cal half, crack-present): ref = a*pred + b, frozen for every resolution
    names = wb.estimator_names(True)
    calib = {k: wb.fit_linear(P_nat[k], ref_mm, is_cal & cp) for k in names}

    # ---- simulated resolutions on all crack-present profiles
    idx_cp = np.nonzero(cp)[0]
    Xcp = p.X[idx_cp]
    ref_cp = ref_mm[idx_cp]
    cl_cp = clusters[idx_cp]
    cal_cp = is_cal[idx_cp]
    test_cp = ~cal_cp
    Pn = {k: v[idx_cp] for k, v in P_nat.items()}

    all_rows = []
    sims = {}  # (psf, ppm) -> preds on crack-present

    def run_sim(psf, ppm, sub=None, include_global=False):
        mdl = wb.SimModel(psf_sigma_px=psf)
        X = Xcp if sub is None else Xcp[sub]
        return wb.predict_all(X, ppm, native_sigma, mdl, include_global=include_global, seed=a.seed + 1, workers=a.workers)

    def eval_cfg(psf, ppm, preds, sel_idx=None, boot=True):
        """Append metric rows on the TEST half for raw / frozen-native / per-ppm refit calibrations."""
        if sel_idx is None:
            sel_idx = np.arange(len(idx_cp))
        ref = ref_cp[sel_idx]
        tst = test_cp[sel_idx]
        cal = cal_cp[sel_idx]
        cl = cl_cp[sel_idx]
        for k, v in preds.items():
            fa, fb = calib[k]
            ra, rb = wb.fit_linear(v, ref, cal)
            for cname, pv in (("raw", v), ("cal_native", fa * v + fb), ("cal_refit", ra * v + rb)):
                pr = np.where(tst, pv, np.nan)  # test clusters only
                all_rows.extend(metrics_rows(k, cname, psf, ppm, pr, ref, cl, boot=boot and psf == a.psf))

    # native (ppm=252) rows
    eval_cfg(a.psf, wb.NATIVE_PX_PER_MM, {k: Pn[k] for k in names}, boot=True)

    for ppm in ppms:
        inc_glob = ppm in (15.0, 25.0, 10.0)
        preds = run_sim(a.psf, ppm, include_global=inc_glob)
        sims[(a.psf, ppm)] = preds
        eval_cfg(a.psf, ppm, preds)
        # resolution-added error: same estimator vs itself at native, same profiles
        for k, v in preds.items():
            pr = np.where(test_cp, v, np.nan)
            # error of the estimator at this resolution vs ITSELF at native (same profiles), binned by operator width
            all_rows.extend(metrics_rows(k, "added", a.psf, ppm, pr, Pn[k], cl_cp, boot=True, bin_by=ref_cp))
        print(f"ppm {ppm:g} done {time.time() - t0:.0f}s")

    # PSF sensitivity on a subsample
    rng = np.random.default_rng(a.seed + 7)
    sub = np.sort(rng.choice(len(idx_cp), min(a.sens_n, len(idx_cp)), replace=False))
    for psf in [float(x) for x in a.sens_psf.split(",") if x]:
        for ppm in ppms:
            preds = run_sim(psf, ppm, sub=sub, include_global=False)
            eval_cfg(psf, ppm, preds, sel_idx=sub, boot=False)
            for k, v in preds.items():
                pr = np.where(test_cp[sub], v, np.nan)
                all_rows.extend(metrics_rows(k, "added", psf, ppm, pr, Pn[k][sub], cl_cp[sub], boot=False, bin_by=ref_cp[sub]))
        print(f"psf {psf} done {time.time() - t0:.0f}s")

    with open(out / f"{a.tag}_metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=METRIC_COLS)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: (f"{r[k]:.6g}" if isinstance(r[k], float) else r[k]) for k in METRIC_COLS})

    # ---- gate derivation
    gate_rows = derive_gates(all_rows, a.psf, [wb.NATIVE_PX_PER_MM] + ppms)
    with open(out / f"{a.tag}_gate.csv", "w", newline="") as f:
        cols = ["estimator", "calib", "psf_sigma_px", "bin", "criterion", "gate_ppm"] + [f"pass_{p_:g}" for p_ in [wb.NATIVE_PX_PER_MM] + ppms]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in gate_rows:
            w.writerow(r)

    # ---- adapter fidelity check
    fid = fidelity_check(p, ppms, native_sigma, a.psf, a.fidelity, a.seed, a.workers) if a.fidelity else None

    make_plots(all_rows, out, a.tag, a.psf, ppms)
    write_report(out, a, p, base_rows, all_rows, gate_rows, fid, native_sigma, calib, len(uc), len(cal_clusters), ppms,
                 time.time() - t0)
    print(f"done in {time.time() - t0:.0f}s -> {out}")


# ----------------------------------------------------------------------------------------------- gate

def _lookup(rows, est, calib, psf, ppm, bin_):
    for r in rows:
        if r["estimator"] == est and r["calib"] == calib and r["psf_sigma_px"] == psf and abs(r["ppm"] - ppm) < 1e-2 and r["bin"] == bin_:
            return r
    return None


def derive_gates(rows, psf, ppm_list):
    """Gate per (estimator, calibration, bin, criterion).  A resolution passes only if every component holds; the gate is
    the lowest sweep value from which all higher values also pass."""
    index = {}
    for r in rows:
        index[(r["estimator"], r["calib"], r["psf_sigma_px"], round(r["ppm"], 4), r["bin"])] = r
    out = []
    ests = sorted({r["estimator"] for r in rows})
    for est in ests:
        for cal in ("raw", "cal_native", "cal_refit", "added"):
            for b in GATE_BINS:
                crits = {"target(MAE,P95,bias,ratio,COV)": None, "MAE<=0.05mm": None, "px-equiv(RMSE<=0.5px, w>=1px)": None}
                flags = {c: [] for c in crits}
                for ppm in ppm_list:
                    r = index.get((est, cal, psf, round(ppm, 4), b))
                    if r is None:
                        for c in flags:
                            flags[c].append(cal == "added" and ppm > 100)  # native vs itself: zero by construction
                        continue
                    s = dict(n=r["n"], bias=r["bias_mm"], mae=r["mae_mm"], p95=r["p95_mm"], ratio=r["ratio"], cov=r["cov"])
                    if cal == "added":
                        # resolution may consume at most 40 % of the 0.05 mm MAE / 0.10 mm P95 budget, |bias| <= 0.01 mm
                        flags["target(MAE,P95,bias,ratio,COV)"].append(
                            r["n"] >= 5 and s["mae"] <= 0.4 * wb.TARGET["mae_mm"] and s["p95"] <= 0.4 * wb.TARGET["p95_mm"]
                            and abs(s["bias"]) <= 0.5 * wb.TARGET["abs_bias_mm"])
                    else:
                        flags["target(MAE,P95,bias,ratio,COV)"].append(wb.passes_target(s)["all"])
                    flags["MAE<=0.05mm"].append(s["mae"] <= wb.TARGET["mae_mm"])
                    flags["px-equiv(RMSE<=0.5px, w>=1px)"].append(r["rmse_mm"] <= 0.5 / ppm)
                for c, fl in flags.items():
                    g = wb.gate_from_curve(ppm_list, fl)
                    row = dict(estimator=est, calib=cal, psf_sigma_px=psf, bin=b, criterion=c,
                               gate_ppm="none" if g is None else f"{g:g}")
                    for p_, ok in zip(ppm_list, fl):
                        row[f"pass_{p_:g}"] = int(ok)
                    out.append(row)
    return out


# ----------------------------------------------------------------------------------------------- fidelity

def _fid_worker(args):
    y, ppm, sm = args
    r = wb.pipeline_width(y, ppm, sm, ink_dark=0.0)
    return {k: r.get(k2, np.nan) for k, k2 in [("dt", "dt_mm"), ("fwhm", "fwhm_mm"), ("core", "profile_core_mm"),
                                                ("ink", "profile_ink_mm"), ("blend", "profile_mm")]}


def fidelity_check(p, ppms, native_sigma, psf, n, seed, workers):
    """1-D reduction (bg_mode='global') vs the unmodified measure._measure_one on synthetic straight-crack images."""
    from concurrent.futures import ProcessPoolExecutor
    rng = np.random.default_rng(seed + 11)
    idx = rng.choice(np.nonzero(p.man >= 100)[0], n, replace=False)
    res = {}
    for ppm in [x for x in ppms if x in (10.0, 15.0, 25.0)]:
        mdl = wb.SimModel(psf_sigma_px=psf)
        Y = wb.simulate_lowres(p.X[idx], ppm, mdl, np.random.default_rng(seed + 12))
        sm = wb.sigma_mm_total(psf, ppm, native_sigma)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            A = list(ex.map(_fid_worker, [(y, ppm, sm) for y in Y], chunksize=8))
        B = [wb.profile_widths(y, ppm, sm, ink_dark=0.0, bg_mode="global") for y in Y]
        rr = {}
        for k in wb.KEYS:
            av = np.array([r[k] for r in A])
            bv = np.array([r[k] for r in B])
            ok = np.isfinite(av) & np.isfinite(bv)
            d = np.abs(av[ok] - bv[ok]) * 1000
            rr[k] = dict(n=int(ok.sum()), median_um=float(np.median(d)), p90_um=float(np.percentile(d, 90)),
                         corr=float(np.corrcoef(av[ok], bv[ok])[0, 1]), fail_adapter=int((~np.isfinite(av)).sum()),
                         fail_reduction=int((~np.isfinite(bv)).sum()))
        res[ppm] = rr
    return res


# ----------------------------------------------------------------------------------------------- plots

def make_plots(rows, out, tag, psf, ppms):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ppm_all = [wb.NATIVE_PX_PER_MM] + ppms
    xs = ppms + [40.0]  # native drawn at a nominal x for readability
    bins = [f"{a:.1f}-{b:.1f}" for a, b in wb.WIDTH_BINS]
    cols = ["#264653", "#2a9d8f", "#8ab17d", "#e9c46a", "#e76f51"]
    cb = dict(zip(bins, cols))

    def series(est, calib, bin_, field):
        ys = []
        for ppm in ppm_all[1:] + [ppm_all[0]]:
            r = _lookup(rows, est, calib, psf, ppm, bin_)
            ys.append(np.nan if r is None else r[field])
        return ys

    best_cand = min(("cand_area", "cand_frac"), key=lambda e: (lambda r: np.inf if r is None else r["mae_mm"])(
        _lookup(rows, e, "cal_refit", psf, 15.0, "0.30-0.50mm")))
    fig, ax = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    for row, est in enumerate(["loc_blend", best_cand]):
        for b in bins:
            ax[row, 0].plot(xs, np.array(series(est, "cal_refit", b, "mae_mm")) * 1000, "-o", color=cb[b], label=f"{b} mm", ms=4)
            ax[row, 1].plot(xs, np.array(series(est, "raw", b, "bias_mm")) * 1000, "-o", color=cb[b], label=f"{b} mm", ms=4)
        ax[row, 0].axhline(wb.TARGET["mae_mm"] * 1000, color="k", ls="--", lw=1)
        ax[row, 0].text(xs[0], wb.TARGET["mae_mm"] * 1000 + 2, "target MAE 50 um", fontsize=8)
        ax[row, 0].axhline(wb.OPERATOR_RMS_UM, color="grey", ls=":", lw=1)
        ax[row, 0].text(xs[0], wb.OPERATOR_RMS_UM + 2, "operator RMS 16.6 um (reference floor)", fontsize=8, color="grey")
        ax[row, 1].axhline(0, color="k", lw=0.8)
        ax[row, 0].set_ylabel(f"{LABEL[est]}\nMAE vs MANwidth, um (bias-refit)")
        ax[row, 1].set_ylabel("bias, um (raw, no calibration)")
        ax[row, 0].set_ylim(0, min(400, max(60, np.nanmax(np.array([series(est, 'cal_refit', b, 'mae_mm') for b in bins])) * 1000 * 1.1)))
        for c in (0, 1):
            ax[row, c].set_xticks(xs)
            ax[row, c].set_xticklabels([f"{x:g}" for x in ppms] + ["252\n(native)"])
            ax[row, c].grid(alpha=0.25)
    ax[1, 0].set_xlabel("simulated resolution, px/mm")
    ax[1, 1].set_xlabel("simulated resolution, px/mm")
    ax[0, 1].legend(title="MANwidth bin", fontsize=8, loc="best")
    fig.suptitle(f"krkCMd: width error vs resolution (PSF sigma {psf} px, test half, crack-present profiles)")
    fig.tight_layout()
    fig.savefig(out / f"{tag}_curve.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    pal = ["#1d3557", "#e76f51", "#2a9d8f", "#e9c46a", "#8ab17d", "#6d597a", "#b56576", "#d00000"]
    for c, calib_name in enumerate(["raw", "cal_native", "cal_refit"]):
        for est, col in zip(HEADLINE, pal):
            ys = []
            for ppm in ppm_all[1:] + [ppm_all[0]]:
                r = _lookup(rows, est, calib_name, psf, ppm, "0.30-0.50mm")
                ys.append(np.nan if r is None else r["mae_mm"] * 1000)
            ax[c].plot(xs, ys, marker="o", color=col, label=LABEL[est], ms=3.5, linestyle="--" if est.startswith("glob") else "-")
        ax[c].axhline(wb.TARGET["mae_mm"] * 1000, color="k", ls="--", lw=1)
        ax[c].set_title(f"{calib_name}", fontsize=10)
        ax[c].set_xticks(xs)
        ax[c].set_xticklabels([f"{x:g}" for x in ppms] + ["252"])
        ax[c].set_xlabel("simulated resolution, px/mm")
        ax[c].grid(alpha=0.25)
        ax[c].set_yscale("log")
    ax[0].set_ylabel("MAE vs MANwidth, um   (0.30-0.50 mm cracks, log)")
    ax[0].legend(fontsize=7, loc="upper right")
    fig.suptitle("Gate bin 0.30-0.50 mm: error of every estimator vs resolution (dashed black = 50 um target)")
    fig.tight_layout()
    fig.savefig(out / f"{tag}_estimators.png", dpi=130)
    plt.close(fig)


# ----------------------------------------------------------------------------------------------- report

def md_table(headers, rows):
    s = "| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    for r in rows:
        s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s


def write_report(out, a, p, base_rows, rows, gate_rows, fid, native_sigma, calib, ncl, ncal, ppms, secs):
    psf = a.psf
    L = []
    L.append(f"# krkCMd open width benchmark and px/mm gate curve\n\n*Generated {dt.date.today()} by `eval/krkcmd_bench.py` "
             f"({secs:.0f} s). Data: Zenodo 10.5281/zenodo.11408398 v1.1, {len(p):,} profiles, 3.96875 um/px (251.97 px/mm).*\n")
    L.append("## 1. Baselines at native resolution (all profiles, um)\n")
    L.append("Reference = operator `MANwidth`. Refusals / no crack found count as 0 um. `crack` = profiles with MANwidth > 0 "
             "(healed cracks have MANwidth = 0).\n")
    L.append(md_table(["method", "RMSE all", "MAE all", "bias all", "RMSE crack", "MAE crack", "bias crack", "RMSE w>=100um", "RMSE w<100um", "note"],
                      [[r["method"], fmt(r["rmse_all_um"]), fmt(r["mae_all_um"]), fmt(r["bias_all_um"]), fmt(r["rmse_crack_um"]),
                        fmt(r["mae_crack_um"]), fmt(r["bias_crack_um"]), fmt(r["rmse_ge100um"]), fmt(r["rmse_lt100um"]), r["note"]]
                       for r in base_rows]))
    L.append(f"\nInter-operator floor: RMS {wb.OPERATOR_RMS_UM} um (5 operators); native pixel pitch 3.97 um; the reference is "
             "quantised to whole pixels.\n")
    L.append("## 2. Error vs resolution, gate bin 0.30-0.50 mm (test half, "
             f"{ncl - ncal} specimen images; PSF sigma {psf} px)\n")
    hdr = ["estimator", "calib"] + [f"{x:g}" for x in ppms] + ["native"]
    for field, title, sc in (("mae_mm", "MAE, um", 1000.0), ("bias_mm", "bias, um", 1000.0)):
        L.append(f"\n**{title}**\n")
        tr = []
        for est in HEADLINE:
            for cal in ("raw", "cal_native", "cal_refit"):
                vals = []
                for ppm in ppms + [wb.NATIVE_PX_PER_MM]:
                    r = _lookup(rows, est, cal, psf, ppm, "0.30-0.50mm")
                    vals.append(fmt(None if r is None else r[field], 1, sc))
                tr.append([LABEL[est], cal] + vals)
        L.append(md_table(hdr, tr))
    L.append("\n## 3. Per width bin, test half (um)\n")
    for est in ["loc_blend", "cand_area", "cand_frac"]:
        for cal in ("raw", "cal_refit"):
            L.append(f"\n**{LABEL[est]}, {cal}: MAE / bias / ratio / COV**\n")
            tr = []
            for b in BIN_ORDER:
                vals = []
                for ppm in ppms + [wb.NATIVE_PX_PER_MM]:
                    r = _lookup(rows, est, cal, psf, ppm, b)
                    vals.append("n/a" if r is None else f"{r['mae_mm'] * 1000:.0f} / {r['bias_mm'] * 1000:+.0f} / {r['ratio']:.2f} / {r['cov'] * 100:.0f}%")
                tr.append([b] + vals)
            L.append(md_table(["bin (mm)"] + [f"{x:g}" for x in ppms] + ["native"], tr))
    L.append("\n## 4. Resolution-added error: estimator at px/mm vs the SAME estimator at native, same profiles (um)\n")
    L.append("Binned by operator width. This isolates what lowering the resolution costs from how well the estimator "
             "matches the operator's definition at native. Cells: MAE / P95 / bias.\n")
    for bname in ("0.30-0.50mm", "<0.5mm"):
        L.append(f"\n**bin {bname}**\n")
        tr = []
        for est in HEADLINE:
            vals = []
            for ppm in ppms:
                r = _lookup(rows, est, "added", psf, ppm, bname)
                vals.append("n/a" if r is None else f"{r['mae_mm'] * 1000:.0f} / {r['p95_mm'] * 1000:.0f} / {r['bias_mm'] * 1000:+.0f}")
            tr.append([LABEL[est]] + vals)
        L.append(md_table(["estimator"] + [f"{x:g}" for x in ppms], tr))
    L.append("\n## 5. Derived gates (lowest px/mm from which every higher swept value passes; 'none' = never)\n")
    L.append("Criteria: `target` = METRICS 1a Target tier for thin cracks: MAE <= 0.05 mm, P95 <= 0.10 mm, |bias| <= 0.02 mm, "
             "|ratio-1| <= 0.05, COV <= 12 %; `MAE<=0.05mm` alone; `px-equiv` = METRICS 1b RMSE <= 0.5 px-equivalent "
             f"(0.5/ppm mm). Sweep: {', '.join(f'{x:g}' for x in ppms)} and native 252.\n")
    tr = []
    G = {(r["estimator"], r["calib"], r["bin"], r["criterion"]): r["gate_ppm"] for r in gate_rows}
    crit = ["target(MAE,P95,bias,ratio,COV)", "MAE<=0.05mm", "px-equiv(RMSE<=0.5px, w>=1px)"]
    for est in HEADLINE:
        for cal in ("raw", "cal_native", "cal_refit", "added"):
            tr.append([LABEL[est], cal] + [G.get((est, cal, "0.30-0.50mm", c), "n/a") for c in crit]
                      + [G.get((est, cal, "<0.5mm", "MAE<=0.05mm"), "n/a")])
    L.append(md_table(["estimator", "calib", "0.30-0.50: target", "0.30-0.50: MAE<=0.05", "0.30-0.50: px-equiv",
                       "<0.5: MAE<=0.05"], tr))
    L.append("\n`added` = error vs the same estimator at native: target there means MAE <= 0.02 mm, P95 <= 0.04 mm, "
             "|bias| <= 0.01 mm (resolution may use 40 % of the budget); `MAE<=0.05mm` and `px-equiv` use the thresholds as written. "
             "'252' = only native passes.\n")
    L.append("\n**Added MAE (um) with 95 % bootstrap CI over specimen images, bin 0.30-0.50 mm**\n")
    tr = []
    for est in ("cand_area", "loc_fwhm", "loc_blend", "cand_frac"):
        vals = []
        for ppm in ppms:
            r = _lookup(rows, est, "added", psf, ppm, "0.30-0.50mm")
            vals.append("n/a" if r is None else f"{r['mae_mm'] * 1000:.0f} [{r['mae_ci_lo'] * 1000:.0f}, {r['mae_ci_hi'] * 1000:.0f}]")
        tr.append([LABEL[est]] + vals)
    L.append(md_table(["estimator"] + [f"{x:g}" for x in ppms], tr))
    L.append("\n**PSF sensitivity, added MAE (um), bin 0.30-0.50 mm, 3,000-profile subsample**\n")
    tr = []
    for est in ("cand_area", "loc_fwhm", "loc_blend"):
        for sp in sorted({r["psf_sigma_px"] for r in rows}):
            vals = []
            for ppm in ppms:
                r = _lookup(rows, est, "added", sp, ppm, "0.30-0.50mm")
                vals.append("n/a" if r is None else f"{r['mae_mm'] * 1000:.0f}")
            tr.append([LABEL[est], sp] + vals)
    L.append(md_table(["estimator", "PSF sigma px"] + [f"{x:g}" for x in ppms], tr))
    if fid:
        L.append("\n## 6. Fidelity of the 1-D reduction vs the unmodified `measure._measure_one` (straight synthetic crack images)\n")
        tr = []
        for ppm, rr in fid.items():
            for k, v in rr.items():
                tr.append([f"{ppm:g}", k, v["n"], f"{v['median_um']:.1f}", f"{v['p90_um']:.0f}", f"{v['corr']:.3f}",
                           v["fail_adapter"], v["fail_reduction"]])
        L.append(md_table(["px/mm", "estimator", "n", "median |diff| um", "p90 |diff| um", "corr", "adapter refusals", "reduction refusals"], tr))
    L.append("\n## 7. Method summary\n")
    L.append(f"- Simulation: sRGB->linear, exposure normalised to 0.75, Gaussian PSF sigma {psf} px (output px; sensitivity "
             f"{a.sens_psf}), exact box integration at a random sub-pixel phase, Poisson shot noise (full well "
             f"{wb.SimModel().full_well_e:g} e-) + read noise {wb.SimModel().read_e:g} e-, sRGB encode, 8-bit rounding.\n"
             f"- Native blur sigma already in the scans: {native_sigma * 1000:.1f} um (median of wide cracks), added in quadrature "
             "to the `sigma_mm` handed to the blend.\n"
             f"- Calibration: least squares ref = a*pred + b on the {ncal} calibration images at native, frozen (`cal_native`), "
             "or refit at each resolution (`cal_refit`); metrics on the other half. Bootstrap CIs resample specimen images.\n"
             "- Ink reference for the ink / blend estimators: scanner black (linear 0), the analogue of the board's printed black.\n")
    (out / f"{a.tag}_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
