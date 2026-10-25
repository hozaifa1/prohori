### snap_kon  vs  cool   (speedup = snap_kon time / cool time; >1 means cool is faster)

| stage | snap_kon p50 ms | cool p50 ms | snap_kon p95 ms | cool p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 53.2 | 52.0 | 64.9 | 67.1 | 1.015 [0.994, 1.036] | 1.023 [0.962, 1.054] | 0.967 [0.954, 1.086] |
| detect | 69.1 | 74.1 | 84.8 | 94.5 | 0.920 [0.909, 0.933] | 0.933 [0.894, 0.947] | 0.898 [0.881, 0.917] |
| rectify | 80.8 | 78.5 | 92.5 | 90.7 | 1.028 [1.024, 1.032] | 1.029 [1.015, 1.050] | 1.020 [1.004, 1.051] |
| measure | 42.3 | 42.9 | 192.0 | 191.3 | 1.004 [1.002, 1.006] | 0.986 [0.977, 1.010] | 1.004 [1.002, 1.023] |
| other | 52.7 | 52.3 | 71.1 | 69.5 | 1.007 [1.005, 1.010] | 1.008 [1.000, 1.015] | 1.023 [0.996, 1.029] |
| analyze | 257.6 | 260.4 | 394.4 | 398.5 | 0.988 [0.984, 0.991] | 0.989 [0.960, 0.999] | 0.990 [0.987, 1.012] |
| e2e | 307.3 | 310.2 | 457.7 | 453.5 | 0.992 [0.987, 0.996] | 0.991 [0.970, 1.004] | 1.009 [0.993, 1.034] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | snap_kon | cool | speedup snap_kon/cool |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 14888 | 15292 | 0.974 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7531 | 7405 | 1.017 |
| analyze total (ms) | 22419 | 22697 | 0.988 |
| OpenCV share of analyze | 66.4 % | 67.4 % | |

Amdahl check: a 0.97x speedup of a 66 % OpenCV share predicts 0.982x end to end; even a 2x faster OpenCV would give only 1.50x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | snap_kon fps | cool fps | x fps | snap_kon e2e p50/p95 ms | cool e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x1 | 3.13 | 3.10 | 0.988 | 321/453 | 327/460 |
| 2x1 | 6.27 | 6.09 | 0.971 | 313/453 | 329/465 |
| 4x1 | 12.15 | 11.69 | 0.962 | 326/464 | 342/468 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | snap_kon ms | cool ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 63.969 | 62.909 | 1.02 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.558 | 3.729 | 0.95 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.528 | 0.526 | 1.00 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 17.775 | 16.141 | 1.10 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.751 | 0.748 | 1.00 | NO |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 8.111 | 8.636 | 0.94 | yes |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.319 | 2.113 | 1.10 | yes |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.988 | 6.115 | 0.98 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.209 | 1.113 | 1.09 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.470 | 0.460 | 1.02 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.151 | 0.148 | 1.02 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.581 | 2.636 | 0.98 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.278 | 5.274 | 1.00 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.072 | 0.99 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.799 | 1.772 | 1.02 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 3.276 | 3.092 | 1.06 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.640 | 0.639 | 1.00 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.913 | 6.339 | 1.09 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.762 | 2.761 | 1.00 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.294 | 1.393 | 1.65 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.038 | 0.037 | 1.03 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.078 | 0.060 | 1.30 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.788 | 2.776 | 1.00 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.406 | 1.413 | 1.00 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 3.284 | 3.465 | 0.95 | yes |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 67.451 | 72.512 | 0.93 | yes |
| 4 | imdecode_jpeg_12MP | 4096x3072 | 64.813 | 62.452 | 1.04 | yes |
| 4 | cvtColor_BGR2GRAY | 4096x3072x3 | 1.341 | 1.054 | 1.27 | yes |
| 4 | resize_AREA_grey_x0.5 | 4096x3072 | 0.156 | 0.150 | 1.04 | yes |
| 4 | resize_AREA_grey_x0.3 | 4096x3072 | 5.084 | 5.265 | 0.97 | yes |
| 4 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.275 | 0.276 | 1.00 | NO |
| 4 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 2.145 | 2.284 | 0.94 | yes |
| 4 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 0.631 | 0.577 | 1.09 | yes |
| 4 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 1.506 | 1.536 | 0.98 | yes |
| 4 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 0.493 | 0.467 | 1.06 | yes |
| 4 | erode_7x7_u8 | 1273x1800 | 0.473 | 0.463 | 1.02 | yes |
| 4 | erode_5x5_u8_ROI | 2000x500 | 0.154 | 0.152 | 1.01 | yes |
| 4 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 0.657 | 0.676 | 0.97 | yes |
| 4 | GaussianBlur_f32_sigma4 | 2000x500 | 5.442 | 5.450 | 1.00 | yes |
| 4 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.070 | 0.072 | 0.97 | yes |
| 4 | dilate_f32_rect | 2000x500 k=17 | 1.812 | 1.807 | 1.00 | yes |
| 4 | medianBlur_u8_k15 | 318x450 | 1.724 | 1.703 | 1.01 | yes |
| 4 | morphologyEx_close_ellipse | 1273x1800 | 0.387 | 0.385 | 1.01 | yes |
| 4 | connectedComponentsWithStats | 1273x1800 | - | - | - | FAILED: A: ok; B: child rc=-6 (crash): Fatal glibc error: malloc.c:2599 (sysmalloc): assertion failed: (old_top == ini |
| 4 | ximgproc_thinning | 1884x204 | 2.782 | 2.669 | 1.04 | yes |
| 4 | distanceTransform_L2_precise | 1884x204 | 0.707 | 0.422 | 1.68 | yes |
| 4 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.016 | 0.016 | 1.00 | yes |
| 4 | findContours_CCOMP | 1884x204 | 0.081 | 0.065 | 1.24 | yes |
| 4 | Laplacian_f32 | 1273x1800 | 0.880 | 0.882 | 1.00 | yes |
| 4 | findHomography_RANSAC | 112 pts | 1.407 | 1.414 | 1.00 | NO |
| 4 | pipeline_bg_map_f32 | 2000x500 | 2.244 | 2.580 | 0.87 | yes |
| 4 | pipeline_detect_board | 4096x3072 (real photo) | 27.714 | 26.378 | 1.05 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | snap_kon ms | cool ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6643.6 | 6518.0 | 1.02 |
| py._detect_board | 85 | 5883.8 | 6430.9 | 0.91 |
| py._locate_cracks | 77 | 5007.5 | 4900.6 | 1.02 |
| py._measure_roi | 372 | 4683.4 | 4636.0 | 1.01 |
| cv2.resize | 1065 | 4331.2 | 4168.1 | 1.04 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 3556.6 | 4202.3 | 0.85 |
| cv2.warpPerspective | 1052 | 2501.8 | 2545.6 | 0.98 |
| py._bg_map | 449 | 1820.7 | 1811.7 | 1.01 |
| py._edge_sigma | 77 | 1465.9 | 1484.6 | 0.99 |
| py.thinning_shim | 849 | 1115.2 | 1112.9 | 1.00 |
| cv2.GaussianBlur | 1196 | 918.7 | 917.8 | 1.00 |
| py._extract_roi | 372 | 901.8 | 903.1 | 1.00 |
| py._match_specimens | 77 | 828.2 | 830.1 | 1.00 |
| py._longest_path | 849 | 727.6 | 721.2 | 1.01 |
| cv2.connectedComponentsWithStats | 302 | 714.6 | 648.5 | 1.10 |
| cv2.filter2D | 77 | 558.9 | 555.1 | 1.01 |
| cv2.Sobel | 154 | 384.0 | 388.3 | 0.99 |
| cv2.medianBlur | 449 | 356.4 | 357.5 | 1.00 |
| cv2.Laplacian | 85 | 334.3 | 330.9 | 1.01 |
| cv2.cvtColor | 85 | 295.6 | 308.1 | 0.96 |
| py._fwhm | 442 | 255.6 | 258.6 | 0.99 |
| cv2.magnitude | 77 | 195.1 | 194.8 | 1.00 |
| cv2.erode | 603 | 176.4 | 175.6 | 1.00 |
| py._black_core | 221 | 165.8 | 167.4 | 0.99 |
| cv2.dilate | 449 | 150.3 | 149.9 | 1.00 |
| cv2.distanceTransform | 225 | 123.0 | 83.4 | 1.48 |
| cv2.polylines | 372 | 98.1 | 74.3 | 1.32 |
| py.gate.assess | 77 | 79.4 | 80.1 | 0.99 |
| cv2.morphologyEx | 77 | 52.1 | 52.1 | 1.00 |
| cv2.findHomography | 232 | 46.7 | 46.9 | 1.00 |
| py._smooth_resample | 222 | 28.7 | 28.5 | 1.01 |
| py._station_widths | 221 | 22.7 | 22.9 | 0.99 |
| cv2.fillConvexPoly | 77 | 17.8 | 17.6 | 1.01 |
| cv2.cornerSubPix | 77 | 17.7 | 17.7 | 1.00 |
| cv2.findContours | 221 | 17.0 | 15.4 | 1.11 |
| cv2.remap | 444 | 16.7 | 16.8 | 0.99 |
| cv2.copyMakeBorder | 849 | 11.1 | 11.2 | 1.00 |
| py._pose_obliquity | 77 | 9.2 | 9.2 | 1.00 |
| py._uncertainty | 220 | 8.9 | 8.8 | 1.01 |
| cv2.getStructuringElement | 449 | 4.9 | 4.7 | 1.04 |

Top 5 OpenCV calls by time in snap_kon (per-call speedup snap_kon/cool):

- cv2.resize: 4331 ms -> 4168 ms over 1065 calls, 1.04x
- cv2.aruco.CharucoDetector.detectBoard: 3557 ms -> 4202 ms over 85 calls, 0.85x
- cv2.warpPerspective: 2502 ms -> 2546 ms over 1052 calls, 0.98x
- cv2.GaussianBlur: 919 ms -> 918 ms over 1196 calls, 1.00x
- cv2.connectedComponentsWithStats: 715 ms -> 649 ms over 302 calls, 1.10x

Accuracy invariance: NOT bitwise identical: 2577 of 10183 leaves differ in 33 of 85 inputs; max |dw| of the reported crack width_mm = 1.550e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 3.520e-01 mm, over all numeric fields 7.080e-01.
- crack width differences over 220 cracks: max 1.550e-02 mm, P99 4.710e-03 mm, mean 5.291e-04 mm (157 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 220 cracks with a known width: snap_kon mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); cool mean |e| 0.1219 mm (median 0.0618, P95 0.4874, bias -0.0055); paired mean(|e_cool| - |e_snap_kon|) = -0.00005 mm [95% CI -0.00027, +0.00017]; cracks certified 109 vs 108
- canonical sha256: snap_kon 13dc541f8dcdda63..., cool 832d4ee68f57e79d...
- unrounded internal measurement scalars differing: 3925 (max |d| 4.357e+02)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): <call sequence length> 1/0, cv2.GaussianBlur 1112/1196, cv2.Rodrigues 70/77, cv2.connectedComponentsWithStats 240/302, cv2.contourArea 1/21, cv2.copyMakeBorder 229/849, cv2.dilate 370/448, cv2.distanceTransform 180/225, cv2.erode 18/603, cv2.findContours 179/221, cv2.findHomography 231/232, cv2.getStructuringElement 3/449, cv2.medianBlur 444/449, cv2.morphologyEx 54/77, cv2.polylines 8/372, cv2.remap 222/444, cv2.resize 966/1065, cv2.solvePnP 73/77, cv2.warpPerspective 543/1052, cv2.ximgproc.thinning 176/849, py._bg_map 448/449, py._black_core 221/221, py._edge_sigma 75/77, py._extract_roi 368/372, py._fwhm 442/442, py._locate_cracks 54/77, py._longest_path 158/849, py._match_specimens 13/77, py._measure_roi 223/371, py._pose_obliquity 43/77, py._smooth_resample 136/222, py._station_widths 221/221, py._uncertainty 220/220, py.gate.assess 1/76
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00470.jpg', 'cracks.C2.quality.dt_rel', '0x1.57886594af4f1p+2', '0x1.2a3886594af4fp+2', 0.7080000000000002]; ['synth/synth_00470.jpg', 'cracks.C2.quality.spread_rel', '0x1.6c56d5cfaacdap+2', '0x1.43d3c36113405p+2', 0.633]; ['synth/synth_00470.jpg', 'cracks.C2.quality.disagree_rel', '0x1.128f5c28f5c29p+2', '0x1.da3a29c779a6bp+1', 0.5851000000000002]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.d45a1cac08312p+2', '0x1.ec395810624ddp+2', 0.3730000000000002]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.d45f06f694467p+2', '0x1.ec37b4a2339c1p+2', 0.37260000000000026]
