"""
File: app/prompts/prompt_loader.py
Purpose: The backend's prompt loader — the twin of agents/prompts.py, kept SEPARATE (no shared
    import) so the backend and the agent worker stay independently deployable. Same convention: one
    prompt per .md file in this directory, read-once + process-lifetime cache, string.Template for
    any $variables. Today it serves only the pleading-summarizer system prompt (§12).
Depends on: pathlib, string.Template (stdlib only)
Related: app/services/case_knowledge_service.py, agents/prompts.py (the agent-side twin),
    docs/DEVELOPER_GUIDELINES.md §10
Safety notes: the summarizer's no-fabrication line ("Be faithful to the text — do not invent") is
    part of pleading_summary.md's immutable region; render() never takes constraint text as a param.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

_PROMPT_DIR = Path(__file__).parent
_cache: dict[str, str] = {}


def _read(name: str) -> str:
    """Read a prompt file once and cache it for the process lifetime (immutable during a run)."""
    cached = _cache.get(name)
    if cached is None:
        cached = (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
        _cache[name] = cached
    return cached


def render(name: str, /, **variables: str) -> str:
    """Return a prompt's text; with variables, substitute $name placeholders via string.Template
    (NOT str.format — leaves literal JSON braces untouched). Verbatim when called with no vars."""
    text = _read(name)
    if variables:
        text = Template(text).safe_substitute(**variables)
    return text
