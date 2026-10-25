### cProfile of analyze(), 85 frames, 1 OpenCV thread(s), cv2 5.1.0-dev, thinning=shim

profiled total 24.2 s (285 ms/frame under cProfile).  Self-time share by kind: cv2 63.9 %, python 20.2 %, numpy 13.9 %, builtin 2.0 %

| # | kind | function | file:line | calls | self ms/frame | share |
|---:|---|---|---|---:|---:|---:|
| 1 | cv2 | `<resize>` |  | 1065 | 49.59 | 17.4 % |
| 2 | cv2 | `<method 'detectBoard' of 'cv2.aruco.CharucoDetector' objects>` |  | 85 | 49.07 | 17.2 % |
| 3 | cv2 | `<warpPerspective>` |  | 1052 | 29.98 | 10.5 % |
| 4 | numpy | `<method 'reduce' of 'numpy.ufunc' objects>` |  | 105297 | 16.03 | 5.6 % |
| 5 | python | `thinning_zs` | /home/ubuntu/prohori/eval/cool_compat.py:39 | 848 | 12.23 | 4.3 % |
| 6 | cv2 | `<GaussianBlur>` |  | 1196 | 10.97 | 3.8 % |
| 7 | numpy | `<method 'partition' of 'numpy.ndarray' objects>` |  | 6526 | 8.04 | 2.8 % |
| 8 | cv2 | `<connectedComponentsWithStats>` |  | 302 | 7.65 | 2.7 % |
| 9 | python | `_longest_path` | /home/ubuntu/prohori/src/prohori/measure.py:297 | 848 | 7.13 | 2.5 % |
| 10 | python | `_locate_cracks` | /home/ubuntu/prohori/src/prohori/measure.py:369 | 77 | 7.02 | 2.5 % |
| 11 | cv2 | `<filter2D>` |  | 77 | 6.51 | 2.3 % |
| 12 | python | `_measure_roi` | /home/ubuntu/prohori/src/prohori/measure.py:565 | 372 | 5.66 | 2.0 % |
| 13 | cv2 | `<Sobel>` |  | 154 | 5.21 | 1.8 % |
| 14 | python | `_prepare` | /home/ubuntu/prohori/src/prohori/measure.py:1048 | 85 | 5.01 | 1.8 % |
| 15 | python | `bfs` | /home/ubuntu/prohori/src/prohori/measure.py:320 | 1696 | 4.77 | 1.7 % |

Top cv2 entries:

| function | file:line | calls | self ms/frame | share |
|---|---|---:|---:|---:|
| `<resize>` |  | 1065 | 49.59 | 17.4 % |
| `<method 'detectBoard' of 'cv2.aruco.CharucoDetector' objects>` |  | 85 | 49.07 | 17.2 % |
| `<warpPerspective>` |  | 1052 | 29.98 | 10.5 % |
| `<GaussianBlur>` |  | 1196 | 10.97 | 3.8 % |
| `<connectedComponentsWithStats>` |  | 302 | 7.65 | 2.7 % |
| `<filter2D>` |  | 77 | 6.51 | 2.3 % |
| `<Sobel>` |  | 154 | 5.21 | 1.8 % |
| `<medianBlur>` |  | 449 | 4.22 | 1.5 % |
| `<Laplacian>` |  | 85 | 4.08 | 1.4 % |
| `<cvtColor>` |  | 85 | 3.70 | 1.3 % |

Top python entries:

| function | file:line | calls | self ms/frame | share |
|---|---|---:|---:|---:|
| `thinning_zs` | /home/ubuntu/prohori/eval/cool_compat.py:39 | 848 | 12.23 | 4.3 % |
| `_longest_path` | /home/ubuntu/prohori/src/prohori/measure.py:297 | 848 | 7.13 | 2.5 % |
| `_locate_cracks` | /home/ubuntu/prohori/src/prohori/measure.py:369 | 77 | 7.02 | 2.5 % |
| `_measure_roi` | /home/ubuntu/prohori/src/prohori/measure.py:565 | 372 | 5.66 | 2.0 % |
| `_prepare` | /home/ubuntu/prohori/src/prohori/measure.py:1048 | 85 | 5.01 | 1.8 % |
| `bfs` | /home/ubuntu/prohori/src/prohori/measure.py:320 | 1696 | 4.77 | 1.7 % |
| `_noise_sigma` | /home/ubuntu/prohori/src/prohori/measure.py:277 | 77 | 3.89 | 1.4 % |
| `_match_once` | /home/ubuntu/prohori/src/prohori/measure.py:412 | 141 | 3.67 | 1.3 % |
| `_fwhm` | /home/ubuntu/prohori/src/prohori/measure.py:499 | 442 | 2.79 | 1.0 % |
| `_analyze` | /home/ubuntu/prohori/src/prohori/measure.py:1041 | 85 | 1.04 | 0.4 % |
