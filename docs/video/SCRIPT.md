# Prohori — demo video script (target 4:40, hard limit 5:00)

Format: Hozaifa on camera in a small picture-in-picture bubble; the screen behind him changes with what he says. **TH** = talking head (camera on him, full frame or large bubble). **SCR** = screen recording or chart, with him in the corner bubble.

What Hozaifa records (D37): only the words in the "Say" column, read at a calm pace, in one or several takes. Everything in the "Screen" column is added in the edit (D38).

Recording tips: phone at eye level, window light in front of you (not behind), quiet room, phone ~60 cm away, landscape. Pause 2 seconds between sections so they can be cut cleanly. If you stumble, pause and say the sentence again; don't restart the section.

| # | Time | Say | Screen |
|---|---|---|---|
| 1 | 0:00–0:25 | **TH.** "Hi, I'm Hozaifa, an electrical engineering graduate from the University of Dhaka, and this is Prohori. *Prohori* means *sentry* in Bengali. In 2013 Rana Plaza collapsed a day after cracks were reported in its walls. Today crack width is still judged by eye, with a plastic card. Prohori measures it in millimetres from a phone photo, and it refuses to give a number when the photo can't support one." | Title card → Rana Plaza news still (credited) → crack-comparator card photo |
| 2 | 0:25–1:15 | **SCR.** "Here's how it works. You tape a printed board next to the crack and take a photo. OpenCV 5 finds the ChArUco board, recovers the wall's pose, and flattens the crack region to a known scale in pixels per millimetre. Then the width is read from the grey levels across the crack, not from a mask edge, because published benchmarks show masks are rarely right to the pixel." | Live phone capture of the panel → overlay with board + crack outline → rectified crop with width profiles |
| 3 | 1:15–1:55 | **SCR.** "Before any number is shown, a quality gate checks the photo: corners found, blur, tilt, glare, resolution. The gate is calibrated with conformal risk control. On photos it never saw, about 97 of every 100 green, certified readings were within tolerance. If the photo isn't good enough, it doesn't guess." | Results card: big mm number ± interval, "Certified" badge; then a far shot: amber "Move closer". On-screen caption: held-out risk number from the final `gate_report.md` |
| 4 | 1:55–2:45 | **SCR.** "That's where the agent comes in. It never looks at pixels. It gets the numbers OpenCV measured and picks one of seven actions: accept, move closer, hold steadier, change the light, re-place the board, accept with a wider uncertainty, or stop and log it. Then it tells you what to do in plain words. Here the photo was too far, the agent said move closer, and the next photo was certified. We tested it on held-out cases against a fixed rule list we wrote ourselves and against random choices. When a photo has several problems at once, the agent gets it certified far more often than the rules do. Here are the numbers." | Agent trace timeline (perception numbers → decision → instruction → re-shot → certified) → ablation bar chart |
| 5 | 2:45–3:30 | **SCR.** "Everything runs on AWS. A Graviton server runs OpenCV behind HTTPS; DynamoDB keeps every visit and every agent decision; S3 keeps the evidence photos, with faces blurred before saving; and if a crack widens by more than the measurement uncertainty, SNS emails an engineer, who has to approve it. We also run the whole pipeline on Graviton4 with COOL, OpenCV's optimised build. We checked that it gives the same widths as stock OpenCV, measured speed and cost per thousand photos, and found and documented a crash that only happens in COOL with more than one thread." | Architecture diagram → CloudWatch / DynamoDB glimpse → COOL results table + Pareto chart |
| 6 | 3:30–4:15 | **SCR.** "Results. On a printed panel with known widths, held out from all tuning, the average error is under a tenth of a millimetre, and lower again on the cracks the gate certifies. The certified readings meet the accuracy bar reported by recent published smartphone methods. Every number, and every failure case, is in the report." | Error distribution plot → table vs published → failure gallery (blur, glare, too far) |
| 7 | 4:15–4:40 | **TH.** "Prohori doesn't decide whether a building is safe. That's an engineer's job. It gives them a number, how sure that number is, how it changed since the last visit, and a request to come and look. The code, the data and every result are public. Thank you." | Closing card: endpoint URL + QR, GitHub URL, "OpenCV AI Competition 2026" |

Word count of the spoken text: about 640 words, about 4:35 at 140 words per minute.

## Numbers used, and where they come from (check before the final edit)

- "about 97 of every 100 green readings": strict level, mean held-out P(wrong | certified) 3.2 %, `eval/results/gate_report.md` (refit on the shipped widths, 2026-10-25).
- 85 / 62 / 2 %: `eval/results/agent_ablation.md`, compound subset, recovery within 3 actions, n = 48.
- 0.070 mm all cracks, 0.056 mm certified, held-out TEST: `eval/results/width_eval.md`.
- 13 % vs 22 % COV below 0.5 mm: `eval/results/width_eval.md` vs Hassouna et al., Sci. Rep. 2026.
- COOL: `eval/results/cool/` REPORT.md.
