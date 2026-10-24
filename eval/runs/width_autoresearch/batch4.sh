#!/bin/bash
cd /f/Projects/Prohori
PY="C:/Program Files/Python312/python"
st() { timeout 250 "$PY" eval/width_eval.py step --name "$1" --desc "$2" --cfg "$3" 2>&1 | tail -1; }
st wide_fwhm_raw "wide estimator = raw FWHM (no blur inversion)" '{"wide":"fwhm"}'
st agg_trim "crack width = interquartile-band mean of the station widths instead of the median" '{"agg":"trim"}'
st smooth_k_09 "smoothing scaled to blur: k 1.2 -> 0.9" '{"smooth_k":0.9}'
st smooth_k_16 "smoothing scaled to blur: k 1.2 -> 1.6" '{"smooth_k":1.6}'
st qscale_02 "q gate ramp width 0.1 -> 0.2" '{"qscale":0.2}'
st mask_sigma_020 "mask smoothing 0.15 -> 0.20" '{"mask_sigma_mm":0.20}'
st inv_sigma_090 "blur inversion uses 0.9 x measured sigma" '{"inv_sigma_scale":0.9}'
st ink_ratio_093 "ink_ratio 0.90 -> 0.93" '{"ink_ratio":0.93}'
