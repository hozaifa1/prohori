| pair | bitwise identical | leaves differing | cracks with |dw| > 0 at 0.0001 mm | max / P99 / mean abs(dw) mm | certification flips | first differing OpenCV call | mean abs error vs truth, A / B (mm) | paired mean abs-error change B-A [95% CI] (mm) |
|---|---|---|---|---|---|---|---|---|
| pip vs self-built 5.0.0 | no | 2449 / 10183 | 159 / 220 | 3.0e-02 / 5.8e-03 / 6.7e-04 | 0 | cv2.findHomography | 0.1218 / 0.1220 | +0.00016 [-0.00013, +0.00056] |
| self-built 5.0.0 vs 5.x snapshot (KleidiCV off) | **yes** | 0 / 10182 | 0 / 220 | 0.0e+00 / 0.0e+00 / 0.0e+00 | 0 | None | 0.1220 / 0.1220 | +0.00000 [+0.00000, +0.00000] |
| snapshot KleidiCV off vs on | no | 203 / 10182 | 6 / 220 | 3.0e-04 / 1.0e-04 / 3.6e-06 | 0 | cv2.warpPerspective | 0.1220 / 0.1220 | +0.00000 [-0.00000, +0.00000] |
| pip: numpy thinning shim vs native ximgproc | **yes** | 0 / 10183 | 0 / 220 | 0.0e+00 / 0.0e+00 / 0.0e+00 | 0 | None | 0.1218 / 0.1218 | +0.00000 [+0.00000, +0.00000] |
| pip vs COOL | no | 2391 / 10184 | 154 / 220 | 3.0e-02 / 1.5e-02 / 7.2e-04 | 1 | cv2.findHomography | 0.1218 / 0.1219 | +0.00010 [-0.00024, +0.00053] |
| self-built 5.0.0 vs COOL | no | 2582 / 10183 | 157 / 220 | 1.5e-02 / 4.7e-03 / 5.3e-04 | 1 | cv2.findHomography | 0.1220 / 0.1219 | -0.00005 [-0.00026, +0.00017] |
| snapshot KleidiCV off vs COOL | no | 2582 / 10183 | 157 / 220 | 1.5e-02 / 4.7e-03 / 5.3e-04 | 1 | cv2.findHomography | 0.1220 / 0.1219 | -0.00005 [-0.00026, +0.00017] |
| snapshot KleidiCV on vs COOL | no | 2577 / 10183 | 157 / 220 | 1.5e-02 / 4.7e-03 / 5.3e-04 | 1 | cv2.findHomography | 0.1220 / 0.1219 | -0.00005 [-0.00027, +0.00017] |
