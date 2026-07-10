"""
File: tests/test_court_schema.py
Purpose: Phase 1 (§13) schema tests — the Court / CourtRuleDocument / CourtRuleChunk models and
    their defaults, the new cases.court_id / sessions.proceeding_type / users.role columns, and
    the case-creation validation of court_id. Pure SQLite/portable per DEV_GUIDELINES §6.
Depends on: pytest, app/models/*, TestClient fixtures (tests/conftest.py)
Related: app/models/{court,court_rule}.py, alembic/versions/0003_court_grounding.py
"""

import uuid

from app.models.court import Court
from app.models.court_rule import CourtRuleChunk, CourtRuleDocument
from app.models.session import DEFAULT_PROCEEDING_TYPE, PROCEEDING_TYPES
from app.models.user import DEFAULT_USER_ROLE, USER_ROLES

# --- model rows + defaults ----------------------------------------------------------------------

def test_court_and_rule_corpus_rows_persist_with_defaults(db_session):
    court = Court(name="Test Special Commercial Court", jurisdiction_description="test forum")
    db_session.add(court)
    db_session.commit()
    assert court.is_active is True
    assert court.deleted_at is None

    document = CourtRuleDocument(
        court_id=court.id,
        title="Operator-supplied rule document",
        source_citation="(operator-supplied citation)",
        source_reference="https://official.example/source",
        storage_path="courts/x/rules.pdf",
    )
    db_session.add(document)
    db_session.commit()
    assert document.ingestion_status == "pending"
    assert document.chunk_count == 0
    assert document.uploaded_by_user_id is None  # seed-script ingests may have no request user

    chunk = CourtRuleChunk(
        court_rule_document_id=document.id,
        court_id=court.id,
        chunk_index=0,
        chunk_text="(operator-supplied text placeholder for schema test only)",
        embedding=[0.1, 0.2, 0.3],
        section_reference=None,  # NULL when not confidently extractable — never guessed
    )
    db_session.add(chunk)
    db_session.commit()
    fetched = db_session.get(CourtRuleChunk, chunk.id)
    assert fetched.embedding == [0.1, 0.2, 0.3]
    assert fetched.section_reference is None


def test_constants_shape():
    assert PROCEEDING_TYPES == (
        "oral_argument",
        "direct_examination",
        "cross_examination",
        "motion_hearing",
    )
    assert DEFAULT_PROCEEDING_TYPE in PROCEEDING_TYPES
    assert USER_ROLES == ("attorney", "admin")
    assert DEFAULT_USER_ROLE == "attorney"


# --- new columns through the API ------------------------------------------------------------------

def test_stub_user_gets_attorney_role(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["role"] == "attorney"  # no user silently becomes admin


def test_session_creation_requires_valid_proceeding_type(client, auth_headers):
    # §13 Phase 4: proceeding_type is REQUIRED at creation and validated against the taxonomy.
    case = client.post(
        "/api/cases", headers=auth_headers, json={"title": "C", "case_facts": "f"}
    ).json()
    missing = client.post(
        "/api/sessions", headers=auth_headers, json={"case_id": case["id"]}
    )
    assert missing.status_code == 422
    invalid = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "bench_trial"},
    )
    assert invalid.status_code == 422
    for proceeding_type in PROCEEDING_TYPES:
        created = client.post(
            "/api/sessions",
            headers=auth_headers,
            json={"case_id": case["id"], "proceeding_type": proceeding_type},
        )
        assert created.status_code == 201
        assert created.json()["proceeding_type"] == proceeding_type


def test_case_create_accepts_valid_court(client, auth_headers, db_session):
    court = Court(name="Test Court")
    db_session.add(court)
    db_session.commit()
    resp = client.post(
        "/api/cases",
        headers=auth_headers,
        json={"title": "With court", "case_facts": "f", "court_id": str(court.id)},
    )
    assert resp.status_code == 201
    assert resp.json()["court_id"] == str(court.id)


def test_case_create_rejects_unknown_court(client, auth_headers):
    resp = client.post(
        "/api/cases",
        headers=auth_headers,
        json={"title": "Bad court", "case_facts": "f", "court_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
    assert "court" in resp.json()["detail"].lower()


def test_case_create_rejects_inactive_court(client, auth_headers, db_session):
    court = Court(name="Retired Court", is_active=False)
    db_session.add(court)
    db_session.commit()
    resp = client.post(
        "/api/cases",
        headers=auth_headers,
        json={"title": "Retired", "case_facts": "f", "court_id": str(court.id)},
    )
    assert resp.status_code == 422


def test_case_create_without_court_still_works_during_rollout(client, auth_headers):
    # Phase 1 behavior: court_id optional until the catalog route + UI selector land (Phases 2/6).
    resp = client.post(
        "/api/cases", headers=auth_headers, json={"title": "No court yet", "case_facts": "f"}
    )
    assert resp.status_code == 201
    assert resp.json()["court_id"] is None
