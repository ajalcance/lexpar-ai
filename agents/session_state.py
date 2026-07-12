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
from datetime import datetime, timezone

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
class TranscriptTurn:
    """One spoken turn accumulated during the session (for the batch write at session end)."""

    speaker: str  # 'attorney' | 'opposing_counsel' | 'judge'
    content: str
    was_interruption: bool = False
    spoken_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    """In-memory memory for one session."""

    case_facts: str = ""
    # Structured digest of the uploaded pleading (§12), loaded at room join and kept in every
    # prompt via snapshot() — this is what lets Opposing Counsel object and the Judge rule with the
    # real case, not a few sentences. Retrieved pleading passages are added per-reply on top.
    case_summary: str = ""
    # The matter before the court: a neutral one/two-line framing of what THIS session decides and
    # the competing positions on it, derived once at room join from the case (case_posture.py), the
    # way a court knows the motion before argument. Shared by BOTH agents via snapshot() so OC
    # opposes the attorney's position on a stable, case-grounded frame (never an invented side) and
    # the judge rules against the real matter. Empty when derivation is off/failed or no case exists
    # — everything then degrades to reasoning from the case summary + exchange as before.
    matter: str = ""
    # §13 plumbing (loaded from the session-context route at room join; NOT snapshot() content):
    # session_id lets any consumer holding the state retrieve pleading/court-rule passages without
    # signature churn; court_id/proceeding_type gate whether/which retrieval and objection grounds
    # apply. All default "" — offline harnesses/tests skip retrieval entirely.
    session_id: str = ""
    court_id: str = ""
    proceeding_type: str = ""
    established_facts: list[str] = field(default_factory=list)
    objections: list[Objection] = field(default_factory=list)
    transcript: list[TranscriptTurn] = field(default_factory=list)

    def add_established_fact(self, fact: str) -> None:
        """Record a fact established during the session. Ignores blank/duplicate facts."""
        cleaned = fact.strip()
        if cleaned and cleaned not in self.established_facts:
            self.established_facts.append(cleaned)

    def add_turn(
        self,
        speaker: str,
        content: str,
        was_interruption: bool = False,
        spoken_at: datetime | None = None,
    ) -> TranscriptTurn:
        """Append a spoken turn to the running transcript."""
        turn = TranscriptTurn(
            speaker=speaker,
            content=content,
            was_interruption=was_interruption,
            spoken_at=spoken_at or datetime.now(timezone.utc),
        )
        self.transcript.append(turn)
        return turn

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
        lines: list[str] = []
        if self.matter:
            lines += ["MATTER BEFORE THE COURT:", self.matter, ""]
        if self.case_summary:
            lines += ["CASE SUMMARY (from the pleading):", self.case_summary, ""]
        lines += ["CASE FACTS:", self.case_facts or "(none)", "", "ESTABLISHED FACTS:"]
        lines += [f"- {fact}" for fact in self.established_facts] or ["(none)"]
        lines += ["", "OBJECTIONS:"]
        lines += [
            f"- [{o.ruling}] {o.grounds} (raised by {o.raised_by})" for o in self.objections
        ] or ["(none)"]
        return "\n".join(lines)

    def recent_exchange(self, max_turns: int = 10, max_chars: int = 2000) -> str:
        """The live back-and-forth: the last `max_turns` transcript turns, speaker-labelled,
        oldest first, capped at `max_chars` (oldest lines dropped first). This is the
        CONVERSATION memory the per-turn prompts carry — snapshot() deliberately holds only the
        durable record (facts + ledger), so without this block Opposing Counsel and the inline
        judge are rebuilt amnesiac every turn (a live pass showed OC repeating the same sentence
        across turns because it could not see its own prior replies)."""
        labels = {"attorney": "ATTORNEY", "opposing_counsel": "OPPOSING COUNSEL", "judge": "JUDGE"}
        lines = [
            f"{labels.get(t.speaker, t.speaker.upper())}: {t.content}"
            for t in self.transcript[-max_turns:]
        ]
        text = "\n".join(lines)
        while len(text) > max_chars and "\n" in text:
            text = text.split("\n", 1)[1]  # drop the oldest line; a single oversize line stays
        return text
