# Dossier addendum — facts verified 2026-08-28 (round 2)

## OpenCV 5 is pip-installable, including on Arm64
- `opencv-python` **5.0.0.93** wheels are on PyPI, uploaded 2026-07-02, with **Linux ARM64** wheels among the targets. Variants: `opencv-python`, `opencv-python-headless`, `opencv-contrib-python`, `opencv-contrib-python-headless` (mutually exclusive, same `cv2` namespace).
- Consequence: the **stock pip OpenCV 5.0 build on the same Graviton instance is the natural, defensible COOL baseline** — and it is the exact baseline OpenCV themselves benchmark against ("78 functions vs the default OpenCV 5.0.0 build"). Same silicon, same OS, same input, one variable changed. This is the cleanest possible A/B and it costs nothing.

## Features module in OpenCV 5
- `features2d` is **renamed to `features`**, scope widened to deep-network feature vectors.
- **ALIKED** — CNN keypoint detector+descriptor, drops into the same call sites as SIFT/ORB.
- **DISK** — RL-trained learned features, strong on wide-baseline and low-texture scenes. Exposed through the `Feature2D` interface; the OpenCV wrapper emits **128-d L2-normalised descriptors** and **requires an ONNX model path or model buffer**.
- **LightGlueMatcher** — attention-based matcher producing **confidence-scored matches**; plugs into the stitching module.
- SIFT/ORB/FAST retained for backward compatibility — so classical-vs-learned ablations are trivially available and make excellent evaluation evidence.

## COOL exists as THREE separate Marketplace listings, each with its own 7-day free trial
| Listing | Latest version | Built on | Instance families | Cheapest software fee |
|---|---|---|---|---|
| Cloud Optimized OpenCV **for AWS Graviton2** | — | — | t4g / c6g / m6g / r6g family class | (free trial; low tier) |
| Cloud Optimized OpenCV **For Graviton3** (`prodview-5b2boxpyztidw`) | COOL **2.0** | OpenCV 4.12.0 baseline in its benchmark note | **c7g, c7gd, m7g** | **c7g.medium = $0.01/hr**, c7g.xlarge $0.01, m7g.xlarge $0.01 |
| Cloud Optimized OpenCV **For AWS Graviton4** (`prodview-fdvbfiewzuehs`) | COOL **3.1** | **OpenCV 5.0.0** | **c8g, m8g, r8g** | **c8g.large = $0.01/hr**, c8g.xlarge $0.01 |

Two strategic consequences:
1. **A cross-generation COOL study (Graviton2 vs 3 vs 4) is available to us and is a far stronger "Best Use of COOL" artifact than a single-instance benchmark.** Nobody else is likely to do this. Scaling behaviour of KleidiCV kernels across Neoverse N1 -> V1 -> V2 is a genuinely interesting result.
2. Each listing carries its **own independent 7-day free trial**, so the entire benchmark campaign can be executed at **zero software fee** if the trials are started deliberately rather than accidentally.

## The $0 path, concretely
- **t4g.small (Graviton2): 750 free hours/month for every AWS account through 2026-12-31.** That is one free Arm box running continuously for the whole build window — this is where day-to-day development and the always-on demo endpoint live.
- **Lambda arm64**: 1M requests + 400,000 GB-s/month, permanently free.
- **AWS Free Plan** (post-2025-07-15 model): **$100 credits on signup + up to $100 more** for five onboarding activities (launch/terminate EC2, configure RDS, deploy Lambda, test a Bedrock prompt, set a Budget). Credits expire 12 months after signup; the Free Plan itself ends at 6 months or when credits are exhausted, whichever is first. Signing up now (Aug 2026) covers the competition and the judging window comfortably.
- **$150 grant** if awarded (50% up front, 50% after the Sep 21 - Oct 2 Zoom check-in).
- **Residual risk:** AWS promotional credits may not be applicable to AWS Marketplace third-party software fees — this could not be confirmed from the published Free Tier terms. Worst case exposure at $0.01/hr is ~$14 for a continuously-running COOL box across the whole window. **Mitigation that reduces it to $0: run COOL only inside the three independent 7-day free trials, timed deliberately (one per Graviton generation), and cancel each subscription before it converts.** Development and the always-on endpoint run on stock pip OpenCV 5 on free t4g.small; COOL is subscribed only for measurement bursts and the final demo recording.
- **Free Plan accounts shut resources down rather than billing a card when credits are exhausted** — which makes the Free Plan the correct choice under a hard zero-spend constraint, at the cost of needing the endpoint to survive until judging ends Nov 9.

## Locally VERIFIED by direct probe (not from docs) — 2026-08-28
`opencv-python 5.0.0` is already installed on the build machine (Python 3.12). A live `dir(cv2)` probe confirms these symbols exist and are callable:

- `cv2.ALIKED`, `cv2.ALIKED_Params`, `cv2.ALIKED_create`
- `cv2.DISK`, `cv2.DISK_create`, `cv2.DISK_createFromMemory`
- `cv2.LightGlueMatcher`, `cv2.LightGlueMatcher_create`, `cv2.LightGlueMatcher_createFromMemory`, `cv2.detail_LightGlueFeaturesMatcher`
- Classical baselines retained: `cv2.SIFT_create`, `cv2.ORB_create`, `cv2.AffineFeature_create`
- `cv2.dnn.readNetFromONNX`, `readNetFromTFLite`, `readNet`

Modules present in the build: `core imgproc imgcodecs videoio dnn features flann calib geometry ptcloud stereo rgbd surface_matching video tracking optflow stitching photo quality signal ml objdetect ximgproc xfeatures2d xphoto xobjdetect saliency reg shape structured_light superres`.

Note `features` (the renamed `features2d`) and `calib`, `ptcloud`, `geometry`, `quality`, `signal` are all built. `quality` is useful for reference-free image quality metrics; `ptcloud` and `geometry` for 3D work.

**Feasibility conclusion: ALIKED / DISK / LightGlue and the new DNN engine are usable from Python today, on the machine, with no compilation.** Any concept resting on them is buildable. DISK/ALIKED require an ONNX model path or buffer at construction.

## Local toolchain present
`git`, `gh` (GitHub CLI), `python 3.12`, `node`, `npm`, `uv`, `ssh`, `reportlab`, `numpy`, `matplotlib`.
Missing and needing install: **AWS CLI v2**, `docker`, `pandoc`.
Consequence: proposal and report PDFs can be generated locally with `reportlab`; repo and releases driven through `gh`; the Graviton box reached over `ssh` / EC2 Instance Connect.

## Load-bearing API check — all PASS (probed live, OpenCV 5.0.0)
`cv2.aruco` (module survives in OpenCV 5) with `ArucoDetector`, `CharucoBoard`, `CharucoDetector`, `DetectorParameters`, `getPredefinedDictionary`; `distanceTransform`; `ximgproc.thinning`; `findContours`; `createCLAHE`; `solvePnP`, `recoverPose`, `findEssentialMat`, `triangulatePoints`, `stereoRectify`; `cv2.quality`; `FaceDetectorYN_create` (for the face-redaction guardrail).
An ArUco generate -> detect round-trip succeeded (marker id 3 recovered).

## FIRST REAL MEASUREMENT RESULT (not a plan — actually run, 2026-08-28)
Characterised the crack-width estimator against synthetic ground truth before committing to it.

**Method:** exact-width rectangles, width measured as `2 * distanceTransform(mask, DIST_L2, DIST_MASK_PRECISE)` sampled at `ximgproc.thinning` skeleton points, median over the skeleton.

| True width (px) | 3 | 5 | 7 | 9 | 15 | 21 |
|---|---|---|---|---|---|---|
| `2*DT` at skeleton | 4.00 | 6.00 | 8.00 | 10.00 | 16.00 | 22.00 |
| **Error** | **+1.00** | **+1.00** | **+1.00** | **+1.00** | **+1.00** | **+1.00** |
| area/length estimator | 3.04 | 5.11 | 7.21 | 9.35 | 16.00 | 23.01 |

**Result: the distance-transform width estimator carries an exactly constant +1.00 px systematic bias, independent of width.** It is a pixel-centre convention artifact (the transform measures centre-to-centre, so `2*DT = w + 1`), and it is therefore removable in closed form by subtracting exactly 1.0 px — not by fitting a fudge factor.

Why this matters for the entry:
1. It converts the dominant systematic error in the whole measurement chain from unknown into known-and-cancelled, which is what makes a sub-millimetre claim defensible rather than hopeful.
2. The area/length alternative is *better for hairline cracks* (error < 0.4 px below 9 px width) but degrades badly on wide cracks (+2 px at 21 px) — so the correct design is a width-dependent estimator, and we can say why, with data.
3. It is exactly the kind of calibration evidence the Overall rubric's Technical Execution line and the mandatory "evaluation evidence including failure cases" requirement reward, and precisely what a classifier-only entry cannot produce.
4. It is also the accuracy-invariance control for the COOL benchmark: the same corrected estimator must return identical numbers under COOL and under stock OpenCV 5, proving COOL is a pure performance layer.

## CORRECTION — ACI 224R-01 Table 4.1, verified against source
An early draft cited "~0.3 mm for protected interior members". That is wrong. The verified table:

| Exposure condition | Tolerable crack width (in) | (mm) |
|---|---|---|
| Dry air or protective membrane | 0.016 | **0.41** |
| Humidity, moist air, soil | 0.012 | **0.30** |
| De-icing chemicals | 0.007 | **0.18** |
| Seawater / seawater spray, wetting and drying | 0.006 | **0.15** |
| Water-retaining structures (excluding pressure pipes) | 0.004 | **0.10** |

0.30 mm is the **humidity / moist air / soil** category, not the protected-interior one. Protected interior is 0.41 mm.

Two consequences, both favourable:
1. **Dhaka is humid.** The 0.30 mm row is the correct and defensible category for most Bangladeshi building exteriors and unconditioned interiors, so the demo threshold stands — what changes is the exposure label attached to it, which must be stated explicitly and selectable per site rather than hardcoded.
2. **ACI's own caveat is an asset, not a liability.** The report states these widths "are not always a reliable indication of steel corrosion and deterioration of concrete to be expected." The system must therefore never output a safety verdict. It outputs a *measured width, its uncertainty, the named exposure category, and the code limit for that category*, then escalates to a qualified human. That is the correct engineering posture, it is what the Agentic Vision rubric's "appropriate human control" line (15%) rewards, and it is what the Overall rubric's "responsible operation" line (10%) rewards. Any entry that prints "UNSAFE" from a phone photo is scoring against itself.

Source: ACI 224R-01 Table 4.1, cross-checked against NCHRP 18-14 Appendix A literature review.
