"""Dependency-free unit tests for the core algorithms."""

from __future__ import annotations

import math

from app.services.chunking import chunk_text, estimate_tokens
from app.services.embeddings import embed_text, embed_texts
from app.services.llm import ContextPassage, _coerce_step, _offline


# ---------------------------------------------------------------- chunking
def test_chunking_respects_headings_and_overlap():
    text = (
        "# Intro\n\nFirst paragraph about onboarding and equipment. " * 6
        + "\n\n## Security\n\nVPN is required for all remote access. " * 6
    )
    chunks = chunk_text(text, target_tokens=60, max_tokens=90, overlap_tokens=15)
    assert len(chunks) >= 2
    assert all(c.token_count > 0 for c in chunks)
    assert any(c.heading == "Security" for c in chunks)
    # indices are contiguous
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunking_empty():
    assert chunk_text("") == []
    assert estimate_tokens("one two three") == 3


# --------------------------------------------------------------- embeddings
def test_embeddings_are_deterministic_and_unit_norm():
    a = embed_text("quarterly revenue was 42 million")
    b = embed_text("quarterly revenue was 42 million")
    assert a == b
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-6)


def test_embeddings_similar_texts_closer_than_unrelated():
    def cos(u, v):
        return sum(x * y for x, y in zip(u, v))

    q = embed_text("how much vacation do employees get")
    near = embed_text("employees accrue vacation days each month")
    far = embed_text("the database uses an HNSW index for vector search")
    assert cos(q, near) > cos(q, far)


def test_embed_texts_batch_length():
    vecs = embed_texts(["a", "b", "c"])
    assert len(vecs) == 3 and all(len(v) == len(vecs[0]) for v in vecs)


# ------------------------------------------------------------- suggestions
def test_suggested_step_coercion():
    ok = _coerce_step({"text": "Email the customer", "rationale": "policy allows it", "priority": "HIGH"})
    assert ok and ok.priority == "high"
    assert _coerce_step({"text": "  "}) is None
    assert _coerce_step("not a dict") is None
    weird = _coerce_step({"text": "Do the thing", "priority": "urgent"})
    assert weird and weird.priority == "medium"  # unknown priority falls back


def test_suggest_actions_offline_returns_empty():
    from app.services import llm

    assert llm.suggest_actions("what is the refund window?", "30 days.", []) == []
    assert llm.suggest_alternative("q", "a", [], ["rejected step"]) is None


# ----------------------------------------------------------- offline synth
def test_offline_synthesis_cites_passages():
    passages = [
        ContextPassage(1, "c1", "Remote Policy", "Equipment", "The company provides one laptop and one monitor.", 0.6),
        ContextPassage(2, "c2", "Remote Policy", "Internet", "Home internet is reimbursed at 50 dollars per month.", 0.5),
    ]
    synth = _offline("what equipment does the company provide", passages)
    assert "[1]" in synth.answer
    assert synth.citations and synth.confidence > 0.2


def test_offline_synthesis_low_confidence_without_evidence():
    synth = _offline("unrelated question", [])
    assert synth.confidence < 0.2
    assert not synth.citations


# ------------------------------------------------------------- parsing
def test_infer_type_and_identifier_sanitiser():
    from app.services.parsing import infer_type, sanitise_identifier

    assert infer_type(["1,234", "$5.00", "12%"]) == "number"
    assert infer_type(["2026-01-03", "2026-02-11"]) == "date"
    assert infer_type(["north", "south"]) == "text"

    taken: set[str] = set()
    assert sanitise_identifier("Unit Price (£)", taken) == "unit_price"
    assert sanitise_identifier("Unit Price (£)", taken) == "unit_price_2"
    assert sanitise_identifier("select", taken) == "select_"
    assert sanitise_identifier("", taken) == "col"


def test_xlsx_parse_infers_columns_and_rows():
    import io

    from openpyxl import Workbook

    from app.services.xlsx_parse import parse_workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Data"
    ws.append(["Product", "Region", "Units", "Unit Price"])
    ws.append(["Pouch", "North", 10, 0.9])
    ws.append(["Box", "South", 4, 2.8])
    buf = io.BytesIO()
    wb.save(buf)

    tables, preview = parse_workbook("sales.xlsx", buf.getvalue())
    assert len(tables) == 1
    t = tables[0]
    assert t.sql_name == "sales_data"
    assert [c.sql_name for c in t.columns] == ["product", "region", "units", "unit_price"]
    assert [c.type for c in t.columns] == ["text", "text", "number", "number"]
    assert t.row_count == 2
    assert "Sheet: Sales Data" in preview


def test_pptx_parse_scores_data_rich_slides():
    import io

    from pptx import Presentation

    from app.services.pptx_parse import parse_deck

    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Agenda"
    s1.placeholders[1].text_frame.text = "Intro and welcome"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Q1 Revenue Results"
    s2.placeholders[1].text_frame.text = "Revenue was £184,000, up 12% from £164,000"
    buf = io.BytesIO()
    prs.save(buf)

    slides, md = parse_deck(buf.getvalue())
    assert len(slides) == 2
    assert slides[1].data_score > slides[0].data_score
    assert "## Slide 2" in md


# ------------------------------------------------------- citation normalisation
def _passage(marker: int, text: str, score: float = 0.9):
    from app.services.llm import ContextPassage

    return ContextPassage(marker=marker, chunk_id=f"c{marker}", title=f"Doc {marker}",
                          heading=None, text=text, score=score)


def test_normalise_citations_renumbers_in_appearance_order():
    from app.services.llm import CitationUse
    from app.services.rag import _normalise_citations

    passages = [_passage(1, "alpha"), _passage(2, "bravo"), _passage(3, "charlie")]
    uses = [CitationUse(marker=3, quote="charlie"), CitationUse(marker=2, quote="bravo")]
    text = "The bravo rule applies [2]. See also charlie [3]."

    out, cites = _normalise_citations(text, uses, passages, [])
    assert out == "The bravo rule applies [1]. See also charlie [2]."
    assert [c.marker for c in cites] == [1, 2]
    assert cites[0].chunk_id == "c2" and cites[1].chunk_id == "c3"


def test_normalise_citations_splices_missing_markers():
    from app.services.llm import CitationUse
    from app.services.rag import _normalise_citations

    passages = [_passage(1, "the refund window is thirty days")]
    uses = [CitationUse(marker=1, quote="refund window is thirty days")]
    text = "Customers can return an item within the refund window. Sale items are excluded."

    out, cites = _normalise_citations(text, uses, passages, [])
    assert "[1]" in out and out.count("[1]") == 1
    assert len(cites) == 1 and cites[0].marker == 1
    # the marker lands on the sentence about the refund window, not the sale one
    assert "refund window. [1]" in out


def test_normalise_citations_drops_stray_marker():
    from app.services.rag import _normalise_citations

    passages = [_passage(1, "alpha")]
    out, cites = _normalise_citations("Nothing here really [4].", [], passages, [])
    assert out == "Nothing here really ." or out == "Nothing here really  ."
    assert cites == []


def test_confidence_rewards_a_strong_cited_passage():
    import types

    from app.models.schemas import Citation
    from app.services.rag import _confidence

    retrieved = [types.SimpleNamespace(score=0.4), types.SimpleNamespace(score=0.3)]
    strong_cite = [Citation(marker=1, chunk_id="c", document_id="d", title="t",
                            category=None, page=None, quote="q", score=0.95)]
    weak = _confidence(0.6, retrieved, [], mode="pinpoint")
    strong = _confidence(0.6, retrieved, strong_cite, mode="pinpoint")
    assert strong > weak


# --------------------------------------------------------------- meta detection
def test_meta_detect_classifies_conversational_input():
    from app.services.meta import detect, is_ephemeral

    assert detect("hi") == "greeting"
    assert detect("Hey there!") == "greeting"
    assert detect("thanks!") == "thanks"
    assert detect("what can you do?") == "capability"
    assert detect("what documents do I have?") == "doc_list"
    assert detect("how many documents do I have?") == "count"
    assert detect("?!?!") == "gibberish"
    assert detect(".") == "gibberish"
    assert detect("42") == "gibberish"

    # real questions are not meta
    assert detect("What is the refund window for a broken candle?") is None
    assert detect("Which product is least profitable?") is None

    assert is_ephemeral("greeting") and is_ephemeral("capability")
    assert not is_ephemeral("doc_list") and not is_ephemeral("count")


def test_chart_hint():
    from app.services.analysis import _chart_hint

    cols = ["region", "revenue"]
    rows = [["North", 100.0], ["South", 250.0], ["East", 180.0]]
    hint = _chart_hint(cols, rows)
    assert hint == {"type": "bar", "x": "region", "series": ["revenue"]}

    months = [["2026-01", 10.0], ["2026-02", 20.0], ["2026-03", 15.0]]
    assert _chart_hint(["month", "sales"], months)["type"] == "line"

    assert _chart_hint(["a", "b", "c"], [["x", "y", "z"]]) is None  # no numeric column
