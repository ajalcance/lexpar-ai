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

# Lowercase case-vocabulary: 4+ char alphabetic tokens. Terms like "ultra vires", "mortgage",
# "foreclosure" are lowercase in pleadings, so the capitalized pass misses them ("ultra vires" was
# heard as "ultra bar" live). They qualify by RECURRENCE in the materials (≥ _MIN_LOWER_COUNT),
# which keeps this case-derived — no legal lexicon.
_LOWER_TOKEN = re.compile(r"\b[a-z][a-z-]{3,}\b")
_MIN_LOWER_COUNT = 2

# Generic English function words — recurrence alone would qualify them, and they are never case
# vocabulary. Deliberately function-words-only (no legal terms — those are exactly what we want).
_FUNCTION_WORDS = frozenset(
    (
        "that", "this", "with", "from", "have", "been", "were", "which", "their", "there",
        "would", "shall", "should", "could", "upon", "under", "over", "into", "such", "other",
        "others", "before", "after", "against", "between", "because", "where", "when", "while",
        "these", "those", "than", "then", "them", "they", "will", "does", "having", "being",
        "also", "only", "same", "each", "further", "herein", "thereof", "hereby", "whereas",
    )
)

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
    """Distinct case-specific terms across the given texts: capitalized entities first (first-seen
    order), then recurring lowercase case-vocabulary (frequency order) into the remaining slots.
    Case-insensitively deduped, boilerplate/function words dropped, capped. Empty sources → []
    (the STT runs unboosted, as before)."""
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
    # Remaining slots: recurring lowercase vocabulary ("ultra vires", "mortgage", "foreclosure").
    counts: dict[str, int] = {}
    order: dict[str, int] = {}
    for source in sources:
        if not source:
            continue
        for match in _LOWER_TOKEN.finditer(source):
            token = match.group(0)
            if token in _FUNCTION_WORDS or token in seen:
                continue
            counts[token] = counts.get(token, 0) + 1
            order.setdefault(token, len(order))
    recurring = sorted(
        (token for token, count in counts.items() if count >= _MIN_LOWER_COUNT),
        key=lambda token: (-counts[token], order[token]),
    )
    for token in recurring:
        if len(terms) >= cap:
            break
        seen.add(token)
        terms.append(token)
    return terms
