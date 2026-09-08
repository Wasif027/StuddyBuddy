"""End-to-end API tests (require Postgres + pgvector)."""

from __future__ import annotations

from tests.conftest import requires_db

pytestmark = requires_db

_NOTES = {
    "title": "Cell biology notes",
    "category": "biology",
    "content": (
        "# Respiration\n\n"
        "Aerobic respiration takes place in the mitochondria and releases about 38 ATP "
        "per glucose molecule. It requires oxygen.\n\n"
        "## Anaerobic respiration\n\n"
        "Anaerobic respiration happens in the cytoplasm, produces only 2 ATP, and in "
        "animal cells produces lactic acid."
    ),
    "source_type": "text",
}


def test_register_seeds_categories_and_profile(auth):
    client, headers, user = auth
    assert user["studyLevel"] == "high-school"
    cats = client.get("/api/v1/categories", headers=headers).json()
    slugs = {c["slug"] for c in cats}
    assert {"mathematics", "biology", "general"} <= slugs
    assert all(c["isDefault"] for c in cats)


def test_update_study_level(auth):
    client, headers, _ = auth
    res = client.patch("/api/v1/auth/me", headers=headers, json={"studyLevel": "a-level"})
    assert res.status_code == 200, res.text
    assert res.json()["studyLevel"] == "a-level"
    bad = client.patch("/api/v1/auth/me", headers=headers, json={"studyLevel": "phd"})
    assert bad.status_code == 422


def test_category_crud(auth):
    client, headers, _ = auth
    res = client.post("/api/v1/categories", headers=headers, json={"label": "Further Maths", "level": "a-level"})
    assert res.status_code == 201, res.text
    cat = res.json()
    assert cat["slug"] == "further-maths" and cat["level"] == "a-level"
    dup = client.post("/api/v1/categories", headers=headers, json={"label": "further maths"})
    assert dup.status_code == 409
    upd = client.patch(f"/api/v1/categories/{cat['id']}", headers=headers, json={"label": "FM"})
    assert upd.json()["label"] == "FM"
    assert client.delete(f"/api/v1/categories/{cat['id']}", headers=headers).status_code == 200


def test_greeting_is_ephemeral(auth):
    client, headers, _ = auth
    res = client.post("/api/v1/query", headers=headers, json={"question": "hi"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["retrievalMode"] == "meta"
    assert body["conversationId"] is None
    assert "StudyBuddy" in body["answer"]


def test_ingest_then_grounded_answer(auth):
    client, headers, _ = auth
    res = client.post("/api/v1/documents", headers=headers, json=_NOTES)
    assert res.status_code == 201, res.text
    assert res.json()["chunksCreated"] >= 1

    ask = client.post(
        "/api/v1/query",
        headers=headers,
        json={"question": "Where does aerobic respiration take place?", "category_id": "biology"},
    )
    assert ask.status_code == 200, ask.text
    body = ask.json()
    assert body["conversationId"]
    assert body["sourceChunks"], "expected retrieved passages"
    assert body["explainLevel"] in ("simple", "standard", "deep", "exam")


def test_answer_without_materials_is_flagged(auth):
    client, headers, _ = auth
    res = client.post(
        "/api/v1/query", headers=headers, json={"question": "Explain the Doppler effect"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # offline provider + no docs → not grounded
    assert body["grounded"] is False
