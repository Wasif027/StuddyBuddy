"""Spreadsheet analytics — text-to-SQL over uploaded workbooks (DuckDB).

Every ``xlsx/xls`` document in scope is loaded (all sheets) into an in-memory
DuckDB session as a registered table. The model writes ONE read-only ``SELECT``
(may JOIN across sheets/files); we validate it against an allowlist, cap it with
an outer ``LIMIT``, run it with a hard timeout, and narrate the result. The SQL
and the result table are returned so the UI can show exactly how the number was
produced.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import tracer
from app.models.orm import Document, DocumentTable, User
from app.services import llm
from app.services.embeddings import embed_text
from app.services.llm import ContextPassage, Synthesis
from app.services.vectorstore import RetrievedChunk, Scope, hybrid_search

logger = get_logger(__name__)
settings = get_settings()
_tracer = tracer(__name__)

_SQL_ALLOWED = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)
_SQL_FORBIDDEN = re.compile(
    r"\b(attach|detach|copy|install|load|pragma|set|reset|export|import|create|insert|"
    r"update|delete|drop|alter|truncate|merge|call|read_csv|read_parquet|read_json|"
    r"read_text|read_blob|glob|system|shell|getenv|sniff_csv)\b",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|q[1-4]|\d{4})", re.IGNORECASE)


@dataclass
class RegisteredTable:
    sql_name: str
    document_title: str
    sheet_name: str
    columns: list[dict]     # {name, sqlName, type}
    row_count: int
    truncated: bool


@dataclass
class AnalysisResult:
    ok: bool
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    tables_used: list[str] = field(default_factory=list)
    assumptions: str = ""
    error: str | None = None
    chart: dict | None = None
    narrative: Synthesis | None = None
    context_chunks: list[RetrievedChunk] = field(default_factory=list)


# --------------------------------------------------------------------- loading
def _coerce_frame(rows: list[list], columns: list[dict]):
    import pandas as pd

    names = [c["sqlName"] for c in columns]
    df = pd.DataFrame(rows, columns=names)
    for c in columns:
        col = c["sqlName"]
        if c["type"] == "number":
            df[col] = pd.to_numeric(
                df[col].map(lambda v: re.sub(r"[,$£€%\s]", "", str(v)) if v not in (None, "") else None),
                errors="coerce",
            )
        elif c["type"] == "date":
            df[col] = pd.to_datetime(df[col], errors="coerce")
        elif c["type"] == "bool":
            df[col] = df[col].map(lambda v: bool(v) if v not in (None, "") else None)
    return df


def _spreadsheet_docs_in_scope(
    db: Session, user: User, primary_id: str | None, scope_ids: list[str] | None
) -> list[str]:
    ids: list[str] = []
    if primary_id:
        ids.append(primary_id)
    if scope_ids:
        ids += [i for i in scope_ids if i not in ids]
    stmt = select(Document.id).where(
        Document.user_id == user.id, Document.source_type.in_(("xlsx", "xls"))
    )
    if ids:
        stmt = stmt.where(Document.id.in_(ids))
    found = [row[0] for row in db.execute(stmt).all()]
    # keep primary first
    if primary_id and primary_id in found:
        found = [primary_id] + [i for i in found if i != primary_id]
    return found


def _load_tables(db: Session, doc_ids: list[str]):
    """Return (duckdb connection, list[RegisteredTable])."""
    import duckdb

    con = duckdb.connect(database=":memory:")
    try:
        con.execute("SET enable_external_access = false")
    except duckdb.Error:  # pragma: no cover - version differences
        pass
    registered: list[RegisteredTable] = []
    taken: set[str] = set()

    rows = db.execute(
        select(DocumentTable, Document.title)
        .join(Document, Document.id == DocumentTable.document_id)
        .where(DocumentTable.document_id.in_(doc_ids))
        .order_by(DocumentTable.document_id, DocumentTable.position)
    ).all()

    for dt, doc_title in rows:
        if dt.row_count == 0:  # header-only / empty sheet — nothing to query
            continue
        name = dt.sql_name
        if name in taken:
            name = f"{dt.sql_name}_{len(taken)}"
        taken.add(name)
        try:
            df = _coerce_frame(dt.rows_json or [], dt.columns_json or [])
            con.register(name, df)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("analysis_register_failed", sheet=dt.sheet_name, error=str(exc))
            continue
        registered.append(
            RegisteredTable(
                sql_name=name,
                document_title=doc_title,
                sheet_name=dt.sheet_name,
                columns=dt.columns_json or [],
                row_count=dt.row_count,
                truncated=dt.truncated,
            )
        )
    return con, registered


def _schema_text(con, tables: list[RegisteredTable]) -> str:
    blocks = []
    for t in tables:
        cols = ", ".join(f'{c["sqlName"]} {c["type"].upper()}' for c in t.columns)
        try:
            sample = con.execute(f'SELECT * FROM "{t.sql_name}" LIMIT 3').fetchall()
        except Exception:  # pragma: no cover
            sample = []
        sample_txt = "\n".join("  " + " | ".join(str(x) for x in row) for row in sample)
        blocks.append(
            f'table "{t.sql_name}"  (from "{t.document_title}" / sheet "{t.sheet_name}", '
            f"{t.row_count} rows)\n  columns: {cols}\n  sample:\n{sample_txt}"
        )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------- SQL guard
def _sanitise_sql(sql: str) -> str | None:
    s = sql.strip().rstrip(";").strip()
    if not s or not _SQL_ALLOWED.match(s):
        return None
    if ";" in s or "--" in s or "/*" in s:
        return None
    if _SQL_FORBIDDEN.search(s):
        return None
    return s


def _run_sql(con, sql: str, cap: int) -> tuple[list[str], list[list]]:
    wrapped = f"SELECT * FROM (\n{sql}\n) AS _wrapped LIMIT {cap + 1}"

    def _exec():
        cur = con.execute(wrapped)
        cols = [d[0] for d in cur.description]
        return cols, [list(r) for r in cur.fetchall()]

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_exec)
        try:
            return fut.result(timeout=settings.analysis_sql_timeout_seconds)
        except FutureTimeout:
            con.interrupt()
            raise TimeoutError("query exceeded the time limit") from None


# ------------------------------------------------------------------- chart hint
def _chart_hint(columns: list[str], rows: list[list]) -> dict | None:
    if not rows or len(rows) > 60 or len(columns) < 2:
        return None
    num_cols, txt_cols = [], []
    for ci, name in enumerate(columns):
        vals = [r[ci] for r in rows if r[ci] is not None]
        if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            num_cols.append(name)
        else:
            txt_cols.append((ci, name))
    if len(txt_cols) != 1 or not (1 <= len(num_cols) <= 3):
        return None
    xi, xname = txt_cols[0]
    x_vals = [str(r[xi]) for r in rows if r[xi] is not None]
    ctype = "line" if x_vals and sum(bool(_MONTH_RE.match(v)) for v in x_vals) >= len(x_vals) * 0.7 else "bar"
    return {"type": ctype, "x": xname, "series": num_cols}


# --------------------------------------------------------------------- context
def _supporting_context(db: Session, user: User, question: str, exclude_ids: list[str]) -> list[RetrievedChunk]:
    try:
        scope = Scope(user_id=user.id)
        hits = hybrid_search(db, query=question, embedding=embed_text(question), k=3, scope=scope)
        return [h for h in hits if h.chunk.document_id not in exclude_ids][:3]
    except Exception as exc:  # pragma: no cover
        logger.warning("analysis_context_failed", error=str(exc))
        return []


# --------------------------------------------------------------------- entry
def run_analysis(
    db: Session,
    user: User,
    *,
    question: str,
    primary_document_id: str | None,
    scope_document_ids: list[str] | None = None,
    history: str | None = None,
) -> AnalysisResult:
    with _tracer.start_as_current_span("analysis.run") as span:
        doc_ids = _spreadsheet_docs_in_scope(db, user, primary_document_id, scope_document_ids)
        if not doc_ids:
            return AnalysisResult(ok=False, error="no spreadsheet data in scope")
        if not llm.provider_ready():
            return AnalysisResult(
                ok=False,
                error="analysis needs a model provider — set LLM_PROVIDER and a key",
            )

        con, tables = _load_tables(db, doc_ids)
        if not tables:
            return AnalysisResult(
                ok=False, error="the spreadsheet has no data rows yet — add some and ask again"
            )
        schema = _schema_text(con, tables)
        span.set_attribute("tables", len(tables))

        sql: str | None = None
        assumptions = ""
        last_err: str | None = None
        for attempt in range(3):
            raw_sql, assumptions = llm.generate_sql(
                question, schema, history=history, prior_error=last_err if attempt else None
            )
            if not raw_sql:
                return AnalysisResult(
                    ok=False,
                    assumptions=assumptions or "the question can't be answered from this data",
                    error="no query",
                )
            sql = _sanitise_sql(raw_sql)
            if sql is None:
                last_err = "the query must be a single read-only SELECT"
                continue
            try:
                cols, result_rows = _run_sql(con, sql, settings.analysis_result_row_cap)
                break
            except Exception as exc:
                last_err = str(exc)[:300]
                logger.info("analysis_sql_retry", attempt=attempt, error=last_err)
                sql = None
        if sql is None:
            err = last_err or "query failed"
            if last_err and re.search(r"not found|binder error|does not have a column", last_err, re.I):
                all_cols = sorted({c["sqlName"] for t in tables for c in t.columns})
                err = f"I couldn't match a column to that. The data has: {', '.join(all_cols)}."
            return AnalysisResult(ok=False, assumptions=assumptions, error=err)

        cap = settings.analysis_result_row_cap
        truncated = len(result_rows) > cap
        result_rows = result_rows[:cap]
        # JSON-safe cells
        result_rows = [
            [c if (c is None or isinstance(c, (int, float, str, bool))) else str(c) for c in row]
            for row in result_rows
        ]
        chart = _chart_hint(cols, result_rows)
        context = _supporting_context(db, user, question, doc_ids)
        ctx_passages = [
            ContextPassage(
                marker=i + 1,
                chunk_id=h.chunk.id,
                title=h.chunk.document.title if h.chunk.document else "",
                heading=h.chunk.heading,
                text=h.chunk.text,
                score=h.score,
            )
            for i, h in enumerate(context)
        ]
        narrative = llm.narrate_analysis(
            question, sql, cols, result_rows, context_passages=ctx_passages or None
        )

        return AnalysisResult(
            ok=True,
            sql=sql,
            columns=cols,
            rows=result_rows,
            row_count=len(result_rows),
            truncated=truncated,
            tables_used=[t.sql_name for t in tables],
            assumptions=assumptions,
            chart=chart,
            narrative=narrative,
            context_chunks=context,
        )
