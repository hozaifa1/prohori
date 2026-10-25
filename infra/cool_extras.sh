#!/usr/bin/env bash
# Extra evidence on the Graviton instance after infra/cool_remote.sh main: (1) cProfile of analyze() per build,
# (2) flag/variant timing table per build, (3) crash-rate matrix + gdb backtrace for the connectedComponentsWithStats
# heap corruption.  Needs ~/venv_pip, ~/coolpy.sh and whichever of ~/venv_ref ~/venv_snapk ~/venv_snapo exist.
# Layout: ~/prohori (bundle), ~/inputs, ~/results/extras (output), ~/bug (repro files).
set -uo pipefail
R=~/results/extras; mkdir -p "$R"
exec > >(tee -a "$R/extras.log") 2>&1
INP="--input raw=$HOME/inputs/raw --input samples=$HOME/inputs/samples --input synth=$HOME/inputs/synth"
declare -A PY
PY[cool]=~/coolpy.sh; PY[pip]=~/venv_pip/bin/python
[ -x ~/venv_ref/bin/python ] && PY[ref]=~/venv_ref/bin/python
[ -x ~/venv_snapk/bin/python ] && PY[snap_kon]=~/venv_snapk/bin/python
[ -x ~/venv_snapo/bin/python ] && PY[snap_koff]=~/venv_snapo/bin/python
ORDER=(cool pip ref snap_kon snap_koff)
echo "== extras start $(date -u +%T) builds: ${!PY[*]}"
sudo systemctl stop unattended-upgrades apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true

# ---- 1. cProfile (1 thread, shim thinning in every build for comparability)
for b in cool pip; do
  echo "== profile $b $(date -u +%T)"
  ${PY[$b]} ~/prohori/eval/cool_profile.py --out "$R/profile_$b" $INP --threads 1 --thinning shim --label "$b" > /dev/null 2>&1 || echo "profile $b failed"
done
# ---- 2. variants
for b in "${ORDER[@]}"; do
  [ -n "${PY[$b]:-}" ] || continue
  echo "== variants $b $(date -u +%T)"
  ${PY[$b]} ~/prohori/eval/cool_variants.py run --label "$b" --out "$R" --threads 1 || echo "variants $b failed"
done
# ---- 3. crash matrix
for b in "${ORDER[@]}"; do
  [ -n "${PY[$b]:-}" ] || continue
  PAIRS+=("$b=${PY[$b]}")
done
echo "== crash matrix $(date -u +%T)"
N=${N:-50} CALLS=${CALLS:-30} bash ~/prohori/infra/cool_cc_matrix.sh "$R/bug" ~/bug/cc_repro.py ~/bug/mask_locator_canvas.png "${PAIRS[@]}"
# ---- 4. gdb backtrace on COOL, 2 threads, real mask
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gdb >/dev/null 2>&1 || echo "gdb install failed"
if command -v gdb >/dev/null; then
  echo "== gdb backtrace $(date -u +%T)"
  env PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12 LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib \
    gdb -batch -ex run -ex bt -ex "info sharedlibrary" --args /opt/cool/venvs/python_3.12/bin/python ~/bug/cc_repro.py --threads 2 --calls 200 --mask ~/bug/mask_locator_canvas.png \
    > "$R/bug/gdb_backtrace_cool_t2.txt" 2>&1 || true
  env PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12 LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib \
    gdb -batch -ex run -ex bt --args /opt/cool/venvs/python_3.12/bin/python ~/bug/cc_repro.py --threads 4 --calls 200 \
    > "$R/bug/gdb_backtrace_cool_t4_synthetic.txt" 2>&1 || true
fi
echo "== extras end $(date -u +%T)"
touch "$R/EXTRAS_DONE"
