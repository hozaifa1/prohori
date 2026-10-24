#!/bin/bash
cd /f/Projects/Prohori
PY="C:/Program Files/Python312/python"
st() { timeout 250 "$PY" eval/width_eval.py step --name "$1" --desc "$2" --cfg "$3" 2>&1 | tail -1; }
st agg_trim2 "re-test after q release: interquartile-band mean of the station widths" '{"agg":"trim"}'
st dscale_2b "re-test after q release: dscale 3 -> 2" '{"dscale":2.0}'
st d0_25b "re-test after q release: d0 3 -> 2.5" '{"d0":2.5}'
st q0_04b "re-test after q release: q0 0.5 -> 0.4" '{"q0":0.4}'
st prof_sigma_008b "re-test after q release: profile smoothing 0.08 mm" '{"prof_sigma_mm":0.08}'
st ink_ratio_095b "re-test after q release: ink_ratio 0.95" '{"ink_ratio":0.95}'
