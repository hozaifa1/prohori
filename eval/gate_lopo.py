"""Leave-one-photo-out (LOPO) re-tuning of the estimator parameters that were tuned in-sample on the first 29 photos.

Tuned parameters (measure.BLEND): ink_ratio (crack toner darkness / board black), d0 and q0 (where the blend switches
from the board-ink area estimator to the edge-based FWHM).  measure.blend_widths is a pure function of per-station
profile numbers that `analyze(debug=True)` returns, so any parameter set can be re-evaluated without re-reading images.

Tuning objective: mean |error| (mm) over the cracks of the photos that pass the LEGACY hand-set gate (the sharp, frontal
photos the parameters were originally calibrated on).  LOPO: for every photo p, the parameters are re-fitted on the
tuning photos other than p and applied to p.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from prohori import gate, measure  # noqa: E402

GRID = {"ink_ratio": [round(x, 2) for x in np.arange(0.76, 1.061, 0.02)], "d0": [3.0, 4.0, 5.0, 6.0, 7.0],
        "q0": [0.4, 0.5, 0.6]}


def raw_record(name, res):
    """Compact per-photo record from an analyze(debug=True) result."""
    o = res["observation"]
    legacy = (o["corners"] >= gate.LEGACY["min_corners"] and o["px_per_mm"] >= gate.LEGACY["min_px_per_mm"] and
              o["blur_var"] >= gate.LEGACY["min_blur_var"] and o["obliquity_deg"] <= gate.LEGACY["max_obliquity_deg"] and
              o["glare_frac"] <= gate.LEGACY["max_glare_frac"])
    cr = []
    for c in res["cracks"]:
        if "raw" not in c or c.get("true_width_mm") is None:
            continue
        r = c["raw"]
        cr.append({"id": c["id"], "true": c["true_width_mm"], "area": np.asarray(r["area"], float),
                   "fwhm": np.array([np.nan if v is None else v for v in r["fwhm"]], float),
                   "Dcore": r["Dcore"], "Dink": r["Dink"], "sigma": r["sigma_mm"], "cert": bool(c.get("certified", False))})
    return {"photo": name, "legacy": legacy, "cracks": cr}


def widths(rec, p):
    out = []
    for c in rec["cracks"]:
        b = measure.blend_widths(c["area"], c["Dcore"], c["Dink"], c["fwhm"], c["sigma"], p)
        out.append(float(np.median(b["w_i"])) - measure.WIDTH_BIAS_MM)
    return np.array(out)


def abs_errs(rec, p):
    t = np.array([c["true"] for c in rec["cracks"]])
    return np.abs(widths(rec, p) - t) if len(t) else np.array([])


def param_sets():
    for ir, d0, q0 in itertools.product(GRID["ink_ratio"], GRID["d0"], GRID["q0"]):
        yield {**measure.BLEND, "ink_ratio": ir, "d0": d0, "q0": q0}


def tune(recs):
    """Best parameter set (min mean |err| over the cracks of `recs`) and its objective."""
    best, bo = None, np.inf
    for p in param_sets():
        e = np.concatenate([abs_errs(r, p) for r in recs]) if recs else np.array([])
        if len(e) and e.mean() < bo:
            best, bo = p, float(e.mean())
    return best, bo


def lopo(recs):
    """Returns dict with default-parameter and LOPO errors per photo, the selected parameters, and in-sample optimum."""
    tune_recs = [r for r in recs if r["legacy"] and r["cracks"]]
    default = measure.BLEND
    per = []
    chosen = []
    for r in recs:
        if not r["cracks"]:
            continue
        fit = [x for x in tune_recs if x["photo"] != r["photo"]]
        p, _ = tune(fit)
        chosen.append((r["photo"], p))
        t = np.array([c["true"] for c in r["cracks"]])
        per.append({"photo": r["photo"], "legacy": r["legacy"], "true": t, "id": [c["id"] for c in r["cracks"]],
                    "cert": np.array([c["cert"] for c in r["cracks"]]),
                    "w_default": widths(r, default), "w_lopo": widths(r, p)})
    insample, obj = tune(tune_recs)
    return {"per": per, "chosen": chosen, "insample_best": insample, "insample_obj": obj}
