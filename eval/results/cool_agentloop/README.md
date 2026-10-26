# COOL developer-agent optimisation loop (OpenCV AI Competition 2026, Agentic Vision)

An agent (Claude Opus) ran a measure - hypothesise - change - verify loop on PROHORI's measurement pipeline (`src/prohori/measure.py`), on a Graviton4
c8g.xlarge with the COOL AMI (OpenCV 5.1.0-dev + KleidiCV), using the runtime measurements of each run (profile, per-stage timings, an accuracy
check against HEAD's outputs) to choose the next change. Every iteration is in `trace.jsonl` (19 records: observation, hypothesis, change + commit,
commands, measurements, accuracy check, keep/discard + reason). The workload is the one of `eval/results/cool/20261025T002750Z/REPORT.md`: 85 frames
(29 phone photos of the printed panel, 6 demo photos, 50 renders), `decode + analyze`, 1 warm-up + 5 timed passes.

**Objective (fixed).** Primary: end-to-end p50 latency per frame, single request, c8g.xlarge, COOL, 4 OpenCV threads. Secondary: USD per 1,000 frames
at saturation (best processes x threads). **Guard rails (fixed).** On the 29 panel photos every crack width within 0.005 mm of HEAD's output on the same
instance and the same gate tier; only the resize / warp-interpolation class may break this, then if the panel TEST MAE gets no worse than +0.002 mm and
tier flips are <= 1 % of cracks.

## Result

All runs below: one c8g.xlarge session (`raw/s2`), runs interleaved HEAD / final / HEAD / final, same frames, same harness (`eval/cool_loop.py`).
"HEAD" = commit 1c1ac4f plus the harness shims it needs on COOL (numpy Zhang-Suen thinning, CCL_BBDT; without them it does not run at >= 2 threads).

### Before / after on COOL (end-to-end ms per frame, decode + analyze)

| | p50 | p95 | mean | vs HEAD (p50) | outputs vs HEAD |
|---|---|---|---|---|---|
| HEAD, 4 OpenCV threads (3 runs) | 186.6 / 187.2 / 184.4 | 324 | 204 | | |
| **final, exact** (main, 1c0a708), 4 threads (3 runs) | **143.1 / 142.1 / 143.8** | 208 | 149 | **-23.2 %** | bit-identical, all 85 frames |
| final + output-changing resize (branch `cool-loop-output-changing`, 8d13353) | 131.8 | 198 | 139 | -29.2 % | see below |
| HEAD, 1 OpenCV thread | 307.2 | 450 | 312 | | |
| final, 1 OpenCV thread (Python threads on) | 225.7 | 276 | 220 | -26.5 % | bit-identical |
| final, 1 OpenCV thread, `PROHORI_THREADS=1` (single-threaded code) | 276.4 | 355 | 273 | -10.0 % | bit-identical |

Stage p50 at 4 threads, HEAD -> final: decode 51.5 -> 53.4 (untouched; 37 % of the final latency), detect 28.9 -> 29.0, rectify 42.7 -> 44.5, measure 27.8 -> 11.0, other 31.4 -> 2.4, analyze 139.6 -> 91.8.
With concurrent sections the stage timers overlap and no longer add up; `raw/s2/F_timeline_f1_t4.txt` has the real timeline.

### COOL vs pip after the optimisation (same instance, same code, same session)

| | pip 5.0.0.93 | COOL | pip / COOL (COOL speed-up) |
|---|---|---|---|
| 4 threads, HEAD, p50 | 188.9 | 186.1 (mean of 3) | 1.015x |
| 4 threads, final, p50 | 142.2 | 143.0 (mean of 3) | **0.994x** (tie) |
| 1 thread, final, p50 | 224.3 | 225.7 | 0.994x |
| 1 thread, final, `PROHORI_THREADS=1`, p50 | 273.2 | 276.4 | 0.988x |

The conclusion of the earlier report stands and is now measured on the optimised code: **COOL = pip within 1 % on this workload**, before and after.
The gains are generic (they apply to the pip build too: pip HEAD 188.9 -> 142.2 ms, -24.7 %), because python + numpy are 45-60 % of the
time and the OpenCV calls that dominate (ArUco `detectBoard`, INTER_AREA `resize`, `warpPerspective`) are not the ones KleidiCV accelerates.

### Throughput and cost (c8g.xlarge; list prices from `eval/results/cool/20261025T002750Z/prices.json`: $0.15952/h + COOL fee $0.01/h)

| build, config (processes x OpenCV threads) | fps | p95 ms under load | USD / 1,000 frames |
|---|---|---|---|
| COOL HEAD 4x1 | 11.98 | 469 | 0.00393 |
| COOL HEAD 2x2 / 1x4 | 7.98 / 4.84 | 375 / 325 | 0.00590 / 0.00974 |
| COOL final 4x1 | 13.57 | 388 | 0.00347 |
| **COOL final 4x1, `PROHORI_THREADS=1`** | **13.78** | 369 | **0.00342** (-13.0 % vs HEAD) |
| COOL final 2x2 / 1x4 | 10.21 / 6.69 | 255 / 204 | 0.00461 / 0.00704 |
| pip HEAD 4x1 | 11.81 | 487 | 0.00375 |
| pip final 4x1, `PROHORI_THREADS=1` | 13.91 | 370 | 0.00319 |

**Best config: 4 processes x 1 OpenCV thread with `PROHORI_THREADS=1`**: $0.00342 per 1,000 frames on COOL (HEAD: $0.00393). The COOL fee still makes COOL 7.2 % dearer
than pip per frame at the same throughput ($0.00319); that did not change. For a single interactive request the best is 1 process x 4 threads (p50 143 ms, 6.69 fps, $0.00704).
At saturation the Python threads add nothing (13.57 vs 13.78 fps), so a worker pool should set `PROHORI_THREADS=1`; a single-request endpoint keeps the default (min(4, CPUs)).

![latency per iteration](latency_per_iteration.png)

## What changed (kept: all on `main`, all bit-identical on 85 frames; tests pin each one to the code it replaced)

| # | commit | change | 4-thread p50 after it (session 1) |
|---|---|---|---|
| 0 | 1c1ac4f | HEAD | 194.9 |
| 1 | b079cdd | `CCL_BBDT` labelling (fixes the COOL heap-corruption path) + in-tree sparse Zhang-Suen `_thin` (no `cv2.ximgproc`, so no contrib needed on COOL; ~3x faster than the native call, 1.65x faster than the numpy shim) | 192.7 |
| 2 | 1f97b7f | `_longest_path` neighbour table / BFS without per-node lists; `_match_once` for all specimens in one broadcast | 188.8 (p95 321 -> 287) |
| 3 | dc56e03 | cached all-255 image, `_warp_valid` (no 12 MP NEAREST warp when the ROI maps well inside the photo), 256-bin histogram medians | 176.4 |
| 4 | 78deaf7 | vectorised `_fwhm` | 177.2 |
| 5 | c081534 | locator elementwise ops via cv2 | 175.6 |
| 6 | 162ce16 | Python threads for independent parts of a frame (`PROHORI_THREADS`, default min(4, CPUs)) | **154.6 (-12 %)** |
| 7 | c7bfcea | `count_nonzero` for big masks, int16 filter responses | 149.9 |
| 17 | c5a29bd | start the two background tasks just before the locator | ~146 (3 repeats, -2 %) |
| 18 | 1c0a708 | biggest ROI tasks first | ~145 (-1.5 %) |

Session 1 ran on another instance than the final table (HEAD was 194.9 ms there, 186.6 in session 2); both show -23 %.

**Discarded**, with numbers (details in `trace.jsonl`):
- dense OpenCV-kernel Zhang-Suen (filter2D + LUT): exact, but 2.17 ms/mask vs 1.10 for the in-tree sparse code (COOL micro-benchmark on the 92 real masks).
- canvas `warpPerspective` -> `remap` with CV_16SC2 maps: building the maps costs 17.4 ms in numpy, more than the 5.3 ms saved (the warp is 2.3 ms at 4 threads).
- board detection on a 1600 / 1800 px side: -6.3 % / -4.0 % but 2 of 168 panel cracks flip tier (1.19 % > 1 %).
- one ArUco threshold window first: no gain on COOL (p50 -1.9 %, mean +0.8 %; partial boards run both detectors).
- OpenCV-thread grid: 4 threads are needed (3: +1 %, 2: +13 %); 2 or 4 Python threads are equal.

### Output-changing candidate (resize class), NOT on main: branch `cool-loop-output-changing`, commit 8d13353

Down-scale the board-detection input and the locator canvas through an exact 2x INTER_AREA first (`_resize_area`). p50 143.0 -> 131.8 ms (-7.8 % on top of the exact final, -29 % vs HEAD).
Guard against HEAD on the same instance: panel TEST MAE +0.0013 mm (limit +0.002; all 168 panel cracks +0.0022, bootstrap CI over photos [-0.0002, +0.0060]), tier flips 1 of 168 (0.6 %, limit 1 %), so by the rule it is **allowed**.
But widths are not within 0.005 mm: max |dw| 0.12 mm on one panel crack (6 panel cracks differ by more than 0.02 mm) and 1.13 mm on one synthetic render (`synth_00170`; the locator assignment changed, not diagnosed further); the demo samples are unchanged.
I left the decision to the orchestrator: cherry-pick 8d13353 for the extra ~8 %, or skip it for bit-identical output.

## Guard-rail check (accuracy invariance, on the same instance)

`eval/cool_loop.py compare`: all 85 frames bitwise identical to HEAD's output (every number of every result, float64 hex) for every kept iteration, so max |dw| = 0 and 0 tier flips over 168 panel cracks.
Also bit-identical on the pip build (F_f1_pip_t4 vs F_head_pip_t4). `tests/test_measure_fast_paths.py` (13 tests) checks each fast path against the replaced code on random inputs.
Full local suite on 1c0a708: 267 passed (254 before + 13 new), `pytest_f1.log`.

## Compatibility

`src/prohori/measure.py` no longer calls `cv2.ximgproc` and no longer uses the default connected-component algorithm: it runs unmodified on COOL (no contrib) and on the pip build (OpenCV 5.0.0 with contrib).
No new required configuration; `PROHORI_THREADS` is optional (`1` = sequential, same code path). `eval/cool_compat.py` is only needed to run the old HEAD on COOL.

## Instance time (`ledger.tsv`)

s1 (iteration runs) 2.0 h as booked: the instance shut itself down through its `shutdown -h +120` timer after my session hit a usage limit (about 1.2 h of it was real work); s2 (final runs) 0.658 h.
**2.66 instance-hours of the 4 h cap, c8g.xlarge only.** Both instances are terminated (only the live t4g.small i-014731cc331b2833d is running, untouched).

## Files

`trace.jsonl` (iterations), `summary.json` (final tables), `latency_per_iteration.png`, `ledger.tsv`, `raw/s1` (iteration runs: `*.loop.json` timings + profile, `*.dump.json.gz` bit-exact result dumps, `guard.json`, `mae.json`, micro-benchmarks), `raw/s2`
(final runs, `f.log`), `pytest_f1.log`. Tools: `eval/cool_loop.py` (run / compare), `eval/cool_loop_mae.py`, `eval/cool_loop_micro.py`, `eval/cool_loop_timeline.py`, `eval/cool_loop_report.py` (rebuilds trace, figure, summary), `infra/cool_loop_*.sh`.
Caveats: the numbers of iterations 16-18 were read from the console because their raw files were lost with the session-1 instance; one machine per session, so differences below ~2 % are noise; 7 of the 29 panel photos have no usable board (frozen split).
