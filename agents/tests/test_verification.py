"""
File: agents/tests/test_verification.py
Purpose: Offline tests for the citation heuristic (ARCHITECTURE §6.5) — clean sentences (real
    reporters, plausible years, or no citation) are not flagged; fabricated-looking ones (bogus
    reporter or implausible year) are. The consistency check's live behavior is in
    test_live_fireworks.py; its pure helpers are in test_verification_consistency.py.
Depends on: pytest, verification
"""

import pytest

from verification import find_suspicious_citations, has_suspicious_citation

CLEAN_SENTENCES = [
    "As the Court held in Marbury v. Madison, 5 U.S. 137 (1803), judicial review is settled.",
    "The Ninth Circuit addressed this in Miller v. Gammie, 335 F.3d 889 (9th Cir. 2003).",
    "Opposing counsel mischaracterizes the timeline of events entirely.",
    "The contract was signed on March 3 and payment followed 30 days later.",
]

FABRICATED_SENTENCES = [
    "As established in Hargrove v. Pinnacle, 892 F.9d 3421 (11th Cir. 2019), the rule applies.",
    "See Delgado v. Fenwick, 77 Cal. 9th 12 (2044), which is directly on point.",
    "The doctrine traces to Whitfield v. Carrington, 500 F.3d 100 (2099).",
]


@pytest.mark.parametrize("sentence", CLEAN_SENTENCES)
def test_clean_sentences_are_not_flagged(sentence):
    assert find_suspicious_citations(sentence) == []
    assert has_suspicious_citation(sentence) is False


@pytest.mark.parametrize("sentence", FABRICATED_SENTENCES)
def test_fabricated_sentences_are_flagged(sentence):
    assert has_suspicious_citation(sentence) is True


def test_unrecognized_reporter_is_the_reason():
    findings = find_suspicious_citations("See 892 F.9d 3421 (2019).")
    assert len(findings) == 1
    assert "unrecognized reporter" in findings[0].reason


def test_future_year_flagged_even_with_known_reporter():
    findings = find_suspicious_citations("See 500 F.3d 100 (2099).")
    assert len(findings) == 1
    assert "implausible year" in findings[0].reason
