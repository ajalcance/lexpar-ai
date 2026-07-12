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
    """The first registered user IS the admin (§13 first-login bootstrap); set explicitly anyway
    so this fixture stays correct even if the arrangement around it changes."""
    me = client.get("/api/auth/me", headers=auth_headers).json()
    user = db_session.get(User, uuid.UUID(me["id"]))
    user.role = "admin"
    db_session.commit()
    return auth_headers


@pytest.fixture()
def attorney_headers(client, auth_headers, db_session):
    """A NON-admin authenticated user for 403 gating tests. The first login auto-promotes (§13
    bootstrap), so an ordinary attorney must be arranged by demoting after login."""
    me = client.get("/api/auth/me", headers=auth_headers).json()
    user = db_session.get(User, uuid.UUID(me["id"]))
    user.role = "attorney"
    db_session.commit()
    return auth_headers


def _court(db_session, name="Seeded Court", **kwargs) -> Court:
    court = Court(name=name, **kwargs)
    db_session.add(court)
    db_session.commit()
    return court


# --- admin gating -------------------------------------------------------------------------------

def test_create_court_requires_auth_and_admin(client, attorney_headers):
    body = {"name": "New Court"}
    assert client.post("/api/courts", json=body).status_code == 401  # no token
    # authenticated attorney, not admin → 403 (authenticated but not authorized)
    assert client.post("/api/courts", headers=attorney_headers, json=body).status_code == 403


def test_admin_can_create_court(client, admin_headers):
    resp = client.post(
        "/api/courts",
        headers=admin_headers,
        json={"name": "Special Commercial Court", "jurisdiction_description": "test forum"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Special Commercial Court"
    assert resp.json()["is_active"] is True


def test_rule_routes_are_admin_gated(client, attorney_headers, db_session):
    court = _court(db_session)
    assert (
        client.get(f"/api/courts/{court.id}/rules", headers=attorney_headers).status_code == 403
    )
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=attorney_headers,
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


def test_rule_upload_rejects_oversize_with_actionable_detail(
    client, admin_headers, db_session, monkeypatch
):
    # Over the size cap → 413 with a specific, surfaceable detail (the frontend shows this message,
    # not a generic "Upload failed"). Patch the cap to 0 so any non-empty file trips it.
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    court = _court(db_session)
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=admin_headers,
        files={"file": ("big.pdf", b"%PDF-1.4 some bytes", "application/pdf")},
    )
    assert resp.status_code == 413
    assert "exceeds" in resp.json()["detail"].lower()


def test_rule_upload_rejects_non_pdf(client, admin_headers, db_session):
    court = _court(db_session)
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=admin_headers,
        files={"file": ("rules.txt", b"text", "text/plain")},
    )
    assert resp.status_code == 415


def test_rule_upload_rejects_pdf_labelled_bytes_without_a_pdf_header(
    client, admin_headers, db_session
):
    # Magic-byte guard: a non-PDF relabelled as application/pdf (content-type is spoofable) is
    # rejected on the missing %PDF- header, not silently stored.
    court = _court(db_session)
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=admin_headers,
        files={"file": ("fake.pdf", b"this is definitely not a pdf", "application/pdf")},
    )
    assert resp.status_code == 415
    assert "pdf" in resp.json()["detail"].lower()


def test_rule_upload_rejects_empty_file(client, admin_headers, db_session):
    court = _court(db_session)
    resp = client.post(
        f"/api/courts/{court.id}/rules",
        headers=admin_headers,
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 422


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


def test_ingest_rule_document_fails_on_near_empty_text(db_session, monkeypatch):
    # A scanned/image rule PDF (no or near-no extractable text) fails ingest with an actionable
    # message pointing at a text-based official copy — never leaves the document silently pending.
    from app.services import document_service

    court = _court(db_session)
    document = court_knowledge_service.create_rule_document_row(
        db_session, court.id, "Scanned Rules", "courts/x/scan.pdf"
    )
    monkeypatch.setattr(document_service, "extract_pdf_text", lambda data: "  RA 11232  ")
    court_knowledge_service.ingest_rule_document(
        db_session, document, b"%PDF", embedder=lambda t: []
    )
    db_session.refresh(document)
    assert document.ingestion_status == "failed"
    assert document.chunk_count == 0
    assert "text-based PDF" in (document.error or "")


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
    assert "scanned" in (document.error or "").lower()


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
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "oral_argument"},
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
    assert ok.json() == {"passages": [], "chunk_ids": []}  # no court → empty, fail-open


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


# --- §13 Phase 5: chunk ids in retrieval + ruling provenance --------------------------------------

def test_court_rules_route_returns_parallel_chunk_ids(
    client, auth_headers, db_session, monkeypatch
):
    from app.services import document_service, embedding_service

    court = _court(db_session, name="Prov Court")
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
    body = client.get(
        f"/api/sessions/{session['id']}/court-rules?q=schema testing&k=1", headers=AGENT
    ).json()
    assert len(body["passages"]) == 1
    assert len(body["chunk_ids"]) == 1  # parallel arrays: id[i] produced passage[i]
    import uuid as _uuid

    from app.models.court_rule import CourtRuleChunk

    row = db_session.get(CourtRuleChunk, _uuid.UUID(body["chunk_ids"][0]))
    assert row is not None and row.court_id == court.id


def test_provenance_route_persists_and_validates(client, auth_headers, db_session):
    session = _session_for_court(client, auth_headers)
    url = f"/api/sessions/{session['id']}/provenance"
    payload = {
        "ruling_type": "objection_ruling",
        "chunk_ids_used": ["court:abc", "case:def"],
        "citation_flags": ["Rule 99"],
    }
    # agent-token only
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, headers=auth_headers, json=payload).status_code == 401
    created = client.post(url, headers=AGENT, json=payload)
    assert created.status_code == 201

    import uuid as _uuid

    from app.models.ruling_provenance import RulingProvenance

    row = db_session.get(RulingProvenance, _uuid.UUID(created.json()["id"]))
    assert row.ruling_type == "objection_ruling"
    assert row.chunk_ids_used == ["court:abc", "case:def"]
    assert row.citation_flags == ["Rule 99"]

    # unknown ruling type → 422; unknown session → 404
    bad = dict(payload, ruling_type="hunch")
    assert client.post(url, headers=AGENT, json=bad).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.post(f"/api/sessions/{missing}/provenance", headers=AGENT, json=payload).status_code
        == 404
    )


def test_user_reads_provenance_for_own_session(client, auth_headers):
    session = _session_for_court(client, auth_headers)
    url = f"/api/sessions/{session['id']}/provenance"
    # agent writes two rows (the live worker's paths)
    for ruling_type, flags in (("objection_ruling", ["Rule 99"]), ("final_ruling", [])):
        assert (
            client.post(
                url,
                headers=AGENT,
                json={
                    "ruling_type": ruling_type,
                    "chunk_ids_used": ["court:x"],
                    "citation_flags": flags,
                },
            ).status_code
            == 201
        )
    # the owning attorney reads them back (oldest first)
    rows = client.get(url, headers=auth_headers)
    assert rows.status_code == 200
    body = rows.json()
    assert [r["ruling_type"] for r in body] == ["objection_ruling", "final_ruling"]
    assert body[0]["citation_flags"] == ["Rule 99"]
    # least privilege both ways: no token → 401; the agent token can't use the USER read route
    assert client.get(url).status_code == 401
    assert client.get(url, headers=AGENT).status_code == 401
    # empty when a session has no rulings
    other = _session_for_court(client, auth_headers)
    assert client.get(
        f"/api/sessions/{other['id']}/provenance", headers=auth_headers
    ).json() == []


# --- Retrieval accuracy: section-aware chunking (A), exact lookup (B), relevance floor (D) -------

def test_chunk_rule_text_keeps_short_sections_whole_and_labels_oversized_subchunks():
    from app.services import document_service

    filler = "filler clause number here. " * ((document_service.CHUNK_CHARS // 27) + 50)
    doc = (
        "Preliminary title, not a section, appearing before the first heading.\n\n"
        "Section 1. A short and complete provision that fits in one chunk.\n\n"
        f"Section 2. {filler} final proviso clause.\n\n"
        "Section 3. Another short provision whose concluding exception must stay intact."
    )
    by_ref: dict = {}
    for text, ref in court_knowledge_service.chunk_rule_text(doc):
        by_ref.setdefault(ref, []).append(text)
    # short sections → exactly one complete chunk each (the tail/exception is not lost)
    assert len(by_ref["Section 1"]) == 1
    assert "one chunk" in by_ref["Section 1"][0]
    assert len(by_ref["Section 3"]) == 1
    assert "concluding exception must stay intact" in by_ref["Section 3"][0]
    # oversized section → multiple sub-chunks, ALL labeled Section 2 (no NULL mid-section chunks)
    assert len(by_ref["Section 2"]) >= 2
    # the no-heading preamble degrades to an unlabeled windowed chunk, never fails
    assert None in by_ref and any("Preliminary title" in t for t in by_ref[None])


def test_chunk_rule_text_no_headings_degrades_to_windowed_unlabeled():
    doc = "Rule prose with no detectable section headings anywhere in it. " * 5
    pairs = court_knowledge_service.chunk_rule_text(doc)
    assert pairs
    assert all(ref is None for _t, ref in pairs)


def _add_rule_chunk(db, court, doc_id, idx, text, ref, emb):
    from app.models.court_rule import CourtRuleChunk

    db.add(
        CourtRuleChunk(
            court_rule_document_id=doc_id,
            court_id=court.id,
            chunk_index=idx,
            chunk_text=text,
            embedding=emb,
            section_reference=ref,
        )
    )
    db.commit()


def test_exact_citation_lookup_bypasses_semantic_rank_and_floor(db_session):
    court = _court(db_session)
    doc = court_knowledge_service.create_rule_document_row(db_session, court.id, "R", "p")
    _add_rule_chunk(db_session, court, doc.id, 0, "Section 73. Squeeze-out.", "Section 73", [0, 1])
    _add_rule_chunk(db_session, court, doc.id, 1, "Section 5. Definitions.", "Section 5", [1, 0])
    # query embeds near Section 5 (cosine 1) and ORTHOGONAL to Section 73 (cosine 0 < floor)
    refs = court_knowledge_service.retrieve_rule_refs(
        db_session, court.id, "Is a Section 73 squeeze-out valid?", k=1,
        embedder=lambda q: [1.0, 0.0], min_score=0.35,
    )
    texts = [t for _id, t in refs]
    # Section 73 is returned FIRST via exact lookup despite being below the relevance floor
    assert texts[0].startswith("[Section 73]")
    # invariant: every returned passage is exactly a stored chunk's text (nothing fabricated)
    assert all(t.startswith("[Section 73]") or t.startswith("[Section 5]") for t in texts)


def test_relevance_floor_returns_fewer_and_zero_without_padding(db_session):
    court = _court(db_session)
    doc = court_knowledge_service.create_rule_document_row(db_session, court.id, "R", "p")
    _add_rule_chunk(db_session, court, doc.id, 0, "Section 1. On point.", "Section 1", [1.0, 0.0])
    _add_rule_chunk(db_session, court, doc.id, 1, "Section 2. Off topic.", "Section 2", [0.0, 1.0])
    # near Section 1 only → Section 2 (cosine 0) dropped by the floor → FEWER than k
    near = court_knowledge_service.retrieve_rule_refs(
        db_session, court.id, "unrelated words", k=4, embedder=lambda q: [1.0, 0.0], min_score=0.35,
    )
    assert len(near) == 1 and near[0][1].startswith("[Section 1]")
    # orthogonal to everything, no citation → ZERO (fail-open no-block), not padded to k
    zero = court_knowledge_service.retrieve_rule_refs(
        db_session, court.id, "totally unrelated", k=4, embedder=lambda q: [0.0, 0], min_score=0.35,
    )
    assert zero == []
    # WITHOUT the floor, the same weak query pads out to the available chunks (contrast)
    padded = court_knowledge_service.retrieve_rule_refs(
        db_session, court.id, "unrelated words", k=4, embedder=lambda q: [1.0, 0.0], min_score=0.0,
    )
    assert len(padded) == 2


# --- admin catalog (include_archived) -------------------------------------------------------------

def test_admin_catalog_includes_archived_courts(client, admin_headers, db_session):
    from datetime import datetime, timezone

    _court(db_session, name="Active Court")
    _court(db_session, name="Archived Court", deleted_at=datetime.now(timezone.utc))
    resp = client.get("/api/courts?include_archived=true", headers=admin_headers)
    assert resp.status_code == 200
    by_name = {c["name"]: c for c in resp.json()}
    assert by_name["Active Court"]["archived"] is False
    assert by_name["Archived Court"]["archived"] is True
    # The regular catalog still hides it (case creation is unaffected).
    names = [c["name"] for c in client.get("/api/courts", headers=admin_headers).json()]
    assert "Archived Court" not in names


def test_admin_catalog_flag_requires_admin(client, attorney_headers):
    resp = client.get("/api/courts?include_archived=true", headers=attorney_headers)
    assert resp.status_code == 403


def test_archived_court_can_still_be_purged(client, admin_headers, db_session):
    from datetime import datetime, timezone

    court = _court(db_session, name="Retired Forum", deleted_at=datetime.now(timezone.utc))
    resp = client.post(f"/api/courts/{court.id}/purge", headers=admin_headers)
    # Previously 404: the purge route fetched via get_court, which filters archived rows —
    # an archived court was an invisible, undeletable orphan.
    assert resp.status_code == 204
    assert client.get("/api/courts?include_archived=true", headers=admin_headers).json() == []
