"""Regenerate every result chart for the demo video as clean 1920x1080 PNGs (dark theme, large type).

Usage:
    python tools/video_charts.py                         # everything
    python tools/video_charts.py ablation gate width cool failures svg
    python tools/video_charts.py ablation --ablation-md eval/results/agent_ablation_v2.md --ablation-out ablation_v2.png

Inputs are re-read from the result files each time (nothing is hard-coded except labels):
    eval/results/agent_ablation.md        compound subset, recovery within 3 actions  -> ablation.png / ablation_v2.png
    eval/results/gate_summary.json        held-out risk / coverage per CRC level      -> gate_risk_coverage.png
    eval/results/width_eval_specimens_shipped.csv, width_eval_tables.csv              -> width_error.png
    eval/results/cool_agentloop/trace.jsonl                                           -> cool_latency.png
    docs/exhibits/gallery/*.json + overlays                                           -> failure_gallery.png
    docs/figures/{architecture,agent_workflow}.svg                                    -> *_full.png + zoomed crops

After the agent rerun: write the new table to a markdown file with the same layout as agent_ablation.md and run
    python tools/video_charts.py ablation --ablation-md <new.md> --ablation-out ablation_v2.png
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_common as vc  # noqa: E402

ROOT = vc.ROOT
RES = ROOT / "eval" / "results"
OUT = vc.ASSETS / "charts"

FONTS = None


def fp(weight: str, size: float):
    from matplotlib import font_manager as fm
    name = {"r": "Geist-Regular", "s": "Geist-SemiBold", "b": "Geist-Bold", "m": "GeistMono-Medium"}[weight]
    return fm.FontProperties(fname=str(FONTS[name]), size=size * 0.72)  # sizes are pixels at 1920x1080 (dpi 100)


def new_fig():
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    return fig, plt


def header(fig, kicker: str, title: str, sub: str | None = None):
    fig.text(0.073, 0.93, kicker.upper(), fontproperties=fp("m", 22), color=vc.MUTED)
    fig.text(0.073, 0.865, title, fontproperties=fp("b", 54), color=vc.TEXT)
    if sub:
        fig.text(0.073, 0.815, sub, fontproperties=fp("r", 27), color=vc.MUTED)


def footer(fig, text: str):
    fig.text(0.073, 0.035, text, fontproperties=fp("m", 17), color=vc.MUTED)


def save(fig, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    fig.savefig(p, dpi=100)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print("wrote", p.relative_to(ROOT))


# ------------------------------------------------------------------ 1. agent ablation
def parse_ablation(md: Path):
    """compound-subset row of the 'recovery within 3 actions' headline table.
    Cell format: '85% [75, 94]'. Columns: P0 random, P1 rules, P2 LLM, P* label rule."""
    text = md.read_text(encoding="utf-8")
    sec = text.split("## Headline", 1)[1].split("###", 1)[0]
    for line in sec.splitlines():
        if line.startswith("| compound"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            n = int(cells[1])
            vals = []
            for c in cells[2:6]:
                m = re.match(r"(\d+)% \[(\d+), (\d+)\]", c)
                vals.append(tuple(int(x) for x in m.groups()))
            return n, vals
    raise ValueError("compound row not found in " + str(md))


def chart_ablation(md: Path, out_name: str):
    n, vals = parse_ablation(md)
    labels = ["Random\nactions", "Fixed rules\n(we wrote)", "AI agent\n(LLM)", "Label ceiling\n(upper bound)"]
    colors = ["#6b7f93", vc.BLUE, vc.AMBER, vc.SURFACE2]
    fig, plt = new_fig()
    header(fig, "Agent ablation, held-out simulator episodes",
           "Several problems at once: who gets it certified?",
           f"Episodes certified within 3 agent actions, compound-failure subset (n = {n}). Whiskers: 95% bootstrap CI.")
    ax = fig.add_axes([0.09, 0.17, 0.86, 0.60])
    for i, (v, lo, hi) in enumerate(vals):
        edge = vc.MUTED if i == 3 else colors[i]
        ax.bar(i, v, width=0.62, color=colors[i], edgecolor=edge, linewidth=3, linestyle="--" if i == 3 else "-", zorder=3)
        ax.errorbar(i, v, yerr=[[v - lo], [hi - v]], color=vc.TEXT, capsize=14, capthick=3, elinewidth=3, zorder=4)
        ax.text(i, hi + 3.0, f"{v}%", ha="center", va="bottom", fontproperties=fp("b", 72),
                color=vc.AMBER if i == 2 else vc.TEXT)
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, fontproperties=fp("s", 32), color=vc.TEXT)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)], fontproperties=fp("m", 22))
    ax.grid(axis="y", color=vc.LINE, lw=1.5, zorder=0)
    ax.tick_params(length=0, pad=14)
    for s in ax.spines.values():
        s.set_visible(False)
    footer(fig, f"Source: {md.relative_to(ROOT).as_posix()}  |  the agent sees only OpenCV's numbers  |  simulator study")
    save(fig, out_name)


# ------------------------------------------------------------------ 2. gate risk / coverage
def pct(s: str):
    m = re.match(r"([\d.]+)% \[([\d.]+)%, ([\d.]+)%\]", s)
    return tuple(float(x) for x in m.groups())


def chart_gate():
    d = json.load(open(RES / "gate_summary.json", encoding="utf-8"))
    rows = d["repeated"]  # alpha -> [risk, risk(alt), P(wrong|certified) CI, certified fraction CI, ..]
    pts = {a: (pct(r[3]), pct(r[2])) for a, r in rows.items()}  # alpha -> ((cov, lo, hi), (wrong, lo, hi))
    strict, default = d["strict_level"], d["default_level"]
    fig, plt = new_fig()
    header(fig, "Quality gate, calibrated with conformal risk control",
           "Stricter gate, fewer wrong numbers",
           "Held-out source photos only. Each dot is one gate setting; whiskers (90%) on the two highlighted settings.")
    ax = fig.add_axes([0.09, 0.17, 0.55, 0.58])
    xs = [pts[a][0][0] for a in pts]
    ys = [pts[a][1][0] for a in pts]
    ax.plot(xs, ys, color=vc.LINE, lw=3, zorder=1)
    for a, ((cx, clo, chi), (wy, wlo, whi)) in pts.items():
        hi_ = a in (strict, default)
        col = vc.OK if a == strict else vc.AMBER if a == default else "#6b7f93"
        if hi_:
            ax.errorbar(cx, wy, xerr=[[cx - clo], [chi - cx]], yerr=[[wy - wlo], [whi - wy]], fmt="none", ecolor=col, elinewidth=2.5, alpha=.6, zorder=2)
        ax.plot(cx, wy, "o", ms=24 if hi_ else 12, color=col, zorder=3, mec=vc.BG, mew=2)
    ax.set_xlim(10, 62)
    ax.set_ylim(0, 36)
    ax.set_xlabel("Cracks that get a number (% of measured cracks)", fontproperties=fp("s", 26), color=vc.MUTED, labelpad=14)
    ax.set_ylabel("Readings outside tolerance (% of certified)", fontproperties=fp("s", 26), color=vc.MUTED, labelpad=14)
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_fontproperties(fp("m", 22))
    ax.grid(color=vc.LINE, lw=1.2)
    ax.tick_params(length=0, pad=10)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    (sx, _, _), (sw, _, _) = pts[strict]
    (dx, _, _), (dw, _, _) = pts[default]
    ax.annotate("GREEN: certified", xy=(sx, sw), xytext=(11.5, 15), fontproperties=fp("b", 32), color=vc.OK, va="center",
                arrowprops=dict(arrowstyle="-", color=vc.OK, lw=2.5, shrinkA=6, shrinkB=12))
    ax.annotate("AMBER: indicative", xy=(dx, dw), xytext=(11.5, 25), fontproperties=fp("b", 32), color=vc.AMBER, va="center",
                arrowprops=dict(arrowstyle="-", color=vc.AMBER, lw=2.5, shrinkA=6, shrinkB=12))

    def big(y, col, head, num, rest):
        fig.text(0.69, y, head, fontproperties=fp("m", 24), color=col)
        fig.text(0.69, y - 0.115, num, fontproperties=fp("b", 120), color=col)
        fig.text(0.69, y - 0.155, rest, fontproperties=fp("r", 28), color=vc.TEXT, linespacing=1.3)
    big(0.725, vc.OK, "GREEN  (level 0.01)", f"{pts[strict][1][0]:g}%", f"wrong, at {pts[strict][0][0]:g}% of cracks certified")
    big(0.43, vc.AMBER, "AMBER  (level 0.05)", f"{pts[default][1][0]:g}%", f"wrong, at {pts[default][0][0]:g}% of cracks given a number")
    fig.text(0.69, 0.14, "About 97 in 100 green readings\nwere within tolerance.", fontproperties=fp("s", 30), color=vc.TEXT, linespacing=1.3)
    footer(fig, "Source: eval/results/gate_summary.json, gate_report.md  |  one printed sheet, one phone: not a field test")
    save(fig, "gate_risk_coverage.png")


# ------------------------------------------------------------------ 3. width error
def chart_width():
    rows = list(csv.DictReader(open(RES / "width_eval_specimens_shipped.csv", encoding="utf-8")))
    key = rows[0].keys().__iter__().__next__()  # unnamed first column = true width
    w = [float(r[key]) for r in rows]
    mae = [float(r["panel_MAE_cor"]) for r in rows]
    n = [int(r["panel_n"]) for r in rows]
    tab = {(r["set"], r["gate"], r["bin"]): r for r in csv.DictReader(open(RES / "width_eval_tables.csv", encoding="utf-8"))}
    allr = tab[("shipped / panel (toner-corrected truth)", "all gate states", "all")]
    cert = tab[("shipped / panel (toner-corrected truth)", "certified only", "all")] if (
        "shipped / panel (toner-corrected truth)", "certified only", "all") in tab else None
    fig, plt = new_fig()
    header(fig, "Held-out TEST, printed panel with known widths",
           "Average error under a tenth of a millimetre",
           "Mean absolute error per printed crack width. Truth: printed width, corrected for toner bleed.")
    ax = fig.add_axes([0.09, 0.17, 0.55, 0.58])
    xs = range(len(w))
    cols = [vc.AMBER if m < 0.1 else vc.BAD for m in mae]
    ax.bar(xs, mae, width=0.64, color=cols, zorder=3)
    ax.axhline(float(allr["MAE"]), color=vc.TEXT, lw=2, ls="--", zorder=2)
    ax.text(-0.45, float(allr["MAE"]) + 0.004, f"mean {float(allr['MAE']):.3f} mm", ha="left", va="bottom", fontproperties=fp("m", 24), color=vc.TEXT)
    for i, m in enumerate(mae):
        ax.text(i, m + 0.004, f"{m:.3f}", ha="center", fontproperties=fp("m", 24), color=vc.TEXT, va="bottom", bbox=dict(facecolor=vc.BG, edgecolor="none", pad=2), zorder=6)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{x:g}" for x in w], fontproperties=fp("m", 24), color=vc.TEXT)
    ax.set_xlabel("True crack width (mm)", fontproperties=fp("s", 24), color=vc.MUTED, labelpad=14)
    ax.set_ylabel("Mean absolute error (mm)", fontproperties=fp("s", 24), color=vc.MUTED, labelpad=14)
    ax.set_ylim(0, 0.2)
    for t in ax.get_yticklabels():
        t.set_fontproperties(fp("m", 20))
    ax.grid(axis="y", color=vc.LINE, lw=1.2, zorder=0)
    ax.tick_params(length=0, pad=10)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.text(0.69, 0.70, "ALL 63 TEST CRACKS", fontproperties=fp("m", 22), color=vc.MUTED)
    fig.text(0.69, 0.60, f"{float(allr['MAE']):.3f} mm", fontproperties=fp("b", 100), color=vc.AMBER)
    fig.text(0.69, 0.555, "mean absolute error", fontproperties=fp("r", 26), color=vc.TEXT)
    if cert is not None:
        fig.text(0.69, 0.43, f"CERTIFIED ONLY ({cert['n']} cracks)", fontproperties=fp("m", 22), color=vc.MUTED)
        fig.text(0.69, 0.33, f"{float(cert['MAE']):.3f} mm", fontproperties=fp("b", 100), color=vc.OK)
        fig.text(0.69, 0.285, "mean absolute error", fontproperties=fp("r", 26), color=vc.TEXT)
    fig.text(0.69, 0.16, "The widest specimens (2 and 3 mm) are" + chr(10) + "under-read; the cause is reported.", fontproperties=fp("r", 26), color=vc.MUTED, linespacing=1.3)
    footer(fig, "Source: eval/results/width_eval.md  |  reference uncertainty +-0.009 mm  |  8 TEST photos of one printed sheet")
    save(fig, "width_error.png")


# ------------------------------------------------------------------ 4. COOL loop latency
def chart_cool():
    recs = [json.loads(l) for l in open(RES / "cool_agentloop" / "trace.jsonl", encoding="utf-8")]
    pts = []
    for r in recs:
        m = r.get("measurements") or {}
        if m.get("e2e_p50_ms"):
            dec = r["decision"]
            kind = "ref" if dec == "reference" else "keep" if dec.startswith("keep") else "opt" if ("optional" in dec or "not adopted" in dec) else "drop"
            pts.append((r["iter"], m["e2e_p50_ms"], m["e2e_p95_ms"], kind))
    fig, plt = new_fig()
    first, last = pts[0][1], [p for p in pts if p[3] == "keep"][-1][1]
    header(fig, "COOL on Graviton4: a developer agent tuned the pipeline",
           f"Latency per photo: {first:.0f} ms to {last:.0f} ms",
           "End-to-end p50 (bars) and p95 (ticks), c8g.xlarge, 4 threads. Each kept change left every width bit-identical.")
    ax = fig.add_axes([0.07, 0.18, 0.89, 0.58])
    cmap = {"ref": "#6b7f93", "keep": vc.AMBER, "opt": "#c98d1a", "drop": vc.SURFACE2}
    for k, (it, p50, p95, kind) in enumerate(pts):
        ax.bar(k, p50, width=0.7, color=cmap[kind], hatch="//" if kind in ("drop", "opt") else None,
               edgecolor=vc.MUTED if kind in ("drop", "opt") else cmap[kind], linewidth=1.5, zorder=3)
        ax.plot([k - 0.32, k + 0.32], [p95, p95], color=vc.TEXT, lw=3, zorder=4)
        ax.text(k, p50 + 5, f"{p50:.0f}", ha="center", fontproperties=fp("b", 24), color=vc.TEXT, zorder=5)
    ax.set_xticks(range(len(pts)))
    ax.set_xticklabels([str(p[0]) for p in pts], fontproperties=fp("m", 22), color=vc.TEXT)
    ax.set_xlabel("Loop iteration (0 = starting code)", fontproperties=fp("s", 24), color=vc.MUTED, labelpad=12)
    ax.set_ylabel("ms per photo", fontproperties=fp("s", 24), color=vc.MUTED, labelpad=12)
    ax.set_ylim(0, 370)
    for t in ax.get_yticklabels():
        t.set_fontproperties(fp("m", 20))
    ax.grid(axis="y", color=vc.LINE, lw=1.2, zorder=0)
    ax.tick_params(length=0, pad=10)
    for s in ax.spines.values():
        s.set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=cmap["ref"]), plt.Rectangle((0, 0), 1, 1, color=cmap["keep"]),
               plt.Rectangle((0, 0), 1, 1, facecolor=cmap["drop"], hatch="//", edgecolor=vc.MUTED)]
    leg = ax.legend(handles, ["starting code", "kept: exact change", "discarded / not adopted"], loc="upper right",
                    prop=fp("r", 22), frameon=False, labelcolor=vc.TEXT)
    footer(fig, "Source: eval/results/cool_agentloop/  |  interleaved head-to-head: 186.6 to 143.1 ms (-23%)  |  COOL = pip within 1%")
    save(fig, "cool_latency.png")


# ------------------------------------------------------------------ 4b. COOL vs pip cost / latency
def chart_pareto():
    rows = list(csv.DictReader(open(RES / "cool" / "20261025T002750Z" / "cost_table.csv", encoding="utf-8")))
    fig, plt = new_fig()
    header(fig, "COOL vs stock OpenCV on Graviton4 (c8g)",
           "Same cost-latency curve; COOL is not cheaper",
           "Every point is one instance size and processes x threads setting. Lower left is better.")
    ax = fig.add_axes([0.09, 0.17, 0.86, 0.58])
    mk = {"c8g.large": "o", "c8g.xlarge": "s", "c8g.2xlarge": "^"}
    col = {"cool": vc.AMBER, "pip": vc.BLUE}
    for r in rows:
        b = r["build"]
        if b not in col:
            continue
        ax.scatter(float(r["p95_ms"]), float(r["usd_per_1000_frames"]), s=260, marker=mk[r["instance"]], color=col[b],
                   alpha=.9, edgecolors=vc.BG, linewidths=1.5, zorder=3)
    ax.set_yscale("log")
    ax.set_xlabel("p95 latency per photo (ms)", fontproperties=fp("s", 26), color=vc.MUTED, labelpad=14)
    ax.set_ylabel("USD per 1,000 photos (EC2 + COOL fee)", fontproperties=fp("s", 26), color=vc.MUTED, labelpad=14)
    for t in ax.get_xticklabels() + ax.get_yticklabels() + ax.get_yticklabels(minor=True):
        t.set_fontproperties(fp("m", 20))
    ax.grid(color=vc.LINE, lw=1.2, which="both", alpha=.7)
    ax.tick_params(length=0, pad=10, which="both")
    for s_ in ax.spines.values():
        s_.set_visible(False)
    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker="o", color="none", markerfacecolor=col["cool"], ms=18, label="COOL (OpenCV 5.1-dev, KleidiCV)"),
         Line2D([], [], marker="o", color="none", markerfacecolor=col["pip"], ms=18, label="stock pip OpenCV 5.0")]
    h += [Line2D([], [], marker=m, color="none", markerfacecolor=vc.MUTED, markeredgecolor="none", ms=16, label=k) for k, m in mk.items()]
    ax.legend(handles=h, loc="lower left", prop=fp("r", 24), frameon=False, labelcolor=vc.TEXT)
    footer(fig, "Source: eval/results/cool/20261025T002750Z/cost_table.csv  |  85 frames  |  list prices; COOL fee included")
    save(fig, "cool_pareto.png")


# ------------------------------------------------------------------ 5. failure gallery
def chart_failures():
    import matplotlib.image as mpimg
    G = ROOT / "docs" / "exhibits" / "gallery"
    cases = [("too-far", "Too far away"), ("blur-heavy", "Heavy blur"), ("oblique-extreme", "Extreme angle")]
    fig, plt = new_fig()
    header(fig, "Failure gallery (live endpoint, 2026-10-26)", "Bad photo in, no number out",
           "OpenCV's numbers become a reason, the reason becomes an instruction.")
    for k, (cid, title) in enumerate(cases):
        j = json.load(open(G / f"{cid}.json", encoding="utf-8"))
        img = mpimg.imread(G / f"{cid}.jpg")
        x0 = 0.05 + k * 0.315
        ax = fig.add_axes([x0, 0.38, 0.29, 0.40])
        ax.imshow(img)
        ax.axis("off")
        fig.text(x0, 0.325, title, fontproperties=fp("b", 34), color=vc.TEXT)
        reasons = ", ".join(j["gate"].get("reasons") or []) or j["gate"]["tier"]
        fig.text(x0, 0.285, f"gate: {(j['gate']['tier'] or 'no result').upper()}  ({reasons})", fontproperties=fp("m", 19), color=vc.AMBER)
        instr = j["llm"]["instruction"]
        fig.text(x0, 0.235, "Agent:", fontproperties=fp("m", 19), color=vc.MUTED)
        import textwrap
        fig.text(x0, 0.205, "\n".join(textwrap.wrap(instr, 40)[:3]), fontproperties=fp("r", 24), color=vc.TEXT, va="top", linespacing=1.25)
    footer(fig, "Source: docs/FAILURE_GALLERY.md  |  too-far is a shrunk real photo; blur and angle are synthetic degradations of one real photo")
    save(fig, "failure_gallery.png")


# ------------------------------------------------------------------ 6. SVG diagrams
def render_svgs():
    from playwright.sync_api import sync_playwright
    figs = ROOT / "docs" / "figures"
    OUT.mkdir(parents=True, exist_ok=True)
    # crops are in fractions of the SVG (x0, y0, x1, y1), aspect 16:9 after padding
    jobs = {
        "architecture": [("full", None), ("zoom_left", (0.03, 0.12, 0.70, 0.965)), ("zoom_right", (0.70, 0.18, 0.955, 0.90))],
        "agent_workflow": [("full", None), ("zoom_perception", (0.03, 0.10, 0.33, 0.90)), ("zoom_agent", (0.33, 0.10, 0.65, 0.90)), ("zoom_action", (0.65, 0.10, 0.96, 0.90))],
    }
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for name, crops in jobs.items():
            svg = (figs / f"{name}.svg").read_text(encoding="utf-8")
            m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
            vw, vh = float(m.group(1)), float(m.group(2))
            for tag, crop in crops:
                x0, y0, x1, y1 = crop or (0, 0, 1, 1)
                cw, ch = (x1 - x0) * vw, (y1 - y0) * vh
                # scale so the crop fits 1920x1080 with a margin; letterbox on the diagram's own white
                s = min(1840 / cw, 1000 / ch)
                pg = b.new_page(viewport={"width": 1920, "height": 1080})
                html = f"""<body style="margin:0;background:#f6f8fa;width:1920px;height:1080px;overflow:hidden;position:relative">
<div style="position:absolute;left:{(1920 - cw*s)/2:.1f}px;top:{(1080 - ch*s)/2:.1f}px;width:{cw*s:.1f}px;height:{ch*s:.1f}px;overflow:hidden;border-radius:12px;background:#fff">
<div style="position:absolute;left:{-x0*vw*s:.1f}px;top:{-y0*vh*s:.1f}px;width:{vw*s:.1f}px;height:{vh*s:.1f}px"><img src="data:image/svg+xml;base64,{__import__('base64').b64encode(svg.encode()).decode()}" style="width:{vw*s:.1f}px;height:{vh*s:.1f}px;display:block"></div></div></body>"""
                pg.set_content(html, wait_until="load")
                pg.wait_for_timeout(300)
                out = OUT / f"{name}_{tag}.png"
                pg.screenshot(path=str(out))
                pg.close()
                print("wrote", out.relative_to(ROOT))
        b.close()


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="*", default=["ablation", "gate", "width", "cool", "pareto", "failures", "svg"])
    ap.add_argument("--ablation-md", default=str(RES / "agent_ablation.md"))
    ap.add_argument("--ablation-out", default=None, help="file name inside docs/video/assets/charts (default: ablation.png and ablation_v2.png)")
    a = ap.parse_args()
    FONTS = vc.setup_matplotlib()
    for w in a.what:
        if w == "ablation":
            md = Path(a.ablation_md)
            if a.ablation_out:
                chart_ablation(md, a.ablation_out)
            else:
                chart_ablation(md, "ablation.png")
                chart_ablation(md, "ablation_v2.png")  # slot: identical until regenerated after the agent rerun
        elif w == "gate":
            chart_gate()
        elif w == "width":
            chart_width()
        elif w == "cool":
            chart_cool()
        elif w == "pareto":
            chart_pareto()
        elif w == "failures":
            chart_failures()
        elif w == "svg":
            render_svgs()
