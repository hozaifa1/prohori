# WIDTHBENCH notes — krkCMd open width benchmark and the empirical px/mm gate curve

*2026-10-19 · TickTick D15 · code `src/prohori/widthbench.py`, CLI `eval/krkcmd_bench.py`, tests `tests/test_widthbench.py`, results `eval/results/krkcmd_*.{csv,md,png}`. Paper IDs (M1, M2, S8, S10, M5) refer to [LITERATURE.md](LITERATURE.md); thresholds to [METRICS.md](METRICS.md) §1a/§1b.*

## 0. Headline

1. **krkCMd cannot validate the absolute accuracy of the `measure.py` estimators. It can only bound what low resolution costs.** Against the operator reference `MANwidth`, every `measure.py` estimator misses the METRICS §1b Floor by a factor of 5: the final blend gets RMSE 313 µm on all 19,098 profiles (329 µm on crack-present ones), against 56 µm for the published AED. Floor is ≤ 1.2 × AED = 67 µm; Target is ≤ AED. In the 0.30–0.50 mm gate bin the blend's MAE is 0.24 mm at native resolution (0.14 mm after a best-case linear recalibration). **Pre-registered hypothesis (METRICS §1c) not supported on this dataset.** The profile integral does not beat the mask-based estimators against `MANwidth`. We publish that.
2. **Why (diagnosed, not guessed).** The operator marks the steepest-gradient edges of the *black crack core* and explicitly excludes bevelled crack-mouth shading (M1, Methods). The profiles hold a black plateau (75 % of crack-present profiles clip to grey 0) inside a wide shaded valley on textured concrete. `measure.py` integrates darkness over a fixed ±1.2 mm window with fixed-mm smoothing (σ = 0.12–0.15 mm), so it reads the valley plus the texture, not the core. A plain "width at 15 % of the way up from the minimum" gets MAE 13 µm in the gate bin at native resolution (all-profile RMSE 46 µm, below AED's 56), so the information is in the profiles. The estimator class is mismatched to this reference, not the data too noisy.
3. **Resolution cost, which is what the gate needs.** Measured as the error of the *same estimator* at a simulated resolution against itself at native (same profiles, bin 0.30–0.50 mm, MAE µm [95 % CI over specimen images]):

   | px/mm | 8 | 10 | 12 | 15 | 20 | 25 |
   |---|---|---|---|---|---|---|
   | windowed area (candidate) | 91 [71,106] | 76 [52,96] | 66 [44,85] | 54 [38,70] | 41 [29,54] | 34 [23,43] |
   | FWHM (`measure.py` arithmetic) | 80 [62,96] | 70 [52,87] | 66 [49,82] | 52 [39,65] | 41 [29,51] | 33 [25,41] |
   | `measure.py` blend | 197 | 188 | 178 | 142 | 112 | 92 |

   The blend's resolution-added error is 2–3× larger than FWHM's because it is unstable on textured profiles (the blend weight and the mask run flip between resolutions). That is a finding for the `measure.py` owner.
4. **Recommended gate: 20 px/mm for a "≤ 0.05 mm MAE" claim on 0.30–0.50 mm cracks (25 px/mm if you want the 95 % upper bound under 0.05 mm, or if optics are soft, PSF σ ≥ 1 px).** Details and limits in §5. The current `GATE_MIN_PX_PER_MM = 8` is **not supported** for a 0.05 mm-class claim: resolution alone adds about 0.09 mm MAE and 0.25 mm P95 at 8 px/mm. I did not change the gate.

## 1. Dataset (obtained and verified)

| item | value |
|---|---|
| Record | Zenodo concept DOI 10.5281/zenodo.11408398, resolved to v1.1 = 10.5281/zenodo.14568863 (2024-12-29, modified 2025-01-29), CC-BY 4.0 |
| Downloaded | `krkCMd_table.csv` 56,292,603 B (md5 310864b5e6628894bda052a89175ea51, matches Zenodo) and `krkCMd_scripts.zip` 273,175 B (md5 4a42050c…, matches), plus `zenodo_record.json`, in `data/datasets/krkcmd/` (git-ignored; `.cache.npz` is our float32 cache) |
| **Not** downloaded | `krkCMd_images.zip`, 38.6 GB of TIFF stacks. The profiles and all references are in the table, and no image is needed for a profile-level benchmark. The scans would only be needed to re-extract profiles at other geometries |
| Rows | 19,098 profiles, 510 columns: `No, Profile, Series, Image, Gridline, Stage, x1..x501, MANwidth, DLMwidth, AEDwidth`. No missing values |
| Profile | 501 real-valued brightness samples (0 = black … 255), 1 px apart along a grid line rotated perpendicular to the local crack axis (grid lines ≥ 100 px apart). Epson Perfection V600 flatbed CCD, 6400 dpi → **3.96875 µm/px = 251.97 px/mm**, no image correction at scan time. A profile is therefore only **1.99 mm** long |
| Units | widths in **µm** |
| Layout | 4 series (CMd_0.28 / CMd_0.23 concrete × 2 / 20 months old), 36 specimen images, 3,183 grid-line locations × 6 self-healing stages (0, 2, 4, 7, 14, 28 days). Rows are stage-ordered in stacks of 6 (verified) |
| `MANwidth` | One trained operator, ImageJ2 at 200 % zoom: pick the points of **greatest brightness gradient on each side of the central part of the crack**, take the distance between them, **excluding bevelled crack-edge areas**. Only the central crack on the grid line is measured. Values are whole pixels (multiples of 3.97 µm, verified). 0–813.6 µm. **4,900 profiles (25.7 %) have `MANwidth` = 0: the crack has healed** |
| Width distribution (crack-present, n = 14,198) | median 175 µm, 5–95 % = 36–448 µm. Bins by `MANwidth` (mm): 0–0.1: 3,865 · 0.1–0.2: 4,237 · 0.2–0.3: 2,897 · **0.3–0.5: 2,884** · 0.5–0.9: 315. Only 4.7 % are under 8 px (31.7 µm) |
| Shipped benchmarks | `DLMwidth` (CNN "metasensor", MATLAB), `AEDwidth` (analytic edge detector, VBA, thresholds on brightness) |

## 2. Citation → finding → how we use it

| Source | Finding (read at full text unless marked) | How used here |
|---|---|---|
| **M1** Jakubowski & Tomczak, *Sci. Data* 12:165 (2025), [10.1038/s41597-025-04485-z](https://doi.org/10.1038/s41597-025-04485-z), full text (Nature page + PMC11775250) | Scan geometry, grid-line extraction, operator edge criterion (above). Reference uncertainty: operator RMS **16.6 µm** (5 operators), specimen-position **7.4 µm**, moisture **18.2 µm**. DLM sensitivity: position 7.8 µm, moisture 25.5 µm; AED: 11.3 and 29.4 µm. Limitation (quoted in METRICS): may not transfer to smartphones. **The data descriptor reports no RMSE of DLM or AED against `MANwidth`.** | Definition of the reference; 16.6 µm drawn as the floor on the plots; baseline RMSEs computed by us from the CSV (METRICS §1b asks for exactly that) |
| Jakubowski & Tomczak, *Constr. Build. Mater.* 422:135768 (2024), [10.1016/j.conbuildmat.2024.135768](https://doi.org/10.1016/j.conbuildmat.2024.135768) | Paywalled (403). **Abstract-level only**: trains and tests the DLM on these 19,098 profiles, with data-drift evaluation and fine-tuning. Train/test split not obtainable | We treat the shipped `DLMwidth` as **in-sample** and say so in every table |
| Tomczak, Jakubowski & Fiołek, *Stud. Geotech. Mech.* 39:73 (2017) | Origin of the AED. Not read; cited only through the VBA header | Context only |
| `CrackWidthAED_VBA.txt` (Zenodo scripts, read in full) | AED stage 1 = number of pixels within **5 grey levels of the global minimum** around the first minimum, × 25.4/6400 mm. Later stages reuse the stage-1 window to decide "healed → 0". | Ported to Python (`aed_vba`). **Reproduces the shipped `AEDwidth` exactly on 98.25 % of rows** (RMSE vs `MANwidth` 55.8 µm for the port vs 56.0 µm for the CSV). The 1.75 % residual is VBA edge behaviour (reads cells beyond column 507). AED is therefore a black-plateau counter, which is why its bias is −23 µm overall and −51 µm in the gate bin |
| `CrackWidthDLM_Matlab.m`, `krknet.mat` | `krknet.mat` is a MATLAB 5 file holding a `SeriesNetwork` as an opaque MCOS object. Running it needs MATLAB's Deep Learning Toolbox. | **DLM cannot be re-executed outside MATLAB** (scipy loads only the opaque handle, no Python reader for MCOS layer objects exists, and I did not reverse-engineer the format). We use the shipped `DLMwidth` column as the DLM baseline. Not reproduced |
| **M2** Hassouna et al., *Sci. Rep.* 2026 (full text, via METRICS) | ≈10 px/mm phone pipeline: < 0.5 mm ratio 0.89, COV 21.9 %; ≥ 0.5 mm ratio 0.98, COV 5.8 % | Source of the Target/Floor tiers used as gate criteria; we compute the same ratio/COV/MRE per bin |
| **S8** Deng et al., *CACAIE* 2026 (full text, via METRICS) | MAE 0.09 mm, 33.9 % relative error on 0.45 mm crack | Context for the 0.05 mm target |
| **S10** Benz & Rodehorst, CVPRW 2024 (full text, via LITERATURE) | Human labels agree with the best model to the exact pixel only 16 % of the time | Supports the design rule that mask edges cannot carry the width claim. The same point shows here from the other side: the *definition* of the edge in a reference matters as much as the pixel |
| **M5** area conservation (our derivation, LITERATURE §2) | ∫(b − I) ds = C·w for any normalised PSF | Tested through `loc_core`, `loc_ink` and `cand_area`. Confirmed in synthetic tests (`test_widthbench.py`), **not** supported against `MANwidth` because the reference excludes shading that the integral includes |
| "Equal Area" (CACAIE 2025), OrthoBoundary (Autom. Constr. 2024) | Abstract-level only | Not used as evidence |

## 3. Baselines at native resolution (µm, all 19,098 profiles; refusals count as 0)

| method | RMSE all | RMSE crack-present | bias crack | note |
|---|---|---|---|---|
| AED, shipped CSV | **56.0** | 62.1 | −37.8 | published baseline. In the 0.3–0.5 mm bin: MAE 51.5, bias −51.3 (it fails the 0.05 mm Target there too) |
| AED, our port | 55.8 | 62.0 | −37.9 | 98.25 % exact |
| DLM, shipped CSV | **27.1** | 28.0 | −5.3 | in-sample; gate bin MAE 15.2 |
| `measure.py` blend, local background | 313 | 329 | +27 | fails Floor (67) |
| `measure.py` blend, as-is (6 mm running-max background) | 930 | 880 | +272 | fails |
| FWHM / 2·DT−1 / integral÷own core / integral÷board-ink | 315 / 368 / 467 / 311 | 296 / 353 / 446 / 330 | +192 / +241 / +46 / +36 | all fail |
| candidate: windowed area | 124 | 119 | +92 | not tuned to the reference definition |
| candidate: 15 %-depth crossing | **45.9** | **29.4** | +0.2 | operator-definition mimic, **not a product estimator** |

The published paper gives no RMSE against `MANwidth` to compare with, so "reproduction" means: the AED port matches the shipped AED column, and the RMSEs above are computed by us from the shipped columns (the METRICS §1b instruction).

## 4. Method

- **Estimators.** `profile_widths` is a 1-D reduction of `measure._measure_one` for a straight crack (distance-transform, FWHM, integral ÷ own core, integral ÷ board-ink, final blend). It calls `measure._fwhm`, `measure._bg_map` and `measure.INK_RATIO` directly and **never edits `measure.py`**. `pipeline_width` feeds the *unmodified* `_measure_one` with a synthetic straight-crack image (profile replicated down 24 mm, edge-padded). Fidelity check, 150 random profiles with `MANwidth` ≥ 100 µm: median |difference| 0–13 µm, correlation 0.86–0.98, 2–4 adapter refusals (report §6). The adapter is too slow (30–140 ms) for the full sweep, hence the reduction.
- **Two background modes.** `glob_*` = as-is: darkness relative to the 6 mm running-max map. On a 2 mm window of textured concrete that is the brightest pixel, so every width explodes (blend RMSE 930 µm). `loc_*` (headline) = line through the medians of the outer 0.2 mm of the window (the same two-band ramp `_measure_one` uses inside its profile integral). Ink reference = scanner black (linear 0), the analogue of the board's printed black; field mode (crack's own core) is `loc_core`.
- **Two candidates, not in `measure.py`, reported separately.** `cand_area`: area-conserving width over a window that follows the crack (half-depth extent + 2 blur sigmas), background from just outside the window, ÷ (bg − black). `cand_frac`: sub-pixel width at 15 % of the way from the profile minimum to the local background. **`cand_frac` mimics the operator's definition and is not a physically unbiased estimator** (it reads narrow on an ideal bar, see the unit test).
- **Degradation model** (`simulate_lowres`). Encoded → linear light; exposure normalised so the 98th-percentile background = 0.75 (camera auto-exposure); Gaussian PSF σ = 0.75 output px (sensitivity 0.5 and 1.0 px, METRICS §1b range) applied on the native grid; exact box integration over each output pixel (cumulative sum, fractional edges) at a **random sub-pixel phase** per profile; Poisson shot noise (full well 4,000 e⁻ at linear 1.0) + 3 e⁻ read noise; sRGB encode; round to 8 bit. It is added on top of the specimen's own edge softness (σ ≈ 19.5 µm median for wide cracks) and the scanner PSF already in the data, so it is conservative for the blur term. Fixed seeds, results independent of worker count. Native column = same exposure normalisation, no PSF, no noise, no resampling.
- **Estimators at low resolution** see the profile as `measure.py` would: cubic resample to S = clip(⌈ppm⌉, 12, 40) px/mm and the blend gets `sigma_mm` = √((σ_psf² + 1/12)/ppm² + σ_native²), the analogue of the board-edge fit.
- **Split and uncertainty.** 36 specimen images, alternate ones → 18 calibration / 18 test. All reported errors are on the **test half, crack-present profiles** (healed profiles with `MANwidth` = 0 are excluded at simulated resolutions, since a single-profile estimator has no way to say "healed"). Bootstrap CIs resample specimen images (200 draws), per METRICS §0.4. Calibrations: `raw`; `cal_native` = one linear map fitted at native on the calibration half and frozen; `cal_refit` = refit at each resolution. One noise realisation per profile.

## 5. The gate

**Criteria used (all on bin 0.30–0.50 mm, the thinnest regime the product claims, panel C1–C3; the literal "< 0.5 mm" bin is also in the CSV):**

- A. METRICS §1a Target against `MANwidth`: MAE ≤ 0.05, P95 ≤ 0.10, |bias| ≤ 0.02 mm, |ratio − 1| ≤ 0.05, COV ≤ 12 %.
- B. MAE ≤ 0.05 mm alone.
- C. METRICS §1b px-equivalent: RMSE ≤ 0.5 / ppm mm.
- D. **Resolution-added** (error vs the same estimator at native): MAE ≤ 0.05 mm (necessary condition), and a strict form (MAE ≤ 0.02, P95 ≤ 0.04, |bias| ≤ 0.01 mm).

A gate is the lowest swept resolution from which every higher one also passes (`gate_from_curve`).

**Result (`krkcmd_gate.csv`).**
- A, B, C against `MANwidth`: **no `measure.py` estimator passes at any resolution, native included**, raw or calibrated. The only passes are for the operator-mimic `cand_frac` at native 252 px/mm alone (MAE 13 µm). At 25 px/mm it reads 84 µm raw; with a bias refit at each resolution it reaches MAE ≤ 0.05 mm from 20 px/mm (42 µm) but still fails the full Target (criterion A) at every swept resolution. That refit curve is a data point for a threshold-type estimator, not a product claim.
- D (MAE ≤ 0.05): the stable estimators pass from **20 px/mm** (windowed area 41 µm, FWHM 41 µm; 2·DT−1 from 25). The strict form (P95 ≤ 0.04 mm) is never met at ≤ 25 px/mm. P95 of the added error is still 0.12 mm at 25 px/mm, because textured concrete has heavy tails.
- 95 % CI (specimen images) of the added MAE at 20 px/mm: windowed area [29, 54], FWHM [29, 51]. **The upper bounds touch 0.05 mm at 20 and clear it at 25** (43 and 41).
- PSF sensitivity (3,000-profile subsample, added MAE of windowed area at 15 / 20 / 25 px/mm): σ = 0.5 px → 61 / 47 / 35; 0.75 → 54 / 41 / 34; **1.0 → 78 / 61 / 48**. With soft optics the 0.05 mm bound moves to 25 px/mm.

**Recommendation (not applied):** the gate that this evidence supports for certifying "≤ 0.05 mm MAE on 0.30–0.50 mm cracks" is **20 px/mm nominal, 25 px/mm if the gate must hold under a 95 % upper bound or PSF σ ≈ 1 px**. Between 12 and 20 px/mm the added error is 0.04–0.07 mm, so a reading can still be issued with an interval that widens as resolution falls (added P95 ≈ 0.25 / 0.20 / 0.19 / 0.14 mm at 8 / 12 / 15 / 20 px/mm for the windowed area estimator), not a bare number. The locked concept's 15 px/mm sits at the edge (54 µm [38, 70]); **8 px/mm cannot carry a 0.05 mm claim**, though it may still support a coarser, interval-qualified statement. METRICS §6 (ppm 8–25) and the `GATE_NOTES` calibration should confirm this on the printed panel.

**What this number is and is not.** It is a necessary condition from an independent dataset: resolution alone may not eat the error budget. It is **not** sufficient (the estimator's own error at native must be added in quadrature, and krkCMd tells us nothing about that for `measure.py`). It comes from textured, heterogeneous concrete scans, which is harsher than a uniform printed panel, so it is probably conservative for the panel and closer to right for real walls. The sweep is coarse (8, 10, 12, 15, 20, 25), the data are 36 images from one lab and one scanner, and the degradation model is mine. The 16.6 µm operator RMS is below every number quoted here, so reference noise does not change the conclusion.

## 6. Findings for the `measure.py` owner (nothing edited)

1. The mask stage's background (`_bg_map`, 6 mm running max) over-reads massively when the substrate is textured (RMSE 930 µm vs 313 µm with a local two-band background). On real concrete walls this matters more than on the printed panel.
2. σ = 0.12–0.15 mm Gaussian smoothing is fixed in millimetres. For cracks narrower than ≈ 0.3 mm the FWHM, the DT mask and the peak `Dcore` become dominated by the smoothing, not the crack (the DT width saturates near 0.3–0.5 mm). Scaling the smoothing to the crack or blur width would remove that.
3. The ±1.2 mm profile window integrates substrate texture: on krkCMd the integral estimators scatter by 0.25 mm MAE where a window following the crack gets 0.09 mm.
4. The final blend is unstable between resolutions on textured profiles (added error 2–3× that of FWHM alone).

## 7. Not done / limits

- DLM not re-run (MATLAB-only network). Published RMSE vs `MANwidth` for DLM/AED could not be found (the data descriptor does not state it; the CBM 2024 paper is paywalled).
- Source TIFF images (38.6 GB) not downloaded or used.
- No test of `measure.py` on real krkCMd images; only on profile-derived straight-crack images, which assume a straight crack with constant profile.
- Healed (`MANwidth` = 0) profiles are included only in the native all-profile baseline, not in the resolution sweep.
- One noise realisation per profile, one random seed for the full run; PSF sensitivity on a 3,000-profile subsample only.
- The candidate estimators were chosen after looking at native-resolution results on a 3,000-profile sample drawn from all profiles (calibration and test halves alike), so their native numbers are mildly optimistic; the resolution-*added* curves, which carry the gate, do not depend on the reference.
