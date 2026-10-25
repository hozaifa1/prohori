### pip_t1  vs  pip_t4   (speedup = pip_t1 time / pip_t4 time; >1 means pip_t4 is faster)

| stage | pip_t1 p50 ms | pip_t4 p50 ms | pip_t1 p95 ms | pip_t4 p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 50.8 | 47.5 | 61.5 | 58.9 | 1.101 [1.067, 1.138] | 1.070 [1.010, 1.200] | 1.044 [0.999, 1.132] |
| detect | 72.4 | 29.9 | 88.8 | 37.5 | 2.382 [2.360, 2.401] | 2.421 [2.338, 2.454] | 2.369 [2.336, 2.426] |
| rectify | 79.3 | 48.3 | 93.5 | 62.5 | 1.605 [1.569, 1.644] | 1.642 [1.564, 1.713] | 1.496 [1.446, 1.559] |
| measure | 42.5 | 28.0 | 179.4 | 150.5 | 1.272 [1.235, 1.329] | 1.518 [1.253, 1.688] | 1.192 [1.168, 1.230] |
| other | 50.8 | 33.7 | 69.7 | 47.2 | 1.558 [1.533, 1.583] | 1.507 [1.473, 1.658] | 1.476 [1.472, 1.596] |
| analyze | 254.1 | 146.8 | 395.1 | 272.1 | 1.624 [1.569, 1.693] | 1.731 [1.483, 1.828] | 1.452 [1.404, 1.466] |
| e2e | 304.3 | 190.0 | 453.9 | 331.0 | 1.514 [1.472, 1.560] | 1.601 [1.547, 1.659] | 1.371 [1.334, 1.412] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip_t1 | pip_t4 | speedup pip_t1/pip_t4 |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7844 | 3345 | 2.345 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3681 | 3751 | 0.982 |
| analyze total (ms) | 11526 | 7095 | 1.624 |
| OpenCV share of analyze | 68.1 % | 47.1 % | |

Amdahl check: a 2.35x speedup of a 68 % OpenCV share predicts 1.640x end to end; even a 2x faster OpenCV would give only 1.52x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip_t1 ms | pip_t4 ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3257.4 | 2738.2 | 1.19 |
| py._detect_board | 43 | 3184.3 | 1368.7 | 2.33 |
| py._locate_cracks | 40 | 2692.6 | 2354.9 | 1.14 |
| py._measure_roi | 197 | 2339.9 | 2238.3 | 1.05 |
| cv2.resize | 560 | 2181.8 | 738.3 | 2.96 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2033.8 | 942.9 | 2.16 |
| cv2.warpPerspective | 554 | 1167.8 | 307.6 | 3.80 |
| py._bg_map | 237 | 1058.3 | 986.6 | 1.07 |
| py._edge_sigma | 40 | 695.9 | 335.2 | 2.08 |
| py.thinning_shim | 426 | 551.0 | 551.4 | 1.00 |
| py._extract_roi | 197 | 454.9 | 224.9 | 2.02 |
| cv2.GaussianBlur | 634 | 453.0 | 224.7 | 2.02 |
| py._match_specimens | 40 | 440.4 | 442.5 | 1.00 |
| py._longest_path | 426 | 364.0 | 363.7 | 1.00 |
| cv2.connectedComponentsWithStats | 160 | 361.2 | 134.4 | 2.69 |
| cv2.medianBlur | 237 | 319.9 | 320.2 | 1.00 |
| cv2.filter2D | 40 | 274.0 | 91.6 | 2.99 |
| cv2.Sobel | 80 | 182.1 | 75.0 | 2.43 |
| cv2.Laplacian | 43 | 164.3 | 58.0 | 2.83 |
| cv2.cvtColor | 43 | 159.4 | 43.1 | 3.70 |
| cv2.erode | 317 | 140.1 | 138.9 | 1.01 |
| py._fwhm | 240 | 139.0 | 138.5 | 1.00 |
| cv2.magnitude | 40 | 96.8 | 27.5 | 3.52 |
| cv2.dilate | 237 | 90.6 | 90.7 | 1.00 |
| py._black_core | 120 | 89.3 | 89.2 | 1.00 |
| cv2.polylines | 197 | 64.9 | 38.9 | 1.67 |
| cv2.distanceTransform | 120 | 64.2 | 32.2 | 2.00 |
| py.gate.assess | 40 | 43.9 | 43.9 | 1.00 |
| cv2.morphologyEx | 40 | 26.5 | 17.9 | 1.49 |
| cv2.findHomography | 120 | 21.9 | 21.8 | 1.00 |
| py._smooth_resample | 120 | 14.8 | 14.7 | 1.01 |
| py._station_widths | 120 | 12.0 | 11.9 | 1.00 |
| cv2.cornerSubPix | 40 | 9.7 | 9.7 | 1.00 |
| cv2.fillConvexPoly | 40 | 8.1 | 7.9 | 1.02 |
| cv2.findContours | 120 | 7.4 | 7.9 | 0.94 |
| cv2.remap | 240 | 7.3 | 6.7 | 1.09 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.01 |
| py._pose_obliquity | 40 | 4.3 | 4.3 | 1.00 |
| cv2.copyMakeBorder | 426 | 4.0 | 3.7 | 1.08 |
| cv2.solvePnP | 40 | 1.8 | 1.9 | 0.99 |

Top 5 OpenCV calls by time in pip_t1 (per-call speedup pip_t1/pip_t4):

- cv2.resize: 2182 ms -> 738 ms over 560 calls, 2.96x
- cv2.aruco.CharucoDetector.detectBoard: 2034 ms -> 943 ms over 43 calls, 2.16x
- cv2.warpPerspective: 1168 ms -> 308 ms over 554 calls, 3.80x
- cv2.GaussianBlur: 453 ms -> 225 ms over 634 calls, 2.02x
- cv2.connectedComponentsWithStats: 361 ms -> 134 ms over 160 calls, 2.69x

Accuracy invariance: BITWISE IDENTICAL: all 5471 numeric/string leaves of 43 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 120 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 120 cracks with a known width: pip_t1 mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); pip_t4 mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); paired mean(|e_pip_t4| - |e_pip_t1|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 59 vs 59
- canonical sha256: pip_t1 11b309ac9f1abacb..., pip_t4 11b309ac9f1abacb...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.magnitude 39/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 19, 'cv2.magnitude')
