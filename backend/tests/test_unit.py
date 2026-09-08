"""Dependency-free unit tests for the core algorithms."""

from __future__ import annotations

import math

from app.services.chunking import chunk_text, estimate_tokens
from app.services.embeddings import embed_text, embed_texts
from app.services.llm import ContextPassage, _offline


# ---------------------------------------------------------------- chunking
def test_chunking_respects_headings_and_overlap():
    text = (
        "# Intro\n\nFirst paragraph about photosynthesis and chlorophyll. " * 6
        + "\n\n## Light reactions\n\nATP is produced in the thylakoid membrane. " * 6
    )
    chunks = chunk_text(text, target_tokens=60, max_tokens=90, overlap_tokens=15)
    assert len(chunks) >= 2
    assert all(c.token_count > 0 for c in chunks)
    assert any(c.heading == "Light reactions" for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunking_empty():
    assert chunk_text("") == []
    assert estimate_tokens("one two three") == 3


# --------------------------------------------------------------- embeddings
def test_embeddings_are_deterministic_and_unit_norm():
    a = embed_text("mitosis has four main phases")
    b = embed_text("mitosis has four main phases")
    assert a == b
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-6)


def test_embeddings_similar_texts_closer_than_unrelated():
    def cos(u, v):
        return sum(x * y for x, y in zip(u, v))

    q = embed_text("how do plants make energy from sunlight")
    near = embed_text("photosynthesis converts light energy into glucose")
    far = embed_text("the database uses an HNSW index for vector search")
    assert cos(q, near) > cos(q, far)


def test_embed_texts_batch_length():
    vecs = embed_texts(["a", "b", "c"])
    assert len(vecs) == 3 and all(len(v) == len(vecs[0]) for v in vecs)


# ----------------------------------------------------------- offline synth
def test_offline_synthesis_cites_passages():
    passages = [
        ContextPassage(1, "c1", "Bio notes", "Cells", "Mitochondria are the site of aerobic respiration.", 0.6),
        ContextPassage(2, "c2", "Bio notes", "Cells", "The nucleus stores the cell's DNA.", 0.5),
    ]
    synth = _offline("where does aerobic respiration happen", passages)
    assert "[1]" in synth.answer
    assert synth.citations and synth.confidence > 0.2


def test_offline_synthesis_low_confidence_without_evidence():
    synth = _offline("unrelated question", [])
    assert synth.confidence < 0.2
    assert not synth.citations
    assert synth.grounded is False


# ------------------------------------------------------- citation normalisation
def _passage(marker: int, text: str, score: float = 0.9):
    from app.services.llm import ContextPassage as CP

    return CP(marker=marker, chunk_id=f"c{marker}", title=f"Doc {marker}", heading=None,
              text=text, score=score)


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

    passages = [_passage(1, "the mitochondrion is the site of respiration")]
    uses = [CitationUse(marker=1, quote="mitochondrion is the site of respiration")]
    text = "Respiration happens in the mitochondrion. The nucleus is separate."

    out, cites = _normalise_citations(text, uses, passages, [])
    assert "[1]" in out and out.count("[1]") == 1
    assert len(cites) == 1 and cites[0].marker == 1


def test_normalise_citations_drops_stray_marker():
    from app.services.rag import _normalise_citations

    passages = [_passage(1, "alpha")]
    out, cites = _normalise_citations("Nothing here really [4].", [], passages, [])
    assert out.startswith("Nothing here really")
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
    assert detect("what materials do I have?") == "doc_list"
    assert detect("how many notes do I have?") == "count"
    assert detect("?!?!") == "gibberish"
    assert detect("42") == "gibberish"

    assert detect("Explain the causes of the French Revolution") is None
    assert detect("Give me practice questions on integration by parts") is None

    assert is_ephemeral("greeting") and is_ephemeral("capability")
    assert not is_ephemeral("doc_list") and not is_ephemeral("count")


# --------------------------------------------------------------- catalog
def test_slugify_and_defaults():
    from app.services.catalog import DEFAULT_CATEGORIES, slugify

    assert slugify("A-level Chemistry!") == "a-level-chemistry"
    assert slugify("   ") == "general"
    slugs = {s for s, _, _ in DEFAULT_CATEGORIES}
    assert {"mathematics", "physics", "general"} <= slugs


# --------------------------------------------------------------- SM-2
def test_sm2_schedule_progression():
    from app.services.sm2 import schedule

    s = schedule(easiness=2.5, interval_days=0, repetitions=0, quality=5)
    assert s.interval_days == 1 and s.repetitions == 1
    s = schedule(easiness=s.easiness, interval_days=s.interval_days, repetitions=s.repetitions, quality=5)
    assert s.interval_days == 6 and s.repetitions == 2
    # a lapse resets repetitions and interval
    lapse = schedule(easiness=2.5, interval_days=6, repetitions=2, quality=1)
    assert lapse.repetitions == 0 and lapse.interval_days == 1
    assert lapse.easiness < 2.5
