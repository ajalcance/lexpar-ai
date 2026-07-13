"""
File: app/schemas/limits.py
Purpose: Shared form-field length caps — one source of truth for the Pydantic `max_length` on
    request schemas. These bound what a user can submit into fields that flow into LLM prompts (the
    case profile → agent context) and the DB, so no single field can bloat a prompt (cost/DoS) or
    the record. Mirror of frontend `src/lib/limits.ts` — keep the two in sync.
Depends on: nothing
Related: app/schemas/{case,court,auth}.py, app/api/courts.py (Form metadata), frontend lib/limits.ts
"""

# Single-line identifier fields (titles, party names, case numbers, citations, person/firm names).
LINE_MAX = 200

# Multi-line free-text answers (relief sought, additional case context, a jurisdiction blurb).
TEXT_MAX = 1000
