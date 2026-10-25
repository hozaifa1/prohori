#!/usr/bin/env bash
# Crash-rate matrix for the connectedComponentsWithStats heap corruption (see eval/results/cool/<ts>/bug_connectedcomponents/).
# Runs on the Graviton instance.  Usage: bash cool_cc_matrix.sh <out-dir> <repro.py> <mask.png> label=python [label=python ...]
# For every build and thread count: N invocations (default 50) of the standalone repro; counts non-zero exits and keeps
# the glibc message.  Extra rows for the first build: connectivity 4 and the BBDT / WU / SPAGHETTI algorithms.
set -uo pipefail
OUT="$1"; REPRO="$2"; MASK="$3"; shift 3
N="${N:-50}"; CALLS="${CALLS:-100}"
mkdir -p "$OUT"
TSV="$OUT/crash_matrix.tsv"
printf 'build\tcv2\tthreads\tconn\talgo\truns\tcrashes\tfirst_message\n' > "$TSV"
run_cell() { # label py threads conn algo
  local label=$1 py=$2 t=$3 conn=$4 algo=$5 crashes=0 msg="" ver
  ver=$($py -c "import cv2; print(cv2.__version__)" 2>/dev/null)
  for i in $(seq 1 "$N"); do
    o=$(timeout 120 $py "$REPRO" --threads "$t" --calls "$CALLS" --mask "$MASK" --conn "$conn" --algo "$algo" 2>&1 >/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then crashes=$((crashes + 1)); [ -z "$msg" ] && msg="rc=$rc $(echo "$o" | tail -1 | cut -c1-110)"; fi
  done
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$label" "$ver" "$t" "$conn" "$algo" "$N" "$crashes" "$msg" | tee -a "$TSV"
}
first=1
for pair in "$@"; do
  label="${pair%%=*}"; py="${pair#*=}"
  for t in 1 2 4; do run_cell "$label" "$py" "$t" 8 default; done
  if [ $first = 1 ]; then
    for v in "4 default" "8 bbdt" "8 wu" "8 spaghetti"; do set -- $v; run_cell "$label" "$py" 4 "$1" "$2"; done
    first=0
  fi
done
