### pip_t1_bbdt  vs  pip_t4_bbdt   (speedup = pip_t1_bbdt time / pip_t4_bbdt time; >1 means pip_t4_bbdt is faster)

| stage | pip_t1_bbdt p50 ms | pip_t4_bbdt p50 ms | pip_t1_bbdt p95 ms | pip_t4_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 46.3 | 47.1 | 59.9 | 61.7 | 0.975 [0.953, 0.994] | 0.983 [0.923, 1.003] | 0.970 [0.964, 0.999] |
| detect | 74.1 | 29.8 | 90.0 | 36.7 | 2.442 [2.422, 2.462] | 2.487 [2.399, 2.522] | 2.450 [2.429, 2.489] |
| rectify | 80.7 | 47.9 | 93.6 | 62.5 | 1.649 [1.612, 1.691] | 1.685 [1.602, 1.766] | 1.497 [1.495, 1.579] |
| measure | 42.2 | 27.9 | 177.7 | 150.3 | 1.260 [1.222, 1.318] | 1.513 [1.251, 1.667] | 1.183 [1.149, 1.213] |
| other | 50.8 | 32.6 | 68.5 | 46.0 | 1.575 [1.550, 1.599] | 1.556 [1.506, 1.627] | 1.490 [1.486, 1.646] |
| analyze | 256.8 | 143.8 | 394.0 | 272.1 | 1.646 [1.586, 1.722] | 1.785 [1.510, 1.844] | 1.448 [1.414, 1.481] |
| e2e | 302.5 | 190.4 | 452.4 | 330.7 | 1.496 [1.460, 1.539] | 1.589 [1.536, 1.646] | 1.368 [1.349, 1.396] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t1_bbdt | pip_t4_bbdt | speedup pip_t1_bbdt/pip_t4_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7828 | 3343 | 2.341 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3761 | 3696 | 1.018 |
| analyze total (ms) | 11589 | 7039 | 1.646 |
| OpenCV share of analyze | 67.5 % | 47.5 % | |

Amdahl check: a 2.34x speedup of a 68 % OpenCV share predicts 1.631x end to end; even a 2x faster OpenCV would give only 1.51x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t1_bbdt ms | pip_t4_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3233.5 | 2742.0 | 1.18 |
| py._detect_board | 43 | 3211.6 | 1366.4 | 2.35 |
| py._locate_cracks | 40 | 2661.7 | 2349.7 | 1.13 |
| py._measure_roi | 197 | 2284.7 | 2235.7 | 1.02 |
| cv2.resize | 560 | 2255.2 | 737.5 | 3.06 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2029.9 | 940.8 | 2.16 |
| cv2.warpPerspective | 554 | 1164.5 | 307.2 | 3.79 |
| py._bg_map | 237 | 1055.5 | 984.6 | 1.07 |
| py._edge_sigma | 40 | 692.5 | 335.3 | 2.06 |
| py.thinning_shim | 426 | 549.5 | 552.7 | 0.99 |
| cv2.GaussianBlur | 634 | 453.5 | 225.0 | 2.02 |
| py._extract_roi | 197 | 452.9 | 225.3 | 2.01 |
| py._match_specimens | 40 | 441.8 | 443.5 | 1.00 |
| py._longest_path | 426 | 362.7 | 360.7 | 1.01 |
| cv2.medianBlur | 237 | 319.7 | 319.7 | 1.00 |
| cv2.connectedComponentsWithStats | 160 | 312.2 | 135.4 | 2.31 |
| cv2.filter2D | 40 | 273.2 | 91.8 | 2.98 |
| cv2.Sobel | 80 | 181.7 | 75.0 | 2.42 |
| cv2.Laplacian | 43 | 163.1 | 58.1 | 2.81 |
| cv2.cvtColor | 43 | 156.4 | 42.6 | 3.67 |
| cv2.erode | 317 | 140.1 | 139.3 | 1.01 |
| py._fwhm | 240 | 138.0 | 138.0 | 1.00 |
| cv2.magnitude | 40 | 96.9 | 27.5 | 3.52 |
| cv2.dilate | 237 | 90.3 | 90.8 | 0.99 |
| py._black_core | 120 | 88.7 | 88.9 | 1.00 |
| cv2.distanceTransform | 120 | 64.1 | 32.3 | 1.99 |
| py.gate.assess | 40 | 43.9 | 43.9 | 1.00 |
| cv2.polylines | 197 | 36.9 | 38.9 | 0.95 |
| cv2.morphologyEx | 40 | 26.6 | 17.9 | 1.48 |
| cv2.findHomography | 120 | 21.7 | 21.7 | 1.00 |
| py._smooth_resample | 120 | 14.8 | 14.7 | 1.01 |
| py._station_widths | 120 | 11.8 | 11.9 | 0.99 |
| cv2.cornerSubPix | 40 | 9.7 | 9.7 | 1.00 |
| cv2.fillConvexPoly | 40 | 8.3 | 8.5 | 0.99 |
| cv2.findContours | 120 | 7.4 | 7.9 | 0.94 |
| cv2.remap | 240 | 7.1 | 6.6 | 1.08 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.00 |
| py._pose_obliquity | 40 | 4.2 | 4.3 | 0.99 |
| cv2.copyMakeBorder | 426 | 4.0 | 3.8 | 1.07 |
| cv2.solvePnP | 40 | 1.8 | 1.8 | 1.01 |

Top 5 OpenCV calls by time in pip_t1_bbdt (per-call speedup pip_t1_bbdt/pip_t4_bbdt):

- cv2.resize: 2255 ms -> 737 ms over 560 calls, 3.06x
- cv2.aruco.CharucoDetector.detectBoard: 2030 ms -> 941 ms over 43 calls, 2.16x
- cv2.warpPerspective: 1165 ms -> 307 ms over 554 calls, 3.79x
- cv2.GaussianBlur: 453 ms -> 225 ms over 634 calls, 2.02x
- cv2.medianBlur: 320 ms -> 320 ms over 237 calls, 1.00x

Accuracy invariance: BITWISE IDENTICAL: all 5471 numeric/string leaves of 43 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 120 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 120 cracks with a known width: pip_t1_bbdt mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); pip_t4_bbdt mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); paired mean(|e_pip_t4_bbdt| - |e_pip_t1_bbdt|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 59 vs 59
- canonical sha256: pip_t1_bbdt 11b309ac9f1abacb..., pip_t4_bbdt 11b309ac9f1abacb...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.magnitude 39/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 19, 'cv2.magnitude')
