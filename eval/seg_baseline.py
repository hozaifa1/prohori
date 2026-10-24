"""Segmentation baseline of the classical locator on every public crack dataset (METRICS section 4).

    python eval/seg_baseline.py              # full run (multiprocessing), writes eval/results/seg_baseline_classical.{csv,md}
    python eval/seg_baseline.py --quick      # 10 images per dataset, for debugging

Protocol
  * The classical locator (measure.py: background-normalised darkness -> threshold -> close -> length/width-filtered
    connected components) is wrapped by prohori.segeval.ClassicalLocator and applied to dataset images that carry no
    ChArUco board, hence no scale.  A *nominal* px/mm is therefore a free parameter.  Two settings are reported:
      default  S = 5 px/mm (middle of measure.py's 3..8 px/mm locator canvas), darkness threshold 0.12 (measure.py)
      tuned    S* chosen on TRAIN/VAL data only (DeepCrack-train, Crack500-val, TUT-val subsets; max mean ODS);
               the threshold is swept over 0.06..0.80 and the ODS point is reported, so the tuned row is an upper bound
               of what the classical path can do without training on the test sets.
  * Variants: 'locator' = located components as measure.py selects them; 'refined' = half-maximum pixels inside the
    component (stand-in for measure.py's stage-2 mask).
  * Metrics per segeval (crack-class IoU, F1, ODS/OIS, clIoU_{0,1,2,4}px, centreline recall).
  * Test split of each dataset (official); datasets with no official split are evaluated on all images.
    Large test sets are strided (every n-th image of the official test split, n in the `stride` column of the CSV)
    to keep the run time bounded.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prohori import datasets as D  # noqa: E402
from prohori import segeval as SE  # noqa: E402

THRESHOLDS = [0.06, 0.09, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
DEFAULT_THR_IDX = THRESHOLDS.index(0.12)
S_DEFAULT = 5.0
S_GRID = (2.0, 3.0, 5.0, 8.0, 12.0)
VARIANTS = ("locator", "refined")

TEST_SETS = [  # (dataset, split, stride)
    ("crack500", "test", 4), ("deepcrack", "test", 1), ("tut", "test", 2), ("facade390", "test", 2),
    ("road420", "test", 2), ("cfd", "test", 1), ("ael", "test", 1), ("cracktree200", "test", 2),
    ("gaps384", "test", 4), ("crackseg9k", "test", 8),
]
TUNE_SETS = [("deepcrack", "train", 10), ("crack500", "val", 12), ("tut", "val", 5)]


def _work(args):
    """Evaluate a chunk of entries for one (S, variants): returns {variant: SweepAccumulator}."""
    entries, S, variants = args
    loc = SE.ClassicalLocator(S, THRESHOLDS)
    accs = {v: SE.SweepAccumulator(THRESHOLDS) for v in variants}
    for nm, ip, mp, sub in entries:
        img, mask = D.load_pair(ip, mp)
        out = loc.sweep_variants(img, variants)
        for v in variants:
            accs[v].add(mask, out[v])
    return accs


def run_chunks(ents, S, variants, pool, nchunk=32):
    chunks = [ents[i::nchunk] for i in range(nchunk) if ents[i::nchunk]]
    total = {v: SE.SweepAccumulator(THRESHOLDS) for v in variants}
    for accs in pool.map(_work, [(c, S, variants) for c in chunks]):
        for v in variants:
            total[v].merge(accs[v])
    return total


def select(name, split, stride, quick):
    ents = D.entries(name, split)[::stride]
    return ents[:10] if quick else ents


def row(dataset, split, stride, variant, S, point, summ):
    a = summ["at_default"] if point == "pipeline_default" else summ["at_ods"]
    r = {"dataset": dataset, "split": split, "stride": stride, "variant": variant, "S_px_per_mm": S,
         "operating_point": point, "threshold": a["threshold"], "n_images": summ["n_images"],
         "precision": a["precision"], "recall": a["recall"], "f1": a["f1"], "crack_iou": a["iou"],
         "ODS": summ["ODS"], "OIS": summ["OIS"]}
    for k in (0, 1, 2, 4):
        r[f"clIoU_{k}px"] = a[f"clIoU_{k}px"]
    r["cl_recall_2px"] = a["cl_recall_2px"]
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "seg_baseline_classical"))
    a = ap.parse_args()
    t0 = time.time()
    pool = ProcessPoolExecutor(max_workers=a.workers)

    # ---- 1. tune the nominal scale on train/val data (never on a test split)
    tune = []
    for n, sp, st in TUNE_SETS:
        tune += [(n, select(n, sp, st, a.quick))]
    tune_rows = []
    for S in S_GRID:
        ods = []
        for n, ents in tune:
            acc = run_chunks(ents, S, ("locator",), pool)["locator"]
            ods.append(acc.ods())
        tune_rows.append({"S_px_per_mm": S, **{f"ODS_{n}": o for (n, _), o in zip(tune, ods)}, "mean_ODS": float(np.mean(ods))})
        print(f"[tune] S={S}: ODS {np.round(ods, 3)} mean {np.mean(ods):.3f}  ({time.time() - t0:.0f}s)", flush=True)
    S_star = max(tune_rows, key=lambda r: r["mean_ODS"])["S_px_per_mm"]
    print("S* =", S_star, flush=True)

    # ---- 2. test-split evaluation
    settings = [("default", S_DEFAULT)] + ([("tuned", S_star)] if S_star != S_DEFAULT else [])
    rows = []
    for name, split, stride in TEST_SETS:
        if not D.available(name):
            print("missing", name)
            continue
        ents = select(name, split, stride, a.quick)
        for tag, S in settings:
            res = run_chunks(ents, S, VARIANTS, pool)
            for v in VARIANTS:
                summ = res[v].summary(DEFAULT_THR_IDX)
                if tag == "default":
                    rows.append(row(name, split, stride, v, S, "pipeline_default", summ))
                rows.append(row(name, split, stride, v, S, f"ODS_{tag}", summ))
            print(f"[test] {name}/{split} S={S}: n={len(ents)} locator ODS={res['locator'].ods():.3f} "
                  f"refined ODS={res['refined'].ods():.3f} ({time.time() - t0:.0f}s)", flush=True)
    # OmniCrack30k substitute: pooled public constituents (cfd, ael, cracktree200, gaps384)
    pooled = {}
    for tag, S in settings:
        accs = {v: SE.SweepAccumulator(THRESHOLDS) for v in VARIANTS}
        n = 0
        for name in ("cfd", "ael", "cracktree200", "gaps384"):
            stride = dict((t[0], t[2]) for t in TEST_SETS)[name]
            ents = select(name, "test", stride, a.quick)
            res = run_chunks(ents, S, VARIANTS, pool)
            n += len(ents)
            for v in VARIANTS:
                accs[v].merge(res[v])
        for v in VARIANTS:
            summ = accs[v].summary(DEFAULT_THR_IDX)
            if tag == "default":
                rows.append(row("omni_public(cfd+ael+cracktree200+gaps384)", "test", 1, v, S, "pipeline_default", summ))
            rows.append(row("omni_public(cfd+ael+cracktree200+gaps384)", "test", 1, v, S, f"ODS_{tag}", summ))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out.with_suffix(".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    write_md(out.with_suffix(".md"), rows, tune_rows, S_star, a.quick, time.time() - t0)
    print("wrote", out.with_suffix(".csv"), out.with_suffix(".md"), f"{time.time() - t0:.0f}s")


REFERENCE = [
    ("SCSegamba (S1, CVPR 2025)", "Crack500 F1 0.755 (crack IoU 0.607), DeepCrack F1 0.911, TUT F1 0.839"),
    ("EfficientCrackNet (S2, WACV 2025)", "Crack500 F1 0.791 (crack IoU 0.654), DeepCrack F1 0.859"),
    ("CrackSCF (S3) / SCRWKV (S4)", "TUT F1 0.838 / 0.843"),
    ("Segment Any Crack (S7)", "OmniCrack30k F1 0.612 / crack IoU 0.441"),
    ("nnU-Net (S10)", "OmniCrack30k clIoU_4px 0.64 (test), clIoU_0px 0.162 (val)"),
]


def fmt(x):
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def write_md(path, rows, tune_rows, S_star, quick, secs):
    L = ["# Classical locator: segmentation baseline", "",
         f"Generated by `eval/seg_baseline.py`{' (QUICK subset run, 10 images/dataset)' if quick else ''}, {secs / 60:.0f} min. "
         "Crack-class metrics only (METRICS section 0 rule 3); pooled over the test split unless stated.", "",
         "The classical locator is **not trained**; METRICS 4c sets no target for it on the public sets (it is scored on "
         "centreline recall and downstream width error). The numbers are the honest baseline that a DNN locator "
         "(EfficientCrackNet-class, S2) has to beat, and they show why mask edges from either path are not the width "
         "measurement (S10).", "",
         "## Setup", "",
         "- Locator: `prohori.segeval.ClassicalLocator`, a pixel-domain re-implementation of `measure._locate_cracks` "
         "(equal masks on a synthetic crack: `tests/test_segeval.py::test_locator_matches_measure_py`). "
         "Differences: no board/validity mask; no perspective rectification; BFS longest path by scipy; stage-2 "
         "(corridor half-max + profile) not applied except in the `refined` variant, which uses half of each "
         "component's 90th-percentile darkness as a stand-in.",
         "- Dataset images have no scale, so the nominal px/mm S is a free parameter: **default S = 5** "
         "(middle of measure.py's 3-8 px/mm locator range, threshold 0.12 as in measure.py) and **tuned S\\*** chosen on "
         "train/val data only (table below). The threshold sweep is 0.06..0.80 (12 values); the `ODS_*` rows use the best "
         "dataset-level threshold on the test split itself (an oracle operating point, as in ODS by definition).",
         "- `pipeline_default` rows are the exact operating point measure.py would use (S=5, threshold 0.12).", "",
         "## Scale tuning (train/val subsets only)", "",
         "| S px/mm | " + " | ".join(k for k in tune_rows[0] if k.startswith("ODS_")) + " | mean ODS |",
         "|---|" + "---|" * (len([k for k in tune_rows[0] if k.startswith("ODS_")]) + 1)]
    for r in tune_rows:
        L.append(f"| {r['S_px_per_mm']:g} | " + " | ".join(fmt(r[k]) for k in r if k.startswith("ODS_")) + f" | {fmt(r['mean_ODS'])} |")
    L += ["", f"Chosen S\\* = {S_star:g} px/mm.", ""]
    for variant in VARIANTS:
        for point in ("pipeline_default", "ODS_tuned" if any(r["operating_point"] == "ODS_tuned" for r in rows) else "ODS_default"):
            sub = [r for r in rows if r["variant"] == variant and r["operating_point"] == point]
            if not sub:
                continue
            L += [f"## Variant `{variant}`, operating point `{point}`", "",
                  "| dataset | n | thr | P | R | F1 | crack IoU | ODS | OIS | clIoU 0px | 1px | 2px | 4px | CL recall@2px |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for r in sub:
                L.append(f"| {r['dataset']} | {r['n_images']} | {r['threshold']:.2f} | {fmt(r['precision'])} | {fmt(r['recall'])} | "
                         f"{fmt(r['f1'])} | {fmt(r['crack_iou'])} | {fmt(r['ODS'])} | {fmt(r['OIS'])} | {fmt(r['clIoU_0px'])} | "
                         f"{fmt(r['clIoU_1px'])} | {fmt(r['clIoU_2px'])} | {fmt(r['clIoU_4px'])} | {fmt(r['cl_recall_2px'])} |")
            L.append("")
    L += ["## Published reference points (METRICS 4c; trained DNNs, not comparable one-to-one)", ""]
    L += [f"- {a}: {b}" for a, b in REFERENCE]
    L += ["", "## Notes and limits", "",
          "- OmniCrack30k itself is distributed on request only; the `omni_public` row pools its public constituents "
          "(CFD, AEL, CrackTree200, GAPs384). See research/DATASETS.md.",
          "- Test sets are deterministic every-n-th subsets of the official test split (`stride` column in the CSV): crack500 /4, tut /2, facade390 /2, road420 /2, cracktree200 /2, gaps384 /4, crackseg9k /8; the rest are complete.",
          "- clIoU uses Zhang-Suen thinning of mask and ground truth (`segeval.skeleton`); ground-truth masks of the "
          "datasets are themselves only ~1-2 px accurate (S10), so clIoU_0px is expected to be low for any method.",
          "- Per-image `clIoU_*_mean_img` variants and the full threshold curves are available from `segeval.SweepAccumulator`."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
