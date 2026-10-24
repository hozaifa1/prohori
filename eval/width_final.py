"""Final report of the D18 width-estimator autoresearch (research/WIDTH_AUTORESEARCH.md).

    python eval/width_final.py --split tune                 # dry run of the whole report on TUNE data (any time)
    python eval/width_final.py --split test --go            # THE one held-out TEST evaluation (refuses to run twice)

Scores the shipped configuration (measure.CFG) next to LEGACY_CFG on the frozen split, with the toner-corrected panel
truth as primary and the nominal truth as secondary, the METRICS 1a tables (all gate states and certified only), tier
checks, the comparison with M2 / S8, per-specimen residuals, error vs px/mm and vs distance from the board, and the
krkCMd black-core convention.  Writes eval/results/width_eval.md (TEST) or width_eval_tune.md (TUNE) plus csv / png.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))
import width_eval as we  # noqa: E402
from prohori import measure  # noqa: E402

RES = we.RES
DONE = we.RUN / "test_run_done.json"
BOARD_W = 140.0
BINS = [("< 0.5 mm", "lt05"), (">= 0.5 mm", "ge05"), ("all", "all")]
SPEC_EDGES = [0, 0.35, 0.45, 0.625, 0.875, 1.25, 1.75, 2.5, 3.01]
SPEC_LAB = [0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
CONFIGS = {"legacy": dict(measure.LEGACY_CFG), "shipped": dict(measure.CFG)}


def boot_mae(err: np.ndarray, groups: np.ndarray, n: int = 1000, seed: int = 0):
    """95 % percentile bootstrap of the MAE over groups (photo groups / render ids), not over individual cracks."""
    err = np.abs(np.asarray(err, float))
    ug = np.unique(groups)
    if len(ug) < 2:
        return (np.nan, np.nan)
    idx = {g: np.nonzero(groups == g)[0] for g in ug}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = rng.choice(ug, len(ug))
        out.append(np.concatenate([err[idx[g]] for g in pick]).mean())
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def collect(which: str):
    out = {}
    for name, cfg in CONFIGS.items():
        ev = we.evaluate(cfg, which)
        p, s = ev["panel"].copy(), ev["synth"].copy()
        s = s[s.nom <= we.SYNTH_MAX_W]
        out[name] = {"panel": p, "synth": s, "S": ev["S"]}
    return out


def table_rows(df: pd.DataFrame, tcol: str, label: str, u_ref: float | None):
    rows = []
    bs = we.bin_stats(df, "width_mm", tcol)
    for gname, gl in (("all gate states", "all"), ("certified only", "cert")):
        for bl, bk in BINS:
            st = bs.get(f"{gl}/{bk}", {"n": 0})
            if st.get("n", 0) == 0:
                continue
            sub = df if gl == "all" else df[df.certified]
            sub = sub if bk == "all" else (sub[sub.nom < 0.5] if bk == "lt05" else sub[sub.nom >= 0.5])
            lo, hi = boot_mae((sub.width_mm - sub[tcol]).values, sub.group.values)
            rows.append({"set": label, "gate": gname, "bin": bl, "n": st["n"], "bias": st["bias"], "MAE": st["MAE"],
                         "MAE_lo": lo, "MAE_hi": hi, "P95": st["P95"], "ratio": st["ratio"], "COV": st["COV"],
                         "MRE": st["MRE"], "U_ref": u_ref})
    return pd.DataFrame(rows)


def fmt(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def md_table(df: pd.DataFrame, cols: list[str], nd: dict | None = None) -> str:
    nd = nd or {}
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    body = ""
    for _, r in df.iterrows():
        body += "| " + " | ".join(
            (str(r[c]) if not isinstance(r[c], (float, np.floating)) else
             (f"{100 * r[c]:.1f} %" if c in ("COV", "MRE") else
              (str(int(r[c])) if c.endswith("n") and float(r[c]).is_integer() else fmt(float(r[c]), nd.get(c, 3))))) for c in cols) + " |\n"
    return head + body


def tier_check(rows: pd.DataFrame, label: str) -> list[str]:
    """Pass / fail of the METRICS 1a tiers on the (primary-truth, certified) numbers and on all gate states."""
    lines = []
    for gate in ("all gate states", "certified only"):
        r = rows[(rows.gate == gate) & (rows.set == label)]
        t = {b: r[r.bin == b].iloc[0] for b in ("< 0.5 mm", ">= 0.5 mm", "all") if len(r[r.bin == b])}
        if "all" not in t:
            continue
        a = t["all"]
        lt = t.get("< 0.5 mm")
        ge = t.get(">= 0.5 mm")
        f = {"MAE <= 0.09": a.MAE <= 0.09, "MRE <= 14.4 %": a.MRE <= 0.144}
        tg = {"MAE <= 0.05": a.MAE <= 0.05, "P95 <= 0.10": a.P95 <= 0.10, "|bias| <= 0.02": abs(a.bias) <= 0.02}
        st = {"MAE <= 0.03": a.MAE <= 0.03}
        if lt is not None:
            f["< 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %"] = (0.89 <= lt.ratio <= 1.11) and lt.COV <= 0.219
            tg["< 0.5 mm |ratio-1| <= 0.05, COV <= 12 %"] = abs(lt.ratio - 1) <= 0.05 and lt.COV <= 0.12
            st["< 0.5 mm COV <= 8 %"] = lt.COV <= 0.08
        if ge is not None:
            f[">= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %"] = (0.98 <= ge.ratio <= 1.02) and ge.COV <= 0.058
            tg[">= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %"] = abs(ge.ratio - 1) <= 0.02 and ge.COV <= 0.04
            st[">= 0.5 mm COV <= 3 %"] = ge.COV <= 0.03
        for tier, d in (("Floor", f), ("Target", tg), ("Stretch", st)):
            lines.append(f"| {label} / {gate} | {tier} | " + "; ".join(f"{k}: {'PASS' if v else 'fail'}" for k, v in d.items()) + " |")
    return lines


def spec_table(df: pd.DataFrame, panel: bool) -> pd.DataFrame:
    d = df.copy()
    d["bin"] = pd.cut(d.nom, SPEC_EDGES, labels=SPEC_LAB)
    d["e_cor"] = d.width_mm - d.true
    d["e_nom"] = d.width_mm - d.true_nom
    g = d.groupby("bin", observed=True)
    out = pd.DataFrame({"n": g.size(), "bias_cor": g.e_cor.mean(), "MAE_cor": g.e_cor.apply(lambda x: x.abs().mean())})
    if panel:
        out["bias_nom"] = g.e_nom.mean()
        out["MAE_nom"] = g.e_nom.apply(lambda x: x.abs().mean())
    out.index = [float(i) for i in out.index]
    return out


def krk_block(cfgs: dict, which: str, workers: int = 3):
    import width_krk as wk
    res = {}
    for name, cfg in cfgs.items():
        t = time.time()
        out = wk.run(cfg, which, workers, ppms=(10.0, 15.0, 20.0))
        res[name] = {f"{p:g}": wk.metrics(out, p) for p in (10.0, 15.0, 20.0)}
        print(f"krk {which} {name} {time.time() - t:.0f}s", flush=True)
    return res


def figures(R: dict, which: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    RES.mkdir(parents=True, exist_ok=True)
    sfx = "" if which == "test" else "_tune"
    col = {"legacy": "#7f7f7f", "shipped": "#1f77b4"}
    # 1. error distribution
    fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=False)
    for a, (key, ttl) in zip(ax, (("panel", f"Printed panel photos, toner-corrected truth ({which})"),
                                  ("synth", f"Photoreal renders, exact truth ({which})"))):
        for name in ("legacy", "shipped"):
            df = R[name][key]
            e = (df.width_mm - df.true).values
            a.hist(e, bins=np.linspace(-1.0, 1.0, 81), alpha=0.55, color=col[name],
                   label=f"{name}: MAE {np.abs(e).mean():.3f}, P95 {np.percentile(np.abs(e), 95):.3f} mm")
        a.axvline(0, color="k", lw=0.8)
        a.set_xlabel("width error (measured - truth), mm")
        a.set_ylabel("cracks")
        a.set_title(ttl, fontsize=10)
        a.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(RES / f"width_error_distribution{sfx}.png", dpi=140)
    plt.close(fig)
    # 2. error vs px/mm (sources: panel + synth) and krkCMd resolution-added error
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for name in ("legacy", "shipped"):
        d = pd.concat([R[name]["panel"].assign(src="panel"), R[name]["synth"].assign(src="synth")])
        d = d[d.ppm > 0]
        d["ae"] = (d.width_mm - d.true).abs()
        edges = [8, 10, 12, 14, 16, 20, 40]
        d["b"] = pd.cut(d.ppm, edges)
        g = d.groupby("b", observed=True).ae.agg(["mean", "size"])
        mids = [0.5 * (i.left + i.right) for i in g.index]
        ax[0].plot(mids, g["mean"], "o-", color=col[name], label=name)
    ax[0].set_xlabel("native px/mm at the crack")
    ax[0].set_ylabel("MAE, mm (panel + renders)")
    ax[0].legend()
    ax[0].set_title("Error vs resolution (real photos + renders)", fontsize=10)
    if "krk" in R:
        for name in ("legacy", "shipped"):
            xs = [10, 15, 20]
            ax[1].plot(xs, [R["krk"][name][f"{p}"]["added_full"] for p in xs], "o-", color=col[name], label=f"{name}, headline width")
        ax[1].plot([10, 15, 20], [R["krk"]["shipped"][f"{p}"]["added_fwhm"] for p in (10, 15, 20)], "s--", color="#d62728",
                   label="FWHM alone (reference)")
        ax[1].set_xlabel("simulated px/mm")
        ax[1].set_ylabel("resolution-added error, mm (0.30-0.50 mm, krkCMd)")
        ax[1].legend(fontsize=8)
        ax[1].set_title("krkCMd: cost of low resolution", fontsize=10)
    fig.tight_layout()
    fig.savefig(RES / f"width_error_vs_ppm{sfx}.png", dpi=140)
    plt.close(fig)
    # 3. distance from the board
    fig, ax = plt.subplots(figsize=(6, 4))
    for name in ("legacy", "shipped"):
        d = R[name]["panel"]
        d = d[(d.sigma_mm <= 0.15) & (d.obliq <= 25)].copy()
        d["dist"] = d.id.map(DIST_BW)
        d["rel"] = d.width_mm / d.true - 1
        g = d.groupby("dist").rel.agg(["mean", "std", "size"])
        ax.errorbar(g.index, 100 * g["mean"], 100 * g["std"] / np.sqrt(g["size"]), fmt="o-", color=col[name], label=name, capsize=2)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("distance of the specimen from the board edge (board widths of 140 mm)")
    ax.set_ylabel("relative width error, % (sharp, frontal photos)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RES / f"width_distance{sfx}.png", dpi=140)
    plt.close(fig)


# specimen centre distance from the board edge (board y = 100 mm), in board widths
DIST_BW = {"C1": 32 / BOARD_W, "C2": 32 / BOARD_W, "C3": 66 / BOARD_W, "C4": 66 / BOARD_W, "C5": 100 / BOARD_W,
           "C6": 100 / BOARD_W, "C7": 134 / BOARD_W, "C8": 134 / BOARD_W}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["tune", "test"], default="tune")
    ap.add_argument("--go", action="store_true", help="required for --split test (the one held-out evaluation)")
    ap.add_argument("--no-krk", action="store_true")
    a = ap.parse_args()
    if a.split == "test":
        if not a.go:
            sys.exit("refusing: the TEST split needs --go (orchestrator approval)")
        if DONE.exists():
            sys.exit(f"refusing: TEST already evaluated ({DONE})")
    pool = we.bleed_pool()
    u_ref = 2.0 * pool["u"]
    R = collect(a.split)
    if not a.no_krk:
        R["krk"] = krk_block(CONFIGS, a.split)
    # --- tables
    rows = []
    for name in ("shipped", "legacy"):
        rows.append(table_rows(R[name]["panel"], "true", f"{name} / panel (toner-corrected truth)", u_ref))
        rows.append(table_rows(R[name]["panel"], "true_nom", f"{name} / panel (nominal truth)", None))
        rows.append(table_rows(R[name]["synth"], "true", f"{name} / synthetic (exact truth)", None))
    T = pd.concat(rows, ignore_index=True)
    sfx = "" if a.split == "test" else "_tune"
    T.to_csv(RES / f"width_eval{sfx}_tables.csv", index=False)
    spec = {}
    for name in ("shipped", "legacy"):
        sp = spec_table(R[name]["panel"], True).add_prefix("panel_").join(spec_table(R[name]["synth"], False).add_prefix("synth_"))
        spec[name] = sp
        sp.to_csv(RES / f"width_eval{sfx}_specimens_{name}.csv")
    figures(R, a.split)
    # --- markdown
    md = [f"# Crack-width estimator: {'held-out TEST' if a.split == 'test' else 'TUNE (dry run, not the claim)'} evaluation (D18)\n\n"]
    md.append(f"*Generated {time.strftime('%Y-%m-%d %H:%M')} by `eval/width_final.py --split {a.split}`. Shipped configuration `measure.CFG` = "
              f"`{json.dumps(CONFIGS['shipped'])}`; LEGACY = `measure.LEGACY_CFG` (the 2026-10-19 estimator). The frozen certification gate "
              f"(`gate_params.json`, fitted on the legacy widths) is used unchanged for the certified-only rows.*\n\n")
    md.append(f"**Reference.** Panel primary truth = nominal stroke width + 2 b (toner bleed b measured from the printed ChArUco squares, "
              f"METRICS 1a): b_y = {pool['by']:.4f} mm across the horizontal specimens (b_x = {pool['bx']:.4f}), pooled over {pool['n']} "
              f"capture-quality-selected photos; **U_ref = +-{u_ref:.3f} mm** on the reference (across-photo spread). Errors below U_ref are not "
              f"meaningful (METRICS section 0 rule 5). Synthetic truth is exact. MAE columns carry a 95 % bootstrap CI over photo groups / render ids.\n\n")
    cols = ["gate", "bin", "n", "bias", "MAE", "MAE_lo", "MAE_hi", "U_ref", "P95", "ratio", "COV", "MRE"]
    for label in [f"{n} / {k}" for n in ("shipped", "legacy") for k in ("panel (toner-corrected truth)", "synthetic (exact truth)", "panel (nominal truth)")]:
        sub = T[T.set == label]
        if len(sub):
            md.append(f"### {label}\n\n" + md_table(sub, cols) + "\n")
    md.append("### Tier check (METRICS 1a), shipped configuration, primary truth\n\n| set | tier | criteria |\n|---|---|---|\n")
    for lab in ("shipped / panel (toner-corrected truth)", "shipped / synthetic (exact truth)"):
        md.append("\n".join(tier_check(T, lab)) + "\n")
    md.append("\n### Per-specimen residuals (bias / MAE in mm; nominal truth next to corrected truth)\n")
    for name in ("shipped", "legacy"):
        md.append(f"\n**{name}**\n\n" + md_table(spec[name].reset_index().rename(columns={"index": "width mm"}),
                                                  list(spec[name].reset_index().rename(columns={"index": "width mm"}).columns)) + "\n")
    if "krk" in R:
        md.append("\n### krkCMd (black-core convention and resolution cost)\n\n| config | px/mm | headline resolution-added (0.30-0.50 mm) | FWHM alone | black-core MAE vs MANwidth (gate bin) | black-core RMSE vs MANwidth (all crack-present) |\n|---|---|---|---|---|---|\n")
        for name in ("shipped", "legacy"):
            for p in ("10", "15", "20"):
                m = R["krk"][name][p]
                md.append(f"| {name} | {p} | {fmt(m['added_full'])} | {fmt(m['added_fwhm'])} | {fmt(m['vsman_core_mae'])} | {fmt(m['core_rmse_all'])} |\n")
        md.append("\nPublished analytic edge detector (M1): RMSE 56 um on all profiles at 252 px/mm; inter-operator floor 16.6 um. The rows above are at simulated PHONE resolution (not comparable one-to-one to native 252 px/mm).\n")
    (RES / ("width_eval.md" if a.split == "test" else "width_eval_tune.md")).write_text("".join(md), encoding="utf-8")
    if a.split == "test":
        DONE.write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "cfg": CONFIGS["shipped"]}))
    print("written", RES / ("width_eval.md" if a.split == "test" else "width_eval_tune.md"))


if __name__ == "__main__":
    main()
