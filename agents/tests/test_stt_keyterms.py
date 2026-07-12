"""
File: agents/tests/test_stt_keyterms.py
Purpose: Offline tests for the case-aware STT vocabulary extraction (stt_keyterms.py) — party
    names / entities pulled from real caption-style case materials, acronyms kept (the terms STT
    actually mangles), caption boilerplate dropped, case-insensitive dedupe, cap, empty fail-open.
Depends on: pytest, stt_keyterms
"""

from __future__ import annotations

from stt_keyterms import MAX_KEYTERMS, extract_keyterms


def test_extracts_party_names_from_a_caption():
    facts = (
        "METROPOLITAN BANK & TRUST COMPANY (METROBANK), PETITIONER, VS. SALAZAR REALTY "
        "CORPORATION REPRESENTED BY INCORPORATORS/STOCKHOLDERS RAMON ANG SALAZAR, JR."
    )
    terms = extract_keyterms("G.R. No. 218738, March 09, 2022", facts)
    assert "METROPOLITAN" in terms
    assert "METROBANK" in terms
    assert "SALAZAR" in terms
    # Caption boilerplate is not case vocabulary.
    assert "PETITIONER" not in terms
    assert "COMPANY" not in terms
    assert "March" not in terms


def test_short_acronyms_kept():
    # The terms STT actually mangled live ("TCT" → "VLT", "SARC" → "SIRC").
    terms = extract_keyterms("SARC pledged its TCT over the Tacloban property.")
    assert "SARC" in terms
    assert "TCT" in terms
    assert "Tacloban" in terms


def test_dedupes_case_insensitively_preserving_first_seen():
    terms = extract_keyterms("METROBANK argued.", "Metrobank replied about METROBANK.")
    assert terms.count("METROBANK") == 1
    assert "Metrobank" not in terms  # deduped against the first-seen casing


def test_cap_and_empty_inputs():
    many = " ".join(f"Entity{chr(ord('A') + i)}x" for i in range(26))
    assert len(extract_keyterms(many)) == MAX_KEYTERMS
    assert extract_keyterms("", "") == []
    assert extract_keyterms("all lowercase words only here") == []
