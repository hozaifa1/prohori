"""Build docs/report/Prohori_Technical_Report.pdf from docs/report/REPORT.md.

Usage:  python tools/make_report_pdf.py [--html-only] [--src PATH] [--out PATH]

Pipeline: markdown -> HTML (small built-in converter; no third-party markdown
package needed) -> PDF via Playwright Chromium (A4, print stylesheet, page
numbers in the footer).  Falls back to a plain reportlab render if Chromium
cannot be launched.  HTML comments (e.g. AGENT_RESULTS_PENDING markers) are
stripped.  Missing images abort the build.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "report" / "REPORT.md"
OUT = ROOT / "docs" / "report" / "Prohori_Technical_Report.pdf"
TITLE = "PROHORI Technical Report"
AUTHOR = "Hozaifa, University of Dhaka"

# --------------------------------------------------------------------------
# Inline markdown
# --------------------------------------------------------------------------


class Inline:
    """Inline converter with a placeholder stash so generated HTML is never re-parsed."""

    def __init__(self, base: Path):
        self.base = base
        self.stash: list[str] = []
        self.images: list[Path] = []

    def _hold(self, s: str) -> str:
        self.stash.append(s)
        return f"\x00{len(self.stash) - 1}\x00"

    def render(self, text: str) -> str:
        # code spans first
        text = re.sub(r"`([^`]+)`", lambda m: self._hold("<code>" + re.sub(r"([/,])(?=\S)", r"\1<wbr>", html.escape(m.group(1), quote=False)) + "</code>"), text)
        # images (inline use is rare; block images are handled elsewhere)
        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: self._hold(self.img_tag(m.group(2), m.group(1))), text)
        # links
        text = re.sub(
            r"\[([^\]]+)\]\(([^)\s]+)\)",
            lambda m: self._hold(f'<a href="{html.escape(m.group(2))}">{self._inner(m.group(1))}</a>'),
            text,
        )
        # bare URLs
        def bare(m):
            url = m.group(0)
            trail = ""
            while url and url[-1] in ".,;:)":
                trail = url[-1] + trail
                url = url[:-1]
            return self._hold(f'<a href="{html.escape(url)}">{html.escape(url)}</a>') + trail

        text = re.sub(r"https?://[^\s<>\x00]+", bare, text)
        text = self._inner(text)
        return self._restore(text)

    def _inner(self, text: str) -> str:
        text = html.escape(text, quote=False)
        text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<![\w*])\*(?=[^\s*])([^*]+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", text)
        return text

    def _restore(self, text: str) -> str:
        while "\x00" in text:
            text = re.sub(r"\x00(\d+)\x00", lambda m: self.stash[int(m.group(1))], text)
        return text

    def img_tag(self, src: str, alt: str) -> str:
        p = (self.base / src).resolve()
        self.images.append(p)
        return f'<img src="{p.as_uri()}" alt="{html.escape(alt)}">'


# --------------------------------------------------------------------------
# Block markdown
# --------------------------------------------------------------------------

RE_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
RE_UL = re.compile(r"^(\s*)[*-]\s+(.*)$")
RE_OL = re.compile(r"^(\s*)\d+\.\s+(.*)$")
RE_IMG = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
RE_TROW = re.compile(r"^\s*\|.*\|\s*$")
RE_TSEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells, cur, in_code = [], "", False
    for ch in line:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def is_block_start(line: str) -> bool:
    return bool(
        RE_HEAD.match(line) or RE_UL.match(line) or RE_OL.match(line) or RE_IMG.match(line)
        or line.startswith("```") or RE_TROW.match(line)
    )


def convert(md: str, base: Path) -> tuple[str, list[Path], str]:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)  # strip HTML comments
    lines = md.replace("\r\n", "\n").split("\n")
    inl = Inline(base)
    out: list[str] = []
    title = TITLE
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
            continue
        m = RE_HEAD.match(line)
        if m:
            level = len(m.group(1))
            body = inl.render(m.group(2))
            if level == 1:
                title = re.sub(r"<[^>]+>", "", body)
                out.append(f'<h1>{body}</h1>')
            else:
                slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", body).lower()).strip("-")
                out.append(f'<h{level} id="{slug}">{body}</h{level}>')
            i += 1
            continue
        m = RE_IMG.match(line)
        if m:
            alt, src = m.group(1), m.group(2)
            out.append(f"<figure>{inl.img_tag(src, alt)}<figcaption>{inl.render(alt)}</figcaption></figure>")
            i += 1
            continue
        if RE_TROW.match(line) and i + 1 < n and RE_TSEP.match(lines[i + 1]):
            head = split_row(line)
            sep = split_row(lines[i + 1])
            aligns = [("right" if c.endswith(":") and not c.startswith(":") else "center" if c.startswith(":") and c.endswith(":") else "left") for c in sep]
            i += 2
            rows = []
            while i < n and RE_TROW.match(lines[i]):
                rows.append(split_row(lines[i]))
                i += 1
            ncol = len(head)
            h = "".join(f'<th style="text-align:{aligns[k] if k < len(aligns) else "left"}">{inl.render(c)}</th>' for k, c in enumerate(head))
            body = []
            for r in rows:
                r = (r + [""] * ncol)[:ncol]
                body.append("<tr>" + "".join(f'<td style="text-align:{aligns[k] if k < len(aligns) else "left"}">{inl.render(c)}</td>' for k, c in enumerate(r)) + "</tr>")
            cls = "wide" if ncol >= 7 else ("mid" if ncol >= 5 else "")
            if len(rows) <= 7:
                cls += " keep"
            out.append(f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table>')
            continue
        m_ul, m_ol = RE_UL.match(line), RE_OL.match(line)
        if m_ul or m_ol:
            tag = "ul" if m_ul else "ol"
            rx = RE_UL if m_ul else RE_OL
            items: list[str] = []
            while i < n:
                mm = rx.match(lines[i])
                if mm:
                    items.append(mm.group(2))
                    i += 1
                    continue
                # indented continuation
                if lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                    continue
                # blank line followed by another item of the same list
                j = i
                while j < n and not lines[j].strip():
                    j += 1
                if j > i and j < n and rx.match(lines[j]):
                    i = j
                    continue
                break
            out.append(f"<{tag}>" + "".join(f"<li>{inl.render(t)}</li>" for t in items) + f"</{tag}>")
            continue
        # paragraph: consecutive plain lines, soft breaks kept as <br>
        buf = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + "<br>\n".join(inl.render(b) for b in buf) + "</p>")
    return "\n".join(out), inl.images, title


# --------------------------------------------------------------------------
# Print stylesheet
# --------------------------------------------------------------------------

CSS = """
@page { size: A4; margin: 18mm 18mm 20mm 18mm; }
* { box-sizing: border-box; }
html { font-family: Cambria, Georgia, "Times New Roman", "DejaVu Serif", serif;
       font-size: 10.5pt; line-height: 1.38; color: #1a1a1a;
       -webkit-print-color-adjust: exact; print-color-adjust: exact;
       font-variant-ligatures: common-ligatures; hyphens: manual; }
body { margin: 0; overflow-wrap: break-word; }
h1 { font-size: 17pt; line-height: 1.2; margin: 0 0 6pt; color: #0b2a4a; }
h2 { font-size: 13.2pt; margin: 15pt 0 5pt; color: #0b2a4a; border-bottom: 0.6pt solid #9fb3c8;
     padding-bottom: 2pt; break-after: avoid; page-break-after: avoid; }
h3 { font-size: 11.2pt; margin: 11pt 0 3pt; color: #0b2a4a; break-after: avoid; page-break-after: avoid; }
h4 { font-size: 10.5pt; margin: 9pt 0 2pt; break-after: avoid; page-break-after: avoid; }
p { margin: 0 0 6pt; orphans: 3; widows: 3; text-align: left; }
h1 + p { color: #333; }
ul, ol { margin: 0 0 6pt; padding-left: 16pt; }
li { margin: 0 0 2pt; orphans: 2; widows: 2; }
a { color: #0b4f9c; text-decoration: none; border-bottom: 0.4pt solid #8fb0d6; }
code { font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 8.9pt; background: #f1f3f5;
       padding: 0 1.5pt; border-radius: 2pt; overflow-wrap: break-word; }
pre { background: #f5f6f8; border: 0.5pt solid #d5dae0; border-radius: 3pt; padding: 6pt 8pt; margin: 4pt 0 8pt;
      font-size: 7.6pt; line-height: 1.32; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
figure { margin: 8pt 0 10pt; text-align: center; break-inside: avoid; page-break-inside: avoid; }
figure img { max-width: 100%; max-height: 100mm; width: auto; height: auto; object-fit: contain; display: block; margin: 0 auto; }
figcaption { font-size: 8.8pt; color: #444; margin-top: 3pt; font-style: italic; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0 9pt; font-size: 8.7pt; line-height: 1.28;
        table-layout: auto; font-family: Calibri, "Segoe UI", "DejaVu Sans", sans-serif; }
table.mid { font-size: 8.2pt; }
table.wide { font-size: 7.6pt; }
th, td { padding: 2.6pt 4.5pt; vertical-align: top; border-bottom: 0.4pt solid #cfd6de; overflow-wrap: break-word; }
table.keep { break-inside: avoid; page-break-inside: avoid; }
th { border-top: 0.9pt solid #0b2a4a; border-bottom: 0.9pt solid #0b2a4a; background: #eef2f6; text-align: left; font-weight: 700; }
table code { font-size: 0.93em; padding: 0; background: none; }
tr { break-inside: avoid; page-break-inside: avoid; }
thead { display: table-header-group; }
tbody tr:nth-child(-n+2) { break-after: avoid; page-break-after: avoid; }
tbody tr:nth-last-child(-n+2) { break-before: avoid; page-break-before: avoid; }
strong { font-weight: 700; }
"""

FOOTER = (
    '<div style="width:100%;font-family:Georgia,serif;font-size:8px;color:#666;'
    'padding:0 18mm;display:flex;justify-content:space-between;">'
    '<span>PROHORI technical report</span>'
    '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>'
)


def build_html(body: str, title: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(TITLE)}</title><style>{CSS}</style></head><body>{body}</body></html>"
    )


# --------------------------------------------------------------------------
# PDF back ends
# --------------------------------------------------------------------------


def pdf_chromium(html_path: Path, out: Path) -> list[str]:
    from playwright.sync_api import sync_playwright

    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        broken = page.evaluate("[...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)")
        if broken:
            raise SystemExit(f"broken images: {broken}")
        overflow = page.evaluate(
            "[...document.querySelectorAll('table, pre, figure img')]"
            ".filter(e => e.scrollWidth > e.clientWidth + 1 || e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)"
            ".map(e => e.tagName + ':' + (e.textContent || e.alt || '').slice(0, 50))"
        )
        problems += [f"possible horizontal overflow: {o}" for o in overflow]
        # images keep native resolution; report any rendered below ~150 dpi equivalent
        low = page.evaluate(
            "[...document.images].filter(i => i.naturalWidth / (i.getBoundingClientRect().width / 96) < 150)"
            ".map(i => i.alt + ' ' + Math.round(i.naturalWidth / (i.getBoundingClientRect().width / 96)) + ' dpi')"
        )
        problems += [f"low-resolution image: {x}" for x in low]
        page.pdf(
            path=str(out), format="A4", print_background=True, prefer_css_page_size=True,
            display_header_footer=True, header_template="<div></div>", footer_template=FOOTER,
            margin={"top": "18mm", "bottom": "20mm", "left": "18mm", "right": "18mm"},
        )
        browser.close()
    return problems


def pdf_reportlab(md_body_text: str, out: Path) -> None:  # pragma: no cover - fallback only
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm)
    flow = []
    for block in re.split(r"\n\s*\n", re.sub(r"<!--.*?-->", "", md_body_text, flags=re.S)):
        t = html.escape(block.strip()).replace("\n", "<br/>")
        if not t:
            continue
        style = styles["Heading2"] if block.lstrip().startswith("#") else styles["BodyText"]
        flow += [Paragraph(t.lstrip("# "), style), Spacer(1, 4)]
    doc.build(flow)


def set_metadata(out: Path, title: str) -> None:
    try:
        import pymupdf as fitz
    except ImportError:
        return
    doc = fitz.open(out)
    meta = doc.metadata or {}
    meta.update({"title": title, "author": AUTHOR, "subject": "OpenCV AI Competition 2026 technical report"})
    doc.set_metadata(meta)
    tmp = out.with_suffix(".tmp.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--html-only", action="store_true", help="write the HTML next to the PDF and stop")
    a = ap.parse_args()

    md = a.src.read_text(encoding="utf-8")
    body, images, title = convert(md, a.src.parent)
    missing = sorted({str(p) for p in images if not p.exists()})
    if missing:
        print("MISSING IMAGES:", *missing, sep="\n  ")
        return 2
    if "AGENT_RESULTS" in body:
        print("marker leaked into output")
        return 3
    doc = build_html(body, title)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.html_only:
        h = a.out.with_suffix(".html")
        h.write_text(doc, encoding="utf-8")
        print("wrote", h)
        return 0
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "report.html"
        hp.write_text(doc, encoding="utf-8")
        try:
            problems = pdf_chromium(hp, a.out)
        except SystemExit:
            raise
        except Exception as e:  # Chromium unavailable -> plain fallback
            print("Chromium failed (%s); using reportlab fallback" % e)
            pdf_reportlab(md, a.out)
            problems = ["reportlab fallback used: no tables/figures"]
    set_metadata(a.out, title)
    try:
        import pymupdf as fitz
        n = len(fitz.open(a.out))
    except ImportError:
        n = "?"
    print(f"wrote {a.out} ({n} pages, {a.out.stat().st_size // 1024} KB)")
    for p in problems:
        print("WARNING:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
