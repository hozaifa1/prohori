# THE BAR — what our concept must beat, blind

## Reference artifact
**FREISA — "Four-legged Robot Ensuring Intelligent Sprinkler Automation"**, Team B-AROL-O.
**Grand Prize winner, OpenCV AI Competition 2023.**
Fetched 2026-08-28 from hackster.io/b-arol-o/four-legged-robot-ensuring-intelligent-sprinkler-automation-845012 and github.com/B-AROL-O/FREISA.

Secondary references: *Charlie* (Cortic Tigers) and *NeoCam* — 2021 grand prize winners.

## What FREISA actually is
A quadruped robot (MangDang MiniPupper 2, 12-DoF, Raspberry Pi 4, Ubuntu 22.04) carrying an OAK-D-Lite depth camera and a pelvis-mounted sprinkler with an onboard reservoir. It walks a garden arena of tomato plants, classifies each plant healthy vs. dried-out with a Roboflow-trained model running on the OAK-D's dedicated VPU, and sprays the ones that need water. Navigation is a hand-written finite state machine whose transitions are driven by camera inference results. A `VisionController` Python class wraps model loading, pipeline launch, and result collection. Docker on the Pi; an HTTP server exposes status. Custom 3D-printed brackets. Replicated across three sites — Turin, Chicago, Nantes.

## Why it won — the qualities we must match or exceed
1. **A closed physical perception→action loop with a real actuator.** Vision does not merely describe; it opens a valve. This is viscerally demonstrable on video.
2. **Architecture documented at professional standard.** SysML models authored in Eclipse Capella — operational entities, interconnections, activity, logical and physical architecture — not a hand-drawn box diagram.
3. **Reproducibility as craft.** Full bill of materials, assembly instructions, servo calibration procedure, printable parts, MIT/CC-BY-SA licensing, REUSE compliance.
4. **A narrative with continuity and charm.** Sequel to their 2022 ARNEIS entry; team lore; prior-winner advisors deliberately recusing themselves from writing code. It reads like a story, not a report.
5. **Distribution.** Hackster writeup (7,437 views), Electromaker, a 4-page interview in The MagPi issue 139, Tom's Hardware. The judges met the project more than once.
6. **Team depth.** Six people, two of them prior OpenCV-contest winners.

## Where FREISA is beatable under the 2026 rubric specifically
These are our attack surfaces. A concept that does not exploit them will lose.
- **Technical execution (30%)** — the vision is an off-the-shelf Roboflow classifier on a VPU. No algorithmic depth, no novel use of OpenCV internals, nothing that OpenCV 5's rewritten DNN engine, ALIKED/DISK/LightGlue, HAL/KleidiCV or 3D module would even be needed for.
- **Evaluation evidence** — essentially absent. No quantitative task-success numbers, no baselines, no failure taxonomy, no ablations. The 2026 package *mandates* evaluation evidence including failure cases.
- **Cloud delivery (10%) and the COOL award (100% of a $1,000 rubric)** — FREISA has no cloud component whatsoever and would score zero on the entire COOL rubric.
- **Agency** — an FSM is not an agent. Under the 2026 Agentic Vision rubric ("orchestration & autonomy" 25%, "failure handling & human control" 15%) an FSM with hardcoded transitions is the weakest possible qualifying entry.
- **Observability and responsible use** — not addressed.

## The exit condition
A blind critic, given our concept and FREISA side by side with labels stripped, must pick **ours** under:
1. the 2026 **Overall** rubric (Technical 30 / Innovation 20 / Impact 20 / UX 10 / Docs 10 / Responsible cloud 10),
2. the **Best Use of COOL** rubric, and
3. the **Agentic Vision** rubric.

...while also passing three hard gates:
- **G1 — Solo, 59 days.** One final-semester engineering student with Claude Code, from 2026-08-28 to 2026-10-26.
- **G2 — $0.00 of the builder's own money.** AWS Free Tier + t4g.small free hours + up to $200 free-plan credits + the $150 grant only.
- **G3 — No hardware he does not already own.** No robot, no drone, no fab, no GPU. A laptop and a phone camera.

Note the asymmetry this creates: FREISA won partly *on hardware charm* we cannot buy. So we cannot beat it by imitation. We must beat it on the axes the 2026 rubric rewards and 2023 did not — depth of OpenCV 5 use, measured performance on Graviton, genuine agency, and evaluation rigour — while matching its documentation craft and its demonstrability on video.
