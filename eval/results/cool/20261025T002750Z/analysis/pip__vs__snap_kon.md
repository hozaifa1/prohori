### pip  vs  snap_kon   (speedup = pip time / snap_kon time; >1 means snap_kon is faster)

| stage | pip p50 ms | snap_kon p50 ms | pip p95 ms | snap_kon p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 51.7 | 53.2 | 64.6 | 64.9 | 0.973 [0.954, 0.993] | 0.972 [0.941, 1.053] | 0.995 [0.932, 1.008] |
| detect | 75.8 | 69.1 | 94.4 | 84.8 | 1.106 [1.096, 1.115] | 1.097 [1.076, 1.134] | 1.112 [1.075, 1.132] |
| rectify | 81.4 | 80.8 | 96.2 | 92.5 | 1.018 [1.014, 1.022] | 1.007 [0.996, 1.025] | 1.040 [0.987, 1.056] |
| measure | 41.9 | 42.3 | 188.6 | 192.0 | 0.983 [0.980, 0.986] | 0.991 [0.963, 1.020] | 0.982 [0.961, 1.012] |
| other | 53.5 | 52.7 | 72.0 | 71.1 | 1.020 [1.017, 1.024] | 1.015 [1.005, 1.031] | 1.012 [1.003, 1.031] |
| analyze | 266.5 | 257.6 | 405.6 | 394.4 | 1.031 [1.028, 1.035] | 1.035 [1.029, 1.054] | 1.028 [1.002, 1.031] |
| e2e | 316.9 | 307.3 | 463.2 | 457.7 | 1.022 [1.017, 1.026] | 1.031 [1.015, 1.053] | 1.012 [0.994, 1.015] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip | snap_kon | speedup pip/snap_kon |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15446 | 14888 | 1.037 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7674 | 7531 | 1.019 |
| analyze total (ms) | 23120 | 22419 | 1.031 |
| OpenCV share of analyze | 66.8 % | 66.4 % | |

Amdahl check: a 1.04x speedup of a 67 % OpenCV share predicts 1.025x end to end; even a 2x faster OpenCV would give only 1.50x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | pip fps | snap_kon fps | x fps | pip e2e p50/p95 ms | snap_kon e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.06 | 3.13 | 1.024 | 331/460 | 321/453 |
| 1x2 | 4.09 | 4.13 | 1.011 | 236/373 | 237/357 |
| 1x4 | 4.63 | 4.73 | 1.021 | 201/335 | 196/332 |
| 2x1 | 6.06 | 6.27 | 1.035 | 332/463 | 313/453 |
| 4x1 | 11.75 | 12.15 | 1.034 | 338/477 | 326/464 |
| 2x2 | 7.97 | 8.14 | 1.021 | 242/378 | 233/372 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | pip ms | snap_kon ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 59.994 | 63.969 | 0.94 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.816 | 3.558 | 1.07 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.642 | 0.528 | 1.22 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 16.023 | 17.775 | 0.90 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.744 | 0.751 | 0.99 | yes |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.797 | 8.111 | 0.59 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.691 | 2.319 | 1.16 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.949 | 5.988 | 0.99 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.439 | 1.209 | 1.19 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.806 | 0.470 | 1.71 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.228 | 0.151 | 1.51 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.499 | 2.581 | 0.97 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.371 | 5.278 | 1.02 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.071 | 0.97 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.778 | 1.799 | 0.99 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.478 | 3.276 | 2.28 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.634 | 0.640 | 0.99 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.970 | 6.913 | 1.01 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.826 | 2.762 | 1.02 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.310 | 2.294 | 1.01 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.041 | 0.038 | 1.09 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.075 | 0.078 | 0.95 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.762 | 2.788 | 0.99 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.307 | 1.406 | 0.93 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.579 | 3.284 | 0.79 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 75.569 | 67.451 | 1.12 | yes |
| 4 | imdecode_jpeg_12MP | 4096x3072 | 60.679 | 64.813 | 0.94 | yes |
| 4 | cvtColor_BGR2GRAY | 4096x3072x3 | 1.014 | 1.341 | 0.76 | yes |
| 4 | resize_AREA_grey_x0.5 | 4096x3072 | 0.624 | 0.156 | 3.99 | yes |
| 4 | resize_AREA_grey_x0.3 | 4096x3072 | 5.277 | 5.084 | 1.04 | yes |
| 4 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.271 | 0.275 | 0.99 | yes |
| 4 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 1.205 | 2.145 | 0.56 | NO |
| 4 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 0.689 | 0.631 | 1.09 | NO |
| 4 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 1.495 | 1.506 | 0.99 | yes |
| 4 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.511 | 0.493 | 1.04 | yes |
| 4 | erode_7x7_u8 | 1273x1800 | 0.815 | 0.473 | 1.73 | yes |
| 4 | erode_5x5_u8_ROI | 2000x500 | 0.229 | 0.154 | 1.49 | yes |
| 4 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 0.637 | 0.657 | 0.97 | yes |
| 4 | GaussianBlur_f32_sigma4 | 2000x500 | 5.324 | 5.442 | 0.98 | yes |
| 4 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.070 | 0.98 | yes |
| 4 | dilate_f32_rect | 2000x500 k=17 | 1.788 | 1.812 | 0.99 | yes |
| 4 | medianBlur_u8_k15 | 318x450 | 7.478 | 1.724 | 4.34 | yes |
| 4 | morphologyEx_close_ellipse | 1273x1800 | 0.379 | 0.387 | 0.98 | yes |
| 4 | connectedComponentsWithStats | 1273x1800 | 2.157 | 2.125 | 1.01 | yes |
| 4 | ximgproc_thinning | 1884x204 | 2.685 | 2.782 | 0.96 | yes |
| 4 | distanceTransform_L2_precise | 1884x204 | 0.706 | 0.707 | 1.00 | yes |
| 4 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.017 | 0.016 | 1.02 | yes |
| 4 | findContours_CCOMP | 1884x204 | 0.077 | 0.081 | 0.95 | yes |
| 4 | Laplacian_f32 | 1273x1800 | 0.880 | 0.880 | 1.00 | yes |
| 4 | findHomography_RANSAC | 112 pts | 1.307 | 1.407 | 0.93 | NO |
| 4 | pipeline_bg_map_f32 | 2000x500 | 2.451 | 2.244 | 1.09 | yes |
| 4 | pipeline_detect_board | 4096x3072 (real photo) | 29.387 | 27.714 | 1.06 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip ms | snap_kon ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6571.1 | 6643.6 | 0.99 |
| py._detect_board | 85 | 6396.3 | 5883.8 | 1.09 |
| py._locate_cracks | 77 | 5247.7 | 5007.5 | 1.05 |
| py._measure_roi | 372 | 4601.4 | 4683.4 | 0.98 |
| cv2.resize | 1065 | 4170.4 | 4331.2 | 0.96 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 4161.7 | 3556.6 | 1.17 |
| cv2.warpPerspective | 1052 | 2328.0 | 2501.8 | 0.93 |
| py._bg_map | 449 | 2048.4 | 1820.7 | 1.13 |
| py._edge_sigma | 77 | 1417.3 | 1465.9 | 0.97 |
| py.thinning_shim | 848 | 1112.2 | 1115.2 | 1.00 |
| py._extract_roi | 372 | 908.3 | 901.8 | 1.01 |
| cv2.GaussianBlur | 1196 | 889.8 | 918.7 | 0.97 |
| py._match_specimens | 77 | 826.2 | 828.2 | 1.00 |
| py._longest_path | 848 | 733.9 | 727.6 | 1.01 |
| cv2.connectedComponentsWithStats | 302 | 700.1 | 714.6 | 0.98 |
| cv2.medianBlur | 449 | 610.0 | 356.4 | 1.71 |
| cv2.filter2D | 77 | 551.3 | 558.9 | 0.99 |
| cv2.Sobel | 154 | 369.7 | 384.0 | 0.96 |
| cv2.Laplacian | 85 | 327.7 | 334.3 | 0.98 |
| cv2.cvtColor | 85 | 310.3 | 295.6 | 1.05 |
| cv2.erode | 603 | 280.6 | 176.4 | 1.59 |
| py._fwhm | 442 | 256.8 | 255.6 | 1.00 |
| cv2.magnitude | 77 | 193.9 | 195.1 | 0.99 |
| cv2.dilate | 449 | 180.7 | 150.3 | 1.20 |
| py._black_core | 221 | 166.3 | 165.8 | 1.00 |
| cv2.distanceTransform | 225 | 123.9 | 123.0 | 1.01 |
| py.gate.assess | 77 | 79.7 | 79.4 | 1.00 |
| cv2.polylines | 372 | 71.1 | 98.1 | 0.72 |
| cv2.morphologyEx | 77 | 51.4 | 52.1 | 0.99 |
| cv2.findHomography | 232 | 41.4 | 46.7 | 0.89 |
| py._smooth_resample | 222 | 28.3 | 28.7 | 0.99 |
| py._station_widths | 221 | 22.9 | 22.7 | 1.01 |
| cv2.cornerSubPix | 77 | 17.5 | 17.7 | 0.99 |
| cv2.fillConvexPoly | 77 | 16.1 | 17.8 | 0.90 |
| cv2.remap | 444 | 15.2 | 16.7 | 0.91 |
| cv2.findContours | 221 | 14.9 | 17.0 | 0.87 |
| cv2.copyMakeBorder | 848 | 9.1 | 11.1 | 0.82 |
| py._uncertainty | 220 | 9.0 | 8.9 | 1.01 |
| py._pose_obliquity | 77 | 8.4 | 9.2 | 0.91 |
| cv2.solvePnP | 77 | 3.7 | 4.5 | 0.84 |

Top 5 OpenCV calls by time in pip (per-call speedup pip/snap_kon):

- cv2.resize: 4170 ms -> 4331 ms over 1065 calls, 0.96x
- cv2.aruco.CharucoDetector.detectBoard: 4162 ms -> 3557 ms over 85 calls, 1.17x
- cv2.warpPerspective: 2328 ms -> 2502 ms over 1052 calls, 0.93x
- cv2.GaussianBlur: 890 ms -> 919 ms over 1196 calls, 0.97x
- cv2.connectedComponentsWithStats: 700 ms -> 715 ms over 302 calls, 0.98x

Accuracy invariance: NOT bitwise identical: 2488 of 10183 leaves differ in 33 of 85 inputs; max |dw| of the reported crack width_mm = 3.040e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 1.826e+00 mm, over all numeric fields 1.826e+00.
- crack width differences over 220 cracks: max 3.040e-02 mm, P99 5.800e-03 mm, mean 6.759e-04 mm (159 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 220 cracks with a known width: pip mean |e| 0.1218 mm (median 0.0615, P95 0.4885, bias -0.0054); snap_kon mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); paired mean(|e_snap_kon| - |e_pip|) = +0.00016 mm [95% CI -0.00013, +0.00056]; cracks certified 109 vs 109
- canonical sha256: pip a8e04739afbbef5b..., snap_kon 13dc541f8dcdda63...
- unrounded internal measurement scalars differing: 3853 (max |d| 1.054e+03)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): <call sequence length> 2/0, cv2.GaussianBlur 1110/1196, cv2.Rodrigues 20/77, cv2.connectedComponentsWithStats 234/302, cv2.contourArea 2/22, cv2.copyMakeBorder 221/848, cv2.dilate 372/449, cv2.distanceTransform 171/225, cv2.erode 16/603, cv2.findContours 171/221, cv2.findHomography 231/232, cv2.getStructuringElement 3/449, cv2.medianBlur 441/449, cv2.morphologyEx 59/77, cv2.polylines 6/372, cv2.remap 214/444, cv2.resize 958/1065, cv2.solvePnP 43/77, cv2.warpPerspective 540/1052, cv2.ximgproc.thinning 159/848, py._bg_map 442/449, py._black_core 221/221, py._edge_sigma 77/77, py._extract_roi 364/372, py._fwhm 440/442, py._locate_cracks 60/77, py._longest_path 140/848, py._match_specimens 14/77, py._measure_roi 224/372, py._pose_obliquity 7/77, py._smooth_resample 124/222, py._station_widths 220/221, py._uncertainty 220/220, py.gate.assess 1/76
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.3767a0f9096bcp+3', 1.826200000000001]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.d45f06f694467p+2', 1.5335999999999999]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.d45a1cac08312p+2', 1.5329999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.65b22d0e56042p+2', 1.3444000000000003]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
