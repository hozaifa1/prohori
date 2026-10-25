# COOL on Graviton4: protocol, findings and how to reproduce (D24, D25, D26)

Goal: prove that COOL (Cloud Optimized OpenCV, AWS Marketplace) runs PROHORI's core measurement workload on AWS
Graviton4, measure what it buys, and prove it returns identical widths.  Results and numbers live in
`eval/results/cool/REPORT.md`; this note is the protocol and the lab book.

## What was verified on the instance (evidence: `eval/results/cool/<ts>/c8g.xlarge/evidence/cool_verify.txt`)

| item | value |
|---|---|
| AMI | `ami-033e481a24f94c8cb`, name `Graviton5-COOL-v3-prod-k6u24vxijyzvg`, Marketplace product code `aajkmdd4qo3r7yhqg61a7aah9`, us-east-1, created 2026-07-15 |
| Instance | c8g.xlarge (4 vCPU, Neoverse-V2, Graviton4), Ubuntu 24.04.3, kernel 6.17.0-1019-aws, IMDSv2 confirmed type and AMI id |
| OpenCV in COOL | **5.1.0-dev** (not 5.0.0), `Version control: unknown`, build timestamp 2026-07-13T03:56:14Z, Release, `-O3 -mcpu=neoverse-v2`, libjpeg-turbo 3.1.2, pthreads, HAL: `carotene 0.0.1, KleidiCV 0.7.0`, ArmPL 25.07.1 on the rpath |
| Python | `/opt/cool/venvs/python_3.12` (numpy 2.5.1); **the venv has no cv2 of its own**: `activate` exports `PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12` and `LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib`, which is how cv2 is found.  `infra/cool_remote.sh` reproduces exactly that environment |
| Version label | no "3.1" string exists anywhere under `/opt/cool` (no VERSION file); the only version facts on the box are the OpenCV 5.1.0-dev build info and `/opt/cool/samples/README.md` ("COOL build (OpenCV 5.1.0) against the standard tag build (OpenCV 5.0.0)").  The Marketplace listing's "Cloud Optimized OpenCV 3.1" is therefore not independently provable from the AMI; we report what the AMI shows |
| Not in COOL | **no `opencv_contrib`**: `cv2.ximgproc` is missing, so `cv2.ximgproc.thinning` (used twice by the pipeline) does not exist.  aruco/CharucoDetector is present (objdetect) |
| Other AMI | `ami-01db31139bc5615d8` (COOL v2, 2026-04-22) is OpenCV **4.14.0-pre**, TBB, no KleidiCV, no ximgproc: rejected (inspect run: `inspect_v2_ami/`) |

### Two facts that shaped the protocol

1. **Thinning shim.**  The AMI has no ximgproc.  The pipeline's only contrib call is `cv2.ximgproc.thinning`
   (Zhang-Suen).  `eval/cool_bench.py` carries `thinning_zs`, a numpy re-implementation that is bit-exact with the
   native function (`tests/test_cool_bench.py` checks 25 random masks; the full pipeline gives bitwise identical widths
   with shim and native on the same build, see REPORT).  The headline comparison uses the **same** shim in every
   build, so the OpenCV builds differ only in OpenCV.  Builds that have contrib also get a native-thinning run.
   `src/prohori/measure.py` is not edited; the shim is installed by replacing `measure.cv2` in the harness.
2. **COOL crash with more than one OpenCV thread.**  `cv2.connectedComponentsWithStats(mask, connectivity=8)` on a
   1273x1800 uint8 mask aborts the process with a glibc heap-corruption error (`malloc.c:2599 sysmalloc` /
   `corrupted size vs. prev_size` / `double free`) as soon as `cv2.setNumThreads(n)` with n >= 2 (default is 4 on a
   c8g.xlarge).  Reproducible on the first PROHORI frame.  connectivity=4, CCL_BBDT and CCL_WU do not crash,
   CCL_SPAGHETTI (the default) does, so the fault is in the parallel SPAGHETTI path of this 5.1.0-dev build.
   Consequence: the headline runs use `cv2.setNumThreads(1)`, and parallelism comes from worker processes (WxT sweep),
   which is also the better deployment shape for a request/response service.  The crashing thread counts are recorded
   as failed sweep configs, not hidden.  Crash rate (50 runs per cell): COOL 0/50 at 1 thread, 50/50 at 2 and 4; pip 5.0.0,
   self-built 5.0.0 and the upstream 5.x snapshot (KleidiCV on and off) 0/50 everywhere, so it is COOL-specific.  Draft bug
   report, repro, mask, matrix: `eval/results/cool/<ts>/bug_connectedcomponents/` (not sent anywhere).
3. **Workaround**: `eval/cool_compat.install_thinning(measure, "auto", "bbdt")` routes the call to `CCL_BBDT` (identical
   labels/stats; pipeline output bitwise identical), which lets COOL run 4 threads.  `--ccl bbdt` in the harness.

## Protocol

- **Workload**: `prohori.measure.analyze` exactly as the service calls it: `cv2.imdecode` of the JPEG, then `analyze`
  (board detection with `aruco.CharucoDetector`, `findHomography`, `cornerSubPix`, rectification by `warpPerspective`,
  crack locator with `GaussianBlur`/`medianBlur`/`morphologyEx`/`connectedComponentsWithStats`/thinning,
  full-resolution ROI warps (`INTER_CUBIC`), profile sampling with `remap`, `distanceTransform`, `GaussianBlur`, gate).
- **Inputs (85 frames, sha256 manifest in every `*.bench.json`)**: 29 real phone photos of the printed panel
  (`data/raw/*.jpg`, 12 MP), 6 committed demo photos (`service/static/samples`, small), and 50 renders from the
  synthetic set `v1` (every 10th of 500, 12 MP).
- **Timing**: warm-up pass, then 5 timed passes (xlarge; 3 on other sizes), un-instrumented, `perf_counter_ns`.  Stages:
  decode, detect, rectify (incl. locator), measure (ROI warps + estimators), other (package + gate), analyze, e2e.
  Speedups are ratios of pooled statistics (mean, p50, p95 over image x rep) with a **paired image-cluster bootstrap**
  (2000 resamples of the images, same resample for both builds) for the 95% CI.
- **Sweep**: `WxT` = W worker processes each with `cv2.setNumThreads(T)`: 1x1, 1x2, 1x4, 2x1, 4x1, 2x2 (xlarge) on a
  stride-2 subset, 1 warm pass + 2 timed passes; fps = frames / wall seconds, latency = per-frame decode+analyze under that
  load.
- **Microbench**: 25 exact OpenCV calls at the sizes the pipeline uses (12 MP source, 1273x1800 rectified canvas,
  2000x500 ROI), median of 3-100 calls, threads = 1 (in process) and default (one child process per case so a crash is
  a result).  The output bytes of every call are hashed: identical hash = bit-exact function.
- **Trace pass** (instrumented, ratios only): `measure.cv2` is replaced by a proxy that times every OpenCV call and
  hashes its output; selected `measure._*` functions are wrapped.  Gives (i) per-function time and the share of
  `analyze` spent inside OpenCV vs Python/numpy (Amdahl), (ii) the first OpenCV call whose output differs between
  builds.
- **Accuracy invariance**: every leaf of every result (crack widths, estimator columns, uncertainties, gate fields,
  board corners) as float64 hex, plus the unrounded internal scalars of `_measure_roi`; `compare` reports
  bitwise identity or max / P99 |dw| in mm, which inputs differ, certification flips, and the first differing OpenCV call.
  Acceptance: identical, or far below `U_ref = 0.009 mm` with no certification flip.
- **Builds on the same c8g.xlarge** (same numpy 2.5.1): `cool` (AMI), `pip` (`opencv-contrib-python-headless==5.0.0.93`),
  `ref` (OpenCV 5.0.0 + contrib 5.0.0 from source (`build_opencv_ref.sh`, about 5 min on 4 vCPU), Release, NEON, bundled libjpeg-turbo/png/zlib, pthreads, **KleidiCV
  off**, flags in `evidence/ref_5.0.0_k*_cmake_command.txt`), and the ablation builds `snap_kon` / `snap_koff`: the
  upstream `5.x` branch at COOL's build timestamp (2026-07-13T03:56Z, the 5.1.0-dev snapshot COOL is made from) with
  KleidiCV on / off and no contrib.  `snap_kon` vs `cool` isolates COOL's own additions (carotene, ArmPL, `-mcpu`,
  parallel tuning) from upstream KleidiCV; `snap_kon` vs `ref` isolates "5.1-dev + KleidiCV" from 5.0.0.
- **Instance sizes**: c8g.large and c8g.2xlarge, COOL and pip only, shorter protocol (3 reps, sweep on every 3rd frame).
- **Cost**: EC2 on-demand list price (AWS Price List API, us-east-1, Linux, published 2026-10-23) plus the COOL software
  fee on COOL runs; `eval/cool_plot.py` computes USD per 1,000 frames = (USD/h) / 3600 * 1000 / fps for every
  build x size x WxT and picks the production configuration.

## Results in one paragraph

COOL runs the whole workload (c8g.large/xlarge/2xlarge); end to end it is 1.014x faster than the pip wheel (break-even, 0.997-1.025x depending on the
baseline build), 67 % of `analyze()` time is OpenCV and COOL speeds that only 1.01x, widths differ from pip like two plain builds differ (max 0.030 mm,
not bitwise), error vs truth is identical, the fee makes it ~7 % dearer per frame, and its default multithreaded connected-components crashes.  Details: `eval/results/cool/<ts>/REPORT.md`.

## How to reproduce (exact commands)

Prerequisites: AWS CLI logged in, Marketplace subscription to "Cloud Optimized OpenCV For AWS Graviton4", key pair
`prohori-key`, security group `infra/state.env:SG` with tcp/22 open to your IP, inputs staged under
`~/prohori_data/cool_stage/{raw,samples,synth}` (copy of `data/raw`, the six committed samples in `service/static/samples`
and every 10th `*.jpg` of the synthetic set `v1`; `cool_stage_half` = every other file of each, used for the size and CCL sessions).

```bash
# 0. local dry run on x86 (output is labelled DRY RUN)
python eval/cool_bench.py run --label dry --out /tmp/dry --input raw=data/raw --stride 10 --reps 2 --thinning shim --threads 1 --trace-reps 1
python -m pytest -q tests/test_cool_bench.py
# 1. main session: COOL, pip, pip native, self-built 5.0.0, COOL repeat, upstream snapshot with KleidiCV on/off,
#    all on ONE c8g.xlarge (about 55 min; the instance terminates itself)
TS=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p eval/results/cool/$TS && cp <prices.json> eval/results/cool/$TS/
bash infra/cool_session.sh xl ami-033e481a24f94c8cb c8g.xlarge main eval/results/cool/$TS/c8g.xlarge 175
# 1b. extras on the same instance before it terminates (cProfile, variant table, crash matrix): infra/cool_extras.sh
#     (see REPORT.md; it needs ~/bug/cc_repro.py and the mask from eval/results/cool/<ts>/bug_connectedcomponents/)
# 2. size sessions (COOL + pip only) and the CCL-workaround session
COOL_INPUTS=~/prohori_data/cool_stage_half bash infra/cool_session.sh lg ami-033e481a24f94c8cb c8g.large   sweep eval/results/cool/$TS/c8g.large   80
COOL_INPUTS=~/prohori_data/cool_stage_half bash infra/cool_session.sh x2 ami-033e481a24f94c8cb c8g.2xlarge sweep eval/results/cool/$TS/c8g.2xlarge 60
COOL_INPUTS=~/prohori_data/cool_stage_half bash infra/cool_session.sh ccl ami-033e481a24f94c8cb c8g.xlarge ccl  eval/results/cool/$TS/ccl_c8g.xlarge 60
# 3. analysis (any machine, no AWS)
python eval/cool_bench.py compare $R/pip/pip.bench.json $R/cool/cool.bench.json --md pip_vs_cool.md   # R=eval/results/cool/$TS/c8g.xlarge
python eval/cool_variants.py compare $R/extras/pip.variants.json $R/extras/cool.variants.json
python eval/cool_plot.py eval/results/cool/$TS --slo-ms 600
```

Using COOL in the live service later: `from cool_compat import install_thinning; install_thinning(measure, "auto", "bbdt")`
(no ximgproc on COOL, avoid the SPAGHETTI crash), `cv2.setNumThreads(1)` per worker process or 2-4 threads with the BBDT route, and
launch with `source /opt/cool/venvs/python_3.12/bin/activate` (that is what makes cv2 importable).

Safety: every instance is tagged `Project=prohori, Purpose=cool-bench`, launched with
`--instance-initiated-shutdown-behavior terminate`, gets `shutdown -h +180` (user data and ssh) and is terminated by a
bash trap when the session script exits; `infra/cool_session.sh` refuses any type except c8g.large/xlarge/2xlarge and
appends launch/terminate times to `eval/results/cool/ledger.tsv`.
