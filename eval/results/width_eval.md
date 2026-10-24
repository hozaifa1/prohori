# Crack-width estimator: held-out TEST evaluation (D18)

*Generated 2026-10-25 00:03 by `eval/width_final.py --split test`. Shipped configuration `measure.CFG` = `{"mask_sigma_mm": 0.15, "prof_sigma_mm": 0.12, "smooth_k": 1.2, "smooth_floor_mm": 0.03, "estimator": "mix", "wide": "fwhm_inv", "d_from": "max_ink_core_inv", "q_gate": true, "q_release": 4.5, "q_release_scale": 1.5, "inv_sigma_scale": 1.0, "agg": "median", "d0": 4.0, "dscale": 4.0, "core_f": 0.85, "core_corr_k": 1.7}`; LEGACY = `measure.LEGACY_CFG` (the 2026-10-19 estimator). The frozen certification gate (`gate_params.json`, fitted on the legacy widths) is used unchanged for the certified-only rows.*

**Reference.** Panel primary truth = nominal stroke width + 2 b (toner bleed b measured from the printed ChArUco squares, METRICS 1a): b_y = 0.0137 mm across the horizontal specimens (b_x = 0.0406), pooled over 14 capture-quality-selected photos; **U_ref = +-0.009 mm** on the reference (across-photo spread). Errors below U_ref are not meaningful (METRICS section 0 rule 5). Synthetic truth is exact. MAE columns carry a 95 % bootstrap CI over photo groups / render ids.

<!-- extras -->
## Summary: before / after, tune vs test (MAE in mm; every panel MAE carries U_ref = +-0.009 mm)

LEGACY is the fixed 2026-10-19 estimator, scored on both splits so that the before/after is like for like. `n` is the TEST count. The TUNE columns are the split used for the loop and for the V1/V2/V3 mid-range selection; the TEST columns were produced once, after the configuration was frozen.

| set | n (test) | LEGACY tune | shipped tune | change | LEGACY test | shipped test | change |
|---|---|---|---|---|---|---|---|
| panel, all gate states, all widths | 63 | 0.120 | 0.099 | -18 % | 0.075 | 0.070 | -7 % |
| panel, all gate states, < 0.5 mm | 16 | 0.043 | 0.044 | +2 % | 0.053 | 0.055 | +4 % |
| panel, all gate states, >= 0.5 mm | 47 | 0.148 | 0.119 | -20 % | 0.082 | 0.075 | -9 % |
| panel, certified only, all widths | 41 | 0.050 | 0.050 | +0 % | 0.059 | 0.056 | -6 % |
| panel, nominal truth, all widths | 63 | 0.118 | 0.100 | -15 % | 0.074 | 0.073 | -1 % |
| synthetic, all widths | 162 | 0.102 | 0.091 | -10 % | 0.121 | 0.098 | -19 % |
| synthetic, < 0.5 mm | 28 | 0.058 | 0.048 | -18 % | 0.052 | 0.050 | -4 % |
| synthetic, >= 0.5 mm | 134 | 0.111 | 0.100 | -9 % | 0.134 | 0.108 | -20 % |

**In plain words.**
* On the **photoreal renders** the improvement holds and is larger on TEST than on TUNE (MAE 0.121 -> 0.098 mm, -19 %), mostly on widths from 0.75 mm up.
* On the **real printed-panel photos** the gain on TEST is much smaller than on TUNE (0.075 -> 0.070 mm, -7 %), inside the bootstrap interval of either number. TEST is the easier half: LEGACY's panel MAE is 0.075 there against 0.120 on TUNE, because the badly blurred or oblique photos that gave most of the TUNE improvement are all in the TUNE half (TUNE: four photos with blur sigma 0.30 mm and/or obliquity 33-42 degrees; TEST: worst blur sigma 0.21 mm at 6 degrees, worst obliquity 23 degrees). The TUNE panel gain must not be read as the expected gain on new photos.
* **Thin cracks (< 0.5 mm) did not improve on the real photos**: panel MAE 0.053 (LEGACY) vs 0.055 (shipped) mm on TEST, a difference far below U_ref and the bootstrap interval but in the wrong direction; the 0.50 mm specimen is 8 um worse (0.030 -> 0.038 mm). On the renders the thin-crack MAE is 0.052 (LEGACY) vs 0.050.
* The certified-only panel MAE is 0.059 -> 0.056 mm (n 39 -> 41), a small gain (-6 %) well inside the bootstrap interval, and the metric the product shows. The frozen gate was fitted on the legacy widths and has to be refitted on the new ones; this report does not do that.
* The 2.0 and 3.0 mm panel specimens are still under-read by 0.16 and 0.14 mm on TEST (LEGACY 0.18 and 0.15). The remaining cause (research/WIDTH_AUTORESEARCH.md section 7) is scale extrapolation from the board to the specimen, which grows with distance and obliquity; it is not the width estimator. Distance and width are confounded in this panel layout (thin specimens near the board, wide ones far), so the distance trend (`width_distance.png`) is a measurement, and the maximum-distance rule in the research note is a PROPOSAL; the gate refit decides it with distance as a gate feature.

## Against the published numbers (METRICS 1a; M2 = Hassouna et al., Sci. Rep. 2026; S8 = Deng et al., CACAIE 2026)

| | M2 < 0.5 mm | shipped, panel TEST (corrected) < 0.5 mm | shipped, renders TEST < 0.5 mm | M2 >= 0.5 mm | shipped, panel >= 0.5 mm | shipped, renders >= 0.5 mm | S8 |
|---|---|---|---|---|---|---|---|
| ratio (measured / true) | 0.89 | 1.10 | 1.01 | 0.98 | 0.98 | 1.03 | |
| COV | 21.9 % | 13.1 % | 16.4 % | 5.8 % | 7.0 % | 10.9 % | |
| MAE, all widths (mm) | | 0.070 | 0.098 | | | | 0.09 |
| MRE, all widths | | 7.4 % | 9.0 % | | | | 14.4 % |
| certified only: MAE (mm) / MRE | | 0.056 / 3.9 % | | | | | |

Reading it honestly. The thin-crack bin has a ratio near 1 (M2: 0.89, an 11 % under-read) and a lower COV (M2: 21.9 %) on both sources, but the panel thin-crack ratio is 1.10, an over-read of 10 % on the corrected truth (the toner-corrected reference itself carries the thin-stroke dot-gain caveat). For >= 0.5 mm the panel ratio is 0.98 with COV 7.0 % against M2's 0.98 and 5.8 %: the COV is the weak point (the geometry above). The Floor tier on all gate states is met on the real photos for MAE (0.070 <= 0.09), MRE and the thin bin; the Target (MAE 0.05 mm, P95 0.10 mm) is not met on all gate states, nor on the certified-only panel cracks (MAE 0.056, P95 0.143). S8's 0.09 mm MAE was measured on 15 cracks against a microscope with a LiDAR rig; this panel is a printed reference with U_ref = +-0.009 mm. M2 and S8 are not on the same targets or conditions, so these rows are context, not a head-to-head.

## Limitations (kept with the numbers)

* The panel reference is the nominal width plus 2 b (toner bleed measured on 20 mm squares and anisotropic: b_y 0.0137, b_x 0.0406 mm per edge). Dot gain on 0.30-0.50 mm strokes may differ, which is the caveat on the corrected thin-crack numbers. U_ref = +-0.009 mm on the reference.
* One printed sheet, one phone, one session; 8 TEST photos and 63 TEST cracks, so the intervals (MAE_lo, MAE_hi, bootstrap over photos or render ids) are wide and most differences between LEGACY and shipped on the real photos lie inside them.
* The synthetic truth at >= 0.5 mm is a per-station median over a crack whose width varies by about 30 % along its length, which puts a floor of roughly 0.05-0.1 mm on the synthetic MAE for wide cracks whatever the estimator; the renders' 3.0 mm bin (9 cracks on TEST) is dominated by a few locator-assignment outliers (bias -0.22 mm for both configurations).
* The black-core width (`width_blackcore_mm`) is accurate only close to 15 px/mm (gate-bin MAE 0.036 mm there, 0.081 at 10 px/mm, 0.048 at 20 px/mm); its all-profile RMSE against the operator reference at 15 px/mm is 0.18 mm, against 56 um for the published edge detector at native 252 px/mm. It is not a parity claim.
* krkCMd: the resolution-added error of the headline width (0.122 mm at 15 px/mm) is still 2.5x that of FWHM alone (0.049 mm): the blend is less stable than FWHM on textured profiles (open).
* The error-vs-px/mm curve in `width_error_vs_ppm.png` is not monotone because resolution is confounded with the photo (blur, obliquity) and with the widths present.
* Certification gate: fitted on the legacy widths and unchanged here; the certified-only rows use it as is. The refit is the orchestrator's.

### shipped / panel (toner-corrected truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 16 | 0.037 | 0.055 | 0.035 | 0.077 | 0.009 | 0.124 | 1.100 | 13.1 % | 14.7 % |
| all gate states | >= 0.5 mm | 47 | -0.056 | 0.075 | 0.048 | 0.111 | 0.009 | 0.225 | 0.982 | 7.0 % | 4.9 % |
| all gate states | all | 63 | -0.032 | 0.070 | 0.048 | 0.098 | 0.009 | 0.209 | 1.012 | 10.6 % | 7.4 % |
| certified only | < 0.5 mm | 5 | -0.020 | 0.036 | 0.014 | 0.056 | 0.009 | 0.056 | 0.943 | 9.5 % | 9.3 % |
| certified only | >= 0.5 mm | 36 | -0.048 | 0.059 | 0.042 | 0.077 | 0.009 | 0.158 | 0.981 | 3.7 % | 3.2 % |
| certified only | all | 41 | -0.045 | 0.056 | 0.042 | 0.074 | 0.009 | 0.143 | 0.976 | 4.9 % | 3.9 % |

### shipped / synthetic (exact truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 28 | 0.003 | 0.050 | 0.036 | 0.067 | None | 0.115 | 1.006 | 16.4 % | 12.9 % |
| all gate states | >= 0.5 mm | 134 | 0.023 | 0.108 | 0.086 | 0.133 | None | 0.361 | 1.029 | 10.9 % | 8.2 % |
| all gate states | all | 162 | 0.020 | 0.098 | 0.080 | 0.119 | None | 0.344 | 1.025 | 12.0 % | 9.0 % |
| certified only | >= 0.5 mm | 4 | 0.058 | 0.062 | 0.013 | 0.111 | None | 0.127 | 1.043 | 3.9 % | 4.8 % |
| certified only | all | 4 | 0.058 | 0.062 | 0.013 | 0.111 | None | 0.127 | 1.043 | 3.9 % | 4.8 % |

### shipped / panel (nominal truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 16 | 0.065 | 0.072 | 0.044 | 0.100 | None | 0.152 | 1.190 | 13.2 % | 21.1 % |
| all gate states | >= 0.5 mm | 47 | -0.027 | 0.073 | 0.050 | 0.105 | None | 0.195 | 1.010 | 8.1 % | 6.0 % |
| all gate states | all | 63 | -0.003 | 0.073 | 0.051 | 0.100 | None | 0.180 | 1.056 | 12.5 % | 9.8 % |
| certified only | < 0.5 mm | 5 | 0.008 | 0.030 | 0.014 | 0.066 | None | 0.059 | 1.018 | 9.2 % | 8.2 % |
| certified only | >= 0.5 mm | 36 | -0.020 | 0.055 | 0.044 | 0.069 | None | 0.130 | 1.004 | 4.6 % | 3.8 % |
| certified only | all | 41 | -0.016 | 0.052 | 0.041 | 0.067 | None | 0.114 | 1.006 | 5.4 % | 4.4 % |

### legacy / panel (toner-corrected truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 16 | 0.036 | 0.053 | 0.034 | 0.073 | 0.009 | 0.111 | 1.098 | 12.2 % | 14.2 % |
| all gate states | >= 0.5 mm | 47 | -0.069 | 0.082 | 0.050 | 0.131 | 0.009 | 0.253 | 0.968 | 7.1 % | 5.3 % |
| all gate states | all | 63 | -0.042 | 0.075 | 0.049 | 0.112 | 0.009 | 0.212 | 1.001 | 10.6 % | 7.5 % |
| certified only | < 0.5 mm | 4 | -0.033 | 0.033 | 0.010 | 0.055 | 0.009 | 0.056 | 0.912 | 7.0 % | 8.8 % |
| certified only | >= 0.5 mm | 35 | -0.055 | 0.062 | 0.047 | 0.078 | 0.009 | 0.159 | 0.973 | 3.6 % | 3.6 % |
| certified only | all | 39 | -0.053 | 0.059 | 0.047 | 0.075 | 0.009 | 0.148 | 0.967 | 4.4 % | 4.1 % |

### legacy / synthetic (exact truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 26 | -0.006 | 0.052 | 0.037 | 0.070 | None | 0.102 | 0.978 | 17.0 % | 13.4 % |
| all gate states | >= 0.5 mm | 134 | 0.023 | 0.134 | 0.107 | 0.165 | None | 0.429 | 1.032 | 14.8 % | 10.6 % |
| all gate states | all | 160 | 0.018 | 0.121 | 0.098 | 0.146 | None | 0.406 | 1.023 | 15.3 % | 11.1 % |
| certified only | >= 0.5 mm | 3 | 0.070 | 0.070 | 0.005 | 0.117 | None | 0.114 | 1.053 | 3.4 % | 5.3 % |
| certified only | all | 3 | 0.070 | 0.070 | 0.005 | 0.117 | None | 0.114 | 1.053 | 3.4 % | 5.3 % |

### legacy / panel (nominal truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 16 | 0.064 | 0.071 | 0.046 | 0.097 | None | 0.139 | 1.188 | 12.4 % | 20.8 % |
| all gate states | >= 0.5 mm | 47 | -0.040 | 0.074 | 0.043 | 0.122 | None | 0.224 | 0.996 | 8.1 % | 5.7 % |
| all gate states | all | 63 | -0.014 | 0.074 | 0.046 | 0.112 | None | 0.183 | 1.045 | 12.6 % | 9.5 % |
| certified only | < 0.5 mm | 4 | -0.005 | 0.023 | 0.018 | 0.027 | None | 0.028 | 0.987 | 6.8 % | 6.7 % |
| certified only | >= 0.5 mm | 35 | -0.026 | 0.051 | 0.039 | 0.066 | None | 0.131 | 0.996 | 4.2 % | 3.4 % |
| certified only | all | 39 | -0.024 | 0.048 | 0.037 | 0.064 | None | 0.120 | 0.995 | 4.6 % | 3.7 % |

### Tier check (METRICS 1a), shipped configuration, primary truth

| set | tier | criteria |
|---|---|---|
| shipped / panel (toner-corrected truth) / all gate states | Floor | MAE <= 0.09: PASS; MRE <= 14.4 %: PASS; < 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: fail |
| shipped / panel (toner-corrected truth) / all gate states | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: fail; < 0.5 mm |ratio-1| <= 0.05, COV <= 12 %: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / panel (toner-corrected truth) / all gate states | Stretch | MAE <= 0.03: fail; < 0.5 mm COV <= 8 %: fail; >= 0.5 mm COV <= 3 %: fail |
| shipped / panel (toner-corrected truth) / certified only | Floor | MAE <= 0.09: PASS; MRE <= 14.4 %: PASS; < 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: PASS |
| shipped / panel (toner-corrected truth) / certified only | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: fail; < 0.5 mm |ratio-1| <= 0.05, COV <= 12 %: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: PASS |
| shipped / panel (toner-corrected truth) / certified only | Stretch | MAE <= 0.03: fail; < 0.5 mm COV <= 8 %: fail; >= 0.5 mm COV <= 3 %: fail |
| shipped / synthetic (exact truth) / all gate states | Floor | MAE <= 0.09: fail; MRE <= 14.4 %: PASS; < 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: fail |
| shipped / synthetic (exact truth) / all gate states | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: PASS; < 0.5 mm |ratio-1| <= 0.05, COV <= 12 %: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / synthetic (exact truth) / all gate states | Stretch | MAE <= 0.03: fail; < 0.5 mm COV <= 8 %: fail; >= 0.5 mm COV <= 3 %: fail |
| shipped / synthetic (exact truth) / certified only | Floor | MAE <= 0.09: PASS; MRE <= 14.4 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: fail |
| shipped / synthetic (exact truth) / certified only | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / synthetic (exact truth) / certified only | Stretch | MAE <= 0.03: fail; >= 0.5 mm COV <= 3 %: fail |

### Per-specimen residuals (bias / MAE in mm; nominal truth next to corrected truth)

**shipped**

| width mm | panel_n | panel_bias_cor | panel_MAE_cor | panel_bias_nom | panel_MAE_nom | synth_n | synth_bias_cor | synth_MAE_cor |
|---|---|---|---|---|---|---|---|---|
| 0.300 | 8 | 0.037 | 0.054 | 0.065 | 0.072 | 10 | -0.005 | 0.035 |
| 0.400 | 8 | 0.037 | 0.056 | 0.066 | 0.072 | 13 | -0.007 | 0.064 |
| 0.500 | 8 | 0.028 | 0.038 | 0.057 | 0.057 | 25 | 0.043 | 0.059 |
| 0.750 | 8 | 0.020 | 0.020 | 0.049 | 0.049 | 25 | -0.008 | 0.059 |
| 1.000 | 8 | -0.028 | 0.033 | 0.000 | 0.041 | 26 | 0.069 | 0.078 |
| 1.500 | 8 | -0.059 | 0.059 | -0.030 | 0.042 | 33 | 0.064 | 0.096 |
| 2.000 | 8 | -0.162 | 0.162 | -0.134 | 0.134 | 21 | 0.024 | 0.142 |
| 3.000 | 7 | -0.144 | 0.144 | -0.114 | 0.120 | 9 | -0.219 | 0.390 |


**legacy**

| width mm | panel_n | panel_bias_cor | panel_MAE_cor | panel_bias_nom | panel_MAE_nom | synth_n | synth_bias_cor | synth_MAE_cor |
|---|---|---|---|---|---|---|---|---|
| 0.300 | 8 | 0.036 | 0.053 | 0.064 | 0.071 | 8 | -0.031 | 0.047 |
| 0.400 | 8 | 0.037 | 0.052 | 0.065 | 0.071 | 13 | -0.008 | 0.060 |
| 0.500 | 8 | 0.015 | 0.030 | 0.044 | 0.047 | 25 | 0.054 | 0.069 |
| 0.750 | 8 | 0.005 | 0.025 | 0.034 | 0.041 | 25 | 0.004 | 0.087 |
| 1.000 | 8 | -0.043 | 0.043 | -0.015 | 0.040 | 26 | 0.049 | 0.114 |
| 1.500 | 8 | -0.070 | 0.070 | -0.041 | 0.046 | 33 | 0.053 | 0.154 |
| 2.000 | 8 | -0.183 | 0.183 | -0.154 | 0.154 | 21 | 0.033 | 0.137 |
| 3.000 | 7 | -0.149 | 0.149 | -0.119 | 0.125 | 9 | -0.208 | 0.368 |


### krkCMd (black-core convention and resolution cost)

| config | px/mm | headline resolution-added (0.30-0.50 mm) | FWHM alone | black-core MAE vs MANwidth (gate bin) | black-core RMSE vs MANwidth (all crack-present) |
|---|---|---|---|---|---|
| shipped | 10 | 0.144 | 0.065 | 0.081 | 0.305 |
| shipped | 15 | 0.122 | 0.049 | 0.036 | 0.183 |
| shipped | 20 | 0.088 | 0.032 | 0.048 | 0.138 |
| legacy | 10 | 0.156 | 0.067 | 0.190 | 0.184 |
| legacy | 15 | 0.133 | 0.055 | 0.196 | 0.169 |
| legacy | 20 | 0.097 | 0.040 | 0.199 | 0.167 |

Published analytic edge detector (M1): RMSE 56 um on all profiles at 252 px/mm; inter-operator floor 16.6 um. The rows above are at simulated PHONE resolution (not comparable one-to-one to native 252 px/mm).
