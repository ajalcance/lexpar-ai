"""
File: agents/session_state.py
Purpose: Structured, in-memory memory of a single sparring session — the case facts, a ledger of
    facts established during the session, and a ledger of objections with their rulings. This is
    the ground truth the verification pass checks a drafted reply against (see verification.py),
    and what lets the agents reason about "what's on the record" instead of re-parsing the raw
    transcript each turn (ARCHITECTURE §6.5).
Depends on: dataclasses (stdlib only — no API keys)
Related: agents/verification.py, agents/opposing_counsel.py, agents/judge.py,
    backend/app/models/transcript.py (durable copy)
Security notes: Holds case facts and transcript-derived content (attorney work product). Keep it in
    memory for the session only; never log the raw ledger — persist through the backend models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_RULINGS = frozenset({"sustained", "overruled"})
_PENDING = "pending"


@dataclass
class Objection:
    """A single objection and its disposition."""

    grounds: str
    raised_by: str  # 'opposing_counsel' | 'attorney'
    ruling: str = _PENDING  # 'pending' | 'sustained' | 'overruled'

    @property
    def is_resolved(self) -> bool:
        return self.ruling != _PENDING


@dataclass
class SessionState:
    """In-memory memory for one session."""

    case_facts: str = ""
    established_facts: list[str] = field(default_factory=list)
    objections: list[Objection] = field(default_factory=list)

    def add_established_fact(self, fact: str) -> None:
        """Record a fact established during the session. Ignores blank/duplicate facts."""
        cleaned = fact.strip()
        if cleaned and cleaned not in self.established_facts:
            self.established_facts.append(cleaned)

    def record_objection(self, grounds: str, raised_by: str) -> Objection:
        """Log a newly raised objection (pending until the judge rules) and return it."""
        objection = Objection(grounds=grounds.strip(), raised_by=raised_by.strip())
        self.objections.append(objection)
        return objection

    def rule_on_objection(self, objection: Objection, ruling: str) -> Objection:
        """Apply the judge's ruling to an objection. Rejects unknown rulings and re-rulings."""
        if ruling not in VALID_RULINGS:
            allowed = sorted(VALID_RULINGS)
            raise ValueError(f"Unknown ruling: {ruling!r} (expected one of {allowed})")
        if objection not in self.objections:
            raise ValueError("Objection is not part of this session.")
        if objection.is_resolved:
            raise ValueError(f"Objection already ruled {objection.ruling!r}; cannot re-rule.")
        objection.ruling = ruling
        return objection

    def pending_objections(self) -> list[Objection]:
        return [o for o in self.objections if not o.is_resolved]

    def sustained_objections(self) -> list[Objection]:
        return [o for o in self.objections if o.ruling == "sustained"]

    def snapshot(self) -> str:
        """A compact text view of the state, suitable as verifier/prompt context."""
        lines = ["CASE FACTS:", self.case_facts or "(none)", "", "ESTABLISHED FACTS:"]
        lines += [f"- {fact}" for fact in self.established_facts] or ["(none)"]
        lines += ["", "OBJECTIONS:"]
        lines += [
            f"- [{o.ruling}] {o.grounds} (raised by {o.raised_by})" for o in self.objections
        ] or ["(none)"]
        return "\n".join(lines)
