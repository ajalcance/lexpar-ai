"""
File: tests/test_prompts.py
Purpose: Byte-identical "moved, not changed" check for the backend's migrated prompt (the pleading
    summarizer, §12) — asserts prompt_loader.render("pleading_summary") equals the exact
    pre-migration _SUMMARY_SYSTEM constant. Mirrors agents/tests/test_prompts.py.
Depends on: pytest, app.prompts.prompt_loader
"""

from app.prompts import prompt_loader

_SUMMARY_GOLDEN = (
    "You are a litigation analyst. Read the pleading excerpt and produce a tight structured brief "
    "the courtroom AI will keep in context. Cover, with short bullet lines: PARTIES; CLAIMS/CAUSES "
    "OF ACTION; KEY DATES; KEY FACTS ALLEGED; DISPUTED FACTS; STIPULATIONS/ADMISSIONS (if any). "
    "Be faithful to the text — do not invent. Plain text, no preamble."
)


def test_pleading_summary_prompt_is_byte_identical():
    assert prompt_loader.render("pleading_summary") == _SUMMARY_GOLDEN


def test_pleading_summary_retains_its_no_fabrication_constraint():
    # The immutable no-fabrication line must survive the move to a file.
    assert "do not invent" in prompt_loader.render("pleading_summary")
