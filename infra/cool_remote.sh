#!/usr/bin/env bash
# Runs ON the Graviton instance (started by infra/cool_session.sh).  MODE=main (c8g.xlarge: COOL, stock pip, self-built
# reference, optional KleidiCV-ON ablation) or MODE=sweep (other sizes: COOL and stock pip only).
# Layout expected: ~/prohori (src, data/print, eval/cool_bench.py, infra/build_opencv_ref.sh), ~/inputs/{raw,samples,synth}.
# Results: ~/results/<label>/... and ~/results/evidence/...   Markers: ~/DONE or ~/FAILED.
set -uo pipefail
MODE="${1:-main}"
R=~/results; EV=$R/evidence; mkdir -p "$EV"
exec > >(tee -a "$R/remote.log") 2>&1
T0=$(date +%s)
fail() { echo "FAILED: $*"; touch ~/FAILED; exit 1; }
# The COOL venv only finds cv2 through the PYTHONPATH / LD_LIBRARY_PATH that its activate script exports (see
# /opt/cool/venvs/python_3.12/bin/activate); this wrapper sets exactly those and runs the venv's python.
cat > ~/coolpy.sh <<'WRAP'
#!/bin/bash
export PYTHONPATH="/opt/cool/python_3.12/site-packages/cv2/python-3.12:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib:${LD_LIBRARY_PATH:-}"
exec /opt/cool/venvs/python_3.12/bin/python "$@"
WRAP
chmod +x ~/coolpy.sh
COOLPY=~/coolpy.sh
INPUTS="--input raw=$HOME/inputs/raw --input samples=$HOME/inputs/samples --input synth=$HOME/inputs/synth"
N=$(nproc)
echo "== start $(date -u +%FT%TZ) mode=$MODE vcpu=$N"

# quiet the box: no background apt / snap work during timing
cloud-init status --wait >/dev/null 2>&1 || true
sudo systemctl stop unattended-upgrades apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service 2>/dev/null || true
for i in $(seq 1 60); do sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break; sleep 5; done

# ---------------------------------------------------------------- 1. verify the COOL install
{
  echo "== date"; date -u; uname -a; head -4 /etc/os-release
  echo "== lscpu"; lscpu
  echo "== IMDSv2"
  TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')
  for k in instance-type ami-id instance-id placement/availability-zone; do
    echo "$k=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/$k)"; done
  echo "== /opt/cool"; ls -la /opt/cool; ls -la /opt/cool/venvs 2>/dev/null
  for f in $(find /opt/cool -maxdepth 3 \( -iname '*version*' -o -iname 'readme*' -o -iname 'release*' -o -iname 'changelog*' -o -iname '*.txt' -o -iname '*.md' \) -type f 2>/dev/null | grep -v site-packages | head -20); do
    echo "---- $f"; head -c 2500 "$f"; echo; done
  echo "== cool python"
  $COOLPY -c "import sys,cv2,numpy; print(sys.version); print('cv2', cv2.__version__, cv2.__file__); print('numpy', numpy.__version__); print('ximgproc', hasattr(cv2,'ximgproc'), 'aruco', hasattr(cv2,'aruco'), 'threads', cv2.getNumThreads(), 'cpus', cv2.getNumberOfCPUs()); print(cv2.getCPUFeaturesLine())"
  echo "== cv2 submodules / thinning"
  $COOLPY -c "import cv2,types; print(sorted(n for n in dir(cv2) if isinstance(getattr(cv2,n),types.ModuleType))); print('ximgproc', hasattr(cv2,'ximgproc'), [n for n in dir(cv2) if 'thin' in n.lower()])"
  echo "== COOL cv2.getBuildInformation()"
  $COOLPY -c "import cv2; print(cv2.getBuildInformation())"
  echo "== pip freeze (COOL venv)"; $COOLPY -m pip freeze 2>/dev/null
  echo "== cv2 shared objects and KleidiCV symbols"
  CV2SO=$($COOLPY -c "import cv2,glob,os; d=os.path.dirname(cv2.__file__); print(' '.join(glob.glob(d+'/*.so*')+glob.glob(d+'/../*.libs/*')))")
  ls -la $CV2SO 2>/dev/null
  for f in $CV2SO; do echo "ldd $f"; ldd "$f" 2>/dev/null | head -40; done
  for f in $CV2SO; do echo "$f: kleidicv string count $(strings -a "$f" 2>/dev/null | grep -ci kleidicv)"; done
  find /opt/cool -iname '*kleidi*' 2>/dev/null | head
} > "$EV/cool_verify.txt" 2>&1
cat "$EV/cool_verify.txt" | head -60
if [ "$MODE" = inspect ]; then touch ~/DONE; exit 0; fi
$COOLPY -c "import cv2; assert cv2.__version__.startswith('5.'), cv2.__version__; assert hasattr(cv2,'aruco')" || fail "COOL cv2 is not OpenCV 5 with aruco"
$COOLPY -c "import cv2; b=cv2.getBuildInformation(); assert 'kleidi' in b.lower(), 'no KleidiCV in build info'" || echo "WARNING: no KleidiCV mention in COOL build info"
NV=$($COOLPY -c "import numpy; print(numpy.__version__)")

# sweep configs for this vCPU count: 1xT for T in 1,2,4,N and Wx1 for W>=2, plus (N/2)x2
SWEEP=$(python3 - <<PY
n=$N
c=["1x1"]+[f"1x{t}" for t in (2,4,8) if t<n]+[f"1x{n}"] if n>1 else ["1x1"]
c+=[f"{w}x1" for w in (2,4,8) if w<=n and w!=n]+([f"{n}x1"] if n>1 else [])
if n>=4: c.append(f"{n//2}x2")
seen=[]; [seen.append(x) for x in c if x not in seen]
print(",".join(seen))
PY
)
echo "sweep configs: $SWEEP"

# ---------------------------------------------------------------- 2. stock pip wheel venv (same numpy)
python3 -m venv ~/venv_pip 2>/dev/null || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip >/dev/null; python3 -m venv ~/venv_pip; }
~/venv_pip/bin/pip install -q "numpy==$NV" "opencv-contrib-python-headless==5.0.0.93" || fail "pip install"
PIPPY=~/venv_pip/bin/python
$PIPPY -c "import cv2,numpy; print(cv2.__version__, cv2.__file__, numpy.__version__)" | tee "$EV/pip_versions.txt"
$PIPPY -m pip freeze > "$EV/pip_freeze.txt"

bench() { # label python extra-args...
  local label=$1 py=$2; shift 2
  echo "== bench $label $(date -u +%T) elapsed $(( $(date +%s) - T0 ))s"
  $py ~/prohori/eval/cool_bench.py run --label "$label" --out "$R/$label" $INPUTS "$@" || echo "BENCH $label FAILED rc=$?"
}
elapsed() { echo $(( $(date +%s) - T0 )); }
# build_ref <id> <prefix> <venv> <ref> <contrib> <kleidi>: build OpenCV from source and install it into <venv> via .pth
build_ref() {
  local id=$1 prefix=$2 venv=$3 ref=$4 contrib=$5 kl=$6
  python3 -m venv "$venv" && "$venv/bin/pip" install -q "numpy==$NV" || { echo "venv $id failed"; return 1; }
  OPENCV_REF="$ref" WITH_CONTRIB="$contrib" bash ~/prohori/infra/build_opencv_ref.sh "$prefix" "$venv/bin/python" "$kl" "$EV" "$N" || { echo "BUILD $id FAILED"; return 1; }
  local sp; sp=$(ls -d "$prefix"/lib/python3.12/site-packages 2>/dev/null)
  echo "$sp" > "$venv/lib/python3.12/site-packages/ocv_ref.pth"
  "$venv/bin/python" -c "import cv2,numpy; print(cv2.__version__, cv2.__file__, numpy.__version__)" | tee "$EV/${id}_versions.txt"
}

# MODE=ccl: does routing connectedComponentsWithStats to BBDT unlock COOL's multithreaded kernels?  Single-frame latency
# at 4 OpenCV threads (1 process x 4 threads) for COOL and pip, plus the invariance of the swap.
if [ "$MODE" = ccl ]; then
  SW=(--sweep "1x2,1x4,2x2,4x1" --sweep-stride 2 --sweep-reps 2)
  B1=(--thinning shim --threads 1 --reps 3 --warmup 1 --trace-reps 2)
  B4=(--thinning shim --threads 4 --reps 5 --warmup 1 --trace-reps 2)
  bench cool_t1        "$COOLPY" "${B1[@]}"
  bench pip_t1         "$PIPPY"  "${B1[@]}"
  bench pip_t1_bbdt    "$PIPPY"  "${B1[@]}" --ccl bbdt
  bench cool_t1_bbdt   "$COOLPY" "${B1[@]}" --ccl bbdt
  bench pip_t4         "$PIPPY"  "${B4[@]}"
  bench pip_t4_bbdt    "$PIPPY"  "${B4[@]}" --ccl bbdt "${SW[@]}"
  bench cool_t4_bbdt   "$COOLPY" "${B4[@]}" --ccl bbdt "${SW[@]}" --micro --micro-mt
  echo "== end $(date -u +%FT%TZ) elapsed $(elapsed)s"
  touch ~/DONE
  exit 0
fi

# MODE=t4trace: per-call OpenCV times inside the pipeline at 4 OpenCV threads (COOL needs the BBDT workaround), COOL vs pip.
if [ "$MODE" = t4trace ]; then
  T4=(--thinning shim --ccl bbdt --threads 4 --reps 2 --warmup 1 --trace-reps 2)
  bench cool_t4_trace "$COOLPY" "${T4[@]}"
  bench pip_t4_trace  "$PIPPY"  "${T4[@]}"
  bench cool_t4_trace2 "$COOLPY" "${T4[@]}"
  echo "== end $(date -u +%FT%TZ) elapsed $(elapsed)s"
  touch ~/DONE
  exit 0
fi

# Thinning: the COOL AMI's OpenCV has no contrib (no cv2.ximgproc).  The headline comparison uses the SAME numpy
# Zhang-Suen thinning (bit-exact with ximgproc.thinning, tested) in every build; builds with contrib also get a
# native-thinning run.
if [ "$MODE" = main ]; then
  FULL=(--thinning shim --threads 1 --reps 5 --warmup 1 --sweep "$SWEEP" --sweep-stride 2 --sweep-reps 2 --micro --micro-mt)
else
  FULL=(--thinning shim --threads 1 --reps 3 --warmup 1 --sweep "$SWEEP" --sweep-stride 3 --sweep-reps 2 --micro --micro-mt --trace-stride 3)
fi

# ---------------------------------------------------------------- 3. benches
bench cool "$COOLPY" "${FULL[@]}"
bench pip  "$PIPPY"  "${FULL[@]}"

if [ "$MODE" = main ]; then
  bench pip_native "$PIPPY" --thinning native --threads 1 --reps 3 --warmup 1 --trace-reps 2
  # ---------------------------------------------------------------- 4. self-built reference: OpenCV 5.0.0 + contrib, KleidiCV OFF
  if build_ref ref_5.0.0_koff "$HOME/ocv_500_koff" ~/venv_ref 5.0.0 1 OFF; then
    bench ref ~/venv_ref/bin/python "${FULL[@]}"
    bench ref_native ~/venv_ref/bin/python --thinning native --threads 1 --reps 3 --warmup 1 --trace-reps 0
  fi
  # ---------------------------------------------------------------- 5. repeat COOL (drift check)
  bench cool_repeat "$COOLPY" --thinning shim --threads 1 --reps 3 --warmup 1 --trace-reps 0
  # ---------------------------------------------------------------- 6. ablation: the upstream 5.x snapshot COOL is built from
  SNAP="5.x@2026-07-13T03:56:14Z"
  if [ "$(elapsed)" -lt 6600 ] && build_ref snap_kon "$HOME/ocv_snap_kon" ~/venv_snapk 5.x@2026-07-13T03:56:14Z 0 ON; then
    bench snap_kon ~/venv_snapk/bin/python "${FULL[@]}"
  else
    echo "ablation snap_kon skipped or failed (elapsed $(elapsed)s)"
  fi
  if [ "$(elapsed)" -lt 7800 ] && build_ref snap_koff "$HOME/ocv_snap_koff" ~/venv_snapo 5.x@2026-07-13T03:56:14Z 0 OFF; then
    bench snap_koff ~/venv_snapo/bin/python --thinning shim --threads 1 --reps 3 --warmup 1 --micro --trace-reps 2 --sweep "1x$N,${N}x1" --sweep-stride 2 --sweep-reps 2
  else
    echo "ablation snap_koff skipped or failed (elapsed $(elapsed)s)"
  fi
fi
echo "== end $(date -u +%FT%TZ) elapsed $(elapsed)s"
touch ~/DONE
