| comparison (A -> B) | stage | A p50 / p95 ms | B p50 / p95 ms | speedup A/B mean [95% CI] | p50 | p95 |
|---|---|---|---|---|---|---|
| pip 4T default CCL -> COOL 4T BBDT | detect | 30 / 37 | 28 / 36 | 1.076 [1.063, 1.089] | 1.060 | 1.041 |
| pip 4T default CCL -> COOL 4T BBDT | rectify | 48 / 62 | 41 / 56 | 1.155 [1.144, 1.167] | 1.169 | 1.113 |
| pip 4T default CCL -> COOL 4T BBDT | measure | 28 / 151 | 29 / 151 | 0.990 [0.986, 0.994] | 0.979 | 0.995 |
| pip 4T default CCL -> COOL 4T BBDT | analyze | 147 / 272 | 136 / 261 | 1.065 [1.058, 1.073] | 1.078 | 1.041 |
| pip 4T default CCL -> COOL 4T BBDT | e2e | 190 / 331 | 183 / 322 | 1.019 [1.008, 1.030] | 1.036 | 1.028 |
| pip 4T BBDT -> COOL 4T BBDT | detect | 30 / 37 | 28 / 36 | 1.069 [1.058, 1.081] | 1.057 | 1.020 |
| pip 4T BBDT -> COOL 4T BBDT | rectify | 48 / 63 | 41 / 56 | 1.142 [1.132, 1.152] | 1.160 | 1.114 |
| pip 4T BBDT -> COOL 4T BBDT | measure | 28 / 150 | 29 / 151 | 0.991 [0.987, 0.995] | 0.976 | 0.994 |
| pip 4T BBDT -> COOL 4T BBDT | analyze | 144 / 272 | 136 / 261 | 1.057 [1.051, 1.063] | 1.056 | 1.041 |
| pip 4T BBDT -> COOL 4T BBDT | e2e | 190 / 331 | 183 / 322 | 1.026 [1.019, 1.034] | 1.038 | 1.027 |
| pip 1T -> pip 4T (default CCL) | detect | 72 / 89 | 30 / 37 | 2.382 [2.360, 2.401] | 2.421 | 2.369 |
| pip 1T -> pip 4T (default CCL) | rectify | 79 / 93 | 48 / 62 | 1.605 [1.569, 1.644] | 1.642 | 1.496 |
| pip 1T -> pip 4T (default CCL) | measure | 42 / 179 | 28 / 151 | 1.272 [1.235, 1.329] | 1.518 | 1.192 |
| pip 1T -> pip 4T (default CCL) | analyze | 254 / 395 | 147 / 272 | 1.624 [1.569, 1.693] | 1.731 | 1.452 |
| pip 1T -> pip 4T (default CCL) | e2e | 304 / 454 | 190 / 331 | 1.514 [1.472, 1.560] | 1.601 | 1.371 |
