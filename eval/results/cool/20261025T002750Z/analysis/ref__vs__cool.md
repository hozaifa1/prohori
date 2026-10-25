### ref  vs  cool   (speedup = ref time / cool time; >1 means cool is faster)

| stage | ref p50 ms | cool p50 ms | ref p95 ms | cool p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 52.6 | 52.0 | 66.3 | 67.1 | 1.003 [0.991, 1.014] | 1.012 [0.956, 1.022] | 0.988 [0.954, 1.030] |
| detect | 77.9 | 74.1 | 97.6 | 94.5 | 1.046 [1.043, 1.050] | 1.051 [1.038, 1.056] | 1.033 [1.019, 1.042] |
| rectify | 82.3 | 78.5 | 96.5 | 90.7 | 1.050 [1.047, 1.054] | 1.048 [1.035, 1.070] | 1.064 [1.031, 1.068] |
| measure | 42.4 | 42.9 | 188.5 | 191.3 | 0.993 [0.990, 0.997] | 0.988 [0.963, 1.018] | 0.985 [0.970, 1.015] |
| other | 53.2 | 52.3 | 71.1 | 69.5 | 1.024 [1.020, 1.027] | 1.017 [1.007, 1.046] | 1.023 [1.010, 1.055] |
| analyze | 268.2 | 260.4 | 408.4 | 398.5 | 1.029 [1.027, 1.031] | 1.030 [1.022, 1.047] | 1.025 [1.012, 1.032] |
| e2e | 317.6 | 310.2 | 466.3 | 453.5 | 1.025 [1.022, 1.027] | 1.024 [1.011, 1.034] | 1.028 [1.015, 1.031] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | ref | cool | speedup ref/cool |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15922 | 15292 | 1.041 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7427 | 7405 | 1.003 |
| analyze total (ms) | 23350 | 22697 | 1.029 |
| OpenCV share of analyze | 68.2 % | 67.4 % | |

Amdahl check: a 1.04x speedup of a 68 % OpenCV share predicts 1.028x end to end; even a 2x faster OpenCV would give only 1.52x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | ref fps | cool fps | x fps | ref e2e p50/p95 ms | cool e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.03 | 3.10 | 1.022 | 334/470 | 327/460 |
| 2x1 | 5.95 | 6.09 | 1.024 | 338/473 | 329/465 |
| 4x1 | 11.43 | 11.69 | 1.023 | 346/483 | 342/468 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | ref ms | cool ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 64.602 | 62.909 | 1.03 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.604 | 3.729 | 0.97 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.685 | 0.526 | 1.30 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 17.543 | 16.141 | 1.09 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.753 | 0.748 | 1.01 | NO |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.853 | 8.636 | 0.56 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.760 | 2.113 | 1.31 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.990 | 6.115 | 0.98 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.488 | 1.113 | 1.34 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.674 | 0.460 | 1.47 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.201 | 0.148 | 1.36 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.609 | 2.636 | 0.99 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.246 | 5.274 | 0.99 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.072 | 0.99 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.795 | 1.772 | 1.01 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.501 | 3.092 | 2.43 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.649 | 0.639 | 1.02 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.913 | 6.339 | 1.09 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.772 | 2.761 | 1.00 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.298 | 1.393 | 1.65 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.038 | 0.037 | 1.03 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.079 | 0.060 | 1.32 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.786 | 2.776 | 1.00 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.410 | 1.413 | 1.00 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.640 | 3.465 | 0.76 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 76.424 | 72.512 | 1.05 | yes |
| 4 | imdecode_jpeg_12MP | 4096x3072 | 64.500 | 62.452 | 1.03 | yes |
| 4 | cvtColor_BGR2GRAY | 4096x3072x3 | 1.048 | 1.054 | 0.99 | yes |
| 4 | resize_AREA_grey_x0.5 | 4096x3072 | 0.610 | 0.150 | 4.06 | yes |
| 4 | resize_AREA_grey_x0.3 | 4096x3072 | 4.923 | 5.265 | 0.94 | yes |
| 4 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.271 | 0.276 | 0.98 | NO |
| 4 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 1.222 | 2.284 | 0.54 | NO |
| 4 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 0.712 | 0.577 | 1.23 | NO |
| 4 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 1.509 | 1.536 | 0.98 | yes |
| 4 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.527 | 0.467 | 1.13 | yes |
| 4 | erode_7x7_u8 | 1273x1800 | 0.682 | 0.463 | 1.47 | yes |
| 4 | erode_5x5_u8_ROI | 2000x500 | 0.199 | 0.152 | 1.30 | yes |
| 4 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 0.661 | 0.676 | 0.98 | yes |
| 4 | GaussianBlur_f32_sigma4 | 2000x500 | 5.389 | 5.450 | 0.99 | yes |
| 4 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.072 | 0.97 | yes |
| 4 | dilate_f32_rect | 2000x500 k=17 | 1.809 | 1.807 | 1.00 | yes |
| 4 | medianBlur_u8_k15 | 318x450 | 7.468 | 1.703 | 4.38 | yes |
| 4 | morphologyEx_close_ellipse | 1273x1800 | 0.380 | 0.385 | 0.99 | yes |
| 4 | connectedComponentsWithStats | 1273x1800 | - | - | - | FAILED: A: ok; B: child rc=-6 (crash): Fatal glibc error: malloc.c:2599 (sysmalloc): assertion failed: (old_top == ini |
| 4 | ximgproc_thinning | 1884x204 | 2.682 | 2.669 | 1.00 | yes |
| 4 | distanceTransform_L2_precise | 1884x204 | 0.694 | 0.422 | 1.65 | yes |
| 4 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.016 | 0.016 | 1.00 | yes |
| 4 | findContours_CCOMP | 1884x204 | 0.081 | 0.065 | 1.25 | yes |
| 4 | Laplacian_f32 | 1273x1800 | 0.880 | 0.882 | 1.00 | yes |
| 4 | findHomography_RANSAC | 112 pts | 1.408 | 1.414 | 1.00 | NO |
| 4 | pipeline_bg_map_f32 | 2000x500 | 2.472 | 2.580 | 0.96 | yes |
| 4 | pipeline_detect_board | 4096x3072 (real photo) | 29.789 | 26.378 | 1.13 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | ref ms | cool ms | x |
|---|---:|---:|---:|---:|
| py._detect_board | 85 | 6734.9 | 6430.9 | 1.05 |
| py._noise_sigma | 77 | 6649.7 | 6518.0 | 1.02 |
| py._locate_cracks | 77 | 5295.8 | 4900.6 | 1.08 |
| py._measure_roi | 372 | 4647.3 | 4636.0 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 4457.6 | 4202.3 | 1.06 |
| cv2.resize | 1065 | 4248.0 | 4168.1 | 1.02 |
| cv2.warpPerspective | 1052 | 2399.1 | 2545.6 | 0.94 |
| py._bg_map | 449 | 2072.9 | 1811.7 | 1.14 |
| py._edge_sigma | 77 | 1457.8 | 1484.6 | 0.98 |
| py.thinning_shim | 849 | 1113.5 | 1112.9 | 1.00 |
| cv2.GaussianBlur | 1196 | 925.4 | 917.8 | 1.01 |
| py._extract_roi | 372 | 922.0 | 903.1 | 1.02 |
| py._match_specimens | 77 | 828.2 | 830.1 | 1.00 |
| py._longest_path | 849 | 719.5 | 721.2 | 1.00 |
| cv2.connectedComponentsWithStats | 302 | 703.6 | 648.5 | 1.08 |
| cv2.medianBlur | 449 | 608.9 | 357.5 | 1.70 |
| cv2.filter2D | 77 | 555.5 | 555.1 | 1.00 |
| cv2.Sobel | 154 | 381.5 | 388.3 | 0.98 |
| cv2.Laplacian | 85 | 336.5 | 330.9 | 1.02 |
| cv2.cvtColor | 85 | 303.1 | 308.1 | 0.98 |
| py._fwhm | 442 | 256.7 | 258.6 | 0.99 |
| cv2.erode | 603 | 234.7 | 175.6 | 1.34 |
| cv2.magnitude | 77 | 195.4 | 194.8 | 1.00 |
| cv2.dilate | 449 | 169.2 | 149.9 | 1.13 |
| py._black_core | 221 | 166.4 | 167.4 | 0.99 |
| cv2.distanceTransform | 225 | 122.8 | 83.4 | 1.47 |
| cv2.polylines | 372 | 87.0 | 74.3 | 1.17 |
| py.gate.assess | 77 | 80.3 | 80.1 | 1.00 |
| cv2.morphologyEx | 77 | 52.4 | 52.1 | 1.01 |
| cv2.findHomography | 232 | 46.7 | 46.9 | 1.00 |
| py._smooth_resample | 222 | 28.8 | 28.5 | 1.01 |
| py._station_widths | 221 | 22.6 | 22.9 | 0.99 |
| cv2.fillConvexPoly | 77 | 17.8 | 17.6 | 1.01 |
| cv2.cornerSubPix | 77 | 17.8 | 17.7 | 1.01 |
| cv2.findContours | 221 | 17.0 | 15.4 | 1.11 |
| cv2.remap | 444 | 16.5 | 16.8 | 0.98 |
| cv2.copyMakeBorder | 849 | 11.3 | 11.2 | 1.01 |
| py._pose_obliquity | 77 | 9.3 | 9.2 | 1.01 |
| py._uncertainty | 220 | 8.9 | 8.8 | 1.01 |
| cv2.getStructuringElement | 449 | 5.1 | 4.7 | 1.07 |

Top 5 OpenCV calls by time in ref (per-call speedup ref/cool):

- cv2.aruco.CharucoDetector.detectBoard: 4458 ms -> 4202 ms over 85 calls, 1.06x
- cv2.resize: 4248 ms -> 4168 ms over 1065 calls, 1.02x
- cv2.warpPerspective: 2399 ms -> 2546 ms over 1052 calls, 0.94x
- cv2.GaussianBlur: 925 ms -> 918 ms over 1196 calls, 1.01x
- cv2.connectedComponentsWithStats: 704 ms -> 649 ms over 302 calls, 1.08x

Accuracy invariance: NOT bitwise identical: 2582 of 10183 leaves differ in 33 of 85 inputs; max |dw| of the reported crack width_mm = 1.550e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 3.520e-01 mm, over all numeric fields 7.080e-01.
- crack width differences over 220 cracks: max 1.550e-02 mm, P99 4.710e-03 mm, mean 5.300e-04 mm (157 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 220 cracks with a known width: ref mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); cool mean |e| 0.1219 mm (median 0.0618, P95 0.4874, bias -0.0055); paired mean(|e_cool| - |e_ref|) = -0.00005 mm [95% CI -0.00026, +0.00017]; cracks certified 109 vs 108
- canonical sha256: ref 2a3fa732f2ac5ea6..., cool 832d4ee68f57e79d...
- unrounded internal measurement scalars differing: 3931 (max |d| 4.357e+02)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): <call sequence length> 1/0, cv2.GaussianBlur 1115/1196, cv2.Rodrigues 70/77, cv2.connectedComponentsWithStats 241/302, cv2.contourArea 1/21, cv2.copyMakeBorder 230/849, cv2.dilate 371/448, cv2.distanceTransform 181/225, cv2.erode 21/603, cv2.findContours 180/221, cv2.findHomography 231/232, cv2.getStructuringElement 3/449, cv2.medianBlur 445/449, cv2.morphologyEx 54/77, cv2.polylines 8/372, cv2.remap 222/444, cv2.resize 967/1065, cv2.solvePnP 73/77, cv2.warpPerspective 549/1052, cv2.ximgproc.thinning 181/849, py._bg_map 448/449, py._black_core 221/221, py._edge_sigma 77/77, py._extract_roi 368/372, py._fwhm 442/442, py._locate_cracks 54/77, py._longest_path 163/849, py._match_specimens 14/77, py._measure_roi 223/371, py._pose_obliquity 43/77, py._smooth_resample 137/222, py._station_widths 221/221, py._uncertainty 220/220, py.gate.assess 1/76
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00470.jpg', 'cracks.C2.quality.dt_rel', '0x1.57886594af4f1p+2', '0x1.2a3886594af4fp+2', 0.7080000000000002]; ['synth/synth_00470.jpg', 'cracks.C2.quality.spread_rel', '0x1.6c56d5cfaacdap+2', '0x1.43d3c36113405p+2', 0.633]; ['synth/synth_00470.jpg', 'cracks.C2.quality.disagree_rel', '0x1.128f5c28f5c29p+2', '0x1.da3a29c779a6bp+1', 0.5851000000000002]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.d45a1cac08312p+2', '0x1.ec395810624ddp+2', 0.3730000000000002]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.d45f06f694467p+2', '0x1.ec37b4a2339c1p+2', 0.37260000000000026]
