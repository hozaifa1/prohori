# PROHORI — Pre-registration: P0 / P1 / P2 triage-agent ablation (Loop 1)

*Written 2026-10-19, before any P0, P1, P2 or oracle policy was run on the dev or test seeds. Anchors: METRICS.md §3, ENTRY_PROHORI_FINAL.md "Agency, stated honestly and then measured", LITERATURE.md A1, A2, A6, A7. This file is hashed (sha256) before the test run, and the hash is printed in `eval/results/agent_ablation.md`. Any change after the hash is taken is listed in the Amendments section at the bottom, with a date, and the hash is retaken.*

## 0. What is being tested, in one paragraph

Three policies get the **same numeric observation** of a phone capture of a ChArUco board and a crack, the same certification-gate result, and the same history. Each picks one of seven actions. A simulated operator carries the action out, a new capture is generated, and the loop repeats until the capture is certified, the policy gives up, or the turn limit is reached. The policies are **P0** (uniform random action), **P1** (`agent.rules_decide`, the fixed-threshold if/else cascade as it stands in the repository at the time of writing) and **P2** (`agent.decide(policy="llm")`, a Bedrock tool-use agent). None of them sees pixels (LITERATURE A1, A2). **This is a simulator study, not a field study.** It measures whether the policy chooses well *inside a model of capture degradation that we wrote*, and it cannot say how the policies behave on a real wall.

## 1. Expectation, stated in advance

1. **P0 is far below both P1 and P2** on every outcome metric. This is a sanity check on the simulator, not a finding.
2. **On single-cause failures P1 will match P2.** One failing feature maps to one action, and P1 already encodes that map. We expect |P2 − P1| < 10 points of recovery on single-cause episodes.
3. **On compound and conflicting failures P2 may beat P1, and the pre-registered success criterion is P2 − P1 ≥ +10 points of recovery within 3 actions on the compound subset** (METRICS §3). It is a bar, not a prediction. Our honest prior that a small, cheap model (Amazon Nova Lite) clears it is below one half: P1 already orders glare and geometry sensibly, and the simulator only rewards a different order in a handful of states.
4. **The test is under-powered for a +10 point effect.** The model-call budget allows about 100 held-out episodes, 48 of them compound. A paired comparison on 48 episodes has a 95% interval about ±15 points wide. If the interval straddles zero we report "no detectable difference", not "P2 equals P1".
5. **If P2 does not beat P1, that result is published** (METRICS §3, ENTRY §Agency).

## 2. Task definition

* **Episode.** A single crack, a ChArUco board (140 × 100 mm, 24 inner corners) taped beside it, a 4000 × 3000 phone frame. Capture 0 is the first photo. After each capture the policy is called once and returns one action; the simulated operator executes it; capture *t+1* is generated. At most **T_max = 6 actions** (7 captures).
* **Observation** (identical for all policies, same fields as `measure.analyze()["observation"]`): `corners`, `corners_total` (24), `blur_var`, `px_per_mm`, `obliquity_deg`, `glare_frac`, `crack_px_extent`, `image_w`, `image_h`. Plus `gate = {certified, reasons}` and `cracks` (measured width records, with no ground truth), plus `history` in the format the service stores (`observation`, `gate`, `decision` per past step). The policy never sees the latent state or the episode class.
* **Gate.** Same function as `measure.py`: reasons in the order `too_few_corners` (corners < 8), `low_resolution` (px/mm < 8), `blurry` (blur_var < 150), `oblique` (obliquity > 45°), `glare` (glare > 0.05), certified only if there are no reasons **and** a crack was measured. Thresholds are read from `agent.GATE_THRESHOLDS` when the run starts and written into the results file. The simulator and the labelling rule are expressed relative to these thresholds, so they stay valid if the gate is refitted. Values at the time of writing: 8 / 8 / 150 / 45 / 0.05.
* **Real-pipeline quirk reproduced on purpose.** In `measure.py`, when the board is not found (fewer than about 7 usable corners) the pipeline returns `px_per_mm = 0`, `obliquity_deg = 0`, `glare_frac = 0`, `crack_px_extent = 0`, and the only gate reason is `too_few_corners`. `blur_var` is then the variance of the Laplacian of the whole frame at quarter resolution. **So glare is invisible whenever the board is lost.** The simulator does the same.
* **Terminal outcomes.** `certified` (the episode ends the moment a capture passes the gate), `abandoned` (action `abandon_and_log`), `widened` (action `accept_with_widened_uncertainty`, allowed only when a crack was measured and the capture is uncertified), `timeout` (6 actions used). `accept` on an uncertified capture is a wasted turn with no state change. The simulated operator executes every other action with a 10% chance of not complying (nothing changes).
* **Common random numbers.** All state transitions are drawn from a generator seeded by `(episode seed, turn index, action id)` and all observation noise by `(episode seed, turn index)`, so every policy faces identical luck for identical choices and comparisons are paired by episode.

## 3. Episode generator

Every parameter is relative to the gate thresholds T (T_c = corners, T_p = px/mm, T_b = blur_var, T_o = obliquity, T_g = glare).

**Nominal (non-failing) capture, drawn first.** Frontal scale `ppm0 = T_p × U(1.25, 2.4)`; obliquity `θ = min(40°, 9° × exp(N(0, 0.8)))`; `blur = T_b × U(1.1, 2.5)`; `glare = 0`; board visibility `vis = 1`; crack framed; dim-light flag `dim ~ Bernoulli(0.25)`. *Anchor:* the 22 board-found photos in `eval/results/panel_photos_2026-10-19.csv` have px/mm / 8 in [1.25, 2.38] (median 1.79), obliquity median 9.6° (range 0.8–42.4°), certified-photo blur_var / 150 in [1.04, 2.45], and glare exactly 0 in all 29 photos.

**Causes** (each replaces the matching nominal value):

| cause | draw | anchor |
|---|---|---|
| `low_res` | `ppm0 = T_p × U(0.35, 0.90)` | assumption (the panel never fell below 9.96 px/mm) |
| `blur` | `blur = T_b × exp(U(ln 0.25, ln 0.92))` | anchored: failing board-found photos span 0.29–0.92 × T_b; whole-frame values of no-board photos 20–31 |
| `glare` | `glare = T_g × exp(U(ln 1.6, ln 8))`, and `glare_susc = glare` | assumption (panel glare is all zero) |
| `oblique` | `θ = U(47°, 68°)` | assumption (panel maximum 42.4°) |
| `board_partial` | `vis = U(0.10, 0.31)` | anchored loosely: real board-found photos had 9–24 corners; no-board photos 0–6 |
| `no_crack` | crack not in frame | assumption |

**Classes.** The class list is fixed, in a fixed order, so the held-out set is balanced and reproducible.

| class | definition | counts in a 25-episode block | counts in the 100-episode test split |
|---|---|---|---|
| **S** single cause | one cause, uniform over the 6 | 5 | 20 |
| **X** conflicting pair | one of 5 named pairs: glare+oblique, oblique+blur, glare+blur, blur+low_res, oblique+low_res | 5 | 20 |
| **C2** other pair | uniform over the other 10 two-subsets | 3 | 12 |
| **C3** triple | uniform over the 20 three-subsets | 4 | 16 |
| **H** hopeless | one of three sub-types with equal probability: *damaged board* (`vis_cap = U(0.10, 0.28)`, start at the cap), *impossible lighting* (`glare_floor = T_g × U(2.5, 6)`, start at `floor × U(1, 1.6)`), *unreachable* (`ppm_cap = T_p × U(0.4, 0.8)`, start at `cap × U(0.7, 1)`); 30% of H episodes also get a `blur` cause | 4 | 16 |
| **M** constrained-marginal | `ppm_cap = T_p × U(0.85, 0.97)` (the operator cannot get closer), start at `cap × U(0.8, 1)`, obliquity `U(0, 12°)`, nothing else wrong | 4 | 16 |

**Compound subset** = X ∪ C2 ∪ C3 (48 of 100 test episodes). **Recoverable** = S ∪ X ∪ C2 ∪ C3. **Correct terminal outcome**: `certified` for recoverable, `abandoned` for H, `widened` for M. The class is latent: no policy sees it.

## 4. Capture-to-observation model

Latent state: `ppm0` (frontal px/mm), `θ`, `blur` (true board-ROI Laplacian variance), `glare`, `vis`, `framed`, `dim`, plus caps (`ppm_cap`, `glare_floor`, `vis_cap`) and `glare_susc`.

* Effective visibility `vis_eff = min(vis, min(1, (22 / ppm0)²))`. The last term is the board spilling out of the frame when too close (22 px/mm is about where board and crack stop fitting a 4000 px frame; the panel maximum was 19.1 with 24 corners).
* Per-corner detection probability `p = 0.97 × f_glare × f_blur × f_tilt × f_res`, with `f_glare = 1 − 0.85 × clip((glare − 0.03)/0.17, 0, 1)`, `f_blur = sigmoid((ln blur − ln 45)/0.3)` (real photos: blur_var 44 → 23 corners, 31 → 6, 20 → 0), `f_tilt = 1 − 0.7 × clip((θ − 45)/25, 0, 1)`, `f_res = sigmoid((ppm0 − 3)/0.8)`. `corners ~ Binomial(round(24 × vis_eff), p)`.
* Board **found** iff `corners ≥ 7`. If found: `px_per_mm = ppm0 × sqrt(cos θ) × exp(N(0, 0.04))` (local scale under tilt), `obliquity_deg = max(0, θ + N(0, 1.2))`, `blur_var = blur × exp(N(0, 0.12))`, `glare_frac = glare × exp(N(0, 0.10))`. Crack measured iff framed, found, `px_per_mm ≥ 3`, and (`glare < 0.1` or a 60% draw succeeds); `crack_px_extent = round(80 × px_per_mm)` if measured else 0.
* Board **not found**: `corners` as drawn, `blur_var = blur × exp(N(ln 1.4, 0.35))` (whole-frame), `px_per_mm = obliquity_deg = glare_frac = crack_px_extent = 0`, reasons `["too_few_corners"]`, no crack.

## 5. Action transitions (each action is skipped entirely with probability 0.10, the operator's non-compliance; otherwise it does the following)

| action | effect on latent state |
|---|---|
| `move_closer` | `ppm0 ← min(ppm_cap, max(1.3 × ppm0 × exp(N(0, 0.15)), T_p × U(1.1, 1.8)))`; `blur ← blur × exp(N(ln 0.85, 0.2))` (closer means shallower focus and magnified shake) |
| `reshoot_steadier` | `blur ← T_b × U(1.1, 2.5) × (0.8 if dim else 1)` |
| `relight` | `glare ← max(glare_floor, T_g × U(0, 0.8))`; if `dim`, with prob 0.5 `blur ← blur × exp(N(ln 0.6, 0.15))` (shading a dim scene costs sharpness) |
| `reposition_marker` | `vis ← min(vis_cap, U(0.9, 1))`, `framed ← True`, `θ ← min(θ, \|N(10°, 7°)\|)` if `θ > 20°`. **Always**, viewpoint changes re-roll viewpoint-dependent nuisances: with prob 0.5 `glare ← max(floor, glare_susc × exp(N(0, 0.7)))` (zero if the episode has no glare susceptibility), with prob 0.5 `blur ← blur × exp(N(0, 0.35))` and `ppm0 ← ppm0 × exp(N(0, 0.10))` |
| `accept_with_widened_uncertainty` | terminal `widened` if a crack was measured, otherwise a wasted turn |
| `accept` | wasted turn if uncertified |
| `abandon_and_log` | terminal `abandoned` |

*What the simulator rewards that a fixed priority list misses:* the re-roll in `reposition_marker` makes it better to fix geometry **before** glare or blur when the board is still detectable, and glare must be fixed **first** when it has hidden the board. These are assumptions we wrote down, and they favour a policy that reasons about order. A different set of assumptions could favour P1. Reported as a limitation.

## 6. The labelling rule (written before any run; single annotator)

`label(obs, gate, cracks, history)` returns an **acceptable set** A and one **primary** action. F is the number of trailing uncertified captures in `history` (that is, before the current one). "Marginal" means every failing check is within 20% of its threshold in the failing direction (low-side checks: `1 − value/T ≤ 0.2`; high-side checks: `value/T − 1 ≤ 0.2`).

1. `gate.certified` → A = {`accept`}.
2. Reasons non-empty, a crack measured, F ≥ 2 and marginal → A = {`accept_with_widened_uncertainty`}.
3. F ≥ 3 → A = {`abandon_and_log`}. (Fourth failed capture, matching `MAX_FAILED_ATTEMPTS = 4` in the agent spec.)
4. Board not found (`px_per_mm == 0`): if `blur_var < 100` → A = {`reshoot_steadier`} (the whole-frame sharpness of the real no-board photos separates cleanly: 20–31 blurred, 291–518 sharp); else if the previous action was not `reposition_marker` → A = {`reposition_marker`}; else A = {`relight`} (next hypothesis: glare hides the board).
5. Board found, reasons empty (no crack in view) → A = {`reposition_marker`}.
6. Board found, failing causes C ⊆ {glare, oblique, low_resolution, blurry, too_few_corners}. Action map: glare → `relight`, oblique → `reposition_marker`, blurry → `reshoot_steadier`, low_resolution → `move_closer`, too_few_corners → `reposition_marker`.
   * 6a. glare ∈ C **and** corners < 12 (glare is hiding the board) → A = {`relight`}.
   * 6b. oblique ∈ C **and** |C| ≥ 2 (tilt is upstream of scale and detection, and re-aiming re-rolls glare) → A = {`reposition_marker`}.
   * 6c. otherwise the failing causes are causally independent and A = {map(c) : c ∈ C}. The **primary** action is that of the cause with the largest log-exceedance `|ln(value/T)|`, ties broken by glare, oblique, blurry, low_resolution, too_few_corners.
   In 1–5 and 6a–6b the primary is the single member of A.

The rule is also run as a policy, **P\*** (the "label policy"), to give a ceiling for what rules can reach in this simulator. P\* was written after the simulator and has seen its couplings; it is **not a competitor**, and P1 is not tuned toward it.

## 7. Metrics

Unit of analysis for confidence intervals: the **episode** (percentile bootstrap, 10,000 resamples, seed 20261019; paired differences resample episodes jointly across policies).

| metric | definition |
|---|---|
| **Primary: recovery@3, compound subset** | share of compound episodes whose capture is certified at or before capture index 3 (three actions). Reported for P0, P1, P2, P\* with CIs, and the **paired difference P2 − P1** with CI |
| Recovery@3 and @6, single / compound / recoverable | as above on S, on X ∪ C2 ∪ C3, on all recoverable |
| Turns-to-certified | median and mean number of actions among episodes that were certified |
| Correct-outcome rate | share of all episodes ending in the correct terminal outcome for their class (§3) |
| Action accuracy | at every decision point on an uncertified capture: strict (= primary action) and acceptable (∈ A). **Wrong-action rate = 1 − acceptable accuracy.** Decision-level, bootstrapped over episodes |
| Escalation precision / recall | **(a) vs the rule:** over decisions, positive = A is {`abandon_and_log`}; **(b) vs truth:** per episode, positive = hopeless class H; predicted = the policy abandoned at some point. Both reported |
| False abandon | share of recoverable episodes the policy abandoned |
| Instruction quality | **not human-rated in this run.** Automated checklist only: ≤ 140 characters, cites a number from the observation, names the same operator behaviour as the chosen action. The human 1–5 rating in METRICS §3 is pending, and its single-annotator limitation applies when it is done |
| Cost | model calls, input and output tokens, dollars, policy fallbacks |

Fallback accounting: if P2 hits an error and `decide()` silently substitutes the rules action, the step is recorded as a fallback and reported. The primary table uses the system as deployed (fallbacks included). A second row reports P2 with fallbacks counted as failures if any occur.

## 8. Splits, seeds and model-call budget

| split | seeds | policies | size |
|---|---|---|---|
| **sim-check** | 900000 and up | any (used only to debug the simulator; never reported; the simulator is changed only on oracle and P0 behaviour, and any other change is logged in Amendments) | scratch |
| **dev** | 1000–1199, blocks of 20 episodes (S3, X4, C2 3, C3 4, H3, M3) | P0, P1, P\* on all 200; **P2 on the first block of 20 only** (the dev-LLM set) | 200 / 20 |
| **test (held out)** | 50000–50099, blocks of 25 (S5, X5, C2 3, C3 4, H4, M4) | P0, P1, P\*, P2, each **exactly once** | 100 |

* **P2 prompt iteration.** The starting prompt (v0) is the `SYSTEM_PROMPT` and tool description in `agent.py` at the time of writing, hashed in the results file. At most **3 revisions** (v1–v3), using the dev-LLM set only. Selection rule, fixed now: pick the version with the highest recovery@3 on the dev-LLM set; ties go to higher acceptable accuracy, then to the earlier version. The test split is not looked at while choosing. The test run happens **once**.
* **P1 is frozen.** No edits to the rules code (`_failures`, `_rule_text`, `_marginal`, `rules_decide`, `_rules`). Its source fingerprint is printed in the results file.
* **Dev-set overfitting is possible and not controlled for**: the dev-LLM set is 20 episodes and is reused across iterations.
* **Model:** `us.amazon.nova-lite-v1:0`, region `us-east-1`, temperature 0, one forced tool call per decision, no hidden fallback model. **Budget:** at most 600 model calls over all work, counting prompt iteration, the one Claude availability probe and smoke tests, logged in `eval/runs/agent_ablation/llm_ledger.jsonl`. Nova Lite: $0.06 / 1M input tokens, $0.24 / 1M output tokens.
* Larger free-policy runs (P0, P1, P\* on 1,000 test-distribution episodes at separate seeds) are reported as a secondary table. They cost no model calls.

## 9. Known limitations, stated now

1. **Single annotator.** The labelling rule was written by one person (the pipeline's author, via an AI coding assistant) and not cross-checked by a second annotator. The rule and the simulator's couplings come from the same reasoning, so agreement between a policy and the label shows the policy shares that reasoning, not that the reasoning is right.
2. **Synthetic operator and degradation model.** Operators comply 90% of the time and respond exactly as the transition table says. Glare, severe obliquity and low px/mm are not present in the 29 real panel photos, so their distributions are assumptions, flagged in §3. Real-pipeline marginals (px/mm, obliquity, blur, corner count) are the only anchored ones.
3. **The observation is rich and clean.** Real captures can produce observation vectors the simulator does not (for example `invalid_image`, a locator that fails after the board is found).
4. **Small sample, one cheap model.** About 100 held-out episodes and Nova Lite. A negative result here does not generalise to larger models; a positive one does not generalise to the field.
5. **No human-rated instruction quality in this run.**

## Amendments

* **A1, 2026-10-19, before any policy run on dev or test seeds.** The `blur` cause range was changed from `exp(U(ln 0.15, ln 0.92))` to `exp(U(ln 0.25, ln 0.92))`. Reason: the calibration check of simulated against real blur_var (KS test against the 22 board-found panel photos) gave p = 0.009 with the wider range, because the real failing photos start at 0.29 × T_b (and the lower, no-board frames are already covered by the board-not-found branch). Only the oracle policy and P0 had been run, on sim-check seeds.
