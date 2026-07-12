"""
File: tests/test_session_isolation.py
Purpose: Lock the invariant that every sparring session is INDEPENDENT — no content from a prior
    rehearsal of the same case leaks into the next. Guards three vectors end to end against the real
    DB + routes: (1) a new session's join context carries only case-level fields, never a prior
    session's transcript or scorecard; (2) writing a session's transcript adds nothing to the
    case-knowledge retrieval corpus (case_chunks) — spoken arguments are never embedded/retrieved;
    (3) scorecards are per-session, never aggregated across rehearsals of one case.
Depends on: pytest, fastapi TestClient (conftest fixtures)
Related: app/services/agent_write_service.py, app/services/case_knowledge_service.py
"""

from sqlalchemy import func, select

from app.models.case_document import CaseChunk

AGENT = {"X-Agent-Token": "test-agent-token"}


def _make_case(client, auth_headers, facts: str) -> str:
    return client.post(
        "/api/cases",
        headers=auth_headers,
        json={"title": "Metrobank v. Salazar", "case_facts": facts},
    ).json()["id"]


def _new_session(client, auth_headers, case_id: str) -> str:
    return client.post(
        "/api/sessions",
        headers=auth_headers,
        json={"case_id": case_id, "proceeding_type": "oral_argument"},
    ).json()["id"]


def _run_and_score(client, session_id: str, *, line: str, weakness: str, score: int) -> None:
    """Complete a session and write its scorecard + a one-line transcript, as the agent does."""
    client.post(f"/api/sessions/{session_id}/complete", headers=AGENT)
    resp = client.post(
        f"/api/sessions/{session_id}/scorecard",
        headers=AGENT,
        json={
            "overall_score": score,
            "strengths": "s",
            "weaknesses": weakness,
            "judge_ruling": "r",
            "transcript": [{"speaker": "attorney", "content": line, "was_interruption": False}],
        },
    )
    assert resp.status_code == 201


def test_new_session_context_carries_no_prior_session_content(client, auth_headers):
    case_id = _make_case(client, auth_headers, facts="CASE_FACTS_MARKER")
    # Session A: a full rehearsal with a distinctive argument + a distinctive scorecard weakness.
    a = _new_session(client, auth_headers, case_id)
    _run_and_score(
        client, a, line="SECRET_ARGUMENT_FROM_SESSION_A", weakness="WEAKNESS_A", score=30
    )

    # Session B on the SAME case: its join context must be case-only — nothing from A.
    b = _new_session(client, auth_headers, case_id)
    ctx = client.get(f"/api/sessions/{b}/context", headers=AGENT).json()
    blob = " ".join(str(v) for v in ctx.values())
    assert "CASE_FACTS_MARKER" in blob  # the shared case material IS present (correct — same case)
    assert "SECRET_ARGUMENT_FROM_SESSION_A" not in blob  # A's transcript never leaks forward
    assert "WEAKNESS_A" not in blob  # A's scorecard never leaks forward


def test_writing_a_transcript_adds_nothing_to_retrieval_corpus(client, auth_headers, db_session):
    case_id = _make_case(client, auth_headers, facts="Facts.")
    before = db_session.scalar(select(func.count()).select_from(CaseChunk))
    a = _new_session(client, auth_headers, case_id)
    _run_and_score(
        client, a, line="an argument that must never become retrievable", weakness="w", score=50
    )
    after = db_session.scalar(select(func.count()).select_from(CaseChunk))
    # Transcripts live in the `transcripts` table for history only — never embedded into
    # case_chunks, so a later rehearsal's retrieval can't surface a prior rehearsal's argument.
    assert after == before


def test_scorecards_are_per_session_not_aggregated(client, auth_headers):
    case_id = _make_case(client, auth_headers, facts="Facts.")
    a = _new_session(client, auth_headers, case_id)
    _run_and_score(client, a, line="arg a", weakness="wa", score=30)
    b = _new_session(client, auth_headers, case_id)
    _run_and_score(client, b, line="arg b", weakness="wb", score=90)

    sa = client.get(f"/api/sessions/{a}/scorecard", headers=auth_headers).json()
    sb = client.get(f"/api/sessions/{b}/scorecard", headers=auth_headers).json()
    # Each rehearsal keeps its own score/weaknesses — no averaging or carryover across the case.
    assert sa["overall_score"] == 30
    assert sb["overall_score"] == 90
    assert sa["weaknesses"] == "wa"
    assert sb["weaknesses"] == "wb"
