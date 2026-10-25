#!/usr/bin/env bash
# bash infra/cool_loop_tree.sh <git-rev> <out.tgz>   a full checkout of src/ + data/print of <git-rev>, overlaid with the CURRENT
# working-tree harness (eval/cool_bench.py cool_compat.py cool_loop.py cool_profile.py) so every variant is measured by the same harness.
set -euo pipefail
cd "$(dirname "$0")/.."
rev="${1:?rev}"; out="${2:?out}"
tmp=$(mktemp -d)
git archive "$rev" src data/print | tar -x -C "$tmp"
mkdir -p "$tmp/eval"
cp eval/cool_bench.py eval/cool_compat.py eval/cool_loop.py eval/cool_profile.py "$tmp/eval/"
find "$tmp" -name __pycache__ -prune -exec rm -rf {} +
tar -czf "$out" -C "$tmp" .
rm -rf "$tmp"
ls -la "$out"
