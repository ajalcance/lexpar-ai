"""
File: tests/test_sessions.py
Purpose: Session state-transition tests (DEV_GUIDELINES §6) — a new session starts in_progress,
    valid transitions succeed, terminal states are final, unknown statuses are rejected, and the
    scorecard is gated on completion.
Depends on: pytest, fastapi (HTTPException), app services + models (via conftest fixtures)
Related: app/services/session_service.py, app/services/scorecard_service.py
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.scorecard import Scorecard
from app.models.user import User
from app.schemas.case import CaseCreate
from app.services import auth_service, case_service, session_service
from tests.conftest import TEST_EMAIL


def _seed_session(db, user=None):
    """Create a case + fresh session for `user`, registering a default user if none is given.
    HTTP-level tests pass the auth_headers user so the session is owned by the requester."""
    if user is None:
        user = auth_service.register_user(db, "seed@example.com", "seed-password-123")
    case = case_service.create_case(db, user, CaseCreate(title="Rivera v. Coastal", case_facts="F"))
    return session_service.create_session(db, user, case)


def test_new_session_starts_in_progress(db_session):
    session = _seed_session(db_session)
    assert session.status == "in_progress"
    assert session.ended_at is None


def test_transition_in_progress_to_completed(db_session):
    session = _seed_session(db_session)
    updated = session_service.transition_status(db_session, session, "completed")
    assert updated.status == "completed"
    assert updated.ended_at is not None


def test_transition_in_progress_to_abandoned(db_session):
    session = _seed_session(db_session)
    updated = session_service.transition_status(db_session, session, "abandoned")
    assert updated.status == "abandoned"
    assert updated.ended_at is not None


def test_terminal_state_rejects_further_transition(db_session):
    session = _seed_session(db_session)
    session_service.transition_status(db_session, session, "completed")
    with pytest.raises(HTTPException) as exc:
        session_service.transition_status(db_session, session, "in_progress")
    assert exc.value.status_code == 409


def test_unknown_status_is_rejected(db_session):
    session = _seed_session(db_session)
    with pytest.raises(HTTPException) as exc:
        session_service.transition_status(db_session, session, "paused")
    assert exc.value.status_code == 422


def test_scorecard_gated_on_completed_session(client, db_session, auth_headers):
    # Own the session with the SAME user auth_headers authenticated as, so the owner-scoped
    # scorecard route resolves it (409 not-completed) rather than 404 not-owned.
    owner = db_session.scalar(select(User).where(User.email == TEST_EMAIL))
    session = _seed_session(db_session, owner)

    # Before completion the scorecard is unavailable.
    early = client.get(f"/api/sessions/{session.id}/scorecard", headers=auth_headers)
    assert early.status_code == 409

    # Complete the session and attach a scorecard (as the Judge agent eventually will).
    session_service.transition_status(db_session, session, "completed")
    db_session.add(
        Scorecard(
            session_id=session.id,
            overall_score=80,
            strengths="s",
            weaknesses="w",
            judge_ruling="r",
        )
    )
    db_session.commit()

    ready = client.get(f"/api/sessions/{session.id}/scorecard", headers=auth_headers)
    assert ready.status_code == 200
    assert ready.json()["overall_score"] == 80.0


# --- GET /api/cases/{case_id}/sessions (rehearsal history, §UI-redesign) -------------------------


def _create_case_via_api(client, auth_headers, title="History Case"):
    resp = client.post(
        "/api/cases", headers=auth_headers, json={"title": title, "case_facts": "F"}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _start_session_via_api(client, auth_headers, case_id, proceeding_type="oral_argument"):
    resp = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case_id, "proceeding_type": proceeding_type},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_list_case_sessions_returns_the_cases_sessions(client, auth_headers):
    case_id = _create_case_via_api(client, auth_headers)
    first = _start_session_via_api(client, auth_headers, case_id)
    second = _start_session_via_api(client, auth_headers, case_id, "cross_examination")

    resp = client.get(f"/api/cases/{case_id}/sessions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert {s["id"] for s in body} == {first, second}
    # Every returned session belongs to this case.
    assert all(s["case_id"] == case_id for s in body)


def test_list_case_sessions_empty_when_none_started(client, auth_headers):
    case_id = _create_case_via_api(client, auth_headers)
    resp = client.get(f"/api/cases/{case_id}/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_case_sessions_requires_auth(client, auth_headers):
    case_id = _create_case_via_api(client, auth_headers)
    assert client.get(f"/api/cases/{case_id}/sessions").status_code == 401


def test_list_case_sessions_unknown_case_404(client, auth_headers):
    import uuid as _uuid

    resp = client.get(f"/api/cases/{_uuid.uuid4()}/sessions", headers=auth_headers)
    assert resp.status_code == 404
