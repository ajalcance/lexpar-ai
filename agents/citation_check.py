"""
File: agents/citation_check.py
Purpose: Citation grounding check (ARCHITECTURE §13 Phase 5). Extracts citation-shaped tokens
    (Section/Sec./Rule/R.A. No./A.M. No./§) from model output and flags any citation that is NOT
    present in the retrieved chunk text actually included in THAT turn's prompt. The comparison is
    deliberately TURN-SCOPED: a citation that exists somewhere in the corpus but was not retrieved
    and shown to the model for this turn still flags — the point is catching what the model
    asserted without having seen it, not what is true in the abstract. Flags are surfaced (logged
    + persisted as provenance), never silently rewritten out of the spoken output.
Depends on: re (stdlib only — pure, no network)
Related: agents/judge.py (quick_ruling / assess_session), agents/opposing_counsel.py
    (stream_reply), backend/app/models/ruling_provenance.py, docs/ARCHITECTURE.md §13
Security notes: Operates on citation labels (e.g. "Section 23"), which are not work product;
    callers may log the citation labels but never the surrounding output text.
"""

from __future__ import annotations

import re

# Citation-shaped surface forms. Deliberately citation-LABEL patterns (instrument + number), not
# rule content. Order matters only for readability; extraction dedupes on canonical form.
_CITATION_PATTERNS = [
    r"\bSection\s+\d+[A-Za-z0-9\-\.]*",
    r"\bSec\.\s*\d+[A-Za-z0-9\-\.]*",
    r"\bRule\s+\d+[A-Za-z0-9\-\.]*",
    r"\bR\.?\s?A\.?\s*No\.?\s*\d+[A-Za-z0-9\-]*",
    r"\bRepublic\s+Act\s+No\.?\s*\d+[A-Za-z0-9\-]*",
    r"\bA\.?\s?M\.?\s*No\.?\s*[0-9][0-9A-Za-z\-\.]*",
    r"§\s*\d+[A-Za-z0-9\-\.]*",
]
_CITATION_RE = re.compile("|".join(f"(?:{p})" for p in _CITATION_PATTERNS), re.IGNORECASE)

# Canonical instrument prefixes: variants of the same reference must compare equal —
# "Section 23" == "SEC. 23" == "§23"; "R.A. No. 11232" == "RA 11232" == "Republic Act No. 11232".
_PREFIX_CANON = [
    (re.compile(r"^(?:section|sec\.?|§)\s*", re.IGNORECASE), "sec "),
    (re.compile(r"^rule\s*", re.IGNORECASE), "rule "),
    (re.compile(r"^(?:republic\s+act|r\.?\s?a\.?)\s*(?:no\.?)?\s*", re.IGNORECASE), "ra "),
    (re.compile(r"^a\.?\s?m\.?\s*(?:no\.?)?\s*", re.IGNORECASE), "am "),
]


def canonical(citation: str) -> str:
    """Normalize a citation to a comparable key (instrument prefix + identifier). Pure."""
    text = citation.strip()
    for pattern, prefix in _PREFIX_CANON:
        if pattern.match(text):
            rest = pattern.sub("", text, count=1)
            # keep the identifier's own hyphens/letters (A.M. numbers), drop dots/whitespace
            ident = re.sub(r"[\s\.]+", "", rest).lower().rstrip(",;:")
            return f"{prefix}{ident}"
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_citations(text: str) -> list[str]:
    """Citation-shaped tokens in `text`, order-preserved, deduped on canonical form. Pure."""
    seen: set[str] = set()
    found: list[str] = []
    for match in _CITATION_RE.finditer(text or ""):
        token = match.group(0).strip().rstrip(".,;:")
        key = canonical(token)
        if key not in seen:
            seen.add(key)
            found.append(token)
    return found


def flag_ungrounded(output_text: str, shown_text: str) -> list[str]:
    """The citations in `output_text` whose canonical form does NOT appear in `shown_text` —
    where `shown_text` must be exactly the retrieved chunk text included in THIS turn's prompt
    (pleading excerpts + procedural rules blocks), not the corpus at large. Pure."""
    shown_keys = {canonical(c) for c in extract_citations(shown_text)}
    return [c for c in extract_citations(output_text) if canonical(c) not in shown_keys]
