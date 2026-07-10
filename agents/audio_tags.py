"""
File: agents/audio_tags.py
Purpose: ElevenLabs v3 "audio tags" ([solemnly], [pauses], …) are spoken-delivery cues authored
    into the Judge's FINAL ruling for expressive TTS (Track B). They must never leak into the
    written scorecard/transcript, so this module strips them to produce the clean, persisted/
    displayed text — the source of truth — while the tagged text is used ONLY as the v3 TTS input.
    Pure + livekit-free so the strip is unit-tested.
Depends on: re (stdlib only)
Related: agents/judge.py (assess_session returns clean ruling + tagged closing_ruling_spoken),
    agents/prompts/judge_assessment_expressive.md (authors the tags), docs/LESSONS.md
Security notes: Delivery direction only — not factual content. The clean (stripped) text is what
    citation_check.flag_ungrounded runs on, so tags never reach the grounding check either.
"""

from __future__ import annotations

import re

# The courtroom-appropriate tags the Judge's expressive prompt is allowed to author. The strip
# below is deliberately BROADER than this list (see _TAG_RE) so a tag the model invents off-list
# is still removed and can never leak into the written ruling.
AUDIO_TAG_ALLOWLIST: tuple[str, ...] = (
    "[pauses]",
    "[solemnly]",
    "[sighs]",
    "[clears throat]",
    "[sternly]",
)

# A bracketed token of lowercase words + spaces only, short — matches audio tags ([sighs],
# [clears throat]) AND any lowercase tag the model invents ([grumbles]); does NOT match citations
# (`Section 23`, `R.A. No. 11232` have no brackets) or bracketed tokens with capitals/digits
# (`[Section 23]`), which are left untouched.
_TAG_RE = re.compile(r"\[[a-z][a-z ]{0,20}\]")


def strip_audio_tags(text: str) -> str:
    """Remove v3 audio-tag tokens and tidy the whitespace/punctuation they leave behind, so the
    result reads as clean prose identical in wording to what was authored, minus the cues."""
    out = _TAG_RE.sub("", text)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)  # a removed tag before punctuation → no space
    out = re.sub(r"[ \t]{2,}", " ", out)  # collapse the doubled spaces a removed inline tag leaves
    return out.strip()
