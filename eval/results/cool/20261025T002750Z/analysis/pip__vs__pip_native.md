### pip  vs  pip_native   (speedup = pip time / pip_native time; >1 means pip_native is faster)

| stage | pip p50 ms | pip_native p50 ms | pip p95 ms | pip_native p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 51.7 | 51.1 | 64.6 | 63.9 | 1.011 [1.011, 1.012] | 1.013 [1.007, 1.020] | 1.011 [1.000, 1.018] |
| detect | 75.8 | 75.6 | 94.4 | 93.8 | 1.002 [1.001, 1.003] | 1.003 [0.993, 1.010] | 1.006 [0.994, 1.011] |
| rectify | 81.4 | 79.9 | 96.2 | 125.8 | 0.970 [0.934, 0.998] | 1.019 [1.001, 1.030] | 0.765 [0.634, 0.989] |
| measure | 41.9 | 41.8 | 188.6 | 210.4 | 0.944 [0.934, 0.957] | 1.002 [0.991, 1.020] | 0.896 [0.889, 0.928] |
| other | 53.5 | 52.8 | 72.0 | 71.7 | 1.007 [1.005, 1.009] | 1.013 [0.999, 1.020] | 1.004 [0.979, 1.015] |
| analyze | 266.5 | 264.7 | 405.6 | 433.0 | 0.978 [0.966, 0.988] | 1.007 [0.985, 1.017] | 0.937 [0.885, 0.962] |
| e2e | 316.9 | 313.8 | 463.2 | 483.4 | 0.983 [0.973, 0.992] | 1.010 [1.001, 1.016] | 0.958 [0.918, 0.968] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip | pip_native | speedup pip/pip_native |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15446 | 17393 | 0.888 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7674 | 6249 | 1.228 |
| analyze total (ms) | 23120 | 23642 | 0.978 |
| OpenCV share of analyze | 66.8 % | 73.6 % | |

Amdahl check: a 0.89x speedup of a 67 % OpenCV share predicts 0.922x end to end; even a 2x faster OpenCV would give only 1.50x.

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip ms | pip_native ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6571.1 | 6529.0 | 1.01 |
| py._detect_board | 85 | 6396.3 | 6548.2 | 0.98 |
| py._locate_cracks | 77 | 5247.7 | 5433.3 | 0.97 |
| py._measure_roi | 372 | 4601.4 | 4974.2 | 0.93 |
| cv2.resize | 1065 | 4170.4 | 4430.6 | 0.94 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 4161.7 | 4150.8 | 1.00 |
| cv2.warpPerspective | 1052 | 2328.0 | 2325.9 | 1.00 |
| py._bg_map | 449 | 2048.4 | 2043.9 | 1.00 |
| py._edge_sigma | 77 | 1417.3 | 1415.9 | 1.00 |
| py._extract_roi | 372 | 908.3 | 905.3 | 1.00 |
| cv2.GaussianBlur | 1196 | 889.8 | 889.6 | 1.00 |
| py._match_specimens | 77 | 826.2 | 830.7 | 0.99 |
| py._longest_path | 848 | 733.9 | 735.2 | 1.00 |
| cv2.connectedComponentsWithStats | 302 | 700.1 | 699.1 | 1.00 |
| cv2.medianBlur | 449 | 610.0 | 610.1 | 1.00 |
| cv2.filter2D | 77 | 551.3 | 552.4 | 1.00 |
| cv2.Sobel | 154 | 369.7 | 368.6 | 1.00 |
| cv2.Laplacian | 85 | 327.7 | 331.5 | 0.99 |
| cv2.cvtColor | 85 | 310.3 | 313.7 | 0.99 |
| cv2.erode | 603 | 280.6 | 279.9 | 1.00 |
| py._fwhm | 442 | 256.8 | 255.9 | 1.00 |
| cv2.magnitude | 77 | 193.9 | 194.0 | 1.00 |
| cv2.dilate | 449 | 180.7 | 181.2 | 1.00 |
| py._black_core | 221 | 166.3 | 166.0 | 1.00 |
| cv2.distanceTransform | 225 | 123.9 | 123.9 | 1.00 |
| py.gate.assess | 77 | 79.7 | 79.5 | 1.00 |
| cv2.polylines | 372 | 71.1 | 70.4 | 1.01 |
| cv2.morphologyEx | 77 | 51.4 | 54.5 | 0.94 |
| cv2.findHomography | 232 | 41.4 | 41.6 | 1.00 |
| py._smooth_resample | 222 | 28.3 | 28.3 | 1.00 |
| py._station_widths | 221 | 22.9 | 22.9 | 1.00 |
| cv2.cornerSubPix | 77 | 17.5 | 17.5 | 1.00 |
| cv2.fillConvexPoly | 77 | 16.1 | 16.5 | 0.97 |
| cv2.remap | 444 | 15.2 | 14.4 | 1.06 |
| cv2.findContours | 221 | 14.9 | 14.5 | 1.02 |
| cv2.copyMakeBorder | 848 | 9.1 | 8.1 | 1.13 |
| py._uncertainty | 220 | 9.0 | 9.0 | 1.00 |
| py._pose_obliquity | 77 | 8.4 | 8.4 | 1.00 |
| cv2.solvePnP | 77 | 3.7 | 3.7 | 1.01 |
| cv2.getStructuringElement | 449 | 3.6 | 3.5 | 1.02 |

Top 5 OpenCV calls by time in pip (per-call speedup pip/pip_native):

- cv2.resize: 4170 ms -> 4431 ms over 1065 calls, 0.94x
- cv2.aruco.CharucoDetector.detectBoard: 4162 ms -> 4151 ms over 85 calls, 1.00x
- cv2.warpPerspective: 2328 ms -> 2326 ms over 1052 calls, 1.00x
- cv2.GaussianBlur: 890 ms -> 890 ms over 1196 calls, 1.00x
- cv2.connectedComponentsWithStats: 700 ms -> 699 ms over 302 calls, 1.00x

Accuracy invariance: BITWISE IDENTICAL: all 10183 numeric/string leaves of 85 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 220 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 220 cracks with a known width: pip mean |e| 0.1218 mm (median 0.0615, P95 0.4885, bias -0.0054); pip_native mean |e| 0.1218 mm (median 0.0615, P95 0.4885, bias -0.0054); paired mean(|e_pip_native| - |e_pip|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 109 vs 109
- canonical sha256: pip a8e04739afbbef5b..., pip_native a8e04739afbbef5b...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- every OpenCV function output in the pipeline is byte-identical across the two builds
