"""Tests for the FastAPI service (uses the real measure/agent/store modules once they exist)."""
import base64
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from service import app as svc  # noqa: E402

SAMPLES = ROOT / "service" / "static" / "samples"


@pytest.fixture(scope="module")
def client():
    svc.RATE_LIMIT_PER_MIN = 10_000
    return TestClient(svc.app)


@pytest.fixture(scope="module")
def sample_bytes():
    files = sorted(SAMPLES.glob("*.jpg"))
    assert files, "no demo samples bundled"
    return files[0].read_bytes()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    for k in ("opencv", "arch", "instance", "version"):
        assert j[k]


def test_index_and_pwa_files(client):
    assert "Prohori" in client.get("/").text
    assert client.get("/manifest.webmanifest").json()["name"]
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "/api/" in sw.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/icon-192.png").status_code == 200
    samples = client.get("/api/samples").json()
    assert len(samples) >= 3
    for s in samples:
        assert client.get(s["url"]).status_code == 200


def test_measure_and_trace(client, sample_bytes):
    r = client.post("/api/measure", files={"image": ("a.jpg", sample_bytes, "image/jpeg")},
                    data={"policy": "rules"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["step"] == 0
    sid = j["session_id"]
    assert len(sid) >= 8
    assert "observation" in j["measurement"] and "gate" in j["measurement"]
    assert isinstance(j["measurement"]["cracks"], list)
    assert j["decision"]["action"] and j["decision"]["instruction"]
    assert j["server_ms"] > 0
    overlay = cv2.imdecode(np.frombuffer(base64.b64decode(j["overlay_jpeg_b64"]), np.uint8), cv2.IMREAD_COLOR)
    assert overlay is not None and max(overlay.shape[:2]) <= 1280

    # second step in the same session
    r2 = client.post("/api/measure", files={"image": ("b.jpg", sample_bytes, "image/jpeg")},
                     data={"session_id": sid, "policy": "rules"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["session_id"] == sid and r2.json()["step"] == 1

    trace = client.get(f"/api/trace/{sid}").json()
    assert len(trace) == 2
    assert trace[0]["decision"]["action"]
    assert "observation" in trace[1]


def test_unknown_trace_is_empty(client):
    r = client.get("/api/trace/does-not-exist")
    assert r.status_code == 200 and r.json() == []


def test_bad_inputs(client, sample_bytes):
    r = client.post("/api/measure", files={"image": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 400
    r = client.post("/api/measure", files={"image": ("x.jpg", sample_bytes, "image/jpeg")}, data={"policy": "bogus"})
    assert r.status_code == 400
    r = client.post("/api/measure", files={"image": ("x.jpg", sample_bytes, "image/jpeg")}, data={"session_id": "../etc"})
    assert r.status_code == 400
    assert client.get("/api/trace/..%2Fetc").status_code in (400, 404)


def test_upload_too_large(client):
    big = b"\xff\xd8" + b"0" * (svc.MAX_UPLOAD_BYTES + 10)
    r = client.post("/api/measure", files={"image": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413


def test_rate_limit():
    old = svc.RATE_LIMIT_PER_MIN
    svc.RATE_LIMIT_PER_MIN = 3
    try:
        svc._RATE.clear()
        assert [svc.rate_limited("1.2.3.4") for _ in range(5)] == [False, False, False, True, True]
        assert svc.rate_limited("9.9.9.9") is False
    finally:
        svc.RATE_LIMIT_PER_MIN = old
        svc._RATE.clear()


def _jpeg_with_orientation(img_bgr, orientation):
    PIL = pytest.importorskip("PIL.Image")
    import io
    im = PIL.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    exif = im.getexif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95, exif=exif)
    return buf.getvalue()


@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_exif_orientation_applied(orientation):
    # asymmetric image: bright block in the top-left corner of a wide frame
    img = np.full((120, 200, 3), 40, np.uint8)
    img[:40, :60] = (255, 255, 255)
    data = _jpeg_with_orientation(img, orientation)
    assert svc.exif_orientation(data) == orientation
    out = svc.decode_image(data)
    expect = {1: (120, 200), 3: (120, 200), 6: (200, 120), 8: (200, 120)}[orientation]
    assert out.shape[:2] == expect
    # where the bright block lands after correcting orientation
    ys, xs = np.where(out[:, :, 0] > 200)
    cy, cx = ys.mean() / out.shape[0], xs.mean() / out.shape[1]
    want = {1: (0.17, 0.15), 3: (0.83, 0.85), 6: (0.15, 0.83), 8: (0.85, 0.17)}[orientation]
    assert abs(cy - want[0]) < 0.12 and abs(cx - want[1]) < 0.12


def test_decode_caps_size():
    big = np.zeros((100, 5000, 3), np.uint8)
    ok, enc = cv2.imencode(".png", big)
    out = svc.decode_image(enc.tobytes())
    assert max(out.shape[:2]) == svc.MAX_DECODE_SIDE
