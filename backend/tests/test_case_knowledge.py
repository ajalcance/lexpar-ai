"""
File: tests/test_case_knowledge.py
Purpose: Tests for the Case Knowledge Base (§12) — pure chunking + cosine ranking, and the ingest →
    retrieve orchestration with an injected deterministic embedder/summarizer (no network, SQLite).
    Also the agent-authed knowledge internal route end to end.
Depends on: pytest, app.services.{document,embedding,case_knowledge}_service, TestClient
"""

import uuid

from app.models.case import Case
from app.models.court import Court
from app.services import case_knowledge_service, document_service, embedding_service

AGENT = {"X-Agent-Token": "test-agent-token"}


# --- pure pieces ------------------------------------------------------------------------------

def test_chunk_text_overlaps_and_covers():
    text = "\n\n".join(f"Paragraph {i} with several words of content here." for i in range(50))
    chunks = document_service.chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)
    # every paragraph's number appears somewhere (nothing dropped)
    joined = " ".join(chunks)
    assert "Paragraph 0" in joined and "Paragraph 49" in joined


def test_chunk_text_empty():
    assert document_service.chunk_text("   ") == []


def test_cosine_and_top_k():
    q = [1.0, 0.0, 0.0]
    cands = [("east", [1.0, 0.0, 0.0]), ("north", [0.0, 1.0, 0.0]), ("east-ish", [0.9, 0.1, 0.0])]
    assert embedding_service.cosine_similarity([1, 0], [1, 0]) == 1.0
    assert embedding_service.top_k(q, cands, 2) == ["east", "east-ish"]


# --- ingest + retrieve (injected embedder/summarizer) -----------------------------------------

def _keyword_embedder(keywords):
    """A toy embedder: each text → a vector of keyword-presence counts. Deterministic, offline."""

    def embed(texts):
        single = isinstance(texts, str)
        items = [texts] if single else texts
        vecs = [[float(t.lower().count(k)) for k in keywords] for t in items]
        return vecs[0] if single else vecs

    return embed


def _seed_case(db_session):
    # §13: cases now reference the forum whose rules ground them.
    court = Court(id=uuid.uuid4(), name="Test Court")
    db_session.add(court)
    case = Case(id=uuid.uuid4(), user_id=uuid.uuid4(), title="Rivera v. Coastal", court_id=court.id)
    db_session.add(case)
    db_session.commit()
    return case


def test_ingest_persists_chunks_and_summary(monkeypatch, db_session):
    case = _seed_case(db_session)
    document = case_knowledge_service.create_document_row(
        db_session, case.id, "complaint.pdf", "cases/x/complaint.pdf", "application/pdf", 1234
    )
    # avoid a real PDF: inject the extracted text
    monkeypatch.setattr(
        document_service,
        "extract_pdf_text",
        lambda data: "The plaintiff was terminated. The termination followed a safety report.",
    )
    embed = _keyword_embedder(["terminated", "safety", "report"])

    case_knowledge_service.ingest_document(
        db_session,
        document,
        b"%PDF-fake",
        embedder=embed,
        summarizer=lambda text: "PARTIES: plaintiff v. Coastal. CLAIM: wrongful termination.",
    )
    db_session.refresh(document)
    assert document.status == "ready"
    assert document.chunk_count >= 1
    db_session.refresh(case)
    assert "wrongful termination" in case.case_summary


def test_ingest_marks_failed_on_no_text(monkeypatch, db_session):
    case = _seed_case(db_session)
    document = case_knowledge_service.create_document_row(
        db_session, case.id, "scan.pdf", "cases/x/scan.pdf", "application/pdf", 10
    )
    monkeypatch.setattr(document_service, "extract_pdf_text", lambda data: "")  # scanned/no text
    case_knowledge_service.ingest_document(db_session, document, b"%PDF", embedder=lambda t: [])
    db_session.refresh(document)
    assert document.status == "failed"
    assert "OCR" in (document.error or "")


def test_retrieve_ranks_relevant_passages(monkeypatch, db_session):
    case = _seed_case(db_session)
    document = case_knowledge_service.create_document_row(
        db_session, case.id, "c.pdf", "k", "application/pdf", 1
    )
    monkeypatch.setattr(
        document_service,
        "extract_pdf_text",
        lambda data: (
            "The safety report was filed on March 3.\n\n"
            "The employment contract is unrelated boilerplate about vacation days."
        ),
    )
    embed = _keyword_embedder(["safety", "report", "contract", "vacation"])
    case_knowledge_service.ingest_document(
        db_session, document, b"%PDF", embedder=embed, summarizer=lambda t: "summary"
    )

    hits = case_knowledge_service.retrieve(
        db_session, case.id, "when was the safety report filed", k=1, embedder=embed
    )
    assert len(hits) == 1
    assert "safety report" in hits[0].lower()


def test_retrieve_empty_when_no_documents(db_session):
    case = _seed_case(db_session)
    assert case_knowledge_service.retrieve(db_session, case.id, "anything") == []


# --- agent-authed knowledge route -------------------------------------------------------------

def test_internal_knowledge_route_requires_agent_token(client, auth_headers):
    case = client.post(
        "/api/cases", headers=auth_headers, json={"title": "C", "case_facts": "f"}
    ).json()
    session = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "oral_argument"},
    ).json()
    url = f"/api/sessions/{session['id']}/knowledge?q=test"
    assert client.get(url).status_code == 401  # no token
    assert client.get(url, headers=auth_headers).status_code == 401  # user JWT, not agent
    # agent token: works, returns the (empty, no-pleading) knowledge bundle
    ok = client.get(url, headers=AGENT)
    assert ok.status_code == 200
    assert ok.json() == {"summary": "", "passages": []}
