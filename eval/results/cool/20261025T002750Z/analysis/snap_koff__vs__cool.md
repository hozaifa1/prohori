### snap_koff  vs  cool   (speedup = snap_koff time / cool time; >1 means cool is faster)

| stage | snap_koff p50 ms | cool p50 ms | snap_koff p95 ms | cool p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 52.4 | 52.0 | 66.2 | 67.1 | 1.003 [0.989, 1.016] | 1.008 [0.946, 1.025] | 0.987 [0.958, 1.034] |
| detect | 68.9 | 74.1 | 84.8 | 94.5 | 0.919 [0.907, 0.931] | 0.930 [0.891, 0.946] | 0.898 [0.877, 0.910] |
| rectify | 83.9 | 78.5 | 97.9 | 90.7 | 1.071 [1.067, 1.075] | 1.069 [1.058, 1.091] | 1.080 [1.057, 1.086] |
| measure | 43.1 | 42.9 | 190.3 | 191.3 | 1.004 [1.000, 1.008] | 1.005 [0.980, 1.036] | 0.995 [0.973, 1.013] |
| other | 53.8 | 52.3 | 71.9 | 69.5 | 1.031 [1.027, 1.034] | 1.029 [1.011, 1.057] | 1.034 [1.014, 1.055] |
| analyze | 261.4 | 260.4 | 399.3 | 398.5 | 1.003 [1.000, 1.006] | 1.004 [0.983, 1.022] | 1.002 [0.997, 1.021] |
| e2e | 311.8 | 310.2 | 460.9 | 453.5 | 1.003 [0.999, 1.007] | 1.005 [0.982, 1.016] | 1.016 [1.003, 1.021] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | snap_koff | cool | speedup snap_koff/cool |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15303 | 15292 | 1.001 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7458 | 7405 | 1.007 |
| analyze total (ms) | 22761 | 22697 | 1.003 |
| OpenCV share of analyze | 67.2 % | 67.4 % | |

Amdahl check: a 1.00x speedup of a 67 % OpenCV share predicts 1.000x end to end; even a 2x faster OpenCV would give only 1.51x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | snap_koff fps | cool fps | x fps | snap_koff e2e p50/p95 ms | cool e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 4x1 | 11.71 | 11.69 | 0.998 | 337/472 | 342/468 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | snap_koff ms | cool ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 64.923 | 62.909 | 1.03 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.599 | 3.729 | 0.97 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.604 | 0.526 | 1.15 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 17.558 | 16.141 | 1.09 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.774 | 0.748 | 1.03 | NO |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.999 | 8.636 | 0.58 | NO |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.745 | 2.113 | 1.30 | NO |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.997 | 6.115 | 0.98 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.514 | 1.113 | 1.36 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.679 | 0.460 | 1.48 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.200 | 0.148 | 1.35 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.621 | 2.636 | 0.99 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.385 | 5.274 | 1.02 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.072 | 0.99 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.814 | 1.772 | 1.02 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.470 | 3.092 | 2.42 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.650 | 0.639 | 1.02 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.913 | 6.339 | 1.09 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.771 | 2.761 | 1.00 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.269 | 1.393 | 1.63 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.039 | 0.037 | 1.05 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.078 | 0.060 | 1.30 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.795 | 2.776 | 1.01 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.400 | 1.413 | 0.99 | NO |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.652 | 3.465 | 0.77 | NO |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 69.031 | 72.512 | 0.95 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | snap_koff ms | cool ms | x |
|---|---:|---:|---:|---:|
| py._noise_sigma | 77 | 6708.8 | 6518.0 | 1.03 |
| py._detect_board | 85 | 5942.6 | 6430.9 | 0.92 |
| py._locate_cracks | 77 | 5346.7 | 4900.6 | 1.09 |
| py._measure_roi | 372 | 4689.7 | 4636.0 | 1.01 |
| cv2.resize | 1065 | 4428.2 | 4168.1 | 1.06 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 3579.4 | 4202.3 | 0.85 |
| cv2.warpPerspective | 1052 | 2454.3 | 2545.6 | 0.96 |
| py._bg_map | 449 | 2085.0 | 1811.7 | 1.15 |
| py._edge_sigma | 77 | 1493.5 | 1484.6 | 1.01 |
| py.thinning_shim | 849 | 1117.3 | 1112.9 | 1.00 |
| cv2.GaussianBlur | 1196 | 926.7 | 917.8 | 1.01 |
| py._extract_roi | 372 | 923.7 | 903.1 | 1.02 |
| py._match_specimens | 77 | 830.7 | 830.1 | 1.00 |
| py._longest_path | 849 | 738.2 | 721.2 | 1.02 |
| cv2.connectedComponentsWithStats | 302 | 719.9 | 648.5 | 1.11 |
| cv2.medianBlur | 449 | 608.8 | 357.5 | 1.70 |
| cv2.filter2D | 77 | 555.8 | 555.1 | 1.00 |
| cv2.Sobel | 154 | 380.1 | 388.3 | 0.98 |
| cv2.Laplacian | 85 | 337.4 | 330.9 | 1.02 |
| cv2.cvtColor | 85 | 303.4 | 308.1 | 0.98 |
| py._fwhm | 442 | 256.5 | 258.6 | 0.99 |
| cv2.erode | 603 | 235.2 | 175.6 | 1.34 |
| cv2.magnitude | 77 | 195.5 | 194.8 | 1.00 |
| cv2.dilate | 449 | 169.1 | 149.9 | 1.13 |
| py._black_core | 221 | 166.9 | 167.4 | 1.00 |
| cv2.distanceTransform | 225 | 122.9 | 83.4 | 1.47 |
| cv2.polylines | 372 | 90.6 | 74.3 | 1.22 |
| py.gate.assess | 77 | 80.9 | 80.1 | 1.01 |
| cv2.morphologyEx | 77 | 52.5 | 52.1 | 1.01 |
| cv2.findHomography | 232 | 46.5 | 46.9 | 0.99 |
| py._smooth_resample | 222 | 28.9 | 28.5 | 1.02 |
| py._station_widths | 221 | 23.0 | 22.9 | 1.01 |
| cv2.fillConvexPoly | 77 | 17.9 | 17.6 | 1.02 |
| cv2.cornerSubPix | 77 | 17.7 | 17.7 | 1.00 |
| cv2.remap | 444 | 17.4 | 16.8 | 1.04 |
| cv2.findContours | 221 | 17.3 | 15.4 | 1.13 |
| cv2.copyMakeBorder | 849 | 11.7 | 11.2 | 1.05 |
| py._pose_obliquity | 77 | 9.2 | 9.2 | 1.00 |
| py._uncertainty | 220 | 9.0 | 8.8 | 1.01 |
| cv2.getStructuringElement | 449 | 5.3 | 4.7 | 1.11 |

Top 5 OpenCV calls by time in snap_koff (per-call speedup snap_koff/cool):

- cv2.resize: 4428 ms -> 4168 ms over 1065 calls, 1.06x
- cv2.aruco.CharucoDetector.detectBoard: 3579 ms -> 4202 ms over 85 calls, 0.85x
- cv2.warpPerspective: 2454 ms -> 2546 ms over 1052 calls, 0.96x
- cv2.GaussianBlur: 927 ms -> 918 ms over 1196 calls, 1.01x
- cv2.connectedComponentsWithStats: 720 ms -> 649 ms over 302 calls, 1.11x

Accuracy invariance: NOT bitwise identical: 2582 of 10183 leaves differ in 33 of 85 inputs; max |dw| of the reported crack width_mm = 1.550e-02 mm, over all mm-valued fields (widths, estimators, uncertainties, lengths) 3.520e-01 mm, over all numeric fields 7.080e-01.
- crack width differences over 220 cracks: max 1.550e-02 mm, P99 4.710e-03 mm, mean 5.300e-04 mm (157 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 1; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- certification flip samples/tilted.jpg crack C5: certified True -> False, risk_ratio 0.8219 -> 0.9474 vs threshold 0.8929 (level 0.05); reasons [] -> ['unstable_width']; width 0.9003 -> 0.9002 mm
- error vs printed ground truth over 220 cracks with a known width: snap_koff mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); cool mean |e| 0.1219 mm (median 0.0618, P95 0.4874, bias -0.0055); paired mean(|e_cool| - |e_snap_koff|) = -0.00005 mm [95% CI -0.00026, +0.00017]; cracks certified 109 vs 108
- canonical sha256: snap_koff 2a3fa732f2ac5ea6..., cool 832d4ee68f57e79d...
- unrounded internal measurement scalars differing: 3931 (max |d| 4.357e+02)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- OpenCV calls whose output bytes differ (differing / total calls): <call sequence length> 1/0, cv2.GaussianBlur 1115/1196, cv2.Rodrigues 70/77, cv2.connectedComponentsWithStats 241/302, cv2.contourArea 1/21, cv2.copyMakeBorder 230/849, cv2.dilate 371/448, cv2.distanceTransform 181/225, cv2.erode 21/603, cv2.findContours 180/221, cv2.findHomography 231/232, cv2.getStructuringElement 3/449, cv2.medianBlur 445/449, cv2.morphologyEx 54/77, cv2.polylines 8/372, cv2.remap 222/444, cv2.resize 967/1065, cv2.solvePnP 73/77, cv2.warpPerspective 549/1052, cv2.ximgproc.thinning 181/849, py._bg_map 448/449, py._black_core 221/221, py._edge_sigma 77/77, py._extract_roi 368/372, py._fwhm 442/442, py._locate_cracks 54/77, py._longest_path 163/849, py._match_specimens 14/77, py._measure_roi 223/371, py._pose_obliquity 43/77, py._smooth_resample 137/222, py._station_widths 221/221, py._uncertainty 220/220, py.gate.assess 1/76
- first divergence (input, call index, function): ('raw/IMG20261019080657.jpg', 3, 'cv2.findHomography')
- worst leaf differences (input, field, A, B, |d|): ['synth/synth_00470.jpg', 'cracks.C2.quality.dt_rel', '0x1.57886594af4f1p+2', '0x1.2a3886594af4fp+2', 0.7080000000000002]; ['synth/synth_00470.jpg', 'cracks.C2.quality.spread_rel', '0x1.6c56d5cfaacdap+2', '0x1.43d3c36113405p+2', 0.633]; ['synth/synth_00470.jpg', 'cracks.C2.quality.disagree_rel', '0x1.128f5c28f5c29p+2', '0x1.da3a29c779a6bp+1', 0.5851000000000002]; ['synth/synth_00440.jpg', 'cracks.C7.estimators.q_core', '0x1.d45a1cac08312p+2', '0x1.ec395810624ddp+2', 0.3730000000000002]; ['synth/synth_00440.jpg', 'cracks.C7.quality.q_core', '0x1.d45f06f694467p+2', '0x1.ec37b4a2339c1p+2', 0.37260000000000026]
