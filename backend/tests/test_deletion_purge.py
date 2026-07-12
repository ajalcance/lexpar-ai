"""
File: tests/test_deletion_purge.py
Purpose: THE LOAD-BEARING TESTS for the two-tier deletion design (archive/supersede vs purge).
    The poison-pill regression is the one that matters most in this whole feature: a superseded/
    archived document's chunks are rigged to WIN both the semantic ranking (best cosine) AND the
    exact-citation lookup (same section_reference the query cites) — and must still NEVER appear
    in retrieval, at every entry point, on both the court and case corpora. Plus: atomic Replace
    (old stays live until the new ingest is ready; failed ingest never strands the corpus),
    archive/restore (restore refused while superseded), purge cascades (document / case / court),
    provenance tombstones surviving a purge, and court-purge blocking while cases reference it.
Depends on: pytest, app/services/{court_knowledge,case_knowledge,court,case}_service.py
Related: docs/ARCHITECTURE.md §13 (two-tier design), tests/test_courts_api.py (fixture patterns)
Security notes: Fixture text is synthetic placeholder prose, never real statutory language.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.case_document import CaseChunk
from app.models.court import Court
from app.models.court_rule import CourtRuleChunk, CourtRuleDocument
from app.models.ruling_provenance import RulingProvenance
from app.models.user import User
from app.services import (
    case_knowledge_service,
    case_service,
    court_knowledge_service,
    court_service,
)

AGENT = {"X-Agent-Token": "test-agent-token"}

# The poisoned (old) chunk wins EVERY ranking mechanism: identical embedding direction to the
# query (cosine 1.0) and the same section the query cites by name.
OLD_VEC = [1.0, 0.0]
NEW_VEC = [0.6, 0.8]  # valid but a WEAKER cosine match than the old chunk
QUERY_VEC = [1.0, 0.0]


def _court(db, name="Deletion Court") -> Court:
    court = Court(name=name)
    db.add(court)
    db.commit()
    return court


def _rule_doc(db, court, title="Rules v1"):
    return court_knowledge_service.create_rule_document_row(
        db, court.id, title, f"courts/{court.id}/{title}.pdf"
    )


def _add_chunk(db, court, doc_id, idx, text, ref, emb):
    chunk = CourtRuleChunk(
        court_rule_document_id=doc_id,
        court_id=court.id,
        chunk_index=idx,
        chunk_text=text,
        embedding=emb,
        section_reference=ref,
    )
    db.add(chunk)
    db.commit()
    return chunk


def _retrieve(db, court, query="Under Section 42, is the transfer valid?", k=50):
    """Generous k + no floor: if the poisoned chunk CAN appear by any mechanism, it will."""
    return court_knowledge_service.retrieve_rule_refs(
        db, court.id, query, k=k, embedder=lambda q: QUERY_VEC, min_score=0.0
    )


# --- THE poison-pill regression (court corpus) ---------------------------------------------------


def test_superseded_chunks_never_retrievable_even_when_winning_every_ranking(db_session):
    court = _court(db_session)
    old_doc = _rule_doc(db_session, court, "Rules v1")
    old_chunk = _add_chunk(
        db_session, court, old_doc.id, 0,
        "Section 42. OLD stale provision text.", "Section 42", OLD_VEC,
    )
    # Replace: new version ingests successfully → old doc superseded atomically.
    new_doc = _rule_doc(db_session, court, "Rules v2")
    _add_chunk(
        db_session, court, new_doc.id, 0,
        "Section 42. NEW corrected provision text.", "Section 42", NEW_VEC,
    )
    old_doc.deleted_at = court_knowledge_service._now()
    old_doc.superseded_by_id = new_doc.id
    db_session.commit()

    results = _retrieve(db_session, court)
    ids = [chunk_id for chunk_id, _t in results]
    texts = [t for _id, t in results]
    # The old chunk is the best cosine match AND matches the cited section — and must be absent
    # from BOTH the exact-citation path and the semantic path.
    assert str(old_chunk.id) not in ids
    assert not any("OLD stale" in t for t in texts)
    # The replacement IS returned (via the exact-citation path despite its weaker cosine).
    assert any("NEW corrected" in t for t in texts)
    # Same guarantee through the passages-only wrapper.
    passages = court_knowledge_service.retrieve_rule_passages(
        db_session, court.id, "Under Section 42, is the transfer valid?", k=50,
        embedder=lambda q: QUERY_VEC,
    )
    assert not any("OLD stale" in p for p in passages)


def test_superseded_chunks_never_reach_the_agent_route(client, auth_headers, db_session):
    court = _court(db_session, name="Route Court")
    old_doc = _rule_doc(db_session, court, "Rules v1")
    _add_chunk(
        db_session, court, old_doc.id, 0,
        "Section 42. OLD stale provision text.", "Section 42", OLD_VEC,
    )
    old_doc.deleted_at = court_knowledge_service._now()
    db_session.commit()

    from app.services import embedding_service

    case = client.post(
        "/api/cases", headers=auth_headers,
        json={"title": "C", "case_facts": "f", "court_id": str(court.id)},
    ).json()
    session = client.post(
        "/api/sessions", headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "oral_argument"},
    ).json()
    # The agent-facing internal route (what OC/Judge/classifier actually call) — same exclusion.
    resp = client.get(
        f"/api/sessions/{session['id']}/court-rules?q=Under Section 42&k=50", headers=AGENT
    )
    assert resp.status_code == 200
    assert resp.json()["passages"] == []  # archived corpus → nothing, not the stale text
    assert embedding_service is not None  # (import kept local-use explicit)


# --- poison-pill (case corpus) --------------------------------------------------------------------


def _seed_case(db):
    from app.services import auth_service

    user = db.scalar(select(User).where(User.email == "seed@example.com"))
    if user is None:
        user = auth_service.register_user(
            db, "seed@example.com", "a-strong-password-123", None, None
        )
    from app.schemas.case import CaseCreate

    return case_service.create_case(db, user, CaseCreate(title="P", case_facts="f")), user


def test_superseded_pleading_chunks_never_retrievable(db_session):
    case, _user = _seed_case(db_session)
    old_doc = case_knowledge_service.create_document_row(
        db_session, case.id, "v1.pdf", "cases/x/v1.pdf", "application/pdf", 1
    )
    old_chunk = CaseChunk(
        case_id=case.id, document_id=old_doc.id, chunk_index=0,
        content="OLD stale pleading text.", embedding=OLD_VEC,
    )
    db_session.add(old_chunk)
    db_session.commit()

    new_doc = case_knowledge_service.create_document_row(
        db_session, case.id, "v2.pdf", "cases/x/v2.pdf", "application/pdf", 1
    )
    db_session.add(
        CaseChunk(
            case_id=case.id, document_id=new_doc.id, chunk_index=0,
            content="NEW corrected pleading text.", embedding=NEW_VEC,
        )
    )
    case_knowledge_service.archive_case_document(db_session, old_doc)

    refs = case_knowledge_service.retrieve_refs(
        db_session, case.id, "the pleading", k=50, embedder=lambda q: QUERY_VEC
    )
    ids = [chunk_id for chunk_id, _t in refs]
    assert str(old_chunk.id) not in ids
    assert not any("OLD stale" in t for _id, t in refs)
    assert any("NEW corrected" in t for _id, t in refs)
    # context_payload (the agent-facing bundle) inherits the same exclusion. Inject the fake
    # embedder so the test stays offline (no Fireworks/OpenAI key needed in CI).
    payload = case_knowledge_service.context_payload(
        db_session, case.id, "the pleading", k=50, embedder=lambda q: QUERY_VEC
    )
    assert str(old_chunk.id) not in payload["chunk_ids"]


# --- atomic Replace -------------------------------------------------------------------------------


def test_replace_supersedes_old_only_after_new_ingest_succeeds(db_session, monkeypatch):
    from app.services import document_service

    court = _court(db_session, name="Replace Court")
    old_doc = _rule_doc(db_session, court, "Rules v1")
    _add_chunk(db_session, court, old_doc.id, 0, "Section 1. Old.", "Section 1", OLD_VEC)

    # Failed replacement ingest → old version must STAY live (never strand the corpus).
    bad = _rule_doc(db_session, court, "Rules v2 bad")
    monkeypatch.setattr(document_service, "extract_pdf_text", lambda data: "")
    court_knowledge_service.ingest_rule_document(
        db_session, bad, b"%PDF", embedder=lambda t: [], supersedes_document_id=old_doc.id
    )
    db_session.refresh(old_doc)
    assert bad.ingestion_status == "failed"
    assert old_doc.deleted_at is None  # untouched by the failed replace
    assert len(_retrieve(db_session, court, query="old provision")) == 1

    # Successful replacement → old superseded atomically, lineage recorded.
    good = _rule_doc(db_session, court, "Rules v2")
    monkeypatch.setattr(
        document_service, "extract_pdf_text", lambda data: "Section 1. New corrected text."
    )
    court_knowledge_service.ingest_rule_document(
        db_session, good, b"%PDF", embedder=lambda t: [NEW_VEC for _ in t],
        supersedes_document_id=old_doc.id,
    )
    db_session.refresh(old_doc)
    assert good.ingestion_status == "ready"
    assert old_doc.deleted_at is not None
    assert old_doc.superseded_by_id == good.id
    texts = [t for _id, t in _retrieve(db_session, court)]
    assert texts and all("New corrected" in t for t in texts)


# --- archive / restore ----------------------------------------------------------------------------


def test_archive_then_restore_round_trip(db_session):
    court = _court(db_session, name="Archive Court")
    doc = _rule_doc(db_session, court)
    _add_chunk(db_session, court, doc.id, 0, "Section 9. Text.", "Section 9", OLD_VEC)

    court_knowledge_service.archive_rule_document(db_session, doc)
    assert _retrieve(db_session, court, query="Section 9 text") == []
    # rows remain (provenance resolvability): the chunk still exists in the DB
    assert db_session.scalars(
        select(CourtRuleChunk).where(
            CourtRuleChunk.court_rule_document_id == doc.id
        )
    ).all()

    court_knowledge_service.restore_rule_document(db_session, doc)
    assert len(_retrieve(db_session, court, query="Section 9 text")) == 1


def test_restore_refused_while_superseded_by_a_live_replacement(db_session):
    court = _court(db_session, name="No-Restore Court")
    old_doc = _rule_doc(db_session, court, "v1")
    new_doc = _rule_doc(db_session, court, "v2")
    old_doc.deleted_at = court_knowledge_service._now()
    old_doc.superseded_by_id = new_doc.id
    db_session.commit()
    with pytest.raises(ValueError, match="replaced by a newer version"):
        court_knowledge_service.restore_rule_document(db_session, old_doc)


# --- purge (document): cascade + provenance tombstone ---


def test_document_purge_cascades_and_provenance_degrades_gracefully(
    client, auth_headers, db_session, monkeypatch
):
    deleted_keys: list[str] = []
    monkeypatch.setattr(
        "app.services.court_knowledge_service.storage_service.delete_object",
        lambda key: deleted_keys.append(key),
    )
    court = _court(db_session, name="Purge Court")
    doc = _rule_doc(db_session, court)
    chunk = _add_chunk(db_session, court, doc.id, 0, "Section 3. Text.", "Section 3", OLD_VEC)

    # a past ruling cites this chunk
    session = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={
            "case_id": client.post(
                "/api/cases", headers=auth_headers, json={"title": "C", "case_facts": "f"}
            ).json()["id"],
            "proceeding_type": "oral_argument",
        },
    ).json()
    prov = RulingProvenance(
        session_id=uuid.UUID(session["id"]),
        ruling_type="objection_ruling",
        chunk_ids_used=[f"court:{chunk.id}"],
        citation_flags=[],
    )
    db_session.add(prov)
    db_session.commit()

    # the loud warning's number is real
    assert court_knowledge_service.provenance_count_for_document(db_session, doc) == 1

    chunk_id = str(chunk.id)  # capture before purge expires the ORM object
    storage_path = doc.storage_path
    court_knowledge_service.purge_rule_document(db_session, doc)
    # chunks + row + storage gone…
    assert db_session.get(CourtRuleDocument, doc.id) is None
    assert not db_session.scalars(
        select(CourtRuleChunk).where(
            CourtRuleChunk.court_id == court.id
        )
    ).all()
    assert deleted_keys == [storage_path]
    # …but the provenance row SURVIVES as a tombstone (graceful degradation, never an error).
    surviving = db_session.get(RulingProvenance, prov.id)
    assert surviving is not None
    assert surviving.chunk_ids_used == [f"court:{chunk_id}"]


# --- court archive / purge ---


def test_court_archive_cascades_documents_out_of_retrieval(db_session):
    court = _court(db_session, name="Cascade Court")
    doc = _rule_doc(db_session, court)
    _add_chunk(db_session, court, doc.id, 0, "Section 7. Text.", "Section 7", OLD_VEC)
    court_service.archive_court(db_session, court)
    assert court.is_active is False and court.deleted_at is not None
    db_session.refresh(doc)
    assert doc.deleted_at is not None  # cascaded soft-archive
    assert _retrieve(db_session, court, query="Section 7 text") == []


def test_court_purge_blocked_while_cases_reference_it(client, auth_headers, db_session):
    court = _court(db_session, name="Referenced Court")
    client.post(
        "/api/cases", headers=auth_headers,
        json={"title": "Ref Case", "case_facts": "f", "court_id": str(court.id)},
    )
    with pytest.raises(HTTPException) as exc:
        court_service.purge_court(db_session, court)
    assert exc.value.status_code == 409
    assert "Ref Case" in exc.value.detail


# --- case purge cascade ---


def test_case_purge_cascades_everything(client, auth_headers, db_session, monkeypatch):
    deleted_keys: list[str] = []
    monkeypatch.setattr(
        "app.services.storage_service.delete_object", lambda key: deleted_keys.append(key)
    )
    from app.models.scorecard import Scorecard
    from app.models.session import Session as SessionModel
    from app.models.transcript import Transcript

    case_body = client.post(
        "/api/cases", headers=auth_headers, json={"title": "Purge Me", "case_facts": "f"}
    ).json()
    case_id = uuid.UUID(case_body["id"])
    session_body = client.post(
        "/api/sessions", headers=auth_headers,
        json={"case_id": str(case_id), "proceeding_type": "oral_argument"},
    ).json()
    session_id = uuid.UUID(session_body["id"])

    doc = case_knowledge_service.create_document_row(
        db_session, case_id, "p.pdf", "cases/x/p.pdf", "application/pdf", 1
    )
    db_session.add_all(
        [
            CaseChunk(case_id=case_id, document_id=doc.id, chunk_index=0,
                      content="text", embedding=[1.0]),
            Transcript(session_id=session_id, speaker="attorney", content="hi"),
            Scorecard(session_id=session_id, overall_score=90, strengths="s",
                      weaknesses="w", judge_ruling="r"),
            RulingProvenance(session_id=session_id, ruling_type="final_ruling",
                             chunk_ids_used=[], citation_flags=[]),
        ]
    )
    db_session.commit()

    from app.models.case import Case

    case = db_session.get(Case, case_id)
    case_service.purge_case(db_session, case)

    assert db_session.get(Case, case_id) is None
    assert not db_session.scalars(
        select(SessionModel).where(SessionModel.case_id == case_id)
    ).all()
    assert not db_session.scalars(
        select(Transcript).where(Transcript.session_id == session_id)
    ).all()
    assert not db_session.scalars(
        select(Scorecard).where(Scorecard.session_id == session_id)
    ).all()
    assert not db_session.scalars(
        select(RulingProvenance).where(RulingProvenance.session_id == session_id)
    ).all()
    assert not db_session.scalars(
        select(CaseChunk).where(CaseChunk.case_id == case_id)
    ).all()
    assert deleted_keys == ["cases/x/p.pdf"]


def test_destructive_actions_disabled_returns_403(client, auth_headers, db_session, monkeypatch):
    # Competition safeguard: with DESTRUCTIVE_ACTIONS_ENABLED=false, archive + purge are refused
    # site-wide (a shared-credential visitor can't delete/hide the demo data).
    from app.config import get_settings

    case = client.post(
        "/api/cases", headers=auth_headers, json={"title": "Demo case", "case_facts": "F"}
    ).json()
    monkeypatch.setattr(get_settings(), "destructive_actions_enabled", False)

    assert client.delete(f"/api/cases/{case['id']}", headers=auth_headers).status_code == 403
    assert client.post(f"/api/cases/{case['id']}/purge", headers=auth_headers).status_code == 403
    # The case is untouched — still readable.
    assert client.get(f"/api/cases/{case['id']}", headers=auth_headers).status_code == 200
