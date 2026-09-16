# CONFLUENCE — Multi-Agent Visual SLAM for a Disaster-Response Spatial Digital Twin

## 1. NAME AND ONE-LINE PITCH

**CONFLUENCE**: independent visual-SLAM "responder" agents (replayed benchmark sequences and self-recorded phone walkthroughs) each map a space and stream their local map into a shared cloud context; an orchestrator agent uses OpenCV 5's deep local-feature matcher to detect when two responders have covered the same ground, merges their maps into one live spatial digital twin, redirects the next responder toward unmapped territory, and gates any uncertain merge behind a human-approval step — so the operational map a flood-response team sees is built, corrected, and re-tasked by vision in real time, not assembled by hand afterward.

## 2. PROBLEM, USERS, AND WHY IT MATTERS

Bangladesh's 2024 cyclone-and-monsoon-flood season affected **18.3 million people**, left **2.7 million in need of assistance**, damaged **334,434 houses** (26,991 destroyed), and hit 11 districts / 73 upazilas / 528 unions — with **5.8 million people affected** in the worst-hit zone alone (Noakhali, Cumilla, Laxmipur, Feni, Chattogram, Moulvibazar, Rangamati, Khagrachari) (UN OCHA/HCTT Humanitarian Response Plan for Cyclone and Monsoon Floods, Jun 2024–Mar 2025, reliefweb.int/report/bangladesh/bangladesh-cyclone-and-monsoon-floods-humanitarian-response-plan-june-march-2025; UNICEF Bangladesh Situation Report No. 3, reliefweb.int/report/bangladesh/unicef-bangladesh-situation-report-no-3-cyclone-remal-and-floods-11-september-2024). This is Hozaifa's own country and region (Dhaka, Asia/Dhaka), not a borrowed cause.

In these responses, multiple independent teams — a volunteer with a phone, an NGO surveyor, a second wave of responders the next day — each walk or wade through partially-overlapping ground, and today each produces an isolated trail of photos/video with no shared, geometrically consistent map. The operational picture is stitched together by hand, hours later, in a spreadsheet or a WhatsApp thread. The result is duplicated coverage (two teams re-clear the same street) and blind spots (no team ever reaches a cut-off block) — a coordination failure, not a sensing failure: each team *does* capture usable video, but nothing merges it into one map while it is still actionable.

**Users**: local disaster-response coordinators (Cyclone Preparedness Programme volunteers, NGO field teams, university volunteer corps that mobilize during Dhaka-area flooding) who need a live, shared, drift-corrected map of which areas have been visually surveyed, without radios, GPS-denied indoor/urban-canyon conditions, or any hardware beyond phones already in responders' pockets.

**Why it matters beyond the demo**: the same distributed-context SLAM problem — many independent agents, each running local visual odometry, whose maps must be merged online with automatic loop-closure detection and human-verified uncertain merges — is the identical technical core used in real multi-robot search-and-rescue research (e.g., MIT-SPARK's Kimera-Multi, github.com/MIT-SPARK/Kimera-Multi, which frames itself explicitly for GPS-denied multi-robot SAR). CONFLUENCE is a phone-only, $0 instantiation of that research area, not a toy.

## 3. WHAT THE SYSTEM DOES (one real run, end to end)

**Setup.** Hozaifa walks three overlapping routes through a real building on his campus (e.g., an academic block with two entrances and a connecting corridor) with his phone camera, on three separate occasions, framed in the demo as three responders surveying a flood-cut building on different days. Each walk is uploaded as one "agent" job. In parallel, the same pipeline is validated on EuRoC MAV, TUM-VI, and Newer College sequences (Section 8) for quantitative, ground-truthed numbers — the phone walk is the *demonstrable real-world instance*, the benchmark sequences are the *evaluated instance*.

**Run.**
1. **Agent 1's job** starts first: the front end undistorts frames, runs OpenCV 5's ALIKED detector, tracks keyframes with LightGlue, recovers relative pose via `findEssentialMat`/`recoverPose`, and produces a local trajectory + a keyframe descriptor store, written to S3 under `agents/1/`.
2. **Agent 2's job** starts next (route 2, different entrance, partially overlapping corridor). As each of its keyframes lands, the orchestrator queries it against Agent 1's descriptor store using the LightGlue matcher. At keyframe 47, Agent 2 gets a match: 61 correspondences against Agent 1's keyframe 112, mean LightGlue confidence 0.79, reprojection error after `solvePnPRansac` = 1.4 px.
3. **This vision result changes what happens next** (the agentic loop, detailed in Section 5): the orchestrator (a) submits a GTSAM pose-graph optimization job that fuses Agent 1's and Agent 2's local graphs into one shared graph — the corridor the two responders both passed through is now one geometrically consistent piece of map, not two disjoint trails; (b) recomputes a coverage/frontier map from the merged graph and finds the east wing is still unmapped; (c) when Agent 3's job is dispatched, it is pointed at the east-wing sequence rather than re-walking the already-covered corridor.
4. **A second match**, later in Agent 3's run, comes back weaker: 9 correspondences, confidence 0.34, against a keyframe that geometrically implies an 11-meter jump — below the accept threshold and geometrically implausible (classic perceptual-aliasing failure, e.g., two visually similar stairwells). The orchestrator does **not** auto-merge; it flags the candidate loop closure and opens a human-approval request in the web UI ("Agent 3 keyframe 203 ↔ Agent 1 keyframe 88 — confidence 0.34, implied jump 11.0 m — approve merge?"). The demo shows Hozaifa rejecting it live; the map stays split at that seam instead of being silently corrupted.
5. The web endpoint shows the live merged map (three colored trajectories converging into one point cloud / pose graph), the coverage frontier, and a scrolling decision log of every merge, rejection, and re-tasking event with the vision numbers that drove it.

**Output**: one shared, versioned digital-twin map (S3-stored PLY/JSON pose graph) that a coordinator could actually use to say "these two blocks are surveyed, send the next team east" — the thing that does not exist today.

## 4. OPENCV 5 DEPTH

- **`cv.ALIKED` / `cv.DISK` (Features module, new in 5.0)** — deep local keypoint detector/descriptors, called as `cv.ALIKED_create()` / `cv.DISK_create()` from Python (OpenCV 5.0 keeps all new algorithms reachable as `cv2.<funcname>()`, per the official OE-5 wiki and OpenCV's own 5.0 announcement, github.com/opencv/opencv/wiki/OpenCV-5; opencv.org/opencv-5). Necessary, not decorative: classical ORB/SIFT front ends fail exactly on the two conditions this application must survive — flood-lit low-texture corridors and cross-day illumination change between responder visits (different times of day, different lighting) — which is precisely the wide-baseline, low-texture regime ALIKED and DISK were built for. This is directly ablation-tested in Section 8 (ALIKED+LightGlue vs. ORB+BFMatcher), not asserted.
- **`cv.LightGlueMatcher` (Features module, new in 5.0)** — attention-based matcher producing confidence-scored correspondences, used twice: (a) intra-agent consecutive-frame tracking for visual odometry, (b) inter-agent keyframe-to-keyframe matching that *is* the loop-closure/merge detector in Section 3. The confidence score it returns is the number that gates the human-approval branch — it is load-bearing for the agentic loop, not a cosmetic swap-in for `BFMatcher`.
- **`cv::d3` 3D/Geometry module — ICP and TSDF (new in 5.0)** — used for local point-cloud registration/refinement between overlapping keyframe neighborhoods once a coarse pose from PnP is available, and for point-cloud export (`.ply`) of the merged map for the digital-twin viewer. OpenCV's own OE-33 wiki documents this as new, and separately documents the SfM/pose-graph-optimization side of the 3D module as still requiring "reimplementation from scratch" from the outdated legacy `libmv`-based module (github.com/opencv/opencv/wiki/OE-33.-3D-Module) — this is exactly why the global backend uses GTSAM (Section 11, weakness #2), and the report will state that split honestly rather than imply OpenCV alone performs full SLAM.
- **`calib3d` geometry — `findEssentialMat`, `recoverPose`, `solvePnPRansac`, camera calibration** — the classical geometric backbone of every relative-pose and inter-agent-alignment step; still first-class in OpenCV 5 and unavoidable for turning matched keypoints into metric(-up-to-scale) poses.
- **`imgproc`/`core` front end (undistort, CLAHE, pyramid building) under Universal Intrinsics 2.0 / KleidiCV** — this is the actual COOL-accelerated workload (Section 6): it is imgproc/core-dominated, which is precisely the 78-function class COOL was benchmarked against (dossier, AWS blog).
- **DNN module** is *not* used for the SLAM path — kept out deliberately so the technical-execution story stays honest about which module does what, rather than padding with an unrelated classifier.

## 5. THE AGENTIC LOOP

**Perception → decision → orchestration → action**, concretely, from the run in Section 3:

```
[Agent 2, keyframe 47]
  ALIKED detect → LightGlue match vs Agent 1 store
    → 61 correspondences, confidence 0.79, PnP reproj err 1.4px
        │
        ▼
[Orchestrator: decision]
  confidence ≥ 0.6 AND reproj err ≤ 2.0px AND geometry plausible
        │
        ├── YES → ACTION 1: enqueue GTSAM pose-graph fusion job
        │          (Agent1 graph ⊕ Agent2 graph → shared graph, S3 write)
        │
        ├── ACTION 2: recompute frontier/coverage map from shared graph
        │          → east wing = lowest coverage
        │
        └── ACTION 3: Agent 3's next job spec is rewritten:
                   task_queue["agent_3"].target_region = "east_wing"
                   (was previously "corridor_2", now redundant)

[Agent 3, keyframe 203, later]
  LightGlue match vs Agent 1 store
    → 9 correspondences, confidence 0.34, implied jump 11.0 m
        │
        ▼
[Orchestrator: decision]
  confidence < 0.6 → REJECT auto-merge
        │
        └── ACTION 4: open human-approval request in web UI + CloudWatch event
                   (map stays split at this seam until a human decides)
```

**What physically/digitally happens for each action**: Action 1 is a real AWS Step Functions execution invoking a Lambda that runs GTSAM optimization and overwrites the shared-map object in S3 — the artifact every subsequent agent and the live viewer reads. Action 2–3 is a rewritten task specification (a JSON document in DynamoDB/S3) that a later job (Agent 3's) actually reads and obeys before it starts — this is the "vision result changes a subsequent tool call" trace the rubric requires, and it is inspectable: the task spec before and after Agent 2's match is logged and diffable. Action 4 is a real, addressable approval object (URL) a human clicks; the map only advances past that seam if approved. None of these are physical actuators (see Section 11, weakness #3) — they are the digital equivalent explicitly named as qualifying by the rubric text itself: "change a subsequent plan, tool call, action, **or human-approval request**."

**Failure handling & human control**: every auto-merge has a machine-checkable threshold (confidence, reprojection error, geometric plausibility) logged alongside the decision; every rejection is escalated rather than silently dropped or silently applied; a human can also *retroactively* revoke an already-approved merge, which triggers a re-optimization of the graph without that edge — this is tested directly in the failure taxonomy (Section 8).

## 6. COOL / GRAVITON PLAN

**Core workload measured**: the per-agent visual front end — undistortion, CLAHE, ALIKED keypoint detection, LightGlue matching, and PnP/essential-matrix pose recovery — run per-frame, per-agent. This is the workload that must scale as more responder agents come online, so it is the correct thing to accelerate and measure, not a side computation chosen because it's convenient.

**Baseline**: the identical Python pipeline, identical OpenCV 5.0.0 version, identical input sequences, running on **stock pip-installed `opencv-python` on the same Graviton instance type** — isolating the COOL delta from any x86-vs-Arm confound, which is the methodologically correct baseline (the dossier's own note that COOL is benchmarked "vs the default OpenCV 5.0.0 build" on the same hardware class is followed exactly).

**What gets measured**: (1) throughput — frames/sec through the front end; (2) per-frame latency (p50/p95); (3) cost — $ per 1,000 frames processed, computed from measured throughput × the instance's hourly rate (EC2 + COOL software fee); (4) CPU utilization from CloudWatch. All four are on the rubric's explicit valid-axis list (latency, throughput, cost, utilization/productivity).

**Instances**: control-plane/orchestrator and the always-on public endpoint run on **t4g.small (Graviton2)**, inside the 750 free-hours/month tier available through 2026-12-31 (dossier) — this keeps the demo alive at genuine $0 for the full 59 days. Benchmark bursts run on **c8g.large (Graviton4) with the COOL AMI**, at the observed **$0.01/hr** cheapest tier, time-boxed to a handful of hours across the project (well inside AWS free-tier promotional credits) specifically to avoid the flagged risk that Marketplace software fees are often not payable with promotional credits — the mitigation is running COOL only in short, deliberately scheduled windows rather than always-on, and using the 7-day free trial to cover the first full benchmark pass.

## 7. AWS ARCHITECTURE

- **EC2 t4g.small (Graviton2, free-tier)** — always-on orchestrator process + FastAPI web endpoint serving the live digital-twin viewer (the judge-facing public URL).
- **EC2 c8g.large (Graviton4, COOL AMI, time-boxed paid burst)** — runs the per-agent visual front end during benchmark and demo-processing windows.
- **AWS Lambda (arm64, Graviton2, perpetually free tier)** — stateless steps: descriptor-store queries, threshold checks, task-spec rewrites.
- **AWS Step Functions** — the state machine that sequences "agent job → front end → inter-agent match check → merge-or-escalate → coverage recompute → next task assignment," giving the whole loop an auditable execution history for free (within the free-tier state-transition allowance).
- **Amazon S3** — raw sequences, per-agent local maps (keyframes/descriptors/poses), the shared merged map (PLY + pose-graph JSON), all versioned.
- **DynamoDB (free tier)** — task queue / task-spec documents, human-approval request records.
- **Amazon CloudWatch** — logs, latency/throughput/utilization metrics for the COOL benchmark and for runtime observability.
- **SSM Session Manager** — headless shell access to both EC2 boxes; no SSH keys, no open port 22.
- **IAM** — least-privilege roles per Lambda/EC2 role, no long-lived root credentials in code.

**Staying at $0**: t4g.small and Lambda arm64 are free-tier-perpetual; S3/DynamoDB/Step Functions/CloudWatch usage at this scale sits inside their always-free tiers; the only paid line item is the COOL AMI's hourly software fee on c8g.large during short, scheduled benchmark bursts, covered by the AWS Free Plan's up to $100–$200 in credits (dossier) — with the $150 grant, if awarded, as an unneeded buffer rather than a dependency.

## 8. EVALUATION PLAN

**Datasets** (all free, direct-download, standard SLAM benchmarks with ground truth):
- **EuRoC MAV** (ETH Zurich ASL) — Vicon ground-truth trajectories, multiple difficulty levels (MH/V1/V2), used for quantitative single-agent VO accuracy.
- **TUM-VI** (TU Munich CVG) — handheld sequences, ground truth at sequence start/end, used to stress illumination and handheld-motion robustness.
- **Newer College Dataset** (Oxford) — handheld, survey-grade-laser ground truth, multiple revisit sessions of the same environment — directly usable as ground-truthed "different agent, same place" inter-session data for map-merge accuracy, not just single-trajectory accuracy.
- **Self-recorded campus walkthroughs** (Hozaifa's own phone, 3 routes) — the real-world, uncontrolled qualitative case for the demo; explicitly reported as one uncontrolled trial, not pooled into the quantitative claims.

**Metrics**:
- Per-agent trajectory accuracy: Absolute Trajectory Error (ATE) and Relative Pose Error (RPE) vs. ground truth, computed with the standard `evo` toolkit.
- Map-merge accuracy: post-merge ATE at overlap regions vs. ground truth, and loop-closure precision/recall (deliberately including known perceptually-aliased Newer College/TUM-VI segments as adversarial test cases).
- Orchestration value: exploration-redundancy reduction — % of frames spent re-covering already-mapped ground, orchestrator-guided task assignment vs. round-robin/random assignment on the same multi-session data.
- COOL value: throughput/latency/cost deltas per Section 6.

**Baselines / ablations** (each isolates one claimed contribution, so nothing is asserted without a control):
1. Single-agent SLAM, no distributed context — shows the merge step is not decorative.
2. ORB+BFMatcher front end substituted for ALIKED+LightGlue, same pipeline — isolates what OpenCV 5's new features actually buy in accuracy/robustness.
3. Random/round-robin task dispatch instead of frontier-based orchestration — isolates the agentic decision's task-effectiveness value.
4. Stock OpenCV vs. COOL on identical Graviton hardware — isolates the COOL delta (Section 6).

**Failure taxonomy** (each reproduced deliberately and shown in the report/video, not hidden): perceptual-aliasing false loop closures (similar-looking corridors/stairwells); feature starvation on textureless/flooded surfaces; illumination change between agent revisits degrading match confidence; drift accumulation in long, loop-closure-free stretches; GTSAM optimization divergence from a bad initial relative pose; human-approval-gate latency effects on "real-time" framing.

## 9. DEMO AND VIDEO PLAN

**What the judge clicks**: the public FastAPI endpoint loads to a scenario picker — "EuRoC benchmark run" (quantitative, ground-truth trajectory overlay showing measured ATE) or "Dhaka campus walkthrough" (the self-recorded 3-route demo). Selecting the campus scenario plays the three trajectories building and merging live, with the scrolling decision log (Section 3) alongside. The judge can click the flagged low-confidence event and see the actual reject/approve control — a live, clickable human-approval gate, not a screenshot of one. A second tab shows the COOL-vs-stock throughput/latency/cost bar chart pulled live from CloudWatch.

**5-minute video**: (0:00–0:30) Hozaifa on camera, the problem stated with the flood numbers from Section 2 and a Dhaka-specific frame. (0:30–1:30) architecture diagram walkthrough (Section 7) narrated. (1:30–3:00) the live run: phone footage of the actual campus walks intercut with the web viewer building the merged map in real time, ending on the human-approval-gate moment from Section 3 step 4. (3:00–4:00) the evaluation numbers: ATE/RPE table, the ORB-vs-ALIKED ablation bar chart, the COOL throughput chart. (4:00–5:00) one induced failure shown honestly (a false loop-closure candidate correctly rejected), then the architecture/cost/repeatability summary and the repo link.

## 10. 59-DAY SOLO BUILD PLAN

- **Week 1 (Aug 28–Sep 3)**: AWS account + free-tier setup (t4g.small, Lambda arm64 hello-world, SSM access); download EuRoC/TUM-VI/KITTI/Newer College subsets; verify `cv.ALIKED_create`, `cv.DISK_create`, `LightGlueMatcher`, `findEssentialMat`/`recoverPose` all import and run on OpenCV 5.0.0 pip, on both laptop and t4g.small.
- **Week 2 (Sep 4–10)**: single-agent VO pipeline (undistort → ALIKED → LightGlue tracking → essential-matrix pose recovery → keyframe selection); GTSAM local pose-graph smoothing; ATE/RPE validated against ground truth on 2–3 EuRoC sequences via `evo`.
- **Week 3 (Sep 11–17)**: intra-trajectory loop-closure/place-recognition; ICP/TSDF local registration from the 3D module; lock down single-agent numbers — this is the technical spine everything else depends on.
- **Week 4 (Sep 18–24)**: multi-agent harness — S3-backed per-agent descriptor/pose stores; inter-agent keyframe query via LightGlue; first successful cross-agent merge on Newer College's multi-session data.
- **Week 5 (Sep 25–Oct 1)**: orchestrator agent — frontier/coverage computation, task-spec rewriting, human-approval-gate logic; wired as a Step Functions state machine + Lambda. (If the grant is awarded, the mandatory Zoom check-in window, Sep 21–Oct 2, is scheduled around this week.)
- **Week 6 (Oct 2–8)**: COOL AMI deployed on c8g.large; stock-vs-COOL throughput/latency/cost benchmark; ORB-vs-ALIKED and orchestrator-vs-random ablations run and logged.
- **Week 7 (Oct 9–15)**: record the three campus phone walkthroughs; run them through the full pipeline; build the FastAPI live-map viewer and scenario picker (the public endpoint).
- **Week 8 (Oct 16–22)**: failure-taxonomy stress tests (induced aliasing, textureless corridor, lighting change, revoked-approval reoptimization); write technical report, architecture diagram, evaluation writeup; privacy pass on the campus footage (blur bystanders, document consent/location-genericization).
- **Week 9 (Oct 23–26)**: record and edit the 5-minute video, freeze the deployment, pin dependencies, finalize build/deploy/test instructions, submit.

## 11. HONEST WEAKNESSES

**1. The "multi-agent" system is not concurrent, physically-coexisting robots — it's dataset replay plus one person walking the same building three times.** A hostile judge, especially one from a robotics/SLAM lineage, can reasonably call this simulation theater rather than real multi-agent robotics — this is the exact critique the candidate slate itself raised against this family. *Survivable, not erasable*: this is disclosed up front, not hidden; it mirrors what the organizers themselves suggested for solo, hardware-constrained builders ("EuRoC, TUM-VI, KITTI, Newer College replay as agents"); and the genuine research contribution — online distributed-context merging with vision-gated, human-controllable loop closure — is identical whether the "agents" are temporally offset or physically simultaneous. But a team with real synchronized hardware would beat this on visceral credibility, and no amount of framing removes that gap.

**2. OpenCV 5's own 3D/SLAM backend is unfinished, so the pose-graph optimizer that actually makes map-merging work is GTSAM, not OpenCV — undercutting the "OpenCV 5 depth" claim at its hardest technical point.** OpenCV's own OE-33 wiki says the SfM/pose-graph side of the 3D module needs "reimplementation from scratch" from an outdated legacy base. *Survivable*: OpenCV 5 supplies the genuinely new, genuinely hard perception front end the 30%-weighted "technical execution" criterion is about — ALIKED/DISK/LightGlue deep local features, calib3d geometry, 3D-module ICP/TSDF — while GTSAM is a backend solver, the same division of labor used by real systems like ORB-SLAM and Kimera. The report states this split explicitly rather than implying OpenCV alone does full SLAM; the risk is a judge who wanted OpenCV to own 100% of the SLAM stack and marks it down regardless of the honest framing.

**3. There is no physical actuator — the "action" is a re-dispatched cloud job and a human-approval click, not a valve opening or a robot moving**, and the reference bar (FREISA) won partly on the visceral demonstrability of vision directly opening a sprinkler valve. *Survivable on the rulebook's own text*: the 2026 Agentic Vision bar explicitly qualifies a result that changes "a subsequent plan, tool call, action, **or human-approval request**" — this concept produces three of those four literally, not metaphorically, and Failure Handling & Human Control (15% of that rubric) is exactly the axis a physical-only actuator entry doesn't automatically win. *Not fully survivable*: the emotional "wow" of watching a sprinkler open on video is real, and a legible live map with a clickable approval gate is a different, more cerebral kind of demonstrable — it will not out-charm a physical actuator on raw video appeal, and that gap is honestly not closeable under G3 (no hardware).
