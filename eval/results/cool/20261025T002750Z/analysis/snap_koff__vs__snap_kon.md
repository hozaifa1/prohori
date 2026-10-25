### snap_koff  vs  snap_kon   (speedup = snap_koff time / snap_kon time; >1 means snap_kon is faster)

| stage | snap_koff p50 ms | snap_kon p50 ms | snap_koff p95 ms | snap_kon p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 52.4 | 53.2 | 66.2 | 64.9 | 0.988 [0.968, 1.007] | 0.985 [0.933, 1.014] | 1.020 [0.943, 1.067] |
| detect | 68.9 | 69.1 | 84.8 | 84.8 | 0.998 [0.996, 1.000] | 0.997 [0.992, 1.009] | 1.000 [0.989, 1.007] |
| rectify | 83.9 | 80.8 | 97.9 | 92.5 | 1.042 [1.038, 1.046] | 1.038 [1.024, 1.059] | 1.058 [1.021, 1.069] |
| measure | 43.1 | 42.3 | 190.3 | 192.0 | 1.000 [0.996, 1.003] | 1.019 [0.995, 1.034] | 0.991 [0.968, 1.006] |
| other | 53.8 | 52.7 | 71.9 | 71.1 | 1.023 [1.019, 1.027] | 1.021 [1.004, 1.047] | 1.011 [1.008, 1.042] |
| analyze | 261.4 | 257.6 | 399.3 | 394.4 | 1.015 [1.014, 1.017] | 1.015 [1.014, 1.031] | 1.012 [1.001, 1.018] |
| e2e | 311.8 | 307.3 | 460.9 | 457.7 | 1.011 [1.007, 1.015] | 1.014 [0.991, 1.026] | 1.007 [0.986, 1.015] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | snap_koff | snap_kon | speedup snap_koff/snap_kon |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15303 | 14888 | 1.028 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7458 | 7531 | 0.990 |
| analyze total (ms) | 22761 | 22419 | 1.015 |
| OpenCV share of analyze | 67.2 % | 66.4 % | |

Amdahl check: a 1.03x speedup of a 67 % OpenCV share predicts 1.019x end to end; even a 2x faster OpenCV would give only 1.51x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | snap_koff fps | snap_kon fps | x fps | snap_koff e2e p50/p95 ms | snap_kon e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x4 | 4.54 | 4.73 | 1.041 | 208/339 | 196/332 |
| 4x1 | 11.71 | 12.15 | 1.038 | 337/472 | 326/464 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | snap_koff ms | snap_kon ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 64.923 | 63.969 | 1.01 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.599 | 3.558 | 1.01 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.604 | 0.528 | 1.14 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 17.558 | 17.775 | 0.99 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.774 | 0.751 | 1.03 | yes |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.999 | 8.111 | 0.62 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.745 | 2.319 | 1.18 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.997 | 5.988 | 1.00 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.514 | 1.209 | 1.25 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.679 | 0.470 | 1.44 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.200 | 0.151 | 1.32 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.621 | 2.581 | 1.02 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.385 | 5.278 | 1.02 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.071 | 1.00 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.814 | 1.799 | 1.01 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.470 | 3.276 | 2.28 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.650 | 0.640 | 1.02 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.913 | 6.913 | 1.00 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.771 | 2.762 | 1.00 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.269 | 2.294 | 0.99 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.039 | 0.038 | 1.02 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.078 | 0.078 | 1.00 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.795 | 2.788 | 1.00 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.400 | 1.406 | 1.00 | yes |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.652 | 3.284 | 0.81 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 69.031 | 67.451 | 1.02 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | snap_koff ms | snap_kon ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6708.8 | 6643.6 | 1.01 |
| py._detect_board | 85 | 5942.6 | 5883.8 | 1.01 |
| py._locate_cracks | 77 | 5346.7 | 5007.5 | 1.07 |
| py._measure_roi | 372 | 4689.7 | 4683.4 | 1.00 |
| cv2.resize | 1065 | 4428.2 | 4331.2 | 1.02 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 3579.4 | 3556.6 | 1.01 |
| cv2.warpPerspective | 1052 | 2454.3 | 2501.8 | 0.98 |
| py._bg_map | 449 | 2085.0 | 1820.7 | 1.15 |
| py._edge_sigma | 77 | 1493.5 | 1465.9 | 1.02 |
| py.thinning_shim | 849 | 1117.3 | 1115.2 | 1.00 |
| cv2.GaussianBlur | 1196 | 926.7 | 918.7 | 1.01 |
| py._extract_roi | 372 | 923.7 | 901.8 | 1.02 |
| py._match_specimens | 77 | 830.7 | 828.2 | 1.00 |
| py._longest_path | 849 | 738.2 | 727.6 | 1.01 |
| cv2.connectedComponentsWithStats | 302 | 719.9 | 714.6 | 1.01 |
| cv2.medianBlur | 449 | 608.8 | 356.4 | 1.71 |
| cv2.filter2D | 77 | 555.8 | 558.9 | 0.99 |
| cv2.Sobel | 154 | 380.1 | 384.0 | 0.99 |
| cv2.Laplacian | 85 | 337.4 | 334.3 | 1.01 |
| cv2.cvtColor | 85 | 303.4 | 295.6 | 1.03 |
| py._fwhm | 442 | 256.5 | 255.6 | 1.00 |
| cv2.erode | 603 | 235.2 | 176.4 | 1.33 |
| cv2.magnitude | 77 | 195.5 | 195.1 | 1.00 |
| cv2.dilate | 449 | 169.1 | 150.3 | 1.13 |
| py._black_core | 221 | 166.9 | 165.8 | 1.01 |
| cv2.distanceTransform | 225 | 122.9 | 123.0 | 1.00 |
| cv2.polylines | 372 | 90.6 | 98.1 | 0.92 |
| py.gate.assess | 77 | 80.9 | 79.4 | 1.02 |
| cv2.morphologyEx | 77 | 52.5 | 52.1 | 1.01 |
| cv2.findHomography | 232 | 46.5 | 46.7 | 1.00 |
| py._smooth_resample | 222 | 28.9 | 28.7 | 1.01 |
| py._station_widths | 221 | 23.0 | 22.7 | 1.01 |
| cv2.fillConvexPoly | 77 | 17.9 | 17.8 | 1.01 |
| cv2.cornerSubPix | 77 | 17.7 | 17.7 | 1.00 |
| cv2.remap | 444 | 17.4 | 16.7 | 1.05 |
| cv2.findContours | 221 | 17.3 | 17.0 | 1.02 |
| cv2.copyMakeBorder | 849 | 11.7 | 11.1 | 1.06 |
| py._pose_obliquity | 77 | 9.2 | 9.2 | 1.00 |
| py._uncertainty | 220 | 9.0 | 8.9 | 1.01 |
| cv2.getStructuringElement | 449 | 5.3 | 4.9 | 1.07 |

Top 5 OpenCV calls by time in snap_koff (per-call speedup snap_koff/snap_kon):

- cv2.resize: 4428 ms -> 4331 ms over 1065 calls, 1.02x
- cv2.aruco.CharucoDetector.detectBoard: 3579 ms -> 3557 ms over 85 calls, 1.01x
- cv2.warpPerspective: 2454 ms -> 2502 ms over 1052 calls, 0.98x
- cv2.GaussianBlur: 927 ms -> 919 ms over 1196 calls, 1.01x
- cv2.connectedComponentsWithStats: 720 ms -> 715 ms over 302 calls, 1.01x

Accuracy invariance: NOT bitwise identical: 203 of 10182 leaves differ in 24 of 85 inputs; max |dw| of the reported crack width_mm = 3.000e-04 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 6.000e-04 mm, over all numeric fields 1.000e-03.
- crack width differences over 220 cracks: max 3.000e-04 mm, P99 1.000e-04 mm, mean 3.636e-06 mm (6 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 220 cracks with a known width: snap_koff mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); snap_kon mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); paired mean(|e_snap_kon| - |e_snap_koff|) = +0.00000 mm [95% CI -0.00000, +0.00000]; cracks certified 109 vs 109
- canonical sha256: snap_koff 2a3fa732f2ac5ea6..., snap_kon 13dc541f8dcdda63...
- unrounded internal measurement scalars differing: 1824 (max |d| 1.371e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): cv2.GaussianBlur 451/1196, cv2.connectedComponentsWithStats 49/302, cv2.copyMakeBorder 24/849, cv2.dilate 203/449, cv2.distanceTransform 5/225, cv2.erode 12/603, cv2.findContours 5/221, cv2.medianBlur 78/449, cv2.morphologyEx 44/77, cv2.remap 2/444, cv2.resize 191/1065, cv2.warpPerspective 167/1052, cv2.ximgproc.thinning 11/849, py._bg_map 112/449, py._black_core 181/221, py._edge_sigma 68/77, py._extract_roi 2/372, py._fwhm 186/442, py._locate_cracks 44/77, py._longest_path 6/849, py._match_specimens 5/77, py._measure_roi 181/372, py._smooth_resample 2/222, py._station_widths 147/221, py._uncertainty 180/220
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 23, 'cv2.warpPerspective')
- worst leaf differences (input, field, A, B, |d|): ['raw/IMG20261019080712.jpg', 'cracks.C3.estimators.wt_core', '0x1.b333333333333p-2', '0x1.b22d0e5604189p-2', 0.0010000000000000009]; ['raw/IMG20261019080751.jpg', 'cracks.C3.estimators.wt_core', '0x1.9db22d0e56042p-3', '0x1.9fbe76c8b4396p-3', 0.0010000000000000009]; ['samples/tilted.jpg', 'cracks.C2.estimators.wt_core', '0x1.b020c49ba5e35p-3', '0x1.b22d0e5604189p-3', 0.0010000000000000009]; ['samples/move-closer.jpg', 'cracks.C3.estimators.wt_core', '0x1.e353f7ced9168p-5', '0x1.db22d0e560419p-5', 0.000999999999999994]; ['raw/IMG20261019080706.jpg', 'cracks.C3.width_blackcore_mm', '0x1.22b6ae7d566cfp-1', '0x1.2305532617c1cp-1', 0.0006000000000000449]
