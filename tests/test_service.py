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


@pytest.fixture(scope="module", autouse=True)
def isolated_env(tmp_path_factory):
    """Keep every test off the repo's data/ folder and off AWS."""
    mp = pytest.MonkeyPatch()
    mp.setenv("PROHORI_DATA_DIR", str(tmp_path_factory.mktemp("data")))
    for k in ("PROHORI_DDB_TABLE", "PROHORI_S3_BUCKET", "PROHORI_SNS_TOPIC_ARN"):
        mp.delenv(k, raising=False)
    yield
    mp.undo()


@pytest.fixture(scope="module")
def client(isolated_env):
    svc.RATE_LIMIT_PER_MIN = 10_000
    # One portal thread / event loop for the whole module. Without the context manager every request spins up a
    # new loop thread, and on this Windows setup that intermittently dies with an access violation.
    with TestClient(svc.app) as c:
        yield c


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
    assert isinstance(j["cool"], bool) and j["opencv_build"]["version"] == j["opencv"]


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


# ---------------------------------------------------------------------------- redaction in the pipeline
FACE = ROOT / "tests" / "data" / "face_astronaut_pd.jpg"
needs_model = pytest.mark.skipif(not svc.redact_mod.model_path().is_file(), reason="YuNet model missing")


def _decode_overlay(j):
    return cv2.imdecode(np.frombuffer(base64.b64decode(j["overlay_jpeg_b64"]), np.uint8), cv2.IMREAD_COLOR)


def _face_lap(img):
    region = img[70:170, 190:260]  # inside the detected face of the test portrait
    return cv2.Laplacian(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


@needs_model
def test_faces_are_blurred_in_overlay_and_evidence_and_counted_in_trace(client):
    r = client.post("/api/measure", files={"image": ("f.jpg", FACE.read_bytes(), "image/jpeg")}, data={"policy": "rules"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["redaction"]["faces"] == 1 and j["redaction"]["status"] == "ok" and j["redaction"]["persisted"]
    orig = cv2.imread(str(FACE))
    assert _face_lap(_decode_overlay(j)) < 0.15 * _face_lap(orig)
    # the persisted evidence is the redacted image too
    step = client.get(f"/api/trace/{j['session_id']}").json()[0]
    assert step["faces_redacted"] == 1 and step["redaction"]["faces"] == 1
    saved = cv2.imread(step["evidence"])
    assert saved is not None and _face_lap(saved) < 0.15 * _face_lap(orig)


@needs_model
def test_evidence_is_not_persisted_when_redaction_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("PROHORI_YUNET_MODEL", "no/such/model.onnx")
    r = client.post("/api/measure", files={"image": ("f.jpg", FACE.read_bytes(), "image/jpeg")}, data={"policy": "rules"})
    assert r.status_code == 200
    j = r.json()
    assert j["redaction"]["status"] == "unavailable" and j["redaction"]["persisted"] is False
    step = client.get(f"/api/trace/{j['session_id']}").json()[0]
    assert step["evidence"] is None  # fail closed: no unredacted image on disk or in S3


# ---------------------------------------------------------------------------- joint history + escalation
@pytest.fixture
def fake_vision(monkeypatch):
    """Deterministic vision + agent so history/escalation logic can be driven exactly."""
    state = {"w": 0.30, "u": 0.03, "certified": True, "action": "accept"}

    def analyze(image, panel_mode=True):
        h, w = image.shape[:2]
        return {"ok": True, "error": None, "timing_ms": {"total": 1.0},
                "observation": {"px_per_mm": 11.0, "corners": 20, "corners_total": 24, "blur_var": 400.0,
                                "obliquity_deg": 5.0, "glare_frac": 0.0, "image_w": w, "image_h": h},
                "gate": {"certified": state["certified"], "reasons": [] if state["certified"] else ["blurry"]},
                "cracks": [{"id": 1, "width_mm": state["w"], "uncertainty_mm": state["u"], "polyline_px": [[1, 1], [9, 9]]},
                           {"id": 2, "width_mm": 0.1, "uncertainty_mm": 0.02, "polyline_px": [[2, 2], [8, 3]]}]}

    def decide(observation, gate, cracks, history, *, policy="rules"):
        return {"action": state["action"], "instruction": "Test instruction.", "rationale": "test",
                "policy": "rules", "model": None, "latency_ms": 0.0}

    monkeypatch.setattr(svc, "analyze", analyze)
    monkeypatch.setattr(svc, "decide", decide)
    monkeypatch.setattr(svc, "draw_overlay", lambda image, result: image)
    monkeypatch.setenv("PROHORI_REDACT", "off")
    return state


def _post(client, data_bytes, **form):
    return client.post("/api/measure", files={"image": ("a.jpg", data_bytes, "image/jpeg")},
                       data={"policy": "rules", **form})


def _old_visit(joint, day, w, u, sess):
    from datetime import datetime, timedelta, timezone
    t = datetime.now(timezone.utc) - timedelta(days=day)
    svc.store_mod.log_measurement(joint, {"ts": t.isoformat(timespec="seconds"), "width_mm": w, "uncertainty_mm": u,
                                          "px_per_mm": 11.0, "inspection_session": sess, "crack_id": 1})


def test_invalid_joint_id_is_rejected(client, sample_bytes, fake_vision):
    for bad in ("a b", "../x", "x" * 65, "a#b"):
        assert _post(client, sample_bytes, joint_id=bad).status_code == 400
    assert client.get("/api/joint/a%20b").status_code == 400
    assert _post(client, sample_bytes, joint_id="  ").status_code == 200  # blank = no joint


def test_certified_measurement_is_logged_and_change_is_judged(client, sample_bytes, fake_vision):
    _old_visit("svc-j1", 30, 0.30, 0.03, "old-a")
    _old_visit("svc-j1", 15, 0.31, 0.03, "old-b")
    fake_vision["w"] = 0.33  # +0.02 vs last visit: inside uncertainty
    j = _post(client, sample_bytes, joint_id="SVC-J1").json()
    assert j["joint"]["id"] == "svc-j1" and j["joint"]["logged"] and j["joint"]["n_visits"] == 3
    assert j["joint"]["previous"]["session"] == "old-b"
    assert not j["joint"]["change"]["significant"]
    assert j["escalation"] is None
    # the logged crack is the headline (first) one, with its uncertainty and the capture's px/mm
    last = client.get("/api/joint/svc-j1").json()["visits"][-1]
    assert last["width_mm"] == 0.33 and last["px_per_mm"] == 11.0 and last["crack_id"] == 1
    step = client.get(f"/api/trace/{j['session_id']}").json()[0]
    assert step["joint_id"] == "svc-j1" and step["joint_logged"] is True


def test_significant_widening_escalates_once(client, sample_bytes, fake_vision, caplog):
    _old_visit("svc-j2", 20, 0.30, 0.03, "old-a")
    fake_vision["w"] = 0.62
    with caplog.at_level("WARNING", logger="prohori.escalate"):
        j = _post(client, sample_bytes, joint_id="svc-j2").json()
    assert j["joint"]["change"]["significant"] and j["joint"]["change"]["direction"] == "wider"
    assert j["escalation"]["escalated"] and j["escalation"]["why"] == ["widening"]
    assert j["escalation"]["sns"] == "local_only"
    assert "approve" not in str(j) and "token" not in str(j)  # the review link never reaches the client
    # a retake in the same session does not make a second escalation (rate limit) and does not add a visit
    j2 = _post(client, sample_bytes, joint_id="svc-j2", session_id=j["session_id"]).json()
    assert j2["joint"]["n_visits"] == 2
    assert j2["escalation"]["escalated"] is False and j2["escalation"]["suppressed"] == "rate_limit"
    trace = client.get(f"/api/trace/{j['session_id']}").json()
    assert trace[0]["escalation"]["escalated"] and "token" not in str(trace)


def test_abandon_and_log_escalates_even_without_a_joint(client, sample_bytes, fake_vision):
    fake_vision.update(certified=False, action="abandon_and_log")
    j = _post(client, sample_bytes).json()
    assert j["joint"] is None
    assert j["escalation"]["escalated"] and j["escalation"]["why"] == ["abandon_and_log"]


def test_uncertified_capture_is_not_logged_to_the_joint(client, sample_bytes, fake_vision):
    _old_visit("svc-j3", 10, 0.30, 0.03, "old-a")
    fake_vision.update(certified=False, w=0.9)
    j = _post(client, sample_bytes, joint_id="svc-j3").json()
    assert j["joint"]["logged"] is False and j["joint"]["n_visits"] == 1
    assert client.get("/api/joint/svc-j3").json()["n_visits"] == 1


def test_joint_endpoint_has_history_change_and_trend(client, fake_vision):
    for day, w in ((40, 0.30), (30, 0.34), (20, 0.38), (10, 0.42)):
        _old_visit("svc-j4", day, w, 0.01, f"s{day}")
    g = client.get("/api/joint/svc-j4").json()
    assert g["joint_id"] == "svc-j4" and g["n_visits"] == 4 and len(g["visits"]) == 4
    assert g["trend"]["significant"] and g["trend"]["direction"] == "widening"
    assert g["trend"]["slope_mm_per_30d"] == pytest.approx(0.12, abs=0.01)
    assert g["change"]["significant"] is True  # +0.04 in 10 days, u 0.01 each: beyond the 0.023 threshold
    assert "not a structural-capacity criterion" in g["note"]
    empty = client.get("/api/joint/svc-nobody").json()
    assert empty["n_visits"] == 0 and empty["visits"] == [] and empty["trend"] is None


def test_approval_page_requires_a_confirming_post(client, sample_bytes, fake_vision):
    import json
    import os
    _old_visit("svc-j5", 20, 0.30, 0.03, "old-a")
    fake_vision["w"] = 0.70
    j = _post(client, sample_bytes, joint_id="svc-j5").json()
    assert j["escalation"]["escalated"]
    appr = sorted((Path(os.environ["PROHORI_DATA_DIR"]) / "approvals").glob("*.json"),
                  key=lambda p: p.stat().st_mtime)[-1]
    token = appr.stem
    page = client.get(f"/api/approve/{token}")
    assert page.status_code == 200 and "svc-j5" in page.text and "I have reviewed this" in page.text
    assert "not a structural-capacity criterion" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert json.loads(appr.read_text())["status"] == "pending"  # a bare GET (mail scanner) does not approve
    done = client.post(f"/api/approve/{token}")
    assert done.status_code == 200 and "Review recorded" in done.text
    assert json.loads(appr.read_text())["status"] == "reviewed"
    again = client.get(f"/api/approve/{token}")
    assert "Already reviewed" in again.text and "I have reviewed this" not in again.text
    assert client.get("/api/approve/not-a-token").status_code == 404
    assert client.post("/api/approve/not-a-token").status_code == 404
    assert client.get("/api/approve/%3Cscript%3E").status_code == 404


def test_joint_follows_the_same_crack_id_as_last_visit(client, sample_bytes, fake_vision):
    from datetime import datetime, timezone
    svc.store_mod.log_measurement("svc-j6", {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                             "width_mm": 0.11, "uncertainty_mm": 0.02, "inspection_session": "old",
                                             "crack_id": 2})
    j = _post(client, sample_bytes, joint_id="svc-j6").json()
    assert j["joint"]["latest"]["crack_id"] == 2 and j["joint"]["latest"]["width_mm"] == 0.1


# ---------------------------------------------------------------------------- two-tier certificate through the API
def test_measure_response_carries_tier(client, sample_bytes):
    j = client.post("/api/measure", files={"image": ("a.jpg", sample_bytes, "image/jpeg")}, data={"policy": "rules"}).json()
    g = j["measurement"]["gate"]
    assert g["tier"] in ("certified", "indicative", "refused")
    assert g["certified"] == (g["tier"] != "refused")
    assert set(g["tiers"]) == {"certified", "indicative"}
    assert 0 < g["tiers"]["certified"]["heldout_mean_cond_risk"] < g["tiers"]["indicative"]["heldout_mean_cond_risk"] < 0.2
    for c in j["measurement"]["cracks"]:
        assert c["tier"] in ("certified", "indicative", "refused") and (c["tier"] != "refused") == c["certified"]
    # stored with the trace as well
    step = client.get(f"/api/trace/{j['session_id']}").json()[0]
    assert step["gate"]["tier"] == g["tier"] and all("tier" in c for c in step["cracks"])


def test_joint_record_stores_tier(client, sample_bytes):
    """Real pipeline: a certified/indicative capture logged to a joint carries its tier."""
    r = client.post("/api/measure", files={"image": ("a.jpg", sample_bytes, "image/jpeg")},
                    data={"policy": "rules", "joint_id": "tier-joint"})
    assert r.status_code == 200
    if r.json()["measurement"]["gate"]["certified"]:
        assert svc.store_mod.get_joint_history("tier-joint")[-1]["tier"] in ("certified", "indicative")
