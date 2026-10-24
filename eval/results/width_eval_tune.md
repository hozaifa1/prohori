# Crack-width estimator: TUNE (dry run, not the claim) evaluation (D18)

*Generated 2026-10-25 00:04 by `eval/width_final.py --split tune`. Shipped configuration `measure.CFG` = `{"mask_sigma_mm": 0.15, "prof_sigma_mm": 0.12, "smooth_k": 1.2, "smooth_floor_mm": 0.03, "estimator": "mix", "wide": "fwhm_inv", "d_from": "max_ink_core_inv", "q_gate": true, "q_release": 4.5, "q_release_scale": 1.5, "inv_sigma_scale": 1.0, "agg": "median", "d0": 4.0, "dscale": 4.0, "core_f": 0.85, "core_corr_k": 1.7}`; LEGACY = `measure.LEGACY_CFG` (the 2026-10-19 estimator). The frozen certification gate (`gate_params.json`, fitted on the legacy widths) is used unchanged for the certified-only rows.*

**Reference.** Panel primary truth = nominal stroke width + 2 b (toner bleed b measured from the printed ChArUco squares, METRICS 1a): b_y = 0.0137 mm across the horizontal specimens (b_x = 0.0406), pooled over 14 capture-quality-selected photos; **U_ref = +-0.009 mm** on the reference (across-photo spread). Errors below U_ref are not meaningful (METRICS section 0 rule 5). Synthetic truth is exact. MAE columns carry a 95 % bootstrap CI over photo groups / render ids.

### shipped / panel (toner-corrected truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 28 | 0.030 | 0.044 | 0.032 | 0.057 | 0.009 | 0.093 | 1.081 | 10.6 % | 12.0 % |
| all gate states | >= 0.5 mm | 77 | -0.103 | 0.119 | 0.053 | 0.181 | 0.009 | 0.498 | 0.943 | 11.8 % | 8.1 % |
| all gate states | all | 105 | -0.067 | 0.099 | 0.048 | 0.147 | 0.009 | 0.444 | 0.980 | 13.0 % | 9.1 % |
| certified only | < 0.5 mm | 7 | -0.007 | 0.017 | 0.009 | 0.026 | 0.009 | 0.033 | 0.979 | 5.9 % | 5.1 % |
| certified only | >= 0.5 mm | 44 | -0.042 | 0.055 | 0.034 | 0.085 | 0.009 | 0.199 | 0.982 | 4.3 % | 3.3 % |
| certified only | all | 51 | -0.037 | 0.050 | 0.031 | 0.078 | 0.009 | 0.176 | 0.982 | 4.6 % | 3.6 % |

### shipped / synthetic (exact truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 41 | -0.003 | 0.048 | 0.037 | 0.061 | None | 0.104 | 0.985 | 16.0 % | 12.9 % |
| all gate states | >= 0.5 mm | 195 | 0.025 | 0.100 | 0.085 | 0.117 | None | 0.348 | 1.020 | 10.8 % | 7.2 % |
| all gate states | all | 236 | 0.020 | 0.091 | 0.078 | 0.106 | None | 0.316 | 1.014 | 11.9 % | 8.2 % |
| certified only | >= 0.5 mm | 7 | 0.132 | 0.132 | 0.066 | 0.203 | None | 0.274 | 1.072 | 3.8 % | 7.2 % |
| certified only | all | 7 | 0.132 | 0.132 | 0.066 | 0.203 | None | 0.274 | 1.072 | 3.8 % | 7.2 % |

### shipped / panel (nominal truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 28 | 0.058 | 0.062 | 0.043 | 0.081 | None | 0.121 | 1.169 | 10.7 % | 18.2 % |
| all gate states | >= 0.5 mm | 77 | -0.074 | 0.114 | 0.055 | 0.169 | None | 0.469 | 0.971 | 12.4 % | 8.6 % |
| all gate states | all | 105 | -0.039 | 0.100 | 0.054 | 0.144 | None | 0.416 | 1.024 | 14.6 % | 11.1 % |
| certified only | < 0.5 mm | 7 | 0.021 | 0.023 | 0.012 | 0.038 | None | 0.047 | 1.061 | 5.8 % | 6.8 % |
| certified only | >= 0.5 mm | 44 | -0.013 | 0.052 | 0.038 | 0.077 | None | 0.170 | 1.005 | 4.9 % | 3.8 % |
| certified only | all | 51 | -0.008 | 0.048 | 0.035 | 0.072 | None | 0.147 | 1.013 | 5.4 % | 4.2 % |

### legacy / panel (toner-corrected truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 28 | 0.030 | 0.043 | 0.030 | 0.056 | 0.009 | 0.092 | 1.080 | 10.3 % | 11.8 % |
| all gate states | >= 0.5 mm | 77 | -0.138 | 0.148 | 0.061 | 0.231 | 0.009 | 0.580 | 0.922 | 13.3 % | 9.3 % |
| all gate states | all | 105 | -0.093 | 0.120 | 0.055 | 0.183 | 0.009 | 0.505 | 0.964 | 14.4 % | 9.9 % |
| certified only | < 0.5 mm | 5 | -0.016 | 0.020 | 0.006 | 0.034 | 0.009 | 0.039 | 0.952 | 5.6 % | 5.6 % |
| certified only | >= 0.5 mm | 41 | -0.047 | 0.053 | 0.037 | 0.074 | 0.009 | 0.150 | 0.975 | 3.8 % | 3.2 % |
| certified only | all | 46 | -0.044 | 0.050 | 0.035 | 0.071 | 0.009 | 0.145 | 0.972 | 4.1 % | 3.5 % |

### legacy / synthetic (exact truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 40 | 0.020 | 0.058 | 0.042 | 0.077 | None | 0.148 | 1.051 | 19.7 % | 15.5 % |
| all gate states | >= 0.5 mm | 195 | 0.020 | 0.111 | 0.095 | 0.129 | None | 0.386 | 1.019 | 12.8 % | 8.3 % |
| all gate states | all | 235 | 0.020 | 0.102 | 0.087 | 0.117 | None | 0.367 | 1.024 | 14.3 % | 9.5 % |
| certified only | >= 0.5 mm | 6 | 0.122 | 0.122 | 0.049 | 0.197 | None | 0.254 | 1.053 | 3.2 % | 5.3 % |
| certified only | all | 6 | 0.122 | 0.122 | 0.049 | 0.197 | None | 0.254 | 1.053 | 3.2 % | 5.3 % |

### legacy / panel (nominal truth)

| gate | bin | n | bias | MAE | MAE_lo | MAE_hi | U_ref | P95 | ratio | COV | MRE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all gate states | < 0.5 mm | 28 | 0.058 | 0.062 | 0.044 | 0.080 | None | 0.120 | 1.168 | 10.4 % | 18.1 % |
| all gate states | >= 0.5 mm | 77 | -0.110 | 0.138 | 0.058 | 0.216 | None | 0.552 | 0.949 | 13.8 % | 9.3 % |
| all gate states | all | 105 | -0.065 | 0.118 | 0.058 | 0.178 | None | 0.475 | 1.008 | 16.0 % | 11.7 % |
| certified only | < 0.5 mm | 5 | 0.012 | 0.018 | 0.009 | 0.031 | None | 0.035 | 1.032 | 5.0 % | 5.1 % |
| certified only | >= 0.5 mm | 41 | -0.018 | 0.046 | 0.033 | 0.064 | None | 0.120 | 0.998 | 4.3 % | 3.2 % |
| certified only | all | 46 | -0.015 | 0.043 | 0.030 | 0.060 | None | 0.115 | 1.002 | 4.5 % | 3.4 % |

### Tier check (METRICS 1a), shipped configuration, primary truth

| set | tier | criteria |
|---|---|---|
| shipped / panel (toner-corrected truth) / all gate states | Floor | MAE <= 0.09: fail; MRE <= 14.4 %: PASS; < 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: fail |
| shipped / panel (toner-corrected truth) / all gate states | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: fail; < 0.5 mm |ratio-1| <= 0.05, COV <= 12 %: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / panel (toner-corrected truth) / all gate states | Stretch | MAE <= 0.03: fail; < 0.5 mm COV <= 8 %: fail; >= 0.5 mm COV <= 3 %: fail |
| shipped / panel (toner-corrected truth) / certified only | Floor | MAE <= 0.09: PASS; MRE <= 14.4 %: PASS; < 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: PASS |
| shipped / panel (toner-corrected truth) / certified only | Target | MAE <= 0.05: PASS; P95 <= 0.10: fail; |bias| <= 0.02: fail; < 0.5 mm |ratio-1| <= 0.05, COV <= 12 %: PASS; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / panel (toner-corrected truth) / certified only | Stretch | MAE <= 0.03: fail; < 0.5 mm COV <= 8 %: PASS; >= 0.5 mm COV <= 3 %: fail |
| shipped / synthetic (exact truth) / all gate states | Floor | MAE <= 0.09: fail; MRE <= 14.4 %: PASS; < 0.5 mm ratio in [0.89, 1.11], COV <= 21.9 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: fail |
| shipped / synthetic (exact truth) / all gate states | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: PASS; < 0.5 mm |ratio-1| <= 0.05, COV <= 12 %: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / synthetic (exact truth) / all gate states | Stretch | MAE <= 0.03: fail; < 0.5 mm COV <= 8 %: fail; >= 0.5 mm COV <= 3 %: fail |
| shipped / synthetic (exact truth) / certified only | Floor | MAE <= 0.09: fail; MRE <= 14.4 %: PASS; >= 0.5 mm ratio in [0.98, 1.02], COV <= 5.8 %: fail |
| shipped / synthetic (exact truth) / certified only | Target | MAE <= 0.05: fail; P95 <= 0.10: fail; |bias| <= 0.02: fail; >= 0.5 mm |ratio-1| <= 0.02, COV <= 4 %: fail |
| shipped / synthetic (exact truth) / certified only | Stretch | MAE <= 0.03: fail; >= 0.5 mm COV <= 3 %: fail |

### Per-specimen residuals (bias / MAE in mm; nominal truth next to corrected truth)

**shipped**

| width mm | panel_n | panel_bias_cor | panel_MAE_cor | panel_bias_nom | panel_MAE_nom | synth_n | synth_bias_cor | synth_MAE_cor |
|---|---|---|---|---|---|---|---|---|
| 0.300 | 14 | 0.027 | 0.047 | 0.055 | 0.062 | 15 | -0.011 | 0.042 |
| 0.400 | 14 | 0.033 | 0.042 | 0.062 | 0.063 | 16 | 0.010 | 0.051 |
| 0.500 | 14 | -0.002 | 0.038 | 0.027 | 0.048 | 31 | -0.005 | 0.051 |
| 0.750 | 14 | 0.006 | 0.033 | 0.035 | 0.051 | 34 | 0.033 | 0.053 |
| 1.000 | 13 | -0.099 | 0.111 | -0.070 | 0.109 | 43 | 0.010 | 0.072 |
| 1.500 | 13 | -0.113 | 0.113 | -0.084 | 0.096 | 37 | 0.062 | 0.096 |
| 2.000 | 11 | -0.295 | 0.295 | -0.267 | 0.267 | 41 | 0.033 | 0.127 |
| 3.000 | 12 | -0.165 | 0.166 | -0.135 | 0.146 | 19 | -0.020 | 0.254 |


**legacy**

| width mm | panel_n | panel_bias_cor | panel_MAE_cor | panel_bias_nom | panel_MAE_nom | synth_n | synth_bias_cor | synth_MAE_cor |
|---|---|---|---|---|---|---|---|---|
| 0.300 | 14 | 0.026 | 0.045 | 0.054 | 0.061 | 14 | 0.009 | 0.047 |
| 0.400 | 14 | 0.035 | 0.041 | 0.063 | 0.064 | 16 | 0.045 | 0.062 |
| 0.500 | 14 | -0.009 | 0.033 | 0.020 | 0.041 | 31 | 0.003 | 0.060 |
| 0.750 | 14 | -0.009 | 0.031 | 0.020 | 0.043 | 34 | 0.043 | 0.068 |
| 1.000 | 13 | -0.121 | 0.125 | -0.093 | 0.113 | 43 | 0.007 | 0.084 |
| 1.500 | 13 | -0.130 | 0.131 | -0.101 | 0.113 | 37 | 0.037 | 0.123 |
| 2.000 | 11 | -0.357 | 0.357 | -0.328 | 0.329 | 41 | 0.012 | 0.139 |
| 3.000 | 12 | -0.268 | 0.269 | -0.238 | 0.245 | 19 | 0.004 | 0.225 |


### krkCMd (black-core convention and resolution cost)

| config | px/mm | headline resolution-added (0.30-0.50 mm) | FWHM alone | black-core MAE vs MANwidth (gate bin) | black-core RMSE vs MANwidth (all crack-present) |
|---|---|---|---|---|---|
| shipped | 10 | 0.136 | 0.062 | 0.071 | 0.211 |
| shipped | 15 | 0.119 | 0.045 | 0.043 | 0.133 |
| shipped | 20 | 0.089 | 0.031 | 0.051 | 0.105 |
| legacy | 10 | 0.154 | 0.064 | 0.205 | 0.198 |
| legacy | 15 | 0.130 | 0.053 | 0.209 | 0.197 |
| legacy | 20 | 0.098 | 0.038 | 0.212 | 0.195 |

Published analytic edge detector (M1): RMSE 56 um on all profiles at 252 px/mm; inter-operator floor 16.6 um. The rows above are at simulated PHONE resolution (not comparable one-to-one to native 252 px/mm).
