### pip_t4_bbdt  vs  cool_t4_bbdt   (speedup = pip_t4_bbdt time / cool_t4_bbdt time; >1 means cool_t4_bbdt is faster)

| stage | pip_t4_bbdt p50 ms | cool_t4_bbdt p50 ms | pip_t4_bbdt p95 ms | cool_t4_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 47.1 | 51.5 | 61.7 | 64.0 | 0.933 [0.907, 0.959] | 0.914 [0.836, 0.966] | 0.964 [0.960, 0.974] |
| detect | 29.8 | 28.2 | 36.7 | 36.0 | 1.069 [1.058, 1.081] | 1.057 [1.028, 1.107] | 1.020 [1.015, 1.044] |
| rectify | 47.9 | 41.3 | 62.5 | 56.1 | 1.142 [1.132, 1.152] | 1.160 [1.121, 1.180] | 1.114 [1.065, 1.207] |
| measure | 27.9 | 28.6 | 150.3 | 151.2 | 0.991 [0.987, 0.995] | 0.976 [0.954, 1.017] | 0.994 [0.965, 1.010] |
| other | 32.6 | 31.2 | 46.0 | 43.5 | 1.057 [1.049, 1.065] | 1.046 [1.029, 1.078] | 1.056 [1.045, 1.079] |
| analyze | 143.8 | 136.2 | 272.1 | 261.4 | 1.057 [1.051, 1.063] | 1.056 [1.046, 1.090] | 1.041 [1.021, 1.046] |
| e2e | 190.4 | 183.4 | 330.7 | 322.1 | 1.026 [1.019, 1.034] | 1.038 [1.000, 1.062] | 1.027 [0.990, 1.030] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t4_bbdt | cool_t4_bbdt | speedup pip_t4_bbdt/cool_t4_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 3343 | 7678 | 0.435 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3696 | -1018 | -3.632 |
| analyze total (ms) | 7039 | 6661 | 1.057 |
| OpenCV share of analyze | 47.5 % | 115.3 % | |

Amdahl check: a 0.44x speedup of a 47 % OpenCV share predicts 0.619x end to end; even a 2x faster OpenCV would give only 1.31x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | pip_t4_bbdt fps | cool_t4_bbdt fps | x fps | pip_t4_bbdt e2e p50/p95 ms | cool_t4_bbdt e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x2 | 3.97 | 3.92 | 0.986 | 224/361 | 227/364 |
| 1x4 | 4.49 | 4.60 | 1.025 | 194/323 | 186/328 |
| 2x2 | 7.77 | 7.65 | 0.984 | 227/381 | 233/380 |
| 4x1 | 11.56 | 11.35 | 0.981 | 317/472 | 324/477 |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t4_bbdt ms | cool_t4_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 2742.0 | 3241.3 | 0.85 |
| py._locate_cracks | 40 | 2349.7 | 2500.1 | 0.94 |
| py._measure_roi | 197 | 2235.7 | 2334.3 | 0.96 |
| py._detect_board | 43 | 1366.4 | 3164.6 | 0.43 |
| py._bg_map | 237 | 984.6 | 925.6 | 1.06 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 940.8 | 2029.3 | 0.46 |
| cv2.resize | 560 | 737.5 | 2157.7 | 0.34 |
| py.thinning_shim | 426 | 552.7 | 550.4 | 1.00 |
| py._match_specimens | 40 | 443.5 | 442.4 | 1.00 |
| py._longest_path | 426 | 360.7 | 363.5 | 0.99 |
| py._edge_sigma | 40 | 335.3 | 728.1 | 0.46 |
| cv2.medianBlur | 237 | 319.7 | 185.1 | 1.73 |
| cv2.warpPerspective | 554 | 307.2 | 1278.2 | 0.24 |
| py._extract_roi | 197 | 225.3 | 450.0 | 0.50 |
| cv2.GaussianBlur | 634 | 225.0 | 465.6 | 0.48 |
| cv2.erode | 317 | 139.3 | 85.9 | 1.62 |
| py._fwhm | 240 | 138.0 | 138.7 | 0.99 |
| cv2.connectedComponentsWithStats | 160 | 135.4 | 313.5 | 0.43 |
| cv2.filter2D | 40 | 91.8 | 276.0 | 0.33 |
| cv2.dilate | 237 | 90.8 | 74.3 | 1.22 |
| py._black_core | 120 | 88.9 | 89.0 | 1.00 |
| cv2.Sobel | 80 | 75.0 | 192.6 | 0.39 |
| cv2.Laplacian | 43 | 58.1 | 168.1 | 0.35 |
| py.gate.assess | 40 | 43.9 | 44.4 | 0.99 |
| cv2.cvtColor | 43 | 42.6 | 152.7 | 0.28 |
| cv2.polylines | 197 | 38.9 | 62.9 | 0.62 |
| cv2.distanceTransform | 120 | 32.3 | 42.9 | 0.75 |
| cv2.magnitude | 40 | 27.5 | 97.3 | 0.28 |
| cv2.findHomography | 120 | 21.7 | 24.5 | 0.89 |
| cv2.morphologyEx | 40 | 17.9 | 27.0 | 0.66 |
| py._smooth_resample | 120 | 14.7 | 14.7 | 1.00 |
| py._station_widths | 120 | 11.9 | 11.8 | 1.01 |
| cv2.cornerSubPix | 40 | 9.7 | 9.8 | 0.99 |
| cv2.fillConvexPoly | 40 | 8.5 | 8.6 | 0.98 |
| cv2.findContours | 120 | 7.9 | 7.3 | 1.09 |
| cv2.remap | 240 | 6.6 | 7.6 | 0.87 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.00 |
| py._pose_obliquity | 40 | 4.3 | 4.7 | 0.91 |
| cv2.copyMakeBorder | 426 | 3.8 | 4.9 | 0.77 |
| cv2.solvePnP | 40 | 1.8 | 2.2 | 0.82 |

Top 5 OpenCV calls by time in pip_t4_bbdt (per-call speedup pip_t4_bbdt/cool_t4_bbdt):

- cv2.aruco.CharucoDetector.detectBoard: 941 ms -> 2029 ms over 43 calls, 0.46x
- cv2.resize: 737 ms -> 2158 ms over 560 calls, 0.34x
- cv2.medianBlur: 320 ms -> 185 ms over 237 calls, 1.73x
- cv2.warpPerspective: 307 ms -> 1278 ms over 554 calls, 0.24x
- cv2.GaussianBlur: 225 ms -> 466 ms over 634 calls, 0.48x

Accuracy invariance: NOT bitwise identical: 1266 of 5472 leaves differ in 18 of 43 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 120 cracks: max 2.990e-02 mm, P99 1.861e-02 mm, mean 8.250e-04 mm (82 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 120 cracks with a known width: pip_t4_bbdt mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); cool_t4_bbdt mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool_t4_bbdt| - |e_pip_t4_bbdt|) = +0.00052 mm [95% CI -0.00002, +0.00126]; cracks certified 59 vs 58
- canonical sha256: pip_t4_bbdt 11b309ac9f1abacb..., cool_t4_bbdt 3cb998050814777d...
- unrounded internal measurement scalars differing: 1937 (max |d| 2.178e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 577/634, cv2.Rodrigues 37/40, cv2.connectedComponentsWithStats 112/160, cv2.copyMakeBorder 104/426, cv2.dilate 196/237, cv2.distanceTransform 81/120, cv2.erode 6/317, cv2.findContours 81/120, cv2.findHomography 120/120, cv2.magnitude 39/40, cv2.medianBlur 229/237, cv2.morphologyEx 30/40, cv2.polylines 1/197, cv2.remap 112/240, cv2.resize 505/560, cv2.solvePnP 37/40, cv2.warpPerspective 275/554, cv2.ximgproc.thinning 69/426, py._bg_map 236/237, py._black_core 112/120, py._edge_sigma 39/40, py._extract_roi 189/197, py._fwhm 224/240, py._locate_cracks 30/40, py._longest_path 62/426, py._match_specimens 7/40, py._measure_roi 112/197, py._pose_obliquity 20/40, py._smooth_resample 54/120, py._station_widths 112/120, py._uncertainty 120/120, py.gate.assess 1/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.42ab367a0f909p+3', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.ec37b4a2339c1p+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.ec395810624ddp+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.74d1b71758e22p+2', 1.5807000000000002]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
