"""
File: tests/test_courts_api.py
Purpose: Phase 2 (§13) tests — admin role gating on court/rule-corpus management (401/403/OK),
    the attorney-readable court catalog, rule-document upload (storage + background ingest
    monkeypatched), the conservative section-heading extraction, and rule ingest/retrieval with a
    deterministic injected embedder (no network, SQLite).
Depends on: pytest, app/api/courts.py, app/services/{court_service,court_knowledge_service}.py
Related: app/security.py (require_admin), scripts/seed_court.py
Security notes: Fixture text is synthetic placeholder prose — deliberately NOT real statutory
    language (§13 no-fabrication constraint applies to test fixtures too).
"""

import uuid

import pytest

from app.models.court import Court
from app.models.user import User
from app.services import court_knowledge_service

# Synthetic, clearly-fake chunk prose (heading shapes only — no real rule content).
SECTION_CHUNK = "Section 12. Placeholder body text for schema testing only, not a real rule."
RULE_CHUNK = "RULE 3\n\nPlaceholder heading-detection text, not a real rule."
PLAIN_CHUNK = "Plain paragraph with no heading at all, also placeholder text."


@pytest.fixture()
def admin_headers(client, auth_headers, db_session):
    """Log the stub user in, then EXPLICITLY promote them to admin (mirrors the operator action)."""
    me = client.get("/api/auth/me", headers=auth_headers).json()
    user = db_session.get(User, uuid.UUID(me["id"]))
    user.role = "admin"
    db_session.commit()
    return auth_headers


def _court(db_session, name="Seeded Court", **kwargs) -> Court:
    court = Court(name=name, **kwargs)
    db_session.add(court)
    db_session.commit()
    return court


# --- admin gating -------------------------------------------------------------------------------

def test_create_court_requires_auth_and_admin(client, auth_headers):
    body = {"name": "New Court"}
    assert client.post("/api/courts", json=body).status_code == 401  # no token
    # authenticated attorney, not admin → 403 (authenticated but not authorized)
    assert client.post("/api/courts", headers=auth_headers, json=body).status_code == 403


def test_admin_can_create_court(client, admin_headers):
    resp = client.post(
        "/api/courts",
        headers=admin_headers,
        json={"name": "Special Commercial Court", "jurisdiction_description": "test forum"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Special Commercial Court"
    assert resp.json()["is_active"] is True


def test_rule_routes_are_admin_gated(client, auth_headers, db_session):
    court = _court(db_session)
    assert (
        client.get(f"/api/courts/{court.id}/rules", headers=auth_headers).status_code == 403
    )
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=auth_headers,
        files={"file": ("r.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert resp.status_code == 403


# --- attorney-readable catalog --------------------------------------------------------------------

def test_catalog_lists_only_active_courts(client, auth_headers, db_session):
    _court(db_session, name="Active Court")
    _court(db_session, name="Retired Court", is_active=False)
    resp = client.get("/api/courts", headers=auth_headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Active Court" in names
    assert "Retired Court" not in names


def test_catalog_requires_auth(client):
    assert client.get("/api/courts").status_code == 401


# --- rule upload route (storage + background ingest monkeypatched) --------------------------------

def test_rule_upload_creates_pending_document(client, admin_headers, db_session, monkeypatch):
    court = _court(db_session)
    monkeypatch.setattr(
        "app.api.courts.storage_service.put_object", lambda key, data, content_type=None: key
    )
    monkeypatch.setattr("app.api.courts._ingest_in_background", lambda doc_id, path: None)

    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=admin_headers,
        files={"file": ("interim_rules.pdf", b"%PDF-fake", "application/pdf")},
        data={
            "title": "Operator-supplied rules",
            "source_citation": "(operator citation)",
            "source_reference": "https://official.example/rules",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["ingestion_status"] == "pending"
    assert body["title"] == "Operator-supplied rules"
    assert body["source_citation"] == "(operator citation)"

    listed = client.get(f"/api/courts/{court.id}/rules", headers=admin_headers).json()
    assert [d["id"] for d in listed] == [body["id"]]


def test_rule_upload_rejects_non_pdf(client, admin_headers, db_session):
    court = _court(db_session)
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=admin_headers,
        files={"file": ("rules.txt", b"text", "text/plain")},
    )
    assert resp.status_code == 415


# --- section-heading extraction (pure, conservative) ----------------------------------------------

def test_extract_section_reference_recognizes_headings():
    assert court_knowledge_service.extract_section_reference(SECTION_CHUNK) == "Section 12"
    assert court_knowledge_service.extract_section_reference(RULE_CHUNK) == "Rule 3"
    assert court_knowledge_service.extract_section_reference("Sec. 5 placeholder.") == "Sec. 5"


def test_extract_section_reference_null_when_not_confident():
    assert court_knowledge_service.extract_section_reference(PLAIN_CHUNK) is None
    # heading-like text NOT at the start doesn't count
    assert (
        court_knowledge_service.extract_section_reference("As stated in Section 4, …") is None
    )
    assert court_knowledge_service.extract_section_reference("Section without number") is None


# --- ingest + retrieval (injected embedder, no network) ------------------------------------------

def _keyword_embedder(keywords):
    def embed(texts):
        single = isinstance(texts, str)
        items = [texts] if single else texts
        vecs = [[float(t.lower().count(k)) for k in keywords] for t in items]
        return vecs[0] if single else vecs

    return embed


def test_ingest_rule_document_persists_chunks_with_sections(db_session, monkeypatch):
    from app.services import document_service

    court = _court(db_session)
    document = court_knowledge_service.create_rule_document_row(
        db_session, court.id, "Rules", "courts/x/rules.pdf"
    )
    monkeypatch.setattr(
        document_service, "extract_pdf_text", lambda data: f"{SECTION_CHUNK}\n\n{PLAIN_CHUNK}"
    )
    embed = _keyword_embedder(["placeholder", "schema", "heading"])
    court_knowledge_service.ingest_rule_document(db_session, document, b"%PDF", embedder=embed)

    db_session.refresh(document)
    assert document.ingestion_status == "ready"
    assert document.chunk_count >= 1
    from sqlalchemy import select

    from app.models.court_rule import CourtRuleChunk

    chunks = db_session.scalars(
        select(CourtRuleChunk).where(CourtRuleChunk.court_id == court.id)
    ).all()
    assert chunks  # denormalized court_id is queryable directly
    assert chunks[0].section_reference == "Section 12"  # first chunk opens with the heading


def test_ingest_rule_document_marks_failed_on_no_text(db_session, monkeypatch):
    from app.services import document_service

    court = _court(db_session)
    document = court_knowledge_service.create_rule_document_row(
        db_session, court.id, "Scan", "courts/x/scan.pdf"
    )
    monkeypatch.setattr(document_service, "extract_pdf_text", lambda data: "")
    court_knowledge_service.ingest_rule_document(
        db_session, document, b"%PDF", embedder=lambda t: []
    )
    db_session.refresh(document)
    assert document.ingestion_status == "failed"
    assert "OCR" in (document.error or "")


def test_retrieve_rule_passages_scoped_to_court_with_section_prefix(db_session, monkeypatch):
    from app.services import document_service

    court = _court(db_session, name="Court A")
    other = _court(db_session, name="Court B")
    document = court_knowledge_service.create_rule_document_row(
        db_session, court.id, "Rules", "courts/x/rules.pdf"
    )
    monkeypatch.setattr(
        document_service,
        "extract_pdf_text",
        lambda data: f"{SECTION_CHUNK}\n\n{PLAIN_CHUNK}",
    )
    embed = _keyword_embedder(["schema", "heading", "paragraph"])
    court_knowledge_service.ingest_rule_document(db_session, document, b"%PDF", embedder=embed)

    hits = court_knowledge_service.retrieve_rule_passages(
        db_session, court.id, "schema testing", k=1, embedder=embed
    )
    assert len(hits) == 1
    assert hits[0].startswith("[Section 12] ")  # verbatim text, heading-prefixed

    # scoped: the other court has no chunks
    assert (
        court_knowledge_service.retrieve_rule_passages(
            db_session, other.id, "schema testing", embedder=embed
        )
        == []
    )


# --- §13 Phase 3: internal court-rules route + context court_id --------------------------------

AGENT = {"X-Agent-Token": "test-agent-token"}


def _session_for_court(client, auth_headers, court_id=None):
    body = {"title": "C", "case_facts": "f"}
    if court_id:
        body["court_id"] = str(court_id)
    case = client.post("/api/cases", headers=auth_headers, json=body).json()
    return client.post(
        "/api/sessions", headers=auth_headers, json={"case_id": case["id"]}
    ).json()


def test_context_route_carries_court_id_and_proceeding_type(client, auth_headers, db_session):
    court = _court(db_session, name="Context Court")
    session = _session_for_court(client, auth_headers, court.id)
    body = client.get(f"/api/sessions/{session['id']}/context", headers=AGENT).json()
    assert body["court_id"] == str(court.id)
    assert body["proceeding_type"] == "oral_argument"
    # and empty-string (not null/missing) when the case names no court
    plain = _session_for_court(client, auth_headers)
    body = client.get(f"/api/sessions/{plain['id']}/context", headers=AGENT).json()
    assert body["court_id"] == ""


def test_court_rules_route_requires_agent_token(client, auth_headers):
    session = _session_for_court(client, auth_headers)
    url = f"/api/sessions/{session['id']}/court-rules?q=test"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_headers).status_code == 401  # user JWT is not enough
    ok = client.get(url, headers=AGENT)
    assert ok.status_code == 200
    assert ok.json() == {"passages": []}  # no court on the case → empty, fail-open


def test_court_rules_route_returns_passages(client, auth_headers, db_session, monkeypatch):
    from app.services import document_service, embedding_service

    court = _court(db_session, name="Rules Court")
    document = court_knowledge_service.create_rule_document_row(
        db_session, court.id, "Rules", "courts/x/rules.pdf"
    )
    monkeypatch.setattr(
        document_service, "extract_pdf_text", lambda data: f"{SECTION_CHUNK}\n\n{PLAIN_CHUNK}"
    )
    embed = _keyword_embedder(["schema", "heading", "paragraph"])
    court_knowledge_service.ingest_rule_document(db_session, document, b"%PDF", embedder=embed)
    monkeypatch.setattr(embedding_service, "embed_text", embed)

    session = _session_for_court(client, auth_headers, court.id)
    resp = client.get(
        f"/api/sessions/{session['id']}/court-rules?q=schema testing&k=1", headers=AGENT
    )
    assert resp.status_code == 200
    passages = resp.json()["passages"]
    assert len(passages) == 1
    assert passages[0].startswith("[Section 12] ")
