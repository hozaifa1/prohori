# PROHORI — agentic crack metrology with a measured error budget

## Name and pitch
**PROHORI** (প্রহরী, Bengali: *sentry*) turns a phone camera into a calibrated crack-measuring instrument. It does not report that a crack exists. It reports **how wide the crack is in millimetres, with a stated uncertainty**, compares that against the code limit for the site's declared exposure class, compares it against the same joint's measurement from a previous visit, and escalates to a named human engineer with the evidence attached. An agent decides, per frame, whether the image it just received is good enough to certify a number — and when it is not, it tells the person holding the phone exactly what to change.

The distinction that carries the entry: **every competing crack project outputs a classification. PROHORI outputs a measurement with an error budget.** A classification cannot be triaged against an engineering standard. A measurement can.

---

## Problem, users, impact

On 24 April 2013 Rana Plaza collapsed outside Dhaka, killing 1,134 people. Cracks had been observed and reported the day before; workers were sent back inside. It remains the deadliest structural failure in the history of the garment industry.

The inspection regime built afterwards is real and still running, and still short of capacity. RMG Sustainability Council and International Accord reporting records **93,576 hazards found in initial inspections of 1,755 factories, a further 58,367 in follow-up inspections, and only 665 of roughly 1,800 factories fully remediated** — more than a decade on. The stated bottleneck is inspector availability. Bangladesh's RMG sector runs roughly 4,000–5,200 registered factories and 4.4 million workers, and about 80% of national export earnings.

*(Scope honesty: these figures describe structural-safety inspection and remediation capacity. They are not used here to describe the RSC's separate labour-rights mandate, which is a different programme and is not evidence for this problem.)*

What is missing between formal engineering audits is not crack *detection* — a trained eye does that fine. It is a **cheap, repeatable, trended, numeric** record: the same joint, measured the same way, on a schedule, by whoever is already walking the building.

**Users.** (1) Safety officers and independent structural engineers doing walkthrough inspections; (2) building owners and facility managers who need defensible evidence between audits; (3) any low-resource setting — schools, clinics, informal housing — where a phone exists and a crack comparator, total station, or drone does not.

**The engineering standard.** ACI 224R-01 Table 4.1, tolerable crack widths for reinforced concrete under service load:

| Exposure condition | in | mm |
|---|---|---|
| Dry air or protective membrane | 0.016 | 0.41 |
| Humidity, moist air, soil | 0.012 | 0.30 |
| De-icing chemicals | 0.007 | 0.18 |
| Seawater, spray, wetting and drying | 0.006 | 0.15 |
| Water-retaining structures | 0.004 | 0.10 |

ACI attaches an explicit caveat: these widths "are not always a reliable indication of steel corrosion and deterioration of concrete to be expected." **PROHORI therefore never emits a safety verdict.** It emits a measurement, its uncertainty, the declared exposure class, that class's limit, the delta since last visit, and a request that a qualified human look. Refusing to output a verdict a phone cannot justify is a design commitment, not a limitation.

---

## What the system does — one real run

An inspector opens PROHORI in a phone browser (PWA, no app store) at a beam–column joint. A printed ChArUco sheet is taped flat beside the crack as the metric reference. They sweep the camera for ~15 seconds.

1. **Perceive.** Frames stream to an arm64 Lambda running OpenCV 5's rewritten DNN engine on an ONNX crack-segmentation model. First batch returns a mask at confidence 0.42, with a Laplacian-variance blur score in the bottom decile.
2. **Decide — and this is a real decision, not a threshold.** The gate (confidence < 0.6) only says *"do not certify."* It does not say what to do about it. The triage agent, running on Bedrock, receives a compact structured observation — mask confidence, blur score, ChArUco corner count, estimated baseline between frames, crack pixel extent, ambient exposure — and chooses from an **open action space** (`request_reshoot(specific_instruction)`, `request_wider_sweep`, `request_relight`, `request_marker_reposition`, `accept_degraded_with_widened_uncertainty`, `abandon_and_log`), writing a free-text rationale that is stored verbatim. Here it returns `request_reshoot("motion blur dominates; brace the phone against the wall and move ~20 cm closer")` with its reasoning logged.
3. **Act — physical.** The instruction renders over the live camera feed. The human repositions. The human is the actuator; the agent is the planner. This is the standard embodiment in image-guided workflows.
4. **Perceive again.** Confidence 0.88, blur cleared.
5. **Decide → a different tool now fires.** Because the frames are certifiable, the orchestrator invokes a tool it did **not** invoke on the first pass: wide-baseline registration with OpenCV 5's **ALIKED** / **DISK** deep local features and **LightGlueMatcher**. Learned features are not decoration here — bare concrete is exactly the low-texture, repetitive surface where ORB and SIFT degrade, and DISK was built for wide-baseline low-texture scenes. 42 inlier correspondences returned.
6. **Decide → triangulate.** Inliers clear the geometry gate, so pose recovery and triangulation run, with the ChArUco board supplying absolute scale that monocular reconstruction cannot recover on its own. Had inliers come back at 9, the agent would have chosen a *different* corrective action — wider sweep, not steadier hands — from the same open action space.
7. **Measure.** The mask is skeletonised (`ximgproc.thinning`), local width read from a `distanceTransform`, **the calibrated +1.00 px estimator bias subtracted** (see error budget below), and converted to millimetres through the triangulated, marker-scaled geometry. Result: **0.34 mm ± 0.06 mm**.
8. **Decide with history.** DynamoDB returns this joint's prior record: 0.21 mm, 61 days ago. The site is declared *humidity / moist air* exposure — limit 0.30 mm. Measured width exceeds the limit; growth is +62% in 61 days.
9. **Act — escalate.** Finding, mask, evidence images, uncertainty, trend and reasoning trace are written to S3 and DynamoDB, and SNS emails a named engineer: *"Joint-3, Site-A: 0.34 mm ± 0.06 (was 0.21 mm, +62% / 61 d). Exceeds ACI 224R-01 humidity-exposure limit 0.30 mm. This is a measurement, not a safety determination — engineering review requested. Evidence: [link]."*

Had the number come back low and flat, the action would have been *log and continue* — no interruption. **The action taken is a function of the measurement, not of a script.**

---

## OpenCV 5 depth

| Component | Why it is necessary, not decorative |
|---|---|
| `cv2.dnn` — rewritten engine, ~80% ONNX operator coverage | Runs the segmentation backbone, and lets the build-time optimizer swap backbones as a config change rather than a rebuild. The optimizer's whole premise depends on this. |
| **ALIKED**, **DISK**, **LightGlueMatcher** (new `features` module) | Wide-baseline registration on low-texture concrete, where ORB/SIFT measurably degrade. LightGlue's confidence-scored matches are the signal the geometry gate reads. Classical detectors are retained as the **ablation baseline**. |
| 3D: `findEssentialMat`, `recoverPose`, `triangulatePoints` | Converts a 2D mask into metric geometry. This is the step that produces millimetres instead of pixels — the entire premise. |
| `cv2.aruco` ChArUco detection | Absolute scale. Monocular SfM is scale-free; there is no honest millimetre without a metric reference. |
| `imgproc`/`core`: `cvtColor`, CLAHE, adaptive threshold, `ximgproc.thinning`, `distanceTransform`, `findContours` | The measurement algorithm itself — **and deliberately the same function family COOL's 78-function benchmark targets**, so the performance story and the correctness story are the same code path rather than a synthetic proxy. |
| `FaceDetectorYN` | Redaction pass blurring incidental faces before any frame is persisted. A code-level answer to responsible operation, not a policy paragraph. |
| HAL / Universal Intrinsics 2.0 / KleidiCV | The reason the imgproc stage is worth benchmarking on Graviton at all: it runs per frame in a live loop, so its latency directly gates how fast the agent can respond to the person holding the phone. |

---

## The measured error budget (already begun)

Before committing to the estimator, it was characterised against exact-width synthetic ground truth:

| True width (px) | 3 | 5 | 7 | 9 | 15 | 21 |
|---|---|---|---|---|---|---|
| `2·distanceTransform` at skeleton | 4.00 | 6.00 | 8.00 | 10.00 | 16.00 | 22.00 |
| **Error** | +1.00 | +1.00 | +1.00 | +1.00 | +1.00 | +1.00 |
| area/length estimator | 3.04 | 5.11 | 7.21 | 9.35 | 16.00 | 23.01 |

The distance-transform estimator carries an **exactly constant +1.00 px bias**, independent of width — a pixel-centre convention artifact, removable in closed form rather than by fitting a fudge factor. The area/length estimator is better below ~9 px and worse above it, so the shipped estimator is width-dependent, and we can say why with data. This single table is the difference between a sub-millimetre claim that is hopeful and one that is defensible, and it is also the **accuracy-invariance probe for the COOL benchmark**: the corrected estimator must return bit-identical numbers under COOL and under stock OpenCV 5.

---

## Two agent loops, one system

### Loop 1 — Inspector (runtime, seconds)
Perception → Bedrock triage over an open action space → instruction to the human, or escalation to an engineer. Traced above.

### Loop 2 — Optimizer (build-time, hours) — organizer-listed area #6
A developer agent that improves the deployed pipeline from its own measurements:

1. Runs the current pipeline on the evaluation corpus **on Graviton under COOL**, producing a **per-subset** eval diff (wall / deck / pavement; lit / shadowed; hairline / wide) plus latency, throughput and cost.
2. An LLM reads that diff and **writes its own hypothesis in free text over an open option space** — it may propose new preprocessing code, not merely select from a frozen enum. Example logged output: *"IoU loss is concentrated in the shadowed-wall subset while lit-wall is unchanged; this is a contrast problem, not a capacity problem — try CLAHE ahead of segmentation before considering a larger backbone."*
3. It applies the change, re-measures, and either **autonomously redeploys** to the live Lambda endpoint (thresholds cleared and no accuracy regression beyond 5% against the live version) or **raises a human-approval request** with the eval diff attached.
4. Every hypothesis, measurement and promotion decision is logged verbatim and shipped as the **Agent Lab trace** in the repo.

**This is not an AI coding assistant writing the entry.** It is a shipped, re-runnable system component whose input is measurement and whose output is a change to what is running in production — which is the rulebook's own worked example of a qualifying developer-agent workflow.

### The agent ablation — the evidence that the agency is real
The unanimous weakness of every "agentic" hackathon entry is that the agency is a threshold cascade wearing agent language. PROHORI answers that with a **measurement instead of an assertion**: the same task is run under three policies —

- **P0 random** — pick a corrective action at random,
- **P1 fixed thresholds** — the if/else cascade a competing entry would ship,
- **P2 the reasoning agent** — open action space, free-text rationale,

— scored on *recovery rate* (did the requested action actually raise confidence on the next attempt?), *turns-to-certified-measurement*, and *escalation precision/recall against hand-labelled ground truth*. If P2 does not beat P1, we report that. **Nobody else in this competition will quantify how much their agent's reasoning is actually worth.** This single ablation is the strongest available evidence for the Agentic Vision rubric's "orchestration & autonomy" line, which is 25% of that award.

---

## COOL / Graviton plan

**Core workload on Graviton under COOL:** the exact per-frame measurement pipeline — `cvtColor` → CLAHE → adaptive threshold → `thinning` → `distanceTransform` → `findContours` — over a fixed 500-frame clip. Same code as the live system.

**Baseline:** stock `pip install opencv-python==5.0.0` on the same instance, same OS, same frames. One variable. This is the exact baseline OpenCV uses for COOL's own published numbers.

**Three-generation study.** COOL ships as three separate Marketplace listings — Graviton2, Graviton3 (COOL 2.0, c7g/m7g), Graviton4 (COOL 3.1 on OpenCV 5.0.0, c8g/m8g/r8g) — each with its own independent 7-day free trial. So the entry reports **COOL-vs-stock speedup across Neoverse N1 → V1 → V2**, not a single data point. This is a materially stronger artifact than the single-instance benchmark the field will submit, and it costs nothing.

**Measured:** per-stage latency; end-to-end fps; **cost per 1,000 frames** (instance $/hr ÷ throughput); CPU utilisation; **accuracy-invariance** (identical width outputs COOL vs stock); and **developer productivity** — an explicitly valid COOL axis, evidenced by the Optimizer's own wall-clock time-to-Pareto-front with COOL on versus off. Reported with COOL version, AMI ID, instance type and raw CSVs in the repo.

---

## AWS architecture and the $0 path

| Service | Role | Cost |
|---|---|---|
| EC2 **t4g.small** (Graviton2) | Always-on orchestrator, FastAPI, PWA, public endpoint | **750 free hrs/month through 2026-12-31** |
| **Lambda arm64** | Per-batch segmentation and registration | 1M req + 400k GB-s/month, permanently free |
| **S3** | Frames, evidence, reports, model artifacts | Free tier |
| **DynamoDB** | Per-joint measurement history, reason codes, agent traces | 25 GB always free |
| **SNS** (email only) | Engineer escalation | 1,000 emails/month free |
| **Bedrock** | Triage agent + Optimizer hypotheses; called per *decision*, never per frame | Free-Plan credits |
| **CloudWatch** | Logs, metrics, traces | Free tier |
| EC2 **c7g/c8g + COOL AMI** | Benchmark bursts only | Inside the three 7-day trials |

Zero-spend discipline: everything always-on is permanently free or free through 2026; **the only Marketplace software fee is confined to deliberately-timed free trials**, because AWS promotional credits do not cover third-party Marketplace fees. Worst case if a cancellation is missed is single-digit dollars, and calendar reminders are set per trial. Security: IAM least privilege, encryption at rest, no public buckets, face redaction before persistence.

---

## Evaluation

**Datasets.** SDNET2018 (56k labelled images, cracks 0.06–25 mm, wall/deck/pavement subsets) for segmentation; METU/Özgenel (40k) as cross-check; CrackForest for out-of-domain; plus a **self-collected two-visit Dhaka set** with caliper/crack-gauge ground truth.

**Metrics.** Segmentation IoU / precision / recall against published SDNET2018 baselines. **Width error against caliper ground truth, reported as a distribution with an error budget, not a single headline number.** Agent recovery rate, turns-to-certified, escalation precision/recall. COOL latency, throughput, $/1k frames, accuracy-invariance.

**Baselines and ablations.** (1) single-shot classifier, no re-shoot loop — what most entries will be; (2) manual crack-gauge measurement — current practice; (3) ORB/SIFT vs ALIKED/DISK+LightGlue; (4) **P0/P1/P2 agent-policy ablation**; (5) COOL on/off.

**Named failure modes, tested not hypothesised.** Motion blur; low light; ChArUco glare or occlusion (→ falls back to relative-width-only, never guesses scale); narrow baseline that never accumulates inliers (→ retry cap, then "measurement unavailable"); hairline cracks below the model's resolution near SDNET2018's 0.06 mm floor; and — stated as a real risk rather than assumed away — **domain shift onto painted, plastered, monsoon-weathered Bangladeshi facades, which is exactly where a model trained on US bridge decks should be expected to degrade.** This is measured on the self-collected set, and reported whatever it says.

---

## Demo and video

**What the judge does:** opens the public endpoint on their own phone, points it at a printed test panel with a known pre-measured crack and a ChArUco marker, deliberately shoots it blurred, watches the agent's rationale appear and request a specific fix, complies, and sees a measurement with uncertainty land — then opens the site-history page and the Agent Lab trace showing the Optimizer's logged hypotheses and a real redeploy.

**Five minutes:** 0:00 the builder on camera and the Rana Plaza / RSC framing; 0:30 architecture and the two loops; 1:15 live run — blur → reasoned instruction → registration → triangulation → 0.34 mm ± 0.06 → escalation email; 3:00 the error-budget table and the P0/P1/P2 ablation; 3:45 the three-generation COOL results with AMI IDs on screen; 4:30 the failure reel — marker glare, a domain-shift miss on a plastered wall — stated plainly.

---

## Honest risk register

1. **Solo builder with a real course load.** Final-semester EEE finals, GRE preparation and thesis work run concurrently. Mitigation: the vertical slice ships in week 1; loops 1 and 2 are independently demoable, so if the Optimizer slips it is cut without breaking the entry; the report and video are drafted from week 6, not week 9.
2. **Crowded category.** Crack inspection is the organizers' own listed area and many of the 761 entrants will attempt some version. Differentiation is in the stack, not the premise: metric width with a characterised error budget, an agent whose value is measured by ablation, and a three-generation COOL study. If a rival matches that depth we lose on execution, which is a fair fight.
3. **No real factory is inspected.** The problem framing is real and cited; the validation surface is public datasets plus accessible Dhaka structures. This is stated plainly in report and video, and the demo never implies factory adoption that did not happen.
4. **The metric reference is required, not optional.** Monocular reconstruction cannot recover absolute scale. The marker is one sheet of paper, fixed per site rather than per frame, and relative growth trend stays valid on frames without it.
