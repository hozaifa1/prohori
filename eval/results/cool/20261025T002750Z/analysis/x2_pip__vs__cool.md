### pip  vs  cool   (speedup = pip time / cool time; >1 means cool is faster)

| stage | pip p50 ms | cool p50 ms | pip p95 ms | cool p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 46.3 | 53.3 | 60.3 | 64.7 | 0.903 [0.872, 0.935] | 0.868 [0.813, 0.948] | 0.932 [0.923, 0.973] |
| detect | 72.4 | 72.4 | 88.9 | 89.7 | 0.999 [0.993, 1.006] | 1.000 [0.985, 1.016] | 0.991 [0.978, 0.993] |
| rectify | 80.9 | 76.7 | 93.0 | 90.3 | 1.064 [1.058, 1.070] | 1.055 [1.043, 1.083] | 1.030 [1.012, 1.126] |
| measure | 42.5 | 43.8 | 177.5 | 177.9 | 0.988 [0.983, 0.993] | 0.970 [0.936, 1.011] | 0.997 [0.977, 1.018] |
| other | 50.1 | 49.7 | 68.2 | 66.9 | 1.022 [1.015, 1.029] | 1.008 [0.988, 1.030] | 1.020 [1.011, 1.056] |
| analyze | 256.4 | 249.5 | 392.2 | 388.2 | 1.018 [1.015, 1.021] | 1.028 [1.005, 1.029] | 1.010 [1.010, 1.020] |
| e2e | 299.2 | 300.3 | 450.6 | 449.2 | 0.999 [0.993, 1.005] | 0.996 [0.977, 1.013] | 1.003 [0.983, 1.012] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | pip | cool | speedup pip/cool |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 2764 | 2709 | 1.020 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 1282 | 1268 | 1.011 |
| analyze total (ms) | 4046 | 3977 | 1.017 |
| OpenCV share of analyze | 68.3 % | 68.1 % | |

Amdahl check: a 1.02x speedup of a 68 % OpenCV share predicts 1.014x end to end; even a 2x faster OpenCV would give only 1.52x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | pip fps | cool fps | x fps | pip e2e p50/p95 ms | cool e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.12 | 3.12 | 1.000 | 307/441 | 309/440 |
| 2x1 | 6.07 | 6.09 | 1.004 | 307/446 | 307/439 |
| 4x1 | 11.78 | 11.80 | 1.002 | 308/447 | 308/444 |
| 8x1 | 21.82 | 21.78 | 0.998 | 319/462 | 322/460 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | pip ms | cool ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 59.599 | 63.428 | 0.94 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.762 | 3.670 | 1.03 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.394 | 0.385 | 1.02 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 15.985 | 16.018 | 1.00 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.622 | 0.630 | 0.99 | NO |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.785 | 8.619 | 0.56 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.660 | 2.101 | 1.27 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.933 | 6.091 | 0.97 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.683 | 1.309 | 1.29 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.794 | 0.464 | 1.71 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.231 | 0.147 | 1.56 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.487 | 2.644 | 0.94 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.259 | 5.205 | 1.01 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.072 | 0.96 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.662 | 1.661 | 1.00 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.470 | 3.089 | 2.42 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.661 | 0.628 | 1.05 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 7.094 | 6.296 | 1.13 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.697 | 2.663 | 1.01 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.287 | 1.385 | 1.65 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.041 | 0.037 | 1.13 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.076 | 0.060 | 1.26 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.724 | 2.754 | 0.99 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.310 | 1.409 | 0.93 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.488 | 3.335 | 0.75 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 70.477 | 70.718 | 1.00 | yes |
| 8 | imdecode_jpeg_12MP | 4096x3072 | 60.116 | 62.162 | 0.97 | yes |
| 8 | cvtColor_BGR2GRAY | 4096x3072x3 | 0.525 | 0.529 | 0.99 | yes |
| 8 | resize_AREA_grey_x0.5 | 4096x3072 | 0.546 | 0.100 | 5.44 | yes |
| 8 | resize_AREA_grey_x0.3 | 4096x3072 | 3.108 | 3.078 | 1.01 | yes |
| 8 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.155 | 0.155 | 1.00 | NO |
| 8 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 0.608 | 1.193 | 0.51 | NO |
| 8 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 0.365 | 0.318 | 1.15 | NO |
| 8 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 0.754 | 0.772 | 0.98 | yes |
| 8 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.484 | 0.500 | 0.97 | yes |
| 8 | erode_7x7_u8 | 1273x1800 | 0.806 | 0.466 | 1.73 | yes |
| 8 | erode_5x5_u8_ROI | 2000x500 | 0.230 | 0.151 | 1.52 | yes |
| 8 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 0.322 | 0.344 | 0.94 | yes |
| 8 | GaussianBlur_f32_sigma4 | 2000x500 | 5.313 | 5.281 | 1.01 | yes |
| 8 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.069 | 0.072 | 0.96 | yes |
| 8 | dilate_f32_rect | 2000x500 k=17 | 1.706 | 1.713 | 1.00 | yes |
| 8 | medianBlur_u8_k15 | 318x450 | 7.467 | 1.186 | 6.29 | yes |
| 8 | morphologyEx_close_ellipse | 1273x1800 | 0.262 | 0.267 | 0.98 | yes |
| 8 | connectedComponentsWithStats | 1273x1800 | - | - | - | FAILED: A: ok; B: child rc=-6 (crash): Fatal glibc error: malloc.c:2599 (sysmalloc): assertion failed: (old_top == ini |
| 8 | ximgproc_thinning | 1884x204 | 2.652 | 2.753 | 0.96 | yes |
| 8 | distanceTransform_L2_precise | 1884x204 | 0.353 | 0.265 | 1.33 | yes |
| 8 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.016 | 0.017 | 0.97 | yes |
| 8 | findContours_CCOMP | 1884x204 | 0.086 | 0.068 | 1.27 | yes |
| 8 | Laplacian_f32 | 1273x1800 | 0.440 | 0.447 | 0.98 | yes |
| 8 | findHomography_RANSAC | 112 pts | 1.309 | 1.412 | 0.93 | NO |
| 8 | pipeline_bg_map_f32 | 2000x500 | 2.311 | 2.189 | 1.06 | yes |
| 8 | pipeline_detect_board | 4096x3072 (real photo) | 24.125 | 20.954 | 1.15 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | pip ms | cool ms | x |
|---|---:|---:|---:|---:|
| py._detect_board | 15 | 1143.3 | 1142.1 | 1.00 |
| py._noise_sigma | 14 | 1094.1 | 1081.2 | 1.01 |
| py._locate_cracks | 14 | 961.6 | 891.8 | 1.08 |
| cv2.resize | 194 | 794.0 | 768.7 | 1.03 |
| py._measure_roi | 68 | 773.1 | 776.5 | 1.00 |
| cv2.aruco.CharucoDetector.detectBoard | 15 | 730.0 | 738.0 | 0.99 |
| cv2.warpPerspective | 192 | 408.7 | 448.9 | 0.91 |
| py._bg_map | 82 | 364.5 | 317.3 | 1.15 |
| py._edge_sigma | 14 | 238.3 | 249.9 | 0.95 |
| py.thinning_shim | 160 | 198.4 | 198.1 | 1.00 |
| py._extract_roi | 68 | 168.6 | 168.2 | 1.00 |
| cv2.GaussianBlur | 218 | 156.1 | 159.1 | 0.98 |
| py._match_specimens | 14 | 147.6 | 148.6 | 0.99 |
| cv2.connectedComponentsWithStats | 54 | 128.6 | 116.3 | 1.11 |
| py._longest_path | 160 | 127.8 | 129.7 | 0.99 |
| cv2.medianBlur | 82 | 111.0 | 64.5 | 1.72 |
| cv2.filter2D | 14 | 92.0 | 92.6 | 0.99 |
| cv2.Sobel | 28 | 58.9 | 63.5 | 0.93 |
| cv2.cvtColor | 15 | 55.0 | 52.9 | 1.04 |
| cv2.Laplacian | 15 | 54.7 | 58.5 | 0.94 |
| py._fwhm | 80 | 48.2 | 48.3 | 1.00 |
| cv2.erode | 110 | 47.4 | 28.8 | 1.65 |
| cv2.magnitude | 14 | 32.5 | 32.7 | 0.99 |
| cv2.dilate | 82 | 30.4 | 24.9 | 1.22 |
| py._black_core | 40 | 30.4 | 30.4 | 1.00 |
| cv2.distanceTransform | 40 | 21.7 | 14.4 | 1.51 |
| py.gate.assess | 14 | 15.9 | 15.9 | 1.00 |
| cv2.polylines | 68 | 13.3 | 13.1 | 1.02 |
| cv2.morphologyEx | 14 | 9.2 | 9.3 | 0.99 |
| cv2.findHomography | 42 | 7.5 | 8.6 | 0.88 |
| py._smooth_resample | 40 | 4.4 | 4.5 | 0.99 |
| py._station_widths | 40 | 3.6 | 3.7 | 0.97 |
| cv2.cornerSubPix | 14 | 3.5 | 3.5 | 0.99 |
| cv2.fillConvexPoly | 14 | 3.0 | 3.1 | 0.95 |
| cv2.findContours | 40 | 2.2 | 2.2 | 1.02 |
| cv2.remap | 80 | 1.8 | 1.9 | 0.93 |
| py._pose_obliquity | 14 | 1.5 | 1.6 | 0.91 |
| py._uncertainty | 40 | 1.5 | 1.5 | 0.98 |
| cv2.copyMakeBorder | 160 | 1.3 | 1.6 | 0.82 |
| cv2.solvePnP | 14 | 0.7 | 0.8 | 0.85 |

Top 5 OpenCV calls by time in pip (per-call speedup pip/cool):

- cv2.resize: 794 ms -> 769 ms over 194 calls, 1.03x
- cv2.aruco.CharucoDetector.detectBoard: 730 ms -> 738 ms over 15 calls, 0.99x
- cv2.warpPerspective: 409 ms -> 449 ms over 192 calls, 0.91x
- cv2.GaussianBlur: 156 ms -> 159 ms over 218 calls, 0.98x
- cv2.connectedComponentsWithStats: 129 ms -> 116 ms over 54 calls, 1.11x

Accuracy invariance: NOT bitwise identical: 1266 of 5472 leaves differ in 18 of 43 inputs; max |dw| of the reported crack width_mm = 2.990e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 2.178e+00 mm, over all numeric fields 2.178e+00.
- crack width differences over 120 cracks: max 2.990e-02 mm, P99 1.861e-02 mm, mean 8.250e-04 mm (82 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 120 cracks with a known width: pip mean |e| 0.1196 mm (median 0.0600, P95 0.4947, bias -0.0343); cool mean |e| 0.1201 mm (median 0.0600, P95 0.5231, bias -0.0344); paired mean(|e_cool| - |e_pip|) = +0.00052 mm [95% CI -0.00002, +0.00126]; cracks certified 59 vs 58
- canonical sha256: pip 11b309ac9f1abacb..., cool 3cb998050814777d...
- unrounded internal measurement scalars differing: 683 (max |d| 5.285e-01)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 204/218, cv2.Rodrigues 14/14, cv2.connectedComponentsWithStats 37/54, cv2.copyMakeBorder 37/160, cv2.dilate 68/82, cv2.distanceTransform 26/40, cv2.findContours 26/40, cv2.findHomography 42/42, cv2.medianBlur 82/82, cv2.morphologyEx 11/14, cv2.polylines 1/68, cv2.remap 40/80, cv2.resize 178/194, cv2.solvePnP 14/14, cv2.warpPerspective 96/192, cv2.ximgproc.thinning 27/160, py._bg_map 82/82, py._black_core 40/40, py._edge_sigma 14/14, py._extract_roi 68/68, py._fwhm 80/80, py._locate_cracks 11/14, py._longest_path 24/160, py._match_specimens 3/14, py._measure_roi 40/68, py._pose_obliquity 9/14, py._smooth_resample 21/40, py._station_widths 40/40, py._uncertainty 40/40
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00440.jpg', 'cracks.C7.estimators.profile_ink', '0x1.f9eecbfb15b57p+2', '0x1.42ab367a0f909p+3', 2.1781999999999995]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.723886594af4fp+2', '0x1.ec37b4a2339c1p+2', 1.9062000000000001]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.723d70a3d70a4p+2', '0x1.ec395810624ddp+2', 1.9059999999999997]; ['synth/synth_00440.jpg', 'cracks.C7.quality.disagree_rel', '0x1.0fa786c22680ap+2', '0x1.74d1b71758e22p+2', 1.5807000000000002]; ['synth/synth_00280.jpg', 'cracks.C5.length_mm', '0x1.3000000000000p+3', '0x1.4000000000000p+3', 0.5]
