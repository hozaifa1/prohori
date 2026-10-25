### ref  vs  snap_koff   (speedup = ref time / snap_koff time; >1 means snap_koff is faster)

| stage | ref p50 ms | snap_koff p50 ms | ref p95 ms | snap_koff p95 ms | x mean [95% CI] | x p50 [95% CI] | x p95 [95% CI] |
|---|---:|---:|---:|---:|---|---|---|
| decode | 52.6 | 52.4 | 66.3 | 66.2 | 1.000 [0.995, 1.008] | 1.004 [0.991, 1.049] | 1.002 [0.992, 1.003] |
| detect | 77.9 | 68.9 | 97.6 | 84.8 | 1.139 [1.127, 1.152] | 1.131 [1.107, 1.172] | 1.150 [1.123, 1.178] |
| rectify | 82.3 | 83.9 | 96.5 | 97.9 | 0.981 [0.978, 0.983] | 0.981 [0.966, 0.988] | 0.986 [0.961, 0.993] |
| measure | 42.4 | 43.1 | 188.5 | 190.3 | 0.990 [0.988, 0.991] | 0.984 [0.977, 0.991] | 0.990 [0.982, 1.025] |
| other | 53.2 | 53.8 | 71.1 | 71.9 | 0.993 [0.991, 0.995] | 0.988 [0.982, 1.006] | 0.990 [0.985, 1.002] |
| analyze | 268.2 | 261.4 | 408.4 | 399.3 | 1.026 [1.022, 1.029] | 1.026 [1.010, 1.046] | 1.023 [1.000, 1.030] |
| e2e | 317.6 | 311.8 | 466.3 | 460.9 | 1.022 [1.019, 1.025] | 1.019 [1.010, 1.038] | 1.012 [1.000, 1.024] |

Where the time goes (OpenCV-call time from the trace pass vs un-instrumented analyze() time of the same frames):

| | ref | snap_koff | speedup ref/snap_koff |
|---|---:|---:|---:|
| time inside OpenCV calls (ms, all frames) | 15922 | 15303 | 1.040 |
| time in Python/numpy and the rest (analyze minus OpenCV, ms) | 7427 | 7458 | 0.996 |
| analyze total (ms) | 23350 | 22761 | 1.026 |
| OpenCV share of analyze | 68.2 % | 67.2 % | |

Amdahl check: a 1.04x speedup of a 68 % OpenCV share predicts 1.027x end to end; even a 2x faster OpenCV would give only 1.52x.

Throughput / latency sweep (WxT = worker processes x cv2 threads each):

| config | ref fps | snap_koff fps | x fps | ref e2e p50/p95 ms | snap_koff e2e p50/p95 ms |
|---|---:|---:|---:|---|---|
| 1x4 | 4.53 | 4.54 | 1.003 | 208/341 | 208/339 |
| 4x1 | 11.43 | 11.71 | 1.025 | 346/483 | 337/472 |

Microbench of the exact OpenCV calls (median ms; x = A/B; bit-exact = identical output bytes):

| threads | call | size | ref ms | snap_koff ms | x | bit-exact |
|---:|---|---|---:|---:|---:|---|
| 1 | imdecode_jpeg_12MP | 4096x3072 | 64.602 | 64.923 | 1.00 | yes |
| 1 | cvtColor_BGR2GRAY | 4096x3072x3 | 3.604 | 3.599 | 1.00 | yes |
| 1 | resize_AREA_grey_x0.5 | 4096x3072 | 0.685 | 0.604 | 1.13 | yes |
| 1 | resize_AREA_grey_x0.3 | 4096x3072 | 17.543 | 17.558 | 1.00 | yes |
| 1 | resize_LINEAR_f32_up | 318x450->1273x1800 | 0.753 | 0.774 | 0.97 | yes |
| 1 | warpPerspective_LINEAR_u8 | 1229x922->1273x1800 | 4.853 | 4.999 | 0.97 | yes |
| 1 | warpPerspective_NEAREST_u8 | 1229x922->1273x1800 | 2.760 | 2.745 | 1.01 | yes |
| 1 | warpPerspective_CUBIC_u8_ROI | 4096x3072->2000x500 | 5.990 | 5.997 | 1.00 | yes |
| 1 | warpPerspective_NEAREST_u8_ROI_valid | 4096x3072->2000x500 | 1.488 | 1.514 | 0.98 | yes |
| 1 | erode_7x7_u8 | 1273x1800 | 0.674 | 0.679 | 0.99 | yes |
| 1 | erode_5x5_u8_ROI | 2000x500 | 0.201 | 0.200 | 1.01 | yes |
| 1 | GaussianBlur_u8_sigma0.7 | 1273x1800 | 2.609 | 2.621 | 1.00 | yes |
| 1 | GaussianBlur_f32_sigma4 | 2000x500 | 5.246 | 5.385 | 0.97 | yes |
| 1 | GaussianBlur_f32_sigma3_sigmaY0 | 71x220 | 0.071 | 0.071 | 1.00 | yes |
| 1 | dilate_f32_rect | 2000x500 k=17 | 1.795 | 1.814 | 0.99 | yes |
| 1 | medianBlur_u8_k15 | 318x450 | 7.501 | 7.470 | 1.00 | yes |
| 1 | morphologyEx_close_ellipse | 1273x1800 | 0.649 | 0.650 | 1.00 | yes |
| 1 | connectedComponentsWithStats | 1273x1800 | 6.913 | 6.913 | 1.00 | yes |
| 1 | ximgproc_thinning | 1884x204 | 2.772 | 2.771 | 1.00 | yes |
| 1 | distanceTransform_L2_precise | 1884x204 | 2.298 | 2.269 | 1.01 | yes |
| 1 | remap_f32_LINEAR_profiles | 71x220 from 2000x500 | 0.038 | 0.039 | 0.98 | yes |
| 1 | findContours_CCOMP | 1884x204 | 0.079 | 0.078 | 1.02 | yes |
| 1 | Laplacian_f32 | 1273x1800 | 2.786 | 2.795 | 1.00 | yes |
| 1 | findHomography_RANSAC | 112 pts | 1.410 | 1.400 | 1.01 | yes |
| 1 | pipeline_bg_map_f32 | 2000x500 | 2.640 | 2.652 | 1.00 | yes |
| 1 | pipeline_detect_board | 4096x3072 (real photo) | 76.424 | 69.031 | 1.11 | yes |

Per-function time inside analyze (trace pass, summed over images, median of reps; instrumented, so use ratios only; py.* rows are inclusive):

| function | calls | ref ms | snap_koff ms | x |
|---|---:|---:|---:|---:|
| py._detect_board | 85 | 6734.9 | 5942.6 | 1.13 |
| py._noise_sigma | 77 | 6649.7 | 6708.8 | 0.99 |
| py._locate_cracks | 77 | 5295.8 | 5346.7 | 0.99 |
| py._measure_roi | 372 | 4647.3 | 4689.7 | 0.99 |
| cv2.aruco.CharucoDetector.detectBoard | 85 | 4457.6 | 3579.4 | 1.25 |
| cv2.resize | 1065 | 4248.0 | 4428.2 | 0.96 |
| cv2.warpPerspective | 1052 | 2399.1 | 2454.3 | 0.98 |
| py._bg_map | 449 | 2072.9 | 2085.0 | 0.99 |
| py._edge_sigma | 77 | 1457.8 | 1493.5 | 0.98 |
| py.thinning_shim | 849 | 1113.5 | 1117.3 | 1.00 |
| cv2.GaussianBlur | 1196 | 925.4 | 926.7 | 1.00 |
| py._extract_roi | 372 | 922.0 | 923.7 | 1.00 |
| py._match_specimens | 77 | 828.2 | 830.7 | 1.00 |
| py._longest_path | 849 | 719.5 | 738.2 | 0.97 |
| cv2.connectedComponentsWithStats | 302 | 703.6 | 719.9 | 0.98 |
| cv2.medianBlur | 449 | 608.9 | 608.8 | 1.00 |
| cv2.filter2D | 77 | 555.5 | 555.8 | 1.00 |
| cv2.Sobel | 154 | 381.5 | 380.1 | 1.00 |
| cv2.Laplacian | 85 | 336.5 | 337.4 | 1.00 |
| cv2.cvtColor | 85 | 303.1 | 303.4 | 1.00 |
| py._fwhm | 442 | 256.7 | 256.5 | 1.00 |
| cv2.erode | 603 | 234.7 | 235.2 | 1.00 |
| cv2.magnitude | 77 | 195.4 | 195.5 | 1.00 |
| cv2.dilate | 449 | 169.2 | 169.1 | 1.00 |
| py._black_core | 221 | 166.4 | 166.9 | 1.00 |
| cv2.distanceTransform | 225 | 122.8 | 122.9 | 1.00 |
| cv2.polylines | 372 | 87.0 | 90.6 | 0.96 |
| py.gate.assess | 77 | 80.3 | 80.9 | 0.99 |
| cv2.morphologyEx | 77 | 52.4 | 52.5 | 1.00 |
| cv2.findHomography | 232 | 46.7 | 46.5 | 1.01 |
| py._smooth_resample | 222 | 28.8 | 28.9 | 0.99 |
| py._station_widths | 221 | 22.6 | 23.0 | 0.98 |
| cv2.fillConvexPoly | 77 | 17.8 | 17.9 | 1.00 |
| cv2.cornerSubPix | 77 | 17.8 | 17.7 | 1.01 |
| cv2.findContours | 221 | 17.0 | 17.3 | 0.98 |
| cv2.remap | 444 | 16.5 | 17.4 | 0.95 |
| cv2.copyMakeBorder | 849 | 11.3 | 11.7 | 0.96 |
| py._pose_obliquity | 77 | 9.3 | 9.2 | 1.01 |
| py._uncertainty | 220 | 8.9 | 9.0 | 1.00 |
| cv2.getStructuringElement | 449 | 5.1 | 5.3 | 0.96 |

Top 5 OpenCV calls by time in ref (per-call speedup ref/snap_koff):

- cv2.aruco.CharucoDetector.detectBoard: 4458 ms -> 3579 ms over 85 calls, 1.25x
- cv2.resize: 4248 ms -> 4428 ms over 1065 calls, 0.96x
- cv2.warpPerspective: 2399 ms -> 2454 ms over 1052 calls, 0.98x
- cv2.GaussianBlur: 925 ms -> 927 ms over 1196 calls, 1.00x
- cv2.connectedComponentsWithStats: 704 ms -> 720 ms over 302 calls, 0.98x

Accuracy invariance: BITWISE IDENTICAL: all 10182 numeric/string leaves of 85 results (every crack width and estimator column, gate outputs, board corners) match as float64 hex; max |dw| = 0 mm.
- crack width differences over 220 cracks: max 0.000e+00 mm, P99 0.000e+00 mm, mean 0.000e+00 mm (0 cracks differ at the 4-decimal reported precision); certification decisions flipped (cracks in both builds): 0; frames where the set of detected cracks differs: 0 []; U_ref = 0.009 mm.
- error vs printed ground truth over 220 cracks with a known width: ref mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); snap_koff mean |e| 0.1220 mm (median 0.0615, P95 0.4910, bias -0.0055); paired mean(|e_snap_koff| - |e_ref|) = +0.00000 mm [95% CI +0.00000, +0.00000]; cracks certified 109 vs 109
- canonical sha256: ref 2a3fa732f2ac5ea6..., snap_koff 2a3fa732f2ac5ea6...
- unrounded internal measurement scalars differing: 0 (max |d| 0.000e+00)
- JPEG decode output identical: True; intra-run determinism (A, B): [True, True]
- every OpenCV function output in the pipeline is byte-identical across the two builds
