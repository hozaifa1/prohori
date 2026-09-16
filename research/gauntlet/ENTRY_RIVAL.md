# ARGUS — Agentic Reconstruction for Geometric Urban Surveillance

*OpenCV AI Competition 2026 — full entry*

---

## 1. Name and pitch

**ARGUS.** Named for the hundred-eyed watchman: a system that keeps looking after everyone else has stopped.

A field operator walks around a structure with a phone for ninety seconds. ARGUS turns that walkthrough into a metrically-calibrated 3D digital twin, tells the operator in real time where the reconstruction is still weak and where to point the camera next, and on every repeat visit compares the new twin to the structure's own history — as true 3D geometry, not a 2D pixel guess — to decide whether anything has actually moved. It escalates exactly one thing to a human: a calibrated, evidenced ticket asking an engineer to look. It never says "unsafe." It never analyzes a single photo in isolation. It watches the same wall, the same slab, the same joint, forever, and it only speaks when the geometry itself has changed by more than measurement noise allows.

ARGUS is built to contend for all three prizes on their own terms: OpenCV 5's new deep-feature and 3D modules do the actual seeing (Technical Execution); a live vision-driven capture-guidance loop and a separate deployment-tuning developer-agent loop each independently satisfy the "vision changes a later action" bar (Agentic Vision); and the reconstruction pipeline — the genuinely CPU-heavy CORE workload — is benchmarked with a reproducible, zero-cost, cross-generation study across all three Graviton COOL listings (Best Use of COOL).

## 2. Problem, users, and impact

Continuous structural health monitoring — fiber-optic strain sensors, tiltmeters, LiDAR scan trucks — exists, but it is capital equipment that only gets deployed on flagship assets: major bridges, dams, airports. The overwhelming majority of the world's structural inventory — municipal retaining walls, parking structures, footbridges, school buildings, apartment blocks — gets inspected by a person with a clipboard, at whatever interval the budget allows, using judgment calibrated on the last visit's memory rather than measurement.

This gap is largest exactly where the organizer's welcomed domains overlap hardest: **safety** and **smart cities** in resource-constrained regions. A municipal public-works department in a mid-sized city, a university facilities-management office, or a post-disaster rapid-assessment team does not have a scan truck or a sensor budget. It has phones.

**Users:** municipal infrastructure-asset managers, university/hospital facilities engineers, and disaster-response structural assessment teams (post-earthquake, post-flood triage) who need repeatable, quantitative structural monitoring without sensor capital cost.

**Impact:** ARGUS converts an unstructured phone walkthrough into the kind of quantitative, repeatable, metrically-scaled measurement that today only fixed sensor networks provide — at the cost of a phone and a set of $2 printed ChArUco reference markers bolted to the site once. It catches the failure mode that 2D-only inspection tools structurally cannot: **out-of-plane deformation** — bulging, settlement, lateral displacement — which does not show up as a crack or a texture anomaly in a single photo, only as a change in 3D shape between visits.

## 3. What the system does — a concrete end-to-end run

**Visit 1 (baseline capture), Retaining Wall B, Site 3:**

1. Operator opens the ARGUS Scout web app on a phone, selects the site, and walks a slow arc in front of the wall while recording (~90 s, ~600 frames sampled to ~150 keyframes). Three ChArUco markers, bolted to the wall at the first visit, are visible in several frames.
2. Frames stream to S3 via presigned URLs as they're captured. A Step Functions workflow starts per batch.
3. On a Graviton worker, `cv2.quality` (reference-free blur/exposure scoring) and a Laplacian-variance gate drop unusable frames before any expensive processing runs.
4. `ALIKED` and `DISK` (via `cv2.features`) extract deep keypoints; `LightGlueMatcher` matches across wide-baseline pairs to build a view graph. `cv2.calib` recovers the essential matrix, poses (`recoverPose`), and a sparse point cloud (`triangulatePoints`); `cv2.aruco`'s `CharucoDetector` locks the reconstruction to metric scale and a fixed world frame tied to the physical markers.
5. **While the operator is still walking**, the coverage map is updated after every batch. Batch 47–52 comes back with mean LightGlue match confidence 0.35 in the northeast corner (below the 0.50 gate) and a 22% coverage gap there. The agent pushes a guidance event over a WebSocket to the phone: an AR arrow and the text *"Re-scan the lower-left corner, hold 1 m closer."* The operator complies; 14 more frames close the gap. This is the live, vision-changes-the-next-physical-action loop — not narration, an instruction that alters what the camera does next.
6. Once coverage and mean reprojection error clear threshold (96% coverage, 0.41 px reprojection error), dense reconstruction runs (`cv2.stereo` / `cv2.rgbd` for dense depth, `cv2.ptcloud` for the fused cloud). This becomes the site's baseline twin, stored in S3 with metadata (pose graph, marker transform, capture date) in DynamoDB.

**Visit 2, five weeks later — the diagnostic run:**

7. A new capture repeats steps 1–6. Before diffing, a lightweight ONNX segmentation network (loaded through the rewritten `cv2.dnn` engine) masks out vegetation growth and a parked utility cart visible in this visit but not the last — dynamic occluders that would otherwise register as false geometric change.
8. The new (masked) dense cloud is coarse-aligned to the baseline twin with `cv2.surface_matching` (point-pair-feature global registration — built for exactly this "align a new scan to a known model" problem) and refined with ICP through `cv2.ptcloud`/`cv2.calib`.
9. A signed per-point distance diff is computed. Result: a localized 3.8 mm ± 0.6 mm outward bulge over 0.4 m² on the wall face — more than 2σ past the site's calibrated alert threshold (2.5 mm, set from the repeatability rig described in §7).
10. **Decision changes as a direct result of this vision output:** the agent calls `create_ticket(severity="review_required", evidence=[diff_heatmap.png, raw_pointcloud.ply, confidence=0.94])`. An SNS/SQS path puts the ticket in the engineer's queue with the full evidence bundle attached. No verdict is printed. The system has never once, on any visit, said "unsafe" — it reports a measured displacement, its uncertainty, and asks a named human to decide, exactly the "appropriate human control" posture the rubric rewards and a "print UNSAFE from a phone photo" system actively scores against.
11. A human engineer opens the ticket in the dashboard, reviews the diff heatmap and raw cloud, and either dismisses it (recorded, feeds the false-escalation metric) or confirms and schedules follow-up (recorded, feeds the taxonomy of confirmed deviations).

## 4. OpenCV 5 depth — specific modules and why each is necessary

This is a 3D geometric-change-detection system, not a 2D classifier with a vision-model bolted on. Every module below is load-bearing, not decorative, and every symbol listed was locally verified against the installed `opencv-python 5.0.0.93` build before being committed to.

| Module / symbol | Role in ARGUS | Why it has to be this, not a shortcut |
|---|---|---|
| `cv2.features` — `ALIKED_create`, `DISK_create`, `LightGlueMatcher_create` | Deep keypoint extraction + confidence-scored wide-baseline matching for the SfM front end | Retaining walls and facades are exactly the low-texture, repetitive, wide-baseline scenes classical SIFT/ORB struggle with. We run the classical pipeline as a permanent side-by-side ablation (§8), not a placeholder — it's retained in OpenCV 5 for backward compatibility, which makes this comparison free |
| `cv2.calib` — `recoverPose`, `findEssentialMat`, `triangulatePoints`, `solvePnP`, `stereoRectify` | Two-view geometry, camera pose recovery, sparse triangulation | This is the actual multi-view geometry math the reconstruction is built on, not a black-box SLAM library |
| `cv2.aruco` — `ArucoDetector`, `CharucoBoard`, `CharucoDetector`, `getPredefinedDictionary` | Fixed physical reference markers give the twin real-world metric scale and a stable world frame across visits, months apart | Without metric ground-truth scale, a "3.8 mm bulge" claim is meaningless — this is what makes the number defensible |
| `cv2.stereo`, `cv2.rgbd` | Dense depth / dense point generation from the posed image set | Sparse SfM points alone can't produce a diff-able surface; the diff needs dense coverage |
| `cv2.ptcloud` | Point cloud fusion and ICP-style fine registration | Native OpenCV 5 3D-vision module, used exactly for its intended purpose: aligning and comparing point sets |
| `cv2.surface_matching` | Global point-pair-feature registration of the new scan to the historical twin before ICP refinement | Coarse alignment across a five-week gap, differing camera paths and possible marker drift needs a global registration step before local ICP will converge — this module exists precisely for "align new scan to known 3D model" |
| `cv2.quality` | Reference-free blur/exposure scoring, gates frames before expensive processing and flags weak evidence in escalation tickets | Cheap, principled frame triage instead of a hand-tuned heuristic |
| `cv2.dnn` (`readNetFromONNX`, rewritten DNN engine, ~80%+ ONNX op coverage) | Loads the ALIKED/DISK ONNX weights (required by the OpenCV wrapper) and a lightweight semantic segmentation model for dynamic-occluder masking (vegetation, vehicles) | OpenCV 5's DNN rewrite is what makes running a real segmentation network *inside* the same OpenCV pipeline — rather than shelling out to a separate ML framework — practical |
| HAL / Universal Intrinsics 2.0 (Arm NEON/SVE codepaths, Arm KleidiCV tuning under COOL) | Not called directly — this is *why* the COOL story works | The CORE workload's hottest functions (feature-pyramid construction, distance-based correspondence search in ICP, image warps in rectification) are exactly the `imgproc`/`core` kernels COOL retunes. The architecture and the benchmark target are the same code path |

**Deep-vs-classical ablation is a first-class deliverable, not an aside.** The same view-graph pipeline runs twice per benchmark sequence — once with ALIKED+DISK+LightGlue, once with SIFT+ORB+brute-force matching — and reports match precision/recall and final pose accuracy for both. On the low-texture/wide-baseline subset of our field dataset, this is where we expect (and will show) the deep features to win decisively; on well-textured, close-range subsets we expect them roughly at parity — reported honestly either way.

## 5. The agentic loop — architecture and a concrete trace

**Perception → decision/orchestration → action**, two independent loops, both qualifying under the rubric's bar (a vision result changes a later plan, tool call, action, or human-approval request) and both traceable end-to-end.

**Loop A — operational (active-perception capture guidance + escalation):**

```
[cv2 feature/coverage metrics] --> [coverage-gap / confidence policy] --> [WebSocket push: re-scan instruction to phone]
                                                                       --> [operator action changes: new frames captured]
[cv2 point-cloud diff + uncertainty] --> [threshold-vs-history policy] --> [create_ticket() / SNS to human queue]
                                                                        --> [engineer approval gate before status changes]
```

**Loop B — developer-agent (COOL-aware deployment tuning):** an MCP-driven agent (hosted via `amazon-bedrock-agentcore-mcp-server`, driven from Claude Code during build and from a scheduled Lambda in production) exposes tools `run_benchmark`, `read_benchmark_result`, `update_deployment_config`, `create_ticket`, `push_guidance`. It runs the COOL-vs-stock benchmark (§6) on a schedule and after every pipeline code change, reads the measured throughput/cost, and — when a configuration change actually wins — rewrites the ECS task definition's instance-family requirement. This is exactly the explicitly-included case from the rubric text: *"iteratively invokes, evaluates, and adjusts an OpenCV 5 workload, with COOL where applicable... using runtime measurements to change a later tool call, configuration, or deployment."*

**Concrete trace (`scan-2026-xx-014`, Retaining Wall B, Site 3 — corresponds to §3 steps 5–10):**

```
[PERCEPTION] batch 47-52: LightGlue mean confidence=0.35 (gate 0.50), NE coverage gap=22%
[DECISION]   coverage_policy.trigger -> request_recapture(region="NE_corner", reason="low_match_confidence")
[ACTION]     ws.push(scout_app, "Re-scan lower-left corner, hold 1m closer")           <- operator behavior changes
[PERCEPTION] batch 65: NE coverage=96%, reprojection_error=0.41px
[DECISION]   coverage_policy.satisfied -> proceed(dense_reconstruction)
[PERCEPTION] point_cloud_diff vs twin(2026-07-02): 3.8mm +/- 0.6mm bulge, area=0.4m^2, z=2.3
[DECISION]   escalation_policy.trigger (threshold=2.5mm) -> create_ticket(severity="review_required", conf=0.94)
[ACTION]     sns.publish(engineer_queue, ticket_id="T-00142", evidence=[diff_heatmap.png, raw_pointcloud.ply])
[HUMAN]      engineer opens T-00142, confirms deviation, schedules follow-up inspection    <- gate, not autopilot
```

```
[DEV-AGENT PERCEPTION] nightly bench: c7g.medium, COOL trial day 3/7, CORE workload throughput = 1.7x stock, $0.01/hr fee
[DEV-AGENT DECISION]   deployment_policy: measured gain > 1.3x threshold -> adopt
[DEV-AGENT ACTION]     update_deployment_config(target="c7g.medium+COOL") -> rewrites ECS task definition
[RESULT]               next production scan (scan-2026-xx-015) executes on the updated instance/COOL config automatically
```

Both loops are logged to CloudWatch with the full perception→decision→action chain, timestamped and correlated by `scan_id` / `run_id`, which is the observability evidence the "failure handling & human control" and "responsible cloud delivery" rubric lines ask for.

## 6. COOL / Graviton plan — baseline and measurements

**CORE workload nominated for COOL:** the feature-extraction + matching + geometric-estimation + point-cloud-registration stage (§3 steps 4, 8) — the heaviest, most parallelizable, most `imgproc`/`core`-bound part of the pipeline, and the part whose hot functions are exactly what COOL retunes.

**Baseline (the clean A/B):** the identical pipeline code and identical fixed benchmark input (a pinned 12-sequence, ~500-frame set covering the ablation and repeatability-rig data) run on **stock `opencv-python==5.0.0.93` pip wheels** on the same instance, same Ubuntu 24.04 arm64 OS, same everything — only the COOL venv activation differs. This is deliberately the same baseline OpenCV itself uses ("78 functions vs default OpenCV 5.0.0 build"), which makes the comparison unimpeachable rather than home-grown.

**Cross-generation matrix (the differentiator):** ARGUS benchmarks all **three independent COOL Marketplace listings** — Graviton2, Graviton3 ("COOL 2.0"), Graviton4 ("COOL 3.1", built on OpenCV 5.0.0) — against their respective stock baselines, six cells total:

| Instance | Generation | Config | Throughput (frames/s, CORE stage) | Latency/scan (median) | $/scan |
|---|---|---|---|---|---|
| t4g.small / c6g.large | Graviton2 (N1) | stock | baseline | baseline | baseline (free tier) |
| c6g.large | Graviton2 (N1) | COOL | +12–18% | −13% | ~$0.01/hr trial |
| c7g.medium | Graviton3 (V1) | stock | baseline | baseline | baseline |
| c7g.medium | Graviton3 (V1) | COOL 2.0 | +20–35% | −22% | $0.01/hr |
| c8g.large | Graviton4 (V2) | stock | baseline | baseline | baseline |
| c8g.large | Graviton4 (V2) | COOL 3.1 | +25–70%* | −30%+ | $0.01/hr |

*\*Range anchored to OpenCV's own published per-function results (avg ~20% faster, up to ~1.8x on best-case functions, core modules >1.2x) and their published end-to-end figure (1.2 fps → 1.6 fps, ~30%); our own reproducible run supplies the exact figures for our specific workload mix and is what ships in the final report, not this range.*

**Reproducibility protocol:** `bench.py`, triggered by the developer agent via SSM RunCommand, N=20 runs per cell, reports median + IQR, pinned input hashes, pinned `opencv-python`/COOL version strings recorded per run. **Accuracy-invariance control:** every cell must return the same point-cloud coordinates and diff magnitudes (within float tolerance) as the stock Graviton2 baseline — proving COOL is a pure performance layer, not a numerically different code path. This is the single most important control in the whole benchmark: it is what turns "COOL made it faster" into "COOL made it faster without changing the answer," which is the only version of that claim worth trusting.

**Zero-spend execution:** each of the three Marketplace listings carries its own independent 7-day free trial. The benchmark campaign is scheduled as three deliberate, time-boxed bursts (one per generation), each subscription cancelled before conversion. Day-to-day development and the always-on public demo endpoint run on the perpetually-free `t4g.small` (750 free hrs/month through 2026-12-31) on stock OpenCV 5 — COOL is only ever active during a measurement burst or the final demo recording. Worst-case exposure if a trial is mistimed is bounded at the $0.01/hr tier; an AWS Budgets hard alarm is wired to auto-stop the instance as a backstop.

## 7. AWS architecture

```
                         ┌─────────────────────────┐
  ARGUS Scout (mobile)   │   API Gateway (WebSocket)│──── live guidance push
  presigned upload  ────▶│   + REST (Lambda, arm64) │◀─── coverage/diff status
                         └───────────┬──────────────┘
                                     │
                                     ▼
                         ┌─────────────────────────┐
                         │      S3 (raw video,      │
                         │  point clouds, twins)     │
                         └───────────┬──────────────┘
                                     │ triggers
                                     ▼
                         ┌─────────────────────────┐
                         │   Step Functions          │  orchestrates per-scan stages
                         └───────────┬──────────────┘
                    ┌────────────────┼─────────────────┐
                    ▼                ▼                  ▼
        ┌───────────────────┐ ┌─────────────┐  ┌──────────────────┐
        │ ECS Fargate/EC2     │ │ t4g.small    │  │ MCP developer agent│
        │ Graviton (c7g/c8g)  │ │ (free tier)  │  │ (AgentCore-hosted,  │
        │ CORE workload:      │ │ always-on:   │  │ run_benchmark,       │
        │ COOL or stock,      │ │ API, dev,    │  │ update_deployment_   │
        │ per current config  │ │ light infer. │  │ config, create_ticket)│
        └─────────┬───────────┘ └──────────────┘  └──────────┬───────────┘
                  │                                            │ rewrites
                  ▼                                            ▼
        ┌───────────────────┐                        ┌──────────────────┐
        │ DynamoDB (site/    │                        │ ECS task definition│
        │ twin metadata,     │                        │ (instance family /  │
        │ ticket state)      │                        │ COOL vs stock flag) │
        └─────────┬───────────┘
                  ▼
        ┌───────────────────┐        ┌───────────────────┐
        │ SNS/SQS ticket      │──────▶│ CloudFront + S3 /    │  public dashboard:
        │ queue (human        │       │ Amplify static web   │  twin viewer, ticket
        │ approval gate)      │       │ (ARGUS dashboard)     │  queue, COOL benchmarks
        └───────────────────┘        └───────────────────┘
                  ▲
                  │ narrates findings (does not decide)
        ┌───────────────────┐
        │ Bedrock (optional)  │
        │ report-prose only   │
        └───────────────────┘

  Cross-cutting: CloudWatch (logs/metrics/traces for both agentic loops), IAM least-privilege
  roles, Secrets Manager, AWS Budgets hard-stop alarm.
```

Deliberate design choice: **Bedrock only writes prose for the human-readable report; it never sits in the decision path.** Every escalate/log/replan decision is made by the vision-and-geometry policy code directly on the `cv2` outputs. This keeps the Agentic Vision qualifying claim clean — vision changes the action, not "an LLM was shown a vision result and narrated it," which the rubric explicitly excludes for AI-coding-assistant use and which we extend as a design principle throughout.

## 8. Evaluation plan

**Datasets:**
1. **Public multi-view benchmark subset** (ETH3D/Tanks-and-Temples-style sequences with ground-truth camera poses) — grounds the deep-vs-classical feature ablation in third-party ground truth, not just our own data.
2. **Repeatability rig** — 3D-printed test panels on a micrometer-driven linear stage (0.1–5 mm controlled steps) with fixed ChArUco markers, built specifically to characterize the twin-diff pipeline's metric bias and precision against exact ground truth before trusting it on real structures — the 3D-displacement analog of a synthetic-ground-truth characterization, run and reported the same rigorous way: bias vs. true displacement, reported per magnitude bin, corrected in closed form if a systematic offset is found rather than papered over with a fudge factor.
3. **Field dataset** — 3–5 real structures (parking-ramp slab, retaining wall, pedestrian footbridge, building facade), each visited 3+ times across the build window, with independent total-station reference measurement where feasible and engineer-adjudicated confirmed/false-alarm labels on every ticket the agent raises.
4. **Adversarial/occlusion set** — sequences deliberately containing motion blur, rain, wet reflective surfaces, vegetation growth, parked-vehicle occlusion, and partial marker occlusion, built to populate the failure taxonomy below rather than to be avoided.

**Metrics:**
- Reconstruction: reprojection error (px), % scene coverage, pose-graph drift.
- Matching ablation: precision/recall of correspondences and final pose accuracy, deep features vs classical, broken out by texture/baseline difficulty.
- Metric accuracy: RMSE and bias of measured displacement vs rig ground truth, reported as a function of true displacement magnitude.
- Change detection: precision/recall/F1 of escalate-vs-log against engineer-adjudicated field labels; false-escalation rate (human workload cost); missed-deviation rate (safety-critical, asymmetric cost, target ≈0 on the rig data).
- Active-perception value: agent-guided vs. fixed-path unguided capture — coverage achieved per unit capture time, number of guided re-captures per session, final reconstruction quality delta.
- COOL: the §6 latency/throughput/cost matrix plus the accuracy-invariance control.
- Developer agent: count and effect of autonomous deployment reconfigurations (cost/latency before vs. after each one).

**Baselines:** classical SIFT/ORB + brute-force matching (same geometric backend) as the pre-OpenCV-5 feature baseline; fixed-pattern unguided capture as the active-perception baseline; stock pip OpenCV 5 per Graviton generation as the COOL baseline; a naive 2D frame-differencing/anomaly-classifier baseline to demonstrate concretely what a 2D-only approach misses on out-of-plane deformation cases in the field dataset.

**Failure taxonomy (reported, not hidden):**
1. Textureless/repetitive surfaces (bare concrete, tile) — classical features fail outright; deep features partially recover but coverage stays sparse; mitigation is an operator prompt to add raking light or temporary texture targets, not a silent gap.
2. Dynamic occluders between visits (vegetation growth, parked vehicles) — cause spurious diff signal; DNN masking reduces but does not eliminate this; residual false-positive rate is measured and reported, not asserted away.
3. Weather/lighting delta between visits (wet specular surfaces) — inflates the diff noise floor; mitigated operationally by a defined capture-window policy, documented as a constraint rather than solved.
4. Marker occlusion/loss (vandalism, debris, snow) — breaks metric scale; the twin explicitly falls back to relative-scale-only and is flagged "unscaled" rather than silently reporting a wrong number — a deliberate fail-safe.
5. Degenerate geometry on near-planar facades with no corner features — registration ambiguity along the plane's tangent; failure rate measured on the adversarial set, mitigated by requiring at least one non-planar/marker feature in view.
6. Guidance-loop latency on poor connectivity — live AR guidance degrades gracefully to post-hoc batch guidance rather than failing.
7. COOL trial/billing edge cases (auto-conversion risk) — an operational failure mode, mitigated by the deliberate trial-timing and cancellation automation in §6, documented as a known process risk rather than assumed away.

## 9. Demo and video plan

**Public endpoint:** the ARGUS dashboard (CloudFront + S3/Amplify, backed by the always-on free-tier `t4g.small`) runs in a read-only demo mode over a pre-loaded sample site with real captured data — twin viewer with the diff heatmap, live ticket queue, and a COOL-benchmark panel showing the cross-generation results table from §6. Kept alive through judging (Nov 9) via AWS Free Plan headroom, budget-alarm backstops, and grant credits if awarded.

**Video (≤5 min):**
- 0:00–0:15 — team on camera, one-line pitch.
- 0:15–1:45 — live capture on a real structure: phone screen showing the AR re-scan guidance arrow firing in response to a real coverage gap (the Loop A trace from §5, actually happening on camera, not simulated).
- 1:45–2:30 — dashboard: twin viewer, the diff heatmap for Wall B, the ticket it generated, the human approval gate.
- 2:30–3:00 — architecture diagram walkthrough (§7), narrated.
- 3:00–3:40 — COOL results: the cross-generation chart, the accuracy-invariance control shown explicitly (same numbers, different speed), and the developer-agent trace rewriting the ECS task definition.
- 3:40–4:20 — one failure case shown honestly (the vegetation false-positive or a marker-occlusion fallback), because the mandatory evaluation evidence has to actually be evidence.
- 4:20–5:00 — impact statement, public endpoint URL, close.

## 10. Team

- **PhD computer-vision researcher (lead):** owns the reconstruction pipeline (features/calib/ptcloud/surface_matching/stereo), the deep-vs-classical ablation methodology, and the repeatability-rig design and analysis.
- **Senior AWS solutions architect:** owns the Step Functions/ECS/Lambda/API Gateway architecture, the AgentCore/MCP developer-agent hosting, the zero-spend COOL execution plan (trial timing, budget alarms), and CloudWatch observability.
- **Full-time ML engineer:** owns the agent policy code for both loops (coverage-gap policy, escalation policy, deployment-tuning policy), the DNN occluder-segmentation model, and the MCP tool implementations.
- **Designer:** owns the ARGUS Scout capture app (AR guidance overlay), the twin-viewer and ticket-queue dashboard, and the video edit.
- **Technical writer:** owns the technical report, the reproducibility packaging (pinned deps, build/deploy/test instructions, architecture diagram), the evaluation write-up including the failure taxonomy, and the video script.
