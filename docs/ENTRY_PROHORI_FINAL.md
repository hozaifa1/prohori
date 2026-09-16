# PROHORI — final locked concept
*OpenCV AI Competition 2026. Locked 2026-08-28 after two gauntlet rounds, four adversarial reviews, and independent verification of every load-bearing claim.*

---

## The pivot that defines this entry

Earlier drafts put a deep-learning segmentation model and multi-view triangulation at the centre, with COOL benchmarking a side harness. That was wrong on four counts, and the final review caught all of them: COOL would not have been running the *core* workload (30% of that award's rubric); the hardest engineering legs contributed least to any rubric; monocular triangulation produces no millimetre that ChArUco pose estimation does not already give on a locally planar surface; and the whole thing was undeliverable by one person in 59 days.

**The classical `imgproc` measurement path is now the product**, it runs live on COOL/Graviton as the path the judge's own demo hits, and the DNN and learned-feature work is demoted to evaluated baselines and ablations.

This trades a ceiling on an Overall Grand Prize that a solo entrant was never realistically taking for a large increase in the probability of taking something — and it puts classical computer-vision rigour in front of Gary Bradski, whose entire lineage is classical CV.

---

## Pitch

**PROHORI** (প্রহরী, Bengali: *sentry*) measures concrete crack width from a phone, in millimetres, **with a published error budget** — and refuses to give a number when the image cannot support one.

The distinguishing property is not detection. It is **metrology**: a characterised systematic bias, a term-by-term uncertainty budget, a resolution gate that declines to certify below a measurable threshold, and a proof that the optimised library returns numerically identical answers to the reference one. Hackathon entries essentially never do metrology.

---

## What it does — one run

An inspector opens an **HTTPS** PWA (secure context is mandatory — `getUserMedia` will not open the camera otherwise), tapes a printed ChArUco board beside a crack, and sweeps the phone for ~15 s.

1. **Perceive.** Frames go to the Graviton service. `cv2.aruco.CharucoDetector` finds the board; `solvePnP` recovers the board plane's pose; a rectifying homography maps the crack region to a fronto-parallel view at a known **px/mm** scale. No SfM, no triangulation — on a locally planar wall the board supplies pose *and* absolute scale directly, and is far better conditioned.
2. **Decide.** First batch: 6 detected corners, Laplacian blur variance in the bottom decile, effective resolution 6 px/mm — **below the certification gate**. A Bedrock triage agent receives a structured observation (corner count, blur variance, px/mm, obliquity angle, glare fraction, crack pixel extent) and selects from a **six-action space** — `reshoot_steadier`, `move_closer`, `relight`, `reposition_marker`, `accept_with_widened_uncertainty`, `abandon_and_log` — generating the free-text instruction that the operator actually reads. *(Named honestly: a six-action space with free-text instruction generation. Not an "open action space.")*
3. **Act — the human is the actuator.** "Brace the phone against the wall and move ~20 cm closer" renders over the live feed. The operator complies.
4. **Re-perceive.** 24 corners, blur cleared, 17 px/mm — gate passed.
5. **Measure.** On the rectified plane: CLAHE → adaptive threshold → `ximgproc.thinning` → `distanceTransform`, **minus the characterised bias** → width in mm. Repeated across **N independently rectified frames**, and the *spread across frames* is reported as empirical uncertainty. This is stronger evidence than a triangulated point estimate, and it costs one loop.
6. **Re-identify across visits.** ALIKED/DISK + `LightGlueMatcher` match today's frame against the stored reference frame for this joint, confirming it is the *same* crack before any trend is computed. This is a single image pair — exactly what LightGlue is for — not a reconstruction problem.
7. **Report and escalate.** Width, uncertainty, px/mm, the declared exposure class, that class's ACI reference value, and the delta since last visit go to DynamoDB and S3; SNS emails a named engineer. The message states plainly that this is a **durability-guidance reference value for reinforced concrete, not a structural-capacity criterion**, and requests engineering review.

If the gate never passes, the system returns **"measurement unavailable"** and logs why. Refusing to answer is a designed behaviour, not a failure.

---

## OpenCV 5 usage

| Module | Role | Status |
|---|---|---|
| `imgproc`/`core` — `cvtColor`, CLAHE, `adaptiveThreshold`, `warpPerspective`, `ximgproc.thinning`, `distanceTransform`, `findContours` | **The core measurement workload.** Also exactly the function family COOL's 78-function benchmark targets. | **Core — runs on COOL/Graviton** |
| `aruco` — `CharucoDetector`, `solvePnP` | Plane pose and absolute metric scale | Core |
| `features` — ALIKED, DISK, `LightGlueMatcher` | Cross-visit re-identification of the same joint; classical SIFT/ORB retained as the ablation baseline | Core (single image pair) |
| `dnn` — ONNX segmentation | **Ablation baseline**, not the primary path: does a learned segmenter beat the classical threshold path on width error? Reported either way. | Ablation |
| `objdetect` — `FaceDetectorYN` | Redaction of incidental faces before any frame is persisted | Core (10 lines) |
| HAL / Universal Intrinsics 2.0 / KleidiCV | Why the imgproc stage is worth running on Graviton at all | Core |

**Cut and why:** `findEssentialMat` / `recoverPose` / `triangulatePoints`. On a locally planar surface with a ChArUco board present they add failure surface and produce no millimetre the board did not already give. Multi-view rigour is recovered honestly through the N-frame spread in step 5.

---

## The error budget — the entry's centre of gravity

**Measured, not projected** (exact-width synthetic rectangles, run on the build machine):

| True width (px) | 3 | 5 | 7 | 9 | 15 | 21 |
|---|---|---|---|---|---|---|
| `2·distanceTransform` at skeleton | 4.00 | 6.00 | 8.00 | 10.00 | 16.00 | 22.00 |
| **Error** | +1.00 | +1.00 | +1.00 | +1.00 | +1.00 | +1.00 |
| area/length estimator | 3.04 | 5.11 | 7.21 | 9.35 | 16.00 | 23.01 |

A constant **+1.00 px** bias — a pixel-centre convention artifact, removable in closed form. Stated precisely: **measured as exactly +1.00 px on axis-aligned synthetic rectangles**; bias on rotated, curved and real antialiased boundaries is characterised separately and reported as a distribution, not assumed equal.

**The budget is published term by term** — scale (board corner localisation), plane pose, edge localisation on the thresholded mask, blur residual, obliquity — and edge localisation dominates on real concrete. The arithmetic is stated openly: at 15 px/mm, a 0.30 mm crack is 4.5 px, so ±1 px of edge localisation per side is already **±0.13 mm**. Any earlier "±0.06 mm" claim was optimistic by 2–3× and is withdrawn. What ships instead is a **px/mm certification gate**: below the resolution at which the budget permits a defensible number, PROHORI declines to certify and the agent asks the operator to move closer.

**Ground truth is instrumented properly.** A caliper cannot enter a 0.3 mm surface crack. Reference widths come from machined/laser-cut slots and feeler gauges of known width, plus a crack-comparator card on real cracks, with the reference's own uncertainty reported.

---

## Agency, stated honestly and then measured

**Loop 1 — Inspector (runtime).** Vision output changes which action fires and what the human is told. This alone clears the Agentic Vision qualifying bar.

**Loop 2 — Agent Lab (build-time).** An LLM reads a **per-subset** eval diff (lit/shadowed, hairline/wide, painted/bare), writes a free-text hypothesis over an open option space, applies a change, re-measures on Graviton, and **recommends** a promotion. **Promotion is always human-approved.** Autonomous redeploy was cut: it scores *worse* under "human control" (15%) and "responsible cloud delivery" (10%) than it gains under "autonomy" (25%), and it deletes a pile of CI/CD and rollback work.

**The ablation — and a pre-registered negative result.** The same task runs under P0 (random action), P1 (fixed-threshold if/else — what a competing entry ships), and P2 (the reasoning agent). Scored on recovery rate, turns-to-certified, and escalation precision/recall.

The honest expectation, stated in advance: **on simple single-cause failures, P1 will probably match P2**, because one feature maps to one action. The ablation is therefore weighted toward **compound and conflicting failure states** — glare plus obliquity with acceptable blur, where no single threshold gives the right action — plus human-rated instruction quality. **The labelling rule is pre-registered before P0/P1/P2 are run, and the single-annotator limitation is stated.** If P2 does not beat P1, that is published.

Almost nobody benchmarks their agent against the if/else cascade it replaced. This is the entry's most distinctive intellectual move, and it costs almost nothing.

---

## COOL / Graviton

**One generation: Graviton4, COOL 3.1 — the only listing verified as built on OpenCV 5.0.0.**

The earlier three-generation Graviton2/3/4 plan is **withdrawn as invalid**: the listings ship different COOL versions on different OpenCV versions (the Graviton3 listing is COOL 2.0, benchmarked against OpenCV 4.12.0), so a "speedup across N1→V1→V2" chart confounds microarchitecture with library version — and any leg not on OpenCV 5 does not count in a competition that mandates OpenCV 5. One subscription, one cancellation, one calendar reminder.

**COOL runs the core workload, live.** The judge's demo hits the COOL-accelerated path. This is what makes the 30-point "Verified COOL on Graviton" line clean rather than arguable.

**Baseline, properly controlled.** Stock `pip opencv-python 5.0.0` *plus* a self-built OpenCV 5.0.0 with documented compiler and threading flags — because the pip ARM64 wheel's build configuration is not necessarily matched to COOL's, and an uncontrolled ~20% delta could be build flags rather than KleidiCV. Both sides' build flags are published.

**Reported:** per-stage latency; end-to-end fps; **cost per 1,000 frames**; a thread/batch sweep; and **accuracy invariance** — the corrected estimator must return numerically identical widths under COOL and under the reference build. Proving an optimised library is numerically faithful, not merely faster, is cheap, rarely done, and directly serves the rubric. COOL version, AMI ID, instance type and raw CSVs ship in the repo.

*(The "developer productivity" axis is dropped — time-to-Pareto-front with COOL on/off is throughput restated, n=1, unreplicable.)*

---

## AWS architecture and the $0 path

| Service | Role | Cost |
|---|---|---|
| EC2 **c8g** + COOL 3.1 AMI | The measurement service — core workload | Inside one 7-day trial; instance cost from Free-Plan credits |
| EC2 **t4g.small** (Graviton2) | Always-on orchestrator, PWA, public endpoint, **TLS** | 750 free hrs/month through 2026-12-31 |
| **Lambda arm64** | Async jobs, report generation | 1M req + 400k GB-s/month, free |
| **S3** / **DynamoDB** / **SNS** | Evidence; per-joint history and agent traces; engineer escalation | Free tiers |
| **Bedrock** | Triage agent + Agent Lab hypotheses — per *decision*, never per frame | Free-Plan credits |
| **CloudWatch** | Logs, metrics, traces | Free tier |

TLS via a free domain plus Let's Encrypt (or CloudFront), because the camera will not open otherwise. IAM least privilege, encryption at rest, no public buckets, face redaction before persistence.

**Zero-spend discipline:** AWS promotional credits do **not** cover Marketplace software fees, so the COOL subscription is confined to one deliberately-timed 7-day trial with a calendar reminder to cancel. Worst case is computed per listing rather than hand-waved as "single-digit dollars".

---

## Evaluation

**Datasets — corrected.** SDNET2018 and METU/Özgenel are **image-level classification** sets with no pixel masks; there are no published SDNET2018 IoU baselines, and any plan resting on them was broken. Segmentation is evaluated on **CrackForest** (118 pixel-annotated), **Crack500** (~3,368 annotated sub-images) and **DeepCrack** (537 pixel-labelled). SDNET2018 is retained only as a scale-and-diversity classification check.

**Metrics.** Width error against instrumented reference widths, reported as a **distribution with the term-by-term budget**, never a single headline number. Segmentation IoU on the mask datasets. Agent recovery rate, turns-to-certified, escalation precision/recall. COOL latency, throughput, cost/1k frames, accuracy invariance.

**Baselines and ablations.** Classical threshold path vs DNN segmentation; SIFT/ORB vs ALIKED/DISK+LightGlue for re-identification; single-shot capture vs the agentic re-shoot loop; P0/P1/P2; COOL vs reference build.

**Failure modes — tested, not hypothesised.** Motion blur; low light; ChArUco glare or occlusion (→ relative width only, never a guessed scale); resolution below the px/mm gate (→ "measurement unavailable"); hairline cracks near the 0.06 mm floor; and **domain shift onto painted, plastered, monsoon-weathered Bangladeshi surfaces**, where a model tuned on US bridge decks should be expected to degrade — measured and reported whatever it says.

**Integrity note.** Real cracks do not grow measurably in a 59-day window. The visit-over-visit trend is demonstrated on a **physically modified test panel**, and the video says so on screen. No fabricated growth figure is presented as observed.

---

## Impact framing, corrected

Rana Plaza (1,134 dead, 2013; cracks reported the day before) and the RSC/International Accord backlog (93,576 hazards across 1,755 factories, 58,367 more on follow-up, 665 of ~1,800 fully remediated, inspector availability the stated bottleneck) establish **why cheap trended numeric records matter** — not that a phone measurement predicts collapse.

**ACI 224R-01 Table 4.1 is durability and appearance guidance for reinforced concrete under service load. It is not a structural-capacity criterion, and it does not apply to plaster, masonry, or informal construction.** PROHORI therefore never emits a safety verdict; it emits a measurement, its uncertainty, the declared exposure class, that class's reference value, the trend, and a request that a qualified human look. ACI's own caveat — that these widths "are not always a reliable indication of steel corrosion and deterioration" — is quoted in the product, not buried in the report.

Users: safety officers and independent structural engineers on walkthrough inspections; building owners needing defensible evidence between audits; low-resource settings with a phone but no crack comparator or total station.

---

## Scope — what actually ships

Realistic budget: five final-semester courses, ~5 h/day GRE, an active thesis. **≈100–140 focused hours over 59 days — about three full-time weeks.**

**Minimum viable entry, contending for all three awards:** HTTPS PWA → ChArUco rectification → CLAHE/threshold → thinning + distanceTransform → bias-corrected mm with a published error budget and px/mm certification gate → Bedrock triage agent with full traces and the P0/P1/P2 ablation → DynamoDB history + SNS escalation → the identical pipeline benchmarked reference-vs-COOL on one Graviton4 instance with CSVs and AMI ID → 3–5 logged, human-approved Agent Lab cycles → report, diagram, video, failure reel.

**Cut, in order:** multi-view triangulation and learned-feature registration for geometry; the three-generation COOL study; autonomous redeploy; training a segmentation model from scratch (freeze a pretrained ONNX in one session, or keep classical primary); two of three eval corpora and the two-visit field study (replaced by the controlled panel).

**Never cut:** the bias-correction table, the P0/P1/P2 ablation, accuracy invariance, the face-redaction pass, the failure reel.

**Week 1 is not planning.** It is the thinnest end-to-end vertical slice — phone frame → ChArUco → one millimetre number → visible on an HTTPS endpoint — because every other claim is worthless until a judge can click something.

---

## What is genuinely novel, stated without inflation

Thinner than an earlier pitch implied, but real:

1. **A measured systematic-bias table and a width reported as a distribution with a term-by-term error budget.** Hackathon entries do not do metrology. This is the most Bradski-legible thing in the entry.
2. **Accuracy invariance as a COOL acceptance criterion** — proving the optimised library is numerically faithful, not just faster.
3. **The P0/P1/P2 agent ablation with a pre-registered negative result.**
4. A capture-time re-shoot loop where the human is the actuator.

**Dropped as unsupportable:** the claim that "every competing crack project outputs a classification." Marker-referenced crack-width quantification is a published field with commercial products. What PROHORI ships that most entries will not is the error budget and the bias correction — that is the claim, and it is defensible.

---

## Risk register

1. **The seductive-hard-leg trap** — the single most likely failure mode was spending weeks 1–5 on multi-view geometry and ONNX-in-Lambda, watching it fail to converge on handheld low-texture concrete, and reaching week 6 with no demo, no COOL run, and finals starting. **Mitigated by executing the cut in week 1, not deferring it.**
2. **Loop 2 is where the strongest agency lives and is also the most cuttable module.** Loop 1 alone qualifies for the award, so Loop 2 is upside. But if it degrades into pasted coding-assistant transcripts it lands inside the "AI coding assistant" carve-out. It ships as a runnable, logged artifact or it does not ship.
3. **Crowded premise.** Crack inspection is an organizer-listed area; many of 761 entrants will attempt some version. Differentiation is metrological rigour, not the premise. Innovation (20%) is capped by this and that is accepted.
4. **No real factory is inspected.** Validation is public mask datasets, instrumented reference widths, and accessible Dhaka structures. Stated plainly; the demo never implies factory adoption.
5. **Solo bandwidth against a fixed deadline.** Report and video drafted from week 6, not week 9.
