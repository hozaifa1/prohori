# Panel photo results (2026-10-19)

Photos: 29.  Board found (>= 6 corners, valid homography): **23/29** (79 %).  At least one crack measured: **22/29**.  Crack measurements: 168 (of which 1 via `gt_roi` fallback).

Gate: fitted CRC gate (gate_params.json).  Final width = blended profile estimator (see `measure.py`), global bias correction = 0.000 mm, INK_RATIO = 0.90.  Certification is per crack (`crack_certified`): mask QA and the CRC-calibrated score at alpha = 0.05; `uncertainty_mm` is the half-width of the conformal 90 % interval.

**Caveat: the estimator parameters (INK_RATIO, blend) were tuned in-sample on these photos, and the gate and interval were fitted on degradations of these same photos, so every number above the out-of-sample section is an in-sample number.**

## Estimators (all measurements)

| estimator | MAE mm | mean signed err mm | RMSE mm |
|---|---|---|---|
| FINAL (blended) | 0.101 | -0.046 | 0.189 |
| dt (2*DT-1px, half-max mask) | 0.143 | -0.030 | 0.204 |
| profile / own plateau | 0.147 | 0.000 | 0.207 |
| profile / board ink | 0.188 | -0.141 | 0.298 |
| FWHM | 0.129 | 0.050 | 0.191 |

## Per nominal width (final estimator; all / certified only)

| nominal mm | n | mean signed err | MAE | n cert | mean signed err cert | MAE cert | mean half-width | inside 90 % interval (cert) |
|---|---|---|---|---|---|---|---|---|
| 0.30 | 22 | 0.058 | 0.065 | 5 | -0.000 | 0.017 | 0.089 | 1.00 |
| 0.40 | 22 | 0.064 | 0.066 | 4 | 0.011 | 0.024 | 0.130 | 1.00 |
| 0.50 | 22 | 0.028 | 0.043 | 0 | n/a | n/a | 0.155 | n/a |
| 0.75 | 22 | 0.025 | 0.042 | 19 | 0.028 | 0.037 | 0.083 | 0.95 |
| 1.00 | 21 | -0.063 | 0.085 | 14 | 0.007 | 0.026 | 0.141 | 1.00 |
| 1.50 | 21 | -0.078 | 0.088 | 16 | -0.021 | 0.034 | 0.205 | 1.00 |
| 2.00 | 19 | -0.255 | 0.255 | 13 | -0.077 | 0.078 | 0.425 | 1.00 |
| 3.00 | 19 | -0.194 | 0.200 | 14 | -0.068 | 0.076 | 0.242 | 1.00 |

## Certified vs uncertified (final estimator)

| group | photos | measurements | MAE mm | mean signed err | rel. MAE |
|---|---|---|---|---|---|
| certified | 19 | 85 | 0.045 | -0.019 | 3.6 % |
| uncertified | 22 | 83 | 0.159 | -0.073 | 18.3 % |
| certified, width >= 0.5 mm | 19 | 76 | 0.048 | -0.022 | 3.3 % |
| certified, width < 0.5 mm | 6 | 9 | 0.020 | 0.005 | 5.8 % |

## Gate reasons (capture level: photos)

`certified`: 19, `too_few_corners`: 7, `unstable_width`: 3

Crack level (flagged measurements): `blurry`: 4, `too_few_corners`: 4, `unstable_width`: 79

## Conformal 90 % interval on these photos (in-sample: calibrated on degradations of them)

| nominal mm | n | covered | certified n | certified covered |
|---|---|---|---|---|
| 0.30 | 22 | 1.00 | 5 | 1.00 |
| 0.40 | 22 | 1.00 | 4 | 1.00 |
| 0.50 | 22 | 0.95 | 0 | n/a |
| 0.75 | 22 | 0.91 | 19 | 0.89 |
| 1.00 | 21 | 0.90 | 14 | 1.00 |
| 1.50 | 21 | 1.00 | 16 | 1.00 |
| 2.00 | 19 | 1.00 | 13 | 1.00 |
| 3.00 | 19 | 1.00 | 14 | 1.00 |

All: 0.970 covered of 168.  For held-out numbers (grouped by source photo) see `gate_report.md`.

Certified-but-wrong (|err| > max(0.05 mm, 10 %)) on these photos: **2 of 85 certified** (2 of 168 measured) - in-sample.

## Out-of-sample estimator accuracy (leave-one-photo-out)

Parameters tuned in-sample: `ink_ratio`, blend switch points `d0`, `q0` (grid in `eval/gate_lopo.py`).  The default column uses the shipped values (tuned on all photos); the LOPO column re-tunes on the sharp, frontal photos (those passing the legacy hand-set gate) **other than** the photo being measured and applies the result to it.

| subset | n cracks | MAE default (in-sample) | MAE LOPO (out-of-sample) | bias default | bias LOPO |
|---|---|---|---|---|---|
| all measured | 168 | 0.101 | 0.104 | -0.046 | -0.070 |
| legacy-gate photos (the tuning set) | 70 | 0.037 | 0.037 | 0.006 | -0.006 |
| not legacy-gate photos | 98 | 0.148 | 0.152 | -0.083 | -0.116 |
| certified by the fitted gate | 85 | 0.045 | 0.048 | -0.019 | -0.030 |
| certified, width < 0.5 mm | 9 | 0.020 | 0.026 | 0.005 | -0.021 |
| certified, width >= 0.5 mm | 76 | 0.048 | 0.050 | -0.022 | -0.032 |

Shipped: ink_ratio 0.90, d0 5.0, q0 0.50.  In-sample grid optimum: ink_ratio 0.98, d0 4.0, q0 0.40.  LOPO choices over 22 folds: ink_ratio [0.94, 0.96, 0.98, 1.0], d0 [4.0, 5.0], q0 [0.4].

Gate out-of-sample (every source photo held out once, whole gate pipeline refitted without it; details in `gate_report.md`): original photos (v0): certified 53.0%, P(wrong | certified) 7.9%, 90 % interval coverage 92.9%; all derived captures: certified 38.3%, P(wrong | certified) 11.3%, 90 % interval coverage 92.1%

## Timing (ms, 12 MP images)

All photos: median 1517, max 2125.  Photos with a board: median 1716, mean 1660, max 2125.  Stage medians (board photos): detect 114, rectify 356, measure 929.

## Cleanest overlays (certified, >= 7 generic cracks, lowest mean relative error)

- `IMG20261019080703.jpg`: 8 cracks, mean relative error 1.7 %  ->  `data/processed/IMG20261019080703_overlay.jpg`
- `IMG20261019080657.jpg`: 8 cracks, mean relative error 2.0 %  ->  `data/processed/IMG20261019080657_overlay.jpg`
- `IMG20261019080712.jpg`: 8 cracks, mean relative error 3.0 %  ->  `data/processed/IMG20261019080712_overlay.jpg`
- `IMG20261019080716.jpg`: 8 cracks, mean relative error 3.5 %  ->  `data/processed/IMG20261019080716_overlay.jpg`
- `IMG20261019080711.jpg`: 8 cracks, mean relative error 4.1 %  ->  `data/processed/IMG20261019080711_overlay.jpg`
- `IMG20261019080706.jpg`: 8 cracks, mean relative error 6.7 %  ->  `data/processed/IMG20261019080706_overlay.jpg`

## Per photo

| photo | corners | px/mm | obliq | blur_var | sigma mm | glare | cracks | certified | reasons | ms |
|---|---|---|---|---|---|---|---|---|---|---|
| IMG20261019080657.jpg | 24 | 10.83 | 19.39 | 301.7 | 0.104 | 0.0 | 8 | yes |  | 2114 |
| IMG20261019080703.jpg | 24 | 13.01 | 8.12 | 244.5 | 0.087 | 0.0 | 8 | yes |  | 2003 |
| IMG20261019080706.jpg | 24 | 14.74 | 0.82 | 183.7 | 0.085 | 0.0 | 8 | yes |  | 2031 |
| IMG20261019080709.jpg | 24 | 13.62 | 8.98 | 158.9 | 0.076 | 0.0 | 8 | yes |  | 2059 |
| IMG20261019080711.jpg | 24 | 12.7 | 8.1 | 196.0 | 0.093 | 0.0 | 8 | yes |  | 2125 |
| IMG20261019080712.jpg | 24 | 12.71 | 9.02 | 162.2 | 0.09 | 0.0 | 8 | yes |  | 2058 |
| IMG20261019080716.jpg | 24 | 11.16 | 21.79 | 358.8 | 0.089 | 0.0 | 8 | yes |  | 1940 |
| IMG20261019080719.jpg | 24 | 13.87 | 14.57 | 367.4 | 0.083 | 0.0 | 7 | yes |  | 1502 |
| IMG20261019080722.jpg | 18 | 17.67 | 1.74 | 120.7 | 0.067 | 0.0 | 8 | yes |  | 1862 |
| IMG20261019080725.jpg | 0 | 0.0 | 0.0 | 319.5232238769531 | 0.0 | 0.0 | 0 | no | too_few_corners | 135 |
| IMG20261019080728.jpg | 0 | 0.0 | 0.0 | 290.5491638183594 | 0.0 | 0.0 | 0 | no | too_few_corners | 117 |
| IMG20261019080733.jpg | 0 | 0.0 | 0.0 | 338.9153137207031 | 0.0 | 0.0 | 0 | no | too_few_corners | 95 |
| IMG20261019080735.jpg | 0 | 0.0 | 0.0 | 518.2440795898438 | 0.0 | 0.0 | 0 | no | too_few_corners | 111 |
| IMG20261019080737.jpg | 16 | 15.79 | 4.49 | 155.8 | 0.071 | 0.0 | 7 | yes |  | 1472 |
| IMG20261019080739.jpg | 24 | 15.16 | 3.9 | 137.4 | 0.079 | 0.0 | 4 | yes |  | 1188 |
| IMG20261019080746.jpg | 19 | 16.28 | 32.55 | 105.1 | 0.079 | 0.0 | 8 | yes |  | 1830 |
| IMG20261019080751.jpg | 24 | 19.06 | 27.76 | 91.5 | 0.163 | 0.0 | 6 | yes |  | 1501 |
| IMG20261019080759.jpg | 24 | 15.35 | 22.69 | 119.7 | 0.106 | 0.0 | 8 | yes |  | 1517 |
| IMG20261019080802_BURST000_COVER.jpg | 9 | 14.99 | 39.6 | 89.1 | 0.316 | 0.0 | 8 | no | unstable_width | 1716 |
| IMG20261019080802_BURST001.jpg | 9 | 14.77 | 39.46 | 88.6 | 0.307 | 0.0 | 8 | no | unstable_width | 1682 |
| IMG20261019080807.jpg | 23 | 9.96 | 42.45 | 44.2 | 0.296 | 0.0 | 8 | no | unstable_width | 1437 |
| IMG20261019080812.jpg | 6 | 0.0 | 0.0 | 31.03839683532715 | 0.0 | 0.0 | 0 | no | too_few_corners | 98 |
| IMG20261019080815.jpg | 24 | 11.74 | 14.56 | 115.8 | 0.098 | 0.0 | 8 | yes |  | 1455 |
| IMG20261019080817.jpg | 24 | 13.94 | 10.21 | 85.7 | 0.137 | 0.0 | 8 | yes |  | 1520 |
| IMG20261019080819.jpg | 24 | 16.16 | 7.7 | 76.1 | 0.185 | 0.0 | 8 | yes |  | 1766 |
| IMG20261019080820.jpg | 18 | 18.05 | 6.34 | 73.5 | 0.212 | 0.0 | 8 | yes |  | 1806 |
| IMG20261019080823.jpg | 0 | 0.0 | 0.0 | 20.180233001708984 | 0.0 | 0.0 | 0 | no | too_few_corners | 80 |
| IMG20261019080826.jpg | 0 | 0.0 | 0.0 | 23.15915870666504 | 0.0 | 0.0 | 0 | no | too_few_corners | 96 |
| IMG20261019080841.jpg | 24 | 13.7 | 5.55 | 107.0 | 0.104 | 0.0 | 8 | yes |  | 1489 |
