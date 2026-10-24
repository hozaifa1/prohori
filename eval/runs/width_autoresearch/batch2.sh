#!/bin/bash
cd /f/Projects/Prohori
PY="C:/Program Files/Python312/python"
st() { timeout 250 "$PY" eval/width_eval.py step --name "$1" --desc "$2" --cfg "$3" 2>&1 | tail -1; }
st r_fwhm_inv "truth=corrected, rerun of iter 2: wide = FWHM with closed-form blur inversion (mix, q gate on)" '{"estimator":"mix","wide":"fwhm_inv"}'
st r_d0_3_3 "truth=corrected, rerun of iter 4: blend switch d0 3 dscale 3" '{"d0":3.0,"dscale":3.0}'
st r_d0_4_3 "truth=corrected: blend switch d0 4 dscale 3" '{"d0":4.0,"dscale":3.0}'
st r_q_gate_off "truth=corrected, rerun of iter 5: drop the q gate" '{"q_gate":false}'
st r_inv_sigma_115 "truth=corrected, rerun of iter 15: blur inversion uses 1.15 x measured sigma" '{"inv_sigma_scale":1.15}'
st r_smooth_k_12 "truth=corrected, rerun of iter 11: smoothing min(fixed, 1.2 sigma)" '{"smooth_k":1.2}'
st r_prof_sigma_008 "truth=corrected, rerun of iter 9: profile smoothing 0.08 mm" '{"prof_sigma_mm":0.08}'
st r_mask_sigma_010 "truth=corrected, rerun of iter 10: mask smoothing 0.10 mm" '{"mask_sigma_mm":0.10}'
st r_ink_ratio_095 "truth=corrected, rerun of iter 12: ink_ratio 0.95" '{"ink_ratio":0.95}'
st r_ink_ratio_085 "truth=corrected, rerun of iter 13: ink_ratio 0.85" '{"ink_ratio":0.85}'
