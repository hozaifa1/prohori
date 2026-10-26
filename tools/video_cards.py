"""Render title/closing/context cards for the demo video as 1920x1080 PNGs (HTML -> Playwright).

Usage: python tools/video_cards.py
Output: docs/video/assets/cards/*.png
Style tokens come from service/static/style.css (dark theme, Geist / Geist Mono, amber accent).
"""
from __future__ import annotations

import base64
import csv
import io
from pathlib import Path

import qrcode
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "video" / "assets" / "cards"
STATIC = ROOT / "service" / "static"
LIVE = "https://184-194-241-186.sslip.io"
GITHUB = "https://github.com/hozaifa1/prohori"


def b64(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def qr_uri(url: str) -> str:
    q = qrcode.QRCode(border=2, box_size=16, error_correction=qrcode.constants.ERROR_CORRECT_Q)
    q.add_data(url)
    q.make(fit=True)
    img = q.make_image(fill_color="#0a121a", back_color="#ffffff").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


CSS = f"""
@font-face {{ font-family: Geist; src: url({b64(STATIC/'fonts/geist-latin-wght-normal.woff2','font/woff2')}) format('woff2'); font-weight:100 900; }}
@font-face {{ font-family: 'Geist Mono'; src: url({b64(STATIC/'fonts/geist-mono-latin-wght-normal.woff2','font/woff2')}) format('woff2'); font-weight:100 900; }}
:root {{ --bg:#0a121a; --surface:#111c27; --surface-2:#1a2838; --line:#263648; --text:#e8eef4; --muted:#9db0c1;
  --amber:#ffbf3c; --ok:#46d27a; --bad:#ff7a6e; }}
* {{ box-sizing:border-box; margin:0; }}
html,body {{ width:1920px; height:1080px; overflow:hidden; background:var(--bg); color:var(--text);
  font-family:Geist,system-ui,sans-serif; -webkit-font-smoothing:antialiased; }}
.frame {{ position:relative; width:1920px; height:1080px; padding:96px 140px;
  background: radial-gradient(1200px 800px at 50% 45%, #16243400 0%, #0a121a 100%), radial-gradient(900px 600px at 30% 40%, #14202e 0%, #0a121a 70%); }}
.mono {{ font-family:'Geist Mono',monospace; }}
.amber {{ color:var(--amber); }}
.muted {{ color:var(--muted); }}
.tag {{ font:600 28px/1 'Geist Mono',monospace; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }}
.rule {{ height:6px; width:140px; background:var(--amber); border-radius:3px; }}
"""


def page(body: str, extra_css: str = "") -> str:
    return f"<!doctype html><meta charset=utf-8><style>{CSS}{extra_css}</style><div class=frame>{body}</div>"


def title_card() -> str:
    icon = b64(STATIC / "icon-512.png", "image/png")
    return page(f"""
<div style="display:flex;flex-direction:column;justify-content:center;height:100%;gap:44px">
  <div style="display:flex;align-items:center;gap:44px">
    <img src="{icon}" width=190 height=190 style="border-radius:40px;box-shadow:0 20px 60px -20px #000">
    <div>
      <div style="font:750 188px/1 Geist;letter-spacing:.14em">PROHORI</div>
      <div class=tag style="margin-top:20px">প্রহরী &nbsp;=&nbsp; sentry, in Bengali</div>
    </div>
  </div>
  <div class=rule></div>
  <div style="font:600 66px/1.18 Geist;max-width:1500px">Crack width in millimetres from a phone photo,<br>
    and it <span class=amber>refuses</span> when unsure.</div>
  <div class="tag" style="margin-top:12px">OpenCV AI Competition 2026</div>
</div>""")


def closing_card() -> str:
    qr = qr_uri(LIVE)
    return page(f"""
<div style="display:flex;align-items:center;justify-content:space-between;height:100%;gap:80px">
  <div style="display:flex;flex-direction:column;gap:38px">
    <div style="font:750 120px/1 Geist;letter-spacing:.14em">PROHORI</div>
    <div class=rule></div>
    <div>
      <div class=tag>Try it live</div>
      <div class="mono amber" style="font:600 64px/1.2 'Geist Mono';margin-top:12px">184-194-241-186.sslip.io</div>
    </div>
    <div>
      <div class=tag>Code, data and every result</div>
      <div class=mono style="font:600 54px/1.2 'Geist Mono';margin-top:12px">github.com/hozaifa1/prohori</div>
    </div>
    <div class=tag style="margin-top:20px">OpenCV AI Competition 2026</div>
  </div>
  <div style="background:#fff;padding:26px;border-radius:30px;box-shadow:0 30px 80px -30px #000">
    <img src="{qr}" width=560 height=560 style="display:block">
    <div class=mono style="color:#0a121a;text-align:center;font:600 28px/1 'Geist Mono';margin-top:12px">scan to open the app</div>
  </div>
</div>""")


def rana_card() -> str:
    return page("""
<div style="display:flex;flex-direction:column;justify-content:center;height:100%;gap:40px">
  <div class=tag>24 April 2013 &nbsp;/&nbsp; Savar, Bangladesh</div>
  <div class=rule></div>
  <div style="font:750 130px/1.05 Geist">Rana Plaza.</div>
  <div style="font:500 68px/1.25 Geist;max-width:1500px;color:var(--text)">
    Cracks were reported <span class=amber>the day before</span>.<br>
    The building collapsed with workers inside.
  </div>
  <div style="display:flex;align-items:baseline;gap:30px;margin-top:10px">
    <div style="font:750 200px/1 Geist;color:var(--bad)">1,134</div>
    <div style="font:600 64px/1.1 Geist">people died.</div>
  </div>
  <div class="mono muted" style="font:500 26px/1.3 'Geist Mono';position:absolute;left:140px;bottom:56px">
    Sources: ILO Rana Plaza Compensation Scheme; Wikipedia, Rana Plaza collapse. See docs/video/CREDITS.md.</div>
</div>""")


def comparator_card() -> str:
    # simple original vector illustration of a plastic crack-width gauge card (not a copy of any product; not to scale)
    widths = [0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0]
    k = 26.0  # drawn px per mm
    rows, y = [], 118.0
    for w in widths:
        h = max(w * k, 3.0)
        y += max(h / 2, 12)
        rows.append(f'<rect x="90" y="{y - h/2:.1f}" width="440" height="{h:.1f}" fill="#101a24"/>'
                    f'<text x="560" y="{y + 11:.1f}" font-family="Geist Mono" font-size="32" font-weight="600" fill="#101a24">{w:g} mm</text>')
        y += max(h / 2 + 22, 30) if h < 20 else h / 2 + 22
    H_card = y + 10
    crack = ('<path d="M 150 40 L 190 150 L 160 250 L 225 360 L 195 450 L 250 540 L 232 600" '
             'fill="none" stroke="#e8eef4" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>'
             '<path d="M 190 150 L 245 190" fill="none" stroke="#e8eef4" stroke-width="3" stroke-linecap="round"/>'
             '<path d="M 225 360 L 170 395" fill="none" stroke="#e8eef4" stroke-width="3" stroke-linecap="round"/>')
    svg = f"""
<svg width="1500" height="{H_card + 20:.0f}" viewBox="0 0 1500 {H_card + 20:.0f}" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="10" width="740" height="{H_card:.0f}" rx="40" fill="#ffbf3c"/>
  <rect x="16" y="26" width="708" height="{H_card - 32:.0f}" rx="28" fill="none" stroke="#101a24" stroke-opacity=".25" stroke-width="3"/>
  <text x="90" y="82" font-family="Geist" font-weight="750" font-size="38" fill="#101a24" letter-spacing="3">CRACK WIDTH GAUGE</text>
  {''.join(rows)}
  <g transform="translate(900,0)">
    <rect x="0" y="10" width="420" height="{H_card:.0f}" rx="26" fill="#2a3544"/>
    {crack}
  </g>
</svg>"""
    return page(f"""
<div class=tag>How crack width is judged today</div>
<div style="font:750 74px/1.08 Geist;margin-top:22px">A plastic card, held up by hand, read <span class=amber>by eye</span>.</div>
<div style="display:flex;justify-content:center;margin-top:34px;transform-origin:top center;transform:scale(1.08)">{svg}</div>
<div class="muted" style="font:500 28px/1.3 Geist;position:absolute;right:140px;bottom:46px">Illustration, not to scale.</div>
""")


def cool_card() -> str:
    # numbers: eval/results/cool/20261025T002750Z/REPORT.md section 0 (c8g.xlarge unless stated)
    rows = [
        ("Accuracy vs printed truth", "0.1218 mm", "0.1219 mm", "same"),
        ("Width change per crack", "reference", "max 0.030 mm", "build noise"),
        ("Speed, end to end", "1.00x", "1.014x", "break-even"),
        ("Cost per 1,000 photos", "baseline", "+6.8 %", "COOL fee"),
        ("Threads > 1", "works", "crashed", "worked around"),
    ]
    trs = "".join(
        f"<tr><td>{a}</td><td class=mono>{b}</td><td class='mono amber'>{c}</td><td class=muted>{d}</td></tr>"
        for a, b, c, d in rows)
    return page(f"""
<div class=tag>COOL on Graviton4 &nbsp;/&nbsp; OpenCV 5.1.0-dev</div>
<div style="font:750 70px/1.08 Geist;margin:22px 0 34px">Same widths, same speed.<br>One crash, found and worked around.</div>
<table>
<thead><tr><th></th><th>pip OpenCV 5.0</th><th>COOL</th><th></th></tr></thead>
<tbody>{trs}</tbody></table>
<div class="mono muted" style="font:500 22px/1.3 'Geist Mono';position:absolute;left:140px;bottom:44px">
Source: eval/results/cool/20261025T002750Z/REPORT.md. 85 frames, c8g.xlarge. Crash: multithreaded connectedComponents.</div>
""", """
table { border-collapse:collapse; width:100%; }
th { text-align:left; font:600 26px 'Geist Mono'; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); padding:0 20px 16px; border-bottom:2px solid var(--line); }
td { padding:20px 20px; border-bottom:1px solid var(--line); font-size:38px; white-space:nowrap; }
td.mono { font-size:36px; }
td:first-child { font-weight:600; width:640px; }
""")


def published_card() -> str:
    # numbers: eval/results/width_eval.md ("Against the published numbers"), held-out TEST, printed panel
    rows = [
        ("Mean absolute error, all widths", "0.070 mm", "certified: 0.056 mm", "0.09 mm", "Deng 2026"),
        ("Spread (COV), cracks under 0.5 mm", "13.1 %", "", "21.9 %", "Hassouna 2026"),
        ("Spread (COV), cracks 0.5 mm and wider", "7.0 %", "", "5.8 %", "Hassouna 2026"),
    ]
    trs = "".join(
        f"<tr><td>{a}</td><td class='mono amber'>{b}<div class='sub'>{c}</div></td><td class=mono>{d}</td><td class=muted>{e}</td></tr>"
        for a, b, c, d, e in rows)
    return page(f"""
<div class=tag>Held-out test vs recent published smartphone methods</div>
<div style="font:750 70px/1.08 Geist;margin:22px 0 34px">Certified readings meet the<br>published accuracy bar.</div>
<table>
<thead><tr><th></th><th>Prohori</th><th>Published</th><th>Source</th></tr></thead>
<tbody>{trs}</tbody></table>
<div class="muted" style="font:500 28px/1.35 Geist;margin-top:34px;max-width:1600px">Context, not a head-to-head: the published methods used other targets and conditions. Prohori: one printed sheet, one phone, 8 test photos, truth known to 0.009 mm.</div>
<div class="mono muted" style="font:500 22px/1.3 'Geist Mono';position:absolute;left:140px;bottom:44px">Source: eval/results/width_eval.md, section "Against the published numbers".</div>
""", """
table { border-collapse:collapse; width:100%; }
th { text-align:left; font:600 26px 'Geist Mono'; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); padding:0 20px 16px; border-bottom:2px solid var(--line); }
td { padding:22px 20px; border-bottom:1px solid var(--line); font-size:36px; vertical-align:middle; white-space:nowrap; }
td.mono { font-size:44px; font-weight:600; }
td:first-child { font-weight:600; width:740px; }
td:last-child { font-size:32px; }
.sub { font:500 24px 'Geist Mono'; color:var(--ok); margin-top:4px; }
""")


CARDS = {
    "title": title_card, "closing": closing_card, "rana_plaza": rana_card,
    "crack_comparator": comparator_card, "cool_vs_pip": cool_card, "published_comparison": published_card,
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        for name, fn in CARDS.items():
            pg.set_content(fn(), wait_until="load")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / f"{name}.png"))
            print("wrote", name)
        b.close()
