"""Render study content (Markdown) to a downloadable PDF.

Uses ``fpdf2`` — pure Python, no system libraries — so it runs on any host. The
output is real selectable text. Handles headings, bullet / numbered lists, block
quotes, fenced code, horizontal rules, simple pipe tables and inline
``**bold**`` / ``*italic*``.
"""

from __future__ import annotations

import re

_H_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUM_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")
_HR_RE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _md_inline(text: str) -> str:
    """Normalise Markdown inline syntax to what fpdf2's markdown mode expects."""
    text = text.replace("__", "**")  # fpdf uses __ for underline; treat as bold
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"__\1__", text)  # *italic* -> __italic__ (fpdf italic)
    text = text.replace("`", "")
    return text


def markdown_to_pdf(title: str, markdown: str, *, footer: str = "StudyBuddy") -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    epw = pdf.epw

    def text_block(s: str, *, size: int = 11, style: str = "", gap: float = 2.0, indent: float = 0.0):
        pdf.set_font("Helvetica", style=style, size=size)
        if indent:
            pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(
            epw - indent, size * 0.55, _md_inline(s).strip(), markdown=True, new_x="LMARGIN", new_y="NEXT"
        )
        pdf.ln(gap)

    # title
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.multi_cell(epw, 9, title.strip(), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    lines = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    in_code = False
    code_buf: list[str] = []
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        if line.strip().startswith("```"):
            if in_code:
                pdf.set_font("Courier", size=9)
                pdf.set_fill_color(244, 242, 238)
                for c in code_buf:
                    pdf.multi_cell(epw, 4.6, c or " ", fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                code_buf, in_code = [], False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(raw)
            i += 1
            continue

        if not line.strip():
            pdf.ln(2)
            i += 1
            continue

        if _HR_RE.match(line):
            y = pdf.get_y()
            pdf.set_draw_color(200, 196, 188)
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(4)
            i += 1
            continue

        h = _H_RE.match(line)
        if h:
            level = len(h.group(1))
            size = {1: 15, 2: 13, 3: 12}.get(level, 11)
            pdf.ln(2)
            text_block(h.group(2), size=size, style="B", gap=1.5)
            i += 1
            continue

        # table: header line followed by a separator
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            rows: list[list[str]] = []
            j = i
            while j < len(lines) and "|" in lines[j]:
                if _TABLE_SEP_RE.match(lines[j]):
                    j += 1
                    continue
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                rows.append(cells)
                j += 1
            _render_table(pdf, rows, epw)
            i = j
            continue

        b = _BULLET_RE.match(line)
        if b:
            pdf.set_font("Helvetica", size=11)
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(epw - 4, 6, "- " + _md_inline(b.group(1)), markdown=True, new_x="LMARGIN", new_y="NEXT")
            i += 1
            continue

        n = _NUM_RE.match(line)
        if n:
            pdf.set_font("Helvetica", size=11)
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(
                epw - 4, 6, f"{n.group(1)}. " + _md_inline(n.group(2)),
                markdown=True, new_x="LMARGIN", new_y="NEXT",
            )
            i += 1
            continue

        if line.lstrip().startswith(">"):
            text_block(line.lstrip()[1:].strip(), style="I", indent=4)
            i += 1
            continue

        text_block(line)
        i += 1

    pdf.set_y(-14)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(150, 145, 138)
    pdf.cell(0, 6, footer, align="C")

    out = pdf.output()
    return bytes(out)


def _render_table(pdf, rows: list[list[str]], epw: float) -> None:
    if not rows:
        return
    cols = max(len(r) for r in rows)
    w = epw / cols
    pdf.ln(1)
    for ri, row in enumerate(rows):
        pdf.set_font("Helvetica", style="B" if ri == 0 else "", size=9)
        if ri == 0:
            pdf.set_fill_color(240, 238, 233)
        for ci in range(cols):
            cell = row[ci] if ci < len(row) else ""
            pdf.cell(w, 7, cell[:60], border=1, fill=(ri == 0))
        pdf.ln(7)
    pdf.ln(3)


def to_markdown_file(title: str, markdown: str) -> bytes:
    return f"# {title.strip()}\n\n{markdown.strip()}\n".encode()
