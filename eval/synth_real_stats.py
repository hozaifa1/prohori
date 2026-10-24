"""Compute the image-statistics vector (eval/synth_stats.py) of the real panel photos in data/raw and cache it.

    python eval/synth_real_stats.py            # -> eval/results/synth_real_stats.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth_stats import ROOT, image_stats  # noqa: E402


def main():
    rows = []
    for p in sorted((ROOT / "data" / "raw").glob("*.jpg")):
        img = cv2.imread(str(p))
        r, _ = image_stats(img, p.stat().st_size)
        r["file"] = p.name
        rows.append(r)
        print(p.name, {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items() if k in ("corners", "px_per_mm", "blur_var", "white_level", "black_level", "noise_white", "blur_sigma_px")}, flush=True)
    out = ROOT / "eval" / "results" / "synth_real_stats.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("wrote", out)


if __name__ == "__main__":
    main()
