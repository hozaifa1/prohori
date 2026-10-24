# WIDTH_AUTORESEARCH: the crack-width estimator, tuned and tested out of sample (TickTick D18)

*Started 2026-10-24. The objective, guard rails, splits and candidate list in sections 1-4 were written before the first candidate was run; the toner-corrected reference (section 3) was added on the orchestrator's instruction after iteration 15 and the loop was restarted from LEGACY (section 6). Code: `src/prohori/measure.py` (`CFG`, `LEGACY_CFG`, `_station_widths`), harness `eval/width_eval.py`, `eval/width_krk.py`, `eval/width_final.py`; machine-readable log `eval/runs/width_autoresearch/log.tsv` (every iteration, plus `scan_log.tsv` for the quick pre-screens); final report `eval/results/width_eval.md`. Paper IDs (M1, M2, M5, S8, ...) refer to [LITERATURE.md](LITERATURE.md); tiers to [METRICS.md](METRICS.md) section 1a.*

## 1. Question and objective (fixed before tuning)

The entry's core claim is a crack width in mm with a published error. The legacy estimator (`LEGACY_CFG`, the 2026-10-19 blend of a board-ink area estimator and an edge-based FWHM) was tuned in-sample on the first 29 photos. D18 asks: is there a more accurate estimator, and does it hold on data it never saw?

**Objective J (minimise, TUNE data only).** `J = 0.5 * MAE_panel + 0.5 * MAE_synth`. MAE is the mean absolute width error over all measured cracks (every gate state, so a refused crack still counts). Panel = real phone photos of the printed test panel; synth = photoreal renders with exact per-station widths (references up to 3.0 mm, the panel's widest specimen). Two independent sources of truth so that neither a printer artefact nor a renderer artefact can be fitted alone.

**Keep rule.** A change is kept if J falls by at least 0.2 % relative and no guard rail trips. Otherwise it is discarded and logged. One change per iteration.

## 2. Guard rails (a kept change must pass all of them, against the previous best AND against LEGACY)

1. No `< 0.5 mm` metric (MAE, MRE, P95, |bias|) of either dataset may worsen by more than 10 % (plus 2 um slack).
2. Panel certified-only MAE (frozen gate) may not exceed LEGACY's under the same truth by more than 10 % (orchestrator decision 2026-10-24; the certified number is what the product shows).
3. krkCMd resolution-added error of the headline width at 15 px/mm in the 0.30-0.50 mm gate bin: no worse than 2 % against the previous best, not worse than LEGACY. This is the "stable between resolutions" test (WIDTHBENCH section 6, item 4); it runs the real `_measure_roi` on profile-derived images, an independent third leg.
4. Coverage (fraction of expected cracks measured) may not fall by more than 2 points (panel) / 3 points (synth).
5. The certification gate (`gate.py`, `gate_params.json`) is frozen and not refitted inside the loop.

Near misses are reported, not waived: `agg = trim` (interquartile-band mean) lowered J by 2.2 % twice but moved the synthetic < 0.5 mm bias from 0.004 to 0.008 mm, which trips guard 1 (10 % + 2 um slack on a bias that small). It stays discarded.

## 3. Reference (truth) and its uncertainty

* **Synthetic**: exact per-station widths of the renders.
* **Panel, primary truth: toner-corrected.** The METRICS 1a protocol: `w_ref = w_nominal + 2 b`, `b` = per-edge toner bleed measured on the same photos from the printed ChArUco squares, independent of every crack estimator. Method (`eval/width_eval.py: measure_bleed`): rectify the board at native resolution; along scan strips inside the marker-free margins of every square row and column take the 50 % crossings between local toner-black and paper-white plateaus in linear light (where blur is a convolution, so symmetric blur does not shift a 50 % crossing); black-square width = 20 s + 2b, white-square width = 20 s - 2b (s = print scale), so `b = (mean black - mean white) / 4` and the scale cancels.
* **Pooling rule (fixed without looking at b).** All photos are of one printed sheet, so there is one true bleed and per-photo scatter is measurement noise. A photo enters the pool if it shows at least 18 of 24 corners, has board-edge blur sigma <= 0.15 mm and obliquity <= 25 degrees, and a measurement was produced. 14 of the 20 photos with a measurable board pass. The pool value is the robust median; the spread is the median absolute deviation across photos.
* **Result.** `b_y = 0.0137 mm` (MAD-sd 0.0047), `b_x = 0.0406 mm` (MAD-sd 0.0044). The bleed is anisotropic. All eight specimens run along the board x axis, so the bleed across them is `b_y` (a specimen's normal mixes the two by its mean squared normal components, 0.014-0.05 for x). `w_ref = nominal + 0.027 mm`.
* **U_ref = +-0.009 mm** on `w_ref` (2 x the across-photo sd). METRICS section 0 rule 5: no error below this is meaningful; every final table prints it next to the MAE.
* **The anisotropy is the print, not the camera.** A print property stays tied to the board axes whatever the camera roll; a camera or ISP artefact stays tied to the image axes. The pooled photos were shot at camera rolls of about -94..-83 degrees, -5..0, 91..92 and 180 degrees (the board x axis runs along image x in some, along image y in others) and `b_x > b_y` holds in every one of them, so the board-frame model is right. Limitation: the roll takes only these few discrete values, so a purely mixed model cannot be excluded, but a camera-axis artefact would have swapped between the roll = 0 and roll = 90 groups and did not.
* **Limitations of the reference.** (a) Dot gain depends on feature size: bleed measured on 20 mm squares may differ on 0.30-0.50 mm strokes, so the corrected truth of the thin specimens carries this extra caveat (the corrected thin-crack bias of +0.02 to +0.03 mm is of that order). (b) U_ref = +-0.009 mm. (c) One print, one phone, one session.
* The nominal truth is reported alongside as a secondary column. Before the switch, half of J was teaching the estimator to imitate the toner bleed (the < 0.5 mm panel bin read ratio 1.14 against 1.05 on exact synthetic truth).

## 4. Frozen splits (frozen before any width was looked at; `eval/runs/width_autoresearch/split.json`)

| Source | Unit of split | TUNE | TEST | Rule |
|---|---|---|---|---|
| Panel photos | photo group (burst frames of one scene together) | 14 photos / 13 groups | 8 photos / 8 groups | usable groups shuffled with seed 20261024, first 60 % (rounded up) TUNE. 7 photos with no board or no crack ROI are unusable |
| Synthetic renders (`data/synth/v1`) | render id | 300 | 200 | same seed, 60 % TUNE |
| krkCMd profiles | specimen image (cluster) | even-indexed clusters (calibration half), 600 gate-bin + 400 other profiles subsampled | odd-indexed clusters, all | widthbench's alternate-image split |

The TEST split is reachable only through `python eval/width_final.py --split test --go`, which refuses to run twice (`eval/runs/width_autoresearch/test_run_done.json`). The TUNE panel set is small (105 cracks from 14 photos), so only few-parameter, physically motivated candidates were tried and the TUNE/TEST gap is reported whatever it is.

Board detection, rectification, locator and ROI extraction do not depend on the width estimator, so they are cached (`measure._prepare`; `eval/runs/width_autoresearch/cache`); a variant costs `measure._finish` only (about 10 s for panel + synth, about 35 s with the krkCMd leg).

## 5. Candidates, motivation and outcome

| # | Candidate | Motivation (citation -> finding -> use) | Outcome (iteration numbers in log.tsv) |
|---|---|---|---|
| C1 | Smoothing scaled to the measured optical blur (`smooth_k`, `smooth_floor_mm`) | WIDTHBENCH section 6 item 2 (own krkCMd measurement): fixed 0.12-0.15 mm smoothing makes FWHM, DT mask and `Dcore` smoothing-limited below 0.3 mm -> scale the smoothing sigma to the blur already measured from the board edges | k = 0.6 rejected (6); k = 1.2 **kept** (24, J -1.2 %, krk resolution-added 0.1221 -> 0.1178); k = 0.9, 1.6 rejected (37, 38); `prof_sigma` 0.08 and `mask_sigma` 0.10 / 0.20 rejected (guards or no gain) |
| C2 | Blend stability: continuous weight; FWHM where resolved | WIDTHBENCH section 6 item 4: the blend's resolution-added error was 2-3x FWHM's (0.130 vs 0.053 mm at 15 px/mm) -> the hard `d`, `q` switches become a ramp starting earlier | blend switch 5/6 -> **3/3 sigma kept** (20, J -12 %: the single largest gain, almost all of it on >= 0.5 mm cracks); q gate off alone rejected on the corrected truth (22 kept it, then re-gated, see C6) |
| C3 | FWHM with closed-form blur correction | M5 + Gaussian-PSF algebra: for a bar of width w blurred by a Gaussian of sigma s the half-maximum width is a known monotone function of w/s (table `_bar_tables`, tested in `tests/test_measure.py`) -> invert it | **kept** as the resolved-crack estimator (19, +0.4 % on its own: a small effect, because for a resolved bar FWHM ~ w anyway; its value is in the 3-6 sigma ramp). Raw FWHM instead of inverted rejected (35) |
| C4 | Better contrast C for the area estimator | M5: `integral = C w`; board ink x 0.90 is a panel calibration (measured: the printed strokes are only 0.72-0.89 of the board black, and in the renders the opposite sign), so a resolved crack should use its own contrast | tried as (a) MAP bar-model fit with an ink-contrast prior (7), (b) precision-weighted own-plateau / board-ink contrast (scan only), (c) area / peak with blur inversion (scan only): all worse than FWHM for resolved cracks. Reason found: the area-equivalent width of a printed stroke differs from its edge-to-edge width by 3-5 % (non-flat toner profile), so the edge definition (FWHM) is the geometric one. The own-plateau idea survives only as the resolvability measure in C6 |
| C5 | Re-tune of `ink_ratio`, `d0`, `q0` | GATE_NOTES section 7: a leave-one-photo-out re-tune did not generalise | `ink_ratio` 0.85 / 0.93 / 0.95 rejected (13, 27, 28, 42, 51); `q0` 0.4 / 0.6 rejected (30, 31, 49); `d0` 2.5 / 3.5 / 4, `dscale` 2 rejected (21, 32, 33, 34, 47, 48) |
| C6 | Diagnosis of the biggest residuals | section 7 | **blend-fault fix kept** (29, 43): resolvability measure that does not depend on how dark the stroke is (`d_from = max_ink_core_inv`), and a q gate that fades out for clearly resolved cracks (`q_release` 4.5 -> 6 sigma) |

Not done: a per-station weight, a learned weight, an estimator with more than the six parameters in `SHIPPED_DELTA`.

## 6. Loop history

* **Epoch 1 (iterations 0-15, nominal panel truth).** LEGACY baseline J = 0.1101 -> 0.0942 at iteration 15. Superseded: judged against a truth that contains the toner bleed.
* **Truth switch (16-17) and restart (18).** Under the toner-corrected truth LEGACY scores J = 0.1110 (panel 0.1200, synthetic 0.1020). The iteration-15 configuration scored 0.0967 but its panel < 0.5 mm MAE (0.0565 vs 0.0434) and certified MAE (0.0557 vs 0.0498) were worse than LEGACY's, so it violated the new guard 2. The earlier "gain" on thin cracks was partly fitting the bleed. The loop restarted from LEGACY and every earlier change was re-tested one at a time (rows 19-28, named `r_*`).
* **Epoch 2 (iterations 19-51).** Kept: 19 (blur-inverted FWHM), 20 (blend switch 3/3), 22 (q gate off), 24 (smoothing scaled to the blur), 29 (resolvability weight, q gate back on), 43 (q gate released for resolved cracks). Iterations 44-51: no further keep (eight consecutive discards; six of them are re-tests of earlier near misses against the new best): a plateau.
* 51 logged iterations in total, plus the quick pre-screens in `scan_log.tsv` and three unlogged attempts of C4. TUNE J: LEGACY 0.1110 -> shipped 0.0903 (-18.6 %).

## 7. Diagnosis of the residuals (measured, not guessed)

Per-specimen residuals are in `eval/results/width_eval.md` (panel nominal and corrected, synthetic binned alike). Findings, all on the TUNE split:

1. **Blend fault (an estimator fault, fixed).** The board-ink area estimator assumes the crack plateau is as dark as the board toner. In several photos the printed strokes' plateau is 0.55-0.74 of the board black, so the ink-area width is biased low by about that factor, and the blend weight (computed from the ink-area width) stayed at 0.2-0.5 where it should have been 1 (for example IMG...0807, specimen C7 of 2.0 mm: FWHM 1.91 mm, headline 1.24 mm). The weight now uses `max(ink-area width, blur-inverted area/peak width) / sigma`, and the q gate (plateau contrast against board ink) is released for clearly resolved cracks. The 2.0 mm panel specimen's bias went from -0.357 to -0.237 mm and the 3.0 mm one from -0.268 to -0.165 mm.
2. **Distance from the board (geometry, not the estimator).** The board homography is fitted on a 140 x 100 mm board and extrapolated up to 234 mm. On sharp frontal photos (blur sigma <= 0.15 mm, obliquity <= 25 degrees) the relative width error falls from +2.8 % at 0.23 board widths to -2.7 % at 0.96 board widths (shipped; LEGACY +5.8 % to -2.9 %). Across all photos it falls from +7.6 % to -8.4 %, and the residual error of the 2.0 and 3.0 mm specimens (-0.24 and -0.17 mm) comes from four photos with obliquity of 32-42 degrees or blur sigma of 0.3 mm (IMG...0746, 0802 x2, 0807, 0819). Important confound: in this panel distance and width are not independent (thin specimens near the board, wide ones far), so the part of the trend caused by the estimator at different widths cannot be separated from the scale extrapolation. Figure: `eval/results/width_distance.png`.
3. **Single-view radial distortion (attempted, failed; time-boxed).** `cv2.calibrateCamera` on the 24 corners of one view with focal length fixed (0.78 x the long side), principal point fixed, k1 only, undistortion applied before the homography (`eval/runs/width_autoresearch/k1_try.py`, 12 TUNE photos). Reprojection RMS was 1.1-5.4 px, k1 came out between -0.044 and +0.153 with no consistent sign, and the panel MAE got worse (0.0758 -> 0.0842 mm, far-specimen bias -2.7 % -> -6.7 %). A single planar view that covers a third of the frame cannot separate k1 from the focal length. Not adopted. The old path is untouched.
4. **Proposed distance rule (for the gate-refit job, nothing changed here).** On sharp frontal captures no specimen up to 0.96 board widths (134 mm from the board edge) is more than 3 % low; on oblique (> 25 degrees) or blurred (sigma > 0.15 mm) captures the error at 0.7-1.0 board widths reaches 8 % on average and 0.5 mm on single cracks. Suggestion: certify only cracks within 0.7 board widths (about 100 mm) of the board, and beyond that only if obliquity <= 25 degrees and blur sigma <= 0.15 mm (both already gate features). Evidence is one printed layout; it is not a validated rule.
5. **Thin cracks.** The corrected-truth panel bias for 0.30-0.50 mm is +0.01 to +0.03 mm, the synthetic one is 0 to +0.01 mm. The remaining difference is of the order of U_ref and of the thin-stroke dot-gain caveat, so the thin-crack estimator was not pushed further on the panel.
6. **krkCMd.** The resolution-added error of the headline width at 15 px/mm fell from 0.130 to 0.118 mm; FWHM alone is 0.045-0.053 mm. The blend remains less stable than FWHM on textured profiles (open). Black-core convention (`width_blackcore_mm`): `core_corr_k` was scanned on krkCMd TUNE (0, 0.8, 1.2, 1.7, 2.0, 2.4) and set to 1.7 (gate-bin MAE 0.047 mm at 15 px/mm, bias -0.014 mm); the bias depends on the simulated resolution (+0.08 mm at 10 px/mm, -0.06 mm at 20 px/mm), so the convention is accurate only near the 15 px/mm operating point. The all-profile RMSE vs `MANwidth` at 15 px/mm is 0.16 mm, against 56 um for the published edge detector at native 252 px/mm: not comparable one-to-one, and clearly not a parity claim.

## 8. Shipped configuration

`measure.CFG = {**LEGACY_CFG, **SHIPPED_DELTA}`:

```
estimator "mix", wide "fwhm_inv", d_from "max_ink_core_inv", d0 3, dscale 3, q_gate True, q_release 4.5, q_release_scale 1.5,
smooth_k 1.2, core_corr_k 1.7 (black-core output only)
```

`LEGACY_CFG` reproduces the old estimator exactly (`analyze(img, cfg=measure.LEGACY_CFG)`, tested). Output keys of `analyze` are unchanged (checked by a test). **The shipped width values changed**, so the certification gate (fitted on the legacy widths) has to be refitted by the orchestrator. The refit should also use the new `q_core` / `wt_core` semantics only if the gate uses them as features: `wt_core` is now the weight of the resolved-crack estimator in a continuous blend (the same meaning, a different curve).

## 9. Held-out result

See `eval/results/width_eval.md` (TEST, evaluated once) with the tune/test comparison, the METRICS tiers, M2 and S8 comparisons, the error distribution and error-vs-px/mm figures.
