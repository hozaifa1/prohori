### pip_t1  vs  cool_t1   (speedup = pip_t1 time / cool_t1 time; >1 means cool_t1 is faster)

| stage | pip_t1 p50 ms | cool_t1 p50 ms | pip_t1 p95 ms | cool_t1 p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 50.8 | 53.1 | 61.5 | 64.0 | 0.956 [0.951, 0.959] | 0.956 [0.946, 0.968] | 0.961 [0.959, 0.967] |
| detect | 72.4 | 72.8 | 88.8 | 90.4 | 1.001 [0.996, 1.008] | 0.995 [0.989, 1.024] | 0.982 [0.971, 0.996] |
| rectify | 79.3 | 76.6 | 93.5 | 91.5 | 1.036 [1.032, 1.041] | 1.035 [1.022, 1.049] | 1.022 [1.011, 1.093] |
| measure | 42.5 | 43.4 | 179.4 | 180.1 | 0.991 [0.986, 0.995] | 0.979 [0.951, 1.018] | 0.997 [0.976, 1.017] |
| other | 50.8 | 49.6 | 69.7 | 67.8 | 1.027 [1.023, 1.031] | 1.022 [1.009, 1.045] | 1.028 [1.009, 1.041] |
| analyze | 254.1 | 251.7 | 395.1 | 390.1 | 1.012 [1.010, 1.015] | 1.010 [1.001, 1.023] | 1.013 [1.001, 1.018] |
| e2e | 304.3 | 305.2 | 453.9 | 450.9 | 1.003 [1.001, 1.006] | 0.997 [0.990, 1.012] | 1.007 [0.998, 1.009] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t1 | cool_t1 | speedup pip_t1/cool_t1 |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7844 | 7678 | 1.022 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3681 | 3706 | 0.993 |
| analyze total (ms) | 11526 | 11384 | 1.012 |
| OpenCV share of analyze | 68.1 % | 67.4 % | |

Amdahl check: a 1.02x speedup of a 68 % OpenCV share predicts 1.015x end to end; even a 2x faster OpenCV would give only 1.52x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t1 ms | cool_t1 ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3257.4 | 3208.9 | 1.02 |
| py._detect_board | 43 | 3184.3 | 3174.6 | 1.00 |
| py._locate_cracks | 40 | 2692.6 | 2501.4 | 1.08 |
| py._measure_roi | 197 | 2339.9 | 2305.8 | 1.01 |
| cv2.resize | 560 | 2181.8 | 2155.8 | 1.01 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2033.8 | 2040.3 | 1.00 |
| cv2.warpPerspective | 554 | 1167.8 | 1276.4 | 0.91 |
| py._bg_map | 237 | 1058.3 | 922.1 | 1.15 |
| py._edge_sigma | 40 | 695.9 | 726.2 | 0.96 |
| py.thinning_shim | 426 | 551.0 | 547.7 | 1.01 |
| py._extract_roi | 197 | 454.9 | 450.2 | 1.01 |
| cv2.GaussianBlur | 634 | 453.0 | 467.9 | 0.97 |
| py._match_specimens | 40 | 440.4 | 442.7 | 0.99 |
| py._longest_path | 426 | 364.0 | 357.1 | 1.02 |
| cv2.connectedComponentsWithStats | 160 | 361.2 | 331.5 | 1.09 |
| cv2.medianBlur | 237 | 319.9 | 185.2 | 1.73 |
| cv2.filter2D | 40 | 274.0 | 276.1 | 0.99 |
| cv2.Sobel | 80 | 182.1 | 192.9 | 0.94 |
| cv2.Laplacian | 43 | 164.3 | 164.1 | 1.00 |
| cv2.cvtColor | 43 | 159.4 | 152.4 | 1.05 |
| cv2.erode | 317 | 140.1 | 85.9 | 1.63 |
| py._fwhm | 240 | 139.0 | 138.9 | 1.00 |
| cv2.magnitude | 40 | 96.8 | 97.1 | 1.00 |
| cv2.dilate | 237 | 90.6 | 74.1 | 1.22 |
| py._black_core | 120 | 89.3 | 89.2 | 1.00 |
| cv2.polylines | 197 | 64.9 | 38.5 | 1.68 |
| cv2.distanceTransform | 120 | 64.2 | 42.8 | 1.50 |
| py.gate.assess | 40 | 43.9 | 45.8 | 0.96 |
| cv2.morphologyEx | 40 | 26.5 | 26.9 | 0.99 |
| cv2.findHomography | 120 | 21.9 | 24.7 | 0.89 |
| py._smooth_resample | 120 | 14.8 | 14.7 | 1.01 |
| py._station_widths | 120 | 12.0 | 11.8 | 1.01 |
| cv2.cornerSubPix | 40 | 9.7 | 9.8 | 1.00 |
| cv2.fillConvexPoly | 40 | 8.1 | 8.8 | 0.92 |
| cv2.findContours | 120 | 7.4 | 7.3 | 1.02 |
| cv2.remap | 240 | 7.3 | 7.6 | 0.96 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.00 |
| py._pose_obliquity | 40 | 4.3 | 4.6 | 0.92 |
| cv2.copyMakeBorder | 426 | 4.0 | 4.8 | 0.84 |
| cv2.solvePnP | 40 | 1.8 | 2.2 | 0.83 |

Top 5 OpenCV calls by time in pip_t1 (per-call speedup pip_t1/cool_t1):

- cv2.resize: 2182 ms -> 2156 ms over 560 calls, 1.01x
- cv2.aruco.CharucoDetector.detectBoard: 2034 ms -> 2040 ms over 43 calls, 1.00x
- cv2.warpPerspective: 1168 ms -> 1276 ms over 554 calls, 0.91x
- cv2.GaussianBlur: 453 ms -> 468 ms over 634 calls, 0.97x
- cv2.connectedComponentsWithStats: 361 ms -> 332 ms over 160 calls, 1.09x

Accuracy invariance: NOT bitwise identical: 1266 of 5472 leaves differ in 18 of 43 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 120 cracks: max 2.990e-02 mm, P99 1.861e-02 mm, mean 8.250e-04 mm (82 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 120 cracks with a known width: pip_t1 mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); cool_t1 mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool_t1| - |e_pip_t1|) = +0.00052 mm [95% CI -0.00002, +0.00126]; cracks certified 59 vs 58
- canonical sha256: pip_t1 11b309ac9f1abacb..., cool_t1 3cb998050814777d...
- unrounded internal measurement scalars differing: 1937 (max |d| 2.178e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 577/634, cv2.Rodrigues 37/40, cv2.connectedComponentsWithStats 112/160, cv2.copyMakeBorder 104/426, cv2.dilate 196/237, cv2.distanceTransform 81/120, cv2.erode 6/317, cv2.findContours 81/120, cv2.findHomography 120/120, cv2.medianBlur 229/237, cv2.morphologyEx 30/40, cv2.polylines 1/197, cv2.remap 112/240, cv2.resize 505/560, cv2.solvePnP 37/40, cv2.warpPerspective 275/554, cv2.ximgproc.thinning 69/426, py._bg_map 236/237, py._black_core 112/120, py._edge_sigma 39/40, py._extract_roi 189/197, py._fwhm 224/240, py._locate_cracks 30/40, py._longest_path 62/426, py._match_specimens 7/40, py._measure_roi 112/197, py._pose_obliquity 20/40, py._smooth_resample 54/120, py._station_widths 112/120, py._uncertainty 120/120, py.gate.assess 1/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.42ab367a0f909p+3', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.ec37b4a2339c1p+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.ec395810624ddp+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.74d1b71758e22p+2', 1.5807000000000002]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
