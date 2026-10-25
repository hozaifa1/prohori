### pip_t1  vs  pip_t1_bbdt   (speedup = pip_t1 time / pip_t1_bbdt time; >1 means pip_t1_bbdt is faster)

| stage | pip_t1 p50 ms | pip_t1_bbdt p50 ms | pip_t1 p95 ms | pip_t1_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 50.8 | 46.3 | 61.5 | 59.9 | 1.061 [1.030, 1.094] | 1.097 [1.018, 1.186] | 1.028 [0.990, 1.034] |
| detect | 72.4 | 74.1 | 88.8 | 90.0 | 0.982 [0.980, 0.984] | 0.977 [0.972, 0.986] | 0.986 [0.979, 0.993] |
| rectify | 79.3 | 80.7 | 93.5 | 93.6 | 0.984 [0.980, 0.989] | 0.983 [0.970, 1.007] | 0.999 [0.972, 1.002] |
| measure | 42.5 | 42.2 | 179.4 | 177.7 | 1.009 [1.007, 1.011] | 1.007 [0.997, 1.012] | 1.010 [1.004, 1.015] |
| other | 50.8 | 50.8 | 69.7 | 68.5 | 1.009 [1.003, 1.014] | 0.999 [0.986, 1.035] | 1.018 [0.976, 1.021] |
| analyze | 254.1 | 256.8 | 395.1 | 394.0 | 0.995 [0.992, 0.997] | 0.990 [0.983, 1.002] | 1.003 [0.993, 1.004] |
| e2e | 304.3 | 302.5 | 453.9 | 452.4 | 1.004 [0.999, 1.009] | 1.006 [0.981, 1.023] | 1.003 [0.995, 1.025] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t1 | pip_t1_bbdt | speedup pip_t1/pip_t1_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7844 | 7828 | 1.002 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3681 | 3761 | 0.979 |
| analyze total (ms) | 11526 | 11589 | 0.995 |
| OpenCV share of analyze | 68.1 % | 67.5 % | |

Amdahl check: a 1.00x speedup of a 68 % OpenCV share predicts 1.001x end to end; even a 2x faster OpenCV would give only 1.52x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t1 ms | pip_t1_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3257.4 | 3233.5 | 1.01 |
| py._detect_board | 43 | 3184.3 | 3211.6 | 0.99 |
| py._locate_cracks | 40 | 2692.6 | 2661.7 | 1.01 |
| py._measure_roi | 197 | 2339.9 | 2284.7 | 1.02 |
| cv2.resize | 560 | 2181.8 | 2255.2 | 0.97 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2033.8 | 2029.9 | 1.00 |
| cv2.warpPerspective | 554 | 1167.8 | 1164.5 | 1.00 |
| py._bg_map | 237 | 1058.3 | 1055.5 | 1.00 |
| py._edge_sigma | 40 | 695.9 | 692.5 | 1.01 |
| py.thinning_shim | 426 | 551.0 | 549.5 | 1.00 |
| py._extract_roi | 197 | 454.9 | 452.9 | 1.00 |
| cv2.GaussianBlur | 634 | 453.0 | 453.5 | 1.00 |
| py._match_specimens | 40 | 440.4 | 441.8 | 1.00 |
| py._longest_path | 426 | 364.0 | 362.7 | 1.00 |
| cv2.connectedComponentsWithStats | 160 | 361.2 | 312.2 | 1.16 |
| cv2.medianBlur | 237 | 319.9 | 319.7 | 1.00 |
| cv2.filter2D | 40 | 274.0 | 273.2 | 1.00 |
| cv2.Sobel | 80 | 182.1 | 181.7 | 1.00 |
| cv2.Laplacian | 43 | 164.3 | 163.1 | 1.01 |
| cv2.cvtColor | 43 | 159.4 | 156.4 | 1.02 |
| cv2.erode | 317 | 140.1 | 140.1 | 1.00 |
| py._fwhm | 240 | 139.0 | 138.0 | 1.01 |
| cv2.magnitude | 40 | 96.8 | 96.9 | 1.00 |
| cv2.dilate | 237 | 90.6 | 90.3 | 1.00 |
| py._black_core | 120 | 89.3 | 88.7 | 1.01 |
| cv2.polylines | 197 | 64.9 | 36.9 | 1.76 |
| cv2.distanceTransform | 120 | 64.2 | 64.1 | 1.00 |
| py.gate.assess | 40 | 43.9 | 43.9 | 1.00 |
| cv2.morphologyEx | 40 | 26.5 | 26.6 | 1.00 |
| cv2.findHomography | 120 | 21.9 | 21.7 | 1.01 |
| py._smooth_resample | 120 | 14.8 | 14.8 | 1.00 |
| py._station_widths | 120 | 12.0 | 11.8 | 1.02 |
| cv2.cornerSubPix | 40 | 9.7 | 9.7 | 1.01 |
| cv2.fillConvexPoly | 40 | 8.1 | 8.3 | 0.97 |
| cv2.findContours | 120 | 7.4 | 7.4 | 1.00 |
| cv2.remap | 240 | 7.3 | 7.1 | 1.02 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.01 |
| py._pose_obliquity | 40 | 4.3 | 4.2 | 1.01 |
| cv2.copyMakeBorder | 426 | 4.0 | 4.0 | 1.00 |
| cv2.solvePnP | 40 | 1.8 | 1.8 | 1.00 |

Top 5 OpenCV calls by time in pip_t1 (per-call speedup pip_t1/pip_t1_bbdt):

- cv2.resize: 2182 ms -> 2255 ms over 560 calls, 0.97x
- cv2.aruco.CharucoDetector.detectBoard: 2034 ms -> 2030 ms over 43 calls, 1.00x
- cv2.warpPerspective: 1168 ms -> 1165 ms over 554 calls, 1.00x
- cv2.GaussianBlur: 453 ms -> 453 ms over 634 calls, 1.00x
- cv2.connectedComponentsWithStats: 361 ms -> 312 ms over 160 calls, 1.16x

Accuracy invariance: BITWISE IDENTICAL: all 5471 numeric/string leaves of 43 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 120 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 120 cracks with a known width: pip_t1 mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); pip_t1_bbdt mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); paired mean(|e_pip_t1_bbdt| - |e_pip_t1|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 59 vs 59
- canonical sha256: pip_t1 11b309ac9f1abacb..., pip_t1_bbdt 11b309ac9f1abacb...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- every OpenCV function output in the pipeline is byte-identical across the two builds
