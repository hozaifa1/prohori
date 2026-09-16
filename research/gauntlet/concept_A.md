# CONCEPT A — Application-First Family

## 1. NAME AND ONE-LINE PITCH

**PROHORI** (প্রহরী — Bengali for "sentry / watchman") — an agentic active-perception system that walks a concrete structure with nothing but a phone camera, measures crack width to sub-millimeter accuracy from multi-view geometry, decides for itself when the shot isn't good enough and asks for a re-shoot, tracks crack growth across repeat visits, and escalates to a human structural engineer automatically when a measured crack crosses an engineering safety threshold — built so the next Rana Plaza gets caught in the inspection log instead of the news.

## 2. PROBLEM, USERS, AND WHY IT MATTERS

On 24 April 2013, Rana Plaza — an eight-story garment-factory building near Dhaka with four illegally-added floors — collapsed. 1,134 people died and roughly 2,500 were injured; inspectors had flagged cracks in the building the day before, factory management sent workers back in anyway, and it remains the deadliest disaster in the history of the clothing industry (Clean Clothes Campaign; Wikipedia "Rana Plaza collapse"). Bangladesh's RMG sector today is 5,200+ registered factories, 4.4 million workers (nearly 60% women), $39.35B exported in FY2024-25 projected to exceed $45B in FY2025-26, over 80% of national export earnings and ~11% of GDP (worldfashionexchange.com; sdfltd.com industry data, 2026). Post-Rana Plaza remediation bodies (the Accord, now the RMG Sustainability Council) still run structural, fire and electrical inspection programs at scale — RSC's newest phase alone covers 1,185 factories across 58 brands starting Nov 2025, and over 1,200 previously-covered factories are still completing corrective-action remediation (RSC quarterly reports, thedailystar.net, rsc-bd.org). This is not a solved problem; it is an *ongoing, funded, institutionally-tracked* one, with a chronic bottleneck: structural inspection is manual, infrequent, and produces a binary "cracked / not cracked" note rather than a measured, trended, engineering-grade number an engineer can triage against a code limit.

Structural engineering codes do not treat all cracks as equal. ACI Committee 224 sets serviceability crack-width limits by exposure — roughly 0.18mm (0.007in) for concrete exposed to de-icing/corrosive conditions, ~0.2mm (0.008in) for exterior exposure, ~0.3mm (0.012in) for protected interior members (ACI 224R-01; NCHRP 654 Appendix A literature review). A crack detector that outputs "crack present" cannot be triaged against these numbers. A crack detector that outputs "0.34mm, up from 0.21mm 61 days ago" can.

**Users**: (1) RSC/DIFE-affiliated safety officers and independent structural engineers doing walkthrough inspections of RMG factory buildings and other occupied structures in Bangladesh; (2) building owners/facility managers who need a paper trail of "we checked, and here's the number" between formal engineering audits; (3) secondarily, any low-resource-setting building-safety context (schools, hospitals) where a phone is available but a laser crack-comparator or total station is not.

**Why it matters beyond a demo**: the target deployment context is real (RSC's active inspection mandate), the failure mode being defended against is documented and catastrophic (Rana Plaza), and the gap PROHORI targets — turning a visual "there's a crack" into a code-referenced, trended, escalatable number — is a genuine gap in current practice, not an invented one.

Sources: [Rana Plaza collapse — Wikipedia](https://en.wikipedia.org/wiki/Rana_Plaza_collapse), [Clean Clothes Campaign — Rana Plaza](https://cleanclothes.org/campaigns/past/ua/2013/cases/ranaplaza), [Bangladesh RMG Industry Data 2026 — SDF](https://sdfltd.com/insights/bangladesh-rmg-industry-data/), [Bangladesh Textile and Garment Industry Statistics 2026](https://www.worldfashionexchange.com/blog/rise-of-bangladesh-textile-and-garment-industry/), [RSC expands mandate — The Daily Star](https://www.thedailystar.net/business/news/rmg-sustainability-council-expands-mandate-beyond-safety-4030546), [RSC Quarterly Aggregate Report](https://rsc-bd.org/wp-content/uploads/2025/01/RSC-Quarterly-Aggregate-Report-3.4.pdf), [ACI 224R-01](https://www.researchgate.net/profile/Saad-Altaan/post/What-are-the-types-of-crack-and-their-causes-and-remedies-in-concrete-structures/attachment/5b4c79f8b53d2f89289a56d8/AS:648972947443713@1531738616217/download/224R_01.pdf), [NCHRP 18-14 Appendix A](https://onlinepubs.trb.org/onlinepubs/nchrp/nchrp_rpt_654AppendixA.pdf).

## 3. WHAT THE SYSTEM DOES (one real run, end to end)

Hozaifa opens PROHORI in his phone's browser (a PWA — no app-store install) at a stairwell landing in an accessible reinforced-concrete building in Dhaka (a real building he has access to; not a garment factory — see Section 11). He tapes a single printed A4 sheet with a ChArUco calibration pattern flat against the wall next to a visible hairline crack near a beam-column joint, and sweeps the phone camera slowly across the region for ~15 seconds while the page streams frames to the backend.

1. **Perceive.** The orchestrator (running on the always-on t4g.small box) batches incoming frames to a Lambda function running OpenCV 5's rewritten DNN engine with an ONNX crack-segmentation model. The first usable batch returns a segmentation mask with **confidence 0.42** — too low, because motion blur softened the crack edge.
2. **Decide.** The policy checks confidence against a 0.6 gate. Below gate → action = *request re-shoot*, reason code `LOW_CONFIDENCE_BLUR`. This is a branch a fixed classifier pipeline does not have: it doesn't just report "unsure," it changes what happens next.
3. **Act (physical).** The web UI overlays a bounding box on the live camera feed with the instruction "Hold steady — move 20cm closer" (guidance rendered from the mask's location and blur score). Hozaifa physically repositions.
4. **Perceive again.** New batch → confidence 0.88. Gate passed.
5. **Decide → Act (tool-call change).** Because confidence is now sufficient, the orchestrator fires a call it did **not** fire in steps 1-4: multi-view registration across the last 5 frames using OpenCV 5's **ALIKED/DISK** deep local features + **LightGlueMatcher**. Result: 42 inlier correspondences (threshold: 15).
6. **Decide → Act (tool-call change).** Inlier count clears the triangulation threshold → fires the **3D module** (pose recovery + triangulation) to reconstruct the crack edge in 3D, using the ChArUco marker (detected via `cv2.aruco`) as the metric scale reference. Had inliers come in under 15 (operator didn't move enough for a wide-enough baseline), the decision branch would instead have been *request wider sweep* — a different re-shoot instruction than the blur case, again driven directly by a vision output (match count).
7. **Perceive → measure.** The segmentation mask is skeletonized (`cv2.ximgproc`/morphology) and, at each skeleton point, local width is read off a `distanceTransform` of the mask, scaled from pixels to millimeters by the triangulated, marker-calibrated geometry. Result: **0.34mm**, 87% confidence.
8. **Decide.** The orchestrator queries DynamoDB for this structure's prior record at this same joint: 0.21mm, logged 61 days earlier. Growth = +62% in 61 days. This exceeds both the absolute ACI 224 interior-exposure limit (~0.3mm) *and* a configured growth-rate flag.
9. **Act (escalation).** The system writes the finding (images, mask, measurement, confidence, growth trend, GPS) to DynamoDB and S3, and fires an SNS email to a nominated engineer contact: *"Crack at Site-A / Joint-3: 0.34mm (was 0.21mm, +62%, 61 days). Exceeds interior serviceability limit. Confidence 87%. Evidence: [S3 link]."* This is the human-approval-request action the Agentic Vision rubric explicitly names as qualifying — a human now has to look at this before anything else happens.

If step 8's numbers had come back low and flat, the action would instead have been *log only, continue sweep* — no escalation, no interruption. The action taken is a direct function of the vision measurement, not a fixed script.

## 4. OPENCV 5 DEPTH

- **`cv2.dnn` (rewritten engine, ~80%+ ONNX op coverage)** — runs the crack-segmentation model. Necessary because the model needs to be swappable (different backbone for higher recall vs. higher precision) without touching the orchestration code; OpenCV 5's DNN rewrite is what makes that swap a config change, not a rebuild.
- **ALIKED, DISK (deep local features) + LightGlueMatcher** — used for wide-baseline multi-view frame registration of the crack region. This is not decorative: classic ORB/SIFT fail on low-texture, repetitive concrete surfaces exactly like the ones being registered here; DISK was explicitly built to be strong on wide-baseline, low-texture scenes, which is the actual failure mode a naive feature pipeline would hit on bare concrete. LightGlue's confidence-scored matches are what step 6's "42 inliers, threshold 15" decision gate reads.
- **3D module (pose recovery + triangulation)** — recovers a metric 3D reconstruction of the crack edge from the registered multi-view frames, combined with `cv2.aruco` ChArUco detection for absolute scale. Necessary because a single 2D mask has no notion of millimeters; this is the step that turns "crack detected" into "crack is 0.34mm," which is the entire point of the system relative to a plain classifier.
- **`cv2.aruco`** — detects the printed calibration pattern each frame, providing the metric scale reference the monocular 3D reconstruction cannot recover on its own (see Section 11, weakness 1, for why this is required rather than avoidable).
- **imgproc/core (cvtColor, adaptive threshold, morphological skeletonization, `distanceTransform`, `findContours`)** — the actual width-measurement algorithm: skeletonize the segmentation mask, read local half-width off the distance transform at each skeleton point, aggregate a percentile width. This is exactly the function set COOL's own 78-function benchmark targets, which is why it is also the COOL workload (Section 6) — not a coincidence, a deliberate alignment so the performance story and the correctness story are the same code path.
- **HAL redesign / Universal Intrinsics 2.0 / Arm KleidiCV paths** — the reason the imgproc-heavy stage above is worth benchmarking on Graviton at all: this is precisely the code path COOL retunes, and it runs once per frame across a live video sweep, so its latency directly gates how fast the re-shoot feedback loop in step 3 can respond.

## 5. THE AGENTIC LOOP

**Perception → decision → action**, concretely (see full trace in Section 3, steps 1-9). Diagram (textual, will be rendered as a real architecture diagram in the deliverable):

```
[phone frames] -> [DNN segmentation] -> confidence?
   low  -> DECIDE: reshoot(reason=blur) -> ACT: on-screen reposition instruction (physical, human-executed)
   high -> DECIDE: register(ALIKED/DISK+LightGlue) -> inliers?
       low  -> DECIDE: reshoot(reason=narrow_baseline) -> ACT: on-screen "sweep wider" instruction
       high -> DECIDE: triangulate + scale via ArUco -> width_mm
           width vs ACI limit AND vs DynamoDB history (growth%) ->
               exceeds  -> ACT: write finding to DynamoDB/S3 + SNS escalation (human-approval request)
               within   -> ACT: log only, continue sweep
```

Two concrete example traces where the vision result **changes** a later tool call:
1. Confidence 0.42 → the registration tool call (ALIKED/DISK/LightGlue) is *not* invoked at all in that cycle. Confidence 0.88 on the re-shot frames → it *is* invoked. The vision output (a scalar confidence) gates whether an entire downstream tool executes.
2. 42 inliers → triangulation + scale-recovery tool call fires with the current frame set. Had it been 9 inliers, that same tool call is withheld and a different action (wider-sweep instruction) fires instead — same upstream stage, different measured output, different next step.

**What the action physically/digitally is**: (a) physical — a human-executed camera reposition, driven by an on-screen instruction generated from the vision output's spatial location and failure reason (this is the "actuator" for a solo, no-robot build: the human is the arm, the agent is the vision-to-instruction planner, which is a legitimate and common embodiment in image-guided workflows, e.g. surgical navigation); (b) digital — a DynamoDB write + S3 evidence upload + SNS email that constitutes a real human-approval request to a named engineer contact, not a chatbot summary.

**Failure handling / human control**: every decision node logs its reason code (`LOW_CONFIDENCE_BLUR`, `NARROW_BASELINE`, `THRESHOLD_EXCEEDED`, `WITHIN_LIMIT`) to DynamoDB, so the full decision trace is auditable after the fact. The system never takes an irreversible action on its own — escalation is a notification requesting human sign-off, not an automated shutdown or repair order.

## 6. COOL / GRAVITON PLAN

**Core workload benchmarked**: the full imgproc/core measurement pipeline from Section 4's fifth bullet — `cvtColor`, adaptive threshold, morphological skeletonization, `distanceTransform`, `findContours` — run once per frame across a fixed 500-frame benchmark clip. This is deliberately the same code that does the crack-width math in the live system, not a synthetic proxy.

**Baseline**: identical Python code, identical frames, run against (a) vanilla `pip install opencv-python` 5.0.0 and (b) the COOL 3.1 build (OpenCV 5.0.0 + Arm KleidiCV), on the same instance. Two instance types tested: **t4g.small** (Graviton2, free-tier, always-on box already in the architecture) and a time-boxed **c8g.large** burst (Graviton4, $0.01/hr, run only during the COOL 7-day free trial window, screen-recorded for reproducibility, then terminated).

**What exactly gets measured**:
- Per-stage wall-clock latency (ms) for each of the 5 functions above, COOL vs. vanilla.
- End-to-end frames/sec throughput over the 500-frame clip (headline number, same style as AWS's own published 1.2fps → 1.6fps case study).
- Cost per 1,000 frames processed = instance $/hr ÷ measured throughput, for both instance types.
- **Accuracy-invariance control**: crack-width output compared bit-for-bit (or within float tolerance) between the COOL and vanilla runs on the same frames, to prove COOL is a pure performance layer, not an accuracy trade-off — a control the dossier's own benchmark claims don't explicitly report, and one a hostile judge would ask for.

**Report format**: a table (stage × build × instance) plus the two headline ratios (fps improvement, $/1000-frames improvement), with the exact COOL version, AMI ID, and instance type recorded per the COOL rubric's reproducibility requirement.

## 7. AWS ARCHITECTURE

- **EC2 t4g.small** (Graviton2, 750 free hrs/month through 2026-12-31) — always-on orchestrator: FastAPI app serving the PWA, running the decision policy, holding the public web endpoint (Nginx + free TLS + free subdomain).
- **AWS Lambda, arm64** (Graviton2, permanently-free tier: 1M requests + 400,000 GB-s/month) — stateless per-batch segmentation and feature-matching jobs, invoked by the orchestrator; keeps the always-on box thin.
- **Amazon S3** (free tier, 5GB) — raw frames, evidence images, generated reports (the "digital twin" evidence store).
- **Amazon DynamoDB** (always-free 25GB) — the structured record store: per-structure, per-joint, per-visit crack measurements, confidence, reason codes, timestamps, GPS — this is what step 8 in Section 3 queries for trend comparison.
- **Amazon SNS** (free tier, 1,000 email notifications/month) — escalation channel to the nominated engineer; email only (not SMS) to avoid any per-message charge outside free tier.
- **Amazon Bedrock, Nova Micro (cheapest per-token model)** — used *sparingly*, only at decision points (a handful of calls per inspection session, not per frame) to draft the natural-language escalation note and, optionally, to reason over ambiguous threshold cases. Funded entirely from AWS Free-Plan credits ($100 base + up to $100 via activities), not personal funds — consistent with the G2 gate definition.
- **EC2 c8g.large, COOL AMI** — time-boxed benchmark burst only (Section 6), $0.01/hr, covered by free-plan credits or the 7-day Marketplace trial; never left running.
- **CloudWatch** — logs/metrics from the orchestrator and Lambda, for the "responsible cloud delivery" rubric line (observability).
- **IAM least-privilege roles**, encryption at rest by default on S3/DynamoDB. **Responsible-use guardrail**: before any frame is persisted to S3, an OpenCV face-detector redaction pass blurs any incidental human faces caught in the sweep (workers in the background of a factory corridor) — a concrete, code-level answer to the "responsible cloud delivery" rubric line, and a second legitimate use of OpenCV beyond the crack pipeline itself.

**Staying at $0**: every always-on component sits in a permanently-free or 2026-dated-free tier (t4g.small, Lambda arm64, S3, DynamoDB, SNS free allotments); the only paid line item (COOL Marketplace software fee) is either inside its 7-day trial or a few cents of $0.01-$0.02/hr burst usage, covered by AWS free-plan credits — never Hozaifa's own money. Bedrock token spend is minimized by calling it only at decision points, and is likewise covered by free-plan credits.

## 8. EVALUATION PLAN

**Datasets**: SDNET2018 (56,000+ labeled 256×256 crack/non-crack patches, CC BY, cracks 0.06-25mm, Utah State) for segmentation precision/recall against a public baseline; METU (~40,000 images) and the Concrete Crack Images for Classification set (Ozgenel, Mendeley, 40,000 images) as secondary classification cross-checks; CrackForest for out-of-domain generalization (road vs. building concrete).

**Metrics**:
- Segmentation: IoU, precision/recall/F1 vs. published SDNET2018 baselines.
- Measurement: on a small self-collected multi-visit dataset (real Dhaka structures, not factories — see weakness 3), width-measurement error against manual caliper/crack-comparator-gauge ground truth, targeting the sub-mm accuracy range reported in the smartphone-SfM literature (RMSE < 0.08mm on lab rock-joint surfaces; UAV photogrammetry crack studies report millimetric accuracy tied to ground sample distance) — cited as feasibility evidence, not claimed as our own result in advance.
- Agent task effectiveness: reshoot-request precision (did a reshoot request actually improve confidence on the next attempt?), escalation precision/recall against a hand-labeled set of "should have escalated" cases.
- COOL: latency, throughput, $/1000 frames, accuracy-invariance (Section 6).

**Baselines**: (1) single-shot classifier with no re-shoot loop (the FSM-equivalent, i.e. what most competing entries and FREISA-style systems would do); (2) manual crack-comparator-gauge measurement (the current real-world practice).

**Failure taxonomy**: motion-blur false negatives; low-light segmentation failure; ArUco marker occlusion/glare (breaks scale recovery — falls back to relative-only measurement); narrow-baseline sweeps that never accumulate enough inliers (system should keep requesting wider sweeps up to a retry cap, then flag "measurement unavailable" rather than guess); hairline cracks near the SDNET2018 lower bound (0.06mm) below the segmentation model's reliable resolution.

## 9. DEMO AND VIDEO PLAN

**What the judge clicks**: the public web endpoint (PWA, works on the judge's own phone or via screen-share) — judge points a phone camera at a printed test panel with a known, pre-measured crack replica and a ChArUco marker; watches the live confidence readout, a reshoot prompt fire on a deliberately blurred first pass, then a measurement and a DynamoDB record appear; judge can then view the "site history" page showing a synthetic two-visit trend and the SNS escalation email that fired.

**5-minute video**: (0:00-0:30) Hozaifa on camera, Rana Plaza framing, the RSC/DIFE inspection numbers; (0:30-1:30) architecture diagram walkthrough (perception → decision → action, plus AWS diagram); (1:30-3:30) live run exactly as in Section 3 — blur → reshoot → registration → triangulation → measurement → escalation, narrated as it happens, on a real accessible structure; (3:30-4:15) COOL benchmark table on screen, fps/cost numbers, AMI/instance IDs shown for reproducibility; (4:15-5:00) evaluation numbers (IoU vs. SDNET2018 baseline, measurement error vs. caliper ground truth) and the honest failure-case reel (a marker-glare miss, a too-narrow sweep).

## 10. 59-DAY SOLO BUILD PLAN

- **Wk 1 (Aug 28 - Sep 3)**: submit grant proposal; stand up t4g.small + S3 + DynamoDB skeleton; get SDNET2018/METU downloaded and a baseline segmentation model trained/fine-tuned, exported to ONNX, running under `cv2.dnn`.
- **Wk 2 (Sep 4-10)**: ArUco/ChArUco scale-reference pipeline working end-to-end on static test images; distance-transform width-measurement algorithm validated against manual caliper on a handful of real cracks.
- **Wk 3 (Sep 11-17)**: ALIKED/DISK + LightGlueMatcher multi-view registration working; 3D triangulation producing metric crack-edge reconstructions; first full perceive→measure pipeline on live video.
- **Wk 4 (Sep 18-24)**: agent decision policy (confidence gate, inlier gate, threshold/trend gate) wired up; on-screen reshoot instruction UI; DynamoDB history queries.
- **Wk 5 (Sep 25 - Oct 1)**: SNS escalation wired; face-redaction guardrail; PWA polish; Lambda offload of segmentation/registration from the t4g.small box.
- **Wk 6 (Oct 2-8)**: COOL AMI benchmark burst (imgproc pipeline, both instance types), accuracy-invariance control, results table. **Mandatory grant Zoom check-in falls in this window (Sep 21-Oct 2) — schedule around it.**
- **Wk 7 (Oct 9-15)**: multi-visit self-collected evaluation data (real Dhaka structures, two visits ~2 weeks apart); measurement-error and escalation-precision numbers computed; failure taxonomy assembled from real misses.
- **Wk 8 (Oct 16-22)**: architecture diagram, technical report, repo cleanup, pinned deps, build/deploy/test instructions, REUSE-style licensing.
- **Wk 9 (Oct 23-26)**: video recording/editing, final rehearsal of the live demo path, submission.

## 11. HONEST WEAKNESSES

1. **The metric scale reference (ArUco marker) is a real operational dependency, not a nicety.** Monocular multi-view SfM reconstructs geometry only up to an unknown scale factor; there is no way to output "0.34mm" instead of "0.34 arbitrary units" without *some* metric reference — a marker, a known object, or a stereo/AR-depth API. I chose a printed marker because it's the cheapest, most controllable option available without native mobile development, and it's standard practice in the crack-photogrammetry literature I checked (UAV photogrammetry studies use scale bars/reference targets for exactly this reason). But a hostile judge can fairly ask "so it's not really marker-free, why is this better than existing scale-bar photogrammetry tools?" **Survivable, not dodgeable**: I state the limitation plainly, keep the marker cheap (one sheet of paper) and fixed-in-place per site rather than needed in every frame, and note that relative width and visit-over-visit growth trend remain valid signals even on frames without the marker present.

2. **Structural inspection is the organizer's own listed favored area #1** — a meaningful fraction of 761 participants will likely submit some version of "AI crack detection." The idea-level novelty ceiling is real. **Partially survivable**: my differentiation is in the *stack*, not the premise — metric width via ALIKED/DISK/LightGlue + 3D triangulation (not just a classifier), a genuine confidence/inlier-gated agentic re-shoot loop (not an FSM), visit-over-visit trend triage against an actual ACI 224 number, and a COOL benchmark on the exact code path doing the measurement. If a competing entry matches this depth, we lose on execution quality, not concept — which is a fair fight to be in, not a guaranteed loss.

3. **No access to an actual RMG factory floor for validation.** The Rana Plaza framing is real and the target deployment context (RSC/DIFE-monitored factories) is real, but the working demo and self-collected multi-visit evaluation data will come from accessible non-factory concrete structures in Dhaka (a personal building, campus infrastructure), because a solo student cannot arrange factory-floor access in 59 days. A hostile judge can say this is lab validation wearing a factory-safety narrative. **Survivable by honesty, not by hiding it**: I state explicitly in the report and video that the deployment target is RSC/DIFE-class inspection and the validation surface is public datasets plus real (non-factory) concrete structures — the underlying physics (crack-width-from-geometry) does not depend on which building it's measuring, and this limitation is shared by essentially every solo entrant in this category, not unique to PROHORI.
