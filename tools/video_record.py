"""Record the LIVE Prohori app (phone viewport) with Playwright, for the demo video.

Usage:  python tools/video_record.py [scene ...]        (default: all scenes)
Scenes: a_certified  b_agent_loop  c_indicative  d_trace

Output: docs/video/assets/screens/<scene>.mp4 (1920x1080, 30 fps, H.264, no audio)
        docs/video/assets/screens/<scene>_still*.png (key frames, 1920x1080)
        docs/video/assets/screens/markers.json (seconds of key events inside each clip)

Only the app's own measure requests with the bundled sample images are sent.
The "closer" recovery photo is not in the sample list UI order the viewer expects, so it is
selected from the same sample dialog (the list API includes it), keeping the same session.
"""
from __future__ import annotations

import base64
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "video" / "assets" / "screens"
RAW = ROOT / "docs" / "video" / "assets" / "tmp"
URL = "https://184-194-241-186.sslip.io/"
VW, VH, DSF = 390, 844, 2
FPS = 30
FAKECAM = RAW / "fakecam.mjpeg"

CURSOR_JS = """
(() => {
  const mk = () => {
    if (document.getElementById('__cur')) return;
    const st = document.createElement('style');
    st.textContent = `
      #__cur{position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
        background:rgba(255,255,255,.28);border:2px solid rgba(255,255,255,.92);box-shadow:0 2px 10px rgba(0,0,0,.5);
        pointer-events:none;z-index:2147483647;transition:transform .12s ease-out, background .12s}
      #__cur.down{transform:scale(.72);background:rgba(246,176,42,.65)}
      .__rip{position:fixed;width:20px;height:20px;margin:-10px 0 0 -10px;border-radius:50%;border:3px solid #f6b02a;
        pointer-events:none;z-index:2147483646;animation:__rip .6s ease-out forwards}
      @keyframes __rip{to{transform:scale(4);opacity:0}}
      html{scroll-behavior:auto !important}`;
    document.head.appendChild(st);
    const c = document.createElement('div'); c.id='__cur'; c.style.display='none'; document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.display='block'; c.style.left=e.clientX+'px'; c.style.top=e.clientY+'px'; }, true);
    addEventListener('mousedown', e => { c.classList.add('down');
      const r=document.createElement('div'); r.className='__rip'; r.style.left=e.clientX+'px'; r.style.top=e.clientY+'px';
      document.body.appendChild(r); setTimeout(()=>r.remove(),700); }, true);
    addEventListener('mouseup', () => c.classList.remove('down'), true);
  };
  if (document.body) mk(); else addEventListener('DOMContentLoaded', mk);
})();
"""


def ease(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * t)


class Driver:
    """Phone-viewport browser driven with easing; frames come from CDP Page.startScreencast so they are true 2x."""

    def __init__(self, pw, scene: str):
        self.scene = scene
        self.fdir = RAW / f"frames_{scene}"
        shutil.rmtree(self.fdir, ignore_errors=True)
        self.fdir.mkdir(parents=True)
        args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-video-capture={FAKECAM}", "--autoplay-policy=no-user-gesture-required"]
        self.browser = pw.chromium.launch(args=args)
        self.ctx = self.browser.new_context(
            viewport={"width": VW, "height": VH}, device_scale_factor=DSF, color_scheme="dark",
            permissions=["camera"], locale="en-GB", timezone_id="Asia/Dhaka")
        self.ctx.add_init_script(CURSOR_JS)
        self.page = self.ctx.new_page()
        self.cdp = self.ctx.new_cdp_session(self.page)
        self.frames: list[tuple[float, bytes]] = []
        self.acks: list[int] = []
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                                "maxWidth": VW * DSF, "maxHeight": VH * DSF, "everyNthFrame": 1})
        self.markers: dict[str, float] = {}
        self.mx, self.my = VW * 0.5, VH * 0.9
        self.stills: list[tuple[str, float]] = []

    def _on_frame(self, ev):
        self.frames.append((float(ev["metadata"]["timestamp"]), base64.b64decode(ev["data"])))
        self.acks.append(ev["sessionId"])

    def flush(self):
        while self.acks:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": self.acks.pop(0)})

    # ---- time/markers (epoch seconds; converted to clip time at compose)
    def mark(self, name: str):
        self.markers[name] = time.time()

    def hold(self, sec: float):
        end = time.time() + sec
        while time.time() < end:
            self.page.wait_for_timeout(15)
            self.flush()

    def wait_js(self, expr: str, timeout: float = 90.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.page.evaluate(expr):
                return
            self.hold(0.1)
        raise TimeoutError(expr)

    # ---- motion
    def move_to(self, x: float, y: float, ms: int = 700):
        self.page.evaluate("(() => { const c = document.getElementById('__cur'); if (c) c.style.opacity = 1; })()")
        steps = max(8, ms // 16)
        x0, y0 = self.mx, self.my
        for i in range(1, steps + 1):
            e = ease(i / steps)
            self.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            self.page.wait_for_timeout(14)
            self.flush()
        self.mx, self.my = x, y

    def click_box(self, bb, ms=800, pre=0.3):
        self.move_to(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, ms)
        self.hold(pre)
        self.page.mouse.down(); self.hold(0.12); self.page.mouse.up()

    def tap(self, selector: str, ms: int = 800):
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        self.hold(0.3)
        self.click_box(loc.bounding_box(), ms)

    def scroll_to(self, y: float, ms: int = 1800):
        self.page.evaluate(
            """([y, ms]) => { const s = document.scrollingElement, y0 = s.scrollTop, t0 = performance.now();
                const f = t => { const k = Math.min(1, (t - t0) / ms), e = .5 - .5 * Math.cos(Math.PI * k);
                  s.scrollTop = y0 + (y - y0) * e; if (k < 1) requestAnimationFrame(f); };
                requestAnimationFrame(f); }""", [y, ms])
        self.hold(ms / 1000 + 0.1)

    def scroll_el(self, selector: str, ms: int = 1800, offset: int = 80):
        y = self.page.evaluate(
            "([sel, off]) => { const r = document.querySelector(sel).getBoundingClientRect(); return r.top + scrollY - off; }",
            [selector, offset])
        self.scroll_to(max(0, y), ms)

    def still(self, name: str):
        self.stills.append((name, time.time()))

    # ---- app actions
    def load(self, policy: str = "llm"):
        self.page.goto(URL, wait_until="networkidle")
        self.page.select_option("#policy", policy)
        self.hold(1.2)
        self.mark("loaded")

    def pick_sample(self, sample_id: str):
        self.tap("#btn-demo")
        self.page.wait_for_selector("#sample-list .sample")
        self.wait_js("[...document.querySelectorAll('#sample-list img')].every(i => i.complete && i.naturalWidth > 0)")
        self.mark(f"dialog_ready_{sample_id}")
        self.hold(1.3)
        loc = self.page.locator(f'#sample-list .sample:has(img[src$="/{sample_id}.jpg"])')
        loc.scroll_into_view_if_needed()
        self.hold(0.6)
        bb = loc.bounding_box()
        self.move_to(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, 900)
        self.hold(0.6)
        self.mark(f"pick_{sample_id}")
        self.page.mouse.down(); self.hold(0.12); self.page.mouse.up()
        self.move_to(VW - 14, VH * 0.62, 600)  # park the pointer at the edge and hide it
        self.page.evaluate("document.getElementById('__cur').style.opacity = 0")

    def wait_result(self, timeout=90.0):
        self.wait_js("!document.querySelector('#view-result').hidden && document.querySelector('#busy').hidden"
                     " && document.querySelectorAll('#trace li.step').length > 0", timeout)
        self.nres = getattr(self, "nres", 0) + 1
        self.mark(f"result_{self.nres}")
        self.hold(0.8)

    def finish(self):
        self.hold(0.8)
        self.markers["end"] = time.time()
        self.cdp.send("Page.stopScreencast")
        self.ctx.close()
        self.browser.close()
        # write frames + concat list
        t0 = self.frames[0][0]
        lines = []
        for i, (ts, data) in enumerate(self.frames):
            fp = self.fdir / f"f{i:05d}.jpg"
            fp.write_bytes(data)
            dur = (self.frames[i + 1][0] - ts) if i + 1 < len(self.frames) else 0.5
            lines.append(f"file '{fp.as_posix()}'" + "\n" + f"duration {max(dur, 0.001):.4f}")
        lines.append(f"file '{(self.fdir / f'f{len(self.frames)-1:05d}.jpg').as_posix()}'")
        lst = self.fdir / "list.txt"
        lst.write_text(chr(10).join(lines))
        self.t0 = t0
        return lst


def make_bg() -> Path:
    """Subtle vignette background (navy, matches the app's dark theme)."""
    import numpy as np
    from PIL import Image
    p = RAW / "bg_1080.png"
    if not p.exists():
        y, x = np.mgrid[0:1080, 0:1920]
        r = np.hypot(x - 960, y - 540) / 1100.0
        k = np.clip(1 - r, 0, 1)[..., None]
        c0 = np.array([8, 14, 21.0]); c1 = np.array([22, 36, 52.0])
        Image.fromarray((c0 + (c1 - c0) * k).astype("uint8")).save(p)
    return p


def compose(scene: str, lst: Path, d: Driver):
    """Place the phone video centered on a 1920x1080 frame with a subtle background."""
    out = OUT / f"{scene}.mp4"
    start = max(0.0, d.markers.get("loaded", d.t0) - d.t0 - 0.5)
    ph = 1000  # phone height on canvas
    pw_ = round(ph * VW / VH / 2) * 2
    bg = make_bg()
    fc = (
        f"[0:v]fps={FPS},trim=start={start:.2f},setpts=PTS-STARTPTS,scale={pw_}:{ph}:flags=lanczos,"
        f"pad={pw_+8}:{ph+8}:4:4:color=0x263648,format=yuv420p[ph];"
        f"[1:v][ph]overlay=(W-w)/2:(H-h)/2:shortest=1,scale=in_range=full:out_range=tv:flags=lanczos,format=yuv420p[v]"
    )
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-loop", "1", "-framerate", str(FPS), "-i", str(bg), "-filter_complex", fc, "-map", "[v]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-r", str(FPS),
           "-movflags", "+faststart", "-an", str(out)]
    subprocess.run(cmd, check=True)
    # stills
    for name, t in d.stills:
        tt = max(0.0, t - d.t0 - start)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{tt:.2f}", "-i", str(out), "-frames:v", "1",
                        str(OUT / f"{scene}_{name}.png")], check=True)
    markers = {k: round(v - d.t0 - start, 2) for k, v in d.markers.items()}
    allm = json.loads((OUT / "markers.json").read_text()) if (OUT / "markers.json").exists() else {}
    allm[scene] = markers
    (OUT / "markers.json").write_text(json.dumps(allm, indent=1))
    dur = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).decode().strip()
    print(f"{scene}: {float(dur):.1f}s -> {out}")


# ------------------------------------------------------------------ scenes
def a_certified(pw):
    d = Driver(pw, "a_certified")
    d.load()
    d.hold(0.8)
    d.still("capture")
    d.hold(1.8)  # viewfinder with the panel
    d.pick_sample("good-straight")
    d.wait_js("!document.querySelector('#busy').hidden", 10)
    d.still("busy")
    d.wait_result()
    d.hold(2.2)
    d.still("result_top")
    d.scroll_el("#gate", 1800, 120)
    d.hold(1.6)
    d.still("gate")
    d.scroll_el("#overlay-wrap", 2000, 70)
    d.hold(1.6)
    d.still("overlay")
    d.tap("#overlay-img")  # tap to zoom the annotated overlay
    d.hold(2.6)
    d.still("overlay_zoom")
    d.tap("#overlay-img")
    d.hold(0.8)
    d.scroll_el("#chips", 1800, 400)
    d.hold(1.8)
    d.scroll_to(0, 1600)
    d.hold(1.2)
    compose("a_certified", d.finish(), d)


def b_agent_loop(pw):
    d = Driver(pw, "b_agent_loop")
    d.load()
    d.hold(0.6)
    d.pick_sample("move-closer")
    d.wait_result()
    d.hold(2.0)
    d.still("refused_top")
    d.hold(2.0)
    d.scroll_el("#trace-panel", 2200, 70)
    d.hold(3.0)
    d.still("trace_step1")
    d.scroll_el("#btn-retake", 1500, 600)  # Retake lives at the bottom of the result view
    d.hold(0.6)
    d.mark("retake_tap")
    d.tap("#btn-retake")
    d.wait_js("!document.querySelector('#view-capture').hidden", 10)
    d.hold(1.0)
    d.pick_sample("closer")
    d.wait_result()
    d.hold(2.2)
    d.still("certified_top")
    d.scroll_el("#overlay-wrap", 2000, 70)
    d.hold(2.0)
    d.scroll_el("#trace-panel", 2200, 70)
    d.hold(3.5)
    d.still("trace_both")
    d.scroll_to(0, 1500)
    d.hold(1.0)
    compose("b_agent_loop", d.finish(), d)


def c_indicative(pw, name="c_indicative", policy="llm"):
    d = Driver(pw, name)
    d.load(policy)
    d.hold(0.6)
    d.pick_sample("blurry-oblique")
    d.wait_result()
    d.hold(2.4)
    d.still("result_top")
    d.scroll_el("#gate", 1800, 120)
    d.hold(2.0)
    d.scroll_el("#chips", 1800, 400)
    d.hold(2.0)
    d.still("chips")
    d.scroll_to(0, 1500)
    d.hold(1.0)
    compose(name, d.finish(), d)


def d_trace(pw):
    """Two-step session (too far -> closer), then slowly read the agent trace timeline."""
    d = Driver(pw, "d_trace")
    d.load()
    d.hold(0.4)
    d.pick_sample("move-closer")
    d.wait_result()
    d.hold(0.8)
    d.scroll_to(0, 600)
    d.page.evaluate("document.querySelector('#btn-retake').click()")
    d.wait_js("!document.querySelector('#view-capture').hidden", 10)
    d.hold(0.5)
    d.pick_sample("closer")
    d.wait_result()
    d.hold(0.8)
    d.scroll_el("#trace-panel", 1600, 60)
    d.hold(2.0)
    d.mark("trace_start")
    total = d.page.evaluate("document.querySelector('#trace-panel').getBoundingClientRect().height")
    steps = d.page.evaluate("document.querySelectorAll('#trace li.step').length")
    d.mark("steps_%d" % steps)
    # slow read: step 1 top, step 1 action, step 2 top, step 2 action
    for i in range(steps):
        d.scroll_el(f"#trace li.step:nth-child({i+1})", 1800, 70)
        d.hold(3.2)
        d.still(f"step{i+1}")
        d.scroll_el(f"#trace li.step:nth-child({i+1}) .act", 1400, 300)
        d.hold(2.2)
    d.hold(1.0)
    compose("d_trace", d.finish(), d)


def c_hold_steady(pw):
    """Same blurry photo with the free rules policy: the agent asks to hold steadier (amber banner)."""
    c_indicative(pw, "c_hold_steady", "rules")


SCENES = {"a_certified": a_certified, "b_agent_loop": b_agent_loop, "c_indicative": c_indicative, "c_hold_steady": c_hold_steady, "d_trace": d_trace}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or list(SCENES)
    with sync_playwright() as pw:
        for n in names:
            SCENES[n](pw)
