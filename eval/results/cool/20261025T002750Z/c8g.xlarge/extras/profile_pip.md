### cProfile of analyze(), 85 frames, 1 OpenCV thread(s), cv2 5.0.0, thinning=shim

profiled total 24.6 s (290 ms/frame under cProfile).  Self-time share by kind: cv2 64.1 %, python 20.2 %, numpy 13.7 %, builtin 2.0 %

| # | kind | function | file:line | calls | self ms/frame | share |
|---:|---|---|---|---:|---:|---:|
| 1 | cv2 | `<resize>` |  | 1065 | 50.79 | 17.5 % |
| 2 | cv2 | `<method 'detectBoard' of 'cv2.aruco.CharucoDetector' objects>` |  | 85 | 48.91 | 16.9 % |
| 3 | cv2 | `<warpPerspective>` |  | 1052 | 27.66 | 9.5 % |
| 4 | numpy | `<method 'reduce' of 'numpy.ufunc' objects>` |  | 105299 | 16.03 | 5.5 % |
| 5 | python | `thinning_zs` | /home/ubuntu/prohori/eval/cool_compat.py:39 | 848 | 12.21 | 4.2 % |
| 6 | cv2 | `<GaussianBlur>` |  | 1196 | 10.70 | 3.7 % |
| 7 | cv2 | `<connectedComponentsWithStats>` |  | 302 | 8.41 | 2.9 % |
| 8 | numpy | `<method 'partition' of 'numpy.ndarray' objects>` |  | 6526 | 8.16 | 2.8 % |
| 9 | cv2 | `<medianBlur>` |  | 449 | 7.18 | 2.5 % |
| 10 | python | `_locate_cracks` | /home/ubuntu/prohori/src/prohori/measure.py:369 | 77 | 7.16 | 2.5 % |
| 11 | python | `_longest_path` | /home/ubuntu/prohori/src/prohori/measure.py:297 | 848 | 7.14 | 2.5 % |
| 12 | cv2 | `<filter2D>` |  | 77 | 6.47 | 2.2 % |
| 13 | python | `_measure_roi` | /home/ubuntu/prohori/src/prohori/measure.py:565 | 372 | 5.65 | 2.0 % |
| 14 | python | `_prepare` | /home/ubuntu/prohori/src/prohori/measure.py:1048 | 85 | 5.34 | 1.8 % |
| 15 | cv2 | `<Sobel>` |  | 154 | 4.91 | 1.7 % |

Top cv2 entries:

| function | file:line | calls | self ms/frame | share |
|---|---|---:|---:|---:|
| `<resize>` |  | 1065 | 50.79 | 17.5 % |
| `<method 'detectBoard' of 'cv2.aruco.CharucoDetector' objects>` |  | 85 | 48.91 | 16.9 % |
| `<warpPerspective>` |  | 1052 | 27.66 | 9.5 % |
| `<GaussianBlur>` |  | 1196 | 10.70 | 3.7 % |
| `<connectedComponentsWithStats>` |  | 302 | 8.41 | 2.9 % |
| `<medianBlur>` |  | 449 | 7.18 | 2.5 % |
| `<filter2D>` |  | 77 | 6.47 | 2.2 % |
| `<Sobel>` |  | 154 | 4.91 | 1.7 % |
| `<Laplacian>` |  | 85 | 4.04 | 1.4 % |
| `<cvtColor>` |  | 85 | 3.76 | 1.3 % |

Top python entries:

| function | file:line | calls | self ms/frame | share |
|---|---|---:|---:|---:|
| `thinning_zs` | /home/ubuntu/prohori/eval/cool_compat.py:39 | 848 | 12.21 | 4.2 % |
| `_locate_cracks` | /home/ubuntu/prohori/src/prohori/measure.py:369 | 77 | 7.16 | 2.5 % |
| `_longest_path` | /home/ubuntu/prohori/src/prohori/measure.py:297 | 848 | 7.14 | 2.5 % |
| `_measure_roi` | /home/ubuntu/prohori/src/prohori/measure.py:565 | 372 | 5.65 | 2.0 % |
| `_prepare` | /home/ubuntu/prohori/src/prohori/measure.py:1048 | 85 | 5.34 | 1.8 % |
| `bfs` | /home/ubuntu/prohori/src/prohori/measure.py:320 | 1696 | 4.80 | 1.7 % |
| `_noise_sigma` | /home/ubuntu/prohori/src/prohori/measure.py:277 | 77 | 3.94 | 1.4 % |
| `_match_once` | /home/ubuntu/prohori/src/prohori/measure.py:412 | 141 | 3.66 | 1.3 % |
| `_fwhm` | /home/ubuntu/prohori/src/prohori/measure.py:499 | 442 | 2.80 | 1.0 % |
| `_analyze` | /home/ubuntu/prohori/src/prohori/measure.py:1041 | 85 | 1.40 | 0.5 % |
