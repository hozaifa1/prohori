#!/bin/bash
cd /f/Projects/Prohori
PY="C:/Program Files/Python312/python"
st() { timeout 250 "$PY" eval/width_eval.py step --name "$1" --desc "$2" --cfg "$3" 2>&1 | tail -1; }
st resolv_weight "blend fault fix: blend weight from resolvability max(ink width, blur-inverted area/peak width)/sigma, q gate back on" '{"d_from":"max_ink_core_inv","q_gate":true}'
st q0_04 "q gate threshold q0 0.5 -> 0.4" '{"q0":0.4}'
st q0_06 "q gate threshold q0 0.5 -> 0.6" '{"q0":0.6}'
st d0_35 "d0 3 -> 3.5 (resolvability weight)" '{"d0":3.5}'
st d0_25 "d0 3 -> 2.5" '{"d0":2.5}'
st dscale_2 "dscale 3 -> 2" '{"dscale":2.0}'
