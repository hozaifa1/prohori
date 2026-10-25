### pip  vs  cool   (speedup = pip time / cool time; >1 means cool is faster)

| stage | pip p50 ms | cool p50 ms | pip p95 ms | cool p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 46.8 | 52.3 | 59.7 | 63.6 | 0.919 [0.892, 0.945] | 0.895 [0.843, 0.964] | 0.940 [0.935, 0.984] |
| detect | 73.9 | 75.1 | 90.6 | 92.4 | 0.993 [0.988, 1.000] | 0.984 [0.979, 1.008] | 0.980 [0.973, 0.982] |
| rectify | 82.8 | 79.0 | 95.3 | 94.2 | 1.046 [1.042, 1.050] | 1.048 [1.037, 1.057] | 1.012 [1.008, 1.100] |
| measure | 42.9 | 43.9 | 183.6 | 184.3 | 0.992 [0.987, 0.996] | 0.977 [0.952, 1.029] | 0.996 [0.978, 1.019] |
| other | 53.6 | 51.7 | 71.9 | 71.2 | 1.018 [1.011, 1.025] | 1.038 [0.981, 1.041] | 1.011 [1.009, 1.035] |
| analyze | 259.3 | 258.9 | 404.6 | 400.6 | 1.012 [1.009, 1.014] | 1.002 [0.997, 1.020] | 1.010 [1.006, 1.018] |
| e2e | 307.7 | 311.7 | 462.9 | 460.9 | 0.997 [0.993, 1.001] | 0.987 [0.972, 1.010] | 1.004 [0.990, 1.005] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip | cool | speedup pip/cool |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 2847 | 2812 | 1.012 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 1322 | 1318 | 1.003 |
| analyze total (ms) | 4169 | 4131 | 1.009 |
| OpenCV share of analyze | 68.3 % | 68.1 % | |

Amdahl check: a 1.01x speedup of a 68 % OpenCV share predicts 1.008x end to end; even a 2x faster OpenCV would give only 1.52x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | pip fps | cool fps | x fps | pip e2e p50/p95 ms | cool e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.04 | 3.02 | 0.994 | 316/454 | 319/455 |
| 2x1 | 5.80 | 5.76 | 0.992 | 320/469 | 326/467 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | pip ms | cool ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 59.484 | 62.184 | 0.96 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.757 | 3.844 | 0.98 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.586 | 0.600 | 0.98 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 17.057 | 17.052 | 1.00 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.867 | 0.874 | 0.99 | NO |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.791 | 8.629 | 0.56 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.661 | 2.104 | 1.26 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.947 | 6.107 | 0.97 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.432 | 1.115 | 1.28 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.827 | 0.503 | 1.64 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.248 | 0.172 | 1.44 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.492 | 2.633 | 0.95 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.781 | 5.877 | 0.98 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.072 | 0.073 | 0.98 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.920 | 1.944 | 0.99 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.473 | 3.237 | 2.31 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.652 | 0.661 | 0.99 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.949 | 6.305 | 1.10 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.811 | 2.778 | 1.01 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.351 | 1.450 | 1.62 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.041 | 0.036 | 1.14 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.075 | 0.063 | 1.20 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 3.021 | 3.022 | 1.00 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.312 | 1.413 | 0.93 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.694 | 3.500 | 0.77 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 74.793 | 75.051 | 1.00 | yes |
| 2 | imdecode_jpeg_12MP | 4096x3072 | 59.473 | 61.855 | 0.96 | yes |
| 2 | cvtColor_BGR2GRAY | 4096x3072x3 | 1.928 | 2.011 | 0.96 | yes |
| 2 | resize_AREA_grey_x0.5 | 4096x3072 | 0.579 | 0.294 | 1.97 | yes |
| 2 | resize_AREA_grey_x0.3 | 4096x3072 | 9.709 | 9.676 | 1.00 | yes |
| 2 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.524 | 0.513 | 1.02 | NO |
| 2 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 2.403 | 4.442 | 0.54 | NO |
| 2 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 1.350 | 1.099 | 1.23 | NO |
| 2 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 2.982 | 3.057 | 0.98 | yes |
| 2 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.820 | 0.706 | 1.16 | yes |
| 2 | erode_7x7_u8 | 1273x1800 | 0.829 | 0.512 | 1.62 | yes |
| 2 | erode_5x5_u8_ROI | 2000x500 | 0.245 | 0.167 | 1.46 | yes |
| 2 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 1.233 | 1.319 | 0.93 | yes |
| 2 | GaussianBlur_f32_sigma4 | 2000x500 | 5.915 | 5.807 | 1.02 | yes |
| 2 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.075 | 0.95 | yes |
| 2 | dilate_f32_rect | 2000x500 k=17 | 1.927 | 1.952 | 0.99 | yes |
| 2 | medianBlur_u8_k15 | 318x450 | 7.483 | 2.625 | 2.85 | yes |
| 2 | morphologyEx_close_ellipse | 1273x1800 | 0.636 | 0.648 | 0.98 | yes |
| 2 | connectedComponentsWithStats | 1273x1800 | - | - | - | FAILED: A: ok; B: child rc=-6 (crash): Fatal glibc error: malloc.c:2599 (sysmalloc): assertion failed: (old_top == ini |
| 2 | ximgproc_thinning | 1884x204 | 2.770 | 2.767 | 1.00 | yes |
| 2 | distanceTransform_L2_precise | 1884x204 | 1.231 | 0.812 | 1.52 | yes |
| 2 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.026 | 0.024 | 1.07 | yes |
| 2 | findContours_CCOMP | 1884x204 | 0.082 | 0.068 | 1.20 | yes |
| 2 | Laplacian_f32 | 1273x1800 | 1.719 | 1.736 | 0.99 | yes |
| 2 | findHomography_RANSAC | 112 pts | 1.310 | 1.416 | 0.93 | NO |
| 2 | pipeline_bg_map_f32 | 2000x500 | 2.571 | 3.314 | 0.78 | yes |
| 2 | pipeline_detect_board | 4096x3072 (real photo) | 39.632 | 43.573 | 0.91 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip ms | cool ms | x |
|---|---:|---:|---:|---:|
| py._detect_board | 15 | 1184.9 | 1184.4 | 1.00 |
| py._noise_sigma | 14 | 1122.1 | 1112.3 | 1.01 |
| py._locate_cracks | 14 | 975.5 | 913.4 | 1.07 |
| cv2.resize | 194 | 808.1 | 806.4 | 1.00 |
| py._measure_roi | 68 | 801.9 | 802.7 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 15 | 764.1 | 764.3 | 1.00 |
| cv2.warpPerspective | 192 | 411.7 | 448.5 | 0.92 |
| py._bg_map | 82 | 372.4 | 327.2 | 1.14 |
| py._edge_sigma | 14 | 240.1 | 251.4 | 0.95 |
| py.thinning_shim | 160 | 204.5 | 204.7 | 1.00 |
| py._extract_roi | 68 | 160.9 | 160.6 | 1.00 |
| cv2.GaussianBlur | 218 | 160.4 | 167.2 | 0.96 |
| py._match_specimens | 14 | 157.0 | 156.1 | 1.01 |
| py._longest_path | 160 | 130.7 | 130.7 | 1.00 |
| cv2.connectedComponentsWithStats | 54 | 128.2 | 117.5 | 1.09 |
| cv2.medianBlur | 82 | 111.3 | 66.4 | 1.68 |
| cv2.filter2D | 14 | 101.0 | 102.5 | 0.99 |
| cv2.Sobel | 28 | 65.2 | 68.3 | 0.95 |
| cv2.Laplacian | 15 | 60.4 | 62.8 | 0.96 |
| cv2.cvtColor | 15 | 55.3 | 55.7 | 0.99 |
| cv2.erode | 110 | 48.9 | 31.1 | 1.57 |
| py._fwhm | 80 | 48.7 | 48.2 | 1.01 |
| cv2.magnitude | 14 | 32.7 | 32.9 | 1.00 |
| cv2.dilate | 82 | 31.6 | 26.4 | 1.20 |
| py._black_core | 40 | 30.9 | 30.6 | 1.01 |
| cv2.distanceTransform | 40 | 22.0 | 14.8 | 1.49 |
| py.gate.assess | 14 | 16.0 | 16.2 | 0.98 |
| cv2.polylines | 68 | 13.5 | 13.4 | 1.01 |
| cv2.morphologyEx | 14 | 9.6 | 9.8 | 0.98 |
| cv2.findHomography | 42 | 7.6 | 8.6 | 0.88 |
| py._smooth_resample | 40 | 5.1 | 5.0 | 1.01 |
| py._station_widths | 40 | 4.0 | 4.1 | 0.99 |
| cv2.cornerSubPix | 14 | 3.5 | 3.5 | 0.98 |
| cv2.fillConvexPoly | 14 | 2.9 | 2.9 | 0.99 |
| cv2.remap | 80 | 2.5 | 2.7 | 0.94 |
| cv2.findContours | 40 | 2.5 | 2.5 | 1.02 |
| py._uncertainty | 40 | 1.6 | 1.5 | 1.02 |
| cv2.copyMakeBorder | 160 | 1.6 | 1.8 | 0.86 |
| py._pose_obliquity | 14 | 1.5 | 1.6 | 0.92 |
| cv2.solvePnP | 14 | 0.6 | 0.8 | 0.82 |

Top 5 OpenCV calls by time in pip (per-call speedup pip/cool):

- cv2.resize: 808 ms -> 806 ms over 194 calls, 1.00x
- cv2.aruco.CharucoDetector.detectBoard: 764 ms -> 764 ms over 15 calls, 1.00x
- cv2.warpPerspective: 412 ms -> 448 ms over 192 calls, 0.92x
- cv2.GaussianBlur: 160 ms -> 167 ms over 218 calls, 0.96x
- cv2.connectedComponentsWithStats: 128 ms -> 118 ms over 54 calls, 1.09x

Accuracy invariance: NOT bitwise identical: 1266 of 5472 leaves differ in 18 of 43 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 120 cracks: max 2.990e-02 mm, P99 1.861e-02 mm, mean 8.250e-04 mm (82 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 120 cracks with a known width: pip mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); cool mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool| - |e_pip|) = +0.00052 mm [95% CI -0.00002, +0.00126]; cracks certified 59 vs 58
- canonical sha256: pip 11b309ac9f1abacb..., cool 3cb998050814777d...
- unrounded internal measurement scalars differing: 683 (max |d| 5.285e-01)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 204/218, cv2.Rodrigues 14/14, cv2.connectedComponentsWithStats 37/54, cv2.copyMakeBorder 37/160, cv2.dilate 68/82, cv2.distanceTransform 26/40, cv2.findContours 26/40, cv2.findHomography 42/42, cv2.medianBlur 82/82, cv2.morphologyEx 11/14, cv2.polylines 1/68, cv2.remap 40/80, cv2.resize 178/194, cv2.solvePnP 14/14, cv2.warpPerspective 96/192, cv2.ximgproc.thinning 27/160, py._bg_map 82/82, py._black_core 40/40, py._edge_sigma 14/14, py._extract_roi 68/68, py._fwhm 80/80, py._locate_cracks 11/14, py._longest_path 24/160, py._match_specimens 3/14, py._measure_roi 40/68, py._pose_obliquity 9/14, py._smooth_resample 21/40, py._station_widths 40/40, py._uncertainty 40/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.42ab367a0f909p+3', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.ec37b4a2339c1p+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.ec395810624ddp+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.74d1b71758e22p+2', 1.5807000000000002]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
