"""
File: tests/test_agent_routes.py
Purpose: End-to-end persistence tests for the internal agent routes (Gap 4) via the test backend
    instance (TestClient) — service-token auth + least privilege, /complete transitions, and
    /scorecard persisting the transcript batch + scorecard so the user then reads a real scorecard.
Depends on: pytest, fastapi TestClient (conftest fixtures)
Related: app/api/internal.py, app/security_agent.py, app/services/agent_write_service.py
"""

AGENT = {"X-Agent-Token": "test-agent-token"}

SCORECARD_PAYLOAD = {
    "overall_score": 84,
    "strengths": "Clear framing of the good-faith argument.",
    "weaknesses": "Drifted from the record once.",
    "judge_ruling": "The position holds up with cleaner sequencing.",
    "criteria": [
        {"name": "Command of the record", "score": 82},
        {"name": "Responsiveness to rulings", "score": 90},
    ],
    "transcript": [
        {"speaker": "attorney", "content": "Good faith throughout.", "was_interruption": False},
        {"speaker": "opposing_counsel", "content": "Objection.", "was_interruption": True},
        {"speaker": "judge", "content": "Sustained.", "was_interruption": False},
    ],
}


def _new_session(client, auth_headers) -> str:
    case = client.post(
        "/api/cases", headers=auth_headers, json={"title": "Rivera v. Coastal", "case_facts": "F"}
    ).json()
    session = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "oral_argument"},
    ).json()
    return session["id"]


def _complete(client, session_id):
    return client.post(f"/api/sessions/{session_id}/complete", headers=AGENT)


def _write_scorecard(client, session_id):
    return client.post(
        f"/api/sessions/{session_id}/scorecard", headers=AGENT, json=SCORECARD_PAYLOAD
    )


def test_internal_routes_reject_missing_or_wrong_token(client, auth_headers):
    session_id = _new_session(client, auth_headers)
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 401
    bad = client.post(f"/api/sessions/{session_id}/complete", headers={"X-Agent-Token": "nope"})
    assert bad.status_code == 401


def test_least_privilege_both_ways(client, auth_headers):
    session_id = _new_session(client, auth_headers)
    # A user JWT does NOT grant the internal route.
    with_user_jwt = client.post(f"/api/sessions/{session_id}/complete", headers=auth_headers)
    assert with_user_jwt.status_code == 401
    # The agent token does NOT grant a user-facing route.
    assert client.get("/api/cases", headers=AGENT).status_code == 401


def test_complete_transitions_and_is_idempotent(client, auth_headers):
    session_id = _new_session(client, auth_headers)
    resp = _complete(client, session_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["ended_at"] is not None
    # Completing again is a conflict (terminal state).
    assert _complete(client, session_id).status_code == 409


def test_complete_unknown_session_is_404(client):
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/api/sessions/{unknown}/complete", headers=AGENT).status_code == 404


def test_scorecard_requires_completed_and_no_duplicate(client, auth_headers):
    session_id = _new_session(client, auth_headers)
    assert _write_scorecard(client, session_id).status_code == 409  # not completed yet
    _complete(client, session_id)
    assert _write_scorecard(client, session_id).status_code == 201
    assert _write_scorecard(client, session_id).status_code == 409  # duplicate


def test_full_session_end_then_user_reads_scorecard_and_transcript(client, auth_headers):
    session_id = _new_session(client, auth_headers)
    _complete(client, session_id)
    _write_scorecard(client, session_id)

    # The user now reads a REAL scorecard (no more 409 "not available yet").
    scorecard = client.get(f"/api/sessions/{session_id}/scorecard", headers=auth_headers)
    assert scorecard.status_code == 200
    assert scorecard.json()["overall_score"] == 84
    assert scorecard.json()["judge_ruling"] == SCORECARD_PAYLOAD["judge_ruling"]
    # The per-dimension rubric breakdown round-trips (agent → DB → user).
    assert scorecard.json()["criteria"] == SCORECARD_PAYLOAD["criteria"]

    # And the session detail returns the batch-written transcript in order.
    session = client.get(f"/api/sessions/{session_id}", headers=auth_headers).json()
    speakers = [t["speaker"] for t in session["transcripts"]]
    assert speakers == ["attorney", "opposing_counsel", "judge"]
    assert session["transcripts"][1]["was_interruption"] is True


def test_context_route_returns_case_facts_for_agent(client, auth_headers, db_session):
    # §13: cases now carry the forum whose rules ground them — create one (owned by the caller,
    # per-user scoping) and reference it.
    import uuid as _uuid

    from app.models.court import Court

    owner = _uuid.UUID(client.get("/api/auth/me", headers=auth_headers).json()["id"])
    court = Court(id=_uuid.uuid4(), user_id=owner, name="Test Court")
    db_session.add(court)
    db_session.commit()

    facts = "Wrongful-termination retaliation claim."
    case = client.post(
        "/api/cases",
        headers=auth_headers,
        json={"title": "Rivera v. Coastal", "case_facts": facts, "court_id": str(court.id)},
    ).json()
    assert case["court_id"] == str(court.id)
    session = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "oral_argument"},
    ).json()

    resp = client.get(f"/api/sessions/{session['id']}/context", headers=AGENT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_facts"] == facts
    assert body["case_title"] == "Rivera v. Coastal"


def test_context_route_requires_agent_token(client, auth_headers):
    session_id = _new_session(client, auth_headers)
    ctx_url = f"/api/sessions/{session_id}/context"
    # No token, and a user JWT, are both rejected — this is an agent-only internal route.
    assert client.get(ctx_url).status_code == 401
    assert client.get(ctx_url, headers=auth_headers).status_code == 401


def test_session_context_carries_the_case_profile(client, auth_headers):
    # Case profile (migration 0007): user-stated ground truth must reach the agent at room join.
    case = client.post(
        "/api/cases",
        headers=auth_headers,
        json={
            "title": "Metrobank v. SARC",
            "case_facts": "F",
            "case_number": "G.R. No. 218738",
            "petitioner": "Metropolitan Bank & Trust Company",
            "respondent": "Salazar Realty Corporation",
            "represented_party": "respondent",
            "relief_sought": "Nullification of the mortgage; quieting of title.",
        },
    ).json()
    session = client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case["id"], "proceeding_type": "oral_argument"},
    ).json()
    ctx = client.get(f"/api/sessions/{session['id']}/context", headers=AGENT).json()
    assert ctx["case_number"] == "G.R. No. 218738"
    assert ctx["petitioner"] == "Metropolitan Bank & Trust Company"
    assert ctx["respondent"] == "Salazar Realty Corporation"
    assert ctx["represented_party"] == "respondent"
    assert ctx["relief_sought"] == "Nullification of the mortgage; quieting of title."
    # And the shape is rejected when the side is not a real side.
    bad = client.post(
        "/api/cases",
        headers=auth_headers,
        json={"title": "T", "represented_party": "the good guys"},
    )
    assert bad.status_code == 422


def test_scorecard_write_persists_llm_usage(client, auth_headers, db_session):
    """Phase 2 (AUDIT B7/B8): the worker's llm_metrics snapshot rides the scorecard write into
    sessions.llm_usage (migration 0008) — and an older worker that omits it leaves NULL."""
    import uuid as _uuid

    from app.models.session import Session

    usage = {
        "roles": {"judge": {"calls": 3, "errors": 0, "prompt_tokens": 900}},
        "canaries": {"no_verified_sentences": 1},
    }
    session_id = _new_session(client, auth_headers)
    _complete(client, session_id)
    resp = client.post(
        f"/api/sessions/{session_id}/scorecard",
        headers=AGENT,
        json={**SCORECARD_PAYLOAD, "llm_usage": usage},
    )
    assert resp.status_code == 201
    row = db_session.get(Session, _uuid.UUID(session_id))
    db_session.refresh(row)
    assert row.llm_usage == usage

    # Older-worker shape (no llm_usage field at all) → NULL, never an error.
    other_id = _new_session(client, auth_headers)
    _complete(client, other_id)
    assert _write_scorecard(client, other_id).status_code == 201
    other = db_session.get(Session, _uuid.UUID(other_id))
    db_session.refresh(other)
    assert other.llm_usage is None
