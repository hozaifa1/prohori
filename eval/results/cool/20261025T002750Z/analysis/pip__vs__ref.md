### pip  vs  ref   (speedup = pip time / ref time; >1 means ref is faster)

| stage | pip p50 ms | ref p50 ms | pip p95 ms | ref p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 51.7 | 52.6 | 64.6 | 66.3 | 0.984 [0.963, 1.007] | 0.983 [0.947, 1.065] | 0.974 [0.936, 1.009] |
| detect | 75.8 | 77.9 | 94.4 | 97.6 | 0.972 [0.969, 0.976] | 0.973 [0.964, 0.985] | 0.967 [0.959, 0.977] |
| rectify | 81.4 | 82.3 | 96.2 | 96.5 | 0.996 [0.992, 1.000] | 0.989 [0.973, 1.007] | 0.998 [0.986, 1.031] |
| measure | 41.9 | 42.4 | 188.6 | 188.5 | 0.993 [0.991, 0.995] | 0.988 [0.976, 1.008] | 1.001 [0.974, 1.027] |
| other | 53.5 | 53.2 | 72.0 | 71.1 | 1.004 [1.000, 1.009] | 1.006 [0.974, 1.019] | 1.011 [0.979, 1.012] |
| analyze | 266.5 | 268.2 | 405.6 | 408.4 | 0.990 [0.989, 0.992] | 0.994 [0.979, 0.997] | 0.993 [0.978, 1.000] |
| e2e | 316.9 | 317.6 | 463.2 | 466.3 | 0.989 [0.986, 0.993] | 0.998 [0.975, 1.010] | 0.993 [0.976, 1.008] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip | ref | speedup pip/ref |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15446 | 15922 | 0.970 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7674 | 7427 | 1.033 |
| analyze total (ms) | 23120 | 23350 | 0.990 |
| OpenCV share of analyze | 66.8 % | 68.2 % | |

Amdahl check: a 0.97x speedup of a 67 % OpenCV share predicts 0.980x end to end; even a 2x faster OpenCV would give only 1.50x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | pip fps | ref fps | x fps | pip e2e p50/p95 ms | ref e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.06 | 3.03 | 0.990 | 331/460 | 334/470 |
| 1x2 | 4.09 | 3.94 | 0.964 | 236/373 | 250/381 |
| 1x4 | 4.63 | 4.53 | 0.977 | 201/335 | 208/341 |
| 2x1 | 6.06 | 5.95 | 0.981 | 332/463 | 338/473 |
| 4x1 | 11.75 | 11.43 | 0.973 | 338/477 | 346/483 |
| 2x2 | 7.97 | 7.79 | 0.977 | 242/378 | 245/386 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | pip ms | ref ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 59.994 | 64.602 | 0.93 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.816 | 3.604 | 1.06 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.642 | 0.685 | 0.94 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 16.023 | 17.543 | 0.91 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.744 | 0.753 | 0.99 | yes |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.797 | 4.853 | 0.99 | yes |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.691 | 2.760 | 0.98 | yes |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.949 | 5.990 | 0.99 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.439 | 1.488 | 0.97 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.806 | 0.674 | 1.20 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.228 | 0.201 | 1.14 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.499 | 2.609 | 0.96 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.371 | 5.246 | 1.02 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.071 | 0.98 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.778 | 1.795 | 0.99 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.478 | 7.501 | 1.00 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.634 | 0.649 | 0.98 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.970 | 6.913 | 1.01 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.826 | 2.772 | 1.02 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.310 | 2.298 | 1.01 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.041 | 0.038 | 1.09 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.075 | 0.079 | 0.94 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.762 | 2.786 | 0.99 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.307 | 1.410 | 0.93 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.579 | 2.640 | 0.98 | yes |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 75.569 | 76.424 | 0.99 | yes |
| 4 | imdecode_jpeg_12MP | 4096x3072 | 60.679 | 64.500 | 0.94 | yes |
| 4 | cvtColor_BGR2GRAY | 4096x3072x3 | 1.014 | 1.048 | 0.97 | yes |
| 4 | resize_AREA_grey_x0.5 | 4096x3072 | 0.624 | 0.610 | 1.02 | yes |
| 4 | resize_AREA_grey_x0.3 | 4096x3072 | 5.277 | 4.923 | 1.07 | yes |
| 4 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.271 | 0.271 | 1.00 | yes |
| 4 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 1.205 | 1.222 | 0.99 | yes |
| 4 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 0.689 | 0.712 | 0.97 | yes |
| 4 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 1.495 | 1.509 | 0.99 | yes |
| 4 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.511 | 0.527 | 0.97 | yes |
| 4 | erode_7x7_u8 | 1273x1800 | 0.815 | 0.682 | 1.20 | yes |
| 4 | erode_5x5_u8_ROI | 2000x500 | 0.229 | 0.199 | 1.15 | yes |
| 4 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 0.637 | 0.661 | 0.96 | yes |
| 4 | GaussianBlur_f32_sigma4 | 2000x500 | 5.324 | 5.389 | 0.99 | yes |
| 4 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.071 | 0.98 | yes |
| 4 | dilate_f32_rect | 2000x500 k=17 | 1.788 | 1.809 | 0.99 | yes |
| 4 | medianBlur_u8_k15 | 318x450 | 7.478 | 7.468 | 1.00 | yes |
| 4 | morphologyEx_close_ellipse | 1273x1800 | 0.379 | 0.380 | 1.00 | yes |
| 4 | connectedComponentsWithStats | 1273x1800 | 2.157 | 2.204 | 0.98 | yes |
| 4 | ximgproc_thinning | 1884x204 | 2.685 | 2.682 | 1.00 | yes |
| 4 | distanceTransform_L2_precise | 1884x204 | 0.706 | 0.694 | 1.02 | yes |
| 4 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.017 | 0.016 | 1.01 | yes |
| 4 | findContours_CCOMP | 1884x204 | 0.077 | 0.081 | 0.95 | yes |
| 4 | Laplacian_f32 | 1273x1800 | 0.880 | 0.880 | 1.00 | yes |
| 4 | findHomography_RANSAC | 112 pts | 1.307 | 1.408 | 0.93 | NO |
| 4 | pipeline_bg_map_f32 | 2000x500 | 2.451 | 2.472 | 0.99 | yes |
| 4 | pipeline_detect_board | 4096x3072 (real photo) | 29.387 | 29.789 | 0.99 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip ms | ref ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6571.1 | 6649.7 | 0.99 |
| py._detect_board | 85 | 6396.3 | 6734.9 | 0.95 |
| py._locate_cracks | 77 | 5247.7 | 5295.8 | 0.99 |
| py._measure_roi | 372 | 4601.4 | 4647.3 | 0.99 |
| cv2.resize | 1065 | 4170.4 | 4248.0 | 0.98 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 4161.7 | 4457.6 | 0.93 |
| cv2.warpPerspective | 1052 | 2328.0 | 2399.1 | 0.97 |
| py._bg_map | 449 | 2048.4 | 2072.9 | 0.99 |
| py._edge_sigma | 77 | 1417.3 | 1457.8 | 0.97 |
| py.thinning_shim | 848 | 1112.2 | 1113.5 | 1.00 |
| py._extract_roi | 372 | 908.3 | 922.0 | 0.99 |
| cv2.GaussianBlur | 1196 | 889.8 | 925.4 | 0.96 |
| py._match_specimens | 77 | 826.2 | 828.2 | 1.00 |
| py._longest_path | 848 | 733.9 | 719.5 | 1.02 |
| cv2.connectedComponentsWithStats | 302 | 700.1 | 703.6 | 1.00 |
| cv2.medianBlur | 449 | 610.0 | 608.9 | 1.00 |
| cv2.filter2D | 77 | 551.3 | 555.5 | 0.99 |
| cv2.Sobel | 154 | 369.7 | 381.5 | 0.97 |
| cv2.Laplacian | 85 | 327.7 | 336.5 | 0.97 |
| cv2.cvtColor | 85 | 310.3 | 303.1 | 1.02 |
| cv2.erode | 603 | 280.6 | 234.7 | 1.20 |
| py._fwhm | 442 | 256.8 | 256.7 | 1.00 |
| cv2.magnitude | 77 | 193.9 | 195.4 | 0.99 |
| cv2.dilate | 449 | 180.7 | 169.2 | 1.07 |
| py._black_core | 221 | 166.3 | 166.4 | 1.00 |
| cv2.distanceTransform | 225 | 123.9 | 122.8 | 1.01 |
| py.gate.assess | 77 | 79.7 | 80.3 | 0.99 |
| cv2.polylines | 372 | 71.1 | 87.0 | 0.82 |
| cv2.morphologyEx | 77 | 51.4 | 52.4 | 0.98 |
| cv2.findHomography | 232 | 41.4 | 46.7 | 0.88 |
| py._smooth_resample | 222 | 28.3 | 28.8 | 0.99 |
| py._station_widths | 221 | 22.9 | 22.6 | 1.02 |
| cv2.cornerSubPix | 77 | 17.5 | 17.8 | 0.98 |
| cv2.fillConvexPoly | 77 | 16.1 | 17.8 | 0.90 |
| cv2.remap | 444 | 15.2 | 16.5 | 0.92 |
| cv2.findContours | 221 | 14.9 | 17.0 | 0.87 |
| cv2.copyMakeBorder | 848 | 9.1 | 11.3 | 0.81 |
| py._uncertainty | 220 | 9.0 | 8.9 | 1.01 |
| py._pose_obliquity | 77 | 8.4 | 9.3 | 0.90 |
| cv2.solvePnP | 77 | 3.7 | 4.5 | 0.83 |

Top 5 OpenCV calls by time in pip (per-call speedup pip/ref):

- cv2.resize: 4170 ms -> 4248 ms over 1065 calls, 0.98x
- cv2.aruco.CharucoDetector.detectBoard: 4162 ms -> 4458 ms over 85 calls, 0.93x
- cv2.warpPerspective: 2328 ms -> 2399 ms over 1052 calls, 0.97x
- cv2.GaussianBlur: 890 ms -> 925 ms over 1196 calls, 0.96x
- cv2.connectedComponentsWithStats: 700 ms -> 704 ms over 302 calls, 1.00x

Accuracy invariance: NOT bitwise identical: 2449 of 10183 leaves differ in 32 of 85 inputs; max |dw| of the reported crack width_mm = 3.040e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 1.826e+00 mm, over all numeric fields 1.826e+00.
- crack width differences over 220 cracks: max 3.040e-02 mm, P99 5.800e-03 mm, mean 6.750e-04 mm (159 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 220 cracks with a known width: pip mean |e| 0.1218 mm (median 0.0615, P95 0.4885, bias -0.0054); ref mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); paired mean(|e_ref| - |e_pip|) = +0.00016 mm [95% CI -0.00013, +0.00056]; cracks certified 109 vs 109
- canonical sha256: pip a8e04739afbbef5b..., ref 2a3fa732f2ac5ea6...
- unrounded internal measurement scalars differing: 3799 (max |d| 1.053e+03)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): <call sequence length> 2/0, cv2.GaussianBlur 1093/1196, cv2.Rodrigues 20/77, cv2.connectedComponentsWithStats 226/302, cv2.contourArea 2/22, cv2.copyMakeBorder 210/848, cv2.dilate 364/449, cv2.distanceTransform 169/225, cv2.erode 16/603, cv2.findContours 169/221, cv2.findHomography 231/232, cv2.getStructuringElement 3/449, cv2.medianBlur 440/449, cv2.morphologyEx 53/77, cv2.polylines 6/372, cv2.remap 214/444, cv2.resize 956/1065, cv2.solvePnP 43/77, cv2.warpPerspective 538/1052, cv2.ximgproc.thinning 155/848, py._bg_map 440/449, py._black_core 221/221, py._edge_sigma 77/77, py._extract_roi 364/372, py._fwhm 424/442, py._locate_cracks 54/77, py._longest_path 140/848, py._match_specimens 12/77, py._measure_roi 224/372, py._pose_obliquity 7/77, py._smooth_resample 122/222, py._station_widths 220/221, py._uncertainty 220/220, py.gate.assess 1/76
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.3767a0f9096bcp+3', 1.826200000000001]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.d45f06f694467p+2', 1.5335999999999999]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.d45a1cac08312p+2', 1.5329999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.65b22d0e56042p+2', 1.3444000000000003]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
