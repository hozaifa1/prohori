"""Calibration helper: render a few synthetic photos and print their statistics next to the real panel photos.

    python eval/synth_calib.py --n 8 --seed 1000
Used to tune the photometric ranges of SynthConfig (PSF, noise, tone, ink ratio); prints medians only.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth_stats import ROOT, image_stats  # noqa: E402

from prohori import synth  # noqa: E402

COLS = ["corners", "px_per_mm", "blur_var", "blur_sigma_px", "white_level", "black_level", "black_white_ratio",
        "noise_white", "noise_black", "noise_white_chroma", "jpeg_bytes_per_mpx", "glare_frac", "obliquity_deg"]


def one(seed):
    buf, img, gt = synth.render(seed, synth.SynthConfig())
    img2 = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)     # decode the JPEG as a consumer would
    r, _ = image_stats(img2, len(buf))
    r["seed"] = seed
    r["psf"] = gt["photometric"]["psf_sigma_px"]
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    with ProcessPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, range(a.seed, a.seed + a.n)))
    syn = pd.DataFrame(rows)
    real = pd.read_csv(ROOT / "eval" / "results" / "synth_real_stats.csv")
    real = real[real.corners >= 18]
    syn_ok = syn[syn.corners >= 18]
    print(f"real n={len(real)}  synth n={len(syn)} (board found {len(syn_ok)})")
    pd.set_option("display.width", 200)
    t = pd.DataFrame({"real_median": real[COLS].median(), "synth_median": syn_ok[COLS].median(),
                      "real_p10": real[COLS].quantile(.1), "synth_p10": syn_ok[COLS].quantile(.1),
                      "real_p90": real[COLS].quantile(.9), "synth_p90": syn_ok[COLS].quantile(.9)})
    print(t.round(3).to_string())
    print(syn[["seed", "corners", "px_per_mm", "blur_sigma_px", "psf", "noise_white", "white_level", "black_level"]].round(2).to_string())
