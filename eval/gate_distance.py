"""Distance-from-board candidates for the certification gate (pre-registered in research/GATE_NOTES.md section 8).

Same data, same 100 grouped splits (rng seed 11, 6 held-out source photos each), same pipeline and the same level
(alpha_cal = 0.05 default) as eval/gate_fit.py, paired by split.  Configurations:
  base   the refitted gate (gate.FEATURES, mask QA)
  F      + monotone feature dist_bw (centroid distance from the board edge, board widths)           [candidate]
  R      + hard rule: farther than 0.7 board widths only with obliquity <= 25 deg and blur sigma <= 0.15 mm   [candidate]
  Ffar   + dist_far_bw (farthest polyline vertex instead of the centroid)                              [sensitivity]
  R0.75  rule with 0.75 board widths instead of 0.7                                                    [sensitivity]

Acceptance (fixed before fitting): A = mean held-out CRC risk <= 5 % and mean certified fraction not more than 2 points below
base; B = at equal coverage (base's certified fraction at alpha_cal = 0.05) the interpolated held-out risk is lower by
>= 0.3 points on average and in >= 60 of the splits.

Usage: python eval/gate_distance.py [--features file.parquet] [--reps 100] [--workers 6] [--out eval/results/gate_distance.md]
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "src"))
import gate_lib as L  # noqa: E402
from prohori import gate as G  # noqa: E402

RES = ROOT / "eval" / "results"
SEED = 11
TEST_GROUPS_N = 6
ALPHA = 0.05
A_NO_HARM_COVERAGE_DROP = 0.02
B_MIN_GAIN = 0.003
B_MIN_SPLITS = 60
DIST_MAX_BW = 0.7
OBLIQ_MAX, SIGMA_MAX_MM = 25.0, 0.15
CONFIGS = ["base", "F", "R", "Ffar", "R0.75"]
_C: dict = {}


def pct(x, nd=1):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{nd}f}%"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def build(df):
    """Per-configuration data dicts (X, feature names, QA mask) sharing the target / groups / truth arrays."""
    D = L.prepare(df)
    qa0 = L.qa_pass(D["raws"])
    alt = L.alt_truth(df)
    D["wrong_alt"], D["err_alt"] = alt["wrong_corr"], alt["err_corr"]
    dist, dfar = df["dist_bw"].values, df["dist_far_bw"].values
    obl, sig = df["obs_obliquity_deg"].values, df["obs_blur_sigma_mm"].values
    good = (obl <= OBLIQ_MAX) & (sig > 0) & (sig <= SIGMA_MAX_MM)

    def rule(th):
        return ~((dist > th) & ~good)
    base = dict(D, qa=qa0, feats=list(G.FEATURES))
    cfg = {"base": base,
           "F": dict(D, X=np.column_stack([D["X"], dist]), feats=list(G.FEATURES) + ["dist_bw"], qa=qa0),
           "Ffar": dict(D, X=np.column_stack([D["X"], dfar]), feats=list(G.FEATURES) + ["dist_far_bw"], qa=qa0),
           "R": dict(D, qa=qa0 & rule(DIST_MAX_BW), feats=list(G.FEATURES)),
           "R0.75": dict(D, qa=qa0 & rule(0.75), feats=list(G.FEATURES))}
    return cfg, D


def _init(cfgs):
    global _C
    _C = cfgs
    os.environ["OMP_NUM_THREADS"] = "1"


def job(args):
    rep, te_groups, groups, seed = args
    tr = [g for g in groups if g not in te_groups]
    out = {"rep": rep, "cfg": {}}
    for name in CONFIGS:
        Dc = _C[name]
        P = L.fit_pipeline(Dc, tr, alphas=L.ALPHAS, seed=seed, interval_variants=[("learned", True, False, 0.9)],
                           interval_alpha=ALPHA)
        pred = L.predict_many(P["model"], Dc["X"])
        te = np.isin(Dc["group"], te_groups)
        Dalt = dict(Dc, wrong=Dc["wrong_alt"])
        res = {}
        for k, lv in P["levels"].items():
            e = L.eval_gate(Dc, te, pred, Dc["qa"], lv["theta"])
            ea = L.eval_gate(Dalt, te, pred, Dc["qa"], lv["theta"])
            res[k] = {"risk": e["joint_risk_capture"], "cond": e["cond_risk"], "cert": e["cert_rate"],
                      "risk_alt": ea["joint_risk_capture"], "cond_alt": ea["cond_risk"]}
        out["cfg"][name] = res
    return out


def risk_at_cert(res, target_cert):
    """Held-out risk of one configuration's alpha ladder interpolated at a given certified fraction."""
    ks = sorted(res, key=float)
    c = np.array([res[k]["cert"] for k in ks])
    r = np.array([res[k]["risk"] for k in ks])
    o = np.argsort(c)
    return float(np.interp(target_cert, c[o], r[o]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=None)
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=str(RES / "gate_distance.md"))
    a = ap.parse_args()
    t0 = time.time()
    df = L.load_rows(a.features)
    cfgs, D = build(df)
    groups = sorted(set(D["group"]))
    rng = np.random.default_rng(SEED)
    jobs = [(r, sorted(rng.choice(groups, TEST_GROUPS_N, replace=False)), groups, 100 + r) for r in range(a.reps)]
    print(f"{len(df)} rows, {len(groups)} groups, {a.reps} splits x {len(CONFIGS)} configs", flush=True)
    with mp.Pool(a.workers, initializer=_init, initargs=(cfgs,)) as pool:
        R = []
        for i, o in enumerate(pool.imap(job, jobs, chunksize=1)):
            R.append(o)
            if i % 10 == 0:
                print(f"  {i + 1}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    k5 = f"{ALPHA:g}"
    md = ["# Distance-from-board candidates for the gate (pre-registered, `research/GATE_NOTES.md` section 8)\n",
          f"Generated by `eval/gate_distance.py` from `{a.features or 'eval/results/gate_calibration_features.parquet'}`: {len(df)} crack "
          f"measurements, {len(groups)} source photos, {a.reps} grouped splits ({TEST_GROUPS_N} held-out photos each, the same splits as "
          f"`gate_fit.py`), alpha_cal = {ALPHA}.  Mean [5th, 95th percentile] over splits; paired by split.\n"]

    # --- diagnostics of the feature itself
    v0 = df["v"].values == 0
    lay = df["dist_layout_bw"].values
    d = df["dist_bw"].values
    ok = np.isfinite(lay)
    md.append("## 1. Does the deployable estimate match the printed layout?\n")
    rows = []
    for ident in sorted(df["crack"].unique()):
        m = (df["crack"].values == ident) & v0
        if m.sum():
            rows.append([ident, f"{df['true_mm'].values[m][0]:g}", f"{lay[m][0]:.3f}", f"{np.mean(d[m]):.3f}",
                         f"{np.mean(df['dist_far_bw'].values[m]):.3f}"])
    md.append("Original photos (variant 0), mean over photos; layout = centre of the specimen below the board edge / 140 mm:\n")
    md.append(md_table(["specimen", "width mm", "layout (truth)", "dist_bw (centroid estimate)", "dist_far_bw"], rows) + "\n")
    err = d[ok] - lay[ok]
    md.append(f"All {int(ok.sum())} rows (all degraded variants): estimate - layout = mean {err.mean():+.3f}, sd {err.std():.3f}, "
              f"P95 |.| {np.percentile(np.abs(err), 95):.3f} board widths (1 board width = 140 mm), correlation {np.corrcoef(d[ok], lay[ok])[0, 1]:.3f}.\n")
    sharp = (df["obs_obliquity_deg"].values <= OBLIQ_MAX) & (df["obs_blur_sigma_mm"].values > 0) & (df["obs_blur_sigma_mm"].values <= SIGMA_MAX_MM)
    md.append(f"Share of rows that satisfy the escape clause (obliquity <= {OBLIQ_MAX:g} deg and blur sigma <= {SIGMA_MAX_MM} mm): "
              f"{pct(sharp.mean())} of all rows, {pct(sharp[v0].mean())} of the original photos.  Rows beyond {DIST_MAX_BW} board widths: "
              f"{pct((d > DIST_MAX_BW).mean())}.\n")

    # --- table
    def agg(name, key, f=lambda r, k: r[k]):
        return np.array([R_["cfg"][name][k5][key] for R_ in R], float)

    base_cert = agg("base", "cert")
    base_risk = agg("base", "risk")
    md.append("## 2. Held-out result at alpha_cal = 0.05 (pre-registered comparison)\n")
    rows, verdict = [], {}
    for name in CONFIGS:
        risk, cond, cert = agg(name, "risk"), agg(name, "cond"), agg(name, "cert")
        eq = np.array([risk_at_cert(R_["cfg"][name], base_cert[i]) for i, R_ in enumerate(R)])
        eq_base = np.array([risk_at_cert(R_["cfg"]["base"], base_cert[i]) for i, R_ in enumerate(R)])
        gain = eq_base - eq
        A = bool(risk.mean() <= 0.05 and cert.mean() >= base_cert.mean() - A_NO_HARM_COVERAGE_DROP)
        B = bool(gain.mean() >= B_MIN_GAIN and (gain > 0).sum() >= B_MIN_SPLITS)
        verdict[name] = {"A": A, "B": B, "risk": float(risk.mean()), "cert": float(cert.mean()), "gain_eq": float(gain.mean()),
                         "splits_improved": int((gain > 0).sum())}
        q = lambda x, f=pct: f"{f(x.mean())} [{f(np.percentile(x, 5))}, {f(np.percentile(x, 95))}]"  # noqa: E731
        rows.append([name, q(risk, lambda v: pct(v, 2)), q(cond), q(cert), f"{100 * (cert.mean() - base_cert.mean()):+.1f} pts",
                     f"{100 * gain.mean():+.2f} pts ({int((gain > 0).sum())}/{len(R)})",
                     "yes" if A else "no", "yes" if B else "no"])
    md.append(md_table(["config", "held-out risk (CRC loss)", "P(wrong|cert)", "cracks certified", "certified vs base",
                        "risk gain at equal coverage (splits improved)", "A: no harm", "B: gain"], rows) + "\n")
    md.append("Configs F and R are the pre-registered candidates; Ffar and R0.75 are sensitivity variants only.\n")

    # --- ladders
    md.append("## 3. Whole alpha ladder (mean over splits): certified fraction and held-out CRC risk\n")
    rows = []
    for k in sorted(R[0]["cfg"]["base"], key=float):
        row = [k]
        for name in ("base", "F", "R"):
            c = np.mean([R_["cfg"][name][k]["cert"] for R_ in R])
            r = np.mean([R_["cfg"][name][k]["risk"] for R_ in R])
            row.append(f"{pct(c)} / {pct(r, 2)}")
        rows.append(row)
    md.append(md_table(["alpha_cal", "base: cert / risk", "F: cert / risk", "R: cert / risk"], rows) + "\n")

    # --- secondary truth
    md.append("## 4. Same certified sets against the toner-corrected width (secondary)\n")
    rows = []
    for name in CONFIGS:
        ra, ca = agg(name, "risk_alt"), agg(name, "cond_alt")
        rows.append([name, pct(ra.mean(), 2), pct(np.nanmean(ca))])
    md.append(md_table(["config", "held-out risk (CRC loss)", "P(wrong|cert)"], rows) + "\n")

    # --- where the extra certified/uncertified rows sit, by true width (full-data refit, in-sample, descriptive only)
    Pb = L.fit_pipeline(cfgs["base"], groups, alphas=[ALPHA], seed=3, interval_variants=[("learned", True, False, 0.9)])
    PF = L.fit_pipeline(cfgs["F"], groups, alphas=[ALPHA], seed=3, interval_variants=[("learned", True, False, 0.9)])
    cert_b = cfgs["base"]["qa"] & (L.predict_many(Pb["model"], cfgs["base"]["X"]) <= Pb["levels"][k5]["theta"])
    cert_f = cfgs["F"]["qa"] & (L.predict_many(PF["model"], cfgs["F"]["X"]) <= PF["levels"][k5]["theta"])
    cert_r = cfgs["R"]["qa"] & cert_b
    md.append("## 5. By true width (fit on all groups, in-sample, descriptive; certified fraction / P(wrong | certified))\n")
    rows = []
    wr = D["wrong"]
    for w in [0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
        m = np.isclose(D["true"], w)
        row = [f"{w:g}", f"{lay[m & ok][0] if (m & ok).any() else float('nan'):.2f}"]
        for c in (cert_b, cert_f, cert_r):
            cc = m & c
            row.append(f"{pct(cc.sum() / m.sum())} / {pct(float((cc & wr).sum() / max(cc.sum(), 1)))}")
        rows.append(row)
    md.append(md_table(["width mm", "layout distance (bw)", "base", "F", "R (rule on base theta)"], rows) + "\n")
    imp = None
    try:
        from sklearn.inspection import permutation_importance
        imp = permutation_importance(PF["model"]["_sk"], cfgs["F"]["X"], cfgs["F"]["y"], n_repeats=3, random_state=0, n_jobs=1)
        order = np.argsort(-imp.importances_mean)[:8]
        md.append("Permutation importance in the fitted F model (top 8): " + ", ".join(
            f"`{cfgs['F']['feats'][i]}` {imp.importances_mean[i]:.3f}" for i in order) + "\n")
    except Exception as e:  # pragma: no cover
        md.append(f"(importance unavailable: {e})\n")

    md.append("## 6. Decision\n")
    for name in ("F", "R"):
        v = verdict[name]
        md.append(f"* **{name}**: A (no harm) = {v['A']}, B (gain at equal coverage) = {v['B']} (mean gain {100 * v['gain_eq']:+.2f} points, "
                  f"improved in {v['splits_improved']}/{len(R)} splits); risk {pct(v['risk'], 2)}, certified {pct(v['cert'])} "
                  f"(base {pct(float(base_cert.mean()))}, risk {pct(float(base_risk.mean()), 2)}).")
    md.append("\n**Confound.** In the panel layout the distance is collinear with the width (two widths per distance), so a held-out "
              "gain here can come from the feature standing in for the specimen identity.  See `research/ERROR_BUDGET.md` for a "
              "synthetic control in which width is fixed and the distance varied.\n")
    Path(a.out).write_text("\n".join(md) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    print("done", f"{time.time() - t0:.0f}s", flush=True)
    print(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    main()
