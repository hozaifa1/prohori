# Triage-agent ablation: P0 random vs P1 rules vs P2 LLM, and (Addendum B) P2g / P3 with a guardrail

*Generated 2026-10-26 21:07. Simulator study on 100 held-out episodes; see the pre-registration for the design and the limits.*

## Provenance

* Pre-registration `research/AGENT_PREREG.md`, sha256 `6e4f590adc4cc1393aa1e46b9f3d6ccc6fe0db5e6fda205d32646384847fcf16`
* Simulator `src/prohori/episodes.py`, sha256 `b332ec8497cce3f6821bff491476fdbfa8d481f029da617bcc2169da6772edfd`
* P1 source fingerprint (rules code, frozen) `b123678d8ad0dcf3`; P2 final prompt+tool fingerprint `4398a6c6a8e08194`
* Gate thresholds used: corners >= 8, px/mm >= 8.0, blur_var >= 150.0, obliquity <= 45.0 deg, glare <= 0.05
* P2 model `us.amazon.nova-lite-v1:0` (us-east-1, temperature 0), forced tool call, no fallback model. Seeds: test 50000-50099, dev 1000-1199, paired common random numbers.
* **Addendum B** (research/AGENT_PREREG.md, written 2026-10-26 before any P2g/P3 decision; the sha256 of the pre-registration file above includes the addendum, the file before it was `91d0dd26575acb64f8dd826cd7e92635e6ed51ba468912f0b3f6a9dc67d3cac5`): P2g = `us.amazon.nova-lite-v1:0` + guardrail, P3 = `us.anthropic.claude-haiku-4-5-20251001-v1:0` + guardrail, both with prompt v2 of the legacy gate (the prompt P2 used; text in `research/prompts/agent_prompt_v2_legacy_gate.txt`, sha256 `ec55aafa4d3c28bc`), temperature 0, no fallback model, one run each on the same seeds.
* P2g Nova Lite + guardrail: run at git `ef5f0a035f`, prompt+tool fingerprint `4398a6c6a8e08194`, model `us.amazon.nova-lite-v1:0`, 151.0 s
* Confidence intervals: 95% percentile bootstrap over episodes, 10000 resamples, seed 20261019.

## Headline: recovery within 3 actions (share of episodes certified by the 4th capture)

| subset | n | P0 random | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail | P* label rule (ceiling) |
|---|---|---|---|---|---|---|
| single (S) | 20 | 30% [10, 50] | 95% [85, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| compound (X+C2+C3) | 48 | 2% [0, 6] | 62% [48, 75] | 85% [75, 94] | 88% [77, 96] | 88% [77, 96] |
| recoverable (S+X+C2+C3) | 68 | 10% [4, 18] | 72% [62, 82] | 90% [82, 96] | 91% [84, 97] | 91% [84, 97] |

### Pre-registered test: P2 minus P1, recovery@3, paired by episode

| subset | n | P2 - P1 (points) | 95% CI | criterion |
|---|---|---|---|---|
| single (S) | 20 | +5.0 | [+0.0, +15.0] | expected |diff| < 10: holds |
| compound (X+C2+C3) | 48 | +22.9 | [+8.3, +37.5] | point estimate >= +10 but CI includes smaller effects |
| recoverable (S+X+C2+C3) | 68 | +17.6 | [+5.9, +29.4] |  |

Recovery within all 6 actions, compound, P2 - P1: +22.9 points [+8.3, +37.5], n=48.

### Addendum B: guardrail variants, recovery@3, paired by episode (primary bar: point estimate >= +10 vs P1 on the compound subset)

| comparison | subset | n | difference (points) | 95% CI | bar vs P1 |
|---|---|---|---|---|---|
| P2g - P1 | single (S) | 20 | +5.0 | [+0.0, +15.0] |  |
| P2g - P1 | compound (X+C2+C3) | 48 | +25.0 | [+12.5, +37.5] | point estimate >= +10, lower bound >= +10: MET |
| P2g - P1 | recoverable (S+X+C2+C3) | 68 | +19.1 | [+10.3, +27.9] |  |
| P2g - P2 | single (S) | 20 | +0.0 | [+0.0, +0.0] |  |
| P2g - P2 | compound (X+C2+C3) | 48 | +2.1 | [-10.4, +14.6] |  |
| P2g - P2 | recoverable (S+X+C2+C3) | 68 | +1.5 | [-7.4, +10.3] |  |

## All outcome metrics, held-out test split

### Recovery within 6 actions

| subset | P0 random | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail | P* label rule (ceiling) |
|---|---|---|---|---|---|
| single (S) | 35% [15, 55] | 95% [85, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| compound (X+C2+C3) | 10% [2, 19] | 62% [48, 75] | 85% [75, 94] | 88% [77, 96] | 88% [77, 96] |
| recoverable (S+X+C2+C3) | 18% [9, 26] | 72% [62, 82] | 90% [82, 96] | 91% [84, 97] | 91% [84, 97] |
| hopeless (H) | 0% [0, 0] | 0% [0, 0] | 0% [0, 0] | 0% [0, 0] | 0% [0, 0] |
| constrained (M) | 0% [0, 0] | 6% [0, 19] | 6% [0, 19] | 6% [0, 19] | 6% [0, 19] |
| all | 12% [6, 19] | 50% [40, 60] | 62% [52, 71] | 63% [53, 72] | 63% [53, 72] |

### Median actions to certified (episodes that were certified)

| subset | P0 random | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail | P* label rule (ceiling) |
|---|---|---|---|---|---|
| single (S) | 3.0 [1.0, 3.0] | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| compound (X+C2+C3) | 6.0 [3.0, 6.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] |
| recoverable (S+X+C2+C3) | 3.0 [2.0, 5.5] | 2.0 [1.0, 2.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] |
| all | 3.0 [1.0, 5.5] | 2.0 [1.0, 2.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] | 2.0 [2.0, 2.0] |

### Correct terminal outcome (certified / abandoned / widened as the class requires)

| subset | P0 random | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail | P* label rule (ceiling) |
|---|---|---|---|---|---|
| single (S) | 35% [15, 55] | 95% [85, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| compound (X+C2+C3) | 10% [2, 19] | 62% [48, 75] | 85% [75, 94] | 88% [77, 96] | 88% [77, 96] |
| recoverable (S+X+C2+C3) | 18% [9, 26] | 72% [62, 82] | 90% [82, 96] | 91% [84, 97] | 91% [84, 97] |
| hopeless (H) | 56% [31, 81] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| constrained (M) | 50% [25, 75] | 88% [69, 100] | 94% [81, 100] | 94% [81, 100] | 94% [81, 100] |
| all | 29% [20, 38] | 79% [71, 87] | 92% [86, 97] | 93% [88, 98] | 93% [88, 98] |

### Action accuracy at decision points on uncertified captures

| subset | metric | P0 random | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail | P* label rule (ceiling) |
|---|---|---|---|---|---|---|
| single (S) | acceptable (in label set) | 10% [4, 18] | 93% [81, 100] | 96% [89, 100] | 100% [100, 100] | 100% [100, 100] |
| single (S) | strict (primary) | 10% [4, 18] | 93% [81, 100] | 96% [89, 100] | 100% [100, 100] | 100% [100, 100] |
| single (S) | addresses some failure | 12% [5, 22] | 100% [100, 100] | 96% [89, 100] | 100% [100, 100] | 100% [100, 100] |
| compound (X+C2+C3) | acceptable (in label set) | 17% [12, 22] | 69% [61, 78] | 73% [65, 81] | 100% [100, 100] | 100% [100, 100] |
| compound (X+C2+C3) | strict (primary) | 16% [10, 21] | 65% [57, 73] | 70% [62, 78] | 96% [93, 99] | 100% [100, 100] |
| compound (X+C2+C3) | addresses some failure | 25% [19, 31] | 98% [96, 100] | 91% [85, 96] | 100% [100, 100] | 100% [100, 100] |
| recoverable (S+X+C2+C3) | acceptable (in label set) | 15% [11, 19] | 73% [66, 81] | 77% [70, 84] | 100% [100, 100] | 100% [100, 100] |
| recoverable (S+X+C2+C3) | strict (primary) | 14% [10, 19] | 69% [62, 77] | 74% [68, 82] | 97% [94, 99] | 100% [100, 100] |
| recoverable (S+X+C2+C3) | addresses some failure | 21% [16, 26] | 99% [97, 100] | 92% [87, 96] | 100% [100, 100] | 100% [100, 100] |
| all | acceptable (in label set) | 15% [12, 19] | 76% [70, 82] | 81% [76, 85] | 100% [100, 100] | 100% [100, 100] |
| all | strict (primary) | 14% [11, 18] | 73% [67, 79] | 78% [73, 83] | 97% [94, 99] | 100% [100, 100] |
| all | addresses some failure | 21% [17, 25] | 99% [97, 100] | 91% [88, 94] | 100% [100, 100] | 100% [100, 100] |

### Escalation (abandon_and_log)

| metric | P0 random | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail | P* label rule (ceiling) |
|---|---|---|---|---|---|
| precision vs truth (episode was hopeless) | 17% [7, 27] | 47% [30, 64] | 70% [50, 88] | 84% [67, 100] | 84% [67, 100] |
| recall vs truth | 56% [31, 81] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| false abandon of recoverable episodes | 56% [44, 68] | 25% [15, 36] | 10% [4, 18] | 4% [0, 10] | 4% [0, 10] |
| precision vs labelling rule (decision level) | 28% [16, 40] | 91% [80, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| recall vs labelling rule | 15% [9, 24] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |

### Instruction text: automated checklist (NOT the human 1-5 rating, which is pending)

| check | P1 rules | P2 LLM (Nova Lite) | P2g Nova Lite + guardrail |
|---|---|---|---|
| within 140 characters | 100% [100, 100] | 100% [100, 100] | 100% [100, 100] |
| contains a digit (original checklist) | 91% [88, 94] | 57% [49, 64] | 99% [98, 100] |
| wording matches the chosen action | 100% [100, 100] | 100% [99, 100] | 100% [100, 100] |
| **instruction faithfulness**: cites a measured number AND zero validator violations (Addendum B) | 91% [88, 94] | 54% [47, 61] | 99% [98, 100] |
| instructions with a wrong number or a wrong certification claim (validator) | 0% [0, 0] | 3% [1, 5] | 0% [0, 0] |
| instructions that cite no measured number | 9% [6, 12] | 45% [38, 52] | 1% [0, 2] |
| decisions breaking a hard prompt rule (action check, on the output the operator sees) | 24% [18, 30] | 19% [15, 24] | 0% [0, 0] |

### Guardrail activity (share of LLM decisions)

| measure | P2g Nova Lite + guardrail |
|---|---|
| first answer had any violation (action or instruction) | 58% [50, 65] |
| re-asked | 58% [50, 65] |
| fixed by the re-ask | 21% [17, 26] |
| **instruction replaced by the rules template (repaired)** | 36% [29, 42] |
| action rejected, rules policy used | 1% [0, 2] |
| rationale withheld | 60% [54, 66] |

Pre-repair faithfulness was not stored per decision; "first answer had any violation" is the nearest quantity (it includes action violations).

## Secondary: free policies on 1,000 episodes (separate seeds 70000-70999, same generator)

No model calls. Shows how far a fixed if/else cascade is from the label-rule ceiling when the sample is large enough to see small differences.

| subset | metric | P0 random | P1 rules | P* label rule (ceiling) |
|---|---|---|---|---|
| single (S) | recovery@3 | 25% [19, 31] | 94% [90, 96] | 98% [96, 100] |
| single (S) | acceptable accuracy | 13% [10, 16] | 90% [86, 94] | 100% [100, 100] |
| compound (X+C2+C3) | recovery@3 | 8% [6, 11] | 70% [66, 74] | 80% [77, 84] |
| compound (X+C2+C3) | acceptable accuracy | 16% [14, 17] | 75% [73, 78] | 100% [100, 100] |
| recoverable (S+X+C2+C3) | recovery@3 | 13% [11, 16] | 77% [74, 80] | 86% [83, 88] |
| recoverable (S+X+C2+C3) | acceptable accuracy | 15% [14, 17] | 78% [76, 80] | 100% [100, 100] |

P* minus P1, recovery@3, compound, n=480: +10.0 points [+6.5, +13.5].

## Model calls, tokens and cost (all work, including prompt iteration and probes)

Section 8 total: calls **419 of 600** allowed (2 returned an error), input tokens 905,729, output tokens 27,771, cost **$0.0610** at $0.06 / $0.24 per million tokens (Nova Lite; the Claude probe, if it succeeded, is priced at the same rate here and is one call).

| tag | calls | input tokens | output tokens | errors | USD |
|---|---|---|---|---|---|
| probe_claude | 2 | 0 | 0 | 2 | 0.0000 |
| smoke | 1 | 1,593 | 64 | 0 | 0.0001 |
| dev_v0 | 56 | 99,322 | 3,793 | 0 | 0.0069 |
| dev_v1 | 49 | 104,364 | 3,278 | 0 | 0.0070 |
| dev_v2 | 50 | 113,704 | 3,376 | 0 | 0.0076 |
| test_final | 261 | 586,746 | 17,260 | 0 | 0.0393 |

P2 fallbacks to the rules policy on the test split: **0 of 261 decisions**.

### Addendum B: calls, tokens, cost and latency

Addendum B total: **519 of 1500** calls allowed, **$0.0719 of $5.00** allowed (Nova Lite $0.06 / $0.24, Claude Haiku 4.5 $1.00 / $5.00 per million input / output tokens). The section 8 total above is unchanged.

| run | model | calls | input tokens | output tokens | errors | USD | call latency p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| p3_devfmt | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 50 | 0 | 0 | 50 | 0.0000 | 0 / 0 |
| p2g_devfmt | `us.amazon.nova-lite-v1:0` | 75 | 173,529 | 5,344 | 0 | 0.0117 | 1051 / 2176 |
| p2g | `us.amazon.nova-lite-v1:0` | 394 | 898,373 | 26,083 | 0 | 0.0602 | 1039 / 1411 |

P2g Nova Lite + guardrail: 392 model calls for 250 decisions, 2 fallbacks to the rules policy (guardrail rejections among them: 2).

## Dev split (free policies, 200 episodes)

| subset | P0 random | P1 rules | P* label rule (ceiling) |
|---|---|---|---|
| recovery@3, single (S) | 17% [3, 30] | 97% [90, 100] | 100% [100, 100] |
| recovery@3, compound (X+C2+C3) | 7% [3, 13] | 62% [53, 71] | 77% [69, 85] |
| recovery@3, recoverable (S+X+C2+C3) | 9% [5, 14] | 69% [61, 76] | 82% [76, 89] |

## Reading these results: original run, P0/P1/P2 (written after those results were seen on 2026-10-19; not part of the pre-registration)

**Verdict on the pre-registered criterion.** On the compound subset P2 beat P1 by +22.9 points of recovery within 3 actions (95% CI +8.3 to +37.5, n = 48 episodes). The point estimate clears the +10 bar; the lower end of the interval does not, so at the stated precision the bar is not demonstrated. On single-cause failures the difference is +5.0 [0, +15], inside the pre-registered "|diff| < 10" expectation, though the interval touches its limit.

**Why P2 won, and why that is weaker than it looks.**
1. P2's final prompt was written with the dev traces in front of us. It contains explicit ordering rules (tilt before everything else, glare first only when it is hiding the board, a try-reposition-then-relight chain when the board is lost) and deterministic helper numbers (`failing_checks`, `widen_now_allowed`, `abandon_now_allowed`). These match the labelling rule, which was written from the same reasoning as the simulator. P1 received no tuning (frozen by pre-registration).
2. P*, the label rule written as plain code, reaches 88% on compound (P2: 85%, intervals overlap almost entirely). The secondary 1,000-episode run puts P* above P1 by +10.0 points [+6.5, +13.5] on compound episodes. **So the P2 gain over P1 is about what a tuned if/else cascade also gets. This run does not show that an LLM reasons better than a well-tuned rule set; it shows that an LLM following a written rule set recovers about as well as that rule set in code, and better than the shipped P1.** Nova Lite does not reach the ceiling by following the rules faithfully: its action matches the label set 73% of the time on compound states (P* 100%, P1 69%), and it often fixes blur before tilt.
3. P1 loses mostly by giving up too often: it abandons 33% of compound episodes (P2 15%, P*  6%) because its fixed priority order spends attempts in the wrong order, and the product rule abandons on the fourth failed capture. Wrong order costs attempts only when the simulator's coupling bites (a reposition re-rolls glare and shake half the time). That coupling is our assumption.
4. P2 never chose `accept_with_widened_uncertainty` on a recoverable episode (0%) although the helper flag allowed it. It kept retrying, which in this simulator usually works. This helps its recovery number and departs from the written rule. It did choose it correctly on 15 of 16 constrained episodes.

**What matched the pre-registered expectation.** P0 is far below everything (sanity check passed). P1 and P2 both catch every hopeless episode (escalation recall 100% against truth); P1's escalation precision against truth is only 47% because it also abandons a quarter of the recoverable episodes.

**Weaknesses of P2 visible here.** Only 57% of its instructions cite a number from the observation (P1: 91%), against its own prompt's instruction. The instruction checklist is automated; the human 1 to 5 rating is not done. Earlier prompt versions showed Nova Lite miscounting attempts and misreading thresholds (calling a blur_var of 313 blurry), which is why the helper fields exist.

**Prompt iteration on the dev-LLM set (20 episodes, 14 recoverable, the same episodes reused for every version; selection rule from the pre-registration).**

| version | change | recovery@3 recoverable | recovery@3 compound | action accuracy (in label set) | calls |
|---|---|---|---|---|---|
| v0 | prompt as in the repository before this work | 79% | 73% | 57% | 56 |
| v1 | observation semantics (zeros mean "not measured" when the board is lost), derived `failing_checks`, abandon/widen precedence | 71% | 64% | 65% | 49 |
| v2 | ordering rules, lost-board chain, `widen_now_allowed` / `abandon_now_allowed` flags | **100%** | **100%** | 82% | 50 |
| reference on the same 20 episodes | P1 / P* | 64% / 79% | 55% / 73% | 84% / 100% | free |

v2 was selected and run once on the held-out split. Dev results are noisy at n = 20, and the 100% is almost certainly optimistic (held-out compound: 85%).

**Other limits.** About 100 held-out episodes, one cheap model, one annotator, a simulator whose glare, severe tilt and low-resolution distributions are assumptions (the real panel has none of them), and a perfectly cooperative operator model. `recovery@6` equals `recovery@3` for P1, P2 and P* because all three abandon at the fourth failed capture. The simulator takes the gate thresholds from `agent.GATE_THRESHOLDS` (the hand-set values); a refit gate will change the numbers. P2 ran on Nova Lite, not the production default model in `agent.py`. A usable-result metric (`usable@3_posthoc`, certified or widened within 3 actions) is in the CSV; it was added after seeing the results and is not part of the pre-registration.


## Reading the Addendum B results, P2g and P3 (written after seeing them, 2026-10-26; not part of the pre-registration)

**P3 (Claude Haiku 4.5) was not run.** Bedrock refused every call with `ResourceNotFoundException: Model use case details have not been submitted for this account`, for the `us.` and the `global.` Haiku 4.5 profiles. That is an Anthropic form that only the account owner can submit. The 50 dev-format decisions all fell back to the rules policy (ledger tag `p3_devfmt`, 0 USD). So the pre-registered live-default rule ("P3 meets or beats P2 and has higher faithfulness") cannot be met, and the live model stays Nova Lite. Nothing below says anything about Claude models.

**P2g (Nova Lite + guardrail), compound subset, recovery within 3 actions.** 88% [77, 96], against 85% for P2 and 62% for P1. P2g - P1 is +25.0 points [+12.5, +37.5], so for the first time the lower end of the interval clears the +10 bar. P2g - P2 is +2.1 [-10.4, +14.6]: no detectable difference between the guarded and the unguarded model, as the pre-registered expectation (within 8 points) said. Single-cause episodes are unchanged (100%).

**What the guardrail did.**
1. Instruction faithfulness went from 54% [47, 61] (P2) to 99% [98, 100] (P2g); P1 is 91%. Most of P2's gap was text that cited no measured number (45% of its instructions), not wrong numbers (3% had a wrong number or claim). The wrong-number check caught few errors on this simulator because Nova's legacy-prompt text rarely mis-states a value; the review's errors came from the live CRC-gate prompt, which this study does not measure.
2. Decisions that break a hard prompt rule fell from 19% (P2) to 0%. The frozen P1 breaks them in 24% of decisions.
3. The first answer had a violation in 58% of decisions. A re-ask fixed 21% of all decisions; 36% still had a violation and got the rules template wording instead (the model's action was kept); 1% (2 decisions) had an action that stayed invalid and went to the rules policy. Nova Lite's own wording is therefore the operator's text in only about two thirds of decisions.
4. Cost: 392 model calls for 250 decisions (1.6 per decision), US$0.06 for the test run, call latency p50 about 1.0 s, p95 1.4 s; a re-asked decision takes two such calls in sequence.

**Why the recovery gain over P2 is small and what it means.** The action check is the prompt's own rule set, which is also what the label policy P* encodes. With it enforced, P2g's action matches the label set in 100% of decisions on uncertified captures and the primary label action in 97% (P2: 81% / 78%), and its recovery equals P* (88% compound). That is expected, not a discovery: the guardrail turns "LLM following the written rules" into "LLM whose answer is overridden by the written rules whenever it deviates". Nova Lite's contribution is the wording of the instruction (under a validator) and a policy that can still choose among the actions the rules allow; this study cannot show it reasons better than P*. False abandon of recoverable episodes dropped to 4% (P2 10%, P1 25%).

**Limits added by Addendum B.** The study measures the legacy-gate prompt on the simulator; the live service uses the CRC-gate prompt, whose guardrail checks are covered by unit tests only. The validator and P* share their source (the prompt's rules), so 0% rule violations for P2g and for P* is by construction. The 54% to 99% faithfulness gain is partly a property of the check "cites a measured number", which the template wording satisfies by design. Faithfulness says the numbers and claims in the text are right; it does not say the advice is good, and the human 1-to-5 rating is still not done.
