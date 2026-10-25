#!/usr/bin/env python3
"""Cost per 1,000 frames and the cost/latency Pareto chart for the COOL benchmark (D26).

Reads a results directory produced by infra/cool_session.sh:
    RUN/prices.json, RUN/<instance-type>/<build>/<build>.bench.json  (builds: cool, pip, ref, ...)
and writes RUN/cost_table.csv, RUN/cost_summary.json and RUN/pareto.png.

cost per 1,000 frames = (EC2 on-demand $/h + COOL software fee $/h, COOL builds only) / 3600 * 1000 / frames-per-second
fps and the latency distribution come from the measured WxT sweep (W worker processes x T cv2 threads each; one
instance, so the whole instance is billed for every configuration).  The x axis is the p95 end-to-end latency of a
frame (decode + analyze) under that configuration's load.

Usage:  python eval/cool_plot.py eval/results/cool/<timestamp> [--slo-ms 2500] [--builds cool,pip,ref]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

# Okabe-Ito colour-blind safe palette
COLORS = {"cool": "#0072B2", "pip": "#D55E00", "ref": "#009E73", "snap_kon": "#CC79A7", "snap_koff": "#E69F00",
          "cool_t4_bbdt": "#56B4E9", "pip_t4_bbdt": "#8C510A"}
NAMES = {"cool": "COOL (OpenCV 5.1.0-dev + KleidiCV)", "pip": "pip opencv 5.0.0.93", "ref": "self-built 5.0.0 (KleidiCV off)",
         "snap_kon": "self-built 5.x snapshot, KleidiCV on", "snap_koff": "self-built 5.x snapshot, KleidiCV off",
         "cool_t4_bbdt": "COOL + BBDT workaround (multi-thread)", "pip_t4_bbdt": "pip + BBDT (same code path)"}
MARKERS = {"c8g.large": "o", "c8g.xlarge": "s", "c8g.2xlarge": "^"}


def load_rows(run: Path, builds: list[str] | None = None) -> list[dict]:
    pr = json.loads((run / "prices.json").read_text())
    rows = []
    for inst_dir in sorted(p for p in run.iterdir() if p.is_dir() and "c8g." in p.name and not p.name.startswith("failed")):
        itype = inst_dir.name[inst_dir.name.index("c8g."):]
        ec2 = pr["ec2_usd_per_hour"][itype]
        fee = pr["cool_fee_usd_per_hour"][itype]
        for bdir in sorted(p for p in inst_dir.iterdir() if p.is_dir()):
            f = bdir / f"{bdir.name}.bench.json"
            if not f.exists() or (builds and bdir.name not in builds):
                continue
            doc = json.loads(f.read_text())
            usd_h = ec2 + (fee if bdir.name.startswith("cool") else 0.0)
            for spec, r in doc.get("sweep", {}).items():
                if "fps" not in r:
                    continue
                rows.append({"instance": itype, "build": bdir.name, "config": spec, "vcpu": pr["vcpu"][itype],
                             "usd_per_hour": usd_h, "fps": r["fps"], "p50_ms": r["e2e_ms"]["p50"],
                             "p95_ms": r["e2e_ms"]["p95"], "usd_per_1000_frames": usd_h / 3600.0 * 1000.0 / r["fps"],
                             "frames_per_usd": r["fps"] * 3600.0 / usd_h})
    return rows


def pareto(rows: list[dict]) -> list[dict]:
    """Non-dominated rows (lower p95 latency and lower cost are both better)."""
    out = []
    for r in rows:
        if not any((o["p95_ms"] <= r["p95_ms"] and o["usd_per_1000_frames"] <= r["usd_per_1000_frames"]) and
                   (o["p95_ms"] < r["p95_ms"] or o["usd_per_1000_frames"] < r["usd_per_1000_frames"]) for o in rows):
            out.append(r)
    return sorted(out, key=lambda r: r["p95_ms"])


def choose(rows: list[dict], build: str, slo_ms: float) -> dict | None:
    """Production pick: cheapest per 1,000 frames among the build's configurations whose p95 latency meets the SLO."""
    ok = [r for r in rows if r["build"] == build and r["p95_ms"] <= slo_ms]
    return min(ok, key=lambda r: r["usd_per_1000_frames"]) if ok else None


def plot(rows, chosen, out_png, slo_ms):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9.2, 5.6), dpi=140)
    for b in COLORS:
        rs = [r for r in rows if r["build"] == b]
        for r in rs:
            ax.scatter(r["p95_ms"], r["usd_per_1000_frames"], s=46, marker=MARKERS[r["instance"]], c=COLORS[b],
                       alpha=0.85, edgecolors="white", linewidths=0.6, zorder=3)
        pf = pareto(rs)
        if len(pf) > 1:
            ax.plot([r["p95_ms"] for r in pf], [r["usd_per_1000_frames"] for r in pf], c=COLORS[b], lw=1.4, alpha=0.7, zorder=2)
    ax.axvline(slo_ms, c="#555555", ls=":", lw=1)
    ax.text(slo_ms, ax.get_ylim()[1], f" p95 SLO {slo_ms:.0f} ms", va="top", ha="left", fontsize=8, color="#555555")
    if chosen:
        ax.scatter(chosen["p95_ms"], chosen["usd_per_1000_frames"], s=330, marker="*", c="#F0E442", edgecolors="black",
                   linewidths=1.0, zorder=5)
        ax.annotate(f"chosen: {chosen['instance']} {chosen['config']}\n${chosen['usd_per_1000_frames']:.4f}/1,000 frames, "
                    f"p95 {chosen['p95_ms']:.0f} ms", (chosen["p95_ms"], chosen["usd_per_1000_frames"]),
                    xytext=(14, 22), textcoords="offset points", fontsize=8.5,
                    arrowprops=dict(arrowstyle="-", color="black", lw=0.8))
    ax.set_xlabel("p95 end-to-end latency per frame (decode + analyze), ms   (lower is better)")
    ax.set_ylabel("EC2 + COOL fee, USD per 1,000 frames   (lower is better)")
    ax.set_title("PROHORI measurement on Graviton4 (c8g): cost vs latency, by OpenCV build, instance size and WxT config")
    ax.title.set_fontsize(10)
    ax.grid(alpha=0.25)
    hb = [plt.Line2D([], [], marker="o", ls="", c=COLORS[b], label=NAMES[b]) for b in COLORS if any(r["build"] == b for r in rows)]
    hi = [plt.Line2D([], [], marker=m, ls="", c="#444444", label=i) for i, m in MARKERS.items() if any(r["instance"] == i for r in rows)]
    leg1 = ax.legend(handles=hb, loc="upper right", fontsize=8, title="OpenCV build", title_fontsize=8)
    ax.add_artist(leg1)
    ax.legend(handles=hi, loc="center right", fontsize=8, title="instance", title_fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--slo-ms", type=float, default=2500.0, help="p95 latency budget used to pick the production config")
    ap.add_argument("--builds", default="", help="comma list (default: every build found)")
    a = ap.parse_args(argv)
    run = Path(a.run)
    rows = load_rows(run, [b for b in a.builds.split(",") if b] or None)
    if not rows:
        print("no sweep rows found")
        return 1
    rows.sort(key=lambda r: (r["instance"], r["build"], r["config"]))
    with open(run / "cost_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    cool_rows = [dict(r, build="cool") if r["build"] == "cool_t4_bbdt" else r for r in rows if r["build"] in ("cool", "cool_t4_bbdt")]
    # the COOL candidates include the multi-thread configs that need the BBDT workaround
    chosen = choose(cool_rows, "cool", a.slo_ms)
    best_other = {b: choose(rows, b, a.slo_ms) for b in sorted({r["build"] for r in rows}) if b != "cool"}
    summ = {"slo_ms": a.slo_ms, "chosen_cool": chosen, "best_per_other_build": best_other,
            "pareto": {b: pareto([r for r in rows if r["build"] == b]) for b in sorted({r["build"] for r in rows})}}
    if chosen:
        summ["cool_vs_best_other_cost_ratio"] = {b: (o["usd_per_1000_frames"] / chosen["usd_per_1000_frames"]) if o else None
                                                 for b, o in best_other.items()}
    (run / "cost_summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    plot(rows, chosen, run / "pareto.png", a.slo_ms)
    print(json.dumps({k: summ[k] for k in ("slo_ms", "chosen_cool", "best_per_other_build", "cool_vs_best_other_cost_ratio") if k in summ}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
