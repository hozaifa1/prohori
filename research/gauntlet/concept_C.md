# CONCEPT C — Prohori

## 1. NAME AND ONE-LINE PITCH

**Prohori** (Bengali প্রহরী — "sentinel, watchman").

An autonomous OpenCV 5 developer agent that designs, benchmarks on AWS Graviton under COOL, and redeploys its own concrete-crack structural-safety pipeline — then, in production, uses the same vision results to decide when to demand a better photo before it will trust its own measurement. One agent, two timescales (build-time self-optimization, run-time self-doubt), one deployed artifact that is a real inspection tool, not a demo.

## 2. PROBLEM, USERS, AND WHY IT MATTERS

On 24 April 2013 the Rana Plaza garment factory building near Dhaka collapsed, killing 1,134 people and injuring roughly 2,500 more — visible structural cracking had been reported the day before and workers were sent back in anyway ([Wikipedia](https://en.wikipedia.org/wiki/Rana_Plaza_collapse), [Clean Clothes Campaign](https://cleanclothes.org/campaigns/past/ua/2013/cases/ranaplaza)). The response was the Bangladesh Accord, now the **RMG Sustainability Council (RSC)**, which put ~1,800 factories under mandatory structural/fire/electrical inspection. As of December 2025, over a decade later: **93,576 safety hazards were found in initial inspections of 1,755 factories, another 58,367 in follow-ups, and only 665 of the 1,800 listed factories have fully completed remediation.** Industry reporting explicitly cites *inspector manpower shortage* and *slow follow-up inspection* as the reason remediation is stalled ([International Accord](https://internationalaccord.org/rsc-safety-remediation-progress-in-bangladesh/), [The Financial Express](https://thefinancialexpress.com.bd/home/one-third-of-identified-1800-factories-mend-safety-faults)). This sits on top of a sector employing over 4.4 million workers across roughly 4,000 factories and generating ~80% of Bangladesh's export earnings ([The Daily Star](https://www.thedailystar.net/business/news/difficult-year-the-apparel-factory-floor-4064836), [Wikipedia: Textile industry in Bangladesh](https://en.wikipedia.org/wiki/Textile_industry_in_Bangladesh)).

The bottleneck is not appetite for inspection, it is **inspector-hours**. A structural engineer walking a facade with calipers and a notebook does not scale to thousands of buildings on a repeat cadence. The users this targets are exactly that constrained population: RSC-style third-party inspectors, factory compliance officers, and building owners who need a **fast, repeatable, quantitative first pass** — flag which cracks widened since last visit, estimate width in millimeters (the number engineering standards actually key severity thresholds to, not "looks bad"), and escalate only the worst cases to a human engineer's limited time. This is triage infrastructure for an inspection backlog that is verifiably real and verifiably not shrinking fast enough, not a hypothetical use case invented to satisfy a rubric line.

Honesty check up front: Prohori is not deployed inside an actual RMG factory during the build window (see Section 11, weakness 1). The problem statement above is real and cited; the evaluation is on public benchmark data plus the builder's own field photos, and the impact claim is *transferability*, argued explicitly, not *field adoption*, claimed falsely.

## 3. WHAT THE SYSTEM DOES (one real run, end to end)

**Phase A — build-time: the agent builds its own product.**

1. Seed data loads: SDNET2018 (56,000 labeled concrete images, cracks annotated 0.06–25 mm wide, wall/deck/pavement subsets — [dataset DOI](https://doi.org/10.15142/T3TD19), [PMC description](https://pmc.ncbi.nlm.nih.gov/articles/PMC6247444/)) plus ~80 phone photos Hozaifa takes himself of real cracks on DU campus buildings and at home, each shot with a standard-size reference card (85.6 mm, ISO/IEC 7810 ID-1) held next to the crack for ground-truth calibration.
2. The agent proposes **candidate #1**: ResNet34-Unet ONNX segmentation model, FP32, reference-card scale calibration, no CLAHE, plain pip OpenCV 5.0.0 (no COOL). It runs this on the Graviton box (t4g.small under the COOL Graviton2 AMI, COOL disengaged for this run as the "off" control) and logs: IoU 0.92 vs SDNET masks, width MAE 1.8 mm vs the 80-photo field set, 640 ms/image, 1.56 img/s.
3. Against declared thresholds (MAE < 2.0 mm, throughput > 1.5 img/s, cost < $0.002/1000 img at t4g.small on-demand rate) candidate #1 **passes accuracy but the agent flags throughput as marginal** for the target use case (an inspector photographing a whole facade in one visit, dozens of shots).
4. **Decision → next tool call**: the agent mutates the config — swap to MobileNetV3-Unet, FP16, and switches the KleidiCV/COOL path on. Re-runs. Result: throughput jumps to 2.1 img/s (a COOL-attributable gain, isolated because only the backend flag changed), but IoU drops to 0.87 and width MAE rises to 2.4 mm — specifically concentrated in the shadow-heavy wall subset, which the eval harness reports per-subset, not just in aggregate.
5. **Decision → next tool call, again driven by the specific failure mode observed, not a blind grid step**: the agent adds a CLAHE contrast-normalization stage ahead of segmentation, because the failure was shadow-localized. Re-runs candidate #3: IoU 0.90, MAE 2.0 mm, throughput 2.0 img/s. Clears all three thresholds.
6. The agent **promotes candidate #3 to production**: it is not a report — it is a real AWS action, an automated redeploy (new container/config pushed to the Lambda function that serves the public endpoint, old candidate's weights archived to S3 with the eval report attached). This redeploy fires automatically because both thresholds cleared *and* the candidate does not regress accuracy more than 5% versus the currently live version; if either condition had failed, the agent would instead open a human-approval request rather than deploy (see Section 11, weakness 2).

**Phase B — run-time: the deployed pipeline doubts itself.**

7. A test user (a second inspector, or Hozaifa acting as one) uploads a phone photo of a crack through the public web endpoint. The reference card in frame is partially occluded by shadow. Segmentation confidence for the reference-card detector comes back at 0.41, below the 0.7 acceptance floor the agent set for itself during evaluation (see step 5's config, which recorded this floor from ROC analysis on the field set).
8. **This vision result changes the next action**: instead of returning a width number it cannot trust, the endpoint returns "reference card not confidently detected — please retake the photo with the card fully lit and unshadowed, or move 30cm closer." This is the same low-confidence-gating logic, reused, not a second independently built agent — a single threshold check on an output the pipeline already computes.
9. User retakes the photo. Card confidence 0.93. Pipeline reports: crack width 3.4 mm ± 0.4 mm (calibrated from card width in pixels), segmentation confidence 0.89, flagged "moderate — recommend re-inspection in 30 days" per a width-severity lookup table cited from standard crack-width serviceability limits.

## 4. OPENCV 5 DEPTH

- **Rewritten DNN engine (~80%+ ONNX op coverage)** — `cv2.dnn.readNetFromONNX` loads whichever segmentation backbone the agent's current candidate specifies (ResNet34-Unet vs MobileNetV3-Unet), switching backend/target and precision at runtime. This is load-bearing, not decorative: the entire search space in Section 3 step 2–5 depends on swapping architectures and precisions through one uniform API without hand-writing a new inference path per candidate.
- **HAL redesign / Universal Intrinsics 2.0 with Arm KleidiCV** — the imgproc stages the agent actually varies (`resize`, `createCLAHE`, morphological thinning for skeletonizing the crack mask to measure width along its length, `Canny`/`Sobel` for edge refinement) are exactly the 78 imgproc/core/I-O functions COOL claims to accelerate. This is the COOL differentiator and it is measured, not assumed — the eval harness isolates the KleidiCV-on/off flag as a single controlled variable (step 4).
- **ALIKED, DISK + LightGlue (OpenCV 5 deep local features/matcher)** — used in the alternate scale-recovery candidate path (two-view, no reference object needed): match keypoints across two photos of the same crack from different angles. This is necessary rather than decorative because classical detectors (ORB/SIFT) are documented to fail on low-texture, repetitive-aggregate concrete surfaces — the evaluation plan (Section 8) runs an explicit ORB-vs-ALIKED/DISK ablation on the same photo pairs to prove the deep features are earning their computational cost, not assumed superior.
- **Improved 3D module** (`recoverPose`, `triangulatePoints`) — converts the ALIKED/DISK+LightGlue two-view correspondences and the phone's approximate baseline into real-world scale, producing crack width in mm without a physical reference object. This is the "no card in shot" fallback candidate; the agent's search includes it as a genuine alternative arm, not a demo of the module for its own sake.
- **New N-dimensional core dtypes / batched array support** — the evaluation harness stacks validation images into batched N-d tensors to sweep batch-shape as one of the mutated config parameters (batch=1 vs 4 vs 8 changes Graviton throughput materially); this specifically exercises the improved core dtype/N-d support rather than looping images one at a time.

## 5. THE AGENTIC LOOP

**Perception → decision → action, concretely, twice:**

*Build-time trace* (Section 3, steps 3–6): perception = {IoU 0.87, width MAE 2.4mm concentrated in shadow-subset, throughput 2.1 img/s} → decision = "accuracy failure is shadow-localized, not global → add CLAHE, not a bigger model" (a specific causal read of the failure mode, logged as text, not a blind hyperparameter step) → action = re-run candidate #3, then on pass, **a real AWS deploy call** that changes what is running in production before any human looks at it.

*Run-time trace* (Section 3, steps 7–9): perception = {reference-card detection confidence 0.41 < 0.7 floor} → decision = "cannot certify a width number under this confidence" → action = the system's response to the human **changes from "here is a measurement" to "take this specific corrective action and resubmit"** — a physical action in the world (the human must move, relight, and re-shoot), not a caveat appended to a bad number.

Human control gate: any production promotion that clears thresholds *and* holds accuracy within 5% of the live version deploys automatically; anything that clears thresholds but regresses accuracy beyond that band is logged as a candidate and a human-approval prompt is raised instead of an autonomous deploy, with the full eval diff attached. This is documented and logged, not asserted after the fact.

## 6. COOL / GRAVITON PLAN

**Core workload measured**: the full inference pipeline — preprocess (resize/CLAHE) → DNN segmentation → postprocess (thinning + width measurement) — run inside COOL's prebuilt Python venv (`/opt/cool/venvs/python_3.12`) on Graviton.

**Instances**: 
- Sustained/free leg: `t4g.small` (Graviton2), under AWS's standing 750 free-hours/month offer through 2026-12-31, using the COOL Graviton2 Marketplace AMI.
- Peak-verification leg: a `c8g.large`/`c8g.xlarge` (Graviton4) burst during COOL's one-time 7-day free software trial, funded by AWS Free Plan sign-up credits (not the builder's money) — see Section 7 for why this is time-boxed.

**Baseline**: identical Python code, identical instance family, running pip-installed vanilla OpenCV 5.0.0 with COOL disengaged. This mirrors the comparison AWS's own COOL blog post already publishes (1.2 fps → 1.6 fps), so the judge has an external reference point to sanity-check Prohori's own numbers against.

**What exactly gets measured** (all five candidates × both COOL-on/off, logged to a CSV the report ships with):
- latency (ms/image, p50/p95),
- throughput (images/sec),
- cost ($/1,000 images, computed from the instance's published on-demand rate ÷ measured throughput),
- accuracy (IoU, width MAE mm) — held constant across the COOL toggle to prove COOL doesn't silently change results,
- **agent search productivity**: wall-clock minutes per candidate evaluated, and candidates-per-hour the optimizer can complete — a direct "developer productivity" measurement (an explicitly valid COOL axis per the rubric), showing COOL doesn't just make the shipped product faster, it makes the agent that builds the product faster too, compounding across the 59-day build.

## 7. AWS ARCHITECTURE — how it stays at $0

- **EC2 `t4g.small`** (Graviton2, AWS Free Tier, 750 hrs/month through 2026-12-31): hosts the agent's optimizer loop and, by default, the fallback production inference path running plain OpenCV 5.0.0 (no COOL) so the service keeps running at $0 indefinitely, independent of any trial window.
- **AWS Lambda, arm64** (Graviton2, free tier: 1M requests + 400,000 GB-s/month): serves the public-facing per-photo inference endpoint via a Function URL — this satisfies the "working public web endpoint" requirement without paying for an always-on API Gateway.
- **S3**: stores candidate weights, configs, and eval reports (covered by Free Plan credits / new-account free tier).
- **CloudWatch**: logs and a basic dashboard (latency, error rate, confidence-gate trigger rate) for the "observability" component of the Responsible Cloud Delivery rubric line, at no cost within free-tier log volume.
- **COOL Marketplace AMI**: used **only** during the one 7-day free trial burst for the verified Graviton4 benchmark in Section 6. This is a deliberate, documented choice, not an oversight: AWS's own Marketplace buyer documentation states promotional/free-tier credits do **not** apply to Marketplace software fees except for Bedrock foundation models ([AWS Marketplace buyer guide](https://docs.aws.amazon.com/marketplace/latest/buyerguide/buyer-paying-for-products.html)) — so a sustained COOL-on production deployment would eventually cost real money that G2 forbids spending. The trial window produces a fully reproducible, timestamped, one-command-repeatable benchmark; production defaults back to free-tier compute.
- Grant funds ($150, if awarded) are treated as a cushion for the c8g burst's EC2-minutes, never a requirement — the plan is written to close at $0 even if the grant is not awarded.

## 8. EVALUATION PLAN

**Datasets**: SDNET2018 (primary, 56,000 images, cracks 0.06–25mm annotated, W/D/P subsets) as the large quantitative benchmark; ~80–120 of the builder's own phone photos (DU campus + home, reference-card calibrated) as a small, explicitly-labeled "field-realism check" — not statistically powered, reported as such, not inflated.

**Metrics**: segmentation IoU/F1 against SDNET masks; crack-width MAE (mm) against hand-measured field-set widths; latency/throughput/cost as in Section 6; COOL-on vs COOL-off speedup ratio per candidate; agent search efficiency (candidates evaluated to reach the Pareto front, wall-clock minutes).

**Baselines**:
1. Plain OpenCV 5.0.0, no COOL — the hardware/software baseline.
2. **A hand-picked "first-try" pipeline a competent engineer would choose without search** (fixed ResNet34-Unet + reference-card calibration, no tuning) — this is the baseline that actually tests whether the *agent's search* adds value over a human's first guess, which is the whole claim of a developer agent and the easiest thing for a hostile judge to doubt.
3. ORB+RANSAC vs ALIKED/DISK+LightGlue on the same two-view photo pairs — isolates whether the OpenCV 5 deep-feature upgrade earns its cost on this specific low-texture surface type.

**Failure taxonomy** (counted and reported, not just aggregated away): false-negative cracks under harsh shadow/glare; width overestimation on hairline cracks near/below the training data's 0.06mm floor; reference-card misdetection rate triggering the re-photo request (this is reported as a *feature* usage rate, not hidden as an error rate); two-view scale-recovery failures when the user doesn't move enough between shots for a usable baseline.

## 9. DEMO AND VIDEO PLAN

**What the judge clicks**: the public Lambda Function URL opens a single page — upload one or two crack photos → sees the segmentation overlay, width in mm with an uncertainty band, and (on a deliberately shadow-occluded test photo the judge can also upload themselves) the live re-photo-request behavior from Section 3 step 8. A second tab, "Agent Lab," shows the optimizer's actual search log: every candidate config tried, its measured accuracy/latency/cost with COOL on and off on Graviton, the Pareto front chart, and which candidate is live in production right now with the logged reason it was promoted.

**5-minute video**: 0:00–0:30 Hozaifa on camera, Dhaka, EEE final semester, why Rana Plaza framing is personal and cited, not decorative; 0:30–1:15 the numbers (1,134 dead, 665/1,800 factories remediated, inspector shortage cited by name); 1:15–2:00 architecture diagram walkthrough (perception→decision→action, dev-loop and run-loop both shown); 2:00–3:15 live: the agent evaluating candidates on the Graviton box, screen-recorded terminal/dashboard showing the real fps jump COOL-on vs off; 3:15–4:15 live production demo: upload a real photo, get a measurement, then upload a deliberately bad photo and watch it get rejected and a specific corrective action requested; 4:15–4:50 evaluation results and failure cases shown honestly, including the ORB-vs-ALIKED/DISK ablation number; 4:50–5:00 close with the impact numbers restated.

## 10. 59-DAY SOLO BUILD PLAN (2026-08-28 → 2026-10-26)

- **Week 1 (Aug 28–Sep 3)**: Submit grant proposal. Stand up AWS account, `t4g.small` free-tier instance, decide COOL trial timing. Pull SDNET2018. Start collecting own field photos (reference-card calibrated). Freeze the candidate config schema (backbone × precision × preprocessing × scale-recovery strategy × KleidiCV flag × batch shape).
- **Week 2 (Sep 4–10)**: Build pipeline v0 — single fixed config, ONNX segmentation + reference-card calibration — running end-to-end on the laptop and on `t4g.small`.
- **Week 3 (Sep 11–17)**: Build the evaluation harness (IoU, width MAE, latency/throughput/cost, per-subset breakdown) and validate it against SDNET2018.
- **Week 4 (Sep 18–24)**: Build the agent loop itself — candidate generation/mutation policy driven by observed failure modes, Pareto tracking, promote/rollback logic with the 5%-regression human-approval gate. Wire it to real AWS redeploy calls (Lambda config update, S3 archive).
- **Week 5 (Sep 25–Oct 1)**: Execute the 7-day COOL Graviton4 trial burst — the verified, reproducible COOL-vs-baseline benchmark across the full candidate grid. Implement the ALIKED/DISK+LightGlue+3D two-view scale-recovery candidate.
- **Week 6 (Oct 2–8)**: Build the run-time confidence-gating wrapper and the public Function URL endpoint/frontend. (Grant Zoom check-in window, if awarded, falls here.)
- **Week 7 (Oct 9–15)**: Full evaluation pass on the field photo set; run the two baselines and the ORB-vs-ALIKED/DISK ablation; compile the failure taxonomy. Add CloudWatch dashboards.
- **Week 8 (Oct 16–22)**: Architecture diagram, technical report, repo cleanup, pinned dependencies, build/deploy/test instructions, responsible-use section.
- **Week 9 (Oct 23–26)**: Record and edit the video, rehearse the live demo end to end, submission buffer before 2026-10-26 23:59 PT.

## 11. HONEST WEAKNESSES

**1. No real RMG factory ever sees this.** The impact section cites Rana Plaza and RSC remediation statistics, but the actual evaluation runs on a public dataset and the builder's own phone photos of campus and home concrete — not a single garment factory wall. A hostile judge's exact line: "you built an inspection tool and inspected nothing that mattered." **Survivable, not erasable.** The problem statement is real and independently cited (Section 2), the *transferability* claim (concrete cracks are concrete cracks regardless of building type) is defensible and stated as such rather than dressed up as field validation, and a stretch goal — a cold email to RSC or a local civil engineering department for even one real facade photo set — is listed as exactly that, a stretch goal, not a claimed deliverable. What this concept must never do is let the demo video imply factory adoption that did not happen.

**2. The "agent" could be read as hyperparameter search wearing a costume.** A skeptical judge scores "orchestration & autonomy" (25% of the Agentic Vision rubric) low if this looks like a grid sweep with an LLM narrating it after the fact. **Survivable if and only if the mutation policy visibly reasons from the specific failure mode** (Section 3 step 5: the CLAHE addition follows directly from the shadow-localized failure, not from an exhaustive next-grid-cell step) and the promote/rollback gate makes a real, logged, sometimes-autonomous, sometimes-human-gated production decision (Section 5). If the actual implementation degrades into an un-annotated grid sweep because of time pressure in Week 4, this weakness becomes fatal — the decision log is the single artifact that most needs protecting from schedule slip.

**3. COOL only ran for one 7-day trial window, not in steady-state production.** The Best Use of COOL rubric weights "verified COOL on Graviton" at 30%; a hostile judge asks why the flagship Special Award's technology was used once and then switched off. **Survivable on the rubric's own text** — the qualifying bar requires COOL execute the claimed core workload with a reproducible method, inputs, baselines, and results, not continuous operation — and the reason is disclosed rather than hidden: AWS Marketplace software fees are explicitly excluded from promotional/free-tier credits except for Bedrock models (Section 7, cited), so sustained COOL-on production would silently break the $0 constraint the competition itself imposes. Making that constraint visible, rather than quietly running COOL 24/7 and hoping no judge checks the marketplace pricing page, is itself evidence for the "responsible cloud delivery" line of the main rubric. The risk that remains: if the 7-day trial produces noisy or unconvincing numbers (single burst, no repeat runs), there is no second trial to fall back on without spending real money — so the trial week's execution has zero margin for error and should be rehearsed on the free `t4g.small` COOL-Graviton2 listing first if one exists, to de-risk the one-shot Graviton4 burst.

---

**200-word summary**: Prohori is a developer agent that builds its own product: it generates candidate OpenCV 5 crack-inspection pipelines (ONNX segmentation backbone × precision × preprocessing × scale-recovery strategy × KleidiCV on/off × batch shape), runs each on AWS Graviton under COOL, measures accuracy (IoU, crack-width MAE against SDNET2018 and the builder's own reference-card-calibrated field photos) against latency/throughput/cost, and — reasoning from the specific failure mode each candidate exhibits, not blind grid search — mutates toward a Pareto front and autonomously redeploys the winner to a public Lambda endpoint. The deployed service then reuses the same confidence logic at run-time: a photo with an undetectable scale reference is refused with a specific corrective instruction ("retake, card fully lit") rather than returning an untrustworthy number. The application isn't arbitrary — it targets Bangladesh's RMG structural-safety inspection backlog, where RSC data shows only 665 of 1,800 flagged factories have completed remediation over a decade after Rana Plaza's 1,134 deaths, citing inspector shortage as the explicit bottleneck. One agent, one artifact, two timescales, real cited impact numbers.

**Single greatest vulnerability**: no real factory ever sees this pipeline during the build window — the impact case is argued and cited, not field-validated, and a hostile judge can call that gap directly.
