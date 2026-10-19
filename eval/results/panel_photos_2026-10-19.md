# Panel photo results (2026-10-19)

Photos: 29.  Board found (>= 6 corners, valid homography): **23/29** (79 %).  At least one crack measured: **22/29**.  Crack measurements: 168 (of which 1 via `gt_roi` fallback).

Gate thresholds: corners >= 8, px/mm >= 8, blur_var >= 150, obliquity <= 45 deg, glare <= 0.05.  Final width = blended profile estimator (see `measure.py`), global bias correction = 0.000 mm, INK_RATIO = 0.90.

## Estimators (all measurements)

| estimator | MAE mm | mean signed err mm | RMSE mm |
|---|---|---|---|
| FINAL (blended) | 0.101 | -0.048 | 0.191 |
| dt (2*DT-1px, half-max mask) | 0.142 | 0.050 | 0.207 |
| profile / own plateau | 0.149 | -0.003 | 0.210 |
| profile / board ink | 0.189 | -0.144 | 0.302 |
| FWHM | 0.131 | 0.049 | 0.194 |

## Per nominal width (final estimator; all / certified only)

| nominal mm | n | mean signed err | MAE | n cert | mean signed err cert | MAE cert | mean u | within 1u (cert) |
|---|---|---|---|---|---|---|---|---|
| 0.30 | 22 | 0.055 | 0.062 | 9 | 0.027 | 0.036 | 0.115 | 1.00 |
| 0.40 | 22 | 0.063 | 0.066 | 9 | 0.029 | 0.036 | 0.126 | 1.00 |
| 0.50 | 22 | 0.024 | 0.039 | 9 | 0.025 | 0.028 | 0.127 | 1.00 |
| 0.75 | 22 | 0.025 | 0.042 | 9 | 0.023 | 0.036 | 0.124 | 0.89 |
| 1.00 | 21 | -0.064 | 0.084 | 9 | 0.016 | 0.022 | 0.116 | 1.00 |
| 1.50 | 21 | -0.079 | 0.087 | 9 | 0.004 | 0.014 | 0.122 | 1.00 |
| 2.00 | 19 | -0.257 | 0.257 | 8 | -0.069 | 0.069 | 0.123 | 0.50 |
| 3.00 | 19 | -0.206 | 0.207 | 8 | -0.045 | 0.048 | 0.120 | 0.75 |

## Certified vs uncertified (final estimator)

| group | photos | measurements | MAE mm | mean signed err | rel. MAE |
|---|---|---|---|---|---|
| certified | 9 | 70 | 0.036 | 0.003 | 5.0 % |
| uncertified | 13 | 98 | 0.148 | -0.085 | 14.7 % |
| certified, width >= 0.5 mm | 9 | 52 | 0.035 | -0.006 | 3.1 % |
| certified, width < 0.5 mm | 9 | 18 | 0.036 | 0.028 | 10.5 % |

## Gate reasons

`blurry`: 13, `certified`: 9, `too_few_corners`: 7

## Timing (ms, 12 MP images)

All photos: median 726, max 1096.  Photos with a board: median 757, mean 792, max 1096.  Stage medians (board photos): detect 62, rectify 209, measure 508.

## Cleanest overlays (certified, >= 7 generic cracks, lowest mean relative error)

- `IMG20261019080657.jpg`: 8 cracks, mean relative error 1.6 %  ->  `data/processed/IMG20261019080657_overlay.jpg`
- `IMG20261019080703.jpg`: 8 cracks, mean relative error 1.6 %  ->  `data/processed/IMG20261019080703_overlay.jpg`
- `IMG20261019080712.jpg`: 8 cracks, mean relative error 2.5 %  ->  `data/processed/IMG20261019080712_overlay.jpg`
- `IMG20261019080711.jpg`: 8 cracks, mean relative error 3.5 %  ->  `data/processed/IMG20261019080711_overlay.jpg`
- `IMG20261019080716.jpg`: 8 cracks, mean relative error 3.8 %  ->  `data/processed/IMG20261019080716_overlay.jpg`
- `IMG20261019080706.jpg`: 8 cracks, mean relative error 5.8 %  ->  `data/processed/IMG20261019080706_overlay.jpg`

## Per photo

| photo | corners | px/mm | obliq | blur_var | sigma mm | glare | cracks | certified | reasons | ms |
|---|---|---|---|---|---|---|---|---|---|---|
| IMG20261019080657.jpg | 24 | 10.83 | 19.39 | 301.7 | 0.104 | 0.0 | 8 | yes |  | 593 |
| IMG20261019080703.jpg | 24 | 13.01 | 8.12 | 244.5 | 0.087 | 0.0 | 8 | yes |  | 643 |
| IMG20261019080706.jpg | 24 | 14.74 | 0.82 | 183.7 | 0.085 | 0.0 | 8 | yes |  | 703 |
| IMG20261019080709.jpg | 24 | 13.62 | 8.98 | 158.9 | 0.076 | 0.0 | 8 | yes |  | 720 |
| IMG20261019080711.jpg | 24 | 12.7 | 8.1 | 196.0 | 0.093 | 0.0 | 8 | yes |  | 703 |
| IMG20261019080712.jpg | 24 | 12.71 | 9.02 | 162.2 | 0.09 | 0.0 | 8 | yes |  | 841 |
| IMG20261019080716.jpg | 24 | 11.16 | 21.79 | 358.8 | 0.089 | 0.0 | 8 | yes |  | 946 |
| IMG20261019080719.jpg | 24 | 13.87 | 14.57 | 367.4 | 0.083 | 0.0 | 7 | yes |  | 932 |
| IMG20261019080722.jpg | 18 | 17.67 | 1.74 | 120.7 | 0.067 | 0.0 | 8 | no | blurry | 1024 |
| IMG20261019080725.jpg | 0 | 0.0 | 0.0 | 319.5232238769531 |  | 0.0 | 0 | no | too_few_corners | 59 |
| IMG20261019080728.jpg | 0 | 0.0 | 0.0 | 290.5491638183594 |  | 0.0 | 0 | no | too_few_corners | 67 |
| IMG20261019080733.jpg | 0 | 0.0 | 0.0 | 338.9153137207031 |  | 0.0 | 0 | no | too_few_corners | 59 |
| IMG20261019080735.jpg | 0 | 0.0 | 0.0 | 518.2440795898438 |  | 0.0 | 0 | no | too_few_corners | 56 |
| IMG20261019080737.jpg | 16 | 15.79 | 4.49 | 155.8 | 0.071 | 0.0 | 7 | yes |  | 757 |
| IMG20261019080739.jpg | 24 | 15.16 | 3.9 | 137.4 | 0.079 | 0.0 | 4 | no | blurry | 593 |
| IMG20261019080746.jpg | 19 | 16.29 | 32.55 | 105.1 | 0.079 | 0.0 | 8 | no | blurry | 1050 |
| IMG20261019080751.jpg | 24 | 19.06 | 27.76 | 91.5 | 0.163 | 0.0 | 6 | no | blurry | 966 |
| IMG20261019080759.jpg | 24 | 15.35 | 22.69 | 119.7 | 0.106 | 0.0 | 8 | no | blurry | 997 |
| IMG20261019080802_BURST000_COVER.jpg | 9 | 14.99 | 39.6 | 89.1 | 0.316 | 0.0 | 8 | no | blurry | 866 |
| IMG20261019080802_BURST001.jpg | 9 | 14.77 | 39.46 | 88.6 | 0.307 | 0.0 | 8 | no | blurry | 1096 |
| IMG20261019080807.jpg | 23 | 9.96 | 42.45 | 44.2 | 0.296 | 0.0 | 8 | no | blurry | 983 |
| IMG20261019080812.jpg | 6 | 0.0 | 0.0 | 31.03839683532715 |  | 0.0 | 0 | no | too_few_corners | 74 |
| IMG20261019080815.jpg | 24 | 11.74 | 14.56 | 115.8 | 0.098 | 0.0 | 8 | no | blurry | 738 |
| IMG20261019080817.jpg | 24 | 13.94 | 10.21 | 85.7 | 0.137 | 0.0 | 8 | no | blurry | 679 |
| IMG20261019080819.jpg | 24 | 16.16 | 7.7 | 76.1 | 0.185 | 0.0 | 8 | no | blurry | 845 |
| IMG20261019080820.jpg | 18 | 18.05 | 6.34 | 73.5 | 0.212 | 0.0 | 8 | no | blurry | 726 |
| IMG20261019080823.jpg | 0 | 0.0 | 0.0 | 20.180233001708984 |  | 0.0 | 0 | no | too_few_corners | 43 |
| IMG20261019080826.jpg | 0 | 0.0 | 0.0 | 23.15915870666504 |  | 0.0 | 0 | no | too_few_corners | 44 |
| IMG20261019080841.jpg | 24 | 13.7 | 5.55 | 107.0 | 0.104 | 0.0 | 8 | no | blurry | 740 |
