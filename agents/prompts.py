"""
File: agents/prompts.py
Purpose: The single source + loader for every LLM prompt the agent worker sends (personas AND the
    sub-task system/instruction prompts that used to be scattered as inline Python constants across
    opposing_counsel.py / judge.py / objection_classifier.py / verification.py). One prompt per
    Markdown file under prompts/; this module reads, caches (process-lifetime), and — for the few
    prompts with variable slots — substitutes via string.Template.
Depends on: pathlib, string.Template (stdlib only — no templating dependency)
Related: agents/prompts/*.md (the text), agents/tests/test_prompts.py (byte-identical golden tests),
    docs/DEVELOPER_GUIDELINES.md §10, backend/app/prompts/prompt_loader.py (the backend twin)
Security / safety notes:
    - Template mechanism is string.Template ($name), NOT str.format — several prompts contain
      literal JSON braces ({"ruling": ...}) that str.format would choke on; $-placeholders leave
      {} untouched. A literal '$' in a templated prompt must be escaped as '$$'.
    - render() NEVER accepts constraint text as a parameter. The no-fabrication /
      never-invent-case-law constraint sections are part of each prompt file's immutable region
      (see DEVELOPER_GUIDELINES §10 + docs/LESSONS.md). A future user-customization layer may
      substitute only style/persona variables via **variables — it has no API surface here to touch
      a constraint. The real enforcement is still code-side (citation_check + fail-safe defaults).
"""

from __future__ import annotations

from pathlib import Path
from string import Template

_PROMPT_DIR = Path(__file__).parent / "prompts"

# Every prompt name → its .md file is <name>.md. Listed so warm_cache() can preload them all and a
# test can assert the registry and the directory stay in sync.
PROMPT_NAMES: tuple[str, ...] = (
    "opposing_counsel",              # OC persona (system)
    "judge",                         # Judge persona (system)
    "oc_reply_style",                # OC output-style instruction
    "oc_continuation",               # OC mid-stream repair (with an already-spoken prefix)
    "oc_continuation_restart",       # OC mid-stream repair (nothing spoken yet)
    "judge_ruling_instruction",      # generate_ruling JSON contract
    "judge_assessment",              # end-of-session assessment instruction
    "judge_assessment_expressive",   # ^ + v3 audio-tag authoring for the final ruling (Track B)
    "judge_quick_ruling",            # inline sustained/overruled system prompt
    "objection_classifier_system",   # tier-3 classifier system prompt ($eligible)
    "consistency_verifier",          # pre-TTS consistency verifier system prompt
)

_cache: dict[str, str] = {}


def _read(name: str) -> str:
    """Read a prompt file once and cache it for the process lifetime. Prompt files are immutable
    during a run, so there is nothing to invalidate — a deploy restarts the process and re-reads."""
    cached = _cache.get(name)
    if cached is None:
        cached = (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
        _cache[name] = cached
    return cached


def render(name: str, /, **variables: str) -> str:
    """Return a prompt's text. With no variables the file is returned verbatim (so literal JSON
    braces are safe); with variables, $name placeholders are substituted via string.Template."""
    text = _read(name)
    if variables:
        text = Template(text).safe_substitute(**variables)
    return text


def warm_cache() -> None:
    """Preload every prompt (called once at worker startup) so no live-path call ever does file I/O
    mid-session — the read cost is paid up front, not inside the voice loop."""
    for name in PROMPT_NAMES:
        _read(name)
