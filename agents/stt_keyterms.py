"""
File: agents/stt_keyterms.py
Purpose: Case-aware STT vocabulary — extract the proper nouns / domain terms of THIS case (party
    names, entities, place names) from the case title, facts, and pleading summary, and feed them to
    Deepgram nova-3 as `keyterm` boosts. A live session showed STT mangling exactly these ("TCT" →
    "VLT", "SARC" → "SIRC", "Tacloban" → "Takloban"); OC and the objection classifier then argued
    faithfully from the misheard words — indistinguishable from hallucination in the transcript.
    Deterministic (no LLM, no hardcoded vocabulary): capitalized/uppercase alphabetic tokens,
    first-seen order, deduped, capped. Pure; wiring lives in main.py (flag STT_KEYTERMS).
Depends on: stdlib only
Related: agents/main.py (deepgram.STT keyterm=…), docs/LESSONS.md
Security notes: Terms derive from case materials (work product) — passed to the STT provider the
    audio already goes to; never logged.
"""

from __future__ import annotations

import re

# A token worth boosting: alphabetic (allowing internal hyphens), 3+ chars, starts uppercase.
# 3 (not 4) so short acronyms like "TCT"/"SARC" — the terms STT actually mangles — qualify.
_TOKEN = re.compile(r"\b[A-Z][A-Za-z-]{2,}\b")

# Common caption/legalese words that are capitalized in pleadings but are not case vocabulary.
_BOILERPLATE = frozenset(
    w.casefold()
    for w in (
        "The", "And", "For", "Versus", "Petitioner", "Respondent", "Plaintiff", "Defendant",
        "Appellant", "Appellee", "Company", "Corporation", "Incorporated", "Represented",
        "Branch", "Court", "Regional", "Trial", "Supreme", "Honorable", "March", "January",
        "February", "April", "June", "July", "August", "September", "October", "November",
        "December",
    )
)

MAX_KEYTERMS = 12


def extract_keyterms(*sources: str, cap: int = MAX_KEYTERMS) -> list[str]:
    """Distinct case-specific terms across the given texts, first-seen order, case-insensitively
    deduped, boilerplate dropped, capped. Empty sources → [] (the STT runs unboosted, as before)."""
    seen: set[str] = set()
    terms: list[str] = []
    for source in sources:
        if not source:
            continue
        for match in _TOKEN.finditer(source):
            token = match.group(0)
            key = token.casefold()
            if key in seen or key in _BOILERPLATE:
                continue
            seen.add(key)
            terms.append(token)
            if len(terms) >= cap:
                return terms
    return terms
