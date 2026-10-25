| OpenCV call (pipeline size) | pip 5.0.0.93 ms | 5.x snapshot, KleidiCV off | 5.x snapshot, KleidiCV on | COOL | COOL vs pip | KleidiCV on vs off | COOL vs snapshot+KleidiCV | output bytes identical (pip = COOL) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| imdecode_jpeg_12MP 4096x3072 | 59.994 | 64.923 | 63.969 | 62.909 | 0.95x | 1.01x | 1.02x | yes |
| cvtColor_BGR2GRAY 4096x3072x3 | 3.816 | 3.599 | 3.558 | 3.729 | 1.02x | 1.01x | 0.95x | yes |
| resize_AREA_grey_x0.5 4096x3072 | 0.642 | 0.604 | 0.528 | 0.526 | 1.22x | 1.14x | 1.00x | yes |
| resize_AREA_grey_x0.3 4096x3072 | 16.023 | 17.558 | 17.775 | 16.141 | 0.99x | 0.99x | 1.10x | yes |
| resize_LINEAR_f32_up 318x450->1273x1800 | 0.744 | 0.774 | 0.751 | 0.748 | 1.00x | 1.03x | 1.00x | no |
| warpPerspective_LINEAR_u8 1229x922->1273x1800 | 4.797 | 4.999 | 8.111 | 8.636 | 0.56x | 0.62x | 0.94x | no |
| warpPerspective_NEAREST_u8 1229x922->1273x1800 | 2.691 | 2.745 | 2.319 | 2.113 | 1.27x | 1.18x | 1.10x | no |
| warpPerspective_CUBIC_u8_ROI 4096x3072->2000x500 | 5.949 | 5.997 | 5.988 | 6.115 | 0.97x | 1.00x | 0.98x | yes |
| warpPerspective_NEAREST_u8_ROI_valid 4096x3072->2000x500 | 1.439 | 1.514 | 1.209 | 1.113 | 1.29x | 1.25x | 1.09x | yes |
| erode_7x7_u8 1273x1800 | 0.806 | 0.679 | 0.470 | 0.460 | 1.75x | 1.44x | 1.02x | yes |
| erode_5x5_u8_ROI 2000x500 | 0.228 | 0.200 | 0.151 | 0.148 | 1.54x | 1.32x | 1.02x | yes |
| GaussianBlur_u8_sigma0.7 1273x1800 | 2.499 | 2.621 | 2.581 | 2.636 | 0.95x | 1.02x | 0.98x | yes |
| GaussianBlur_f32_sigma4 2000x500 | 5.371 | 5.385 | 5.278 | 5.274 | 1.02x | 1.02x | 1.00x | yes |
| GaussianBlur_f32_sigma3_sigmaY0 71x220 | 0.069 | 0.071 | 0.071 | 0.072 | 0.96x | 1.00x | 0.99x | yes |
| dilate_f32_rect 2000x500 k=17 | 1.778 | 1.814 | 1.799 | 1.772 | 1.00x | 1.01x | 1.02x | yes |
| medianBlur_u8_k15 318x450 | 7.478 | 7.470 | 3.276 | 3.092 | 2.42x | 2.28x | 1.06x | yes |
| morphologyEx_close_ellipse 1273x1800 | 0.634 | 0.650 | 0.640 | 0.639 | 0.99x | 1.02x | 1.00x | yes |
| connectedComponentsWithStats 1273x1800 | 6.970 | 6.913 | 6.913 | 6.339 | 1.10x | 1.00x | 1.09x | yes |
| ximgproc_thinning 1884x204 | 2.826 | 2.771 | 2.762 | 2.761 | 1.02x | 1.00x | 1.00x | yes |
| distanceTransform_L2_precise 1884x204 | 2.310 | 2.269 | 2.294 | 1.393 | 1.66x | 0.99x | 1.65x | yes |
| remap_f32_LINEAR_profiles 71x220 from 2000x500 | 0.041 | 0.039 | 0.038 | 0.037 | 1.13x | 1.02x | 1.03x | yes |
| findContours_CCOMP 1884x204 | 0.075 | 0.078 | 0.078 | 0.060 | 1.24x | 1.00x | 1.30x | yes |
| Laplacian_f32 1273x1800 | 2.762 | 2.795 | 2.788 | 2.776 | 0.99x | 1.00x | 1.00x | yes |
| findHomography_RANSAC 112 pts | 1.307 | 1.400 | 1.406 | 1.413 | 0.93x | 1.00x | 1.00x | no |
| pipeline_bg_map_f32 2000x500 | 2.579 | 2.652 | 3.284 | 3.465 | 0.74x | 0.81x | 0.95x | no |
| pipeline_detect_board 4096x3072 (real photo) | 75.569 | 69.031 | 67.451 | 72.512 | 1.04x | 1.02x | 0.93x | yes |
