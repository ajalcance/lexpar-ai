"""
File: agents/tests/test_audio_tags.py
Purpose: Tests for strip_audio_tags (Track B) — the guarantee that v3 audio-tag delivery cues never
    leak into the persisted/displayed ruling: known AND invented tags are removed, while
    citation-shaped text is preserved exactly. The clean output is what the scorecard/transcript and
    citation_check see.
Depends on: pytest, audio_tags
"""

from audio_tags import AUDIO_TAG_ALLOWLIST, strip_audio_tags


def test_strips_known_allowlist_tags():
    assert (
        strip_audio_tags("The court [solemnly] finds for the plaintiff.")
        == "The court finds for the plaintiff."
    )
    assert strip_audio_tags("[pauses] So ordered.") == "So ordered."
    assert strip_audio_tags("Sustained. [sighs]") == "Sustained."


def test_strips_invented_offlist_tags_so_none_can_leak():
    # A tag the model invents off the allowlist is still lowercase+short → removed, never persisted.
    assert strip_audio_tags("The court [grumbles] finds against.") == "The court finds against."


def test_preserves_citation_shaped_text_exactly():
    assert strip_audio_tags("Section 23 controls here.") == "Section 23 controls here."
    assert strip_audio_tags("R.A. No. 11232 applies.") == "R.A. No. 11232 applies."
    # a bracketed token with a capital/number is NOT a lowercase audio tag → left untouched
    assert strip_audio_tags("See [Section 23].") == "See [Section 23]."


def test_clean_prose_is_unchanged():
    clean = "The petitioner established good faith. The objection is overruled."
    assert strip_audio_tags(clean) == clean


def test_every_allowlisted_tag_is_stripped():
    for tag in AUDIO_TAG_ALLOWLIST:
        assert strip_audio_tags(f"A {tag} B") == "A B"
