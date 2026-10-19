"""Face redaction (src/prohori/redact.py). Test face: NASA astronaut portrait (public domain,
from scikit-image's data set), tests/data/face_astronaut_pd.jpg. No personal photos."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from prohori import redact

DATA = Path(__file__).resolve().parent / "data" / "face_astronaut_pd.jpg"
SAMPLES = Path(__file__).resolve().parent.parent / "service" / "static" / "samples"

pytestmark = pytest.mark.skipif(not redact.model_path().is_file(), reason="YuNet model not downloaded (models/)")


@pytest.fixture(scope="module")
def face_img():
    img = cv2.imread(str(DATA))
    assert img is not None
    return img


def _lap(img, box):
    x, y, w, h = box
    g = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def test_face_is_detected_and_blurred(face_img):
    r = redact.redact_faces(face_img)
    assert r.status == "ok" and r.faces == 1 and r.safe_to_persist
    x, y, w, h = r.boxes[0]
    # the face box lies on the portrait's face (upper middle of the frame)
    assert 120 < x + w / 2 < 330 and 40 < y + h / 2 < 260
    assert _lap(r.image, (x, y, w, h)) < 0.1 * _lap(face_img, (x, y, w, h))
    # the pixels well away from the face are untouched
    assert np.array_equal(r.image[300:, :150], face_img[300:, :150])
    # the input is never modified in place
    assert face_img.shape == r.image.shape and not np.array_equal(face_img, r.image)


def test_summary_is_json_friendly(face_img):
    s = redact.redact_faces(face_img).summary()
    assert s["faces"] == 1 and s["status"] == "ok" and s["model"] == "yunet_2023mar" and s["ms"] > 0


def test_no_face_means_identical_image():
    img = cv2.imread(str(SAMPLES / "good-straight.jpg"))
    assert img is not None
    r = redact.redact_faces(img)
    assert r.status == "ok" and r.faces == 0
    assert r.image is img or np.array_equal(r.image, img)


def test_large_frame_boxes_map_back_to_full_resolution(face_img):
    big = np.full((2400, 3200, 3), 128, np.uint8)
    big[800:800 + 512, 1500:1500 + 512] = face_img
    r = redact.redact_faces(big)
    assert r.faces >= 1
    x, y, w, h = r.boxes[0]
    cx, cy = x + w / 2, y + h / 2
    assert 1500 + 120 < cx < 1500 + 330 and 800 + 40 < cy < 800 + 260
    assert _lap(r.image, (x, y, w, h)) < 0.1 * _lap(big, (x, y, w, h))


def test_missing_model_fails_closed(face_img, monkeypatch):
    monkeypatch.setenv(redact.ENV_MODEL, "does/not/exist.onnx")
    r = redact.redact_faces(face_img)
    assert r.status == "unavailable" and r.faces == 0
    assert not r.safe_to_persist
    assert np.array_equal(r.image, face_img)  # untouched, and the caller must not persist it


def test_explicit_opt_out(face_img, monkeypatch):
    monkeypatch.setenv(redact.ENV_SWITCH, "off")
    r = redact.redact_faces(face_img)
    assert r.status == "disabled" and r.safe_to_persist and r.faces == 0


def test_blur_boxes_handles_edges_and_degenerate_boxes():
    img = np.random.default_rng(0).integers(0, 255, (100, 100, 3), dtype=np.uint8)
    out = redact.blur_boxes(img, [(-20, -20, 60, 60), (90, 90, 40, 40), (10, 10, 0, 0)])
    assert out.shape == img.shape
    assert not np.array_equal(out[:30, :30], img[:30, :30])
