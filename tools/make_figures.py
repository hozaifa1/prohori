"""Draw the three documentation figures of the CURRENT build (matplotlib only, no graphviz needed).

    python tools/make_figures.py            # writes docs/figures/{architecture,agent_workflow,dev_agent_loop}.{png,svg}

Every box names something that exists in the code: OpenCV calls are the ones found in src/prohori/*.py, AWS services are the
ones created by infra/*.sh.  The developer-loop figure reads its counts from eval/results/cool_agentloop/trace.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1b2430"
MUTED = "#5b6573"
C = {  # fill, edge
    "cv": ("#e3f0ff", "#2b6cb0"),     # OpenCV 5 stages
    "ml": ("#eef0ff", "#4c51bf"),     # gate / learned parts
    "agent": ("#fff3d6", "#b7791f"),  # agent
    "aws": ("#fff0e0", "#c05621"),    # AWS services
    "human": ("#e6f6ec", "#2f855a"),  # human in the loop
    "user": ("#f1f3f5", "#6b7280"),   # phone / operator
    "bad": ("#fde8e8", "#c53030"),
}


def box(ax, x, y, w, h, title, lines=(), kind="cv", fs=9, tfs=10.5, bold=True):
    fc, ec = C[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.0,rounding_size=0.12", fc=fc, ec=ec, lw=1.6, zorder=2))
    ty = y + h - 0.22
    ax.text(x + 0.14, ty, title, fontsize=tfs, fontweight="bold" if bold else "normal", color=INK, va="top", ha="left", zorder=3)
    if lines:
        ax.text(x + 0.14, ty - 0.36, "\n".join(lines), fontsize=fs, color=INK, va="top", ha="left", linespacing=1.35, zorder=3)


def arrow(ax, p, q, color=INK, lw=1.6, style="-|>", rad=0.0, ls="-", label=None, lpos=0.5, loff=(0, 0.12), lfs=8.5):
    a = FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=14, color=color, lw=lw, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}", zorder=4, shrinkA=0, shrinkB=0)
    ax.add_patch(a)
    if label:
        mx = p[0] + (q[0] - p[0]) * lpos + loff[0]
        my = p[1] + (q[1] - p[1]) * lpos + loff[1]
        ax.text(mx, my, label, fontsize=lfs, color=MUTED, ha="center", va="bottom", zorder=5,
                bbox=dict(fc="white", ec="none", pad=1.0, alpha=0.85))


def canvas(w, h, title, sub=None):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(-0.5, w + 0.8)
    ax.set_ylim(-0.6, h)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(0.3, h - 0.3, title, fontsize=17, fontweight="bold", color=INK, va="top")
    if sub:
        ax.text(0.3, h - 0.82, sub, fontsize=10, color=MUTED, va="top")
    return fig, ax


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=170 if ext == "png" else None, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


def legend(ax, items, x, y, step=2.6):
    for i, (k, t) in enumerate(items):
        fc, ec = C[k]
        ax.add_patch(FancyBboxPatch((x + i * step, y), 0.32, 0.22, boxstyle="round,pad=0,rounding_size=0.04", fc=fc, ec=ec, lw=1.4))
        ax.text(x + i * step + 0.42, y + 0.11, t, fontsize=8.5, color=INK, va="center")


# ============================================================================================ architecture
def architecture():
    W, H = 22, 12.6
    fig, ax = canvas(W, H, "PROHORI architecture (as deployed 2026-10-26)",
                     "Phone photo of a crack beside a printed ChArUco board -> width in mm + quality tier + next action. "
                     "Live: https://184-194-241-186.sslip.io")

    # phone
    box(ax, 0.3, 6.1, 3.0, 3.4, "Phone / browser", ["PWA (service/static)", "camera needs HTTPS", "capture, upload, demo", "samples, agent trace", "view, approval page"], "user")
    # AWS region frame
    ax.add_patch(FancyBboxPatch((4.0, 0.55), 17.7, 10.45, boxstyle="round,pad=0,rounding_size=0.2", fc="#fcfcfd", ec="#9aa3af", lw=1.4, ls="--", zorder=1))
    ax.text(4.2, 10.82, "AWS us-east-1", fontsize=11, fontweight="bold", color=MUTED, va="top")

    # EC2 frame
    ax.add_patch(FancyBboxPatch((4.3, 3.25), 11.3, 7.2, boxstyle="round,pad=0,rounding_size=0.15", fc="#f7fafc", ec="#c05621", lw=1.8, zorder=1))
    ax.text(4.5, 10.3, "EC2 c8g.large  (Graviton4, Ubuntu 24.04, Elastic IP)  -  COOL: Cloud Optimized OpenCV 5.1.0-dev (KleidiCV)",
            fontsize=10.2, fontweight="bold", color="#9c4221", va="top")
    box(ax, 4.55, 8.55, 2.1, 1.25, "Caddy", ["TLS (Let's Encrypt)", "<ip>.sslip.io"], "aws", fs=8.5)
    box(ax, 6.95, 8.55, 3.0, 1.25, "FastAPI / uvicorn", ["service/app.py", "/api/measure /api/trace", "/api/approve /health"], "aws", fs=8.5)
    box(ax, 10.25, 8.55, 5.1, 1.25, "systemd unit + CloudWatch forwarder", ["journald -> infra/cwlogs_forwarder.py", "structured JSON access lines"], "aws", fs=8.5)

    # pipeline (row 2: y 5.4..8.2, row 3: y 3.45..4.8)
    box(ax, 4.55, 5.4, 3.35, 2.8, "1  Privacy first", ["cv2.FaceDetectorYN (YuNet,", "dnn module) on the frame;", "faces blurred in the copy that", "is drawn, returned and stored.", "No model -> no evidence", "saved (fail closed)."], "cv", fs=8.4)
    box(ax, 8.1, 5.4, 3.9, 2.8, "2  Measure  (measure.py)", ["objdetect aruco.CharucoDetector ->", "calib3d findHomography(RANSAC),", "solvePnP(IPPE) -> px/mm, tilt", "imgproc warpPerspective, remap,", "resize, GaussianBlur, Laplacian,", "morphology, CCL_BBDT, distance-", "Transform, thinning -> width"], "cv", fs=8.4)
    box(ax, 12.2, 5.4, 3.2, 2.8, "3  Quality gate", ["gate.py + gate_params.json", "conformal risk control;", "monotone boosted trees", "(numpy). Per crack:", "certified / indicative /", "refused, reason codes,", "90 % interval"], "ml", fs=8.4)
    box(ax, 4.55, 3.45, 6.0, 1.35, "4  Triage agent  (agent.py)", ["numbers only, never pixels: rules (P1) or Bedrock Converse + forced tool", "choose_action (Amazon Nova Lite); guardrails; rules fallback on any failure"], "agent", fs=8.4)
    box(ax, 10.75, 3.45, 4.65, 1.35, "5  History + escalation", ["history.py: change vs last visit (GUM guard band)", "escalate.py: abandon / widening -> SNS"], "human", fs=8.4)

    # arrows inside
    arrow(ax, (7.9, 6.8), (8.1, 6.8))
    arrow(ax, (12.0, 6.8), (12.2, 6.8))
    arrow(ax, (5.6, 8.55), (5.6, 8.2), lw=1.4)
    arrow(ax, (6.65, 9.15), (6.95, 9.15), lw=1.4)
    arrow(ax, (8.4, 8.55), (8.4, 8.2), lw=1.4)
    # gate -> agent (elbow in the gap between row 2 and row 3)
    ax.plot([13.8, 13.8, 7.5], [5.4, 5.1, 5.1], color=INK, lw=1.6, zorder=4)
    arrow(ax, (7.5, 5.1), (7.5, 4.8))
    arrow(ax, (10.55, 4.1), (10.75, 4.1))
    ax.text(10.6, 5.2, "observation + gate + cracks + history", fontsize=8.3, color=MUTED, ha="center", va="bottom", bbox=dict(fc="#f7fafc", ec="none", pad=1))

    # user <-> caddy
    arrow(ax, (3.3, 8.9), (4.55, 9.15))
    ax.text(3.8, 9.45, "HTTPS"+chr(10)+"photo", fontsize=8, color=MUTED, ha="center")
    arrow(ax, (4.55, 8.7), (3.3, 8.2))
    ax.text(3.8, 7.9, "overlay,"+chr(10)+"tier, next"+chr(10)+"action", fontsize=8, color=MUTED, ha="center", va="top")

    # AWS services on the right
    sx = 16.35
    box(ax, sx, 8.1, 5.15, 1.9, "Amazon Bedrock", ["Converse API, model", "us.amazon.nova-lite-v1:0,", "fallback nova-micro; temperature 0", "cap: 200 LLM decisions / day", "input: the numbers only"], "aws", fs=8.4)
    box(ax, sx, 6.2, 2.5, 1.65, "DynamoDB", ["prohori-traces: every", "step, joint history,", "approvals; TTL 90 d"], "aws", fs=8.0)
    box(ax, sx + 2.65, 6.2, 2.5, 1.65, "S3 (private, SSE)", ["evidence/<session>/", "NNNN.jpg, faces", "already blurred"], "aws", fs=8.0)
    box(ax, sx, 4.1, 2.5, 1.85, "SNS", ["prohori-escalations", "e-mail to an engineer", "with a review link"], "aws", fs=8.0)
    box(ax, sx + 2.65, 4.1, 2.5, 1.85, "CloudWatch", ["Logs (14 d), metric", "filters, dashboard,", "5xx alarm -> SNS"], "aws", fs=8.0)
    box(ax, sx, 1.1, 5.15, 2.7, "Engineer (human approval)", ["opens /api/approve/<token>: sees the joint,", "width +/- interval, change, agent trace;", "a click records \"I have reviewed this\".", "The token goes only into the SNS message", "(never into an API response). The tool gives", "no safety verdict."], "human", fs=8.2)

    # agent -> Bedrock along the gutter under row 3 and right of the EC2 frame
    ax.plot([7.5, 7.5, 15.95, 15.95], [3.45, 3.35, 3.35, 8.4], color="#b7791f", lw=1.8, zorder=4)
    arrow(ax, (15.95, 8.4), (sx, 8.4), color="#b7791f", lw=1.8)
    arrow(ax, (15.4, 4.3), (sx, 4.9), lw=1.4)               # escalation -> SNS
    ax.text(15.7, 4.05, "", fontsize=1)
    arrow(ax, (sx + 1.25, 4.1), (sx + 1.25, 3.8), lw=1.4)   # SNS -> engineer

    # lower strip: infra as code
    ax.add_patch(FancyBboxPatch((4.3, 0.8), 11.3, 2.2, boxstyle="round,pad=0,rounding_size=0.15", fc="#ffffff", ec="#9aa3af", lw=1.2, zorder=1))
    ax.text(4.5, 2.85, "Repeatable deployment (infra/, bash + AWS CLI)", fontsize=10, fontweight="bold", color=INK, va="top")
    ax.text(4.5, 2.45, "up.sh: budget alarm, private S3, DynamoDB, SNS, least-privilege IAM role, security group, EIP, t4g.small\n"
                       "cool_live.sh up | verify | cutover: launch COOL AMI c8g.large, deploy, compare widths + tiers, move the Elastic IP\n"
                       "push.sh: ship committed HEAD (git archive -> S3 -> instance)   rollback_t4g.sh: back to the stock-pip t4g.small\n"
                       "observability.sh: log group, metric filters, dashboard, alarm        state.env: ids of the live resources",
            fontsize=8.5, color=INK, va="top", linespacing=1.45)
    legend(ax, [("cv", "OpenCV 5 stage"), ("ml", "learned gate"), ("agent", "agent"), ("aws", "AWS service"), ("human", "human in the loop")], 0.4, 0.15)
    save(fig, "architecture")


# ============================================================================================ agent workflow
def agent_workflow():
    W, H = 22, 12.2
    fig, ax = canvas(W, H, "PROHORI agent workflow: perception -> decision -> action -> new capture",
                     "OpenCV output changes what the agent does next. The LLM never sees pixels; it sees the numbers OpenCV produced.")
    for x, w, t in ((0.3, 6.6, "PERCEPTION  (OpenCV 5)"), (7.3, 7.2, "DECISION / ORCHESTRATION"), (14.9, 6.9, "ACTION")):
        ax.add_patch(FancyBboxPatch((x, 10.2), w, 0.62, boxstyle="round,pad=0,rounding_size=0.1", fc=INK, ec=INK))
        ax.text(x + w / 2, 10.51, t, color="white", fontsize=12, fontweight="bold", ha="center", va="center")

    box(ax, 0.3, 8.0, 6.6, 1.95, "Capture n  (JPEG from the phone)", ["faces blurred for storage (YuNet);", "ChArUco detect, homography, rectify, locate cracks,", "estimate widths (aruco / calib3d / imgproc)"], "cv", fs=8.8)
    box(ax, 0.3, 4.55, 6.6, 3.2, "Observation  +  per-crack results", ["corners 0-24, px/mm, obliquity (deg), blur variance,", "blur sigma (mm), glare fraction, noise, crack coverage", "per crack: width, 90 % interval, risk ratio, reasons", "", "Gate (conformal risk control, fitted on 2,584", "degraded captures of 21 photo groups):", "tier certified / indicative / refused + reason codes", "e.g. low_resolution, too_few_corners, blurry,", "oblique, glare, noisy, unstable_width, ..."], "cv", fs=8.8)
    box(ax, 0.3, 1.0, 6.6, 3.1, "Reading the tiers (held-out numbers)", ["board not found: px/mm, tilt, glare read 0 = not measured", "certified: about 3 in 100 readings wrong (3.2 %)", "indicative: about 11.5 in 100 wrong, usable with its interval", "refused: no number is endorsed", "", "These numbers are the only input. No pixels reach the model."], "ml", fs=8.8)

    box(ax, 7.3, 7.3, 7.2, 2.65, "Derived by code (agent.py), not by the model", ["failing_checks with the number behind each reason", "all_failures_marginal, crack_measured", "widen_now_allowed (>= 2 failed tries, marginal)", "abandon_now_allowed (4th failed capture)", "history: last 6 steps, prior_indicative_captures"], "agent", fs=8.8)
    box(ax, 7.3, 4.25, 3.4, 2.75, "Policy P1: rules", ["fixed if/else cascade,", "same inputs.", "Always available.", "Fallback for the", "LLM policy."], "agent", fs=8.8)
    box(ax, 11.1, 4.25, 3.4, 2.75, "Policy P2: Bedrock LLM", ["Converse API, Nova Lite,", "temperature 0, forced tool", "choose_action(action,", "instruction, rationale).", "llm is the default policy."], "agent", fs=8.8)
    box(ax, 7.3, 1.0, 7.2, 2.95, "Guardrails (code, after the model answers)", ["an uncertified capture is never accepted; a certified one only accepted", "answer checked against the numbers: values, counts, a number cited", "violation -> one re-ask with the findings", "still wrong: rules action; real-number template sentence", "invalid action / empty text / API error / 200 calls per day -> rules", "instruction <= 140 characters; guardrail record stored in the trace"], "bad", fs=8.8)

    box(ax, 14.9, 7.4, 6.9, 2.55, "Seven actions", ["accept   |   accept_with_widened_uncertainty", "move_closer   (low_resolution, thin crack)", "reshoot_steadier   (blurry, bad outline)", "relight   (glare, noise)", "reposition_marker   (board lost/cropped, tilt, crack out of frame)", "abandon_and_log   (4th failed capture)"], "agent", fs=8.8)
    box(ax, 14.9, 5.0, 6.9, 2.0, "Instruction to the operator", ["one short sentence that names the number,", "e.g. \"Move closer: the board is 2.71 px/mm\"", "shown in the app next to the overlay"], "user", fs=8.8)
    box(ax, 14.9, 2.35, 3.35, 2.25, "Accept", ["certified width +", "90 % interval;", "joint history: change", "vs last visit"], "human", fs=8.6)
    box(ax, 18.45, 2.35, 3.35, 2.25, "Escalate (SNS)", ["abandon_and_log or", "significant widening;", "e-mail to an engineer", "who must approve"], "human", fs=8.6)
    box(ax, 14.9, 0.75, 6.9, 1.35, "Human approval", ["engineer opens /api/approve/<token>, confirms \"reviewed\"", "(opening the link alone never approves)"], "human", fs=8.6)

    # flow
    arrow(ax, (3.6, 8.0), (3.6, 7.75))
    ax.plot([6.9, 7.1, 7.1], [6.2, 6.2, 8.6], color=INK, lw=1.8, zorder=4)
    arrow(ax, (7.1, 8.6), (7.3, 8.6), lw=1.8)
    ax.text(7.0, 6.45, "numbers", fontsize=8, color=MUTED, ha="right", rotation=0)
    arrow(ax, (9.0, 7.3), (9.0, 7.0), lw=1.4)
    arrow(ax, (12.8, 7.3), (12.8, 7.0), lw=1.4)
    arrow(ax, (9.0, 4.25), (9.0, 3.95), lw=1.4)
    arrow(ax, (12.8, 4.25), (12.8, 3.95), lw=1.4)
    arrow(ax, (11.1, 5.6), (10.7, 5.6), lw=1.2, ls="--", color="#b7791f")
    ax.text(10.9, 5.75, "fallback", fontsize=7.5, color="#9c4221", ha="center")
    ax.plot([14.5, 14.7, 14.7], [2.5, 2.5, 8.7], color=INK, lw=1.8, zorder=4)
    arrow(ax, (14.7, 8.7), (14.9, 8.7), lw=1.8)
    arrow(ax, (18.35, 7.4), (18.35, 7.0), lw=1.4)
    arrow(ax, (16.5, 5.0), (16.5, 4.6), lw=1.4)
    arrow(ax, (20.1, 5.0), (20.1, 4.6), lw=1.4)
    arrow(ax, (20.1, 2.35), (20.1, 2.1), lw=1.4)
    # retake loop: right lane, bottom lane, left lane back to capture n
    lane = "#c05621"
    ax.plot([21.8, 22.3, 22.3, -0.2, -0.2], [6.0, 6.0, 0.35, 0.35, 8.95], color=lane, lw=2.2, ls="--", zorder=1)
    arrow(ax, (-0.2, 8.95), (0.3, 8.95), color=lane, lw=2.2)
    ax.text(11.0, 0.42, "retake: capture n+1 (operator follows the instruction; the loop ends at accept or abandon_and_log)",
            fontsize=9.2, color="#9c4221", ha="center", va="bottom", fontweight="bold", zorder=6, bbox=dict(fc="white", ec="none", pad=1.5))
    ax.text(0.3, -0.3, "Observability: every step (observation, gate, decision, rationale, model, tokens, latency) is written to DynamoDB and shown in the app's Agent trace panel; "
                       "a worked trace is in docs/TRACE_EXHIBIT.md.", fontsize=8.8, color=MUTED, va="center")
    save(fig, "agent_workflow")


# ============================================================================================ developer loop
def dev_loop():
    rows = [json.loads(l) for l in open(ROOT / "eval/results/cool_agentloop/trace.jsonl", encoding="utf-8")]
    dec = [str(r.get("decision", "")).lower() for r in rows]
    n_keep = sum(d == "keep" for d in dec[1:])
    n_disc = sum(d == "discard" for d in dec[1:])
    n_other = len(rows) - 1 - n_keep - n_disc
    W, H = 22, 9.4
    fig, ax = canvas(W, H, "Developer-agent loop: Claude Code optimising PROHORI on COOL (Graviton4 c8g.xlarge)",
                     f"{len(rows)} records in eval/results/cool_agentloop/trace.jsonl: reference + {n_keep} kept, {n_disc} discarded, {n_other} other "
                     "(left optional / default kept).  Runtime measurements decide each next change.")
    y = 5.2
    bw, bh, gap = 3.25, 2.55, 0.45
    xs = [0.4 + i * (bw + gap) for i in range(5)]
    spec = [
        ("1  Profile", ["cProfile + per-stage timers on", "85 frames (29 panel photos,", "6 demo photos, 50 renders),", "COOL OpenCV 5.1.0-dev,", "p50 / p95 per frame"], "cv"),
        ("2  Hypothesis", ["agent reads the profile:", "e.g. \"ufunc.reduce is 9.5 %", "of time, 105k calls\" or", "\"the locator starts 22 ms", "after detection ends\""], "agent"),
        ("3  Change", ["one edit in measure.py", "one git commit per idea", "(sparse thinning, bool-mask", "sums, Python threads,", "task order ...)"], "agent"),
        ("4  Bit-exact check", ["all 85 frames: every number", "as float64 hex vs HEAD;", "13 fast-path unit tests;", "guard rails: |dw| <= 0.005 mm,", "no tier flip"], "ml"),
        ("5  Timing", ["interleaved HEAD / new runs", "on the same instance and", "session; 3 repeats for", "anything under 3 %"], "cv"),
    ]
    for x, (t, ls, k) in zip(xs, spec):
        box(ax, x, y, bw, bh, t, ls, k, fs=8.8)
    for i in range(4):
        arrow(ax, (xs[i] + bw, y + bh / 2), (xs[i + 1], y + bh / 2), lw=1.8)
    # decision diamond-ish box
    dx = xs[4] + 0.0
    box(ax, dx, 1.9, bw, 2.55, "6  Keep or discard", ["keep: exact and faster", "discard: not exact, or", "gain below noise / cost", "(reason + numbers in the", "trace)"], "human", fs=8.8)
    arrow(ax, (xs[4] + bw / 2, y), (xs[4] + bw / 2, 4.45), lw=1.8)
    # loop back to profile
    ax.add_patch(FancyArrowPatch((dx, 3.2), (xs[0] + bw / 2, y), connectionstyle="angle3,angleA=180,angleB=-90", arrowstyle="-|>",
                                 mutation_scale=16, color="#c05621", lw=2.0, ls="--", zorder=1))
    ax.text(10.6, 2.95, "next iteration: re-profile the kept tree (\"what is hot now?\")", fontsize=9.5, color="#9c4221", fontweight="bold", ha="center",
            bbox=dict(fc="white", ec="none", pad=1.5))
    # end: deploy
    box(ax, 0.4, 0.3, 10.6, 2.2, "7  When no idea is left: ship the kept tree and run it", ["infra/cool_live.sh verify: POST every demo sample to the old and the new box,", "compare tiers and widths (tolerance 0.005 mm);", "infra/push.sh deploys the committed HEAD to the live COOL c8g.large;", "/health reports opencv 5.1.0-dev, cool: true"], "aws", fs=8.8)
    box(ax, 11.3, 0.3, 8.7, 1.45, "Result (eval/results/cool_agentloop/README.md)", ["end-to-end p50 per frame 186.6 -> 143.1 ms (-23.2 %), 4 OpenCV threads,", "outputs bit-identical on all 85 frames; COOL = pip within 1 % here"], "user", fs=8.8)
    save(fig, "dev_agent_loop")


if __name__ == "__main__":
    import sys
    todo = sys.argv[1:] or ["architecture", "agent_workflow", "dev_loop"]
    for name in todo:
        globals()[name]()
