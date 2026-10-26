"""Prohori triage agent: decides what the phone operator should do next.

DESIGN NOTE (deliberate, and part of the pitch): the LLM NEVER sees pixels.
OpenCV turns each capture into a small numeric *observation* (ChArUco corners
found, blur variance, px/mm, obliquity, glare fraction, ...) and a pass/fail
*certification gate*. This module only forwards those numbers (plus measured
crack widths, with polylines and ground truth stripped) to an Amazon Bedrock
model that must answer through ONE forced tool, ``choose_action``. The chosen
action and the instruction text are what the operator reads next. Every call
returns latency/model/token metadata so the caller can log a full trace.

Policies
  "llm"    Bedrock Converse + forced tool use. Any failure falls back to rules.
  "rules"  P1 baseline: fixed-threshold if/else (also the safety net for "llm").
  "random" P0 baseline: seeded random action (for the ablation).

Guardrail (``validate_decision`` / ``_llm``): every LLM answer is checked by deterministic code before the operator
sees it. The ACTION must obey the hard constraints already written in the prompt and the rules (no accept on an
uncertified capture, widen/abandon only when the flags allow it, glare-hiding-board and obliquity ordering, board lost,
the action must address a failing reason). The INSTRUCTION must not contain a number that disagrees with the
measurements (value and unit), a wrong "N of M cracks certified" count, an "all cracks certified" claim that is false, or a
tier word ("certified"/"indicative") that disagrees with the gate. On a violation the model is asked once more with the
violations listed; if it still violates, the model's action is kept only when the action check passes and the
instruction is replaced by the rules-policy template for that action, filled with the real numbers. The outcome is
returned as ``decision["guardrail"]``.

``decide()`` never raises.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("prohori.agent")

ACTIONS = [
    "accept",
    "accept_with_widened_uncertainty",
    "move_closer",
    "reshoot_steadier",
    "relight",
    "reposition_marker",
    "abandon_and_log",
]

# LEGACY single-feature thresholds (the pre-calibration hand-set gate; mirrors gate.LEGACY). The deployed gate is a
# conformal-risk-controlled model with NO honest single-feature thresholds (eval/results/gate_report.md section 7), so
# the live rules/prompt do not quote these as requirements. They are kept (a) as the severity scale for the five legacy
# reason codes when the gate dict is the legacy one, and (b) because the pre-registered episode simulator
# (episodes.py, tests/test_episodes.py) is defined on them and must not change.
LEGACY_GATE_THRESHOLDS = {
    "min_corners": 8,           # of 24 ChArUco inner corners
    "min_px_per_mm": 8.0,       # rectified scale at the crack
    "min_blur_var": 150.0,      # variance of Laplacian on the board ROI
    "max_obliquity_deg": 45.0,  # camera-to-board-plane tilt
    "max_glare_frac": 0.05,     # fraction of saturated pixels on board/crack ROI
}
GATE_THRESHOLDS = LEGACY_GATE_THRESHOLDS  # name used by episodes.py, eval/agent_ablation.py and the tests

# GUIDANCE (not gate thresholds): px/mm needed before a crack of a given width can pass the deployed gate, taken from
# eval/results/gate_report.md section 7 ("Required px/mm by crack width", default level, other features at good
# values) and mirrored in gate_params.json["required_px_per_mm"]; tests/test_agent.py checks the two agree.
# (upper width bound in mm, px/mm needed). Widths >= the last bound pass at any px/mm in the calibrated 3-30 range
# when the rest of the capture is good. The 0.3 mm row is the krkCMd/D15 recommendation (20 px/mm for a 0.05 mm
# claim): the fitted gate lets 0.3 mm pass only in the best conditions. 0.4 and 0.5 mm both need about 10 in the shipped refit (2026-10-25).
GATE_GUIDANCE_PPM = ((0.35, 20.0), (0.60, 10.0))
GUIDANCE_DEFAULT_PPM = 8.0     # practical target when the crack width is unknown or already wide
GUIDANCE_SOFT_BLUR_VAR = 150.0  # Laplacian variance below this = soft picture (used to tell blur from distance)
GUIDANCE_SOFT_BLUR_SIGMA_MM = 0.2  # edge-spread blur sigma above this (mm on the wall) = soft picture
CERT_RISK_RATIO_FALLBACK = 0.872  # exp(theta) of the default level (theta = -0.137) if gate_params.json is unreadable

# Reason codes the deployed gate can emit (gate.py: REASON_GROUPS + qa_reasons + ood_reasons) plus the two the
# pipeline adds before the gate runs.
GATE_REASON_CODES = (
    "too_few_corners", "low_resolution", "blurry", "oblique", "glare", "noisy", "low_coverage", "unstable_width",
    "mask_blowup", "mask_holes", "mask_fragmented", "low_confidence", "invalid_image",
)
# Short plain-language label per code (used inside operator instructions).
REASON_SHORT = {
    "too_few_corners": "board not fully seen", "low_resolution": "too far for its width", "blurry": "picture is soft",
    "oblique": "angle too steep", "glare": "glare", "noisy": "grainy picture", "low_coverage": "crack partly out of view",
    "unstable_width": "width readings not stable", "mask_blowup": "outline smeared", "mask_holes": "outline has holes",
    "mask_fragmented": "outline broken up", "low_confidence": "not enough confidence", "invalid_image": "unreadable image",
}
MAX_FAILED_ATTEMPTS = 4          # escalate to abandon_and_log at this many failed captures
MARGINAL_FACTOR = 0.20           # "marginal" = within 20% of the threshold
INSTRUCTION_MAX = 140
RATIONALE_MAX = 400

DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_FALLBACK_MODELS = "us.amazon.nova-lite-v1:0"
_MODEL_FALLTHROUGH_CODES = {"AccessDeniedException", "ValidationException", "ResourceNotFoundException"}
READ_TIMEOUT_S = 6
CONNECT_TIMEOUT_S = 3

SYSTEM_PROMPT = f"""You are the triage agent inside Prohori, a handheld concrete-crack measurement tool.
An inspector points a phone at a crack with a printed ChArUco reference board (24 inner corners, known square size) placed beside it. OpenCV rectifies the wall plane using the board and measures crack width in millimetres. You never see the image; you only get numbers computed by OpenCV. Your job: decide the ONE thing the operator should do next, and tell them in one short instruction. Your choice must visibly follow from the numbers.

OBSERVATION FIELDS
- corners / corners_total: ChArUco corners detected out of 24. Few or zero = board hidden, cropped, glared out or too blurry to detect.
- blur_var: variance of the Laplacian (sharpness). Low = motion blur or defocus. blur_sigma_mm (when present): edge blur in mm on the wall.
- px_per_mm: image pixels per millimetre on the wall plane after rectification. Low = too far away. Width precision is roughly 1/px_per_mm.
- obliquity_deg: tilt between the camera axis and the board plane. High = shooting at a steep angle; perspective error grows and effective px/mm along the crack drops.
- glare_frac: fraction of saturated (blown-out) pixels. High = specular reflection that can hide the crack or board corners.
- noise_sigma (when present): picture grain. crack_coverage (when present): share of the crack length that is inside the frame, 1 = all of it.
- crack_px_extent: size of the detected crack in pixels (0/None = no crack found).
- image_w, image_h: frame size.
Values may be null or 0 when OpenCV could not compute them.
- board_found, failing_checks, all_failures_marginal, crack_measured, widen_now_allowed, abandon_now_allowed: derived for you by code, not by OpenCV on pixels. widen_now_allowed and abandon_now_allowed already count the failed attempts for you. failing_checks lists every failed gate reason with the numbers that matter for it. all_failures_marginal is true when the failure is close to passing. crack_measured is true when a crack width was measured.

BOARD NOT FOUND (board_found=false, corners below about 7): OpenCV could not calibrate, so px_per_mm, obliquity_deg and glare_frac are reported as 0. Those zeros mean "not measured", not "fine": glare, a steep angle, a cropped board or blur can each have lost the board, and you cannot tell which from the board numbers. Only blur_var is still informative, and it is then the sharpness of the whole frame: below about 100 the frame itself is blurred.

CERTIFICATION GATE
Each measured crack is certified or flagged on its own. A learned gate (conformal risk control: among certified cracks the width is wrong by more than 10 percent or 0.05 mm in at most about 5 percent) decides, from many numbers at once. There are NO simple per-number thresholds: do not invent one. The capture is certified when at least one crack is certified; flagged cracks still report a width and a wider 90 percent range (interval_mm), but are not certified.
measured_cracks lists per crack: certified, status, reasons, interval_mm, risk_ratio (predicted error over tolerance; certification needs about {CERT_RISK_RATIO_FALLBACK:.2f} or less). gate.reasons lists what would have to improve (for an uncertified capture, those of the best crack):
- too_few_corners: board cropped, hidden or partly seen.
- low_resolution: too far away for the crack's width.
- blurry: soft picture, shake or defocus.
- oblique: shooting at a steep angle.
- glare: blown-out reflections.
- noisy: grainy picture, usually too little light.
- low_coverage: the crack is partly outside the frame.
- unstable_width: the width readings disagree along the crack, usually from blur or too few pixels across a thin crack.
- mask_blowup, mask_holes: the crack outline is smeared or has holes (quality check on the outline).
- mask_fragmented: the crack outline is broken into pieces.
- low_confidence: nothing single to blame, the capture is just worse than the gate has seen certify.
- invalid_image: the frame was unusable, ask for a retake (reposition_marker).
certified=false with an empty reasons list means no crack was detected: use reposition_marker to frame the crack next to the board.
GUIDANCE (rules of thumb from the gate's calibration, not thresholds): wide cracks (0.75 mm and up) can certify at low px/mm if the capture is otherwise good; a 0.4 or 0.5 mm crack needs about 10 px/mm, a 0.3 mm crack about 20 and the best conditions. When a thin crack is flagged and px_per_mm is below that, move_closer is the fix. When blur_var is below {GUIDANCE_SOFT_BLUR_VAR:.0f} the picture is soft: that is a steadiness problem even when the reason is unstable_width or low_confidence.

ACTIONS
- accept: the capture is certified; report the certified width(s) and, if some cracks are flagged, say how many and why. Use ONLY when gate.certified is true.
- accept_with_widened_uncertainty: the failure is only marginal (all_failures_marginal is true), the inspector already retried at least twice (consecutive_failed_attempts_before_this >= 2), and a crack was measured (crack_measured is true). Report the best crack with its wider range, not certified.
- move_closer: fix low px/mm (low_resolution, or unstable_width / low_confidence on a thin crack that is below its px/mm guidance) when the board is otherwise found.
- reshoot_steadier: fix blur or a bad outline (blurry, unstable_width or low_confidence on a soft picture, mask_blowup, mask_holes): brace the phone, wait for focus, tap to focus, hold still.
- relight: fix glare, noise or poor light (tilt/shade the surface, change angle to the light, turn on a light, turn off flash).
- reposition_marker: fix geometry or visibility: board missing, cropped, occluded or too few corners; low_coverage (put the whole crack in frame); mask_fragmented; also obliquity (stand square to the wall so the camera faces the board plane).
- abandon_and_log: give up on this crack and log the failure; use once consecutive_failed_attempts_before_this is {MAX_FAILED_ATTEMPTS - 1} or more (this capture is the {MAX_FAILED_ATTEMPTS}th failure).

RULES
1. Prefer the single action that fixes the dominant failure. Name the number that triggered it in the instruction, e.g. "Move closer: the board is only 3 px/mm, a 0.5 mm crack needs about 10."
2. Compound failures: decide which to fix first, in this order.
   a. Glare that is hiding the board (glare is a reason and corners is below 12): relight first.
   b. Obliquity together with ANY other reason: reposition_marker first. A steep angle lowers px/mm and corner detection, and re-aiming the phone changes the glare and the shake, so fixes made before it are often undone.
   c. Otherwise the reasons are independent: fix the first of glare, blurry, oblique, low_resolution, too_few_corners, low_coverage, noisy, mask_blowup, mask_holes, mask_fragmented, unstable_width, low_confidence that is present.
2a. Board not found (board_found=false): if blur_var is below 100, reshoot_steadier. Otherwise reposition_marker. If last_actions ends with reposition_marker and the board is still not found, try relight, because glare may be hiding the board.
3. Use history. Do not repeat an action that already failed twice in a row; try the next-most-important fix or escalate.
3a. Marginal exit first: if widen_now_allowed is true, choose accept_with_widened_uncertainty. This beats a further retry and beats abandon_and_log.
3b. Otherwise, never choose abandon_and_log unless abandon_now_allowed is true; when it is true, choose abandon_and_log.
4. Never accept an uncertified capture. Never ask for another shot when gate.certified is true: choose accept (even if some cracks are flagged). One exception, rule 4a.
4a. Two tiers: gate.tier is "certified" (strict, about 3 in 100 certified readings wrong), "indicative" (default level: usable with the interval_mm range, more wrong readings) or "refused". gate.certified is true for both certified and indicative. If gate.tier is "indicative", prior_indicative_captures is 0 and gate.tier_reasons is not empty, you MAY choose the one improving action that fixes the first tier_reasons entry (same action mapping as above) to reach a certified reading; the instruction must say the current reading is usable. Otherwise (second indicative capture in a row, or no tier_reasons) choose accept. Never use abandon_and_log or accept_with_widened_uncertainty on a certified or indicative capture.
5. instruction: at most {INSTRUCTION_MAX} characters, plain words, imperative, for someone holding a phone on a ladder. No jargon, no emojis. rationale: one or two sentences for the audit trace, citing the numbers.
Always answer by calling the choose_action tool."""

TOOL_NAME = "choose_action"
TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": TOOL_NAME,
                "description": "Choose the single next action for the phone operator and the instruction they will read.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ACTIONS},
                            "instruction": {
                                "type": "string",
                                "description": f"Max {INSTRUCTION_MAX} chars, imperative, cites the triggering number.",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "1-2 sentences for the audit trace.",
                            },
                        },
                        "required": ["action", "instruction", "rationale"],
                    }
                },
            }
        }
    ],
    "toolChoice": {"tool": {"name": TOOL_NAME}},
}


# --------------------------------------------------------------------------- helpers
def _num(x: Any) -> float | None:
    try:
        if x is None or isinstance(x, bool):
            return None
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _fmt(x: Any, nd: int = 1) -> str:
    v = _num(x)
    if v is None:
        return "?"
    return f"{v:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{v:.0f}"


def _clean_instruction(text: Any) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) <= INSTRUCTION_MAX:
        return s
    cut = s[: INSTRUCTION_MAX - 1]
    if " " in cut[60:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def _gate_reasons(gate: dict | None) -> list[str]:
    return list((gate or {}).get("reasons") or [])


def _certified(gate: dict | None) -> bool:
    return bool((gate or {}).get("certified"))


def _tier(gate: dict | None) -> str | None:
    """Capture-level tier of the two-tier certificate ("certified" | "indicative" | "refused"), None for older gates."""
    return (gate or {}).get("tier")


def _indicative(gate: dict | None) -> bool:
    """Certified at the default level but not at the strict one: usable with the interval shown."""
    return _certified(gate) and _tier(gate) == "indicative"


def prior_indicative(history: list[dict] | None) -> int:
    """Number of trailing history steps whose capture was only "indicative" (one improving retry is enough)."""
    n = 0
    for step in reversed(history or []):
        if not _indicative(step.get("gate")):
            break
        n += 1
    return n


def failed_attempts(history: list[dict] | None) -> int:
    """Number of trailing history steps whose gate was not certified."""
    n = 0
    for step in reversed(history or []):
        if _certified(step.get("gate")):
            break
        n += 1
    return n


def _last_actions(history: list[dict] | None) -> list[str]:
    out = []
    for step in history or []:
        d = step.get("decision") or {}
        if d.get("action"):
            out.append(d["action"])
    return out


def _result(action, instruction, rationale, policy, model, t0, fallback_reason=None, it=None, ot=None) -> dict:
    return {
        "action": action,
        "instruction": _clean_instruction(instruction),
        "rationale": str(rationale or "")[:RATIONALE_MAX],
        "policy": policy,
        "model": model,
        "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        "fallback_reason": fallback_reason,
        "input_tokens": it,
        "output_tokens": ot,
    }


# --------------------------------------------------------------------------- rules (P1)
def _failures(observation: dict, gate: dict) -> dict[str, float]:
    """Failed checks -> normalised severity (0 = at threshold, 1 = 100% past it).

    Uses the gate's reasons as the source of truth, plus the numbers for severity.
    """
    T = GATE_THRESHOLDS
    o = observation or {}
    corners, ppm, blur = _num(o.get("corners")), _num(o.get("px_per_mm")), _num(o.get("blur_var"))
    obl, gl = _num(o.get("obliquity_deg")), _num(o.get("glare_frac"))
    sev: dict[str, float] = {}
    for r in _gate_reasons(gate):
        if r == "too_few_corners":
            sev[r] = 1.0 if not corners else max(0.0, 1 - corners / T["min_corners"])
        elif r == "low_resolution":
            sev[r] = 1.0 if not ppm else max(0.0, 1 - ppm / T["min_px_per_mm"])
        elif r == "blurry":
            sev[r] = 1.0 if blur is None else max(0.0, 1 - blur / T["min_blur_var"])
        elif r == "oblique":
            sev[r] = 0.0 if obl is None else max(0.0, obl / T["max_obliquity_deg"] - 1)
        elif r == "glare":
            sev[r] = 0.0 if gl is None else max(0.0, gl / T["max_glare_frac"] - 1)
        else:
            sev[r] = 0.0
    return sev


def _board_missing(o: dict) -> bool:
    corners, ppm = _num(o.get("corners")), _num(o.get("px_per_mm"))
    return not corners or corners < 4 or not ppm


def _rule_text(reason: str, o: dict) -> tuple[str, str]:
    """(action, instruction) for fixing one failure reason."""
    T = GATE_THRESHOLDS
    if reason == "glare":
        g = _num(o.get("glare_frac"))
        gtxt = "Too much" if g is None else f"{g * 100:.0f}%"
        return "relight", f"Cut the glare: tilt or shade the wall. {gtxt} is blown out, max {T['max_glare_frac'] * 100:.0f}%."
    if reason == "blurry":
        return "reshoot_steadier", f"Hold steady and retake: sharpness is {_fmt(o.get('blur_var'), 0)}, need {T['min_blur_var']:.0f} or more."
    if reason == "oblique":
        return "reposition_marker", f"Stand square to the wall: tilt is {_fmt(o.get('obliquity_deg'), 0)} degrees, max {T['max_obliquity_deg']:.0f}."
    if reason == "low_resolution":
        return "move_closer", f"Move closer: the board is only {_fmt(o.get('px_per_mm'), 1)} px/mm, need {T['min_px_per_mm']:.0f} or more."
    # too_few_corners / unknown
    return "reposition_marker", f"Show the whole board: only {_fmt(o.get('corners'), 0)} of {_fmt(o.get('corners_total') or 24, 0)} corners found."


def _marginal(observation: dict, gate: dict) -> bool:
    sev = _failures(observation, gate)
    return bool(sev) and all(v <= MARGINAL_FACTOR for v in sev.values())


def rules_decide(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    """P1 baseline: fixed-threshold if/else. Same return shape as the LLM policy."""
    t0 = time.perf_counter()
    try:
        return _rules(observation, gate, cracks, history, t0)
    except Exception as e:  # pragma: no cover - last-resort safety
        log.warning("rules_decide failed: %s", e)
        return _result("reposition_marker", "Retake the photo with the whole board in view.",
                       f"Rules error: {e}", "rules", None, t0)


def _rules(observation, gate, cracks, history, t0) -> dict:
    T = GATE_THRESHOLDS
    o = observation or {}
    if _certified(gate):
        w = (cracks or [{}])[0] if cracks else {}
        wtxt = f" Width {_fmt(w.get('width_mm'), 2)} mm." if _num(w.get("width_mm")) is not None else ""
        return _result("accept", f"Capture certified.{wtxt} Move to the next crack.",
                       "All gate checks passed.", "rules", None, t0)

    prior_fails = failed_attempts(history)
    attempts = prior_fails + 1  # including this one
    reasons = _gate_reasons(gate)
    if attempts >= MAX_FAILED_ATTEMPTS:
        return _result("abandon_and_log", f"Stop here and log this crack as not measurable after {attempts} tries.",
                       f"{attempts} consecutive uncertified captures ({', '.join(reasons) or 'unknown'}).", "rules", None, t0)

    if cracks and prior_fails >= 2 and _marginal(o, gate):
        return _result("accept_with_widened_uncertainty", "Close enough: keep this shot, the error bar will be widened.",
                       f"Only marginal gate failures ({', '.join(reasons)}) after {prior_fails} retries; crack measured.",
                       "rules", None, t0)

    if not reasons or reasons == ["invalid_image"]:
        msg = "Frame the crack next to the board and retake: no crack was found." if not reasons else "Retake the photo: the image could not be read."
        return _result("reposition_marker", msg, f"Not certified without a measurable gate failure ({reasons or 'no crack detected'}).", "rules", None, t0)

    # Board not found at all (nothing else is trustworthy): glare can hide it, otherwise move/show the board.
    if _board_missing(o):
        gl = _num(o.get("glare_frac"))
        if gl is not None and gl > T["max_glare_frac"]:
            action, text = _rule_text("glare", o)
        else:
            action, text = ("reposition_marker",
                            f"Board not found: put the whole board beside the crack and retake ({_fmt(o.get('corners'), 0)} of {_fmt(o.get('corners_total') or 24, 0)} corners).")
        return _result(action, text, "Board missing or too few corners to calibrate scale.", "rules", None, t0)

    # Fixed priority: glare > blur > oblique > low_resolution > too_few_corners.
    order = ["glare", "blurry", "oblique", "low_resolution", "too_few_corners"]
    present = [r for r in order if r in reasons] or ["too_few_corners"]
    # Compound glare+oblique: if scale is also low, geometry first.
    if "glare" in present and "oblique" in present and "low_resolution" in present:
        present.remove("oblique")
        present.insert(0, "oblique")
    # Avoid repeating an action that already failed twice in a row.
    acts = _last_actions(history)
    pick = present[0]
    if len(acts) >= 2 and acts[-1] == acts[-2]:
        for r in present:
            if _rule_text(r, o)[0] != acts[-1]:
                pick = r
                break
    action, text = _rule_text(pick, o)
    others = [r for r in present if r != pick]
    why = f"Fixing {pick} first (fixed priority)." + (f" Also failing: {', '.join(others)}." if others else "")
    return _result(action, text, why, "rules", None, t0)


# --------------------------------------------------------------------------- rules for the deployed (CRC) gate
# The legacy functions above are frozen (P1 pre-registration, research/AGENT_PREREG.md). Everything below handles the
# deployed gate dict (mode "crc"/"crc_textured", or "none" when no board was found) and is picked by rules_policy().
_CRC_MODES = ("crc", "crc_textured", "none", "off")
_QA_CODES = ("mask_blowup", "mask_holes", "mask_fragmented")
_CRC_ORDER = ["glare", "blurry", "oblique", "low_resolution", "too_few_corners", "low_coverage", "noisy",
              "mask_blowup", "mask_holes", "mask_fragmented", "unstable_width", "low_confidence"]


def _is_crc(gate: dict | None, cracks: list | None = None) -> bool:
    """True for the deployed gate's dict. Legacy dicts (no mode, or mode "legacy") keep the frozen legacy rules."""
    g = gate or {}
    if g.get("mode") in _CRC_MODES:
        return True
    return g.get("mode") is None and any(isinstance(c, dict) and "risk_ratio" in c for c in cracks or [])


def cert_risk_ratio(gate: dict | None = None) -> float:
    """Risk ratio (predicted error over tolerance) at which the gate certifies: exp(theta) of the active level."""
    try:
        from . import gate as _g
        P = _g.load_params()
        level = (gate or {}).get("level") or P["default_level"]
        return float(math.exp(P["levels"][level]["theta"]))
    except Exception:
        return CERT_RISK_RATIO_FALLBACK


def guidance_ppm(width_mm: Any) -> float | None:
    """px/mm a crack of this width needs to pass the gate (GATE_GUIDANCE_PPM), None for wide cracks (no hard need)."""
    w = _num(width_mm)
    if w is None:
        return None
    for bound, ppm in GATE_GUIDANCE_PPM:
        if w < bound:
            return ppm
    return None


def _best_crack(cracks: list) -> dict | None:
    """The crack the capture-level reasons come from: lowest risk_ratio (as in gate.assess), else the first measured."""
    ok = [c for c in cracks or [] if isinstance(c, dict) and _num(c.get("width_mm")) is not None]
    rr = [c for c in ok if _num(c.get("risk_ratio")) is not None]
    if rr:
        return min(rr, key=lambda c: _num(c["risk_ratio"]))
    return ok[0] if ok else None


def _crack_ppm(o: dict, crack: dict | None) -> float | None:
    return _num((crack or {}).get("px_per_mm")) or _num(o.get("px_per_mm"))


def _is_soft(o: dict) -> bool:
    bv, bs = _num(o.get("blur_var")), _num(o.get("blur_sigma_mm"))
    return (bv is not None and bv < GUIDANCE_SOFT_BLUR_VAR) or (bs is not None and bs > GUIDANCE_SOFT_BLUR_SIGMA_MM)


def _below_guidance(o: dict, crack: dict | None) -> bool:
    need = guidance_ppm((crack or {}).get("width_mm"))
    ppm = _crack_ppm(o, crack)
    return need is not None and ppm is not None and ppm < need


def _crc_marginal(gate: dict, cracks: list, o: dict | None = None) -> bool:
    """Close to certifying: the best crack's risk ratio is within MARGINAL_FACTOR of the certify level, the board was
    found, and the failure is a score failure (outline-QA failures are not "close")."""
    c = _best_crack(cracks)
    reasons = _gate_reasons(gate)
    if c is None or _certified(gate) or not reasons:
        return False
    rr = _num(c.get("risk_ratio"))
    if rr is None or any(r in _QA_CODES or r == "invalid_image" for r in reasons):
        return False
    if o is not None and (o.get("board_found") is False or _board_missing(o)):
        return False
    return rr <= cert_risk_ratio(gate) * (1 + MARGINAL_FACTOR)


def _closer_text(o: dict, crack: dict | None) -> str:
    ppm, w = _crack_ppm(o, crack), _num((crack or {}).get("width_mm"))
    need = guidance_ppm(w)
    if need is not None and w is not None:
        return f"Move closer: only {_fmt(ppm, 1)} px/mm here, a {_fmt(w, 1)} mm crack needs about {need:.0f}."
    return f"Move closer: only {_fmt(ppm, 1)} px/mm here, aim for {GUIDANCE_DEFAULT_PPM:.0f} or more."


def _crc_fix(reason: str, o: dict, crack: dict | None) -> tuple[str, str]:
    """(action, instruction) that fixes one deployed-gate reason code."""
    if reason == "glare":
        g = _num(o.get("glare_frac"))
        return "relight", "Cut the glare: tilt or shade the wall, turn off flash." + ("" if not g else f" {g * 100:.0f}% is blown out.")
    if reason == "noisy":
        return "relight", f"Add light: the picture is grainy (noise {_fmt(o.get('noise_sigma'), 1)}). Turn on a light or avoid deep shade."
    if reason == "blurry":
        return "reshoot_steadier", f"Hold steady and retake: sharpness is {_fmt(o.get('blur_var'), 0)}. Brace the phone, tap to focus."
    if reason == "oblique":
        return "reposition_marker", f"Stand square to the wall: tilt is {_fmt(o.get('obliquity_deg'), 0)} degrees. Face the board straight on."
    if reason == "low_resolution":
        return "move_closer", _closer_text(o, crack)
    if reason == "low_coverage":
        cov = _num(o.get("crack_coverage"))
        return "reposition_marker", "Put the whole crack in the frame" + (f": only {cov * 100:.0f}% of it is visible." if cov is not None else ".")
    if reason in ("mask_blowup", "mask_holes"):
        what = "smeared" if reason == "mask_blowup" else "full of holes"
        return "reshoot_steadier", f"Retake sharper: the crack outline is {what}. Brace the phone, tap to focus."
    if reason == "mask_fragmented":
        return "reposition_marker", "Frame the crack as one clear line next to the board: its outline is broken into pieces."
    if reason == "invalid_image":
        return "reposition_marker", "Retake the photo: the image could not be read."
    if reason in ("unstable_width", "low_confidence"):
        if _is_soft(o):
            return "reshoot_steadier", f"Hold steady and retake: the picture is soft (sharpness {_fmt(o.get('blur_var'), 0)}). Brace the phone, tap to focus."
        if _below_guidance(o, crack) or (reason == "unstable_width" and (_crack_ppm(o, crack) or 0) < GUIDANCE_DEFAULT_PPM):
            return "move_closer", _closer_text(o, crack)
        if reason == "unstable_width":
            return "reshoot_steadier", "Hold steady and retake: the width readings disagree along the crack."
        return "reshoot_steadier", "Retake steadier and square to the wall: this shot is worse than any I can certify."
    # too_few_corners / unknown
    return "reposition_marker", f"Show the whole board: only {_fmt(o.get('corners'), 0)} of {_fmt(o.get('corners_total') or 24, 0)} corners found."


def _crc_pick(reasons: list[str], o: dict) -> list[str]:
    """Reasons ordered by what to fix first (prompt rules 2a-2c)."""
    present = [r for r in _CRC_ORDER if r in reasons] + [r for r in reasons if r not in _CRC_ORDER]
    corners = _num(o.get("corners"))
    if "glare" in reasons and corners is not None and corners < 12:
        present.remove("glare")
        present.insert(0, "glare")
    elif "oblique" in reasons and len(reasons) > 1:
        present.remove("oblique")
        present.insert(0, "oblique")
    return present


def _mm(x: Any) -> str:
    v = _num(x)
    return "?" if v is None else f"{v:.2f}"


def _range_txt(crack: dict | None) -> str:
    iv = (crack or {}).get("interval_mm")
    return f"{_mm(iv[0])} to {_mm(iv[1])}" if isinstance(iv, (list, tuple)) and len(iv) == 2 else ""


def _crc_accept(cracks: list, gate: dict) -> str:
    cert = [c for c in cracks or [] if c.get("certified")]
    n = len(cert) or int(_num(gate.get("cracks_certified")) or 0)
    total = len(cracks or []) or int(_num(gate.get("cracks_total")) or n)
    best = min(cert, key=lambda c: _num(c.get("risk_ratio")) or 0) if cert else _best_crack(cracks)
    w, rng = _num((best or {}).get("width_mm")), _range_txt(best)
    tail = f" Best: {_mm(w)} mm" + (f" (90% range {rng})." if rng else ".") if w is not None else ""
    ind = " Indicative reading: use it with the range." if _indicative(gate) else ""
    return f"Certified {n} of {total} cracks.{tail}{ind} " + ("Flagged ones are marked." if total > n else "Move on.")


def rules_policy(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    """Rule-based policy for whichever gate produced `gate`: the frozen legacy rules (rules_decide) or the CRC rules."""
    if _is_crc(gate, cracks):
        return crc_rules_decide(observation, gate, cracks, history)
    return rules_decide(observation, gate, cracks, history)


def crc_rules_decide(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    t0 = time.perf_counter()
    try:
        return _crc_rules(observation, gate, cracks, history, t0)
    except Exception as e:  # pragma: no cover - last-resort safety
        log.warning("crc_rules_decide failed: %s", e)
        return _result("reposition_marker", "Retake the photo with the whole board in view.",
                       f"Rules error: {e}", "rules", None, t0)


def _crc_rules(observation, gate, cracks, history, t0) -> dict:
    o = observation or {}
    if _indicative(gate) and prior_indicative(history) == 0 and gate.get("tier_reasons"):
        # Two-tier certificate: the capture is usable (indicative) but one improving retake could reach "certified".
        # Offered once; accepting is always fine (the second indicative capture in a row is accepted).
        best = _best_crack(cracks)
        present = _crc_pick(list(gate["tier_reasons"]), o)
        action, text = _crc_fix(present[0], o, best)
        return _result(action, f"Usable as is. For a certified reading: {text}",
                       f"Indicative tier (passes the default level, not the strict one); fixing {present[0]} "
                       f"would move it toward certified. One optional retake, accepting is fine.", "rules", None, t0)
    if _certified(gate):
        return _result("accept", _crc_accept(cracks, gate),
                       f"Gate certified {gate.get('cracks_certified')} of {gate.get('cracks_total')} cracks.", "rules", None, t0)

    prior_fails = failed_attempts(history)
    attempts = prior_fails + 1
    reasons = _gate_reasons(gate)
    best = _best_crack(cracks)

    # Rule 3a: the marginal exit beats a further retry and beats abandon_and_log.
    if cracks and prior_fails >= 2 and _crc_marginal(gate, cracks, o):
        rng = _range_txt(best)
        return _result("accept_with_widened_uncertainty",
                       f"Close enough: keep this shot. Best crack {_mm((best or {}).get('width_mm'))} mm" + (f", range {rng}" if rng else "") + ", not certified.",
                       f"Risk ratio {_fmt((best or {}).get('risk_ratio'), 2)} is within {MARGINAL_FACTOR:.0%} of the certify level "
                       f"{cert_risk_ratio(gate):.2f} after {prior_fails} retries ({', '.join(reasons)}).", "rules", None, t0)

    if attempts >= MAX_FAILED_ATTEMPTS:
        return _result("abandon_and_log", f"Stop here and log this crack as not measurable after {attempts} tries.",
                       f"{attempts} consecutive uncertified captures ({', '.join(reasons) or 'unknown'}).", "rules", None, t0)

    if not reasons:
        return _result("reposition_marker", "Frame the crack next to the board and retake: no crack was found.",
                       "Not certified and no gate reason: no crack detected.", "rules", None, t0)

    acts = _last_actions(history)
    # Rule 2a: board not found. Zeros for ppm/obliquity/glare mean "not measured".
    if reasons == ["invalid_image"]:
        return _result("reposition_marker", "Retake the photo: the image could not be read.", "Image unusable.", "rules", None, t0)
    if o.get("board_found") is False or _board_missing(o):
        bv = _num(o.get("blur_var"))
        if bv is not None and bv < 100:
            action, text = "reshoot_steadier", f"Hold steady and retake: the whole frame is soft (sharpness {_fmt(bv, 0)}) and the board was not found."
        elif acts and acts[-1] == "reposition_marker":
            action, text = "relight", "Still no board: cut glare, tilt or shade the wall, turn off flash. Glare can hide the board."
        else:
            action, text = ("reposition_marker",
                            f"Board not found: put the whole board beside the crack and retake ({_fmt(o.get('corners'), 0)} of {_fmt(o.get('corners_total') or 24, 0)} corners).")
        return _result(action, text, "Board missing or too few corners to calibrate scale.", "rules", None, t0)

    present = _crc_pick(reasons, o)
    pick = present[0]
    if len(acts) >= 2 and acts[-1] == acts[-2]:  # rule 3: do not repeat an action that failed twice in a row
        for r in present:
            if _crc_fix(r, o, best)[0] != acts[-1]:
                pick = r
                break
    action, text = _crc_fix(pick, o, best)
    others = [r for r in present if r != pick]
    rr = _num((best or {}).get("risk_ratio"))
    why = (f"Fixing {pick} ({REASON_SHORT.get(pick, pick)}) first." + (f" Also: {', '.join(others)}." if others else "")
           + (f" Best crack risk ratio {rr:.2f}, certify at {cert_risk_ratio(gate):.2f}." if rr is not None else "")
           + (" The ratio alone would pass; the capture is outside what the gate was calibrated on."
              if rr is not None and rr <= cert_risk_ratio(gate) else ""))
    return _result(action, text, why, "rules", None, t0)


# --------------------------------------------------------------------------- random (P0)
def random_decide(observation: dict, gate: dict, cracks: list, history: list[dict], *, seed: int = 0) -> dict:
    """P0 baseline: seeded random action (deterministic per seed and history length)."""
    t0 = time.perf_counter()
    rng = random.Random(f"{seed}:{len(history or [])}")
    action = rng.choice(ACTIONS)
    return _result(action, f"Random baseline says: {action.replace('_', ' ')}.", "Uniform random action (P0 baseline).",
                   "random", None, t0)


# --------------------------------------------------------------------------- LLM (P2)
_client_lock = threading.Lock()
_client_cache: dict[str, Any] = {}


def _region() -> str:
    return os.environ.get("PROHORI_AWS_REGION", DEFAULT_REGION)


def _get_client():
    """Cached bedrock-runtime client (short timeout, one retry)."""
    region = _region()
    with _client_lock:
        c = _client_cache.get(region)
        if c is None:
            import boto3
            from botocore.config import Config

            c = boto3.client(
                "bedrock-runtime",
                region_name=region,
                config=Config(read_timeout=READ_TIMEOUT_S, connect_timeout=CONNECT_TIMEOUT_S,
                              retries={"max_attempts": 1, "mode": "standard"}),
            )
            _client_cache[region] = c
        return c


def _models() -> list[str]:
    primary = os.environ.get("PROHORI_BEDROCK_MODEL", DEFAULT_MODEL).strip()
    fb = os.environ.get("PROHORI_BEDROCK_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS)
    out = [primary] + [m.strip() for m in fb.split(",") if m.strip()]
    seen, uniq = set(), []
    for m in out:
        if m and m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq


def _obs_for_llm(o: dict, extra: bool = False) -> dict:
    keys = ["corners", "corners_total", "blur_var", "px_per_mm", "obliquity_deg", "glare_frac",
            "crack_px_extent", "image_w", "image_h"]
    out = {}
    if extra:  # the deployed gate also looks at these; only sent when OpenCV produced them
        for k in ("blur_sigma_mm", "noise_sigma", "crack_coverage"):
            n = _num((o or {}).get(k))
            if n is not None:
                out[k] = round(n, 4)
    for k in keys:
        v = (o or {}).get(k)
        if isinstance(v, (list, tuple)):  # raw corner arrays are not for the model; send the count
            v = len(v)
        n = _num(v)
        out[k] = None if n is None else (round(n, 4) if n != int(n) else int(n))
    return out


def _derived_for_llm(observation: dict, gate: dict, cracks: list) -> dict:
    """Deterministic helper numbers so the model does not have to do threshold arithmetic."""
    T = GATE_THRESHOLDS
    o = observation or {}
    board_found = bool(_num(o.get("px_per_mm")))
    d: dict[str, Any] = {"board_found": board_found, "crack_measured": bool(cracks)}
    if _is_crc(gate, cracks):
        return _derived_crc(o, gate, cracks, board_found, d)
    reasons = _gate_reasons(gate)
    checks = []
    if board_found:
        spec = {
            "too_few_corners": ("corners", T["min_corners"], "min"),
            "low_resolution": ("px_per_mm", T["min_px_per_mm"], "min"),
            "blurry": ("blur_var", T["min_blur_var"], "min"),
            "oblique": ("obliquity_deg", T["max_obliquity_deg"], "max"),
            "glare": ("glare_frac", T["max_glare_frac"], "max"),
        }
        for r in reasons:
            if r in spec:
                key, thr, kind = spec[r]
                v = _num(o.get(key))
                if v is None:
                    continue
                past = (1 - v / thr) if kind == "min" else (v / thr - 1)
                checks.append({"check": r, "value": round(v, 4), "threshold": thr, "percent_past_threshold": round(100 * past)})
        d["failing_checks"] = checks
        d["all_failures_marginal"] = bool(checks) and all(c["percent_past_threshold"] <= 100 * MARGINAL_FACTOR for c in checks)
    return d


def _derived_crc(o: dict, gate: dict, cracks: list, board_found: bool, d: dict) -> dict:
    """failing_checks / all_failures_marginal for the deployed gate: one entry per reason code, with the number that
    matters for it; marginal = the best crack's risk_ratio is within MARGINAL_FACTOR of the certify level."""
    best = _best_crack(cracks)
    if not board_found:
        return d
    value_of = {"too_few_corners": "corners", "low_resolution": "px_per_mm", "blurry": "blur_var",
                "oblique": "obliquity_deg", "glare": "glare_frac", "noisy": "noise_sigma", "low_coverage": "crack_coverage"}
    checks = []
    for r in _gate_reasons(gate):
        c = {"check": r, "meaning": REASON_SHORT.get(r, r)}
        k = value_of.get(r)
        if k and _num(o.get(k)) is not None:
            c["value"] = round(_num(o[k]), 4)
        if r == "low_resolution" and best is not None:
            need = guidance_ppm(best.get("width_mm"))
            c["crack_px_per_mm"] = _crack_ppm(o, best)
            c["px_per_mm_guidance"] = need if need is not None else GUIDANCE_DEFAULT_PPM
        checks.append(c)
    d["failing_checks"] = checks
    d["all_failures_marginal"] = _crc_marginal(gate, cracks, o)
    rr = _num((best or {}).get("risk_ratio"))
    if rr is not None:
        cert = cert_risk_ratio(gate)
        d["best_crack_risk_ratio"] = round(rr, 3)
        d["certify_at_risk_ratio"] = round(cert, 3)
        d["percent_past_certify_level"] = round(100 * (rr / cert - 1))
    if best is not None and not _certified(gate):
        d["soft_picture"] = _is_soft(o)
        need = guidance_ppm(best.get("width_mm"))
        if need is not None:
            d["px_per_mm_guidance_for_best_crack"] = {"width_mm": round(_num(best["width_mm"]), 2), "needed": need,
                                                     "crack_px_per_mm": _crack_ppm(o, best)}
    return d


def _attempt_flags(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    n = failed_attempts(history)
    if _is_crc(gate, cracks):
        marginal = bool(cracks) and _crc_marginal(gate, cracks, observation or {})
    else:
        marginal = bool(cracks) and bool(_gate_reasons(gate)) and _marginal(observation, gate) and bool(_num((observation or {}).get("px_per_mm")))
    return {"widen_now_allowed": n >= 2 and marginal and not _certified(gate),
            "abandon_now_allowed": n >= MAX_FAILED_ATTEMPTS - 1 and not _certified(gate)}


def build_user_payload(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    """Everything the LLM gets: numbers only. polyline_px and true_width_mm are stripped."""
    crc = _is_crc(gate, cracks)
    cr = []
    for c in cracks or []:
        keys = ("id", "width_mm", "uncertainty_mm", "length_mm")
        if crc:
            keys += ("px_per_mm", "certified", "status", "reasons", "interval_mm", "risk_ratio", "tier")
        cr.append({k: c.get(k) for k in keys if k in c})
    hist = []
    for i, s in enumerate((history or [])[-6:]):
        d = s.get("decision") or {}
        hist.append({
            "observation": _obs_for_llm(s.get("observation") or {}, crc),
            "gate": {"certified": _certified(s.get("gate")), "reasons": _gate_reasons(s.get("gate"))},
            "action_taken": d.get("action"),
        })
    return {
        "current_capture": {
            "observation": _obs_for_llm(observation, crc),
            "gate": {"certified": _certified(gate), "reasons": _gate_reasons(gate),
                     **({"cracks_certified": gate.get("cracks_certified"), "cracks_total": gate.get("cracks_total")} if crc else {}),
                     **({"tier": gate.get("tier"), "tier_reasons": list(gate.get("tier_reasons") or []),
                         "prior_indicative_captures": prior_indicative(history)} if crc and gate.get("tier") else {})},
            "measured_cracks": cr,
            **_derived_for_llm(observation, gate, cracks),
        },
        "history_oldest_first": hist,
        "consecutive_failed_attempts_before_this": failed_attempts(history),
        **_attempt_flags(observation, gate, cracks, history),
        "last_actions": _last_actions(history)[-4:],
    }


# --------------------------------------------------------------------------- guardrail (deterministic checks on LLM output)
# Everything below is derived from the rule set that already exists in SYSTEM_PROMPT and in the rules policy. It adds no
# new policy: a check is only a hard constraint when the prompt states it as one ("ONLY", "never", "first", "choose").
IMPROVING_ACTIONS = ("move_closer", "reshoot_steadier", "relight", "reposition_marker")
HIDING_CORNERS = 12            # prompt rule 2a: glare is hiding the board below this many corners
BOARD_BLURRED_VAR = 100.0      # prompt rule 2a': whole-frame blur_var below this = the frame itself is blurred

# Which actions fix which gate reason (prompt "ACTIONS" section). unstable_width / low_confidence depend on the picture
# (see _fix_actions).
_REASON_FIXES = {
    "too_few_corners": {"reposition_marker"}, "low_resolution": {"move_closer"}, "blurry": {"reshoot_steadier"},
    "oblique": {"reposition_marker"}, "glare": {"relight"}, "noisy": {"relight"}, "low_coverage": {"reposition_marker"},
    "mask_blowup": {"reshoot_steadier"}, "mask_holes": {"reshoot_steadier"}, "mask_fragmented": {"reposition_marker"},
    "invalid_image": {"reposition_marker"},
}

# Wording an instruction must show for the action it announces (same lists as the ablation's checklist).
ACTION_WORDS = {
    "move_closer": re.compile(r"closer|nearer|approach|forward|step in", re.I),
    "reshoot_steadier": re.compile(r"steady|still|brace|blur|sharp|focus|hold|shake", re.I),
    "relight": re.compile(r"glare|light|shade|tilt|reflect|flash|angle|shadow", re.I),
    "reposition_marker": re.compile(r"board|square|angle|frame|position|centre|center|whole|marker|crack|wall|retake", re.I),
    "accept": re.compile(r"certif|accept|next|good|done|indicative|usable", re.I),
    "accept_with_widened_uncertainty": re.compile(r"widen|error bar|close enough|accept|keep|uncertain|range|not certified", re.I),
    "abandon_and_log": re.compile(r"log|stop|give up|abandon|not measurable|cannot|can't|skip|unable", re.I),
}


def _board_lost(o: dict) -> bool:
    return o.get("board_found") is False or _board_missing(o)


def _fix_actions(reason: str, o: dict, crack: dict | None) -> set[str]:
    """Actions that fix one reason code (prompt ACTIONS section; same split as the rules for the two ambiguous codes)."""
    if reason in _REASON_FIXES:
        return set(_REASON_FIXES[reason])
    if reason in ("unstable_width", "low_confidence"):
        if _is_soft(o):
            return {"reshoot_steadier"}
        if _below_guidance(o, crack) or (reason == "unstable_width" and (_crc_ppm(o, crack) or 0) < GUIDANCE_DEFAULT_PPM):
            return {"move_closer"}
        return {"reshoot_steadier", "move_closer", "reposition_marker"}
    return {"reposition_marker"}  # unknown code: same default as the rules


def check_action(action: str, observation: dict, gate: dict, cracks: list, history: list[dict]) -> list[str]:
    """Violations of the hard constraints in the prompt/rules by `action`. Empty list = acceptable."""
    o, gate, cracks, history = observation or {}, gate or {}, cracks or [], history or []
    v: list[str] = []
    if action not in ACTIONS:
        return [f"action {action!r} is not one of the allowed actions"]
    flags = _attempt_flags(o, gate, cracks, history)
    best = _best_crack(cracks)
    if _certified(gate):  # rule 4 / 4a
        if action == "accept":
            return v
        tr = list(gate.get("tier_reasons") or [])
        if _indicative(gate) and prior_indicative(history) == 0 and tr and action in IMPROVING_ACTIONS:
            first = _crc_pick(tr, o)[0]
            want = _fix_actions(first, o, best)
            if action not in want:
                v.append(f"gate.tier is indicative: the one optional retake must fix the first tier_reasons entry "
                         f"({first}), which means {' or '.join(sorted(want))}, not {action} (rule 4a)")
            return v
        tier = gate.get("tier") or "certified"
        v.append(f"gate.certified is true (tier {tier}): choose accept, not {action} (rule 4 / 4a)")
        return v
    # not certified (tier refused, or a legacy uncertified gate)
    if action == "accept":
        return [f"gate.certified is false (tier {gate.get('tier') or 'refused'}): never choose accept on an uncertified capture (rule 4)"]
    if flags["widen_now_allowed"]:
        if action != "accept_with_widened_uncertainty":
            v.append("widen_now_allowed is true: choose accept_with_widened_uncertainty (rule 3a)")
        return v
    if action == "accept_with_widened_uncertainty":
        return ["widen_now_allowed is false: accept_with_widened_uncertainty needs a marginal failure, at least 2 failed "
                "attempts before this one and a measured crack (rule 3a)"]
    if flags["abandon_now_allowed"]:
        if action != "abandon_and_log":
            v.append(f"abandon_now_allowed is true ({failed_attempts(history)} failed attempts before this one): choose abandon_and_log (rule 3b)")
        return v
    if action == "abandon_and_log":
        return ["abandon_now_allowed is false: never choose abandon_and_log before the 4th failed capture (rule 3b)"]
    reasons = _gate_reasons(gate)
    acts = _last_actions(history)
    if reasons == ["invalid_image"]:
        return [] if action == "reposition_marker" else ["reason invalid_image: ask for a retake with reposition_marker"]
    if _board_lost(o):  # rule 2a' (zeros are "not measured")
        bv = _num(o.get("blur_var"))
        if bv is not None and bv < BOARD_BLURRED_VAR:
            want = "reshoot_steadier"
            why = f"board not found and blur_var {_fmt(bv, 0)} is below {BOARD_BLURRED_VAR:.0f}: the whole frame is blurred"
        elif acts and acts[-1] == "reposition_marker":
            want, why = "relight", "board still not found after reposition_marker: glare may be hiding it"
        else:
            want, why = "reposition_marker", "board not found"
        if action != want:
            v.append(f"{why}: choose {want}, not {action} (rule 2a)")
        return v
    if not reasons:
        return [] if action == "reposition_marker" else ["certified is false with no reasons means no crack was detected: choose reposition_marker"]
    corners = _num(o.get("corners"))
    if "glare" in reasons and corners is not None and corners < HIDING_CORNERS:
        if action != "relight":
            v.append(f"glare is a failing reason and only {_fmt(corners, 0)} corners are found (below {HIDING_CORNERS}): glare is hiding the board, "
                     f"choose relight first, not {action} (rule 2a)")
        return v
    if "oblique" in reasons and len(reasons) > 1:
        if action != "reposition_marker":
            v.append(f"oblique together with another reason ({', '.join(r for r in reasons if r != 'oblique')}): "
                     f"choose reposition_marker first, not {action} (rule 2b)")
        return v
    fixes: set[str] = set()
    for r in reasons:
        fixes |= _fix_actions(r, o, best)
    if action not in fixes:
        v.append(f"{action} fixes none of the failing reasons ({', '.join(reasons)}); allowed: {', '.join(sorted(fixes))}")
    return v


# ---- instruction checks
_WORDNUM = {"zero": 0, "no": 0, "none": 0, "one": 1, "two": 2, "both": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUMW = r"(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)")
_UNIT_AFTER = [
    ("ppm", re.compile(r"^\s*(px\s*/\s*mm|px\s+per\s+mm|pixels?\s+per\s+(?:mm|millimet\w+)|px\s*/\s*millimet\w+)", re.I)),
    ("advice", re.compile(r"^\s*(seconds?|secs?|s\b|ms\b|minutes?|mins?|cm\b|centimet\w+|metres?|meters?|m\b|feet|ft\b|foot|inch\w*|steps?|paces?)", re.I)),
    ("px", re.compile(r"^\s*(px|pixels?)\b", re.I)),
    ("mm", re.compile(r"^\s*(mm|millimet\w+)", re.I)),
    ("pct", re.compile(r"^\s*(%|percent|per\s*cent)", re.I)),
    ("deg", re.compile(r"^\s*(°|degrees?|deg\b)", re.I)),
    ("corners", re.compile(r"^\s*(?:of\s+\d+\s+)?corners?", re.I)),
    ("attempts", re.compile(r"^\s*(?:more\s+)?(tries|try|attempts?|captures?|shots?|retakes?|retries|photos?|times|failures?|failed)\b", re.I)),
    ("cracks", re.compile(r"^\s*(?:measured\s+)?cracks?\b", re.I)),
    ("ordinal", re.compile(r"^(st|nd|rd|th)\b", re.I)),
]
_UNIT_BEFORE = [
    ("blur", re.compile(r"(sharpness|blur\w*|focus)\W+(?:\w+\W+){0,2}$", re.I)),
    ("deg", re.compile(r"(tilt|angle|obliquity)\W+(?:\w+\W+){0,2}$", re.I)),
    ("noise", re.compile(r"(noise|grain\w*)\W+(?:\w+\W+){0,2}$", re.I)),
    ("ratio", re.compile(r"(ratio)\W+(?:\w+\W+){0,2}$", re.I)),
]
_LIMIT_BEFORE = re.compile(r"\b(need\w*|max\w*|min\w*|limit|at least|above|below|under|over|threshold|aim for|target|up to)\W+(?:about\W+|around\W+)?$", re.I)
# "certified" used as a purpose, a negation or a condition is not a claim that the capture IS certified
_CERT_NEG = re.compile(r"(\bnot|n't|\bnever|\bcannot|\bwithout|\buntil|\bbefore|\bto reach|\bto get|\bto be|\bto become|\bto make|\bfor a|\bfor the|"
                       r"\breach(?:ing)?|\bget(?:ting)? a|\btoward|\bso (?:it|the|this)|\bwould be|\bif\b|\bcould be|\bcan be|\bmay be|\bmight be|\bwill be|"
                       r"\bbecome|\bbecomes|\bwhen)\W+(?:\w+\W+){0,3}$", re.I)


def _wn(tok: str) -> int | None:
    tok = tok.lower()
    return int(tok) if tok.isdigit() else _WORDNUM.get(tok)


def _decimals(tok: str) -> int:
    t = tok.replace(",", "")
    return len(t.split(".")[1]) if "." in t else 0


def _matches(tok: str, values) -> bool:
    """True when the cited number equals a value rounded (or truncated) to the number of decimals it was written with."""
    d = _decimals(tok)
    q = 10 ** d
    xi = round(float(tok.replace(",", "")) * q)
    for val in values:
        a = val * q
        if xi in (math.floor(a + 0.5 + 1e-9), math.floor(a + 1e-9)):
            return True
    return False


def _counts(gate: dict, cracks: list) -> tuple[int, int]:
    """(certified cracks, total cracks) as the gate/cracks report them."""
    g = gate or {}
    tot = _num(g.get("cracks_total"))
    cer = _num(g.get("cracks_certified"))
    if tot is None:
        tot = len(cracks or [])
    if cer is None:
        if any("certified" in c for c in cracks or [] if isinstance(c, dict)):
            cer = sum(1 for c in cracks if isinstance(c, dict) and c.get("certified"))
        else:
            cer = tot if _certified(g) else 0
    return int(cer), int(tot)


_UNIT_OF_CHECK = {"too_few_corners": "corners", "low_resolution": "ppm", "blurry": "blur", "oblique": "deg", "glare": "pct",
                  "noisy": "noise", "low_coverage": "pct"}
_UNITS = ("ppm", "mm", "pct", "deg", "corners", "blur", "noise", "px", "ratio", "attempts", "cracks")
_UNIT_LABEL = {"ppm": "px/mm", "mm": "mm", "pct": "percent", "deg": "degrees", "corners": "corners", "blur": "sharpness",
               "noise": "noise", "px": "pixels", "ratio": "risk ratio", "attempts": "attempts", "cracks": "cracks"}


def value_pool(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict[str, dict[str, list[float]]]:
    """Every number the model could legitimately cite, by unit: {"unit": {"m": measured, "c": constants}}.

    "m" = measured, or derived from this capture/history (what counts as "cites a measured number"); "c" = constants that
    appear in the prompt (thresholds, guidance table, caps)."""
    o, gate, cracks, history = observation or {}, gate or {}, cracks or [], history or []
    crc = _is_crc(gate, cracks)
    P = {u: {"m": [], "c": []} for u in _UNITS}

    def add(u, x, kind="m", scale=1.0):
        n = _num(x)
        if n is not None:
            P[u][kind].append(n * scale)

    obs_all = [o] + [(s or {}).get("observation") or {} for s in history]
    for ob in obs_all:
        add("ppm", ob.get("px_per_mm"))
        add("deg", ob.get("obliquity_deg"))
        add("pct", ob.get("glare_frac"), scale=100.0)
        add("pct", ob.get("crack_coverage"), scale=100.0)
        add("corners", ob.get("corners"))
        add("corners", ob.get("corners_total"))
        add("blur", ob.get("blur_var"))
        add("noise", ob.get("noise_sigma"))
        add("mm", ob.get("blur_sigma_mm"))
        add("px", ob.get("crack_px_extent"))
        add("px", ob.get("image_w"))
        add("px", ob.get("image_h"))
    for cl in [cracks] + [(s or {}).get("cracks") or [] for s in history]:
        for c in cl:
            if not isinstance(c, dict):
                continue
            for k in ("width_mm", "uncertainty_mm", "length_mm"):
                add("mm", c.get(k))
            iv = c.get("interval_mm")
            if isinstance(iv, (list, tuple)):
                for x in iv:
                    add("mm", x)
            add("ppm", c.get("px_per_mm"))
            add("ratio", c.get("risk_ratio"))
    cer, tot = _counts(gate, cracks)
    for x in (cer, tot, tot - cer):
        add("cracks", x)
    n_prior = failed_attempts(history)
    for x in (n_prior, n_prior + 1):
        add("attempts", x)
    # derived helper numbers the model was shown (failing_checks, percent past the certify level, ...)
    try:
        d = _derived_for_llm(o, gate, cracks)
    except Exception:  # pragma: no cover - defensive
        d = {}
    for c in d.get("failing_checks") or []:
        u = _UNIT_OF_CHECK.get(c.get("check"))
        if u and c.get("value") is not None:
            add(u, c["value"], scale=100.0 if u == "pct" else 1.0)
        add("pct", c.get("percent_past_threshold"))
        add("ppm", c.get("crack_px_per_mm"))
        add("ppm", c.get("px_per_mm_guidance"), "c")
    add("pct", d.get("percent_past_certify_level"))
    add("ratio", d.get("best_crack_risk_ratio"))
    add("ratio", d.get("certify_at_risk_ratio"))
    g = d.get("px_per_mm_guidance_for_best_crack") or {}
    add("ppm", g.get("crack_px_per_mm"))
    add("mm", g.get("width_mm"))
    # constants that appear in the prompt
    for c in cracks:
        if isinstance(c, dict):
            need = guidance_ppm(c.get("width_mm"))
            if need is not None:
                add("ppm", need, "c")
    add("ppm", GUIDANCE_DEFAULT_PPM, "c")
    add("pct", 90, "c")                       # "90 percent range"
    add("mm", 0.05, "c")                      # gate tolerance, quoted in the prompt
    add("corners", 24, "c")
    add("corners", 7, "c")
    add("corners", HIDING_CORNERS, "c")
    add("blur", BOARD_BLURRED_VAR, "c")
    add("blur", GUIDANCE_SOFT_BLUR_VAR, "c")
    add("attempts", MAX_FAILED_ATTEMPTS, "c")
    add("ratio", cert_risk_ratio(gate), "c")
    if not crc:
        T = GATE_THRESHOLDS
        add("ppm", T["min_px_per_mm"], "c")
        add("deg", T["max_obliquity_deg"], "c")
        add("pct", T["max_glare_frac"], "c", scale=100.0)
        add("corners", T["min_corners"], "c")
        add("blur", T["min_blur_var"], "c")
    return P


def _unit_for(text: str, m: re.Match) -> str | None:
    after = text[m.end(): m.end() + 24]
    for u, rx in _UNIT_AFTER:
        if rx.match(after):
            return u
    before = text[max(0, m.start() - 28): m.start()]
    for u, rx in _UNIT_BEFORE:
        if rx.search(before):
            return u
    return None


def _count_claim_violations(text: str, gate: dict, cracks: list) -> tuple[list[str], list[tuple[int, int]]]:
    """Checks "N of M cracks ...", "Certified N of M", "all cracks certified", "no cracks certified". Returns the
    violations and the character spans they cover (so the number scan does not look at them again)."""
    cer, tot = _counts(gate, cracks)
    flg = tot - cer
    v: list[str] = []
    spans: list[tuple[int, int]] = []

    def covered(pos: int) -> bool:
        return any(a <= pos < b for a, b in spans)

    def neg_before(pos: int) -> bool:
        return bool(re.search(r"(\bnot|n't)\s+$", text[max(0, pos - 12): pos], re.I))

    for m in re.finditer(rf"\b(certified|flagged)\s+{_NUMW}\s+of\s+{_NUMW}\b(?:\s+(?:measured\s+)?cracks?)?", text, re.I):
        kind, n, mm_ = m.group(1).lower(), _wn(m.group(2)), _wn(m.group(3))
        spans.append(m.span())
        if mm_ is not None and mm_ != tot:
            v.append(f"says {m.group(0)!r} but the gate reports {tot} cracks")
        want = cer if kind == "certified" else flg
        if n is not None and n != want:
            v.append(f"says {m.group(0)!r} but {want} of {tot} cracks are {kind}")
    for m in re.finditer(rf"\b{_NUMW}\s+of\s+(?:the\s+)?{_NUMW}\s+(?:measured\s+)?cracks?\b(?:\s+(?:are|were|is|was|got|have|have been)?\s*(not certified|uncertified|certified|flagged|passed|pass))?", text, re.I):
        if covered(m.start()):
            continue
        spans.append(m.span())
        n, mm_, kind = _wn(m.group(1)), _wn(m.group(2)), (m.group(3) or "").lower()
        if mm_ is not None and mm_ != tot:
            v.append(f"says {m.group(0)!r} but the gate reports {tot} cracks")
        if n is None:
            continue
        if kind in ("certified", "passed", "pass"):
            want, nm = cer, "certified"
        elif kind in ("flagged", "not certified", "uncertified"):
            want, nm = flg, "flagged"
        else:
            want, nm = None, ""
        if want is not None and n != want:
            v.append(f"says {m.group(0)!r} but {want} of {tot} cracks are {nm}")
        elif want is None and n not in (cer, flg, tot):
            v.append(f"says {m.group(0)!r} but {cer} of {tot} cracks are certified")
    for m in re.finditer(r"\b(all|every|both|each)\b(?:\s+(?:of\s+)?the)?(?:\s+" + _NUMW + r")?\s+cracks?\b[^.;:]{0,30}?\b(certified|flagged|passed|pass|uncertified)\b", text, re.I):
        if covered(m.start()):
            continue
        spans.append(m.span())
        quant, kind = m.group(1).lower(), m.group(3).lower()
        holds = (cer == 0 and tot > 0) if kind in ("flagged", "uncertified") else (cer == tot and tot > 0)
        if neg_before(m.start()):
            holds = not holds
        if quant == "both" and tot != 2:
            holds = False
        if not holds:
            v.append(f"says {m.group(0)!r} but {cer} of {tot} cracks are certified")
    for m in re.finditer(r"\b(no|none of the|zero)\s+cracks?\s+(?:are |were |was |is |got |have been )?(certified|passed)\b", text, re.I):
        if covered(m.start()):
            continue
        spans.append(m.span())
        if cer != 0:
            v.append(f"says {m.group(0)!r} but {cer} of {tot} cracks are certified")
    return v, spans


def _tier_claim_violations(text: str, gate: dict, skip: list[tuple[int, int]] | None = None) -> list[str]:
    """The words 'certified' / 'indicative' / 'usable' must agree with gate.tier (or gate.certified for a legacy gate)."""
    certified = _certified(gate)
    tier = _tier(gate) or ("certified" if certified else "refused")
    v: list[str] = []
    positive = 0
    for m in re.finditer(r"\bcertified\b", text, re.I):
        before = text[max(0, m.start() - 40): m.start()]
        if _CERT_NEG.search(before):
            continue
        positive += 1
    if positive and not certified:
        v.append(f"calls the capture certified but gate.certified is false (tier {tier})")
    elif positive and tier == "indicative" and not re.search(r"indicative|usable|strict|range|interval", text, re.I):
        v.append("calls an indicative capture certified without saying it is indicative (gate.tier is indicative, not certified)")
    if re.search(r"\bindicative\b", text, re.I) and tier != "indicative":
        v.append(f"says indicative but gate.tier is {tier}")
    if re.search(r"\b(usable as is|usable as-is|already usable)\b", text, re.I) and not certified:
        v.append(f"says the reading is usable but gate.certified is false (tier {tier})")
    if tier == "certified" and re.search(r"\b(not certified|uncertified|refused)\b", text, re.I):
        v.append("says the capture is not certified but gate.tier is certified")
    return v


def check_instruction(action: str, instruction: str, observation: dict, gate: dict, cracks: list,
                      history: list[dict]) -> tuple[list[str], dict]:
    """(violations, stats) for the operator-facing text. stats: numbers cited, how many matched a measured value."""
    text = str(instruction or "")
    o, gate, cracks, history = observation or {}, gate or {}, cracks or [], history or []
    v: list[str] = []
    cv, spans = _count_claim_violations(text, gate, cracks)
    v += cv
    v += _tier_claim_violations(text, gate, spans)
    P = value_pool(o, gate, cracks, history)
    union_m = [x for u in P.values() for x in u["m"]]
    union_c = [x for u in P.values() for x in u["c"]]
    cited = measured = 0
    prev_unit, prev_end = None, 0
    for m in _NUM_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            cited += 1
            measured += 1  # a "N of M cracks" count that passed the count check is a measured number
            continue
        tok = m.group(1)
        unit = _unit_for(text, m)
        if (unit is None and prev_unit and not re.search(r"[.;:!?]\s", text[prev_end:m.start()])
                and _LIMIT_BEFORE.search(text[max(0, m.start() - 24): m.start()])):
            # "only 6 px/mm, need 8 or more": the limit is in the unit of the value before it;
            # "a 0.5 mm crack needs about 10": what a crack width needs is a scale
            unit = "ppm" if prev_unit == "mm" else prev_unit
        prev_unit, prev_end = unit, m.end()
        if unit == "advice":
            continue  # "hold still for 2 seconds": advice, not a measurement
        cited += 1
        if unit == "ordinal":
            unit = "attempts"
        strict = unit == "corners" and re.match(r"\s+of\s+\d+\s+corners?", text[m.end(): m.end() + 24], re.I)
        if unit in P:
            ms, cs, label = P[unit]["m"], ([] if strict else P[unit]["c"]), _UNIT_LABEL[unit]
        else:
            ms, cs, label = union_m, union_c, ""
        if _matches(tok, ms):
            measured += 1
        elif not _matches(tok, cs):
            known = ", ".join(f"{x:g}" for x in sorted({round(x, 2) for x in ms})[:6]) or "none"
            v.append(f"cites {tok}{' ' + label if label else ''} but no such value was measured or defined "
                     f"(known {label or 'measured'} values: {known})")
    if measured == 0:  # prompt rule 1: "Name the number that triggered it in the instruction"
        v.append("cites no measured number: rule 1 says to name the measured number that triggered the action")
    w = ACTION_WORDS.get(action)
    if w is not None and not w.search(text):
        v.append(f"the instruction does not describe the chosen action {action}")
    seen, out = set(), []
    for x in v:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out, {"numbers": cited, "measured": measured}


def validate_decision(action: str, instruction: str, observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    """{"action": [...], "instruction": [...], "numbers": n, "measured": k}; both lists empty = the decision is faithful."""
    av = check_action(action, observation, gate, cracks, history)
    iv, st = check_instruction(action, instruction, observation, gate, cracks, history)
    return {"action": av, "instruction": iv, **st}


def is_faithful(action: str, instruction: str, observation: dict, gate: dict, cracks: list, history: list[dict]) -> bool:
    """The ablation's "instruction faithfulness": cites at least one measured number AND has zero instruction violations."""
    iv, st = check_instruction(action, instruction, observation, gate, cracks, history)
    return not iv and st["measured"] >= 1


# ---- rules-policy template text for a given action (used when the model's instruction cannot be repaired)
def _legacy_accept(cracks: list) -> str:
    w = (cracks or [{}])[0] if cracks else {}
    wtxt = f" Width {_fmt(w.get('width_mm'), 2)} mm." if _num(w.get("width_mm")) is not None else ""
    return f"Capture certified.{wtxt} Move to the next crack."


def _board_lost_text(action: str, o: dict) -> str:
    c, tot = _fmt(o.get("corners"), 0), _fmt(o.get("corners_total") or 24, 0)
    if action == "reshoot_steadier":
        return f"Hold steady and retake: the whole frame is soft (sharpness {_fmt(o.get('blur_var'), 0)}) and the board was not found."
    if action == "relight":
        return "Still no board: cut glare, tilt or shade the wall, turn off flash. Glare can hide the board."
    return f"Board not found: put the whole board beside the crack and retake ({c} of {tot} corners)."


def template_instruction(action: str, observation: dict, gate: dict, cracks: list, history: list[dict]) -> str:
    """The rules policy's wording for `action`, filled with this capture's real numbers (always at least one)."""
    text = _template_text(action, observation, gate, cracks, history)
    if not re.search(r"\d", text):
        o = observation or {}
        text += f" ({_fmt(o.get('corners'), 0)} of {_fmt(o.get('corners_total') or 24, 0)} corners seen.)"
    return text


def _template_text(action: str, observation: dict, gate: dict, cracks: list, history: list[dict]) -> str:
    o, gate, cracks, history = observation or {}, gate or {}, cracks or [], history or []
    crc = _is_crc(gate, cracks)
    best = _best_crack(cracks)
    if action == "accept":
        return _crc_accept(cracks, gate) if crc else _legacy_accept(cracks)
    if action == "accept_with_widened_uncertainty":
        if crc and best is not None:
            rng = _range_txt(best)
            return f"Close enough: keep this shot. Best crack {_mm(best.get('width_mm'))} mm" + (f", range {rng}" if rng else "") + ", not certified."
        w = _num(best.get("width_mm")) if best else _num((cracks[0] if cracks else {}).get("width_mm"))
        return ("Close enough: keep this shot, the error bar will be widened." if w is None
                else f"Close enough: keep this shot. Best crack {_mm(w)} mm, the error bar will be widened.")
    if action == "abandon_and_log":
        return f"Stop here and log this crack as not measurable after {failed_attempts(history) + 1} tries."
    reasons = _gate_reasons(gate)
    if _certified(gate):  # the optional improving retake on an indicative capture
        tr = list(gate.get("tier_reasons") or [])
        if tr:
            return "Usable as is. For a certified reading: " + _crc_fix(_crc_pick(tr, o)[0], o, best)[1]
    if _board_lost(o) and reasons != ["invalid_image"]:
        return _board_lost_text(action, o)
    if not reasons:
        return "Frame the crack next to the board and retake: no crack was found."
    if crc:
        pool = _crc_pick(reasons, o)
    else:
        pool = [r for r in ("glare", "blurry", "oblique", "low_resolution", "too_few_corners") if r in reasons] or ["too_few_corners"]
    for r in pool:
        a, t = _crc_fix(r, o, best) if crc else _rule_text(r, o)
        if a == action:
            return t
    # no failing reason maps to this action: neutral wording with the relevant real number
    if action == "move_closer":
        return _closer_text(o, best)
    if action == "reshoot_steadier":
        return f"Hold steady and retake: sharpness is {_fmt(o.get('blur_var'), 0)}. Brace the phone, tap to focus."
    if action == "relight":
        return "Cut the glare: tilt or shade the wall, turn off flash."
    return f"Show the whole board: only {_fmt(o.get('corners'), 0)} of {_fmt(o.get('corners_total') or 24, 0)} corners found."


def guardrail_enabled() -> bool:
    return os.environ.get("PROHORI_GUARDRAIL", "1").strip().lower() not in ("0", "false", "off", "no")


def _reask_text(violations: list[str]) -> str:
    return ("Your previous answer broke these checks, which code runs on every answer:\n- " + "\n- ".join(violations[:8])
            + "\nAnswer again with the choose_action tool. Keep the rules in the system prompt. Every number in the instruction "
              "must be copied from the data above, and any statement about how many cracks are certified must match the data.")


class GuardrailReject(ValueError):
    """The model's action failed the action check and could not be fixed: the caller falls back to the rules policy."""

    def __init__(self, msg: str, guardrail: dict):
        super().__init__(msg)
        self.guardrail = guardrail


def _extract_tool_use(resp: dict) -> tuple[dict, int | None, int | None]:
    for block in (resp.get("output", {}).get("message", {}).get("content") or []):
        tu = block.get("toolUse")
        if tu and tu.get("name") == TOOL_NAME:
            usage = resp.get("usage") or {}
            return tu.get("input") or {}, usage.get("inputTokens"), usage.get("outputTokens")
    raise ValueError("no choose_action toolUse block in response")


def _converse(client, model: str, system: str, messages: list) -> dict:
    return client.converse(
        modelId=model,
        system=[{"text": system}],
        messages=messages,
        inferenceConfig={"maxTokens": 400, "temperature": 0.0},
        toolConfig=TOOL_CONFIG,
    )


def _parse_answer(resp: dict) -> tuple[str, str, str, int | None, int | None]:
    args, it, ot = _extract_tool_use(resp)
    action = args.get("action")
    if action not in ACTIONS:
        raise ValueError(f"invalid action from model: {action!r}")
    instruction = _clean_instruction(args.get("instruction"))
    if not instruction:
        raise ValueError("empty instruction from model")
    return action, instruction, str(args.get("rationale") or ""), it, ot


def _add(a, b):
    return b if a is None else (a if b is None else a + b)


def _llm(observation, gate, cracks, history, t0, guardrail: bool | None = None) -> dict:
    client = _get_client()
    payload = build_user_payload(observation, gate, cracks, history)
    user_text = json.dumps(payload, separators=(",", ":"))
    messages = [{"role": "user", "content": [{"text": user_text}]}]
    use_guard = guardrail_enabled() if guardrail is None else bool(guardrail)
    last_err: Exception | None = None
    for model in _models():
        try:
            resp = _converse(client, model, SYSTEM_PROMPT, messages)
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code") if hasattr(e, "response") else None
            last_err = e
            if code in _MODEL_FALLTHROUGH_CODES:
                log.warning("model %s unavailable (%s); trying next", model, code)
                continue
            raise
        action, instruction, rationale, it, ot = _parse_answer(resp)
        calls = 1
        gr = None
        if use_guard:
            val = validate_decision(action, instruction, observation, gate, cracks, history)
            viol = val["action"] + val["instruction"]
            gr = {"violations": viol, "reask": False, "final_violations": viol, "repaired": False,
                  "action_rejected": False, "rationale_withheld": False}
            if viol:
                gr["reask"] = True
                prev = json.dumps({"action": action, "instruction": instruction, "rationale": rationale}, separators=(",", ":"))
                messages2 = messages + [{"role": "assistant", "content": [{"text": prev}]},
                                        {"role": "user", "content": [{"text": _reask_text(viol)}]}]
                try:
                    resp2 = _converse(client, model, SYSTEM_PROMPT, messages2)
                    a2, i2, r2, it2, ot2 = _parse_answer(resp2)
                    calls += 1
                    it, ot = _add(it, it2), _add(ot, ot2)
                    action, instruction, rationale = a2, i2, r2
                    val = validate_decision(action, instruction, observation, gate, cracks, history)
                except Exception as e:  # the re-ask failed: judge the first answer as it stands
                    gr["reask_error"] = f"{type(e).__name__}: {e}"[:120]
                gr["final_violations"] = val["action"] + val["instruction"]
                if val["action"]:
                    gr["action_rejected"] = True
                    raise GuardrailReject("guard: " + "; ".join(val["action"])[:250], gr)
                if val["instruction"]:
                    instruction = template_instruction(action, observation, gate, cracks, history)
                    gr["repaired"] = True
            riv, _ = check_instruction(None, rationale, observation, gate, cracks, history)  # type: ignore[arg-type]
            riv = [x for x in riv if not x.startswith("cites no measured number")]   # a rationale may be number-free
            if riv:
                rationale = "Model rationale withheld: it cited values that do not match the measurements."
                gr["rationale_withheld"] = True
        else:
            bad = check_action(action, observation, gate, cracks, history)
            cert = _certified(gate)
            if (cert and action != "accept" and bad) or (not cert and action == "accept"):
                raise ValueError("guard: " + "; ".join(bad)[:250])
        r = _result(action, instruction, rationale, "llm", model, t0, None, it, ot)
        r["llm_calls"] = calls
        if gr is not None:
            r["guardrail"] = gr
        return r
    raise last_err or RuntimeError("no Bedrock model configured")


def _llm_budget_ok() -> bool:
    """Hard cost cap: at most PROHORI_LLM_DAILY_CAP Bedrock decisions per UTC day.

    The counter is a file shared by all server workers (one byte appended per call).
    """
    cap = int(os.environ.get("PROHORI_LLM_DAILY_CAP", "200"))
    if cap <= 0:
        return False
    try:
        root = Path(os.environ.get("PROHORI_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
        f = root / "llm_calls" / time.strftime("%Y%m%d.cnt", time.gmtime())
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size >= cap:
            return False
        with open(f, "ab") as fh:
            fh.write(b".")
        return True
    except OSError:
        return True


def decide(observation: dict, gate: dict, cracks: list, history: list[dict], *, policy: str = "llm",
           guardrail: bool | None = None) -> dict:
    """Pick the next operator action. Never raises.

    policy "llm" -> Bedrock tool-use agent (falls back to rules on any failure);
    "rules" -> fixed-threshold baseline; "random" -> seeded random baseline.
    The model only ever sees the numeric observation, never the image.
    """
    t0 = time.perf_counter()
    history = history or []
    cracks = cracks or []
    observation = observation or {}
    gate = gate or {}
    try:
        if policy == "rules":
            return rules_policy(observation, gate, cracks, history)
        if policy == "random":
            return random_decide(observation, gate, cracks, history)
        if policy != "llm":
            r = rules_policy(observation, gate, cracks, history)
            r["fallback_reason"] = f"unknown policy {policy!r}"
            return r
        if not _llm_budget_ok():
            r = rules_policy(observation, gate, cracks, history)
            r["fallback_reason"] = "daily LLM call cap reached"
            return r
        try:
            return _llm(observation, gate, cracks, history, t0, guardrail)
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"[:300]
            log.warning("LLM policy failed, using rules: %s", reason)
            r = rules_policy(observation, gate, cracks, history)
            r["fallback_reason"] = reason
            if getattr(e, "guardrail", None):
                r["guardrail"] = e.guardrail
            r["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            return r
    except Exception as e:  # absolute last resort
        return _result("reposition_marker", "Retake the photo with the whole board in view.",
                       f"decide() internal error: {e}", "rules", None, t0, f"internal: {e}"[:300])
