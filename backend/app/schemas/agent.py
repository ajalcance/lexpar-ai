"""
File: app/schemas/agent.py
Purpose: Request shapes for the internal, agent-only session-write routes — the batch transcript
    and the scorecard the agents worker persists at session end.
Depends on: pydantic
Related: app/api/internal.py, app/services/agent_write_service.py, agents/scorecard_builder.py
Security notes: Carries transcript content (attorney work product) — accepted only from the agent
    service credential, never logged.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptTurnIn(BaseModel):
    speaker: str  # 'attorney' | 'opposing_counsel' | 'judge'
    content: str
    was_interruption: bool = False
    spoken_at: datetime | None = None


class CriterionIn(BaseModel):
    """One rubric dimension of the judge's performance breakdown (name + 0-100 sub-score)."""

    name: str
    score: float = Field(ge=0, le=100)


class ScorecardWriteIn(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    strengths: str
    weaknesses: str
    judge_ruling: str
    # Per-dimension rubric breakdown (command of the record, responsiveness, etc.). Additive and
    # optional: an older worker that omits it persists an empty breakdown, not an error.
    criteria: list[CriterionIn] = []
    transcript: list[TranscriptTurnIn] = []
    # Per-session LLM usage/canary counters (agents llm_metrics.snapshot()) → sessions.llm_usage
    # (migration 0008). Additive and optional, same contract as criteria. Counts only.
    llm_usage: dict = {}


class SessionContextOut(BaseModel):
    """The case context the agents worker loads at room join to seed its SessionState."""

    case_facts: str = ""
    case_title: str = ""
    case_summary: str = ""  # §12: the structured pleading digest, always in agent context
    court_id: str = ""  # §13: the case's forum ("" when none) — enables court-rules retrieval
    proceeding_type: str = ""  # §13: drives eligible objection grounds (classifier, Phase 4)
    # Case profile (user-stated ground truth, migration 0007): the record from second zero —
    # parties/number feed STT keyterms + the snapshot; represented_party fixes OC's side by
    # declaration; relief_sought anchors the matter and the judge's assessment. "" when unset.
    case_number: str = ""
    petitioner: str = ""
    respondent: str = ""
    represented_party: str = ""  # 'petitioner' | 'respondent' | ""
    relief_sought: str = ""


class KnowledgeOut(BaseModel):
    """Case-knowledge retrieval for the agents (§12): the summary + the query-relevant passages.
    `chunk_ids` parallels `passages` — which chunks were actually shown (§13 provenance)."""

    summary: str = ""
    passages: list[str] = []
    chunk_ids: list[str] = []


class CourtRulesOut(BaseModel):
    """Court-rules retrieval for the agents (§13): verbatim rule passages for the session's forum.
    A SIBLING shape to KnowledgeOut, not a `scope` param on it — the case shape carries a summary
    field that has no rules counterpart (no LLM digest of rules exists, by design), so overloading
    one route would force dead fields on both callers. `chunk_ids` parallels `passages`."""

    passages: list[str] = []
    chunk_ids: list[str] = []


class ProvenanceWriteIn(BaseModel):
    """§13 Phase 5: the audit trail for one ruling — which chunks the model was actually shown,
    and which citations in its output were NOT grounded in them (turn-scoped check)."""

    ruling_type: str  # 'objection_ruling' | 'final_ruling' (validated in the service)
    chunk_ids_used: list[str] = []
    citation_flags: list[str] = []
