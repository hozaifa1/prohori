# OpenCV AI Competition 2026 — Verified Fact Dossier
(All facts pulled from opencv.org/opencv-ai-competition-2026, opencv26.devpost.com, AWS Marketplace, AWS Physical AI blog on 2026-08-28. Treat as ground truth.)

## Objective (non-negotiable)
Maximize prize money. Rules allow **ONE Overall Award + BOTH Special Awards**.
Ceiling = $5,000 (Grand) + $1,000 (Best Use of COOL) + $1,000 (Agentic Vision) = **$7,000**.
Any candidate idea that cannot credibly contend for all three is inferior by construction.

## Timeline
- Build phase: **2026-08-26 -> 2026-10-26 23:59 PT** (final submission). ~59 days remain from Aug 28.
- Grant proposal: rolling review, form still LIVE (jotform.com/form/262145877145059). Notices began Aug 25.
- Grant recipients: mandatory 30-min Zoom check-in Sep 21 - Oct 2 for 2nd half of credits.
- Judging Oct 27 - Nov 9. Winners Nov 10 on OpenCV Live!.
- 761 registered participants. Teams 1-5. Hozaifa is solo.

## Hard requirements (all entries)
1. **OpenCV 5** used for substantive image or video analysis.
2. A **meaningful component running on AWS**.
3. Final package: technical report; judge-accessible code repo; pinned deps + build/deploy/test instructions; architecture diagram; **working public web endpoint OR arranged live screen-share**; **<=5-min video showing the team, the app working, architecture, principal results**; evaluation evidence incl. failure cases & limitations.

## Overall rubric (100 pts)
| Criterion | Weight |
|---|---|
| Technical execution (OpenCV 5 correctness/depth) | 30 |
| Innovation | 20 |
| Real-world impact | 20 |
| User experience | 10 |
| Documentation | 10 |
| Responsible cloud delivery (repeatability, observability, security, responsible use) | 10 |

Ties -> Technical Execution, then Real-World Impact. At least 2 independent judge scores, averaged.

## Best Use of COOL rubric
| Criterion | Weight |
|---|---|
| Verified COOL on Graviton | 30 |
| Architecture & technical quality | 25 |
| Measured performance / value | 20 |
| Innovation | 15 |
| Reproducibility | 10 |

Qualifying bar: **COOL must execute the claimed CORE workload on AWS Graviton** (or the Arm leg of a documented hybrid). Must supply COOL version + instance/deployment config, reproducible eval method + inputs + baselines + results, and evidence COOL actually ran the core workload. Valid measurement axes: latency, throughput, utilization, **cost**, or **developer productivity**.

## Agentic Vision rubric
| Criterion | Weight |
|---|---|
| Substantive OpenCV 5 + agent | 30 |
| Orchestration & autonomy | 25 |
| Task effectiveness | 20 |
| Failure handling & human control | 15 |
| User experience | 10 |

Qualifying bar: image/video results must **change a subsequent plan, tool call, action, or human-approval request**. A chatbot explaining a fixed vision result does NOT qualify. Must supply an agent workflow diagram (perception -> decision/orchestration -> action), a **trace showing OpenCV 5 output altering a later decision/tool call/action**, and evaluation of task success, failure handling, observability, human control.
Explicit carve-out: *"Using an AI coding assistant to write the entry does not itself qualify as Agentic Vision."*
Explicit inclusion: a **developer-agent workflow qualifies** when it "iteratively invokes, evaluates, and adjusts an OpenCV 5 workload, with COOL where applicable — for example by using visual test outputs or runtime measurements to change a later tool call, configuration, or deployment — and culminates in a running image or video workload."

## Organizer-favoured project areas (verbatim from the site)
1. Active perception — autonomous inspection with agentic orchestration or MCP
2. Video prediction — physics-informed prediction for process control
3. Visual SLAM — multi-agent SLAM with distributed context
4. Spatial digital twins — real-time twins of physical environments
5. COOL pipelines — server / serverless / container / hybrid x86-Arm
6. Developer agents — integrate COOL with Codex, Claude Code, Kiro, or MCP systems

Domains welcomed: healthcare, safety, accessibility, agriculture, environmental monitoring, smart cities, education, retail, sports analytics.
Framing: "Physical AI and Generative AI systems in which visual understanding drives useful decisions, actions, predictions, or interactions."

## Grant proposal contents required (PDF upload)
team name; problem statement + intended real-world impact; planned OpenCV 5 image/video analysis; planned AWS architecture & services; high-level architecture diagram or technical description; target users/beneficiaries; proposed evaluation method + judge demonstration; declared path (COOL / Agentic / both / neither); team bio incl. hackathon & competition history.
Grant selection weights: OpenCV 5 & core image/video fit 20 / Technical & AWS feasibility 20 / Innovation 20 / Real-world impact 20 / Team strength 10 / Evaluation & demo plan 10.

## COOL (Cloud-Optimized OpenCV Library) — verified technical facts
- AWS Marketplace AMI sold by OpenCV. Ubuntu 24.04 LTS, 64-bit Arm. Latest version **"Cloud Optimized OpenCV 3.1", built on OpenCV 5.0.0**.
- Built with **Arm KleidiCV** + OpenCV-core hand tuning + parallelization tuning.
- Benchmarked over **78 imgproc/core/I-O functions vs the default OpenCV 5.0.0 build**. Avg ~20% faster; up to ~1.8x (some fns ~70% faster); core modules >1.2x. AWS blog end-to-end image workflow: 1.2 fps (pip OpenCV) -> 1.6 fps (COOL) = ~30%.
- Separate Marketplace listings exist per Graviton generation (Graviton 2 / 3 / 4). The Graviton4 listing targets **c8g, m8g, r8g** families.
- Install layout: libs at `/opt/cool`; prebuilt venvs `/opt/cool/venvs/python_3.10|3.11|3.12`; C++ SDK at `/opt/cool/cpp_sdk/lib`. Activate with `source /opt/cool/venvs/python_3.12/bin/activate`.
- Pricing: **7-day free trial**, then hourly software fee on top of EC2. Cheapest observed: **c8g.large / c8g.xlarge = $0.01/hr**, c8g.2xlarge $0.02, c8g.4xlarge & m8g.4xlarge $0.04. Trial auto-converts to paid unless cancelled.
- Roadmap: more CPU archs, GPU backends, serverless integration.

## Cost / zero-spend facts (hard constraint: Hozaifa spends $0 of his own money)
- **t4g.small (Graviton2) — 750 free hours/month for ALL AWS accounts through 2026-12-31.** A free 24/7 Arm box for the whole build window.
- AWS Lambda arm64 (Graviton2): 1M requests + 400,000 GB-s/month, permanently free.
- New AWS Free Plan account: up to **$100 credits + up to $100 more via activities**.
- Grant if awarded: **$150** (50% up front, 50% after the Zoom check-in).
- RISK TO VERIFY: AWS Marketplace software fees are frequently NOT payable with AWS promotional credits. Mitigation levers: the 7-day free trial; the $0.01/hr tier; time-boxed benchmark bursts rather than always-on.

## OpenCV 5.0 — what "technical depth" looks like (released June 2026)
- **Rewritten DNN engine**: ~80%+ ONNX operator coverage (vs ~22% in 4.x); built-in **LLM/VLM support**.
- **HAL redesign on Universal Intrinsics 2.0**: one vector codebase mapping to SSE, AVX2/512, **NEON, SVE**, RVV. Tuned paths for Intel IPP, **Arm KleidiCV**, Qualcomm FastCV, RISC-V RVV.
- New deep local features: **ALIKED, DISK**, plus the **LightGlue** matcher.
- Improved 3D vision module; new core dtypes; real N-dimensional + scalar support; better Python bindings.

## Automation surface (Hozaifa wants maximum autonomy via CLI/MCP)
- AWS CLI v2, CloudFormation / CDK, SAM.
- `awslabs/mcp` — official open-source AWS MCP servers, incl. **amazon-bedrock-agentcore-mcp-server** (122 tools across 7 primitives), usable from Claude Code.
- Amazon Bedrock AgentCore Runtime can host MCP servers (stateful since Mar 2026).
- EC2 Instance Connect / SSM Session Manager for headless shell into the Graviton box.

## Judges
Gary Bradski (OpenCV founder, co-author of *Learning OpenCV*, ex-Intel / Willow Garage / Industrial Perception; deep classical-CV plus robotics taste), Phil Nelson (Director of Content & Creative, OpenCV). AWS may nominate up to 2 more.

## Builder profile (for team-strength scoring and feasibility)
Hozaifa — final-semester EEE, University of Dhaka. Solo entrant. Strengths: semiconductor device physics, TCAD/Sentaurus, GAA-FeFET + HZO thesis, neuromorphic computing / spiking neural networks, MIT-BIH ECG signal work, prior hackathon record (incl. an IEEE TCAD hackathon). Based in Dhaka, Bangladesh (Asia/Dhaka). No robot hardware, no fab access, no GPU cluster, no funds. Has Claude Code available for heavy autonomous implementation.
