"""
File: agents/tests/test_citation_check.py
Purpose: Offline tests for the §13 Phase 5 citation grounding check — extraction of citation-
    shaped tokens, canonical equivalence across surface variants, and the TURN-SCOPED flagging
    rule (a citation not present in this turn's shown chunks flags, even if plausible).
Depends on: pytest, citation_check
Security notes: All fixture text is synthetic placeholder prose — citation LABELS only, no rule
    content (§13 no-fabrication constraint applies to tests too).
"""

from citation_check import canonical, extract_citations, flag_ungrounded


def test_extracts_all_surface_forms():
    text = (
        "Under Section 23 and Sec. 5, per Rule 8, citing R.A. No. 11232, "
        "also A.M. No. 01-2-04-SC, and § 73."
    )
    found = extract_citations(text)
    keys = {canonical(c) for c in found}
    assert keys == {"sec 23", "sec 5", "rule 8", "ra 11232", "am 01-2-04-sc", "sec 73"}


def test_canonical_equivalence_across_variants():
    assert canonical("Section 12") == canonical("SEC. 12") == canonical("§12")
    assert canonical("R.A. No. 11232") == canonical("RA 11232")
    assert canonical("Republic Act No. 11232") == canonical("ra 11232")
    assert canonical("A.M. No. 01-2-04-SC") == canonical("AM 01-2-04-SC")
    # different identifiers stay distinct
    assert canonical("Section 12") != canonical("Section 13")
    assert canonical("Rule 8") != canonical("Section 8")


def test_extraction_dedupes_and_ignores_plain_text():
    assert extract_citations("Section 9 twice: section 9.") == ["Section 9"]
    assert extract_citations("No citations in this placeholder sentence.") == []
    assert extract_citations("") == []


def test_flags_citation_not_in_shown_chunks():
    shown = "RELEVANT PROCEDURAL RULES:\n- [Section 12] Placeholder rule text (not real)."
    output = "Sustained under Section 12; see also Rule 99."
    assert flag_ungrounded(output, shown) == ["Rule 99"]  # Section 12 was shown; Rule 99 was not


def test_turn_scoping_flags_unretrieved_but_real_citations():
    # The distinction that matters: "Section 40" may exist in the corpus, but if it was not in
    # THIS turn's retrieved blocks, it still flags — the model asserted it without having seen it.
    shown_this_turn = "- [Section 12] Placeholder rule text (not real)."
    assert flag_ungrounded("As Section 40 provides…", shown_this_turn) == ["Section 40"]


def test_variant_match_does_not_false_flag():
    # model says "Section 12", the chunk heading reads "SEC. 12" — same citation, no flag
    shown = "- [SEC. 12] Placeholder body."
    assert flag_ungrounded("Overruled per Section 12.", shown) == []


def test_no_citations_no_flags():
    assert flag_ungrounded("Sustained. Move along, counsel.", "any shown text") == []
