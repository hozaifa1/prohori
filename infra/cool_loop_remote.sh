#!/usr/bin/env bash
# Runs ON the loop instance.   bash cool_loop_remote.sh setup      (once: COOL wrapper, stock pip venv, quiet box)
#                              bash cool_loop_remote.sh run <py> <tree> <label> <threads> <compat> [extra harness args...]
# <py> = cool | pip.  <tree> = a directory holding src/, data/print/, eval/ (a full checkout of one variant).  Results go to
# ~/out/<label>/ (<label>.loop.json, <label>.dump.json.gz).  Inputs: ~/inputs/{raw,samples,synth}.
set -uo pipefail
cmd="${1:?setup|run}"; shift
case "$cmd" in
setup)
  cat > ~/coolpy.sh <<'WRAP'
#!/bin/bash
# exactly what /opt/cool/venvs/python_3.12/bin/activate exports (the venv has no cv2 of its own)
export PYTHONPATH="/opt/cool/python_3.12/site-packages/cv2/python-3.12:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib:${LD_LIBRARY_PATH:-}"
exec /opt/cool/venvs/python_3.12/bin/python "$@"
WRAP
  chmod +x ~/coolpy.sh
  cloud-init status --wait >/dev/null 2>&1 || true
  sudo systemctl stop unattended-upgrades apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service 2>/dev/null || true
  for i in $(seq 1 60); do sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || break; sleep 5; done
  NV=$(~/coolpy.sh -c "import numpy; print(numpy.__version__)")
  python3 -m venv ~/venv_pip 2>/dev/null || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip >/dev/null; python3 -m venv ~/venv_pip; }
  ~/venv_pip/bin/pip install -q "numpy==$NV" "opencv-contrib-python-headless==5.0.0.93" 2>&1 | tail -2
  ~/venv_pip/bin/python -c "import cv2,numpy; print('pip', cv2.__version__, numpy.__version__)"
  ~/coolpy.sh -c "import cv2,numpy; print('cool', cv2.__version__, cv2.__file__, numpy.__version__, hasattr(cv2,'ximgproc'), cv2.getNumThreads(), cv2.getNumberOfCPUs())"
  mkdir -p ~/out ~/trees; nproc; uptime
  ;;
run)
  py="$1"; tree="$2"; label="$3"; threads="$4"; compat="$5"; shift 5
  if [ "$py" = cool ]; then PY=~/coolpy.sh; else PY=~/venv_pip/bin/python; fi
  cd "$tree" || exit 2
  $PY eval/cool_loop.py run --label "$label" --out ~/out/"$label" \
     --input raw=$HOME/inputs/raw --input samples=$HOME/inputs/samples --input synth=$HOME/inputs/synth \
     --threads "$threads" --compat "$compat" "$@"
  ;;
esac
