### pip  vs  cool   (speedup = pip time / cool time; >1 means cool is faster)

| stage | pip p50 ms | cool p50 ms | pip p95 ms | cool p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 51.7 | 52.0 | 64.6 | 67.1 | 0.987 [0.969, 1.008] | 0.994 [0.961, 1.068] | 0.963 [0.960, 1.021] |
| detect | 75.8 | 74.1 | 94.4 | 94.5 | 1.018 [1.012, 1.024] | 1.023 [1.008, 1.032] | 0.999 [0.986, 1.005] |
| rectify | 81.4 | 78.5 | 96.2 | 90.7 | 1.046 [1.042, 1.051] | 1.037 [1.024, 1.058] | 1.062 [1.035, 1.075] |
| measure | 41.9 | 42.9 | 188.6 | 191.3 | 0.987 [0.984, 0.990] | 0.977 [0.948, 1.024] | 0.986 [0.966, 1.018] |
| other | 53.5 | 52.3 | 72.0 | 69.5 | 1.028 [1.025, 1.031] | 1.023 [1.014, 1.040] | 1.035 [1.009, 1.038] |
| analyze | 266.5 | 260.4 | 405.6 | 398.5 | 1.019 [1.016, 1.021] | 1.023 [1.008, 1.031] | 1.018 [1.002, 1.020] |
| e2e | 316.9 | 310.2 | 463.2 | 453.5 | 1.014 [1.010, 1.017] | 1.022 [1.000, 1.038] | 1.021 [0.998, 1.028] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip | cool | speedup pip/cool |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15446 | 15292 | 1.010 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7674 | 7405 | 1.036 |
| analyze total (ms) | 23120 | 22697 | 1.019 |
| OpenCV share of analyze | 66.8 % | 67.4 % | |

Amdahl check: a 1.01x speedup of a 67 % OpenCV share predicts 1.007x end to end; even a 2x faster OpenCV would give only 1.50x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | pip fps | cool fps | x fps | pip e2e p50/p95 ms | cool e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.06 | 3.10 | 1.012 | 331/460 | 327/460 |
| 2x1 | 6.06 | 6.09 | 1.004 | 332/463 | 329/465 |
| 4x1 | 11.75 | 11.69 | 0.995 | 338/477 | 342/468 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | pip ms | cool ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 59.994 | 62.909 | 0.95 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.816 | 3.729 | 1.02 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.642 | 0.526 | 1.22 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 16.023 | 16.141 | 0.99 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.744 | 0.748 | 1.00 | NO |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.797 | 8.636 | 0.56 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.691 | 2.113 | 1.27 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.949 | 6.115 | 0.97 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.439 | 1.113 | 1.29 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.806 | 0.460 | 1.75 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.228 | 0.148 | 1.54 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.499 | 2.636 | 0.95 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.371 | 5.274 | 1.02 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.072 | 0.96 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.778 | 1.772 | 1.00 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.478 | 3.092 | 2.42 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.634 | 0.639 | 0.99 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.970 | 6.339 | 1.10 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.826 | 2.761 | 1.02 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.310 | 1.393 | 1.66 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.041 | 0.037 | 1.13 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.075 | 0.060 | 1.24 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.762 | 2.776 | 0.99 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.307 | 1.413 | 0.93 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.579 | 3.465 | 0.74 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 75.569 | 72.512 | 1.04 | yes |
| 4 | imdecode_jpeg_12MP | 4096x3072 | 60.679 | 62.452 | 0.97 | yes |
| 4 | cvtColor_BGR2GRAY | 4096x3072x3 | 1.014 | 1.054 | 0.96 | yes |
| 4 | resize_AREA_grey_x0.5 | 4096x3072 | 0.624 | 0.150 | 4.15 | yes |
| 4 | resize_AREA_grey_x0.3 | 4096x3072 | 5.277 | 5.265 | 1.00 | yes |
| 4 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.271 | 0.276 | 0.98 | NO |
| 4 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 1.205 | 2.284 | 0.53 | NO |
| 4 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 0.689 | 0.577 | 1.19 | NO |
| 4 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 1.495 | 1.536 | 0.97 | yes |
| 4 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.511 | 0.467 | 1.09 | yes |
| 4 | erode_7x7_u8 | 1273x1800 | 0.815 | 0.463 | 1.76 | yes |
| 4 | erode_5x5_u8_ROI | 2000x500 | 0.229 | 0.152 | 1.50 | yes |
| 4 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 0.637 | 0.676 | 0.94 | yes |
| 4 | GaussianBlur_f32_sigma4 | 2000x500 | 5.324 | 5.450 | 0.98 | yes |
| 4 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.072 | 0.95 | yes |
| 4 | dilate_f32_rect | 2000x500 k=17 | 1.788 | 1.807 | 0.99 | yes |
| 4 | medianBlur_u8_k15 | 318x450 | 7.478 | 1.703 | 4.39 | yes |
| 4 | morphologyEx_close_ellipse | 1273x1800 | 0.379 | 0.385 | 0.98 | yes |
| 4 | connectedComponentsWithStats | 1273x1800 | - | - | - | FAILED: A: ok; B: child rc=-6 (crash): Fatal glibc error: malloc.c:2599 (sysmalloc): assertion failed: (old_top == ini |
| 4 | ximgproc_thinning | 1884x204 | 2.685 | 2.669 | 1.01 | yes |
| 4 | distanceTransform_L2_precise | 1884x204 | 0.706 | 0.422 | 1.67 | yes |
| 4 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.017 | 0.016 | 1.02 | yes |
| 4 | findContours_CCOMP | 1884x204 | 0.077 | 0.065 | 1.18 | yes |
| 4 | Laplacian_f32 | 1273x1800 | 0.880 | 0.882 | 1.00 | yes |
| 4 | findHomography_RANSAC | 112 pts | 1.307 | 1.414 | 0.92 | NO |
| 4 | pipeline_bg_map_f32 | 2000x500 | 2.451 | 2.580 | 0.95 | yes |
| 4 | pipeline_detect_board | 4096x3072 (real photo) | 29.387 | 26.378 | 1.11 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip ms | cool ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6571.1 | 6518.0 | 1.01 |
| py._detect_board | 85 | 6396.3 | 6430.9 | 0.99 |
| py._locate_cracks | 77 | 5247.7 | 4900.6 | 1.07 |
| py._measure_roi | 372 | 4601.4 | 4636.0 | 0.99 |
| cv2.resize | 1065 | 4170.4 | 4168.1 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 4161.7 | 4202.3 | 0.99 |
| cv2.warpPerspective | 1052 | 2328.0 | 2545.6 | 0.91 |
| py._bg_map | 449 | 2048.4 | 1811.7 | 1.13 |
| py._edge_sigma | 77 | 1417.3 | 1484.6 | 0.95 |
| py.thinning_shim | 848 | 1112.2 | 1112.9 | 1.00 |
| py._extract_roi | 372 | 908.3 | 903.1 | 1.01 |
| cv2.GaussianBlur | 1196 | 889.8 | 917.8 | 0.97 |
| py._match_specimens | 77 | 826.2 | 830.1 | 1.00 |
| py._longest_path | 848 | 733.9 | 721.2 | 1.02 |
| cv2.connectedComponentsWithStats | 302 | 700.1 | 648.5 | 1.08 |
| cv2.medianBlur | 449 | 610.0 | 357.5 | 1.71 |
| cv2.filter2D | 77 | 551.3 | 555.1 | 0.99 |
| cv2.Sobel | 154 | 369.7 | 388.3 | 0.95 |
| cv2.Laplacian | 85 | 327.7 | 330.9 | 0.99 |
| cv2.cvtColor | 85 | 310.3 | 308.1 | 1.01 |
| cv2.erode | 603 | 280.6 | 175.6 | 1.60 |
| py._fwhm | 442 | 256.8 | 258.6 | 0.99 |
| cv2.magnitude | 77 | 193.9 | 194.8 | 1.00 |
| cv2.dilate | 449 | 180.7 | 149.9 | 1.21 |
| py._black_core | 221 | 166.3 | 167.4 | 0.99 |
| cv2.distanceTransform | 225 | 123.9 | 83.4 | 1.49 |
| py.gate.assess | 77 | 79.7 | 80.1 | 0.99 |
| cv2.polylines | 372 | 71.1 | 74.3 | 0.96 |
| cv2.morphologyEx | 77 | 51.4 | 52.1 | 0.99 |
| cv2.findHomography | 232 | 41.4 | 46.9 | 0.88 |
| py._smooth_resample | 222 | 28.3 | 28.5 | 0.99 |
| py._station_widths | 221 | 22.9 | 22.9 | 1.00 |
| cv2.cornerSubPix | 77 | 17.5 | 17.7 | 0.99 |
| cv2.fillConvexPoly | 77 | 16.1 | 17.6 | 0.91 |
| cv2.remap | 444 | 15.2 | 16.8 | 0.91 |
| cv2.findContours | 221 | 14.9 | 15.4 | 0.97 |
| cv2.copyMakeBorder | 848 | 9.1 | 11.2 | 0.82 |
| py._uncertainty | 220 | 9.0 | 8.8 | 1.02 |
| py._pose_obliquity | 77 | 8.4 | 9.2 | 0.91 |
| cv2.solvePnP | 77 | 3.7 | 4.4 | 0.85 |

Top 5 OpenCV calls by time in pip (per-call speedup pip/cool):

- cv2.resize: 4170 ms -> 4168 ms over 1065 calls, 1.00x
- cv2.aruco.CharucoDetector.detectBoard: 4162 ms -> 4202 ms over 85 calls, 0.99x
- cv2.warpPerspective: 2328 ms -> 2546 ms over 1052 calls, 0.91x
- cv2.GaussianBlur: 890 ms -> 918 ms over 1196 calls, 0.97x
- cv2.connectedComponentsWithStats: 700 ms -> 649 ms over 302 calls, 1.08x

Accuracy invariance: NOT bitwise identical: 2391 of 10184 leaves differ in 32 of 85 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 220 cracks: max 2.990e-02 mm, P99 1.504e-02 mm, mean 7.150e-04 mm (154 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 220 cracks with a known width: pip mean |e| 0.1218 mm (median 0.0615, P95 0.4885, bias -0.0054); cool mean |e| 0.1219 mm (median 0.0618, P95 0.4874, bias -0.0055); paired mean(|e_cool| - |e_pip|) = +0.00010 mm [95% CI -0.00024, +0.00053]; cracks certified 109 vs 108
- canonical sha256: pip a8e04739afbbef5b..., cool 832d4ee68f57e79d...
- unrounded internal measurement scalars differing: 3715 (max |d| 1.064e+03)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): <call sequence length> 1/0, cv2.GaussianBlur 1102/1196, cv2.Rodrigues 70/77, cv2.connectedComponentsWithStats 224/302, cv2.contourArea 1/22, cv2.copyMakeBorder 208/848, cv2.dilate 371/449, cv2.distanceTransform 162/225, cv2.erode 18/603, cv2.findContours 161/221, cv2.findHomography 231/232, cv2.medianBlur 441/449, cv2.morphologyEx 57/77, cv2.polylines 2/372, cv2.remap 214/444, cv2.resize 964/1065, cv2.solvePnP 74/77, cv2.warpPerspective 540/1052, cv2.ximgproc.thinning 146/848, py._bg_map 448/449, py._black_core 213/221, py._edge_sigma 76/77, py._extract_roi 364/372, py._fwhm 426/442, py._locate_cracks 57/77, py._longest_path 130/848, py._match_specimens 13/77, py._measure_roi 213/372, py._pose_obliquity 43/77, py._smooth_resample 112/222, py._station_widths 213/221, py._uncertainty 220/220, py.gate.assess 1/76
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.42ab367a0f909p+3', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.ec37b4a2339c1p+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.ec395810624ddp+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.74d1b71758e22p+2', 1.5807000000000002]; ['synth/synth_00470.jpg', 'cracks.C2.quality.dt_rel', '0x1.57886594af4f1p+2', '0x1.2a3886594af4fp+2', 0.7080000000000002]
