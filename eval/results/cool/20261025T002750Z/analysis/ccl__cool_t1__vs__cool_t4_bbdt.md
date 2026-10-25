### cool_t1  vs  cool_t4_bbdt   (speedup = cool_t1 time / cool_t4_bbdt time; >1 means cool_t4_bbdt is faster)

| stage | cool_t1 p50 ms | cool_t4_bbdt p50 ms | cool_t1 p95 ms | cool_t4_bbdt p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 53.1 | 51.5 | 64.0 | 64.0 | 1.010 [1.001, 1.023] | 1.031 [0.997, 1.085] | 1.001 [0.995, 1.005] |
| detect | 72.8 | 28.2 | 90.4 | 36.0 | 2.559 [2.536, 2.583] | 2.582 [2.477, 2.699] | 2.511 [2.478, 2.580] |
| rectify | 76.6 | 41.3 | 91.5 | 56.1 | 1.789 [1.743, 1.840] | 1.855 [1.766, 1.950] | 1.629 [1.583, 1.691] |
| measure | 43.4 | 28.6 | 180.1 | 151.2 | 1.271 [1.235, 1.331] | 1.517 [1.269, 1.662] | 1.191 [1.126, 1.220] |
| other | 49.6 | 31.2 | 67.8 | 43.5 | 1.635 [1.613, 1.656] | 1.591 [1.552, 1.689] | 1.559 [1.551, 1.694] |
| analyze | 251.7 | 136.2 | 390.1 | 261.4 | 1.709 [1.643, 1.792] | 1.847 [1.599, 1.950] | 1.492 [1.429, 1.523] |
| e2e | 305.2 | 183.4 | 450.9 | 322.1 | 1.537 [1.497, 1.581] | 1.664 [1.592, 1.699] | 1.400 [1.350, 1.422] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | cool_t1 | cool_t4_bbdt | speedup cool_t1/cool_t4_bbdt |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 7678 | 7678 | 1.000 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 3706 | -1018 | -3.641 |
| analyze total (ms) | 11384 | 6661 | 1.709 |
| OpenCV share of analyze | 67.4 % | 115.3 % | |

Amdahl check: a 1.00x speedup of a 67 % OpenCV share predicts 1.000x end to end; even a 2x faster OpenCV would give only 1.51x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | cool_t1 ms | cool_t4_bbdt ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 40 | 3208.9 | 3241.3 | 0.99 |
| py._detect_board | 43 | 3174.6 | 3164.6 | 1.00 |
| py._locate_cracks | 40 | 2501.4 | 2500.1 | 1.00 |
| py._measure_roi | 197 | 2305.8 | 2334.3 | 0.99 |
| cv2.resize | 560 | 2155.8 | 2157.7 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 43 | 2040.3 | 2029.3 | 1.01 |
| cv2.warpPerspective | 554 | 1276.4 | 1278.2 | 1.00 |
| py._bg_map | 237 | 922.1 | 925.6 | 1.00 |
| py._edge_sigma | 40 | 726.2 | 728.1 | 1.00 |
| py.thinning_shim | 426 | 547.7 | 550.4 | 1.00 |
| cv2.GaussianBlur | 634 | 467.9 | 465.6 | 1.01 |
| py._extract_roi | 197 | 450.2 | 450.0 | 1.00 |
| py._match_specimens | 40 | 442.7 | 442.4 | 1.00 |
| py._longest_path | 426 | 357.1 | 363.5 | 0.98 |
| cv2.connectedComponentsWithStats | 160 | 331.5 | 313.5 | 1.06 |
| cv2.filter2D | 40 | 276.1 | 276.0 | 1.00 |
| cv2.Sobel | 80 | 192.9 | 192.6 | 1.00 |
| cv2.medianBlur | 237 | 185.2 | 185.1 | 1.00 |
| cv2.Laplacian | 43 | 164.1 | 168.1 | 0.98 |
| cv2.cvtColor | 43 | 152.4 | 152.7 | 1.00 |
| py._fwhm | 240 | 138.9 | 138.7 | 1.00 |
| cv2.magnitude | 40 | 97.1 | 97.3 | 1.00 |
| py._black_core | 120 | 89.2 | 89.0 | 1.00 |
| cv2.erode | 317 | 85.9 | 85.9 | 1.00 |
| cv2.dilate | 237 | 74.1 | 74.3 | 1.00 |
| py.gate.assess | 40 | 45.8 | 44.4 | 1.03 |
| cv2.distanceTransform | 120 | 42.8 | 42.9 | 1.00 |
| cv2.polylines | 197 | 38.5 | 62.9 | 0.61 |
| cv2.morphologyEx | 40 | 26.9 | 27.0 | 1.00 |
| cv2.findHomography | 120 | 24.7 | 24.5 | 1.01 |
| py._smooth_resample | 120 | 14.7 | 14.7 | 1.00 |
| py._station_widths | 120 | 11.8 | 11.8 | 1.00 |
| cv2.cornerSubPix | 40 | 9.8 | 9.8 | 1.00 |
| cv2.fillConvexPoly | 40 | 8.8 | 8.6 | 1.02 |
| cv2.remap | 240 | 7.6 | 7.6 | 0.99 |
| cv2.findContours | 120 | 7.3 | 7.3 | 1.00 |
| py._uncertainty | 120 | 4.8 | 4.8 | 1.01 |
| cv2.copyMakeBorder | 426 | 4.8 | 4.9 | 0.97 |
| py._pose_obliquity | 40 | 4.6 | 4.7 | 1.00 |
| cv2.rectangle | 40 | 2.3 | 2.2 | 1.03 |

Top 5 OpenCV calls by time in cool_t1 (per-call speedup cool_t1/cool_t4_bbdt):

- cv2.resize: 2156 ms -> 2158 ms over 560 calls, 1.00x
- cv2.aruco.CharucoDetector.detectBoard: 2040 ms -> 2029 ms over 43 calls, 1.01x
- cv2.warpPerspective: 1276 ms -> 1278 ms over 554 calls, 1.00x
- cv2.GaussianBlur: 468 ms -> 466 ms over 634 calls, 1.01x
- cv2.connectedComponentsWithStats: 332 ms -> 313 ms over 160 calls, 1.06x

Accuracy invariance: BITWISE IDENTICAL: all 5472 numeric/string leaves of 43 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 120 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 120 cracks with a known width: cool_t1 mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); cool_t4_bbdt mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool_t4_bbdt| - |e_cool_t1|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 58 vs 58
- canonical sha256: cool_t1 3cb998050814777d..., cool_t4_bbdt 3cb998050814777d...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- every OpenCV function output in the pipeline is byte-identical across the two builds
