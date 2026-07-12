"""
File: agents/case_posture.py
Purpose: Derive "the matter before the court" once at session start — a neutral one/two-line framing
    of what the session decides and the competing positions, from the case materials (§12 pleading
    summary + raw facts + proceeding type). This is the shared frame both Opposing Counsel and the
    Judge reason against (SessionState.matter → snapshot()), so OC opposes the attorney's position
    on a stable, case-grounded matter instead of inventing a side on a thin opening, and the judge
    rules the real matter. Runs on the FAST model (same latency philosophy as the classifier). Pure
    builder + parse; only derive_matter makes an API call.
Depends on: agents/prompts.py, agents/llm_router.py, agents/session_state.py
Related: agents/main.py (calls derive_matter at room join, flag-gated), agents/session_state.py
Security notes: Feeds case facts/summary (attorney work product) to the model; never logged, sent
    only to the configured endpoint.
"""

from __future__ import annotations

import json
import logging

import prompts
from llm_router import build_endpoint, chat, objection_config
from session_state import SessionState

logger = logging.getLogger("lexpar.agents.posture")

# gpt-oss reasons before emitting; give headroom so the hidden reasoning doesn't eat the content
# (docs/LESSONS.md empty-content bug). A ceiling — a simple framing stops well short.
_MATTER_MAX_TOKENS = 1024


def build_matter_messages(state: SessionState) -> list[dict[str, str]]:
    """Assemble the derivation messages: the framing instruction + the case materials. Pure."""
    summary = state.case_summary.strip() or "(no pleading summary)"
    facts = state.case_facts.strip() or "(none provided)"
    proceeding = state.proceeding_type or "unspecified"
    context = (
        f"PROCEEDING TYPE: {proceeding}\n\n"
        f"CASE SUMMARY (from the pleading):\n{summary}\n\n"
        f"CASE FACTS:\n{facts}"
    )
    return [
        {"role": "system", "content": prompts.render("derive_matter")},
        {"role": "user", "content": context},
    ]


def parse_matter(content: str) -> str:
    """Pull the framed matter out of the model's JSON. Fail-safe: returns "" on non-JSON / missing
    field / blank, so the caller degrades to no explicit matter (never a fabricated/partial one)."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return ""
    try:
        data = json.loads(content[start : end + 1])
    except (ValueError, TypeError):
        return ""
    matter = data.get("matter", "") if isinstance(data, dict) else ""
    return str(matter).strip()


def derive_matter(state: SessionState) -> str:
    """Derive the matter before the court from the case materials (one FAST-model call). Returns ""
    on empty inputs or any error/unparseable output — best-effort; the session then proceeds with no
    explicit matter (OC + judge reason from the case summary + exchange, as before)."""
    if not (state.case_summary.strip() or state.case_facts.strip()):
        return ""  # nothing to frame a matter from
    try:
        endpoint = build_endpoint(objection_config())
        content = chat(
            endpoint,
            build_matter_messages(state),
            temperature=0.0,
            max_tokens=_MATTER_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        return parse_matter(content)
    except Exception:
        logger.warning(
            "could not derive the matter before the court [session=%s]", state.session_id
        )
        return ""
