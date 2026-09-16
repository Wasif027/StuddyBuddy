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

# fpdf2's core fonts are Latin-1 only; transliterate the symbols study content
# actually uses, then drop anything still out of range.
_TRANSLIT = {
    "–": "-", "—": "-", "‑": "-", "‒": "-", "―": "-",
    "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'",
    "…": "...", "•": "-", "·": "*", "∙": "*", "×": "x", "÷": "/",
    "→": "->", "←": "<-", "↔": "<->", "⇒": "=>", "⇐": "<=", "⟶": "->",
    "≤": "<=", "≥": ">=", "≠": "!=", "≈": "~", "≡": "==", "∝": "prop to",
    "∞": "infinity", "√": "sqrt", "∑": "sum", "∏": "product", "∫": "integral",
    "∂": "d", "∆": "delta", "∇": "nabla", "°": " deg", "′": "'", "″": '"',
    "±": "+/-", "∴": "therefore", "∵": "because", "∈": "in", "∉": "not in",
    "⊂": "subset", "⊆": "subset=", "∪": "union", "∩": "intersect", "∅": "empty set",
    "≅": "~=", "⟨": "<", "⟩": ">", "µ": "u", "π": "pi", "θ": "theta",
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "λ": "lambda", "σ": "sigma", "τ": "tau", "φ": "phi", "ω": "omega",
    "Δ": "Delta", "Σ": "Sigma", "Ω": "Omega", "Φ": "Phi", "Π": "Pi",
    " ": " ", " ": " ", " ": " ", "​": "",
}
_TRANSLIT_RE = re.compile("|".join(map(re.escape, _TRANSLIT)))


_LATEX_WORD = {
    "times": " x ", "cdot": "*", "cdots": "...", "div": " / ", "pm": " +/- ", "mp": " -/+ ",
    "leq": " <= ", "le": " <= ", "geq": " >= ", "ge": " >= ", "neq": " != ", "ne": " != ",
    "approx": " ~ ", "equiv": " = ", "sim": " ~ ", "propto": " prop ", "to": " -> ",
    "rightarrow": " -> ", "longrightarrow": " -> ", "Rightarrow": " => ", "implies": " => ",
    "leftarrow": " <- ", "leftrightarrow": " <-> ", "infty": "infinity", "partial": "d",
    "nabla": "nabla", "ldots": "...", "dots": "...", "deg": " deg", "circ": " deg",
    "left": "", "right": "", "big": "", "Big": "", "bigg": "", "displaystyle": "",
    "quad": "  ", "qquad": "   ", "!": "", ",": " ", ";": " ", ":": " ", " ": " ",
    "%": "%", "&": " ", "#": "#", "$": "$", "_": "_", "{": "{", "}": "}",
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta", "epsilon": "e",
    "varepsilon": "e", "zeta": "zeta", "eta": "eta", "theta": "theta", "vartheta": "theta",
    "iota": "iota", "kappa": "k", "lambda": "lambda", "mu": "u", "nu": "v", "xi": "xi",
    "pi": "pi", "rho": "rho", "sigma": "sigma", "tau": "tau", "upsilon": "y", "phi": "phi",
    "varphi": "phi", "chi": "chi", "psi": "psi", "omega": "omega",
    "Gamma": "Gamma", "Delta": "Delta", "Theta": "Theta", "Lambda": "Lambda", "Xi": "Xi",
    "Pi": "Pi", "Sigma": "Sigma", "Phi": "Phi", "Psi": "Psi", "Omega": "Omega",
    "sum": "sum", "prod": "product", "int": "integral", "lim": "lim", "log": "log",
    "ln": "ln", "sin": "sin", "cos": "cos", "tan": "tan", "sqrt": "sqrt",
}
_SUP1 = {"0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3"}
_CMD_RE = re.compile(r"[a-zA-Z]+|.", re.S)


def _brace_arg(s: str, i: int) -> tuple[str, int]:
    """Read one LaTeX argument at s[i:] — a {...} group (brace-matched) or one token."""
    while i < len(s) and s[i] in " \t":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            depth += 1 if s[j] == "{" else (-1 if s[j] == "}" else 0)
            if depth == 0:
                return s[i + 1 : j], j + 1
            j += 1
        return s[i + 1 :], len(s)
    if s[i] == "\\" and i + 1 < len(s):
        m = _CMD_RE.match(s, i + 1)
        return s[i : m.end()], m.end()
    return s[i], i + 1


def _sup(arg: str) -> str:
    a = _delatex(arg)
    if len(a) == 1 and a in _SUP1:
        return _SUP1[a]
    return f"^{a}" if len(a) == 1 else f"^({a})"


def _delatex(text: str) -> str:
    """Turn LaTeX (the tutor writes maths in it) into readable plain text — recursive
    so nested \\frac{-b \\pm \\sqrt{...}}{2a} comes out as (-b +/- sqrt(...)) / (2a)."""
    text = re.sub(r"\$\$?", "", text)
    text = re.sub(r"\\[\[\]()]", "", text)
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            if text[i + 1] == "\\":
                out.append("  ")
                i += 2
                continue
            m = _CMD_RE.match(text, i + 1)
            cmd = m.group(0)
            i = m.end()
            if cmd in ("frac", "dfrac", "tfrac", "cfrac"):
                a, i = _brace_arg(text, i)
                b, i = _brace_arg(text, i)
                out.append(f"({_delatex(a)}) / ({_delatex(b)})")
            elif cmd == "sqrt":
                if i < n and text[i] == "[":
                    i = text.find("]", i) + 1 or i
                a, i = _brace_arg(text, i)
                out.append(f"sqrt({_delatex(a)})")
            elif cmd in ("text", "mathrm", "mathbf", "mathit", "mathsf", "mathcal",
                         "operatorname", "boldsymbol", "vec", "hat", "bar", "tilde",
                         "overline", "underline"):
                a, i = _brace_arg(text, i)
                out.append(_delatex(a))
            elif cmd in _LATEX_WORD:
                out.append(_LATEX_WORD[cmd])
            # unknown command: drop it
        elif ch == "^":
            a, i = _brace_arg(text, i + 1)
            out.append(_sup(a))
        elif ch == "_":
            a, i = _brace_arg(text, i + 1)
            da = _delatex(a)
            out.append(da if len(da) == 1 else f"_({da})")
        elif ch == "{":
            a, i = _brace_arg(text, i)
            out.append(_delatex(a))
        elif ch == "}":
            i += 1
        else:
            out.append(ch)
            i += 1
    return re.sub(r"[ \t]{2,}", " ", "".join(out))


def _latin1(text: str) -> str:
    text = _delatex(text)
    text = _TRANSLIT_RE.sub(lambda m: _TRANSLIT[m.group()], text)
    return text.encode("latin-1", "replace").decode("latin-1")


def _md_inline(text: str) -> str:
    """Normalise Markdown inline syntax to what fpdf2's markdown mode expects."""
    text = _latin1(text)
    text = text.replace("__", "**")  # fpdf uses __ for underline; treat as bold
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"__\1__", text)  # *italic* -> __italic__ (fpdf italic)
    text = text.replace("`", "")
    return text


def markdown_to_pdf(title: str, markdown: str, *, footer: str = "StudyBuddy") -> bytes:
    from fpdf import FPDF

    class _Doc(FPDF):
        # An auto-called footer never creates its own page (a manual set_y(-x)
        # near the bottom margin does — that was the stray blank last page).
        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("Helvetica", size=8)
            self.set_text_color(150, 145, 138)
            self.cell(0, 6, _latin1(footer), align="C")
            self.set_text_color(0, 0, 0)

    pdf = _Doc(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    epw = pdf.epw
    # Trailing blank lines / a final "---" would push the auto-break onto a new,
    # near-empty page. Strip them.
    markdown = re.sub(r"(?:\s*\n)*(?:-{3,}\s*)?\s*$", "", markdown or "")

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
    pdf.multi_cell(epw, 9, _latin1(title.strip()), new_x="LMARGIN", new_y="NEXT")
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
                    pdf.multi_cell(epw, 4.6, _latin1(c) or " ", fill=True, new_x="LMARGIN", new_y="NEXT")
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
            pdf.cell(w, 7, _latin1(cell[:60]), border=1, fill=(ri == 0))
        pdf.ln(7)
    pdf.ln(3)


def to_markdown_file(title: str, markdown: str) -> bytes:
    return f"# {title.strip()}\n\n{markdown.strip()}\n".encode()
