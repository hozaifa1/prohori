### cool_t1_bbdt  vs  pip_t1_bbdt   (speedup = cool_t1_bbdt time / pip_t1_bbdt time; >1 means pip_t1_bbdt is faster)

| stage | cool_t1_bbdt p50 ms | pip_t1_bbdt p50 ms | cool_t1_bbdt p95 ms | pip_t1_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 53.4 | 46.3 | 64.6 | 59.9 | 1.118 [1.086, 1.152] | 1.153 [1.075, 1.240] | 1.079 [1.031, 1.086] |
| detect | 72.5 | 74.1 | 89.8 | 90.0 | 0.980 [0.972, 0.986] | 0.978 [0.960, 0.990] | 0.998 [0.991, 1.011] |
| rectify | 77.3 | 80.7 | 90.5 | 93.6 | 0.953 [0.949, 0.958] | 0.958 [0.939, 0.972] | 0.966 [0.909, 0.978] |
| measure | 43.4 | 42.2 | 179.8 | 177.7 | 1.016 [1.012, 1.021] | 1.028 [0.984, 1.056] | 1.012 [0.987, 1.032] |
| other | 50.2 | 50.8 | 68.3 | 68.5 | 0.984 [0.978, 0.990] | 0.989 [0.969, 1.001] | 0.997 [0.951, 1.014] |
| analyze | 250.8 | 256.8 | 389.6 | 394.0 | 0.983 [0.980, 0.986] | 0.977 [0.971, 0.992] | 0.989 [0.982, 0.995] |
| e2e | 304.6 | 302.5 | 450.7 | 452.4 | 1.002 [0.998, 1.007] | 1.007 [0.984, 1.024] | 0.996 [0.991, 1.024] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | cool_t1_bbdt | pip_t1_bbdt | speedup cool_t1_bbdt/pip_t1_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7677 | 7828 | 0.981 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3712 | 3761 | 0.987 |
| analyze total (ms) | 11389 | 11589 | 0.983 |
| OpenCV share of analyze | 67.4 % | 67.5 % | |

Amdahl check: a 0.98x speedup of a 67 % OpenCV share predicts 0.987x end to end; even a 2x faster OpenCV would give only 1.51x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | cool_t1_bbdt ms | pip_t1_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3228.4 | 3233.5 | 1.00 |
| py._detect_board | 43 | 3178.4 | 3211.6 | 0.99 |
| py._locate_cracks | 40 | 2502.0 | 2661.7 | 0.94 |
| py._measure_roi | 197 | 2302.0 | 2284.7 | 1.01 |
| cv2.resize | 560 | 2158.2 | 2255.2 | 0.96 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2043.0 | 2029.9 | 1.01 |
| cv2.warpPerspective | 554 | 1276.5 | 1164.5 | 1.10 |
| py._bg_map | 237 | 923.7 | 1055.5 | 0.88 |
| py._edge_sigma | 40 | 728.7 | 692.5 | 1.05 |
| py.thinning_shim | 426 | 549.5 | 549.5 | 1.00 |
| cv2.GaussianBlur | 634 | 465.2 | 453.5 | 1.03 |
| py._extract_roi | 197 | 449.9 | 452.9 | 0.99 |
| py._match_specimens | 40 | 441.2 | 441.8 | 1.00 |
| py._longest_path | 426 | 358.5 | 362.7 | 0.99 |
| cv2.connectedComponentsWithStats | 160 | 325.0 | 312.2 | 1.04 |
| cv2.filter2D | 40 | 273.9 | 273.2 | 1.00 |
| cv2.Sobel | 80 | 194.0 | 181.7 | 1.07 |
| cv2.medianBlur | 237 | 185.2 | 319.7 | 0.58 |
| cv2.Laplacian | 43 | 166.6 | 163.1 | 1.02 |
| cv2.cvtColor | 43 | 155.1 | 156.4 | 0.99 |
| py._fwhm | 240 | 137.8 | 138.0 | 1.00 |
| cv2.magnitude | 40 | 97.2 | 96.9 | 1.00 |
| py._black_core | 120 | 88.7 | 88.7 | 1.00 |
| cv2.erode | 317 | 85.8 | 140.1 | 0.61 |
| cv2.dilate | 237 | 74.1 | 90.3 | 0.82 |
| py.gate.assess | 40 | 44.7 | 43.9 | 1.02 |
| cv2.distanceTransform | 120 | 42.9 | 64.1 | 0.67 |
| cv2.polylines | 197 | 38.4 | 36.9 | 1.04 |
| cv2.morphologyEx | 40 | 27.0 | 26.6 | 1.02 |
| cv2.findHomography | 120 | 24.7 | 21.7 | 1.14 |
| py._smooth_resample | 120 | 14.9 | 14.8 | 1.01 |
| py._station_widths | 120 | 11.8 | 11.8 | 1.00 |
| cv2.cornerSubPix | 40 | 9.8 | 9.7 | 1.01 |
| cv2.fillConvexPoly | 40 | 8.7 | 8.3 | 1.04 |
| cv2.remap | 240 | 7.5 | 7.1 | 1.05 |
| cv2.findContours | 120 | 7.3 | 7.4 | 0.98 |
| cv2.copyMakeBorder | 426 | 4.8 | 4.0 | 1.20 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.00 |
| py._pose_obliquity | 40 | 4.7 | 4.2 | 1.11 |
| cv2.solvePnP | 40 | 2.2 | 1.8 | 1.21 |

Top 5 OpenCV calls by time in cool_t1_bbdt (per-call speedup cool_t1_bbdt/pip_t1_bbdt):

- cv2.resize: 2158 ms -> 2255 ms over 560 calls, 0.96x
- cv2.aruco.CharucoDetector.detectBoard: 2043 ms -> 2030 ms over 43 calls, 1.01x
- cv2.warpPerspective: 1277 ms -> 1165 ms over 554 calls, 1.10x
- cv2.GaussianBlur: 465 ms -> 453 ms over 634 calls, 1.03x
- cv2.connectedComponentsWithStats: 325 ms -> 312 ms over 160 calls, 1.04x

Accuracy invariance: NOT bitwise identical: 1266 of 5472 leaves differ in 18 of 43 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 120 cracks: max 2.990e-02 mm, P99 1.861e-02 mm, mean 8.250e-04 mm (82 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified False -> True, risk_ratio 0.9474 -> 0.8219 vs threshold 0.8929 (level 0.05); reasons ['unstable_width'] -> []; width 0.9002 -> 0.9003 mm
- error vs printed ground truth over 120 cracks with a known width: cool_t1_bbdt mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); pip_t1_bbdt mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); paired mean(|e_pip_t1_bbdt| - |e_cool_t1_bbdt|) = -0.00052 mm [95% CI -0.00126, +0.00002]; cracks certified 58 vs 59
- canonical sha256: cool_t1_bbdt 3cb998050814777d..., pip_t1_bbdt 11b309ac9f1abacb...
- unrounded internal measurement scalars differing: 1937 (max |d| 2.178e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 577/634, cv2.Rodrigues 37/40, cv2.connectedComponentsWithStats 112/160, cv2.copyMakeBorder 104/426, cv2.dilate 196/237, cv2.distanceTransform 81/120, cv2.erode 6/317, cv2.findContours 81/120, cv2.findHomography 120/120, cv2.medianBlur 229/237, cv2.morphologyEx 30/40, cv2.polylines 1/197, cv2.remap 112/240, cv2.resize 505/560, cv2.solvePnP 37/40, cv2.warpPerspective 275/554, cv2.ximgproc.thinning 69/426, py._bg_map 236/237, py._black_core 112/120, py._edge_sigma 39/40, py._extract_roi 189/197, py._fwhm 224/240, py._locate_cracks 30/40, py._longest_path 62/426, py._match_specimens 7/40, py._measure_roi 112/197, py._pose_obliquity 20/40, py._smooth_resample 54/120, py._station_widths 112/120, py._uncertainty 120/120, py.gate.assess 1/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.42ab367a0f909p+3', '0x1.f9eecbfb15b57p+2', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.ec37b4a2339c1p+2', '0x1.723886594af4fp+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.ec395810624ddp+2', '0x1.723d70a3d70a4p+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.74d1b71758e22p+2', '0x1.0fa786c22680ap+2', 1.5807000000000002]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.4000000000000p+3', '0x1.3000000000000p+3', 0.5]
