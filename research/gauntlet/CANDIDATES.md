# Candidate slate — OpenCV AI Competition 2026

Seven candidates generated against the dossier. The gauntlet must kill or promote each on evidence, not taste.

---

## C1 — Active-Perception Structural Inspection Agent
Handheld/drone video of concrete structures. OpenCV 5 DNN engine runs an ONNX crack-segmentation model; ALIKED/DISK + LightGlue register multi-view frames; OpenCV 5 3D module recovers scale so crack **width in mm** is measured, not just detected. The agent decides *where to look again* — re-image region X at higher zoom, request a second sweep, or escalate to a human engineer with a bounded confidence claim.
- Impact: building-safety inspection; Bangladesh RMG factory / post-Rana-Plaza framing is genuine and personal.
- Data: SDNET2018, CrackForest, Concrete Crack Images, METU.
- COOL leg: the register-and-measure front end is imgproc/core heavy.
- Weakness to attack: the "action" is a re-tasking instruction with no actuator behind it. Is that a real perception-action loop or theatre?

## C2 — Physics-Informed Video Prediction for Process Control
Predict the next N frames of a physical process, then use prediction residual to trigger a control action or alarm. Organizer-listed area #2, and Hozaifa's device-physics background is a genuine moat almost no other entrant has.
- Weakness to attack: what process, and where does the video come from? Without a real process feed this collapses into a dataset demo. Candidate domains: combustion/flame, solder reflow, fluid flow, boiling, crystal growth.

## C3 — Autonomous Pipeline-Optimizer Developer Agent on COOL/Graviton
An agent that, given a vision task plus labelled data, generates candidate OpenCV 5 pipelines, executes them on the COOL Graviton box, measures accuracy against visual ground truth **and** latency/throughput/cost, and uses those measurements to mutate the next candidate (interpolation choice, threshold strategy, op ordering, dtype, KleidiCV paths, DNN backend/target, batch shape). Converges to a Pareto front and **deploys the winner as a running service**.
- This is the rulebook's own worked example of a qualifying developer-agent workflow, and organizer-listed area #6.
- COOL story is inherent: reproducible measurement is the product.
- Weakness to attack: Real-world impact is 20% of the overall rubric and this is a developer tool. Does it ceiling out at the Special Awards while losing the Grand Prize?

## C4 — Hybrid: C3's optimizer wrapped around C1's application
Outer loop: a deployment agent that tunes and deploys the vision pipeline on Graviton from measurements. Inner loop: a runtime active-perception agent doing the inspection task.
- Maximises coverage of all three rubrics.
- Weakness to attack: scope explosion for a solo builder in 59 days. Two agent loops means two failure surfaces and twice the evaluation burden.

## C5 — Agentic Navigation/Scene Assistant for Blind Users
Active perception: the agent chooses what to look at, zooms, re-queries, asks for confirmation.
- Strong impact and UX. Weakness to attack: heavily crowded hackathon territory; innovation ceiling is low; likely several of the other 760 participants build this.

## C6 — Smallholder Crop-Disease Active Perception (Bangladesh)
Low-end phone camera, agent guides the farmer to reshoot, then decides diagnosis vs escalate.
- Weakness to attack: OpenCV 5 depth is thin — mostly a classifier with cv2 glue. Technical execution is 30% of the rubric.

## C7 — Multi-Agent Visual SLAM with Distributed Context
N SLAM agents (dataset replay or simulated robots) run as containers on Graviton; COOL accelerates the imgproc-heavy front end; OpenCV 5's ALIKED/DISK + LightGlue form a modern feature front-end; a cloud map-merge service holds distributed context; an orchestrating agent decides which agent explores where, when to relocalize, and when to share map context — driven by visual coverage and drift estimates.
- Organizer-listed area #3. Strong taste alignment with Gary Bradski (robotics/SLAM lineage).
- Needs no hardware: EuRoC, TUM-VI, KITTI, Newer College replay as "agents".
- Impact framing: disaster mapping / search and rescue (flood and cyclone response is credible from Dhaka).
- Weakness to attack: is multi-agent SLAM solo-buildable to a *demonstrable, evaluated* standard in 59 days? Is the impact claim earned or asserted?
