#!/bin/bash
cd /f/Projects/Prohori
PY="C:/Program Files/Python312/python"
st() { timeout 200 "$PY" eval/width_eval.py step --name "$1" --desc "$2" --cfg "$3" 2>&1 | tail -1; }
st wide_fit "wide estimator = MAP bar-model fit (Gaussian blur from the board, ink-contrast prior)" '{"wide":"fit"}'
st d_from_fwhminv "blend weight from the blur-inverted FWHM width instead of the ink-area width" '{"d_from":"fwhm_inv"}'
st prof_sigma_008 "profile smoothing 0.12 -> 0.08 mm" '{"prof_sigma_mm":0.08}'
st mask_sigma_010 "mask smoothing 0.15 -> 0.10 mm" '{"mask_sigma_mm":0.10}'
st smooth_k_12 "smoothing scaled to blur: min(fixed, 1.2 * sigma)" '{"smooth_k":1.2}'
st ink_ratio_095 "ink_ratio 0.90 -> 0.95" '{"ink_ratio":0.95}'
st ink_ratio_085 "ink_ratio 0.90 -> 0.85" '{"ink_ratio":0.85}'
st inv_sigma_085 "blur inversion uses 0.85 x measured sigma" '{"inv_sigma_scale":0.85}'
st inv_sigma_115 "blur inversion uses 1.15 x measured sigma" '{"inv_sigma_scale":1.15}'
