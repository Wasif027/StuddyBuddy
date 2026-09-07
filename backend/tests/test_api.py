"""End-to-end API tests (require Postgres + pgvector)."""

from __future__ import annotations

import io
import uuid

from tests.conftest import requires_db

pytestmark = requires_db


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"
    ws.append(["product", "region", "units", "unit_cost", "unit_price"])
    rows = [
        ("Pouch", "North", 10, 0.40, 0.90),
        ("Pouch", "South", 5, 0.40, 0.90),
        ("Cold Box", "North", 8, 3.10, 2.80),   # sold at a loss
        ("Pallet Wrap", "East", 3, 6.40, 11.50),
        ("Weekend Delivery", "West", 12, 5.90, 5.50),  # sold at a loss
    ]
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pptx_bytes() -> bytes:
    from pptx import Presentation

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Q1 Highlights"
    s.placeholders[1].text_frame.text = "Revenue up 12% to £184,000 this quarter"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Safety"
    s2.placeholders[1].text_frame.text = "Lifting limit reduced to 20kg"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()

_VACATION = {
    "title": "Vacation Policy",
    "category": "policy",
    "content": (
        "# Vacation Policy\n\n"
        "Full-time employees accrue 1.75 vacation days per month, for a total of 21 days per year. "
        "Unused days roll over up to a maximum of 10 days. Requests need manager approval two weeks ahead.\n\n"
        "## Sick leave\n\nSick leave is separate and uncapped."
    ),
}
_SEC_V1 = {
    "title": "Security Policy v1",
    "category": "security",
    "content": "# Access\n\nProduction access needs manager approval and is time-boxed to 8 hours. Passwords are 12 characters.",
}
_SEC_V2 = {
    "title": "Security Policy v2",
    "category": "security",
    "content": "# Access\n\nProduction access needs VP approval and is time-boxed to 4 hours. Passwords are 16 characters, rotated every 90 days.",
}


def test_health(app_client):
    r = app_client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["services"]["postgres"] == "up"


def test_auth_flow(app_client):
    r = app_client.post("/api/v1/auth/register", json={"username": "flowuser", "password": "password123"})
    assert r.status_code in (201, 409)
    r = app_client.post("/api/v1/auth/login", json={"username": "flowuser", "password": "password123"})
    assert r.status_code == 200
    token = r.json()["token"]
    me = app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["username"] == "flowuser"
    assert app_client.post("/api/v1/auth/login", json={"username": "flowuser", "password": "wrong"}).status_code == 401


def test_requires_auth(app_client):
    for path in ("/api/v1/documents", "/api/v1/categories", "/api/v1/conversations", "/api/v1/suggestions"):
        assert app_client.get(path).status_code == 401
    assert app_client.post("/api/v1/query", json={"question": "hi"}).status_code == 401


def test_documents_are_per_user(auth, app_client):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    assert len(client.get("/api/v1/documents", headers=headers).json()) >= 1

    other = app_client.post(
        "/api/v1/auth/register",
        json={"username": f"other_{uuid.uuid4().hex[:10]}", "password": "password123"},
    ).json()
    other_h = {"Authorization": f"Bearer {other['token']}"}
    assert client.get("/api/v1/documents", headers=other_h).json() == []


def test_query_creates_conversation_and_persists(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)

    r = client.post(
        "/api/v1/query",
        json={"question": "How many vacation days per year and do they roll over?"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversationId"] and body["messageId"]
    assert body["sourceChunks"] and 0.0 <= body["confidence"] <= 1.0
    assert any("vacation" in c["text"].lower() for c in body["sourceChunks"])

    convs = client.get("/api/v1/conversations", headers=headers).json()
    assert len(convs) == 1 and convs[0]["messageCount"] == 2

    detail = client.get(f"/api/v1/conversations/{body['conversationId']}", headers=headers).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["answer"]["confidence"] == body["confidence"]


def test_document_summary_mode(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)

    r = client.post(
        "/api/v1/query",
        json={"question": "Summarise the Vacation Policy document and its key points.",
              "bypassCache": True},
        headers=headers,
    ).json()
    assert r["retrievalMode"] == "document"
    assert r["insufficientEvidence"] is False
    # a whole-document read should surface more than one passage
    assert len(r["sourceChunks"]) >= 1
    assert all(c["documentId"] == r["sourceChunks"][0]["documentId"] for c in r["sourceChunks"])


def test_explicit_document_id_forces_document_mode(auth):
    client, headers, _ = auth
    doc_id = client.post("/api/v1/documents", json=_SEC_V1, headers=headers).json()["documentId"]
    r = client.post(
        "/api/v1/query",
        json={"question": "what's this about", "documentId": doc_id, "bypassCache": True},
        headers=headers,
    ).json()
    assert r["retrievalMode"] == "document"
    assert {c["documentId"] for c in r["sourceChunks"]} == {doc_id}


def test_overview_mode(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    client.post("/api/v1/documents", json=_SEC_V1, headers=headers)
    r = client.post(
        "/api/v1/query",
        json={"question": "Give me an overview of the key points across all the documents.",
              "bypassCache": True},
        headers=headers,
    ).json()
    assert r["retrievalMode"] == "overview"


def test_followup_uses_conversation_context(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_SEC_V1, headers=headers)

    first = client.post(
        "/api/v1/query",
        json={"question": "What does the security policy say about production access?"},
        headers=headers,
    ).json()
    cid = first["conversationId"]

    # Anaphoric follow-up — the subject ("it") lives only in the history.
    second = client.post(
        "/api/v1/query",
        json={"question": "And how long is it time-boxed to?", "conversationId": cid},
        headers=headers,
    ).json()
    assert second["conversationId"] == cid
    assert second["sourceChunks"], "follow-up should still retrieve the access passage"
    assert any("access" in c["text"].lower() for c in second["sourceChunks"])


def test_rejects_plain_text_upload(auth):
    client, headers, _ = auth
    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=headers,
    )
    assert r.status_code == 415


def test_xlsx_upload_and_analysis(auth):
    from app.services import llm

    client, headers, _ = auth
    up = client.post(
        "/api/v1/documents/upload",
        files={"file": ("orders.xlsx", _xlsx_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"category": "sales"},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    assert up.json()["status"] == "ready"

    r = client.post(
        "/api/v1/query",
        json={"question": "Which products are being sold at a loss?", "bypassCache": True},
        headers=headers,
    ).json()
    assert r["retrievalMode"] == "analysis"
    assert r["analysis"] is not None
    if llm.provider_ready():
        assert r["analysis"]["ok"] is True
        assert r["analysis"]["sql"].lower().lstrip().startswith(("select", "with"))
        loss_products = {str(row[0]).lower() for row in r["analysis"]["rows"]}
        assert any("box" in p or "weekend" in p for p in loss_products)
    else:
        assert r["analysis"]["ok"] is False  # graceful without a model provider


def test_xlsx_analysis_rejects_unsafe_sql():
    from app.services.analysis import _sanitise_sql

    assert _sanitise_sql("SELECT * FROM orders") == "SELECT * FROM orders"
    assert _sanitise_sql("SELECT 1; DROP TABLE orders") is None
    assert _sanitise_sql("DROP TABLE orders") is None
    assert _sanitise_sql("SELECT * FROM read_csv('/etc/passwd')") is None
    assert _sanitise_sql("SELECT * FROM orders -- comment") is None


def test_pptx_upload_slide_metadata(auth):
    client, headers, _ = auth
    up = client.post(
        "/api/v1/documents/upload",
        files={"file": ("review.pptx", _pptx_bytes(),
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        data={"category": "deck"},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    doc_id = up.json()["documentId"]

    r = client.post(
        "/api/v1/query",
        json={"question": "Summarise the review deck", "documentId": doc_id, "bypassCache": True},
        headers=headers,
    ).json()
    assert r["retrievalMode"] == "document"
    kinds = {c["metadata"].get("kind") for c in r["sourceChunks"]}
    assert "slide" in kinds
    assert any(c["metadata"].get("slide") for c in r["sourceChunks"])


def test_compare_mode(auth):
    client, headers, _ = auth
    id1 = client.post("/api/v1/documents", json=_SEC_V1, headers=headers).json()["documentId"]
    id2 = client.post("/api/v1/documents", json=_SEC_V2, headers=headers).json()["documentId"]

    r = client.post(
        "/api/v1/query",
        json={
            "question": "How do the access approval and password rules differ?",
            "compareDocumentIds": [id1, id2],
            "bypassCache": True,
        },
        headers=headers,
    ).json()
    assert r["compareMode"] is True
    # retrieval must be restricted to the two named documents
    assert {c["documentId"] for c in r["sourceChunks"]} <= {id1, id2}


def test_conversation_rename_and_delete(auth):
    client, headers, _ = auth
    conv = client.post("/api/v1/conversations", json={"title": "Scratch"}, headers=headers).json()
    cid = conv["id"]
    assert client.patch(f"/api/v1/conversations/{cid}", json={"title": "Renamed"}, headers=headers).json()["title"] == "Renamed"
    assert client.delete(f"/api/v1/conversations/{cid}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/conversations/{cid}", headers=headers).status_code == 404


_HANDBOOK = {
    "title": "Complaints handbook",
    "category": "policy",
    "content": (
        "# Broken items\n\nIf a candle arrives broken, offer the customer a free replacement "
        "or a full refund within 30 days. Ask them to send a photo. Log the breakage against "
        "the courier so we can claim it back.\n\n"
        "# Late delivery\n\nIf a parcel is more than 5 working days late, refund the shipping "
        "fee and send an apology with a discount code."
    ),
}


def test_suggestions_flow_and_history(auth):
    from app.services import llm

    client, headers, _ = auth
    client.post("/api/v1/documents", json=_HANDBOOK, headers=headers)

    body = client.post(
        "/api/v1/query",
        json={
            "question": "A customer emailed that their candle arrived smashed. What should I do?",
            "bypassCache": True,
        },
        headers=headers,
    ).json()
    assert body["conversationId"] and body["messageId"]

    if not llm.provider_ready():
        assert body["suggestions"] == []
        return

    sugs = body["suggestions"]
    assert sugs, "a complaint scenario should produce next steps"
    assert all(s["decision"] == "pending" and s["text"] and s["priority"] in ("high", "medium", "low") for s in sugs)

    # accept the first with a note
    acc = client.post(
        f"/api/v1/suggestions/{sugs[0]['id']}/decide",
        json={"decision": "accept", "note": "done via Zendesk"},
        headers=headers,
    ).json()
    assert acc["suggestion"]["decision"] == "accepted" and acc["suggestion"]["note"] == "done via Zendesk"

    # reject the last -> an alternative should come back
    if len(sugs) > 1:
        rej = client.post(
            f"/api/v1/suggestions/{sugs[-1]['id']}/decide",
            json={"decision": "reject"},
            headers=headers,
        ).json()
        assert rej["suggestion"]["decision"] == "rejected"
        if rej["alternative"]:
            assert rej["alternative"]["rejectDepth"] == 1 and rej["alternative"]["decision"] == "pending"

    # history: the accepted one shows up, filterable
    hist = client.get("/api/v1/suggestions?status=accepted", headers=headers).json()
    assert any(h["id"] == sugs[0]["id"] and h["conversationDeleted"] is False for h in hist)

    # a pure factual lookup should stay quiet
    factual = client.post(
        "/api/v1/query",
        json={"question": "What is the refund window for broken items?", "bypassCache": True},
        headers=headers,
    ).json()
    assert len(factual["suggestions"]) <= 1


def test_suggestion_survives_conversation_delete(auth):
    from app.services import llm

    if not llm.provider_ready():
        return
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_HANDBOOK, headers=headers)
    body = client.post(
        "/api/v1/query",
        json={"question": "A customer's order is 8 days late. What should I do?", "bypassCache": True},
        headers=headers,
    ).json()
    if not body["suggestions"]:
        return
    sid = body["suggestions"][0]["id"]
    assert client.delete(f"/api/v1/conversations/{body['conversationId']}", headers=headers).status_code == 200
    hist = client.get("/api/v1/suggestions", headers=headers).json()
    row = next((h for h in hist if h["id"] == sid), None)
    assert row is not None and row["conversationDeleted"] is True


def test_stream_query(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    with client.stream(
        "POST",
        "/api/v1/query",
        json={"question": "How many vacation days?", "stream": True, "bypassCache": True},
        headers=headers,
    ) as r:
        assert r.status_code == 200
        joined = "\n".join(line for line in r.iter_lines() if line)
    assert "event: grounding" in joined and "event: final" in joined


# --------------------------------------------------------------- meta / conversational


def test_greeting_is_ephemeral(auth):
    client, headers, _ = auth
    r = client.post("/api/v1/query", json={"question": "hey there!"}, headers=headers).json()
    assert r["retrievalMode"] == "meta"
    assert r["conversationId"] is None and r["messageId"] is None
    assert r["insufficientEvidence"] is False
    # nothing persisted
    assert client.get("/api/v1/conversations", headers=headers).json() == []


def test_no_documents_prompts_to_add_one(auth):
    client, headers, _ = auth
    r = client.post(
        "/api/v1/query", json={"question": "What is our refund window?"}, headers=headers
    ).json()
    assert "add document" in r["answer"].lower() or "add a document" in r["answer"].lower()
    # a real question with an empty library isn't saved as a chat either
    assert client.get("/api/v1/conversations", headers=headers).json() == []


def test_doc_list_meta_answer(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    client.post("/api/v1/documents", json=_SEC_V1, headers=headers)
    r = client.post(
        "/api/v1/query", json={"question": "what documents do I have?"}, headers=headers
    ).json()
    assert r["retrievalMode"] == "meta"
    assert "Vacation Policy" in r["answer"] and "Security Policy v1" in r["answer"]


def test_capability_meta_answer(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    r = client.post(
        "/api/v1/query", json={"question": "what can you do?"}, headers=headers
    ).json()
    assert r["retrievalMode"] == "meta"
    low = r["answer"].lower()
    assert "calculation" in low and "citation" in low
    assert "policies" in low  # names the user's actual categories


def test_corrupt_pdf_gives_clear_error(auth):
    client, headers, _ = auth
    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("broken.pdf", b"%PDF-1.4 this is not really a pdf", "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 422
    assert "pdf" in r.json()["detail"].lower()


def test_header_only_spreadsheet_ingests_then_analysis_is_guarded(auth):
    from openpyxl import Workbook

    from app.services import llm

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"
    ws.append(["date", "product", "revenue"])  # header only, no data rows
    buf = io.BytesIO()
    wb.save(buf)

    client, headers, _ = auth
    up = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty-orders.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"category": "sales"},
        headers=headers,
    )
    assert up.status_code == 201, up.text
    assert up.json()["status"] == "ready"

    r = client.post(
        "/api/v1/query",
        json={"question": "What was the total revenue?", "intent": "analysis", "bypassCache": True},
        headers=headers,
    ).json()
    assert r["retrievalMode"] == "analysis"
    assert r["analysis"]["ok"] is False
    if llm.provider_ready():
        assert "no data rows" in r["analysis"]["error"].lower()


def test_citations_are_numbered_in_order(auth):
    from app.services import llm

    if not llm.provider_ready():
        return
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    client.post("/api/v1/documents", json=_SEC_V1, headers=headers)
    r = client.post(
        "/api/v1/query",
        json={"question": "How many vacation days per year do full-time staff get?",
              "bypassCache": True},
        headers=headers,
    ).json()
    markers = [c["marker"] for c in r["citations"]]
    assert markers == list(range(1, len(markers) + 1))  # 1..k, in order, no gaps
    for m in markers:
        assert f"[{m}]" in r["answer"]


def test_clear_fact_reads_high_confidence(auth):
    from app.services import llm

    if not llm.provider_ready():
        return
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    r = client.post(
        "/api/v1/query",
        json={"question": "How many vacation days do full-time employees accrue per month?",
              "bypassCache": True},
        headers=headers,
    ).json()
    assert r["confidenceLabel"] in ("high", "medium")
    assert r["insufficientEvidence"] is False


def test_suggestions_carry_a_kind(auth):
    from app.services import llm

    if not llm.provider_ready():
        return
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_HANDBOOK, headers=headers)
    r = client.post(
        "/api/v1/query",
        json={"question": "Amber & Oud keeps selling below cost — what should I do about it?",
              "bypassCache": True},
        headers=headers,
    ).json()
    for s in r["suggestions"]:
        assert s["kind"] in ("explore", "external")


def test_unfindable_question_has_friendly_wording(auth):
    client, headers, _ = auth
    client.post("/api/v1/documents", json=_VACATION, headers=headers)
    r = client.post(
        "/api/v1/query",
        json={"question": "What is the zorblax frimble allocation for Q3?", "bypassCache": True},
        headers=headers,
    ).json()
    assert r["insufficientEvidence"] is True
    low = r["answer"].lower()
    assert "couldn't find anything" in low or "limited evidence" in low
