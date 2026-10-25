#!/usr/bin/env python3
"""Accuracy check for OUTPUT-CHANGING candidates of the COOL optimisation loop (resize / warp-interpolation class).

  python eval/cool_loop_mae.py REF.dump.json.gz NEW.dump.json.gz [--json OUT]

Same truth as eval/width_eval.py (panel reference = nominal printed width + 2 * toner bleed, METRICS 1a) and its frozen split
(eval/runs/width_autoresearch/split.json).  For both dumps (cool_loop.py run) it reports the panel width MAE on the held-out
TEST photos, on the TUNE photos and on all measured panel cracks, the paired change NEW - REF with a bootstrap 95 % CI over
photos, and the gate-tier flips.  Verdict "allowed" = TEST MAE worsens by <= 0.002 mm AND tier flips <= 1 % of panel cracks.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "src"))


def _load(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _cracks(flat: dict) -> dict:
    out: dict = {}
    for k, v in flat.items():
        if k.startswith("cracks."):
            _, cid, rest = k.split(".", 2)
            out.setdefault(cid, {})[rest] = v
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("new")
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    import width_eval as W  # noqa: E402  (frozen split, bleed pool, toner-corrected truth)
    from cool_bench import _fnum, _rekey_all
    sp = json.load(open(W.SPLIT))["panel"]
    R, N = _rekey_all(_load(a.ref)), _rekey_all(_load(a.new))
    pool = W.bleed_pool()
    rows = []
    n_cr = n_flip = 0
    for name in sorted(R):
        if not name.startswith("raw/") or name not in N:
            continue
        base = name.split("/", 1)[1]
        cr, cn = _cracks(R[name]), _cracks(N[name])
        for cid in sorted(set(cr) | set(cn)):
            n_cr += 1
            if cr.get(cid, {}).get("tier") != cn.get(cid, {}).get("tier"):
                n_flip += 1
            if cid in cr and cid in cn and "width_mm" in cr[cid] and "width_mm" in cn[cid]:
                nom = _fnum(cr[cid].get("true_width_mm"))
                if nom is None:
                    continue
                ref = W.toner_w_ref(cid, nom, pool)
                split = "test" if base in sp["test_files"] else "tune" if base in sp["tune_files"] else "other"
                rows.append((base, split, abs(_fnum(cr[cid]["width_mm"]) - ref), abs(_fnum(cn[cid]["width_mm"]) - ref)))
    out = {"n_panel_cracks": n_cr, "tier_flips": n_flip, "tier_flip_share": n_flip / max(n_cr, 1)}
    rng = np.random.default_rng(11)
    for sel in ("test", "tune", "all"):
        r = [x for x in rows if sel == "all" or x[1] == sel]
        if not r:
            continue
        e0, e1 = np.array([x[2] for x in r]), np.array([x[3] for x in r])
        photos = sorted({x[0] for x in r})
        idx = {p: [i for i, x in enumerate(r) if x[0] == p] for p in photos}
        bs = []
        for _ in range(2000):
            pick = rng.integers(0, len(photos), len(photos))
            ii = np.concatenate([idx[photos[j]] for j in pick])
            bs.append(e1[ii].mean() - e0[ii].mean())
        out[sel] = {"n": len(r), "mae_ref": float(e0.mean()), "mae_new": float(e1.mean()), "delta": float(e1.mean() - e0.mean()),
                    "delta_ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    t = out.get("test", {})
    out["allowed"] = bool(t and t["delta"] <= 0.002 and out["tier_flip_share"] <= 0.01)
    print(json.dumps(out, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
