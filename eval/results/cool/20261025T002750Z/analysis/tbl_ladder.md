| step (A -> B) | e2e speedup A/B (mean, 95% CI) | analyze() | OpenCV-call time A/B | Python/numpy time A/B | OpenCV share of analyze (A -> B) |
|---|---|---|---|---|---|
| pip 5.0.0.93 -> self-built 5.0.0 (same source, other compiler) | 0.989 [0.986, 0.993] | 0.990 | 0.970 | 1.033 | 66.8 % -> 68.2 % |
| self-built 5.0.0 -> self-built 5.x snapshot (library version only, KleidiCV off) | 1.022 [1.019, 1.025] | 1.026 | 1.040 | 0.996 | 68.2 % -> 67.2 % |
| snapshot KleidiCV off -> on (KleidiCV only) | 1.011 [1.007, 1.015] | 1.015 | 1.028 | 0.990 | 67.2 % -> 66.4 % |
| snapshot KleidiCV on -> COOL (COOL's own build/tuning only) | 0.992 [0.987, 0.996] | 0.988 | 0.974 | 1.017 | 66.4 % -> 67.4 % |
| pip 5.0.0.93 -> COOL (the claim) | 1.014 [1.010, 1.017] | 1.019 | 1.010 | 1.036 | 66.8 % -> 67.4 % |
| COOL -> COOL repeated later (drift) | 0.993 [0.990, 0.995] | 0.995 | n/a | n/a | n/a |
