"""PROHORI web service: FastAPI app serving the phone PWA and the measurement API.

Run from the repo root:  uvicorn service.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import base64
import collections
import datetime as _dt
import json
import logging
import math
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATIC_DIR = HERE / "static"
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

log = logging.getLogger("prohori.service")

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_DECODE_SIDE = 4096
MAX_OVERLAY_SIDE = 1280
OVERLAY_JPEG_QUALITY = 80
RATE_LIMIT_PER_MIN = int(os.environ.get("PROHORI_RATE_LIMIT", "30"))
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VALID_POLICIES = ("llm", "rules")

# --------------------------------------------------------------------------
# Contract modules, with local fallbacks used only if the real ones are missing
# --------------------------------------------------------------------------
try:
    from prohori.measure import analyze, draw_overlay  # type: ignore

    MEASURE_IMPL = "prohori.measure"
except (ImportError, AttributeError):  # pragma: no cover - only before measure.py exists
    MEASURE_IMPL = "stub"

    def analyze(image_bgr: np.ndarray, *, panel_mode: bool = True) -> dict:
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        reasons = [] if blur > 50 else ["image too blurry"]
        return {
            "ok": True,
            "observation": {
                "corners": 18, "corners_total": 24, "blur_var": blur,
                "px_per_mm": 11.2, "obliquity_deg": 8.0, "glare_frac": 0.01,
                "crack_px_extent": 120.0, "image_w": w, "image_h": h,
            },
            "gate": {"certified": not reasons, "reasons": reasons},
            "cracks": [{
                "id": 1, "width_mm": 0.52, "uncertainty_mm": 0.06, "true_width_mm": None,
                "length_mm": 40.0,
                "polyline_px": [[w * 0.3, h * 0.5], [w * 0.5, h * 0.52], [w * 0.7, h * 0.5]],
            }],
            "timing_ms": {"total": 1.0}, "error": None,
        }

    def draw_overlay(image_bgr: np.ndarray, result: dict) -> np.ndarray:
        out = image_bgr.copy()
        for c in result.get("cracks", []):
            pts = np.array(c.get("polyline_px", []), np.int32).reshape(-1, 1, 2)
            if len(pts) > 1:
                cv2.polylines(out, [pts], False, (0, 0, 255), 4)
        return out


try:
    from prohori.agent import decide  # type: ignore

    AGENT_IMPL = "prohori.agent"
except (ImportError, AttributeError):  # pragma: no cover
    AGENT_IMPL = "stub"

    def decide(observation: dict, gate: dict, cracks: list, history: list, *, policy: str = "llm") -> dict:
        if gate.get("certified"):
            action, text = "accept", "Measurement certified. Accept."
        elif (observation.get("px_per_mm") or 0) < 8:
            action, text = "move_closer", "Move closer: the board resolution is too low."
        else:
            action, text = "reshoot_steadier", "Hold steadier and reshoot."
        return {"action": action, "instruction": text, "rationale": "stub rules",
                "policy": "rules", "model": None, "latency_ms": 0.0}


# Store: a small in-process fallback keeps the trace working if store.py is absent.
_FALLBACK_TRACE: dict[str, list[dict]] = {}
try:
    from prohori.store import get_trace, log_trace, save_evidence  # type: ignore

    STORE_IMPL = "prohori.store"
except (ImportError, AttributeError):  # pragma: no cover
    STORE_IMPL = "stub"

    def log_trace(session_id: str, step: dict) -> None:
        _FALLBACK_TRACE.setdefault(session_id, []).append(step)

    def get_trace(session_id: str) -> list[dict]:
        return list(_FALLBACK_TRACE.get(session_id, []))

    def save_evidence(session_id: str, step_idx: int, jpeg_bytes: bytes) -> str | None:
        return None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy types / NaN / inf into plain JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, np.generic):
        return to_jsonable(obj.item())
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, bytes):
        return None
    return obj


def exif_orientation(data: bytes) -> int:
    """Tiny JPEG EXIF parser: returns the orientation tag (1..8), 1 if absent/unreadable."""
    try:
        if data[:2] != b"\xff\xd8":
            return 1
        i, n = 2, len(data)
        while i + 4 <= n:
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                i += 2
                continue
            if marker in (0xD9, 0xDA):
                break
            seglen = int.from_bytes(data[i + 2:i + 4], "big")
            if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
                tiff = data[i + 10:i + 2 + seglen]
                bo = "little" if tiff[:2] == b"II" else "big"
                ifd = int.from_bytes(tiff[4:8], bo)
                count = int.from_bytes(tiff[ifd:ifd + 2], bo)
                for k in range(count):
                    e = ifd + 2 + k * 12
                    if int.from_bytes(tiff[e:e + 2], bo) == 0x0112:
                        val = int.from_bytes(tiff[e + 8:e + 10], bo)
                        return val if 1 <= val <= 8 else 1
                return 1
            i += 2 + seglen
    except Exception:
        pass
    return 1


def apply_orientation(img: np.ndarray, orientation: int) -> np.ndarray:
    if orientation == 2:
        return cv2.flip(img, 1)
    if orientation == 3:
        return cv2.rotate(img, cv2.ROTATE_180)
    if orientation == 4:
        return cv2.flip(img, 0)
    if orientation == 5:
        return cv2.transpose(img)
    if orientation == 6:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if orientation == 7:
        return cv2.rotate(cv2.transpose(img), cv2.ROTATE_180)
    if orientation == 8:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def decode_image(data: bytes) -> np.ndarray:
    """Decode bytes to BGR, apply EXIF orientation ourselves, cap the longest side."""
    buf = np.frombuffer(data, np.uint8)
    # IGNORE_ORIENTATION so we never double-rotate, whatever the OpenCV build does.
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if img is None or img.size == 0:
        raise ValueError("could not decode image")
    img = apply_orientation(img, exif_orientation(data))
    h, w = img.shape[:2]
    m = max(h, w)
    if m > MAX_DECODE_SIDE:
        s = MAX_DECODE_SIDE / m
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(img)


def encode_overlay(img: np.ndarray) -> bytes:
    h, w = img.shape[:2]
    m = max(h, w)
    if m > MAX_OVERLAY_SIDE:
        s = MAX_OVERLAY_SIDE / m
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, OVERLAY_JPEG_QUALITY])
    if not ok:
        raise RuntimeError("overlay encode failed")
    return enc.tobytes()


def slim_cracks(cracks: list[dict], max_pts: int = 300) -> list[dict]:
    out = []
    for c in cracks or []:
        c = dict(c)
        pl = c.get("polyline_px")
        if isinstance(pl, (list, tuple)) and len(pl) > max_pts:
            stride = math.ceil(len(pl) / max_pts)
            c["polyline_px"] = list(pl)[::stride]
        out.append(c)
    return out


def drop_polylines(cracks: list[dict]) -> list[dict]:
    return [{k: v for k, v in c.items() if k != "polyline_px"} for c in cracks or []]


# --- in-memory session history (fallback + fast path) ------------------------
_SESSIONS: "collections.OrderedDict[str, list[dict]]" = collections.OrderedDict()
_SESSIONS_LOCK = threading.Lock()
_MAX_SESSIONS = 500


def _remember(session_id: str, step: dict) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS.setdefault(session_id, []).append(step)
        _SESSIONS.move_to_end(session_id)
        while len(_SESSIONS) > _MAX_SESSIONS:
            _SESSIONS.popitem(last=False)
        if len(_SESSIONS[session_id]) > 200:
            del _SESSIONS[session_id][:-200]


def session_history(session_id: str) -> list[dict]:
    try:
        steps = get_trace(session_id)
        if steps:
            return list(steps)
    except Exception:
        log.exception("get_trace failed")
    with _SESSIONS_LOCK:
        return list(_SESSIONS.get(session_id, []))


# --- rate limiting --------------------------------------------------------------
_RATE: dict[str, collections.deque] = {}
_RATE_LOCK = threading.Lock()


def rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        dq = _RATE.setdefault(ip, collections.deque())
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= RATE_LIMIT_PER_MIN:
            return True
        dq.append(now)
        if len(_RATE) > 5000:
            for k in [k for k, v in _RATE.items() if not v or now - v[-1] > 60]:
                _RATE.pop(k, None)
    return False


# --- health info --------------------------------------------------------------
_INSTANCE: str | None = None
_VERSION: str | None = None
_INFO_LOCK = threading.Lock()


def _imds_instance_type() -> str:
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        token = urllib.request.urlopen(req, timeout=0.3).read().decode()
        req2 = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": token})
        return urllib.request.urlopen(req2, timeout=0.3).read().decode().strip() or "local"
    except Exception:
        return "local"


def instance_type() -> str:
    global _INSTANCE
    with _INFO_LOCK:
        if _INSTANCE is None:
            _INSTANCE = os.environ.get("PROHORI_INSTANCE") or _imds_instance_type()
        return _INSTANCE


def version() -> str:
    global _VERSION
    with _INFO_LOCK:
        if _VERSION is None:
            v = os.environ.get("PROHORI_VERSION")
            if not v:
                try:
                    v = subprocess.run(
                        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                        text=True, timeout=2).stdout.strip()
                except Exception:
                    v = ""
            _VERSION = v or "dev"
        return _VERSION


# --------------------------------------------------------------------------
# The pipeline (CPU heavy; runs in the threadpool)
# --------------------------------------------------------------------------
_STEP_LOCK = threading.Lock()


def run_pipeline(data: bytes, session_id: str, policy: str, t0: float) -> dict:
    image = decode_image(data)
    h, w = image.shape[:2]

    result = to_jsonable(analyze(image, panel_mode=True))
    observation = result.get("observation") or {}
    gate = result.get("gate") or {"certified": False, "reasons": []}
    cracks = result.get("cracks") or []

    with _STEP_LOCK:
        history = session_history(session_id)
        step_idx = len(history)

    try:
        decision = to_jsonable(decide(observation, gate, cracks, history, policy=policy))
    except Exception as exc:  # the agent must never take the demo down
        log.exception("decide failed")
        decision = {
            "action": "reshoot_steadier",
            "instruction": "The triage agent failed on this frame. Please retake the photo.",
            "rationale": f"agent error: {type(exc).__name__}", "policy": "rules",
            "model": None, "latency_ms": 0.0,
        }

    try:
        overlay_jpeg = encode_overlay(draw_overlay(image, result))
    except Exception:
        log.exception("overlay failed")
        overlay_jpeg = encode_overlay(image)
    overlay_b64 = base64.b64encode(overlay_jpeg).decode("ascii")

    evidence = None
    try:
        evidence = save_evidence(session_id, step_idx, overlay_jpeg)
    except Exception:
        log.exception("save_evidence failed")

    measurement = dict(result)
    measurement["cracks"] = slim_cracks(cracks)

    step = {
        "session_id": session_id,
        "step": step_idx,
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
        "image": {"w": w, "h": h, "bytes": len(data)},
        "policy_requested": policy,
        "ok": result.get("ok"),
        "error": result.get("error"),
        "observation": observation,
        "gate": gate,
        "cracks": drop_polylines(cracks),
        "decision": decision,
        "action": decision.get("action"),
        "timing_ms": result.get("timing_ms"),
        "evidence": evidence,
        "server_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    try:
        log_trace(session_id, to_jsonable(step))
    except Exception:
        log.exception("log_trace failed")
    _remember(session_id, step)

    return {
        "session_id": session_id,
        "step": step_idx,
        "measurement": measurement,
        "decision": decision,
        "overlay_jpeg_b64": overlay_b64,
        "server_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
app = FastAPI(title="Prohori", version="0.1.0", docs_url="/docs", redoc_url=None)

NO_CACHE = {"Cache-Control": "no-cache"}


@app.on_event("startup")
async def _warm() -> None:
    # Resolve the (slow-ish) instance/version lookups once, off the request path.
    threading.Thread(target=lambda: (instance_type(), version()), daemon=True).start()


@app.get("/health")
async def health() -> dict:
    inst = await run_in_threadpool(instance_type)
    ver = await run_in_threadpool(version)
    return {
        "status": "ok",
        "opencv": cv2.__version__,
        "arch": platform.machine(),
        "instance": inst,
        "version": ver,
        "impl": {"measure": MEASURE_IMPL, "agent": AGENT_IMPL, "store": STORE_IMPL},
    }


def _err(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"detail": msg}, status_code=status)


@app.post("/api/measure")
async def api_measure(
    request: Request,
    image: UploadFile = File(...),
    session_id: str | None = Form(None),
    policy: str = Form(os.environ.get("PROHORI_DEFAULT_POLICY", "rules")),
):
    t0 = time.perf_counter()
    ip = request.client.host if request.client else "unknown"
    if rate_limited(ip):
        return _err(429, "Too many requests, slow down (limit %d per minute)." % RATE_LIMIT_PER_MIN)

    policy = (policy or "rules").strip().lower()
    if policy not in VALID_POLICIES:
        return _err(400, "policy must be 'llm' or 'rules'.")

    session_id = (session_id or "").strip() or str(uuid.uuid4())
    if not SESSION_RE.match(session_id):
        return _err(400, "invalid session_id.")

    data = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _err(413, "Image too large (max 15 MB).")
    if not data:
        return _err(400, "Empty upload.")

    try:
        payload = await run_in_threadpool(run_pipeline, data, session_id, policy, t0)
    except ValueError as exc:
        return _err(400, str(exc))
    except Exception as exc:
        log.exception("pipeline failed")
        return _err(500, f"Measurement failed: {type(exc).__name__}: {exc}")
    return JSONResponse(payload)


@app.get("/api/trace/{session_id}")
async def api_trace(session_id: str):
    if not SESSION_RE.match(session_id):
        return _err(400, "invalid session_id.")
    steps = await run_in_threadpool(session_history, session_id)
    return JSONResponse(to_jsonable(steps))


@app.get("/api/samples")
async def api_samples():
    meta = STATIC_DIR / "samples" / "samples.json"
    try:
        return JSONResponse(json.loads(meta.read_text(encoding="utf-8")))
    except Exception:
        return JSONResponse([])


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE)


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript",
                        headers={**NO_CACHE, "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json", headers=NO_CACHE)


class _NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", _NoCacheStatic(directory=str(STATIC_DIR)), name="static")
