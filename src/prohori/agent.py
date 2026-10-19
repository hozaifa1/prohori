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

``decide()`` never raises.
"""
from __future__ import annotations

import json
import logging
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

# Certification-gate thresholds. Mirrors GATE_* in measure.py; keep in sync.
GATE_THRESHOLDS = {
    "min_corners": 8,           # of 24 ChArUco inner corners
    "min_px_per_mm": 8.0,       # rectified scale at the crack
    "min_blur_var": 150.0,      # variance of Laplacian on the board ROI
    "max_obliquity_deg": 45.0,  # camera-to-board-plane tilt
    "max_glare_frac": 0.05,     # fraction of saturated pixels on board/crack ROI
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
- blur_var: variance of the Laplacian (sharpness). Low = motion blur or defocus.
- px_per_mm: image pixels per millimetre on the wall plane after rectification. Low = too far away. Width precision is roughly 1/px_per_mm.
- obliquity_deg: tilt between the camera axis and the board plane. High = shooting at a steep angle; perspective error grows and effective px/mm along the crack drops.
- glare_frac: fraction of saturated (blown-out) pixels. High = specular reflection that can hide the crack or board corners.
- crack_px_extent: size of the detected crack in pixels (0/None = no crack found).
- image_w, image_h: frame size.
Values may be null or 0 when OpenCV could not compute them.
- board_found, failing_checks, all_failures_marginal, crack_measured, widen_now_allowed, abandon_now_allowed: derived for you by code, not by OpenCV on pixels. widen_now_allowed and abandon_now_allowed already count the failed attempts for you. failing_checks lists every failed gate check with its value, its threshold and how many percent past the threshold it is. all_failures_marginal is true when every failed check is within 20% of its threshold. crack_measured is true when a crack width was measured.

BOARD NOT FOUND (board_found=false, corners below about 7): OpenCV could not calibrate, so px_per_mm, obliquity_deg and glare_frac are reported as 0. Those zeros mean "not measured", not "fine": glare, a steep angle, a cropped board or blur can each have lost the board, and you cannot tell which from the board numbers. Only blur_var is still informative, and it is then the sharpness of the whole frame: below about 100 the frame itself is blurred.

CERTIFICATION GATE (a capture is "certified" only if ALL pass)
- corners >= {GATE_THRESHOLDS['min_corners']} (reason: too_few_corners)
- px_per_mm >= {GATE_THRESHOLDS['min_px_per_mm']} (reason: low_resolution)
- blur_var >= {GATE_THRESHOLDS['min_blur_var']} (reason: blurry)
- obliquity_deg <= {GATE_THRESHOLDS['max_obliquity_deg']} (reason: oblique)
- glare_frac <= {GATE_THRESHOLDS['max_glare_frac']} (reason: glare)
The input gives you the gate result and the list of failed reasons. certified=false with an empty reasons list means no crack was detected: use reposition_marker to frame the crack next to the board. Reason invalid_image: the frame was unusable, ask for a retake (reposition_marker).

ACTIONS
- accept: the capture is certified; report the width. Use ONLY when gate.certified is true.
- accept_with_widened_uncertainty: the gate fails only marginally (all_failures_marginal is true), the inspector already retried at least twice (consecutive_failed_attempts_before_this >= 2), and a crack was measured (crack_measured is true). Report it with a larger error bar.
- move_closer: fix low px/mm (reason low_resolution) when the board is otherwise found.
- reshoot_steadier: fix blur (brace the phone, wait for focus, tap to focus, hold still).
- relight: fix glare or poor light (tilt/shade the surface, change angle to the light, turn off flash).
- reposition_marker: fix geometry or visibility: board missing, cropped, occluded or too few corners; also use it to fix obliquity (stand square to the wall so the camera faces the board plane).
- abandon_and_log: give up on this crack and log the failure; use once consecutive_failed_attempts_before_this is {MAX_FAILED_ATTEMPTS - 1} or more (this capture is the {MAX_FAILED_ATTEMPTS}th failure).

RULES
1. Prefer the single action that fixes the dominant failure. Name the number that triggered it in the instruction, e.g. "Move closer: the board is only 6 px/mm, need 8 or more."
2. Compound failures: decide which to fix first, in this order.
   a. Glare that is hiding the board (glare fails and corners is below 12): relight first.
   b. Obliquity fails together with ANY other check: reposition_marker first. A steep angle lowers px/mm and corner detection, and re-aiming the phone changes the glare and the shake, so fixes made before it are often undone.
   c. Otherwise the failures are independent: fix the one with the largest percent_past_threshold.
2a. Board not found (board_found=false): if blur_var is below 100, reshoot_steadier. Otherwise reposition_marker. If last_actions ends with reposition_marker and the board is still not found, try relight, because glare may be hiding the board.
3. Use history. Do not repeat an action that already failed twice in a row; try the next-most-important fix or escalate.
3a. Marginal exit first: if widen_now_allowed is true, choose accept_with_widened_uncertainty. This beats a further retry and beats abandon_and_log.
3b. Otherwise, never choose abandon_and_log unless abandon_now_allowed is true; when it is true, choose abandon_and_log.
4. Never accept an uncertified capture. Never ask for another shot when gate.certified is true: choose accept.
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


def _obs_for_llm(o: dict) -> dict:
    keys = ["corners", "corners_total", "blur_var", "px_per_mm", "obliquity_deg", "glare_frac",
            "crack_px_extent", "image_w", "image_h"]
    out = {}
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


def _attempt_flags(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    n = failed_attempts(history)
    marginal = bool(cracks) and bool(_gate_reasons(gate)) and _marginal(observation, gate) and bool(_num((observation or {}).get("px_per_mm")))
    return {"widen_now_allowed": n >= 2 and marginal and not _certified(gate),
            "abandon_now_allowed": n >= MAX_FAILED_ATTEMPTS - 1 and not _certified(gate)}


def build_user_payload(observation: dict, gate: dict, cracks: list, history: list[dict]) -> dict:
    """Everything the LLM gets: numbers only. polyline_px and true_width_mm are stripped."""
    cr = []
    for c in cracks or []:
        cr.append({k: c.get(k) for k in ("id", "width_mm", "uncertainty_mm", "length_mm") if k in c})
    hist = []
    for i, s in enumerate((history or [])[-6:]):
        d = s.get("decision") or {}
        hist.append({
            "observation": _obs_for_llm(s.get("observation") or {}),
            "gate": {"certified": _certified(s.get("gate")), "reasons": _gate_reasons(s.get("gate"))},
            "action_taken": d.get("action"),
        })
    return {
        "current_capture": {
            "observation": _obs_for_llm(observation),
            "gate": {"certified": _certified(gate), "reasons": _gate_reasons(gate)},
            "measured_cracks": cr,
            **_derived_for_llm(observation, gate, cracks),
        },
        "history_oldest_first": hist,
        "consecutive_failed_attempts_before_this": failed_attempts(history),
        **_attempt_flags(observation, gate, cracks, history),
        "last_actions": _last_actions(history)[-4:],
    }


def _extract_tool_use(resp: dict) -> tuple[dict, int | None, int | None]:
    for block in (resp.get("output", {}).get("message", {}).get("content") or []):
        tu = block.get("toolUse")
        if tu and tu.get("name") == TOOL_NAME:
            usage = resp.get("usage") or {}
            return tu.get("input") or {}, usage.get("inputTokens"), usage.get("outputTokens")
    raise ValueError("no choose_action toolUse block in response")


def _llm(observation, gate, cracks, history, t0) -> dict:
    client = _get_client()
    payload = build_user_payload(observation, gate, cracks, history)
    messages = [{"role": "user", "content": [{"text": json.dumps(payload, separators=(",", ":"))}]}]
    last_err: Exception | None = None
    for model in _models():
        try:
            resp = client.converse(
                modelId=model,
                system=[{"text": SYSTEM_PROMPT}],
                messages=messages,
                inferenceConfig={"maxTokens": 400, "temperature": 0.0},
                toolConfig=TOOL_CONFIG,
            )
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code") if hasattr(e, "response") else None
            last_err = e
            if code in _MODEL_FALLTHROUGH_CODES:
                log.warning("model %s unavailable (%s); trying next", model, code)
                continue
            raise
        args, it, ot = _extract_tool_use(resp)
        action = args.get("action")
        if action not in ACTIONS:
            raise ValueError(f"invalid action from model: {action!r}")
        instruction = _clean_instruction(args.get("instruction"))
        if not instruction:
            raise ValueError("empty instruction from model")
        cert = _certified(gate)
        if cert and action != "accept":
            raise ValueError(f"guard: certified gate but model chose {action}")
        if not cert and action == "accept":
            raise ValueError("guard: model chose accept on uncertified gate")
        return _result(action, instruction, args.get("rationale") or "", "llm", model, t0, None, it, ot)
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


def decide(observation: dict, gate: dict, cracks: list, history: list[dict], *, policy: str = "llm") -> dict:
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
            return rules_decide(observation, gate, cracks, history)
        if policy == "random":
            return random_decide(observation, gate, cracks, history)
        if policy != "llm":
            r = rules_decide(observation, gate, cracks, history)
            r["fallback_reason"] = f"unknown policy {policy!r}"
            return r
        if not _llm_budget_ok():
            r = rules_decide(observation, gate, cracks, history)
            r["fallback_reason"] = "daily LLM call cap reached"
            return r
        try:
            return _llm(observation, gate, cracks, history, t0)
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"[:300]
            log.warning("LLM policy failed, using rules: %s", reason)
            r = rules_decide(observation, gate, cracks, history)
            r["fallback_reason"] = reason
            r["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            return r
    except Exception as e:  # absolute last resort
        return _result("reposition_marker", "Retake the photo with the whole board in view.",
                       f"decide() internal error: {e}", "rules", None, t0, f"internal: {e}"[:300])
