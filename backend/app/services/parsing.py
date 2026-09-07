"""Shared types + helpers for upload parsing.

Kept dependency-light (no openpyxl / python-pptx here) so it can be imported by
both the format parsers and the ingestion service without cycles.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Literal

FileKind = Literal["pdf", "docx", "xlsx", "pptx"]

ColumnType = Literal["text", "number", "date", "bool"]


@dataclass
class ParsedColumn:
    name: str          # original header
    sql_name: str      # sanitised identifier used in SQL
    type: ColumnType


@dataclass
class ParsedTable:
    sheet_name: str
    sql_name: str
    columns: list[ParsedColumn]
    rows: list[list[Any]]        # JSON-safe cell values, header excluded
    row_count: int              # true row count (rows may be truncated)
    truncated: bool = False

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


@dataclass
class ParsedSlide:
    index: int                  # 1-based
    title: str | None
    bullets: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)   # markdown
    notes: str | None = None
    has_chart: bool = False
    has_table: bool = False
    data_score: float = 0.0


@dataclass
class ParsedUpload:
    title: str
    kind: FileKind
    text: str                                   # markdown-ish, for retrieval
    tables: list[ParsedTable] = field(default_factory=list)
    slides: list[ParsedSlide] = field(default_factory=list)
    # per-block location info, aligned to the order blocks appear in ``text``;
    # consumed by the chunker-adjacent metadata pass. Optional.
    page_map: list[tuple[str, int]] = field(default_factory=list)  # (heading, page/slide no.)


# --------------------------------------------------------------------- helpers
_IDENT_RE = re.compile(r"[^a-z0-9_]+")
_SQL_RESERVED = {
    "select", "from", "where", "group", "order", "by", "having", "join", "on",
    "as", "and", "or", "not", "null", "table", "index", "case", "when", "then",
    "else", "end", "limit", "offset", "union", "all", "distinct", "into", "values",
}


def sanitise_identifier(name: str, taken: set[str], fallback: str = "col") -> str:
    """Snake-case a header into a safe, unique SQL identifier."""
    base = _IDENT_RE.sub("_", (name or "").strip().lower()).strip("_")
    if not base or base[0].isdigit():
        base = f"{fallback}_{base}" if base else fallback
    if base in _SQL_RESERVED:
        base = f"{base}_"
    candidate = base
    n = 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    taken.add(candidate)
    return candidate


_NUM_RE = re.compile(r"^-?[$£€]?\s?[\d,]+(\.\d+)?%?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2})?)?$")


def infer_type(values: list[Any]) -> ColumnType:
    """Best-effort column type from a sample of non-null cell values."""
    sample = [v for v in values if v not in (None, "")][:200]
    if not sample:
        return "text"
    if all(isinstance(v, bool) for v in sample):
        return "bool"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in sample):
        return "number"
    if all(isinstance(v, (_dt.date, _dt.datetime)) for v in sample):
        return "date"
    strs = [str(v).strip() for v in sample]
    # ISO date / month strings ("2026-01-03", "2026-01")
    if all(_DATE_RE.match(s) for s in strs):
        return "date"
    # strings that all look numeric ("1,234", "$5.00", "12%")
    if all(_NUM_RE.match(s) for s in strs):
        return "number"
    return "text"


def json_safe(value: Any) -> Any:
    """Coerce a cell value into something JSON / DuckDB friendly."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, _dt.time):
        return value.isoformat()
    return str(value)


def markdown_table(headers: list[str], rows: list[list[Any]], max_rows: int = 20) -> str:
    """Render a small markdown table for retrieval text / slide extracts."""
    if not headers:
        return ""
    head = "| " + " | ".join(str(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = []
    for r in rows[:max_rows]:
        cells = [("" if c is None else str(c)) for c in r]
        cells += [""] * (len(headers) - len(cells))
        body.append("| " + " | ".join(cells[: len(headers)]) + " |")
    out = "\n".join([head, sep, *body])
    if len(rows) > max_rows:
        out += f"\n\n_({len(rows) - max_rows} more rows)_"
    return out
