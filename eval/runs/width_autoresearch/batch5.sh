#!/bin/bash
cd /f/Projects/Prohori
PY="C:/Program Files/Python312/python"
st() { timeout 250 "$PY" eval/width_eval.py step --name "$1" --desc "$2" --cfg "$3" 2>&1 | tail -1; }
st q_release_45 "q gate released for clearly resolved cracks (d from 4.5 to 6 sigma): blur-limitation, not plateau darkness, is what the gate should test" '{"q_release":4.5,"q_release_scale":1.5}'
st q_release_5 "q release start 4.5 -> 5.0" '{"q_release":5.0,"q_release_scale":1.5}'
st q_release_55 "q release start 5.5, scale 1" '{"q_release":5.5,"q_release_scale":1.0}'
