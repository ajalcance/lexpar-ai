"""
File: agents/verification.py
Purpose: The pre-TTS verification pass (ARCHITECTURE §6.5). Two checks:
    (a) consistency of a drafted reply against SessionState — a small, fast Fireworks model
        (via llm_router.verification_config) returns any contradictions with the session record;
    (b) fabricated legal citations — a regex heuristic that flags citation-shaped text using an
        unrecognized reporter abbreviation or an implausible year. The heuristic is deliberately
        conservative: it catches obviously invented citations without a legal database.
    The citation heuristic is offline; the consistency check makes a live API call.
Depends on: json, re, datetime (stdlib); agents/session_state.py, agents/llm_router.py
Related: agents/opposing_counsel.py, agents/judge.py, docs/ARCHITECTURE.md §6.5
Security notes: Operates on reply text (attorney work product). Return findings by reference to the
    matched span; never log the full reply or send it anywhere but the configured verifier endpoint.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import prompts
from llm_router import build_endpoint, chat, verification_config
from session_state import SessionState

# Earliest plausible U.S. case-law year (Judiciary Act era). Anything before this, or in the
# future, is treated as a fabrication signal.
MIN_PLAUSIBLE_YEAR = 1789

# Common U.S. case reporters, normalized to single spaces. Not exhaustive — the goal is to catch
# citations to reporters that plainly do not exist, not to validate every real one.
KNOWN_REPORTERS = frozenset(
    {
        "U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d",
        "F.", "F.2d", "F.3d", "F.4th", "F. Supp.", "F. Supp. 2d", "F. Supp. 3d", "F.R.D.",
        "Cal.", "Cal. 2d", "Cal. 3d", "Cal. 4th", "Cal. 5th",
        "Cal. App.", "Cal. App. 2d", "Cal. App. 3d", "Cal. App. 4th", "Cal. App. 5th",
        "Cal. Rptr.", "Cal. Rptr. 2d", "Cal. Rptr. 3d",
        "N.E.", "N.E.2d", "N.E.3d", "N.W.", "N.W.2d", "N.W.3d",
        "S.E.", "S.E.2d", "S.W.", "S.W.2d", "S.W.3d",
        "So.", "So. 2d", "So. 3d", "P.", "P.2d", "P.3d",
        "A.", "A.2d", "A.3d", "N.Y.", "N.Y.2d", "N.Y.3d", "N.Y.S.", "N.Y.S.2d",
    }
)

# A reporter token: a capitalized abbreviation (letters/dots/digits, e.g. "U.S.", "F.3d") or an
# ordinal series token (e.g. "2d", "3d", "4th").
_REPORTER_TOKEN = r"(?:[A-Z][A-Za-z0-9.]*|\d(?:st|nd|rd|th|d))"

# "<volume> <reporter> <page>" with an optional trailing "(... year)".
_CITATION_RE = re.compile(
    r"\b(?P<vol>\d{1,4})\s+"
    r"(?P<rep>" + _REPORTER_TOKEN + r"(?:\s+" + _REPORTER_TOKEN + r"){0,3})\s+"
    r"(?P<page>\d{1,4})"
    r"(?:\s*\((?P<paren>[^)]*)\))?"
)


@dataclass
class CitationFinding:
    """A citation-shaped span that looks fabricated, with the reason(s) it was flagged."""

    citation: str
    reason: str


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def find_suspicious_citations(text: str) -> list[CitationFinding]:
    """Return findings for citation-shaped spans with an unknown reporter or implausible year."""
    findings: list[CitationFinding] = []
    for match in _CITATION_RE.finditer(text):
        reasons: list[str] = []

        reporter = re.sub(r"\s+", " ", match.group("rep")).strip()
        if reporter not in KNOWN_REPORTERS:
            reasons.append(f"unrecognized reporter {reporter!r}")

        paren = match.group("paren") or ""
        year_match = re.search(r"\b(\d{4})\b", paren)
        if year_match:
            year = int(year_match.group(1))
            if year < MIN_PLAUSIBLE_YEAR or year > _current_year():
                reasons.append(f"implausible year {year}")

        if reasons:
            findings.append(
                CitationFinding(citation=match.group(0).strip(), reason="; ".join(reasons))
            )
    return findings


def has_suspicious_citation(text: str) -> bool:
    """True if any citation-shaped span in `text` looks fabricated."""
    return bool(find_suspicious_citations(text))


def _build_consistency_messages(reply: str, state: SessionState) -> list[dict[str, str]]:
    """Build the (system, user) messages for the consistency verifier. Pure — no API call."""
    user = f"SESSION RECORD:\n{state.snapshot()}\n\nDRAFT REPLY:\n{reply}"
    return [
        {"role": "system", "content": prompts.render("consistency_verifier")},
        {"role": "user", "content": user},
    ]


def _parse_consistency(content: str) -> list[str]:
    """Extract the contradictions list from the verifier's JSON reply. Pure — no API call."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("verifier did not return a JSON object")
    data = json.loads(content[start : end + 1])
    contradictions = data.get("contradictions", [])
    if not isinstance(contradictions, list):
        raise ValueError("verifier 'contradictions' field is not a list")
    return [str(item) for item in contradictions]


def check_consistency(reply: str, state: SessionState) -> list[str]:
    """
    Check that `reply` does not contradict `state` (case facts, established facts, sustained
    objection rulings) using the small verification model. Returns a list of contradiction
    descriptions — empty means consistent. Fails closed: if the verifier output can't be parsed,
    returns a non-empty result so the caller regenerates rather than trusting an unverified draft.
    """
    endpoint = build_endpoint(verification_config())
    messages = _build_consistency_messages(reply, state)
    content = chat(
        endpoint,
        messages,
        temperature=0.0,
        # gpt-oss reasons before emitting (docs/LESSONS.md): the SESSION RECORD this checks
        # against grew with the CASE PROFILE + MATTER blocks, and a live session showed repeated
        # fail-closed "no verified sentences" silences — a truncated/empty verifier response
        # parses as a contradiction and silences a fine reply. 512 -> 1024; ceiling, not floor.
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    try:
        return _parse_consistency(content)
    except (ValueError, json.JSONDecodeError):
        return ["verification failed: verifier response could not be parsed"]
