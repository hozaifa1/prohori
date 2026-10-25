### cool_t1  vs  cool_t1_bbdt   (speedup = cool_t1 time / cool_t1_bbdt time; >1 means cool_t1_bbdt is faster)

| stage | cool_t1 p50 ms | cool_t1_bbdt p50 ms | cool_t1 p95 ms | cool_t1_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 53.1 | 53.4 | 64.0 | 64.6 | 0.993 [0.992, 0.994] | 0.996 [0.986, 0.998] | 0.991 [0.987, 0.997] |
| detect | 72.8 | 72.5 | 90.4 | 89.8 | 1.001 [0.999, 1.002] | 1.004 [0.997, 1.006] | 1.007 [0.999, 1.009] |
| rectify | 76.6 | 77.3 | 91.5 | 90.5 | 0.997 [0.994, 0.999] | 0.991 [0.983, 1.008] | 1.011 [0.985, 1.029] |
| measure | 43.4 | 43.4 | 180.1 | 179.8 | 1.002 [1.001, 1.003] | 1.000 [0.992, 1.009] | 1.001 [1.000, 1.004] |
| other | 49.6 | 50.2 | 67.8 | 68.3 | 0.998 [0.993, 1.004] | 0.988 [0.983, 1.023] | 0.993 [0.965, 1.016] |
| analyze | 251.7 | 250.8 | 390.1 | 389.6 | 1.000 [0.998, 1.001] | 1.004 [0.993, 1.008] | 1.001 [0.995, 1.007] |
| e2e | 305.2 | 304.6 | 450.9 | 450.7 | 0.998 [0.997, 1.000] | 1.002 [0.990, 1.006] | 1.000 [0.995, 1.001] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | cool_t1 | cool_t1_bbdt | speedup cool_t1/cool_t1_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7678 | 7677 | 1.000 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3706 | 3712 | 0.998 |
| analyze total (ms) | 11384 | 11389 | 1.000 |
| OpenCV share of analyze | 67.4 % | 67.4 % | |

Amdahl check: a 1.00x speedup of a 67 % OpenCV share predicts 1.000x end to end; even a 2x faster OpenCV would give only 1.51x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | cool_t1 ms | cool_t1_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3208.9 | 3228.4 | 0.99 |
| py._detect_board | 43 | 3174.6 | 3178.4 | 1.00 |
| py._locate_cracks | 40 | 2501.4 | 2502.0 | 1.00 |
| py._measure_roi | 197 | 2305.8 | 2302.0 | 1.00 |
| cv2.resize | 560 | 2155.8 | 2158.2 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2040.3 | 2043.0 | 1.00 |
| cv2.warpPerspective | 554 | 1276.4 | 1276.5 | 1.00 |
| py._bg_map | 237 | 922.1 | 923.7 | 1.00 |
| py._edge_sigma | 40 | 726.2 | 728.7 | 1.00 |
| py.thinning_shim | 426 | 547.7 | 549.5 | 1.00 |
| cv2.GaussianBlur | 634 | 467.9 | 465.2 | 1.01 |
| py._extract_roi | 197 | 450.2 | 449.9 | 1.00 |
| py._match_specimens | 40 | 442.7 | 441.2 | 1.00 |
| py._longest_path | 426 | 357.1 | 358.5 | 1.00 |
| cv2.connectedComponentsWithStats | 160 | 331.5 | 325.0 | 1.02 |
| cv2.filter2D | 40 | 276.1 | 273.9 | 1.01 |
| cv2.Sobel | 80 | 192.9 | 194.0 | 0.99 |
| cv2.medianBlur | 237 | 185.2 | 185.2 | 1.00 |
| cv2.Laplacian | 43 | 164.1 | 166.6 | 0.98 |
| cv2.cvtColor | 43 | 152.4 | 155.1 | 0.98 |
| py._fwhm | 240 | 138.9 | 137.8 | 1.01 |
| cv2.magnitude | 40 | 97.1 | 97.2 | 1.00 |
| py._black_core | 120 | 89.2 | 88.7 | 1.01 |
| cv2.erode | 317 | 85.9 | 85.8 | 1.00 |
| cv2.dilate | 237 | 74.1 | 74.1 | 1.00 |
| py.gate.assess | 40 | 45.8 | 44.7 | 1.02 |
| cv2.distanceTransform | 120 | 42.8 | 42.9 | 1.00 |
| cv2.polylines | 197 | 38.5 | 38.4 | 1.00 |
| cv2.morphologyEx | 40 | 26.9 | 27.0 | 1.00 |
| cv2.findHomography | 120 | 24.7 | 24.7 | 1.00 |
| py._smooth_resample | 120 | 14.7 | 14.9 | 0.99 |
| py._station_widths | 120 | 11.8 | 11.8 | 1.00 |
| cv2.cornerSubPix | 40 | 9.8 | 9.8 | 1.00 |
| cv2.fillConvexPoly | 40 | 8.8 | 8.7 | 1.01 |
| cv2.remap | 240 | 7.6 | 7.5 | 1.01 |
| cv2.findContours | 120 | 7.3 | 7.3 | 1.00 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.01 |
| cv2.copyMakeBorder | 426 | 4.8 | 4.8 | 0.99 |
| py._pose_obliquity | 40 | 4.6 | 4.7 | 0.99 |
| cv2.rectangle | 40 | 2.3 | 2.0 | 1.12 |

Top 5 OpenCV calls by time in cool_t1 (per-call speedup cool_t1/cool_t1_bbdt):

- cv2.resize: 2156 ms -> 2158 ms over 560 calls, 1.00x
- cv2.aruco.CharucoDetector.detectBoard: 2040 ms -> 2043 ms over 43 calls, 1.00x
- cv2.warpPerspective: 1276 ms -> 1277 ms over 554 calls, 1.00x
- cv2.GaussianBlur: 468 ms -> 465 ms over 634 calls, 1.01x
- cv2.connectedComponentsWithStats: 332 ms -> 325 ms over 160 calls, 1.02x

Accuracy invariance: BITWISE IDENTICAL: all 5472 numeric/string leaves of 43 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 120 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 120 cracks with a known width: cool_t1 mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); cool_t1_bbdt mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool_t1_bbdt| - |e_cool_t1|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 58 vs 58
- canonical sha256: cool_t1 3cb998050814777d..., cool_t1_bbdt 3cb998050814777d...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- every OpenCV function output in the pipeline is byte-identical across the two builds
