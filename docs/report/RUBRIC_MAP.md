# Rubric self-check: where the evidence for each criterion is

For judges and for me. One line per criterion. Paths are relative to the repository root. Gaps are listed at the end; no evidence is invented.

## Overall rubric (100 points)

| Criterion (weight) | Evidence |
|---|---|
| Technical execution (30) | OpenCV 5 pipeline `src/prohori/measure.py`; module and call-site table in `docs/report/REPORT.md` section 3; method in section 4; held-out width results `eval/results/width_eval.md`; gate `eval/results/gate_report.md`; 310 tests in `tests/` (310 passed on 02704a0); pre-registrations `research/AGENT_PREREG.md`, `research/WIDTH_AUTORESEARCH.md`, `research/GATE_NOTES.md`. |
| Innovation (20) | Conformal risk control per crack on a width measurement with two tiers (`gate_report.md`; `research/LITERATURE.md` states no 2024 to 2026 crack-width paper found does this); grey-level width with a toner-corrected truth (`WIDTH_AUTORESEARCH.md` section 3); pre-registered agent ablation; developer-agent loop on COOL (`eval/results/cool_agentloop/`). |
| Real-world impact (20) | Report section 2 (Rana Plaza, ACI 224R-01 thresholds, users); `docs/ENTRY_PROHORI.md`; `research/ADDENDUM.md` (verified ACI table); phone web app `service/static/`; video script opening `docs/video/SCRIPT.md`. |
| User experience (10) | Web app with demo samples, overlay, per-crack tier and interval, instruction text and Agent trace panel (`service/static/`, screenshots in `docs/demo/screens*/`); README "Try it in 30 seconds"; approval page `/api/approve/<token>`. |
| Documentation (10) | `README.md` (requirements table, results, repository map, reproduction commands); technical report `docs/report/REPORT.md` and PDF; figures `docs/figures/`; `docs/TRACE_EXHIBIT.md`; `docs/FAILURE_GALLERY.md`; research notes in `research/`; release bundles with SHA-256 (README). |
| Responsible cloud delivery (10) | Report sections 7 and 11; `infra/up.sh` (budget, private encrypted S3, DynamoDB TTL, KMS SNS, least-privilege role, IMDSv2, encrypted EBS); `infra/observability.sh` (logs, dashboard, `prohori-5xx` alarm); `infra/cool_live.sh`, `push.sh`, `rollback_t4g.sh`; face redaction `src/prohori/redact.py` (fail closed); human approval `src/prohori/escalate.py`; `research/SERVICE_NOTES.md`. |

## Best Use of COOL rubric

| Criterion (weight) | Evidence |
|---|---|
| Verified COOL on Graviton (30) | `eval/results/cool/20261025T002750Z/REPORT.md` section 1 (AMI id, build info, IMDSv2 confirmation) and `c8g.xlarge/evidence/cool_verify.txt`; the live `/health` reports `"opencv":"5.1.0-dev","cool":true,"instance":"c8g.large"`; per-run `*.bench.json` record the `cv2` file under `/opt/cool`; all 85 frames run on c8g.large, xlarge and 2xlarge. |
| Architecture and technical quality (25) | Report section 8; `eval/cool_compat.py`; BBDT workaround in `measure.py`; crash repro `cool/.../bug_connectedcomponents/`; `infra/cool_live.sh` (launch, verify against the old box to 0.005 mm, cutover with automatic rollback); `infra/bootstrap_cool.sh`. |
| Measured performance and value (20) | Speed ladder and invariance (`cool/.../REPORT.md` sections 2 and 3); cost Pareto `cool/.../pareto.png` and `cost_table.csv`; developer-loop before and after and COOL against pip (`cool_agentloop/README.md`): p50 186.6 to 143.1 ms, USD 0.00393 to 0.00342 per 1,000 frames, COOL against pip 0.994x and +7.2 % cost. |
| Innovation (15) | Developer-agent loop with a bit-exact guard on all 85 frames (`cool_agentloop/trace.jsonl`, `docs/figures/dev_agent_loop.png`); the ladder that separates compiler, library version, KleidiCV and COOL's own tuning; the multithreading crash finding. |
| Reproducibility (10) | `research/COOL_NOTES.md` (protocol and commands); raw benchmark JSON committed; `python eval/cool_bench.py compare ...`; `python eval/cool_loop_report.py`; `eval/results/cool/ledger.tsv`; git tags `cool-loop-*`; `infra/cool_session.sh`. |

## Agentic Vision rubric

| Criterion (weight) | Evidence |
|---|---|
| Substantive OpenCV 5 plus agent (30) | The agent's only input is OpenCV-derived numbers (`src/prohori/agent.py`; `docs/figures/agent_workflow.png`); the OpenCV pipeline is in `measure.py`; report sections 3 and 6. |
| Orchestration and autonomy (25) | Seven actions with a forced tool call, derived flags (`failing_checks`, `widen_now_allowed`, `abandon_now_allowed`), retake loop, joint history and escalation (`history.py`, `escalate.py`); workflow figure; developer-agent loop `cool_agentloop/trace.jsonl` (19 records). |
| Task effectiveness (20) | Pre-registered simulator ablation `eval/results/agent_ablation.md` (compound episodes, recovery within 3 actions: 62 % rules, 85 % AI agent, 88 % AI agent with fact-check, 88 % plain-code ceiling; +25.0 points over rules [+12.5, +37.5]; instructions faithful 91 / 54 / 99 %); live trace `docs/TRACE_EXHIBIT.md` (`move_closer` then `accept`, guardrail record included); `docs/FAILURE_GALLERY.md`. |
| Failure handling and human control (15) | Guardrails (action rules, instruction fact-check, one re-ask, template fallback) and rules fallback in `agent.py` (tests in `tests/test_agent.py`, `tests/test_guardrail.py`); human approval page and SNS (`research/SERVICE_NOTES.md` section 3); gallery of cases where the system does and does not refuse; 200-per-day cap. |
| User experience (10) | Instruction text shown beside the overlay, Agent trace panel, policy selector (README "Try it in 30 seconds"); `docs/demo/screens*/`. |

**Agentic qualifying-bar items.** Workflow diagram: `docs/figures/agent_workflow.png`. Trace where OpenCV output changes a later action: `docs/TRACE_EXHIBIT.md` and `docs/exhibits/trace_exhibit.json`. Evaluation of task success, failure handling, observability and human control: `agent_ablation.md`, `FAILURE_GALLERY.md`, trace panel and CloudWatch, approval page. Developer-agent workflow: `docs/figures/dev_agent_loop.png`, `eval/results/cool_agentloop/`.

## Hard requirements

OpenCV 5 for substantive analysis (`measure.py`); AWS component (EC2 on Graviton4, DynamoDB, S3, SNS, Bedrock, CloudWatch); technical report (`docs/report/`); public code repository (README states the Apache-2.0 licence); pinned dependencies and build, deploy and test instructions (README, `service/requirements.txt`); architecture diagram (`docs/figures/architecture.png`); working endpoint (https://184-194-241-186.sslip.io); video of 5 minutes or less (script in `docs/video/SCRIPT.md`; URL to add); evaluation, failure cases, limitations (README, report sections 9 and 10).

## Gaps and risks I noticed

1. **No video yet.** The Devpost field is `VIDEO_URL_TBD`. The video script's numbers need re-checking (see item 9).
2. **Claude Haiku 4.5 was not evaluated.** P2g (Nova Lite + guardrail) is in `agent_ablation.md` and the live box (build b3e9907) runs it as the default policy `llm`. P3 (Haiku 4.5) produced no results because the AWS account has not submitted Anthropic's use-case form. The compound-recovery gain of P2g over P2 (+2.1 points [-10.4, +14.6]) is not detectable, and P2g equals the plain-code ceiling; the 0 % rule violations hold by construction.
3. **PDF.** `docs/report/Prohori_Technical_Report.pdf` is built from `REPORT.md` by `python tools/make_report_pdf.py`; rebuild it after any edit to the report.
4. **No field validation.** One printed panel, one phone, one session; no real concrete crack against a microscope.
5. **Accuracy Target not met.** MAE 0.070 mm against the 0.05 mm target; thin cracks did not improve on real photos; 2.0 and 3.0 mm specimens are under-read by 0.14 to 0.16 mm.
6. **Gate guarantee is empirical.** Risk within alpha in 69 of 100 splits (0.05) and 76 of 100 (0.01); hardest time-contiguous block 6.09 % risk and 27.2 % wrong given passing. The 0.3 mm interval bin covers 86.3 %.
7. **Agent study is a simulator.** One cheap model, about 100 episodes, one annotator; no human rating of instruction text; the live prompt was not measured (its guardrail checks are unit-tested only). Before the guardrail the LLM's instruction text had a wrong number or claim in live traces; the guardrail catches those in the recorded exhibits and raised faithfulness from 54 % to 99 % in the simulator.
8. **COOL is a tie.** No speed win (0.994x) and +7.2 % cost at list price. The build label "COOL 3.1" cannot be proven from the AMI. The AMI name contains "Graviton5" while the instances are Graviton4. The crash bug report was drafted but not sent anywhere.
9. **Video script claims.** The script's agent numbers are simulator results (88 and 62 in 100 on compound episodes, 99 % faithful instructions) and are said as such. Its published-comparison line is context, not a head-to-head (`width_eval.md`; thin-crack ratio 1.10 against 0.89, wide-crack COV 7.0 % against 5.8 %). The "97 of 100 green readings" line is a mean over splits; risk is within alpha in 69 of 100 of them.
10. **Remaining known inconsistencies.**
    - `research/GATE_NOTES.md` section 7 says the 0.3, 1.0 and 2.0 mm interval bins are under 90 %; the current `gate_report.md` gives 86.3 %, 90.2 % and 90.5 % (README was corrected).
    - The README and exhibits use "certified" for cracks that pass at the amber level, while the tier "certified" is the strict level.
    - `eval/results/synth_validation.md`, `krkcmd_report.md` and the numbers in `GATE_NOTES.md` section 7 describe the legacy estimator.
    - The agent study measured the legacy-gate prompt; the live prompt differs.
11. **Security note.** `GET /api/trace/<session>` is unauthenticated, and SSH is open to one /24 of the operator's address. The security group and role are documented; no external review was done.
12. **Instance-hours differ by study.** 2.198 h (COOL benchmark) and 2.66 h (developer loop); anyone quoting a single "COOL spend" figure must add them.
