### pip_t4  vs  pip_t4_bbdt   (speedup = pip_t4 time / pip_t4_bbdt time; >1 means pip_t4_bbdt is faster)

| stage | pip_t4 p50 ms | pip_t4_bbdt p50 ms | pip_t4 p95 ms | pip_t4_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 47.5 | 47.1 | 58.9 | 61.7 | 0.939 [0.896, 0.985] | 1.008 [0.879, 1.070] | 0.955 [0.878, 1.003] |
| detect | 29.9 | 29.8 | 37.5 | 36.7 | 1.007 [1.003, 1.011] | 1.003 [0.997, 1.017] | 1.020 [0.997, 1.035] |
| rectify | 48.3 | 47.9 | 62.5 | 62.5 | 1.012 [1.009, 1.015] | 1.008 [1.002, 1.033] | 0.999 [0.997, 1.043] |
| measure | 28.0 | 27.9 | 150.5 | 150.3 | 0.999 [0.998, 1.001] | 1.004 [0.993, 1.008] | 1.002 [0.996, 1.002] |
| other | 33.7 | 32.6 | 47.2 | 46.0 | 1.020 [1.009, 1.032] | 1.032 [0.987, 1.063] | 1.028 [1.011, 1.060] |
| analyze | 146.8 | 143.8 | 272.1 | 272.1 | 1.008 [1.005, 1.011] | 1.021 [0.994, 1.028] | 1.000 [0.996, 1.026] |
| e2e | 190.0 | 190.4 | 331.0 | 330.7 | 0.993 [0.981, 1.004] | 0.998 [0.959, 1.039] | 1.001 [0.976, 1.036] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t4 | pip_t4_bbdt | speedup pip_t4/pip_t4_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 3345 | 3343 | 1.000 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3751 | 3696 | 1.015 |
| analyze total (ms) | 7095 | 7039 | 1.008 |
| OpenCV share of analyze | 47.1 % | 47.5 % | |

Amdahl check: a 1.00x speedup of a 47 % OpenCV share predicts 1.000x end to end; even a 2x faster OpenCV would give only 1.31x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t4 ms | pip_t4_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 2738.2 | 2742.0 | 1.00 |
| py._locate_cracks | 40 | 2354.9 | 2349.7 | 1.00 |
| py._measure_roi | 197 | 2238.3 | 2235.7 | 1.00 |
| py._detect_board | 43 | 1368.7 | 1366.4 | 1.00 |
| py._bg_map | 237 | 986.6 | 984.6 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 942.9 | 940.8 | 1.00 |
| cv2.resize | 560 | 738.3 | 737.5 | 1.00 |
| py.thinning_shim | 426 | 551.4 | 552.7 | 1.00 |
| py._match_specimens | 40 | 442.5 | 443.5 | 1.00 |
| py._longest_path | 426 | 363.7 | 360.7 | 1.01 |
| py._edge_sigma | 40 | 335.2 | 335.3 | 1.00 |
| cv2.medianBlur | 237 | 320.2 | 319.7 | 1.00 |
| cv2.warpPerspective | 554 | 307.6 | 307.2 | 1.00 |
| py._extract_roi | 197 | 224.9 | 225.3 | 1.00 |
| cv2.GaussianBlur | 634 | 224.7 | 225.0 | 1.00 |
| cv2.erode | 317 | 138.9 | 139.3 | 1.00 |
| py._fwhm | 240 | 138.5 | 138.0 | 1.00 |
| cv2.connectedComponentsWithStats | 160 | 134.4 | 135.4 | 0.99 |
| cv2.filter2D | 40 | 91.6 | 91.8 | 1.00 |
| cv2.dilate | 237 | 90.7 | 90.8 | 1.00 |
| py._black_core | 120 | 89.2 | 88.9 | 1.00 |
| cv2.Sobel | 80 | 75.0 | 75.0 | 1.00 |
| cv2.Laplacian | 43 | 58.0 | 58.1 | 1.00 |
| py.gate.assess | 40 | 43.9 | 43.9 | 1.00 |
| cv2.cvtColor | 43 | 43.1 | 42.6 | 1.01 |
| cv2.polylines | 197 | 38.9 | 38.9 | 1.00 |
| cv2.distanceTransform | 120 | 32.2 | 32.3 | 1.00 |
| cv2.magnitude | 40 | 27.5 | 27.5 | 1.00 |
| cv2.findHomography | 120 | 21.8 | 21.7 | 1.00 |
| cv2.morphologyEx | 40 | 17.9 | 17.9 | 1.00 |
| py._smooth_resample | 120 | 14.7 | 14.7 | 1.00 |
| py._station_widths | 120 | 11.9 | 11.9 | 1.00 |
| cv2.cornerSubPix | 40 | 9.7 | 9.7 | 1.00 |
| cv2.findContours | 120 | 7.9 | 7.9 | 1.00 |
| cv2.fillConvexPoly | 40 | 7.9 | 8.5 | 0.93 |
| cv2.remap | 240 | 6.7 | 6.6 | 1.01 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.00 |
| py._pose_obliquity | 40 | 4.3 | 4.3 | 1.00 |
| cv2.copyMakeBorder | 426 | 3.7 | 3.8 | 0.99 |
| cv2.solvePnP | 40 | 1.9 | 1.8 | 1.01 |

Top 5 OpenCV calls by time in pip_t4 (per-call speedup pip_t4/pip_t4_bbdt):

- cv2.aruco.CharucoDetector.detectBoard: 943 ms -> 941 ms over 43 calls, 1.00x
- cv2.resize: 738 ms -> 737 ms over 560 calls, 1.00x
- cv2.medianBlur: 320 ms -> 320 ms over 237 calls, 1.00x
- cv2.warpPerspective: 308 ms -> 307 ms over 554 calls, 1.00x
- cv2.GaussianBlur: 225 ms -> 225 ms over 634 calls, 1.00x

Accuracy invariance: BITWISE IDENTICAL: all 5471 numeric/string leaves of 43 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 120 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 120 cracks with a known width: pip_t4 mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); pip_t4_bbdt mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); paired mean(|e_pip_t4_bbdt| - |e_pip_t4|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 59 vs 59
- canonical sha256: pip_t4 11b309ac9f1abacb..., pip_t4_bbdt 11b309ac9f1abacb...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.magnitude 2/40
- first divergence (input, call index, function): ('raw/IMG20261019080751.jpg', 19, 'cv2.magnitude')
