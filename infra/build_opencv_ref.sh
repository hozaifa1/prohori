#!/usr/bin/env bash
# Build a CONTROLLED REFERENCE OpenCV for the COOL comparison, from source, on the Graviton instance itself:
# Release, NEON baseline, bundled libjpeg-turbo/libpng/zlib (as in the pip wheels), pthreads parallel backend, no
# IPP/TBB/OpenMP/OpenCL, Arm KleidiCV switched OFF or ON.  Only the modules PROHORI imports are built (plus python3
# bindings); the OpenCV code in those modules is identical to a full build.
#
# Runs ON the Graviton instance (Ubuntu 24.04 arm64), NOT on the laptop.
# Usage: [OPENCV_REF=5.0.0|5.x@<UTC date>] [WITH_CONTRIB=1|0] \
#          bash build_opencv_ref.sh <install-prefix> <python-in-venv> <KLEIDICV=OFF|ON> <evidence-dir> [jobs]
#   OPENCV_REF   a tag (default 5.0.0, the version of the pip wheel) or "<branch>@<UTC timestamp>": the last commit of
#                that branch before the timestamp (used to rebuild the 5.1.0-dev snapshot COOL is built from:
#                COOL's build info says 2026-07-13T03:56:14Z, "Version control: unknown").
#   WITH_CONTRIB 1 = also build opencv_contrib (ximgproc) at the same ref (tags only).
# Output: <prefix>/lib/python3.12/site-packages/cv2 (add it to a venv with a .pth), plus in <evidence-dir>:
#   ref_<id>_commits.txt, ref_<id>_cmake_command.txt (the exact cmake invocation), ref_<id>_cmake_cache.txt (resolved
#   flags), ref_<id>_configure.log, ref_<id>_ninja.log, ref_<id>_build_time.txt     (<id> = ref + kleidi setting)
set -euo pipefail
PREFIX="${1:?prefix}"; PY="${2:?python}"; KLEIDI="${3:-OFF}"; EVID="${4:?evidence dir}"; JOBS="${5:-$(nproc)}"
REF="${OPENCV_REF:-5.0.0}"; CONTRIB="${WITH_CONTRIB:-1}"
ID="$(echo "$REF" | tr '@:/' '___')_k${KLEIDI}"
SRC="${SRC_DIR:-$HOME/ocvsrc}"
mkdir -p "$SRC" "$EVID"
t0=$(date +%s)
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential cmake ninja-build git pkg-config python3-dev >/dev/null

clone() { # repo dir
  local repo=$1 dir=$2
  [ -d "$dir" ] && return 0
  case "$REF" in
    *@*)
      local br="${REF%@*}" ts="${REF#*@}"
      local since; since=$(date -u -d "$ts - 4 days" +%F)
      git clone -q --shallow-since="$since" --branch "$br" "https://github.com/opencv/$repo" "$dir"
      git -C "$dir" checkout -q "$(git -C "$dir" rev-list -1 --before="$ts" "origin/$br")";;
    *) git clone -q --depth 1 --branch "$REF" "https://github.com/opencv/$repo" "$dir";;
  esac
}
OCV="$SRC/opencv_$(echo "$REF" | tr '@:/' '___')"
clone opencv "$OCV"
ARGS_EXTRA=()
LIST=core,imgproc,imgcodecs,calib3d,features2d,flann,objdetect,video
case "$REF" in *@*) LIST=core,imgproc,imgcodecs,calib,features,flann,objdetect,video,geometry; CONTRIB=0;; esac
{ echo "opencv $(git -C "$OCV" rev-parse HEAD) $(git -C "$OCV" log -1 --format=%cI) ref $REF"; } > "$EVID/ref_${ID}_commits.txt"
if [ "$CONTRIB" = 1 ]; then
  CON="$SRC/opencv_contrib_$(echo "$REF" | tr '@:/' '___')"
  clone opencv_contrib "$CON"
  echo "opencv_contrib $(git -C "$CON" rev-parse HEAD) ref $REF" >> "$EVID/ref_${ID}_commits.txt"
  ARGS_EXTRA+=(-DOPENCV_EXTRA_MODULES_PATH="$CON/modules"); LIST="$LIST,ximgproc"
fi
{ echo "gcc $(gcc --version | head -1)"; echo "cmake $(cmake --version | head -1)"; echo "kleidicv=$KLEIDI contrib=$CONTRIB"; } >> "$EVID/ref_${ID}_commits.txt"
NPINC=$("$PY" -c 'import numpy; print(numpy.get_include())')
PYINC=$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')
B="$SRC/build_${ID}"
rm -rf "$B"; mkdir -p "$B"
CMAKE_ARGS=(-S "$OCV" -B "$B" -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_INSTALL_PREFIX="$PREFIX"
  "${ARGS_EXTRA[@]}"
  -DBUILD_LIST="$LIST,python3"
  -DWITH_KLEIDICV="$KLEIDI"
  -DBUILD_JPEG=ON -DBUILD_PNG=ON -DBUILD_ZLIB=ON -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_OPENJPEG=OFF -DWITH_JASPER=OFF
  -DWITH_OPENEXR=OFF -DWITH_GTK=OFF -DWITH_FFMPEG=OFF -DWITH_GSTREAMER=OFF -DWITH_V4L=OFF -DWITH_OPENCL=OFF
  -DWITH_IPP=OFF -DWITH_TBB=OFF -DWITH_OPENMP=OFF -DWITH_PTHREADS_PF=ON
  -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF -DBUILD_opencv_apps=OFF
  -DBUILD_SHARED_LIBS=ON -DENABLE_NEON=ON
  -DPYTHON3_EXECUTABLE="$PY" -DPYTHON3_INCLUDE_DIR="$PYINC" -DPYTHON3_NUMPY_INCLUDE_DIRS="$NPINC"
  -DOPENCV_PYTHON3_INSTALL_PATH="$PREFIX/lib/python3.12/site-packages")
{ printf 'cmake'; printf ' %q' "${CMAKE_ARGS[@]}"; echo; } > "$EVID/ref_${ID}_cmake_command.txt"
cmake "${CMAKE_ARGS[@]}" > "$EVID/ref_${ID}_configure.log" 2>&1
grep -E "CMAKE_BUILD_TYPE|CMAKE_CXX_FLAGS|CPU_BASELINE|CPU_DISPATCH|WITH_KLEIDICV|ENABLE_NEON|WITH_PTHREADS|BUILD_JPEG|BUILD_LIST|CMAKE_C_COMPILER:|CMAKE_CXX_COMPILER:" "$B/CMakeCache.txt" > "$EVID/ref_${ID}_cmake_cache.txt" || true
ninja -C "$B" -j "$JOBS" > "$EVID/ref_${ID}_ninja.log" 2>&1
ninja -C "$B" install >> "$EVID/ref_${ID}_ninja.log" 2>&1
echo "build+install seconds: $(( $(date +%s) - t0 )) (jobs $JOBS, $(nproc) vCPU)" > "$EVID/ref_${ID}_build_time.txt"
echo "ok: cv2 in $PREFIX/lib/python3.12/site-packages"
