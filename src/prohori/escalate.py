"""Engineer escalation with a human-approval step.

When the triage agent abandons a capture (``abandon_and_log``) or a joint shows a significant widening
(history.py), an escalation is raised:
  1. a plain-language message is built (joint, width +/- interval, change since last visit, px/mm, link to
     the agent trace, and the statement that this is durability guidance, not a structural verdict);
  2. an approval record with a random secret token is stored (store.py, same DynamoDB table);
  3. the message is published to the SNS topic in env PROHORI_SNS_TOPIC_ARN (unset: logged locally only);
  4. a named engineer opens ``/api/approve/<token>`` from the message and confirms that they reviewed it.

Escalation is a request for a human to look. It never changes a measurement and never states a safety verdict.
The approval token is a secret (192 random bits): it goes only into the SNS message and the server log,
never into any API response or trace step, so the inspector cannot approve their own escalation.
Rate limit: at most one escalation per joint (or per session when no joint id) per ``PROHORI_ESCALATION_COOLDOWN_S``
seconds (default 3600).

Env: PROHORI_SNS_TOPIC_ARN, PROHORI_AWS_REGION, PROHORI_PUBLIC_URL (base for links, default relative paths),
     PROHORI_ESCALATION_COOLDOWN_S.
IAM: sns:Publish on the topic ARN (plus the DynamoDB actions store.py already needs).
"""
from __future__ import annotations

import logging
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from . import history as _history
from . import store

log = logging.getLogger("prohori.escalate")

ENV_TOPIC = "PROHORI_SNS_TOPIC_ARN"
ENV_REGION = "PROHORI_AWS_REGION"
ENV_PUBLIC_URL = "PROHORI_PUBLIC_URL"
ENV_COOLDOWN = "PROHORI_ESCALATION_COOLDOWN_S"
DEFAULT_COOLDOWN_S = 3600

DISCLAIMER = ("This is a durability-guidance reference, not a structural-capacity criterion. "
              "Prohori does not give a safety verdict. Please have a qualified engineer review this joint.")

_sns_lock = threading.Lock()
_approval_lock = threading.Lock()  # read-modify-write of approval records
_esc_lock = threading.Lock()  # makes check-rate-limit + record atomic within this process
_sns_cache: dict[str, Any] = {}


def cooldown_s() -> float:
    try:
        return max(0.0, float(os.environ.get(ENV_COOLDOWN, DEFAULT_COOLDOWN_S)))
    except ValueError:
        return float(DEFAULT_COOLDOWN_S)


def _sns_client():
    region = os.environ.get(ENV_REGION, "us-east-1")
    with _sns_lock:
        c = _sns_cache.get(region)
        if c is None:
            import boto3
            from botocore.config import Config

            c = boto3.client("sns", region_name=region,
                             config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2, "mode": "standard"}))
            _sns_cache[region] = c
        return c


def _reset_clients() -> None:
    with _sns_lock:
        _sns_cache.clear()


def _link(path: str) -> str:
    base = os.environ.get(ENV_PUBLIC_URL, "").rstrip("/")
    return f"{base}{path}"


# --------------------------------------------------------------------------- decision
def triggers(decision: dict | None, summary: dict | None) -> list[str]:
    """Reasons to escalate for this capture: "abandon_and_log", "widening", "trend"."""
    out: list[str] = []
    if (decision or {}).get("action") == "abandon_and_log":
        out.append("abandon_and_log")
    ch = (summary or {}).get("change") or {}
    if ch.get("significant") and ch.get("direction") == "wider":
        out.append("widening")
    tr = (summary or {}).get("trend") or {}
    if tr.get("significant") and tr.get("direction") == "widening":
        out.append("trend")
    return out


def _fmt(x: Any, d: int = 2) -> str:
    try:
        return f"{float(x):.{d}f}"
    except (TypeError, ValueError):
        return "n/a"


def build_message(*, joint_id: str | None, session_id: str, why: list[str], crack: dict | None,
                  gate: dict | None, observation: dict | None, summary: dict | None, token: str,
                  decision: dict | None = None) -> tuple[str, str]:
    """(subject, body) in plain language. SNS subjects are ASCII, one line, at most 100 characters."""
    label = joint_id or f"session {session_id[:8]}"
    subject = f"Prohori: engineering review requested - {label}"[:100]
    lines = [f"Prohori asks an engineer to review: {label}", ""]
    reasons = []
    if "abandon_and_log" in why:
        reasons.append("the triage agent could not obtain a certifiable measurement and abandoned the capture")
    if "widening" in why:
        reasons.append("the crack is wider than at the last visit, beyond measurement uncertainty")
    if "trend" in why:
        reasons.append("the visit history shows a steady widening trend")
    lines.append("Why: " + "; ".join(reasons) + ".")
    lines.append("")
    c = crack or {}
    u = c.get("uncertainty_mm")
    if c.get("width_mm") is not None:
        s = f"Width: {_fmt(c.get('width_mm'))} mm"
        if u is not None:
            kind = (summary or {}).get("uncertainty_kind", "standard")
            level = (summary or {}).get("level") or _history.change_level()
            if kind == "standard":
                k = _history.coverage_factor(level)
                s += f" +/- {_fmt(u)} mm (standard uncertainty; {int(round(level * 100))}% interval +/- {_fmt(k * float(u))} mm)"
            else:
                s += f" +/- {_fmt(u)} mm ({int(round(level * 100))}% interval)"
        lines.append(s)
    else:
        lines.append("Width: no certified width in this capture.")
        reasons_g = (gate or {}).get("reasons") or []
        if reasons_g:
            lines.append("Gate reasons: " + ", ".join(str(r).replace("_", " ") for r in reasons_g))
    ch = (summary or {}).get("change")
    prev = (summary or {}).get("previous")
    if ch and ch.get("delta_mm") is not None and prev:
        sign = "+" if ch["delta_mm"] >= 0 else "-"
        lines.append(f"Change since last visit: {sign}{_fmt(abs(ch['delta_mm']))} mm over {_fmt(ch.get('days'), 1)} days "
                     f"(decision threshold {_fmt(ch.get('threshold_mm'))} mm): {ch.get('verdict')}.")
    tr = (summary or {}).get("trend")
    if tr and tr.get("slope_mm_per_30d") is not None:
        lines.append(f"Trend over {tr.get('n')} visits: {_fmt(tr['slope_mm_per_30d'], 3)} mm per 30 days "
                     f"(interval {_fmt(tr.get('slope_lo_mm_per_30d'), 3)} to {_fmt(tr.get('slope_hi_mm_per_30d'), 3)}).")
    o = observation or {}
    if o.get("px_per_mm") is not None:
        lines.append(f"Image scale: {_fmt(o.get('px_per_mm'), 1)} px/mm (certification needs 8 or more).")
    if decision and decision.get("instruction"):
        lines.append(f"Agent instruction to the operator: {decision['instruction']}")
    lines += ["",
              f"Agent trace: {_link('/api/trace/' + session_id)}",
              f"Confirm you reviewed this: {_link('/api/approve/' + token)}",
              "",
              DISCLAIMER]
    return subject, "\n".join(lines)


# --------------------------------------------------------------------------- publish
def _publish(topic: str, subject: str, body: str) -> str:
    try:
        _sns_client().publish(TopicArn=topic, Subject=subject, Message=body)
        return "published"
    except Exception as exc:
        log.warning("SNS publish failed: %s: %s", type(exc).__name__, exc)
        return "failed"


def _publish_and_record(topic: str, subject: str, body: str, token: str) -> str:
    status = _publish(topic, subject, body)
    with _approval_lock:
        rec = store.get_approval(token)
        if rec is not None:
            rec["sns"] = status
            store.put_approval(token, rec)
    return status


def escalate(*, session_id: str, joint_id: str | None, why: list[str], crack: dict | None = None,
             gate: dict | None = None, observation: dict | None = None, summary: dict | None = None,
             decision: dict | None = None, background: bool = True) -> dict:
    """Raise an escalation for ``why`` (non-empty list of triggers). Returns a public dict (no token):
        {escalated, why, escalation_id, status, sns, joint_id} or {escalated: False, suppressed: "rate_limit", ...}.
    ``background`` publishes to SNS on a daemon thread so the capture response is never delayed by the network
    (sns is then "queued"); tests pass background=False."""
    key = joint_id or f"session-{session_id}"
    log_pk = f"{store.ESCALATION_PREFIX}{key}"
    token = secrets.token_urlsafe(24)
    esc_id = uuid.uuid4().hex[:12]
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _esc_lock:
        now = time.time()
        recent = store.list_records(log_pk, newest_first=True, limit=1)
        if recent:
            try:
                last = datetime.fromisoformat(recent[0]["sk"]).timestamp()
                if now - last < cooldown_s():
                    return {"escalated": False, "suppressed": "rate_limit", "why": why, "joint_id": joint_id,
                            "retry_after_s": int(cooldown_s() - (now - last)),
                            "escalation_id": recent[0].get("escalation_id")}
            except (KeyError, ValueError):
                pass
        store.append_record(log_pk, {"escalation_id": esc_id, "joint_id": joint_id, "inspection_session": session_id,
                                     "why": why, "created": created})
    subject, body = build_message(joint_id=joint_id, session_id=session_id, why=why, crack=crack, gate=gate,
                                  observation=observation, summary=summary, token=token, decision=decision)
    topic = os.environ.get(ENV_TOPIC, "").strip()
    store.put_approval(token, {
        "escalation_id": esc_id, "status": "pending", "created": created, "reviewed": None,
        "joint_id": joint_id, "session_id": session_id, "why": why, "subject": subject, "message": body,
        "sns": "queued" if topic else "local_only",
    })
    if not topic:
        log.warning("ESCALATION (no SNS topic configured, logged locally only): %s\n%s", subject, body)
        sns = "local_only"
    elif background:
        threading.Thread(target=_publish_and_record, args=(topic, subject, body, token), daemon=True).start()
        sns = "queued"
    else:
        sns = _publish_and_record(topic, subject, body, token)
    return {"escalated": True, "why": why, "escalation_id": esc_id, "status": "pending", "sns": sns,
            "joint_id": joint_id, "created": created}


# --------------------------------------------------------------------------- human approval
def get_review(token: str) -> dict | None:
    """The approval record for a token, or None. Token format is checked so junk never reaches the store."""
    if not token or len(token) > 80 or not all(ch.isalnum() or ch in "-_" for ch in token):
        return None
    return store.get_approval(token)


def mark_reviewed(token: str, reviewer_note: str | None = None) -> dict | None:
    """Mark the escalation reviewed (idempotent: the first review time is kept). Returns the record or None."""
    if get_review(token) is None:
        return None
    with _approval_lock:
        rec = store.get_approval(token)
        if rec is None:
            return None
        if rec.get("status") != "reviewed":
            rec["status"] = "reviewed"
            rec["reviewed"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if reviewer_note:
                rec["note"] = reviewer_note[:500]
            store.put_approval(token, rec)
        return rec
