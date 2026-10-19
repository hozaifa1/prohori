# PROHORI — Evaluation metrics, benchmarks and target thresholds

*Compiled 2026-09-18. Every threshold below cites the paper that anchors it. Paper IDs (S#, M#, A#, B#) refer to [LITERATURE.md](LITERATURE.md). A threshold with no citation is marked **[eng]**: an engineering target set by us, not by the literature.*

## 0. Reporting rules (apply to every section)

1. **No single headline number.** Width is always reported **per width bin**, as a distribution: bias, MAE, P95 |error| and a coverage-checked interval.
2. **Width bins follow the literature**, so results compare directly: **< 0.5 mm** and **≥ 0.5 mm** (M2, S8), and also per specimen (C1–C8 = 0.30, 0.40, 0.50, 0.75, 1.0, 1.5, 2.0, 3.0 mm).
3. **Crack-class IoU, not 2-class mIoU.** Where a paper reports 2-class mIoU (S1, S2, S3, S4), we also show crack IoU. From the same TP/FP/FN counts, **IoU = F1 / (2 − F1)** exactly.
4. **Confidence intervals** are 95% percentile bootstraps over *capture sessions*, not frames, because frames within a session are correlated.
5. **The reference has an uncertainty, and it is reported.** No claimed error may be smaller than the reference's own uncertainty (M1 shows even expert operators disagree by an RMS of 16.6 µm).
6. **Calibration and test data are split by session.** Conformal guarantees (A3, A5) assume exchangeability, so calibration captures are never reused for test.

---

## 1. Crack-width metrology — the primary claim

### 1a. Instrumented test panel (`data/print/PRINT_ME_test_panel_A4.pdf`)

**Ground truth protocol.**
- **Nominal widths are corrected for toner spread without extra equipment.** Printers spread toner, so a printed line comes out slightly wider than its nominal width. The fix needs no scanner and no extra task for Hozaifa; it uses the same desk photos. The same sheet carries wide black features of exactly known nominal size (ChArUco marker borders and squares). Toner bleed per edge is `b = (measured − nominal) / 2` on those wide features, where the estimator is accurate. The crack reference is then `w_ref = w_nominal + 2b`, and U_ref is the spread of `b` across features and captures. This is the printed standard-chart approach (Zhu et al., CACAIE 2024, AB), self-calibrated from the same image.
- **Synthetic renders** (known exact widths, controlled blur, noise and perspective) and the **krkCMd profiles** (§1b) supply the remaining ground truth. Real-crack photos are opportunistic only and are never required.

**Metrics** (per specimen and per bin, at each capture condition):

| Metric | Definition |
|---|---|
| Bias | mean(ŵ − w_ref) |
| MAE | mean \|ŵ − w_ref\| |
| P95 | 95th percentile of \|ŵ − w_ref\| |
| Ratio | mean(ŵ / w_ref) — M2's format |
| COV | SD(ŵ / w_ref) / mean(ŵ / w_ref) — M2's format |
| MRE | mean \|ŵ − w_ref\| / w_ref — S8 and M2 format |
| Error curves | MAE vs px/mm, vs obliquity θ, vs blur (Laplacian variance) |

**Thresholds** (all at or above the certification gate, after aggregating N ≥ 5 rectified frames):

| Tier | < 0.5 mm bin | ≥ 0.5 mm bin | Overall | Anchor |
|---|---|---|---|---|
| **Floor** (parity with the published state of the art — below this, do not claim anything) | ratio ∈ [0.89, 1.11], COV ≤ 21.9% | ratio ∈ [0.98, 1.02], COV ≤ 5.8% | MAE ≤ 0.09 mm, MRE ≤ 14.4%, max \|err\| ≤ 0.15 mm | M2 (smartphone + checkerboard, ≈10 px/mm): < 0.5 mm ratio 0.89 / COV 21.86%; ≥ 0.5 mm ratio 0.98 / COV 5.77%. S8 (LiDAR + camera + IMU): MAE 0.09 mm, MRE 14.37%, max AE 0.15 mm |
| **Target** (the "beats the literature" claim) | \|ratio − 1\| ≤ 0.05, COV ≤ 12% | \|ratio − 1\| ≤ 0.02, COV ≤ 4% | **MAE ≤ 0.05 mm**, **P95 ≤ 0.10 mm**, \|bias\| ≤ 0.02 mm | Halves M2's thin-crack COV and removes its 11% under-read. 0.05 mm = the resolution of M2's reference instrument (microscope + comparator) |
| **Stretch** | COV ≤ 8% | COV ≤ 3% | MAE ≤ 0.03 mm | ≈ 0.45 px at 15 px/mm. Only reachable with the sub-pixel profile estimator (LITERATURE §2, M5) |

**Worked check against the locked error budget.** At 15 px/mm, ±1 px of edge placement per side gives ±0.13 mm (ENTRY_PROHORI_FINAL). The Target tier therefore **requires sub-pixel estimation** (M5). A binary-mask estimator should land near the Floor tier. That prediction is falsifiable, and it is exactly what campaign C1 tests.

### 1b. Open width benchmark — krkCMd (M1, *Scientific Data* 2025)

Source: Zenodo [10.5281/zenodo.11408398](https://doi.org/10.5281/zenodo.11408398), CC-BY 4.0. It has 19,098 grey-level profiles at 252 px/mm, each with an operator reference width (`MANwidth`) and two benchmark predictions (`DLMwidth` from the CNN, `AEDwidth` from the analytic edge detector).

| Metric | Definition | Threshold |
|---|---|---|
| RMSE vs `MANwidth` at native resolution | on all 19,098 profiles | **Baseline = RMSE(AEDwidth) and RMSE(DLMwidth), computed by us from the CSV.** Target: Prohori estimator ≤ AED RMSE. Floor: within 1.2× AED RMSE |
| Irreducible floor | inter-operator RMS | **16.6 µm** (M1). No claimed RMSE below this is meaningful |
| RMSE vs simulated phone resolution | profiles box-integrated and decimated to **10 / 15 / 20 / 25 px/mm**, then a Gaussian PSF (σ = 0.5–1.0 px) and shot noise are added | **[eng]** Target: RMSE ≤ 0.5 px-equivalent (≤ 33 µm at 15 px/mm) on profiles with w_ref ≥ 1 px. This curve **sets the px/mm gate empirically**: the gate is the lowest px/mm at which the < 0.5 mm-bin Target of §1a still holds |
| Bias per width decile | mean(ŵ − w_ref) in each decile of w_ref | Report. There must be no monotone trend after correction (otherwise the closed-form correction is incomplete) |

*Stated limitation (quoted from M1):* results "may not align with … digital cameras or smartphones". krkCMd validates the **estimator**, and the panel validates the **pipeline**.

### 1c. Width-estimator ablation (campaign C1)

The same rectified crops are run through each estimator, and the §1a metrics are reported per bin.

| Estimator | Source |
|---|---|
| `2·distanceTransform` at skeleton, **minus 1.00 px** (closed-form bias) | ADDENDUM, first measurement result |
| Area / skeleton length | ADDENDUM; area-length is ranked 86.6% accuracy in the Automation in Construction 2024 OrthoBoundary study (AB) |
| **Profile integral** `∫(b − I)ds / C` | M5 derivation; "Equal Area" prior art (CACAIE 2025, AB) |
| Orthogonal-boundary (skeleton tangent → normal → edge-to-edge) | OrthoBoundary, Automation in Construction 2024 (AB): 90.1% |
| DNN mask + GrabCut edge refinement + distance transform | M2 (the published pipeline to beat) |

**Pre-registered hypothesis:** the profile integral beats every mask-based estimator in the < 0.5 mm bin, because mask edges carry label-level noise (S10: 16% exact-pixel centreline agreement even for the best model). If it does not, that result is published.

---

## 2. Certification gate and uncertainty — the refusal claim

| Metric | Definition | Threshold | Anchor |
|---|---|---|---|
| **Certified-but-wrong rate** | fraction of held-out captures that pass the gate *and* have \|ŵ − w_ref\| > τ, with **τ = 0.05 mm** | **≤ α = 0.05**, guaranteed in expectation by CRC | A3 (ICLR 2024), Theorem 1. The gate λ̂ is fitted on calibration sessions with `L_i(λ) = 1[q_i ≥ λ]·1[\|err_i\| > τ]` |
| CRC slack term | B/(n+1) with B = 1 | ≤ 0.01, so **n ≥ 100 calibration captures** | A3 |
| **Interval coverage** | fraction of test captures whose conformal 90% width interval contains w_ref | **∈ [0.88, 0.95]** (split conformal gives ≥ 1 − α, and ≤ 1 − α + 1/(n+1) under continuous scores) | Split conformal; A5 for the morphological variant |
| Interval size | median width of the 90% interval, among certified captures | **[eng]** ≤ 0.10 mm (< 0.5 mm bin), ≤ 0.15 mm (≥ 0.5 mm bin) | — |
| Morphological margin λ̂ | the conformal dilation radius (A5) that makes the dilated mask cover the GT mask at 90% | Report in px and mm. It is the per-pipeline boundary-uncertainty readout | A5 (MICCAI 2025) |
| **Certification yield** | fraction of sessions that reach "certified" within ≤ 3 agent turns under the capture protocol | **[eng]** ≥ 70% on the panel; report on real walls | — |
| Risk–coverage curve | certified-but-wrong rate vs fraction certified, swept over λ | Report the whole curve; the area under it (AURC) is the single scalar for campaign C3 | A3 |
| Refusal correctness | among refused captures, the fraction that *would* have been out of tolerance | Report (this shows the gate refuses for the right reasons) | — |

*Stated caveat:* the CRC and conformal guarantees hold for captures **exchangeable with the calibration sessions**: same board, phone class and surface class. On a new surface class (painted plaster, for example), the guarantee is re-established with that class's calibration captures or is not claimed.

---

## 3. Agentic triage — Loop 1

Protocol: **P0** (random action) vs **P1** (fixed-threshold if/else) vs **P2** (LLM agent). All three receive the **same numeric observation vector** q = {#corners, reprojection RMS, px/mm, θ, blur variance, glare fraction, crack pixel extent}. Per A1 and A2, no policy judges pixels directly.

| Metric | Definition | Threshold |
|---|---|---|
| **Recovery rate** | fraction of sessions that start below the gate and reach certified | Report per policy. **Pre-registered:** P2 − P1 ≥ +10 pts on the **compound-failure subset** (e.g. glare + obliquity with acceptable blur). On single-cause failures, P1 ≈ P2 is expected and stated in advance |
| Turns-to-certified | median number of agent turns among recovered sessions | Report; lower is better |
| Wrong-action rate | fraction of turns whose chosen action does not address the dominant failure, judged against a **labelling rule written before any run** | Report |
| Escalation precision / recall | for `abandon_and_log` / escalate-to-engineer decisions vs the pre-registered rule | Report both |
| Instruction quality | human rating 1–5 on clarity and actionability, with the single-annotator limitation disclosed | Report the mean and distribution |
| Sample size | sessions per policy and failure class | **[eng]** ≥ 30 per policy on the compound subset, with a bootstrap CI on the P2 − P1 difference |

Framing: this is the information-seeking vs information-receiving factorisation of A7 (CoRL 2024), with the human as actuator (A6: viewpoint choice against an explicit quality objective). **If P2 does not beat P1, that result is published.**

---

## 4. Segmentation — a locator, reported as an ablation

The segmenter's job in Prohori is to **locate** the crack and its centreline. Measurement belongs to §1. Segmentation metrics are reported for comparability with the literature and to explain downstream width error.

### 4a. Datasets

| Dataset | Content | Role | Access |
|---|---|---|---|
| **Crack500** | 3,368 phone images of asphalt (augmented from 500) | Comparability with S1 and S2 | public |
| **DeepCrack** | 537 images of concrete, brick and asphalt | Comparability with S1 and S2 | public |
| **TUT** (S3) | 1,408 images across 8 cluttered scenes | Clutter and domain stress | `github.com/Karl1109/CrackSCF` |
| **OmniCrack30k** (S10) | 30,017 images from 20 subsets, 5 materials | Universal benchmark, clIoU protocol | `github.com/ben-z-original/omnicrack30k` |
| **Facade390** (S6) | Building-façade cracks with stains, paint and joints (UAV) | Nearest public match to Dhaka walls | released with CrackSAM |
| **Road420** (S6) | iPhone road cracks, including night shots | Phone-capture domain check | released with CrackSAM |
| **Prohori-Dhaka** (ours) | Painted, plastered, weathered surfaces around Dhaka, rectified ROIs | Real domain shift. Labelled by one annotator (disclosed) | to be released with the entry |

### 4b. Metrics

| Metric | Definition | Anchor |
|---|---|---|
| P, R, **F1**, **crack IoU** | pixel counts pooled over the test set; IoU = F1/(2 − F1) | S1, S2, S7 |
| ODS / OIS | best F1 at a dataset-level / image-level threshold | S1 (Eqs. 17–18) |
| **clIoU_ρ, ρ ∈ {0, 1, 2, 4} px** | centreline IoU with a positional tolerance of radius ρ | S10 |
| Centreline recall @ 2 px | fraction of GT skeleton within 2 px of the predicted skeleton, **on the test panel** | [eng] — this decides how many width stations survive |
| Mask-QA rejection rate | fraction of masks rejected by the EDT-ratio / hole test | S8 |
| Complexity | params, GFLOPs @512², **CPU latency through `cv2.dnn` on c8g** | S1, S2 |

### 4c. Reference numbers and thresholds

| Model | Crack500 F1 (crack IoU) | DeepCrack F1 | TUT F1 | OmniCrack30k | Params |
|---|---|---|---|---|---|
| SCSegamba (S1) | 0.755 (0.607) | 0.911 | 0.839 | — | 2.80 M |
| EfficientCrackNet (S2) | 0.791 (0.654) | 0.859 | — | — | 0.26 M |
| CrackSCF (S3) | — | — | 0.838 | — | 4.79 M |
| SCRWKV (S4) | — | — | **0.843** | — | 1.22 M |
| Segment Any Crack (S7) | — | — | — | F1 0.612 / IoU 0.441 | SAM |
| nnU-Net (S10) | — | — | — | clIoU_4px 0.64 (test); clIoU_0px 0.162 (val) | — |

**Thresholds for Prohori's DNN locator** (EfficientCrackNet-class, retrained, ONNX, run through `cv2.dnn`):
- **Floor:** Crack500 F1 ≥ 0.75 and DeepCrack F1 ≥ 0.82, i.e. within 4 points of S2's published numbers, which is enough to show the reimplementation is faithful.
- **[eng]** CPU latency ≤ 100 ms per 512² tile on c8g.large (p95).
- On TUT, Facade390 and Prohori-Dhaka: **report only**. The publishable result is the *drop* from in-domain to cross-domain, compared against S7's 44% IoU anchor.

**Classical locator** (CLAHE → adaptive threshold → thinning): no target on the public sets, since it is not trained for them. It is scored on centreline recall @ 2 px on the panel and on **downstream width error (§1)**, the only score that matters for the product.

---

## 5. COOL / Graviton — systems and accuracy invariance

| Metric | Definition | Threshold |
|---|---|---|
| **Accuracy invariance** | max \|ŵ_COOL − ŵ_ref\| over all panel captures, identical inputs | **= 0 (bitwise).** If not bitwise, report the max deviation in mm and its source (for example SIMD reduction order), and require it to be < 1 µm **[eng]** |
| Per-stage latency | p50 / p95 per stage: detect board, rectify, locate, measure, aggregate | Report for COOL vs stock pip OpenCV 5.0.0 vs self-built OpenCV 5.0.0 (build flags published) |
| End-to-end latency | frame in → certified number out, server side | **[eng]** p95 ≤ 500 ms on c8g.large |
| Throughput | frames/s at the thread/batch sweet spot | Report the sweep |
| Cost | USD per 1,000 frames at on-demand price | Report |

---

## 6. Robustness and failure-mode matrix (evidence the rules require)

Each cell reports certified-but-wrong rate, yield and MAE on the panel.

| Factor | Levels | Anchor for including it |
|---|---|---|
| Resolution | 8, 10, 12, 15, 20, 25 px/mm | M2 names resolution as the dominant limit; M1 is used for the downsampling sweep |
| Obliquity θ | 0°, 15°, 30°, 45° | Li et al., CACAIE 2025 (AB): non-perpendicular shots distort pixel scale |
| Motion blur | Laplacian-variance deciles | dos Santos et al., JCSHM 2025 (AB): blur is a dominant aleatoric factor |
| Illumination / glare | diffuse, raking, specular on the board | same |
| Board–crack non-coplanarity | 0, 5, 10 mm offset | Assumption behind marker scale (LITERATURE §2 note) |
| Surface | printed panel, bare concrete, painted plaster, weathered plaster | S6 Facade390; the S8 failure mode is fragmentation under domain shift |

---

## 7. Summary scoreboard (what the final report leads with)

| Claim | Metric | Target | Beats |
|---|---|---|---|
| Thin-crack width | < 0.5 mm bin, \|ratio − 1\| and COV | ≤ 0.05, ≤ 12% | M2: 0.11, 21.9% |
| Overall width | MAE, P95 | ≤ 0.05 mm, ≤ 0.10 mm | S8: 0.09 mm MAE, 0.15 mm max |
| Refusal is principled | certified-but-wrong rate | ≤ 5% (CRC-guaranteed) | no 2024–26 crack-width paper reports this |
| Uncertainty is honest | 90% interval coverage | 0.88–0.95 | — |
| Agent earns its place | P2 − P1 recovery on compound failures | ≥ +10 pts (pre-registered) | P1 if/else baseline |
| COOL is faithful | max \|Δw\| | 0 (bitwise) | — |
