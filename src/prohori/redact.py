"""Face redaction before anything is persisted or returned (privacy by design).

Uses OpenCV's ``FaceDetectorYN`` with the YuNet model (Wu, Peng, Yu, "YuNet: A Tiny Millisecond-level
Face Detector", Machine Intelligence Research 20(5), 2023; ONNX from the official opencv_zoo, see
models/README.md for URL + sha256). Detected faces are blurred with a strong, feathered Gaussian
blur (sigma proportional to the face size, so it is not reversible by simple deblurring).

Design choices
  * Detection runs on a copy downscaled to ``DETECT_MAX_SIDE`` px (fast, and YuNet is trained for
    small faces); boxes are mapped back to full resolution. Boxes are expanded by ``MARGIN`` so hair
    line / chin / ears are covered.
  * ``redact_faces`` never raises. It returns a ``RedactionResult`` with a ``status``:
        "ok"          detector ran (faces may be 0)
        "disabled"    PROHORI_REDACT=off (explicit opt-out, tests / dev only)
        "unavailable" model file missing or detector failed. The image is returned UNCHANGED and the
                      caller must treat it as not safe to persist (fail closed, see ``safe_to_persist``).
  * The detector object is not thread-safe, so calls are serialised with a lock.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("prohori.redact")

MODEL_NAME = "face_detection_yunet_2023mar.onnx"
ENV_MODEL = "PROHORI_YUNET_MODEL"
ENV_SWITCH = "PROHORI_REDACT"  # "off" disables (never set in production)
SCORE_THRESHOLD = 0.6
NMS_THRESHOLD = 0.3
TOP_K = 200
DETECT_MAX_SIDE = 1600
MARGIN = 0.30  # expand each box by this fraction of its size on every side
MIN_FACE_PX = 12  # ignore detections smaller than this in the original image (noise)

_lock = threading.Lock()
_detector = None
_detector_path: str | None = None
_load_error: str | None = None


def release() -> None:
    """Drop the detector. Registered at exit: destroying an OpenCV DNN object during interpreter teardown,
    after OpenCV's own thread pool is gone, crashes on Windows (access violation at process exit)."""
    global _detector, _detector_path
    with _lock:
        _detector = None
        _detector_path = None


atexit.register(release)


@dataclass
class RedactionResult:
    image: np.ndarray
    faces: int = 0
    status: str = "ok"
    boxes: list[tuple[int, int, int, int]] = field(default_factory=list)  # x, y, w, h in image px
    ms: float = 0.0

    @property
    def safe_to_persist(self) -> bool:
        """True when persisting ``image`` cannot leak an unredacted face (detector ran, or explicit opt-out)."""
        return self.status in ("ok", "disabled")

    def summary(self) -> dict:
        return {"faces": int(self.faces), "status": self.status, "model": "yunet_2023mar", "ms": round(self.ms, 1)}


def model_path() -> Path:
    env = os.environ.get(ENV_MODEL)
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "models" / MODEL_NAME


def _get_detector(width: int, height: int):
    """Create (once) and size the YuNet detector. Caller holds _lock."""
    global _detector, _detector_path, _load_error
    path = str(model_path())
    if _detector is None or _detector_path != path:
        _detector = None
        _load_error = None
        if not Path(path).is_file():
            _load_error = f"model file not found: {path}"
            raise FileNotFoundError(_load_error)
        _detector = cv2.FaceDetectorYN.create(path, "", (320, 320), SCORE_THRESHOLD, NMS_THRESHOLD, TOP_K)
        _detector_path = path
    _detector.setInputSize((int(width), int(height)))
    return _detector


def detect_faces(image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Face boxes (x, y, w, h) in the coordinates of ``image_bgr``. Raises if the model is unavailable."""
    h, w = image_bgr.shape[:2]
    s = min(1.0, DETECT_MAX_SIDE / max(h, w))
    small = image_bgr if s == 1.0 else cv2.resize(
        image_bgr, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    with _lock:
        det = _get_detector(small.shape[1], small.shape[0])
        _, faces = det.detect(small)
    boxes: list[tuple[int, int, int, int]] = []
    if faces is not None:
        for f in faces:
            x, y, bw, bh = (float(v) / s for v in f[:4])
            if min(bw, bh) < MIN_FACE_PX:
                continue
            boxes.append((int(round(x)), int(round(y)), int(round(bw)), int(round(bh))))
    return boxes


def blur_boxes(image_bgr: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Return a copy with each box (expanded by MARGIN) replaced by a strongly blurred, feathered ellipse."""
    out = image_bgr.copy()
    H, W = out.shape[:2]
    for (x, y, bw, bh) in boxes:
        mx, my = bw * MARGIN, bh * MARGIN
        x0, y0 = max(0, int(x - mx)), max(0, int(y - my))
        x1, y1 = min(W, int(x + bw + mx)), min(H, int(y + bh + my))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        roi = out[y0:y1, x0:x1]
        sigma = max(6.0, max(x1 - x0, y1 - y0) / 3.0)
        # Downscale-blur-upscale first: kills fine structure far faster than a huge kernel, then smooth.
        small = cv2.resize(roi, (max(2, (x1 - x0) // 8), max(2, (y1 - y0) // 8)), interpolation=cv2.INTER_AREA)
        up = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
        blurred = cv2.GaussianBlur(up, (0, 0), sigma / 4.0)
        mask = np.zeros(roi.shape[:2], np.float32)
        cv2.ellipse(mask, ((x1 - x0) // 2, (y1 - y0) // 2), ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, sigma / 10.0))[..., None]
        roi[:] = (blurred.astype(np.float32) * mask + roi.astype(np.float32) * (1.0 - mask)).astype(np.uint8)
    return out


def redact_faces(image_bgr: np.ndarray) -> RedactionResult:
    """Blur every detected face. Never raises; see module docstring for ``status`` semantics."""
    t0 = time.perf_counter()
    if os.environ.get(ENV_SWITCH, "").strip().lower() in ("off", "0", "false", "no"):
        return RedactionResult(image_bgr, 0, "disabled", [], (time.perf_counter() - t0) * 1000)
    try:
        boxes = detect_faces(image_bgr)
        out = blur_boxes(image_bgr, boxes) if boxes else image_bgr
        return RedactionResult(out, len(boxes), "ok", boxes, (time.perf_counter() - t0) * 1000)
    except Exception as exc:
        log.warning("face redaction unavailable: %s: %s", type(exc).__name__, exc)
        return RedactionResult(image_bgr, 0, "unavailable", [], (time.perf_counter() - t0) * 1000)
