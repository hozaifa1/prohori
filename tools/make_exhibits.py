"""Regenerate the agent-trace exhibit and the failure gallery by calling a running PROHORI endpoint.

    python tools/make_exhibits.py trace   [--base https://184-194-241-186.sslip.io] [--out docs/exhibits]
    python tools/make_exhibits.py gallery [--base ...] [--out docs/exhibits]

trace    POSTs service/static/samples/move-closer.jpg and then closer.jpg with the same session_id and policy=llm, then
         GETs /api/trace/<session_id>.  Writes <out>/trace_exhibit.json (the stored trace, as the endpoint returned it) and the two
         overlay JPEGs.  Needs the endpoint to have Bedrock access for policy=llm (use --policy rules for a local server).
gallery  Builds degraded copies of service/static/samples/good-straight.jpg (blur, glare, tilt; see DEGRADE below), posts every
         case with policy=llm and policy=rules, and writes <out>/gallery/<case>.json (gate, key numbers, both decisions) and an
         overlay JPEG (llm run, 900 px wide).

Only the standard library plus numpy / cv2 are used (no requests).
"""
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
import uuid
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "service" / "static" / "samples"


def post_image(base: str, jpeg: bytes, session_id: str, policy: str) -> dict:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("session_id", session_id), ("policy", policy)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="x.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                 + jpeg + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(base.rstrip("/") + "/api/measure", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def jpeg_bytes(img: np.ndarray, q: int = 92) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    assert ok
    return buf.tobytes()


# ---------------------------------------------------------------------------------------------- trace
def cmd_trace(a) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sid = a.session or time.strftime("exhibit-%Y%m%dT%H%M%S", time.gmtime())
    for i, name in enumerate(("move-closer", "closer")):
        res = post_image(a.base, (SAMPLES / f"{name}.jpg").read_bytes(), sid, a.policy)
        (out / f"trace_step{i}_overlay.jpg").write_bytes(base64.b64decode(res["overlay_jpeg_b64"]))
        print(name, res["decision"]["action"], "|", res["decision"]["instruction"])
    trace = get_json(f"{a.base.rstrip('/')}/api/trace/{sid}")
    (out / "trace_exhibit.json").write_text(json.dumps(trace, indent=1), encoding="utf-8")
    print("session", sid, "->", out / "trace_exhibit.json")


# ---------------------------------------------------------------------------------------------- gallery
def blur(img, sigma):
    return cv2.GaussianBlur(img, (0, 0), sigma)


def glare(img, strength_sigma_x, strength_sigma_y, cx=0.40, cy=0.72, power=2.5):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = np.exp(-(((xx - cx * w) / (strength_sigma_x * w)) ** 2 + ((yy - cy * h) / (strength_sigma_y * h)) ** 2) ** power)[..., None]
    return np.clip(img * (1 - g) + 255 * g, 0, 255).astype(np.uint8)


def tilt(img, k):
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[0, 0], [w, k * h * 0.5], [w, h - k * h * 0.5], [0, h]])
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REPLICATE)


def read(name):
    return cv2.imread(str(SAMPLES / name))


# (case id, what it shows, how the input is made)
DEGRADE = [
    ("too-far", "Much too far away (real photo, shrunk x0.25)", lambda: read("move-closer.jpg")),
    ("board-partial", "Board mostly out of frame (real photo)", lambda: read("board-partial.jpg")),
    ("blur-mild", "Blur sigma 5 px added to good-straight (synthetic)", lambda: blur(read("good-straight.jpg"), 5.0)),
    ("blur-heavy", "Blur sigma 11 px added to good-straight (synthetic)", lambda: blur(read("good-straight.jpg"), 11.0)),
    ("oblique-real", "Real shaky, steep photo (about 42 degrees)", lambda: read("blurry-oblique.jpg")),
    ("oblique-extreme", "Perspective squeeze k=0.7 on good-straight, about 67 degrees (synthetic)", lambda: tilt(read("good-straight.jpg"), 0.7)),
    ("glare-moderate", "Soft glare blob over the board, about 3 % saturated (synthetic)", lambda: glare(read("good-straight.jpg"), 0.30, 0.22, power=1.5)),
    ("glare-heavy", "Large glare blob over the board, about 12 % saturated (synthetic)", lambda: glare(read("good-straight.jpg"), 0.34, 0.30, power=2.5)),
    ("control-good", "Control: good-straight, no change (real photo)", lambda: read("good-straight.jpg")),
]

KEYS = ("corners", "px_per_mm", "blur_var", "blur_sigma_mm", "obliquity_deg", "glare_frac", "noise_sigma", "crack_coverage")


def cmd_gallery(a) -> None:
    out = Path(a.out) / "gallery"
    out.mkdir(parents=True, exist_ok=True)
    tag = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    summary = []
    for cid, desc, make in DEGRADE:
        img = make()
        h, w = img.shape[:2]
        rec = {"case": cid, "description": desc, "input_px": [w, h]}
        for pol in ("llm", "rules"):
            res = post_image(a.base, jpeg_bytes(img), f"gallery-{cid}-{pol}-{tag}", pol)
            m = res["measurement"]
            g, o = m["gate"], m["observation"]
            rec[pol] = {"action": res["decision"]["action"], "instruction": res["decision"]["instruction"],
                        "policy_used": res["decision"].get("policy"), "model": res["decision"].get("model")}
            if res["decision"].get("guardrail") is not None:
                gr_ = res["decision"]["guardrail"]
                rec[pol]["guardrail"] = {k: gr_.get(k) for k in ("violations", "reask", "repaired", "action_rejected")}
            if pol == "llm":
                rec["gate"] = {"tier": g.get("tier"), "certified": g.get("certified"), "reasons": g.get("reasons"),
                               "cracks_certified": g.get("cracks_certified"), "cracks_total": g.get("cracks_total")}
                rec["observation"] = {k: o.get(k) for k in KEYS}
                jpg = cv2.imdecode(np.frombuffer(base64.b64decode(res["overlay_jpeg_b64"]), np.uint8), cv2.IMREAD_COLOR)
                s = 900 / max(jpg.shape[:2])
                (out / f"{cid}.jpg").write_bytes(jpeg_bytes(cv2.resize(jpg, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), 85))
                cv2.imwrite(str(out / f"{cid}_input.jpg"), cv2.resize(img, None, fx=600 / max(h, w), fy=600 / max(h, w), interpolation=cv2.INTER_AREA),
                            [cv2.IMWRITE_JPEG_QUALITY, 80])
        (out / f"{cid}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        summary.append(rec)
        print(cid, rec["gate"]["tier"], rec["gate"]["reasons"], "|", rec["llm"]["action"], "/", rec["rules"]["action"])
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["trace", "gallery"])
    ap.add_argument("--base", default="https://184-194-241-186.sslip.io")
    ap.add_argument("--out", default=str(ROOT / "docs" / "exhibits"))
    ap.add_argument("--policy", default="llm", help="policy for the trace exhibit (llm or rules)")
    ap.add_argument("--session", default=None)
    a = ap.parse_args()
    {"trace": cmd_trace, "gallery": cmd_gallery}[a.what](a)
