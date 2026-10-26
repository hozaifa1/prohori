#!/usr/bin/env python3
"""Builds eval/results/cool_agentloop/{trace.jsonl, summary.json, tables.md, latency_per_iteration.png} from the raw runs
(raw/s1 = session 1, the iteration runs; raw/s2 = session 2, the final before/after + pip-vs-COOL runs) and the iteration notes
below (hypothesis, change, decision, reason: written by the developer agent while it ran the loop).

  python eval/cool_loop_report.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "eval" / "results" / "cool_agentloop"
RAW = OUT / "raw"
PRICES = json.loads((OUT.parent / "cool" / "20261025T002750Z" / "prices.json").read_text())
P_EC2 = PRICES["ec2_usd_per_hour"]["c8g.xlarge"]
P_FEE = PRICES["cool_fee_usd_per_hour"]["c8g.xlarge"]

# values read off the console for runs whose raw files were lost when the session-1 instance shut itself down
# (the usage limit hit before the last results were fetched): label -> (p50, p95, mean) e2e ms at 4 OpenCV threads
CONSOLE = {"o6_cool_t4": (147.1, 222.0, 157.0), "o7_cool_t4": (145.3, 211.5, 151.9), "o7_rep1": (146.4, 212.4, 153.3),
           "o7_rep2": (147.9, 214.2, 154.0), "c7_rep1": (148.9, 214.0, 154.2), "c7_rep2": (150.1, 214.2, 156.2),
           "o8_rep1": (146.0, 213.1, 152.9), "o8_rep2": (143.8, 212.4, 151.3)}


def find(label: str) -> dict | None:
    for f in glob.glob(str(RAW / "*" / label / f"{label}.loop.json")):
        return json.loads(Path(f).read_text())
    return None


def guard(label: str) -> dict | None:
    for f in glob.glob(str(RAW / "*" / label / "guard.json")):
        return json.loads(Path(f).read_text())
    return None


def mae(label: str) -> dict | None:
    for f in glob.glob(str(RAW / "*" / label / "mae.json")):
        return json.loads(Path(f).read_text())
    return None


def meas(label: str) -> dict:
    d = find(label)
    if d is None:
        p50, p95, mean = CONSOLE[label]
        return {"label": label, "e2e_p50_ms": p50, "e2e_p95_ms": p95, "e2e_mean_ms": mean, "source": "console (raw file lost)"}
    s = d["stages"]
    m = {"label": label, "cv2_threads": d["threads"], "e2e_p50_ms": round(s["e2e"]["p50"], 1), "e2e_p95_ms": round(s["e2e"]["p95"], 1),
         "e2e_mean_ms": round(s["e2e"]["mean"], 1), "stage_p50_ms": {k: round(v["p50"], 1) for k, v in s.items()},
         "analyze_p50_ms": round(s["analyze"]["p50"], 1), "fps_in_process": round(d["fps_inproc"], 2),
         "frames": d["protocol"]["reps"] * len(d["protocol"]["inputs"])}
    if "profile" in d:
        m["profile_top5_ms_per_frame"] = [[r["function"][:50] + (" " + r["where"] if r["where"] else ""), round(r["ms_per_frame"], 2)]
                                           for r in d["profile"]["top"][:5]]
        m["profile_share_by_kind"] = {k: round(v, 3) for k, v in d["profile"]["share_by_kind"].items()}
    if "sweep" in d:
        m["sweep"] = {k: {"fps": round(v["fps"], 2), "p50_ms": round(v["e2e_ms"]["p50"], 1), "p95_ms": round(v["e2e_ms"]["p95"], 1)}
                      for k, v in d["sweep"].items() if "fps" in v}
    return m


def gsum(label: str) -> dict | None:
    g = guard(label)
    if g is None:
        return None
    return {"bitwise_identical_all_85_frames": g["bitwise_identical_all"], "panel_cracks": g["panel_cracks"],
            "max_abs_dw_mm": round(g["max_abs_dw_mm"], 4), "tier_flips": g["tier_flips"], "certified_flips": g["certified_flips"],
            "guard_pass": g["pass"]}


def msum(label: str) -> dict | None:
    m = mae(label)
    if m is None:
        return None
    return {"test_mae_delta_mm": round(m["test"]["delta"], 4), "tune_mae_delta_mm": round(m["tune"]["delta"], 4),
            "all_mae_delta_mm": round(m["all"]["delta"], 4), "tier_flips": m["tier_flips"], "tier_flip_share": round(m["tier_flip_share"], 4),
            "allowed_output_changing": m["allowed"]}


CMD = ("python eval/cool_loop.py run --label {l} --out ~/out/{l} --input raw=~/inputs/raw --input samples=~/inputs/samples "
       "--input synth=~/inputs/synth --threads 4 --compat {c} --reps 5 --profile   (c8g.xlarge, COOL AMI ami-033e481a24f94c8cb)")
GUARD_CMD = "python eval/cool_loop.py compare head_cool_t4.dump.json.gz {l}.dump.json.gz"

# iteration notes: id, label of the measurement, commit, kind, files, change text, hypothesis, decision, reason, observation-source label
IT = [
    dict(i=0, label="head_cool_t4", commit="1c1ac4f", kind="baseline", prof_from=None,
         change="none: HEAD measured on COOL with the harness shims (numpy Zhang-Suen thinning, CCL_BBDT) so that it runs at 4 threads",
         hyp="Reference point. HEAD cannot run on COOL as shipped (no cv2.ximgproc, heap corruption in connectedComponentsWithStats at >=2 threads).",
         decision="reference", reason="p50 194.9 ms at 4 threads, 321.0 ms at 1 thread; python+numpy+builtin = 59 % of profiled time at 4 threads."),
    dict(i=1, label="c1_cool_t4", commit="b079cdd", kind="exact", prof_from="head_cool_t4", files=["src/prohori/measure.py"],
         change="_cc_stats: connectedComponentsWithStatsWithAlgorithm(CCL_BBDT); _thin: in-tree sparse Zhang-Suen (filter2D neighbour code kept up to date by subtraction); the three cv2.ximgproc / default-CCL call sites use them",
         hyp="Brief priorities 1 and 2: BBDT removes the COOL crash path, the in-tree thinning removes the contrib dependency; thinning_zs was 7 % of profiled time and sparse code updates should beat re-gathering 8 neighbours every sweep.",
         decision="keep", reason="bit-identical on all 85 frames; thinning 12.5 -> 7.2 ms/frame in the profile; e2e p50 -1.1 % (inside the noise, but the code now runs unmodified on COOL and pip)."),
    dict(i=2, label="c2_cool_t4", commit="1f97b7f", kind="exact", prof_from="c1_cool_t4", files=["src/prohori/measure.py"],
         change="_longest_path: neighbour table by 8 padded gathers + flat list BFS (order of the original per-node lists kept); _match_once/_fit_affine: all specimens in one broadcast distance matrix (reduceat)",
         hyp="numpy ufunc.reduce was 9.5 % of profiled time with 105k calls/85 frames (per-specimen sum/min/mean in _match_once), _longest_path + bfs 8 %.",
         decision="keep", reason="bit-identical; p50 192.7 -> 188.8 ms, p95 321 -> 287 ms (long skeletons were the tail)."),
    dict(i=3, label="c3_cool_t4", commit="dc56e03", kind="exact", prof_from="c2_cool_t4", files=["src/prohori/measure.py"],
         change="_ones255 (one cached 12 MB all-255 image instead of 8 np.full per frame), _warp_valid (validity mask of a warp without warping when the 4 corners map 2 px inside the photo), _median_u8 (np.median of uint8 / LUT-mapped samples from a 256-bin histogram, same float32 arithmetic)",
         hyp="partition (np.median of 1M-sample ROIs and the 2.3 MP locator canvas) 4.5 %, np.full of 12 MP arrays and 12 MP NEAREST warps for validity masks that are almost always all-true.",
         decision="keep", reason="bit-identical; p50 188.8 -> 176.4 ms (-6.6 %), the biggest single-thread gain."),
    dict(i=4, label="c4_cool_t4", commit="78deaf7", kind="exact", prof_from="c3_cool_t4", files=["src/prohori/measure.py"],
         change="_fwhm vectorised over the profile rows with the dtype/operation order of the scalar scan (float32 for Dsmooth, float64 for the black-core depth)",
         hyp="_fwhm scalar numpy indexing loop (called twice per ROI).",
         decision="keep", reason="bit-identical (1600 randomised cases in tests); p50 flat (176.4 -> 177.2), mean -0.8 %: kept because it is exact and removes ~1700 Python-level loop iterations per ROI."),
    dict(i=5, label="c5_cool_t4", commit="c081534", kind="exact", prof_from="c4_cool_t4", files=["src/prohori/measure.py"],
         change="_locate_cracks elementwise float ops (subtract/max/divide/compare/mask) through cv2 instead of numpy temporaries; one astype instead of two",
         hyp="_locate_cracks self time 4 % = several 2.3 MP numpy temporaries.",
         decision="keep", reason="bit-identical; p50 177.2 -> 175.6 (-0.9 %), mean -1.3 %."),
    dict(i=6, label="c6_cool_t4", commit="162ce16", kind="exact", prof_from="c5_cool_t4", files=["src/prohori/measure.py"],
         change="Python threads (default min(4, CPUs); PROHORI_THREADS=1 = sequential, same code path) for the independent parts of a frame: board-quality statistics and edge sigma run beside the crack locator; the per-crack ROI extraction and measurement run concurrently",
         hyp="At 4 OpenCV threads the serial Python/numpy part dominates (python+numpy+builtin = 45 % of the profile) and 3 cores idle while one crack is measured; OpenCV and numpy release the GIL in their big calls.",
         decision="keep", reason="bit-identical; p50 175.6 -> 154.6 ms (-12.0 %), p95 260 -> 220. Ablation on the same tree: Python threads off 176.3 ms (so the gain is entirely the threads), 2 threads 154.8 ms."),
    dict(i=7, label="c7_cool_t4", commit="c7bfcea", kind="exact", prof_from="c6_cool_t4", files=["src/prohori/measure.py"],
         change="np.count_nonzero instead of bool .sum()/.all() on multi-megapixel masks; int16 Laplacian / filter2D responses converted to float32 only where used; no np.where copy when the validity mask is all-true",
         hyp="ufunc.reduce still 7 % of profiled time with 76k calls: bool sums over 6.6 MP board masks (numpy sums bool at ~1 GB/s).",
         decision="keep", reason="bit-identical; p50 154.6 -> 149.9 ms (-3.0 %), mean -3.0 %."),
    dict(i=8, label=None, commit=None, kind="micro-experiment", prof_from="c7_cool_t4", files=["eval/cool_loop_micro.py"],
         change="DENSE Zhang-Suen re-expressed with OpenCV kernels (filter2D neighbour code + LUT + masked clear per sub-iteration), on the 92 masks the pipeline really thins",
         hyp="Brief priority 2 literally: OpenCV kernels may beat the Python sparse code on COOL.",
         decision="discard", reason="exact but 2.17 ms/mask vs 1.10 ms for the in-tree sparse code and 1.82 for the old numpy shim (COOL, 1 thread; micro_t1.json): the masks are small (median 5k foreground px in a 21k px box), dense sweeps touch every box pixel.",
         extra={"micro": "raw/s1/micro_t1.json"}),
    dict(i=9, label=None, commit=None, kind="micro-experiment", prof_from="c7_cool_t4", files=["eval/cool_loop_micro.py"],
         change="canvas warpPerspective(INTER_LINEAR) -> remap with CV_16SC2 maps (brief priority 4)",
         hyp="KleidiCV warp LINEAR is 8.6 ms vs 3.3 ms for remap with fixed-point maps (REPORT section 6).",
         decision="discard", reason="the maps depend on the frame's homography: building them in numpy costs 17.4 ms (f32) + 1.4 ms (convertMaps), more than the 5.3 ms saved at 1 thread; at 4 threads the warp is only 2.3 ms. Output also differs (6.6 % of pixels, max 4 grey levels)."),
    dict(i=10, label="c7_t3p4", commit="c7bfcea", kind="tuning", prof_from=None, files=[],
         change="OpenCV threads x PROHORI_THREADS grid on the same tree: (1,1) 283.6 / (1,4) 224.9 / (2,2) 173.5 / (2,4) 169.1 / (3,4) 151.3 / (4,2) 147.8 / (4,4) 149.9 ms",
         hyp="Is the default (4 OpenCV threads, 4 Python threads) the best use of 4 vCPUs?",
         decision="keep default", reason="4 OpenCV threads is needed (3 -> +1 %, 2 -> +13 %); 2 or 4 Python threads are equivalent (OpenCV's pthread pool serialises concurrent parallel regions), so min(4, CPUs) stays."),
    dict(i=11, label="o1a_cool_t4", commit="eb0e48a (tag cool-loop-cand-o1a)", kind="output-changing (resize)", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="locator canvas down-scale: exact 2x INTER_AREA first, then INTER_AREA to the target size (_resize_area)",
         hyp="resize INTER_AREA 12 MP -> 0.3 is 16 ms at 1 thread / 5.3 ms at 4 threads (micro); two-stage 6.0 / 2.0 ms.",
         decision="not adopted alone", reason="guard allows it (panel TEST MAE +0.0013 mm <= 0.002, 0 tier flips) but the gain is only -2.9 % p50 (145.6 vs 149.9)."),
    dict(i=12, label="o1ab_cool_t4", commit="4d0fdef (tag cool-loop-cand-o1ab) -> 8d13353 on branch cool-loop-output-changing", kind="output-changing (resize)", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="the same two-stage down-scale also for the board-detection input (4096 -> 2000 px)",
         hyp="Both big AREA resizes (7.4 + 5.3 ms at 4 threads) become 3.5 + 2.0 ms.",
         decision="optional (separate commit, not on main)", reason="p50 149.9 -> 138.4 ms (-7.7 %). Resize-class exception: panel TEST MAE +0.0013 mm (<= 0.002), 1/168 tier flips (0.6 % <= 1 %), but max |dw| 0.12 mm on one panel crack and 1.13 mm on one synthetic render (a different component matched), so it is left to the orchestrator."),
    dict(i=13, label="o3_cool_t4", commit="a8c676a (tag cool-loop-cand-o3)", kind="output-changing (detect size)", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="DETECT_MAX_SIDE 2000 -> 1600",
         hyp="Fewer pixels for the ArUco detector (20.5 ms/frame, the largest single OpenCV call).",
         decision="discard", reason="-6.3 % p50 (140.4) but 2/168 panel tier flips (1.19 % > 1 %), max |dw| 0.13 mm."),
    dict(i=14, label="o4_cool_t4", commit="2087162 (tag cool-loop-cand-o4)", kind="output-changing (detect size)", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="DETECT_MAX_SIDE 2000 -> 1800", hyp="A smaller step than 1600 might keep the tiers.",
         decision="discard", reason="143.9 ms (-4.0 %) and still 2 tier flips (1.19 %)."),
    dict(i=15, label="o5_cool_t4", commit="5a79b20 (tag cool-loop-cand-o5)", kind="output-changing (resize)", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="locator two-stage resize + DETECT_MAX_SIDE 1800", hyp="Combine the two.",
         decision="discard", reason="143.3 ms: slower than o1ab (138.4) with the same one flip and a larger MAE change (+0.0014 test)."),
    dict(i=16, label="o6_cool_t4", commit="87e56e5 (tag cool-loop-cand-o6)", kind="output-changing (detector parameters)", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="ArUco adaptiveThreshWinSizeMin 23 (one threshold window) first; full detector only if fewer than 24 corners are found",
         hyp="Local test: 44 % less detectBoard time with identical corner counts on 35 frames.",
         decision="discard", reason="on COOL at 4 threads p50 147.1 (-1.9 %) but mean 157.0 (+0.8 %): many frames have partial boards, so both detectors run; 10 frames differ, max |dw| 0.0022 mm. No gain worth the robustness risk."),
    dict(i=17, label="o7_cool_t4", commit="c5a29bd", kind="exact", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="start the board-quality / edge-sigma threads just before the locator (after its own big resize/warp calls) instead of right after detection",
         hyp="Timeline (eval/cool_loop_timeline.py): the locator started 22 ms after detection ended because the two background tasks compete for the OpenCV thread pool.",
         decision="keep", reason="bit-identical; 3 interleaved repeats: c7 149.9 / 148.9 / 150.1 vs o7 145.3 / 146.4 / 147.9 ms (-2.1 % p50, -1.5 % mean)."),
    dict(i=18, label="o8_rep2", commit="1c0a708", kind="exact", prof_from="c7_cool_t4", files=["src/prohori/measure.py"],
         change="_pmap(cost=...): start the biggest ROI tasks first (results still in order)",
         hyp="8 ROIs on 4 threads: the longest task should not start last.",
         decision="keep", reason="bit-identical; 146.0 / 143.8 ms vs 146.4 / 147.9 for o7 (-1.5 %); noise-level but never worse."),
]


def final_tables() -> dict:
    """Session-2 runs (one instance, interleaved): HEAD vs final on COOL, COOL vs pip after optimisation, throughput and cost."""
    def g(l):
        return meas(l)
    out = {}
    rows = {}
    for tag, labels in (("HEAD (1c1ac4f) + harness shims", ["F_head_cool_t4_A", "F_head_cool_t4_B", "F_head_cool_t4_C"]),
                        ("final, exact (1c0a708)", ["F_f1_cool_t4_A", "F_f1_cool_t4_B", "F_f1_cool_t4_C"]),
                        ("final + output-changing resize (8d13353)", ["F_f2_cool_t4_A"])):
        ms = [g(l) for l in labels if find(l)]
        rows[tag] = {"runs": [m["label"] for m in ms], "p50": [m["e2e_p50_ms"] for m in ms], "p95": [m["e2e_p95_ms"] for m in ms],
                     "mean": [m["e2e_mean_ms"] for m in ms], "stage_p50_first_run": ms[0]["stage_p50_ms"]}
    out["cool_4_threads"] = rows
    t1 = {}
    for tag, l in (("HEAD", "F_head_cool_t1"), ("final exact, Python threads on", "F_f1_cool_t1"), ("final exact, PROHORI_THREADS=1", "F_f1p1_cool_t1")):
        if find(l):
            m = g(l)
            t1[tag] = {k: m[k] for k in ("e2e_p50_ms", "e2e_p95_ms", "e2e_mean_ms")} | {"sweep": m.get("sweep")}
    out["cool_1_thread"] = t1
    pip = {}
    for tag, l in (("HEAD pip 4T", "F_head_pip_t4"), ("final pip 4T", "F_f1_pip_t4"), ("HEAD pip 1T", "F_head_pip_t1"),
                   ("final pip 1T", "F_f1_pip_t1"), ("final pip 1T PROHORI_THREADS=1", "F_f1p1_pip_t1")):
        if find(l):
            m = g(l)
            pip[tag] = {k: m[k] for k in ("e2e_p50_ms", "e2e_p95_ms", "e2e_mean_ms")} | {"sweep": m.get("sweep")}
    out["pip"] = pip
    # cost: USD per 1000 frames = USD/h / 3600 * 1000 / fps ; COOL pays the fee
    cost = []
    for build, lab, usd in (("COOL HEAD", "F_head_cool_sw_bbdt", P_EC2 + P_FEE), ("COOL final", "F_f1_cool_t1", P_EC2 + P_FEE),
                            ("COOL final PROHORI_THREADS=1", "F_f1p1_cool_t1", P_EC2 + P_FEE), ("pip HEAD", "F_head_pip_t1", P_EC2),
                            ("pip final", "F_f1_pip_t1", P_EC2), ("pip final PROHORI_THREADS=1", "F_f1p1_pip_t1", P_EC2)):
        m = find(lab)
        if not m or "sweep" not in m:
            continue
        for spec, r in m["sweep"].items():
            if "fps" in r:
                cost.append({"build": build, "config": spec, "fps": round(r["fps"], 2), "p50_ms": round(r["e2e_ms"]["p50"], 1),
                             "p95_ms": round(r["e2e_ms"]["p95"], 1), "usd_per_hour": round(usd, 5),
                             "usd_per_1000_frames": round(usd / 3600 * 1000 / r["fps"], 5)})
    out["throughput_cost"] = cost
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main() -> int:
    final_tables()
    recs = []
    for it in IT:
        m = meas(it["label"]) if it.get("label") else {}
        prof = None
        if it.get("prof_from"):
            pm = meas(it["prof_from"])
            prof = pm.get("profile_top5_ms_per_frame")
        compat = "thin+bbdt" if it["i"] == 0 else "none"
        r = {"iter": it["i"], "timestamp": (find(it["label"]) or {}).get("env", {}).get("utc") if it.get("label") else None,
             "observation": {"motivated_by_run": it.get("prof_from"), "profile_top5_ms_per_frame": prof},
             "hypothesis": it["hyp"],
             "change": {"kind": it["kind"], "commit": it.get("commit"), "files": it.get("files", []), "summary": it["change"]},
             "commands": ([CMD.format(l=it["label"], c=compat)] + ([GUARD_CMD.format(l=it["label"])] if it["i"] > 0 else [])) if it.get("label") else ["python eval/cool_loop_micro.py --input raw=~/inputs/raw --out micro_t1.json --threads 1"],
             "measurements": m, "accuracy_check": gsum(it["label"]) if it.get("label") else None,
             "width_mae_check_output_changing": msum(it["label"]) if it.get("label") else None,
             "decision": it["decision"], "reason": it["reason"]}
        if it.get("extra"):
            r["measurements"] = {**m, **it["extra"]}
        recs.append(r)
    (OUT / "trace.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")

    # ---- figure: p50 (bar) and p95 (tick) per measured iteration
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pts = [(r["iter"], r["measurements"]) for r in recs if r["measurements"].get("e2e_p50_ms")]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    col = {"keep": "#0072B2", "reference": "#555555"}
    for k, (i, m) in enumerate(pts):
        dec = next(r["decision"] for r in recs if r["iter"] == i)
        kept = dec.startswith("keep") or dec == "reference"
        oc = "optional" in dec or "not adopted" in dec
        c = col.get(dec.split()[0] if kept else "x", "#E69F00" if oc else "#BBBBBB")
        ax.bar(k, m["e2e_p50_ms"], color=c, hatch=None if kept else "//", edgecolor="white")
        ax.plot([k - 0.3, k + 0.3], [m["e2e_p95_ms"]] * 2, color="black", lw=1.2)
        ax.text(k, m["e2e_p50_ms"] + 3, f'{m["e2e_p50_ms"]:.0f}', ha="center", fontsize=8)
    ax.set_xticks(range(len(pts)))
    ax.set_xticklabels([f"{i}" for i, _ in pts])
    ax.set_xlabel("iteration (0 = HEAD; blue = kept exact change, amber = output-changing candidate that passes the guard, grey hatched = discarded)")
    ax.set_ylabel("end-to-end ms per frame (bar p50, tick p95)")
    ax.set_title("COOL, c8g.xlarge, 4 OpenCV threads, 85 frames x 5 reps: latency per loop iteration")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "latency_per_iteration.png", dpi=140)
    print("wrote trace.jsonl,", len(recs), "records; figure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
