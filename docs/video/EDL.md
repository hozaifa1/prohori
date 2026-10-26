# Edit decision list (screens only)

Everything below is a **Screen** asset from `docs/video/assets/`. Hozaifa's face and voice are added in the final edit (speaker bubble + captions, see the `talking-head-video` skill). All stills are 1920x1080 PNG; all clips are 1920x1080 H.264, 30 fps, no audio, phone centred on a dark vignette. Times in clips are seconds from the start of that MP4 (rounded; the exact event times are in `assets/screens/markers.json`). Stills can take a slow punch-in (about 1.0 to 1.15x) to stay alive. Durations are suggestions that sum to each script row; retime to the real read.

Regenerate: `python tools/video_cards.py`, `python tools/video_charts.py`, `python tools/video_rectify.py`, `python tools/video_record.py [scene ...]` (the last one calls the live endpoint; clips are git-ignored).

Paths: `C` = `docs/video/assets/cards/`, `G` = `docs/video/assets/charts/`, `V` = `docs/video/assets/screens/`.

| Row | Script time | # | Asset (in-out) | Dur | What it shows / cue |
|---|---|---|---|---|---|
| 1 | 0:00-0:25 | 1 | `C/title.png` | 5 s | "PROHORI", tagline. Hold under "Hi, I'm Hozaifa ... Prohori means sentry". |
| | | 2 | `C/rana_plaza.png` | 10 s | Cue on "In 2013 Rana Plaza collapsed a day after cracks were reported". No photo (copyright); sources in CREDITS.md. |
| | | 3 | `C/crack_comparator.png` | 10 s | Cue on "judged by eye, with a plastic card". Original vector drawing. |
| 2 | 0:25-1:15 | 4 | `V/a_certified.mp4` 0.0-5.5 | 5.5 s | Live viewfinder of the printed panel (simulated camera feed). "You tape a printed board ... take a photo." |
| | | 5 | `V/a_certified.mp4` 6.0-17.8 | 11.8 s | Demo samples, pick "Good capture", Measuring... (cut the dialog wait: 6.0-8.7 is images loading, can trim to 8.7-17.8 = 9.1 s). |
| | | 6 | `V/a_certified.mp4` 23.5-38.5 | 15 s | Annotated overlay (board corners + crack outlines), then tap-to-zoom. "OpenCV 5 finds the ChArUco board ... flattens the crack region". |
| | | 7 | `G/rectified_profile.png` | 18 s | Rectified crop at known px/mm, cross-section lines, grey-level profile with half-depth width. Cue: "the width is read from the grey levels across the crack, not from a mask edge". Slow push toward the amber width label. |
| 3 | 1:15-1:55 | 8 | `V/a_certified.mp4` 17.8-23.5 | 6 s | Result: green Accept banner, "Certified", 1.00 mm, 0.92 to 1.07 range, "~97 of 100 certified readings were within tolerance". Cue: "Before any number is shown, a quality gate checks the photo". |
| | | 9 | `G/gate_risk_coverage.png` | 14 s | Green 3.2% wrong at 25.8% certified; amber 11.5% at 38.7%. Cue: "about 97 of every 100 green readings were within tolerance". |
| | | 10 | `V/b_agent_loop.mp4` 14.9-22.5 | 7.6 s | Amber "Move closer" banner on the far photo, 3.10 mm "Flagged / too far". Cue: "If the photo isn't good enough, it doesn't guess". |
| | | 11 | `V/c_hold_steady.mp4` 19.8-31.0 | 11 s | Optional alternative/extra: blurry and skewed photo, amber "Hold steadier" banner, crack K6 "Indicative" (rules policy). Use if row 3 needs filler or for "tilt, blur" in the gate list. Without it, extend 9 and 10. |
| 4 | 1:55-2:45 | 12 | `V/d_trace.mp4` 33-44 (trace read) | 14 s | Agent trace panel: step 1 numbers (scale 2.7 px/mm, gate 0/8) then "Move closer" instruction; step 2 numbers (scale 8.0 px/mm, +5.3) then "Accept". Slow scroll is already in the clip; stretch with a 0.8x slow-down if needed. Cue: "It never looks at pixels ... picks one of seven actions". |
| | | 13 | `V/b_agent_loop.mp4` 14.9-22.5 then 41.6-47 | 13 s | Refused/"Move closer" banner, then (cut) certified "Accept" banner 1.99 mm, "5 of 8 cracks certified". Cue: "the photo was too far, the agent said move closer, and the next photo was certified". |
| | | 14 | `G/agent_workflow_full.png` (optional) or zoom crops | 8 s | Perception / decision / action diagram. Crops: `agent_workflow_zoom_perception.png`, `_zoom_agent.png`, `_zoom_action.png`. Cue: "seven actions". Optional if time is short. |
| | | 15 | `G/ablation_v2.png` | 15 s | Five bars: P0 random 2%, P1 rules 62%, P2 AI agent 85%, P2g AI agent + fact-check 88%, P* ideal rule ceiling 88%; whiskers = 95% CI (compound subset, n = 48). Cue: "The chart shows how often each one turns a bad photo into a certified reading". Do not say the fact-check agent beats the rule ceiling: it equals it. |
| | | 15b | `G/faithfulness.png` | 8 s | Instructions that cite a measured number and contain no wrong number or claim: rules 91%, AI agent 54%, AI agent + fact-check 99%. Cue: "Every instruction it writes is checked against the measured numbers before you see it". Show right after #15; trim #12 to 11 s or #14 to 5 s to keep row 4 at about 50 s. |
| 5 | 2:45-3:30 | 16 | `G/architecture_full.png` | 6 s | Whole architecture. Cue: "Everything runs on AWS". |
| | | 17 | `G/architecture_zoom_left.png` | 8 s | Caddy, FastAPI, measure, gate, agent on the Graviton4 box. Cue: "A Graviton server runs OpenCV behind HTTPS". |
| | | 18 | `G/architecture_zoom_right.png` | 9 s | Bedrock, DynamoDB, S3, SNS, CloudWatch, engineer approval. Cue: "DynamoDB keeps every visit ... SNS emails an engineer". (No AWS console glimpse was recorded: it needs the account. `V/d_trace.mp4` is the in-app view of what DynamoDB stores.) |
| | | 19 | `C/cool_vs_pip.png` | 8 s | Same widths, same speed, one crash found and worked around. Cue: "same widths as stock OpenCV ... a crash that only happens with more than one thread". |
| | | 20 | `G/cool_latency.png` | 7 s | Developer-agent loop: 195 to 144 ms per photo, results bit-identical. |
| | | 21 | `G/cool_pareto.png` | 7 s | Cost vs latency, COOL on the same curve as pip, not cheaper. Cue: "speed and cost per thousand photos". |
| 6 | 3:30-4:15 | 22 | `G/width_error.png` | 15 s | 0.070 mm mean error on all 63 held-out cracks, 0.056 mm on the 41 certified. Cue: "average error is under a tenth of a millimetre, and lower again on the cracks the gate certifies". |
| | | 23 | `C/published_comparison.png` | 14 s | Certified MAE 0.056 vs 0.09 mm published; COV 13.1 vs 21.9% (thin), 7.0 vs 5.8% (wide, slightly worse). Cue: "meet the accuracy bar reported by recent published smartphone methods". |
| | | 24 | `G/failure_gallery.png` | 16 s | Too far, heavy blur, extreme angle: all refused, each with the agent's instruction. Cue: "every failure case is in the report". |
| 7 | 4:15-4:40 | 25 | `C/closing.png` | 25 s | Live URL + QR, GitHub URL, "OpenCV AI Competition 2026". Optionally open on the talking head full frame for the first ~10 s ("Prohori doesn't decide whether a building is safe ...") and bring the card in for the last ~15 s. |

Row totals: row 1 = 25 s, row 2 = 50 s (5.5 + 11.8 + 15 + 18), row 3 = 38 s without #11 (6 + 14 + 7.6, plus 10 s of holds) or 49 s with it, row 4 = 58 s with #15b (14 + 13 + 8 + 15 + 8), so trim to about 50 s as noted in #15b, row 5 = 45 s, row 6 = 45 s, row 7 = 25 s. Times are suggestions; the clip in-points assume the pacing recorded on 2026-10-26.

## Notes for the edit

* **Numbers to re-check before the final render** (SCRIPT.md "Numbers used"): the script's "about 97 of every 100 green readings" matches the strict gate level (3.2% wrong, `gate_summary.json`) and the app's own text. The older line "about five in a hundred" in SCRIPT.md refers to the default level (mean risk 4.3%, P(wrong | certified) 11.5%) and is stale: do not say it. Ablation 88 (AI agent + fact-check) / 85 / 62 / 2% and the 91 / 54 / 99% faithfulness bars match `eval/results/agent_ablation.md` (compound, n = 48; faithfulness over all decisions); width numbers match `width_eval.md`; COOL numbers match `cool/20261025T002750Z/REPORT.md`.
* **Ablation and faithfulness charts:** `G/ablation_v2.png` and `G/faithfulness.png` were regenerated from the final `agent_ablation.md` (includes P2g) with `python tools/video_charts.py ablation faithfulness`. The old four-bar `ablation.png` was removed. Labels: P0 random, P1 rules, P2 AI agent, P2g AI agent + fact-check, P* ideal rule ceiling. The fact-check is the code guardrail, not a second model.
* **Live clips are real runs** of the deployed app (Bedrock agent Nova Lite behind the guardrail, COOL box) with the app's own demo samples. The LLM wording varies a little between runs (for example "a 0.5 mm crack needs about 10" in these clips; the older gallery says "about 20"). The narration does not quote that number.
* The viewfinder in `a_certified.mp4` is a simulated camera feed (one of the sample photos), not a phone.
* No browser chrome or devtools is visible in any clip; no personal data is shown (the app footer, off screen, only lists the architecture and build).
* The glare cases in `docs/FAILURE_GALLERY.md` certify (a documented limitation), so the failure gallery shows too-far, heavy blur and extreme angle instead of glare. Do not add a glare shot to the "refuses" story.
* `G/architecture_*` and `G/agent_workflow_*` keep the diagrams' own light background (they are existing figures); the zoom crops are legible at 1080p, the full views are for orientation only.
* Captions/bubble: keep the bottom-right 560 px free on the phone clips (the phone is centred, so the bubble sits on the vignette, not on the app).
