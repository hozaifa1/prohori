# Bug report (draft, not sent): `cv2.connectedComponentsWithStats` corrupts the heap when OpenCV uses 2 or more threads (COOL AMI, OpenCV 5.1.0-dev)

Status: draft for the PROHORI team; **not reported anywhere**.  Found 2026-10-25 while benchmarking PROHORI's measurement
pipeline on the COOL AMI.

## Summary

On the AWS Marketplace "Cloud Optimized OpenCV For AWS Graviton4" AMI, `cv2.connectedComponentsWithStats(mask, connectivity=8)`
(default algorithm, `CCL_SPAGHETTI`) on a 1800x1273 `uint8` mask aborts the Python process with a glibc heap-corruption
assertion whenever `cv2.setNumThreads(n)` is 2 or more.  The AMI's default thread count is the vCPU count (4 on a
c8g.xlarge), so **with default settings PROHORI's very first frame kills the process**.  With 1 thread it never fails.
It is specific to the COOL build: the same call on pip OpenCV 5.0.0.93, OpenCV 5.0.0 built from source, and upstream
`5.x` built at COOL's own build date with and without KleidiCV never crashed in 50 runs per thread count.

## Environment

| | |
|---|---|
| AMI | `ami-033e481a24f94c8cb` (`Graviton5-COOL-v3-prod-k6u24vxijyzvg`, AWS Marketplace product code `aajkmdd4qo3r7yhqg61a7aah9`, created 2026-07-15), us-east-1 |
| Instance | c8g.xlarge (4 vCPU, Neoverse-V2), Ubuntu 24.04.3, kernel 6.17.0-1019-aws |
| OpenCV | `5.1.0-dev` from `/opt/cool/python_3.12/site-packages/cv2/python-3.12/cv2.cpython-312-aarch64-linux-gnu.so` + `/opt/cool/cpp_sdk/lib/libopencv_*.so.501`; `Version control: unknown`, build timestamp 2026-07-13T03:56:14Z, Release `-O3 -mcpu=neoverse-v2`, HAL `carotene 0.0.1, KleidiCV 0.7.0`, parallel framework pthreads, GCC 13.3.0 (full text: `../c8g.xlarge/cool/cool.build_info.txt`) |
| Python | `/opt/cool/venvs/python_3.12` (3.12.3, numpy 2.5.1), environment exactly as its `activate` sets it: `PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12`, `LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib` |

## Steps to reproduce

```bash
source /opt/cool/venvs/python_3.12/bin/activate
python cc_repro.py --threads 1 --calls 100 --mask mask_locator_canvas.png   # prints "OK components: ..."
python cc_repro.py --threads 2 --calls 100 --mask mask_locator_canvas.png   # aborts
python cc_repro.py --threads 2 --calls 100                                  # synthetic sine-line mask, aborts too
```

`cc_repro.py` uses only `cv2` and `numpy`.  `mask_locator_canvas.png` is the 1800x1273 binary mask PROHORI's locator
passes to `connectedComponentsWithStats` for the first photo of the test panel (66,089 foreground pixels, thin curved
cracks; lossless PNG, 14 KB).  The script without `--mask` draws a 5-px sine line on a blank 1800x1273 canvas.

Expected: the call returns the components.  Actual (any run, 2 or 4 threads):

```
Fatal glibc error: malloc.c:2599 (sysmalloc): assertion failed: (old_top == initial_top (av) && old_size == 0) || ((unsigned long) (old_size) >= MINSIZE && prev_inuse (old_top) && ((unsigned long) old_end & (pagesize - 1)) == 0)
```
(other runs of the same program print `corrupted size vs. prev_size` or `double free or corruption (out)`; exit code 134, SIGABRT.)

## Crash rate (N = 50 fresh processes per cell, 30 calls each; `crash_matrix.tsv`)

| build (all on the same c8g.xlarge) | threads 1 | threads 2 | threads 4 |
|---|---|---|---|
| **COOL** (5.1.0-dev, KleidiCV 0.7.0) | 0 / 50 | **50 / 50** | **50 / 50** |
| pip `opencv-contrib-python-headless 5.0.0.93` | 0 / 50 | 0 / 50 | 0 / 50 |
| OpenCV 5.0.0 + contrib built from source, KleidiCV off | 0 / 50 | 0 / 50 | 0 / 50 |
| upstream `5.x` @ 2026-07-13T03:56Z (commit 8fdf15e), KleidiCV 26.03 **on** | 0 / 50 | 0 / 50 | 0 / 50 |
| upstream `5.x` @ 2026-07-13T03:56Z, KleidiCV **off** | 0 / 50 | 0 / 50 | 0 / 50 |

Variants on COOL at 4 threads (50 runs each): `connectivity=4` 0 crashes, `CCL_BBDT` 0, `CCL_WU` 0, `CCL_SPAGHETTI` (the default)
50.  Shape dependence (probe run, 300 calls, 2 threads): 1800x1273 crashes; 1000x1000, 500x2000 (4 threads), 300x200 and 64x64 did not.
(`../repro/cc_crash_repro_output.txt`.)

Conclusion: COOL-specific (not upstream 5.1-dev, not KleidiCV as built by upstream), in the parallel `CCL_SPAGHETTI` path
for connectivity 8 on large masks.

## Diagnostics collected

- `gdb_backtrace_cool_t2.txt`, `gdb_backtrace_cool_t4_synthetic.txt`: the abort is raised from the main thread inside glibc `sysmalloc`; gdb cannot unwind
  past it ("previous frame inner to this frame (corrupt stack?)"), so the writer is not identified.  libopencv has no debug symbols.
- `valgrind_cool_t2.txt`: valgrind is not usable here, the COOL `libopencv_core` throws a `cv::Exception` in its static initialisers
  under valgrind (CPU feature detection), before the repro runs.
- `MALLOC_CHECK_=3` turns it into `double free or corruption (out)` during the same call.
- Not yet tried (would need the vendor): an ASan build, or a build of the 5.1.0-dev parallel CCL path with symbols.

## Workaround used by PROHORI

`cv2.setNumThreads(1)` in every worker process and scale with processes (`W` workers x 1 thread).  That is also the
better-scaling shape for this workload: on a c8g.xlarge 4 processes x 1 thread reach 11.7 frames/s, a single process with 4
threads would reach 4.6 frames/s on the builds that can run it.
