### pip_t4  vs  cool_t4_bbdt   (speedup = pip_t4 time / cool_t4_bbdt time; >1 means cool_t4_bbdt is faster)

| stage | pip_t4 p50 ms | cool_t4_bbdt p50 ms | pip_t4 p95 ms | cool_t4_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 47.5 | 51.5 | 58.9 | 64.0 | 0.877 [0.845, 0.909] | 0.921 [0.805, 0.969] | 0.921 [0.855, 0.968] |
| detect | 29.9 | 28.2 | 37.5 | 36.0 | 1.076 [1.063, 1.089] | 1.060 [1.031, 1.112] | 1.041 [1.014, 1.063] |
| rectify | 48.3 | 41.3 | 62.5 | 56.1 | 1.155 [1.144, 1.167] | 1.169 [1.141, 1.198] | 1.113 [1.086, 1.203] |
| measure | 28.0 | 28.6 | 150.5 | 151.2 | 0.990 [0.986, 0.994] | 0.979 [0.954, 1.020] | 0.995 [0.961, 1.008] |
| other | 33.7 | 31.2 | 47.2 | 43.5 | 1.078 [1.066, 1.090] | 1.079 [1.028, 1.110] | 1.086 [1.060, 1.129] |
| analyze | 146.8 | 136.2 | 272.1 | 261.4 | 1.065 [1.058, 1.073] | 1.078 [1.056, 1.100] | 1.041 [1.028, 1.068] |
| e2e | 190.0 | 183.4 | 331.0 | 322.1 | 1.019 [1.008, 1.030] | 1.036 [0.990, 1.063] | 1.028 [0.992, 1.054] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t4 | cool_t4_bbdt | speedup pip_t4/cool_t4_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 3345 | 7678 | 0.436 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3751 | -1018 | -3.685 |
| analyze total (ms) | 7095 | 6661 | 1.065 |
| OpenCV share of analyze | 47.1 % | 115.3 % | |

Amdahl check: a 0.44x speedup of a 47 % OpenCV share predicts 0.621x end to end; even a 2x faster OpenCV would give only 1.31x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t4 ms | cool_t4_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 2738.2 | 3241.3 | 0.84 |
| py._locate_cracks | 40 | 2354.9 | 2500.1 | 0.94 |
| py._measure_roi | 197 | 2238.3 | 2334.3 | 0.96 |
| py._detect_board | 43 | 1368.7 | 3164.6 | 0.43 |
| py._bg_map | 237 | 986.6 | 925.6 | 1.07 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 942.9 | 2029.3 | 0.46 |
| cv2.resize | 560 | 738.3 | 2157.7 | 0.34 |
| py.thinning_shim | 426 | 551.4 | 550.4 | 1.00 |
| py._match_specimens | 40 | 442.5 | 442.4 | 1.00 |
| py._longest_path | 426 | 363.7 | 363.5 | 1.00 |
| py._edge_sigma | 40 | 335.2 | 728.1 | 0.46 |
| cv2.medianBlur | 237 | 320.2 | 185.1 | 1.73 |
| cv2.warpPerspective | 554 | 307.6 | 1278.2 | 0.24 |
| py._extract_roi | 197 | 224.9 | 450.0 | 0.50 |
| cv2.GaussianBlur | 634 | 224.7 | 465.6 | 0.48 |
| cv2.erode | 317 | 138.9 | 85.9 | 1.62 |
| py._fwhm | 240 | 138.5 | 138.7 | 1.00 |
| cv2.connectedComponentsWithStats | 160 | 134.4 | 313.5 | 0.43 |
| cv2.filter2D | 40 | 91.6 | 276.0 | 0.33 |
| cv2.dilate | 237 | 90.7 | 74.3 | 1.22 |
| py._black_core | 120 | 89.2 | 89.0 | 1.00 |
| cv2.Sobel | 80 | 75.0 | 192.6 | 0.39 |
| cv2.Laplacian | 43 | 58.0 | 168.1 | 0.34 |
| py.gate.assess | 40 | 43.9 | 44.4 | 0.99 |
| cv2.cvtColor | 43 | 43.1 | 152.7 | 0.28 |
| cv2.polylines | 197 | 38.9 | 62.9 | 0.62 |
| cv2.distanceTransform | 120 | 32.2 | 42.9 | 0.75 |
| cv2.magnitude | 40 | 27.5 | 97.3 | 0.28 |
| cv2.findHomography | 120 | 21.8 | 24.5 | 0.89 |
| cv2.morphologyEx | 40 | 17.9 | 27.0 | 0.66 |
| py._smooth_resample | 120 | 14.7 | 14.7 | 1.00 |
| py._station_widths | 120 | 11.9 | 11.8 | 1.01 |
| cv2.cornerSubPix | 40 | 9.7 | 9.8 | 0.99 |
| cv2.findContours | 120 | 7.9 | 7.3 | 1.09 |
| cv2.fillConvexPoly | 40 | 7.9 | 8.6 | 0.91 |
| cv2.remap | 240 | 6.7 | 7.6 | 0.88 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.00 |
| py._pose_obliquity | 40 | 4.3 | 4.7 | 0.91 |
| cv2.copyMakeBorder | 426 | 3.7 | 4.9 | 0.76 |
| cv2.solvePnP | 40 | 1.9 | 2.2 | 0.83 |

Top 5 OpenCV calls by time in pip_t4 (per-call speedup pip_t4/cool_t4_bbdt):

- cv2.aruco.CharucoDetector.detectBoard: 943 ms -> 2029 ms over 43 calls, 0.46x
- cv2.resize: 738 ms -> 2158 ms over 560 calls, 0.34x
- cv2.medianBlur: 320 ms -> 185 ms over 237 calls, 1.73x
- cv2.warpPerspective: 308 ms -> 1278 ms over 554 calls, 0.24x
- cv2.GaussianBlur: 225 ms -> 466 ms over 634 calls, 0.48x

Accuracy invariance: NOT bitwise identical: 1266 of 5472 leaves differ in 18 of 43 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 120 cracks: max 2.990e-02 mm, P99 1.861e-02 mm, mean 8.250e-04 mm (82 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 120 cracks with a known width: pip_t4 mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); cool_t4_bbdt mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool_t4_bbdt| - |e_pip_t4|) = +0.00052 mm [95% CI -0.00002, +0.00126]; cracks certified 59 vs 58
- canonical sha256: pip_t4 11b309ac9f1abacb..., cool_t4_bbdt 3cb998050814777d...
- unrounded internal measurement scalars differing: 1937 (max |d| 2.178e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 577/634, cv2.Rodrigues 37/40, cv2.connectedComponentsWithStats 112/160, cv2.copyMakeBorder 104/426, cv2.dilate 196/237, cv2.distanceTransform 81/120, cv2.erode 6/317, cv2.findContours 81/120, cv2.findHomography 120/120, cv2.magnitude 39/40, cv2.medianBlur 229/237, cv2.morphologyEx 30/40, cv2.polylines 1/197, cv2.remap 112/240, cv2.resize 505/560, cv2.solvePnP 37/40, cv2.warpPerspective 275/554, cv2.ximgproc.thinning 69/426, py._bg_map 236/237, py._black_core 112/120, py._edge_sigma 39/40, py._extract_roi 189/197, py._fwhm 224/240, py._locate_cracks 30/40, py._longest_path 62/426, py._match_specimens 7/40, py._measure_roi 112/197, py._pose_obliquity 20/40, py._smooth_resample 54/120, py._station_widths 112/120, py._uncertainty 120/120, py.gate.assess 1/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.42ab367a0f909p+3', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.ec37b4a2339c1p+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.ec395810624ddp+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.74d1b71758e22p+2', 1.5807000000000002]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
