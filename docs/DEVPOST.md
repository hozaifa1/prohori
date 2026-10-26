# Devpost submission fields (ready to paste)

## Project name
PROHORI (প্রহরী, "sentry")

## Tagline (under 200 characters)
Crack width in millimetres from a phone photo, with a calibrated gate that refuses unreliable readings and an agent that tells you how to retake the photo.

## Inspiration
On 24 April 2013 the Rana Plaza building near Dhaka collapsed and 1,134 people died. Cracks had been reported the day before. Today, crack width on site is still judged by eye or with a plastic comparator card, and a phone measurement that looks confident but is wrong is worse than no measurement. I wanted a tool that gives a number in millimetres, says how far to trust it, and says plainly when it cannot give one.

## What it does
You tape or place a printed ChArUco board next to a crack and take a photo. PROHORI finds the board with OpenCV 5, flattens the wall plane to a known scale, and reads each crack's width in millimetres from the grey levels. A gate calibrated with conformal risk control labels each crack **certified (green)**, **indicative (amber)** or **refused**, with a 90 % interval and reason codes. An agent reads those numbers, never the pixels, and picks one of seven actions: accept, accept with a wider interval, move closer, hold steady, re-light, reposition the board, or stop and log. When a joint widens by more than the measurement uncertainty, or after four failed captures, it e-mails an engineer, and only that engineer's confirmation counts. It does not decide whether a building is safe.

## How we built it
* **Measurement.** `aruco.CharucoDetector`, `findHomography`, `solvePnP`, `warpPerspective`, `remap`, connected components, `distanceTransform`, and a blur-aware grey-level width estimator, all in OpenCV 5. The estimator was tuned by an agent loop under rules written first, with frozen splits and a test split that can only be run once. Truth is a printed panel of eight strokes (0.3 to 3.0 mm), corrected for toner spread (U_ref +-0.009 mm).
* **Gate.** Monotone gradient-boosted trees predict relative error; conformal risk control sets two thresholds on 2,584 degraded captures from 21 source photos. Held-out: 3.2 % of certified (green) readings and 11.5 % of readings passing at green or amber are wrong; 25.8 % and 38.7 % of cracks pass; the 90 % interval covers 91.5 %.
* **Agent.** A fixed-rule policy and an LLM policy on Amazon Bedrock with one forced tool call, guardrails in code, and a fallback to the rules. A pre-registered simulator study compares them.
* **AWS.** One Graviton4 c8g.large instance running the COOL AMI (OpenCV 5.1.0-dev, KleidiCV 0.7.0 HAL) behind Caddy and FastAPI; DynamoDB for traces and joint history; S3 for evidence with faces blurred first; SNS for escalations; CloudWatch for logs, a dashboard and a 5xx alarm; a least-privilege IAM role; idempotent scripts for deploy, push and rollback.
* **COOL.** I measured COOL against the stock pip wheel with a ladder that separates compiler, library version, KleidiCV and COOL's own tuning, then ran a developer-agent loop (Claude Code) that profiled the pipeline on COOL and kept only changes that left every output bit-identical.

<!-- AGENT_RESULTS_PENDING -->
Agent results (update when the guardrail re-run is in): on 100 held-out simulated episodes, the LLM policy (Nova Lite) recovers 85 % of compound-failure captures within three actions against 62 % for the rules and 88 % for a label rule written as plain code; the re-run with a guardrail and Claude Haiku 4.5 is pending. The live default model is Nova Lite until that run is in.
<!-- /AGENT_RESULTS_PENDING -->

## Challenges
* **A truth I could trust.** Toner spreads on paper, so a printed 0.3 mm stroke is wider than 0.3 mm. I measured the spread from the printed board squares, restarted the width tuning after I saw that earlier gains were partly the estimator learning the spread, and kept the test split locked until the end.
* **A small, honest calibration set.** The gate learned from degraded copies of 29 photos of one sheet. I chose its levels on grouped splits and report that the risk is within its target in 69 of 100 of them, not a guarantee for new walls or phones.
* **LLM text that is wrong while the action is right.** In a live trace the agent said "move closer" correctly but quoted a number that contradicted the measurement. I added code checks on the instruction text, which are in the repository and pending in the re-run.
* **COOL on a multithreaded workload.** `connectedComponentsWithStats` aborts the process on COOL at 2 or more OpenCV threads (50 of 50 runs). Routing it to the BBDT algorithm gives identical output and fixes it.
* **Being solo.** One person, one phone, one printed sheet.

## Accomplishments that we're proud of
* Width error of 0.070 mm MAE over 63 cracks on 8 held-out photos, and 0.056 mm on the 41 that pass the gate; the 90 % interval covers 91.5 % of held-out readings.
* A gate that says how often it is wrong, and a report that states where the guarantee does not hold.
* A live endpoint on COOL and Graviton4, with a trace in which a number computed by OpenCV (2.71 px/mm) changes the agent's next action (`move_closer`), and the next photo (7.98 px/mm) passes.
* A developer-agent loop that made the pipeline 23.2 % faster (186.6 to 143.1 ms per frame at 4 threads) and 13.0 % cheaper per 1,000 frames with bit-identical output on 85 frames.
* Every number in the report points to a result file, and the failure cases are published.

## What we learned
* Grey-level profiles beat mask edges for width: even the best crack segmenters agree with labels on the exact centreline pixel only 16.2 % of the time.
* Refusing is a product feature only if you can say how often the accepted answers are wrong, and what that number does not cover.
* An LLM that follows written rules matches those rules in code. In my simulator it did not reason better than a well-tuned rule list.
* COOL is a correct Arm runtime for this workload but not a speed or cost win: it ties the pip wheel (0.994x after optimisation) and costs 7.2 % more at list price, because the OpenCV calls that dominate here are not the ones KleidiCV speeds up. The gains came from profiling and fixing my own code, and apply to both builds.

## What's next
* Measure real concrete cracks against a microscope, with more than one phone and more than one wall.
* Refit the gate on much more data so a group-level risk guarantee becomes possible.
* Re-identify the same crack across visits (the earlier LightGlue plan was not built).
* Report the COOL threading crash upstream (a draft bug report and repro are in the repository).
* A human rating of the agent's instruction text, and the pending agent re-run.

## Built with (tags)
OpenCV 5, ArUco / ChArUco, COOL (Cloud Optimized OpenCV), Arm KleidiCV, AWS Graviton4 (EC2 c8g), Amazon Bedrock, Amazon DynamoDB, Amazon S3, Amazon SNS, Amazon CloudWatch, AWS IAM, Python, FastAPI, NumPy, scikit-learn, Caddy, Progressive Web App, Claude Code

## Award declarations

**Overall Award.** Technical execution: a complete OpenCV 5 measurement pipeline (objdetect, calib3d, imgproc, dnn) with a held-out evaluation (MAE 0.070 mm, 63 cracks), a reference with stated uncertainty, and 309 passing tests. Innovation: conformal risk control applied per crack to a width measurement, so "refuse" comes with a measured wrong-reading rate. Impact: a documented use case in Bangladesh's garment and residential buildings. UX, documentation and cloud: a phone web app with demo samples and an agent trace, a technical report and a failure gallery, and a least-privilege, observable, repeatable AWS deployment with face redaction and human approval.

**Best Use of COOL.** The qualifying bar is that COOL executes the claimed core workload on Graviton. The COOL AMI (OpenCV 5.1.0-dev, KleidiCV 0.7.0 HAL) runs PROHORI's full measurement workload on c8g.large, xlarge and 2xlarge for all 85 test frames and serves the live endpoint; the build, instance and AMI evidence, the baselines (stock pip wheel, a self-built 5.0.0, an upstream snapshot with KleidiCV on and off), the inputs and the raw timings are in the repository. The measured axes are developer productivity and cost: a developer-agent loop cut p50 per frame 23.2 % and cost per 1,000 frames 13.0 % with bit-identical output, and the report states plainly that COOL ties the pip wheel (0.994x) and costs 7.2 % more at list price. The rubric items are covered by an invariance ladder, a found-and-worked-around multithreading crash, a cost Pareto, and reproduction commands.

**Agentic Vision.** The qualifying bar is that image results change a later plan, action or human-approval request. In PROHORI the agent sees only numbers OpenCV computed; in the published trace, 2.71 px/mm and a `low_resolution` reason produce `move_closer`, and the next photo at 7.98 px/mm is accepted. The repository has the workflow diagram (perception, decision, action), guardrails with a rules fallback, a human-approval step for escalations, a failure gallery, and a pre-registered evaluation. A second qualifying workflow is the developer-agent loop that used runtime measurements and bit-exact output checks to decide each next change to an OpenCV workload on COOL. Using an AI assistant to write the entry is not what is claimed.

## Links
* Live endpoint: https://184-194-241-186.sslip.io
* GitHub: https://github.com/hozaifa1/prohori
* Technical report (PDF in the repository): docs/report/Prohori_Technical_Report.pdf (source: docs/report/REPORT.md)
* Rubric map: docs/report/RUBRIC_MAP.md
* Data bundles: https://github.com/hozaifa1/prohori/releases/tag/v1.0-submission
* Video (5 minutes or less): VIDEO_URL_TBD
