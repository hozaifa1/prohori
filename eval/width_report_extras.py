"""Adds the tune-vs-test, M2 / S8 and limitations sections to eval/results/width_eval.md (documentation only; reads the
csv tables written by width_final.py for TUNE and TEST, runs no evaluation)."""
from pathlib import Path

import pandas as pd

RES = Path(__file__).resolve().parents[1] / "eval" / "results"
MARK = "<!-- extras -->"
P, S, N = "panel (toner-corrected truth)", "synthetic (exact truth)", "panel (nominal truth)"


def get(T, name, label, gate, bin_, col):
    r = T[(T.set == f"{name} / {label}") & (T.gate == gate) & (T.bin == bin_)]
    return float(r[col].iloc[0]) if len(r) else float("nan")


def main():
    tu = pd.read_csv(RES / "width_eval_tune_tables.csv")
    te = pd.read_csv(RES / "width_eval_tables.csv")
    rows = []
    for lab, label, gate, b in [("panel, all gate states, all widths", P, "all gate states", "all"),
                                ("panel, all gate states, < 0.5 mm", P, "all gate states", "< 0.5 mm"),
                                ("panel, all gate states, >= 0.5 mm", P, "all gate states", ">= 0.5 mm"),
                                ("panel, certified only, all widths", P, "certified only", "all"),
                                ("panel, nominal truth, all widths", N, "all gate states", "all"),
                                ("synthetic, all widths", S, "all gate states", "all"),
                                ("synthetic, < 0.5 mm", S, "all gate states", "< 0.5 mm"),
                                ("synthetic, >= 0.5 mm", S, "all gate states", ">= 0.5 mm")]:
        v = {(sp, n): get(T, n, label, gate, b, "MAE") for sp, T in (("tune", tu), ("test", te)) for n in ("legacy", "shipped")}
        n_te = get(te, "shipped", label, gate, b, "n")
        rows.append(f"| {lab} | {int(n_te)} | {v['tune', 'legacy']:.3f} | {v['tune', 'shipped']:.3f} | "
                    f"{100 * (v['tune', 'shipped'] / v['tune', 'legacy'] - 1):+.0f} % | {v['test', 'legacy']:.3f} | "
                    f"{v['test', 'shipped']:.3f} | {100 * (v['test', 'shipped'] / v['test', 'legacy'] - 1):+.0f} % |")

    def a(n, l, g, b, c):
        return get(te, n, l, g, b, c)

    def chg(label, gate, b):
        return 100 * (a("shipped", label, gate, b, "MAE") / a("legacy", label, gate, b, "MAE") - 1)

    txt = f"""{MARK}
## Summary: before / after, tune vs test (MAE in mm; every panel MAE carries U_ref = +-0.009 mm)

LEGACY is the fixed 2026-10-19 estimator, scored on both splits so that the before/after is like for like. `n` is the TEST count. The TUNE columns are the split used for the loop and for the V1/V2/V3 mid-range selection; the TEST columns were produced once, after the configuration was frozen.

| set | n (test) | LEGACY tune | shipped tune | change | LEGACY test | shipped test | change |
|---|---|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

**In plain words.**
* On the **photoreal renders** the improvement holds and is larger on TEST than on TUNE (MAE {a('legacy', S, 'all gate states', 'all', 'MAE'):.3f} -> {a('shipped', S, 'all gate states', 'all', 'MAE'):.3f} mm, {chg(S, 'all gate states', 'all'):+.0f} %), mostly on widths from 0.75 mm up.
* On the **real printed-panel photos** the gain on TEST is much smaller than on TUNE ({a('legacy', P, 'all gate states', 'all', 'MAE'):.3f} -> {a('shipped', P, 'all gate states', 'all', 'MAE'):.3f} mm, {chg(P, 'all gate states', 'all'):+.0f} %), inside the bootstrap interval of either number. TEST is the easier half: LEGACY's panel MAE is 0.075 there against 0.120 on TUNE, because the badly blurred or oblique photos that gave most of the TUNE improvement are all in the TUNE half (TUNE: four photos with blur sigma 0.30 mm and/or obliquity 33-42 degrees; TEST: worst blur sigma 0.21 mm at 6 degrees, worst obliquity 23 degrees). The TUNE panel gain must not be read as the expected gain on new photos.
* **Thin cracks (< 0.5 mm) did not improve on the real photos**: panel MAE {a('legacy', P, 'all gate states', '< 0.5 mm', 'MAE'):.3f} (LEGACY) vs {a('shipped', P, 'all gate states', '< 0.5 mm', 'MAE'):.3f} (shipped) mm on TEST, a difference far below U_ref and the bootstrap interval but in the wrong direction; the 0.50 mm specimen is 8 um worse (0.030 -> 0.038 mm). On the renders the thin-crack MAE is {a('legacy', S, 'all gate states', '< 0.5 mm', 'MAE'):.3f} (LEGACY) vs {a('shipped', S, 'all gate states', '< 0.5 mm', 'MAE'):.3f}.
* The certified-only panel MAE is {a('legacy', P, 'certified only', 'all', 'MAE'):.3f} -> {a('shipped', P, 'certified only', 'all', 'MAE'):.3f} mm (n {int(a('legacy', P, 'certified only', 'all', 'n'))} -> {int(a('shipped', P, 'certified only', 'all', 'n'))}), a small gain ({chg(P, 'certified only', 'all'):+.0f} %) well inside the bootstrap interval, and the metric the product shows. The frozen gate was fitted on the legacy widths and has to be refitted on the new ones; this report does not do that.
* The 2.0 and 3.0 mm panel specimens are still under-read by 0.16 and 0.14 mm on TEST (LEGACY 0.18 and 0.15). The remaining cause (research/WIDTH_AUTORESEARCH.md section 7) is scale extrapolation from the board to the specimen, which grows with distance and obliquity; it is not the width estimator. Distance and width are confounded in this panel layout (thin specimens near the board, wide ones far), so the distance trend (`width_distance.png`) is a measurement, and the maximum-distance rule in the research note is a PROPOSAL; the gate refit decides it with distance as a gate feature.

## Against the published numbers (METRICS 1a; M2 = Hassouna et al., Sci. Rep. 2026; S8 = Deng et al., CACAIE 2026)

| | M2 < 0.5 mm | shipped, panel TEST (corrected) < 0.5 mm | shipped, renders TEST < 0.5 mm | M2 >= 0.5 mm | shipped, panel >= 0.5 mm | shipped, renders >= 0.5 mm | S8 |
|---|---|---|---|---|---|---|---|
| ratio (measured / true) | 0.89 | {a('shipped', P, 'all gate states', '< 0.5 mm', 'ratio'):.2f} | {a('shipped', S, 'all gate states', '< 0.5 mm', 'ratio'):.2f} | 0.98 | {a('shipped', P, 'all gate states', '>= 0.5 mm', 'ratio'):.2f} | {a('shipped', S, 'all gate states', '>= 0.5 mm', 'ratio'):.2f} | |
| COV | 21.9 % | {100 * a('shipped', P, 'all gate states', '< 0.5 mm', 'COV'):.1f} % | {100 * a('shipped', S, 'all gate states', '< 0.5 mm', 'COV'):.1f} % | 5.8 % | {100 * a('shipped', P, 'all gate states', '>= 0.5 mm', 'COV'):.1f} % | {100 * a('shipped', S, 'all gate states', '>= 0.5 mm', 'COV'):.1f} % | |
| MAE, all widths (mm) | | {a('shipped', P, 'all gate states', 'all', 'MAE'):.3f} | {a('shipped', S, 'all gate states', 'all', 'MAE'):.3f} | | | | 0.09 |
| MRE, all widths | | {100 * a('shipped', P, 'all gate states', 'all', 'MRE'):.1f} % | {100 * a('shipped', S, 'all gate states', 'all', 'MRE'):.1f} % | | | | 14.4 % |
| certified only: MAE (mm) / MRE | | {a('shipped', P, 'certified only', 'all', 'MAE'):.3f} / {100 * a('shipped', P, 'certified only', 'all', 'MRE'):.1f} % | | | | | |

Reading it honestly. The thin-crack bin has a ratio near 1 (M2: 0.89, an 11 % under-read) and a lower COV (M2: 21.9 %) on both sources, but the panel thin-crack ratio is {a('shipped', P, 'all gate states', '< 0.5 mm', 'ratio'):.2f}, an over-read of 10 % on the corrected truth (the toner-corrected reference itself carries the thin-stroke dot-gain caveat). For >= 0.5 mm the panel ratio is {a('shipped', P, 'all gate states', '>= 0.5 mm', 'ratio'):.2f} with COV {100 * a('shipped', P, 'all gate states', '>= 0.5 mm', 'COV'):.1f} % against M2's 0.98 and 5.8 %: the COV is the weak point (the geometry above). The Floor tier on all gate states is met on the real photos for MAE (0.070 <= 0.09), MRE and the thin bin; the Target (MAE 0.05 mm, P95 0.10 mm) is not met on all gate states, nor on the certified-only panel cracks (MAE {a('shipped', P, 'certified only', 'all', 'MAE'):.3f}, P95 {a('shipped', P, 'certified only', 'all', 'P95'):.3f}). S8's 0.09 mm MAE was measured on 15 cracks against a microscope with a LiDAR rig; this panel is a printed reference with U_ref = +-0.009 mm. M2 and S8 are not on the same targets or conditions, so these rows are context, not a head-to-head.

## Limitations (kept with the numbers)

* The panel reference is the nominal width plus 2 b (toner bleed measured on 20 mm squares and anisotropic: b_y 0.0137, b_x 0.0406 mm per edge). Dot gain on 0.30-0.50 mm strokes may differ, which is the caveat on the corrected thin-crack numbers. U_ref = +-0.009 mm on the reference.
* One printed sheet, one phone, one session; 8 TEST photos and 63 TEST cracks, so the intervals (MAE_lo, MAE_hi, bootstrap over photos or render ids) are wide and most differences between LEGACY and shipped on the real photos lie inside them.
* The synthetic truth at >= 0.5 mm is a per-station median over a crack whose width varies by about 30 % along its length, which puts a floor of roughly 0.05-0.1 mm on the synthetic MAE for wide cracks whatever the estimator; the renders' 3.0 mm bin (9 cracks on TEST) is dominated by a few locator-assignment outliers (bias -0.22 mm for both configurations).
* The black-core width (`width_blackcore_mm`) is accurate only close to 15 px/mm (gate-bin MAE 0.036 mm there, 0.081 at 10 px/mm, 0.048 at 20 px/mm); its all-profile RMSE against the operator reference at 15 px/mm is 0.18 mm, against 56 um for the published edge detector at native 252 px/mm. It is not a parity claim.
* krkCMd: the resolution-added error of the headline width (0.122 mm at 15 px/mm) is still 2.5x that of FWHM alone (0.049 mm): the blend is less stable than FWHM on textured profiles (open).
* The error-vs-px/mm curve in `width_error_vs_ppm.png` is not monotone because resolution is confounded with the photo (blur, obliquity) and with the widths present.
* Certification gate: fitted on the legacy widths and unchanged here; the certified-only rows use it as is. The refit is the orchestrator's.

"""
    p = RES / "width_eval.md"
    s = p.read_text(encoding="utf-8")
    first = "### shipped / panel (toner-corrected truth)"
    if MARK in s:
        s = s[:s.index(MARK)] + s[s.index(first):]
    i = s.index(first)
    p.write_text(s[:i] + txt + s[i:], encoding="utf-8")
    print("extras written")


if __name__ == "__main__":
    main()
