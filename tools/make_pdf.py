"""Render a restricted-Markdown file to a clean A4 PDF with reportlab.

Supports: # / ## / ### headings, - bullets, 1. numbered, **bold**, *italic*,
`code`, --- rules, | pipe tables |, ![alt](img.png) images, and blank-line paras.
Deliberately small: the grant form only accepts a PDF, and this has to be
reproducible from the repo with no pandoc/LaTeX install.

Usage: python make_pdf.py input.md output.pdf ["Doc Title"]
"""
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, Image,
                                KeepTogether, ListFlowable, ListItem, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

INK = colors.HexColor("#111418")
MUTED = colors.HexColor("#5b6470")
RULE = colors.HexColor("#d4d9e0")
ACCENT = colors.HexColor("#0b6bcb")
BAND = colors.HexColor("#eef2f7")


def styles():
    ss = getSampleStyleSheet()
    base = dict(fontName="Helvetica", textColor=INK, leading=11.6)
    return {
        "h1": ParagraphStyle("h1", ss["Normal"], fontName="Helvetica-Bold",
                             fontSize=16, leading=19.5, textColor=INK,
                             spaceBefore=2, spaceAfter=5, keepWithNext=True),
        "h2": ParagraphStyle("h2", ss["Normal"], fontName="Helvetica-Bold",
                             fontSize=11.2, leading=14.0, textColor=ACCENT,
                             spaceBefore=5, spaceAfter=3.5, keepWithNext=True),
        "h3": ParagraphStyle("h3", ss["Normal"], fontName="Helvetica-Bold",
                             fontSize=9.5, leading=11.6, textColor=INK,
                             spaceBefore=5, spaceAfter=2.5, keepWithNext=True),
        "body": ParagraphStyle("body", ss["Normal"], fontSize=8.7,
                               alignment=TA_JUSTIFY, spaceAfter=2.8, **base),
        "bullet": ParagraphStyle("bullet", ss["Normal"], fontSize=8.7,
                                 spaceAfter=1.8, **base),
        "cell": ParagraphStyle("cell", ss["Normal"], fontSize=8.0, leading=10.2,
                               fontName="Helvetica", textColor=INK),
        "cellh": ParagraphStyle("cellh", ss["Normal"], fontSize=8.0, leading=10.2,
                                fontName="Helvetica-Bold", textColor=INK),
        "cap": ParagraphStyle("cap", ss["Normal"], fontSize=7.6, leading=9.5,
                              fontName="Helvetica-Oblique", textColor=MUTED,
                              spaceBefore=2.5, spaceAfter=6),
    }


def inline(t):
    t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    t = re.sub(r"`([^`]+)`",
               r'<font face="Courier" size="8.2" color="#8a2f6b">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
               r'<link href="\2" color="#0b6bcb">\1</link>', t)
    t = re.sub(r"(?<![\">])(https?://[^\s<)]+)",
               r'<link href="\1" color="#0b6bcb">\1</link>', t)
    return t


def table_from(rows, S, width):
    cleaned = [r for r in rows if not re.fullmatch(r"\s*\|[\s:|-]+\|\s*", r)]
    grid = [[c.strip() for c in r.strip().strip("|").split("|")] for r in cleaned]
    ncol = max(len(r) for r in grid)
    grid = [r + [""] * (ncol - len(r)) for r in grid]
    data = [[Paragraph(inline(c), S["cellh" if i == 0 else "cell"]) for c in row]
            for i, row in enumerate(grid)]
    first = max(0.20, min(0.46, 1.0 - 0.62)) if ncol > 2 else 0.5
    rest = (1.0 - first) / (ncol - 1) if ncol > 1 else 1.0
    cw = [width * first] + [width * rest] * (ncol - 1) if ncol > 1 else [width]
    t = Table(data, colWidths=cw, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE),
        ("INNERGRID", (0, 1), (-1, -1), 0.3, RULE),
        ("BOX", (0, 0), (-1, -1), 0.55, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
    ]))
    return t


def build(md_path, pdf_path, title=None, footer=""):
    S = styles()
    src = Path(md_path).read_text(encoding="utf-8").splitlines()
    doc = BaseDocTemplate(str(pdf_path), pagesize=A4,
                          leftMargin=16 * mm, rightMargin=16 * mm,
                          topMargin=11 * mm, bottomMargin=11 * mm,
                          title=title or Path(md_path).stem,
                          author="S M Hozaifa Hossain")
    W = doc.width

    def deco(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(MUTED)
        if footer:
            canvas.drawString(d.leftMargin, 9 * mm, footer)
        canvas.drawRightString(d.leftMargin + d.width, 9 * mm,
                               "Page %d" % canvas.getPageNumber())
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(d.leftMargin, 11.5 * mm, d.leftMargin + d.width, 11.5 * mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(
        id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width,
                              doc.height, id="f")], onPage=deco)])

    flow, i = [], 0
    while i < len(src):
        ln = src[i].rstrip()
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("|") and ln.count("|") >= 2:
            blk = []
            while i < len(src) and src[i].strip().startswith("|"):
                blk.append(src[i])
                i += 1
            flow += [Spacer(1, 2), table_from(blk, S, W), Spacer(1, 5)]
            continue
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", ln.strip())
        if m:
            p = Path(md_path).parent / m.group(2)
            if p.exists():
                from reportlab.lib.utils import ImageReader
                iw, ih = ImageReader(str(p)).getSize()
                w = 440
                flow += [Image(str(p), width=w, height=w * ih / iw, hAlign="CENTER"),
                         Spacer(1, 2), Paragraph(inline(m.group(1)), S["cap"]), Spacer(1, 3)]
            i += 1
            continue
        if re.fullmatch(r"-{3,}", ln.strip()):
            flow.append(HRFlowable(width="100%", thickness=0.5, color=RULE,
                                   spaceBefore=5, spaceAfter=7))
            i += 1
            continue
        if ln.startswith("### "):
            flow.append(Paragraph(inline(ln[4:]), S["h3"]))
            i += 1
            continue
        if ln.startswith("## "):
            h_p = Paragraph(inline(ln[3:]), S["h2"])
            # check if next non-empty line is an image
            next_idx = i + 1
            while next_idx < len(src) and not src[next_idx].strip():
                next_idx += 1
            if next_idx < len(src) and re.match(r"!\[([^\]]*)\]\(([^)]+)\)", src[next_idx].strip()):
                m_img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", src[next_idx].strip())
                p_img = Path(md_path).parent / m_img.group(2)
                if p_img.exists():
                    from reportlab.lib.utils import ImageReader
                    iw, ih = ImageReader(str(p_img)).getSize()
                    w = 440
                    flow.append(KeepTogether([
                        h_p,
                        Spacer(1, 2),
                        Image(str(p_img), width=w, height=w * ih / iw, hAlign="CENTER"),
                        Spacer(1, 2),
                        Paragraph(inline(m_img.group(1)), S["cap"]),
                        Spacer(1, 3)
                    ]))
                    i = next_idx + 1
                    continue
            flow.append(h_p)
            i += 1
            continue
        if ln.startswith("# "):
            flow.append(Paragraph(inline(ln[2:]), S["h1"]))
            i += 1
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            items, numbered = [], bool(re.match(r"^\s*\d+\.", ln))
            while i < len(src) and re.match(r"^\s*([-*]|\d+\.)\s+", src[i]):
                txt = re.sub(r"^\s*([-*]|\d+\.)\s+", "", src[i].rstrip())
                items.append(ListItem(Paragraph(inline(txt), S["bullet"]),
                                      leftIndent=12))
                i += 1
            flow += [ListFlowable(items, bulletType="1" if numbered else "bullet",
                                  bulletFontSize=7, leftIndent=13,
                                  bulletColor=ACCENT),
                     Spacer(1, 4)]
            continue
        para = [ln]
        i += 1
        while i < len(src) and src[i].strip() and not re.match(
                r"^(\s*([-*]|\d+\.)\s+|#{1,3} |\||!\[|-{3,}$)", src[i]):
            para.append(src[i].rstrip())
            i += 1
        flow.append(Paragraph(inline(" ".join(para)), S["body"]))

    doc.build(flow)
    print("wrote", pdf_path, Path(pdf_path).stat().st_size, "bytes")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2],
          sys.argv[3] if len(sys.argv) > 3 else None,
          sys.argv[4] if len(sys.argv) > 4 else "")
