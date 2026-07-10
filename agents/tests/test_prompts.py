"""
File: agents/tests/test_prompts.py
Purpose: The load-bearing "moved, not changed" verification for the prompt-storage migration
    (DEVELOPER_GUIDELINES §10). Each migrated prompt is asserted BYTE-IDENTICAL to a frozen golden
    string — the exact pre-migration inline-constant value. If a prompt file drifts by a single
    byte, this fails, so the structural migration cannot silently change what any model is sent.
    Also checks the registry↔directory stay in sync, warm_cache works, and $-templating (not
    str.format) leaves literal JSON braces intact.
Depends on: pytest, prompts
"""

import prompts

# --- frozen goldens: the EXACT pre-migration text (see git history of the removed constants) -----

# Static prompts — returned verbatim (no substitution).
STATIC_GOLDENS = {
    "oc_reply_style": (
        "Respond as opposing counsel in a few spoken sentences. Output only the words you say "
        "aloud in the courtroom — no analysis, headings, quotation marks, or preamble."
    ),
    "judge_ruling_instruction": (
        "If you cite a rule, name only a section heading that appears in RELEVANT PROCEDURAL "
        "RULES; otherwise rule without naming a specific citation. "
        'Respond ONLY with JSON: {"ruling": "<what you say aloud from the bench>"}.'
    ),
    "judge_assessment": (
        "Review the full session below. Then, as the presiding judge:\n"
        "1. For EACH objection still marked [pending] in the SESSION RECORD, in the order listed, "
        "rule 'sustained' or 'overruled' based on what the transcript shows. Objections already "
        "marked [sustained] or [overruled] were ruled from the bench DURING the session — do NOT "
        "re-rule them; treat those rulings as final.\n"
        "2. List 2-5 key facts the attorney genuinely established on the record (supported by the "
        "transcript and not undercut by a sustained objection). Return an empty array if none.\n"
        "3. Give a one- to two-sentence closing ruling from the bench that reflects the session as "
        "a whole, including a brief acknowledgment of the objections already ruled during the "
        "session. If you cite a rule, name only a section heading that appears in RELEVANT "
        "PROCEDURAL RULES; otherwise rule without naming a specific citation.\n"
        'Respond ONLY with JSON: {"rulings": ["sustained"|"overruled", ...], "established_facts": '
        '["<fact>", ...], "closing_ruling": "<what you say aloud>"}. The rulings array must have '
        "exactly one entry per [pending] objection, in the same order (empty array if none are "
        "pending)."
    ),
    "judge_quick_ruling": (
        "You are the presiding judge in a courtroom rehearsal. Opposing Counsel just objected to "
        "the attorney's in-progress statement. Rule IMMEDIATELY, as from the bench: sustained or "
        "overruled, with one short reason (a few words, spoken aloud). If you cite a rule, name "
        "only a section heading that appears in RELEVANT PROCEDURAL RULES; otherwise rule without "
        'naming a specific citation. Respond ONLY with JSON: {"ruling": "sustained"|"overruled", '
        '"reason": "<a few words>"}.'
    ),
    "consistency_verifier": (
        "You are a verification model in a courtroom rehearsal system. You check a DRAFT REPLY "
        "only for factual consistency with the SESSION RECORD — not style, tone, or "
        "persuasiveness. Flag any statement in the draft that contradicts the case facts, an "
        "established fact, or a sustained objection ruling. Respond ONLY with JSON: "
        '{"consistent": boolean, "contradictions": [string, ...]}. If nothing in the draft '
        "contradicts the record, return consistent=true and an empty contradictions list."
    ),
}


def test_static_prompts_are_byte_identical():
    for name, golden in STATIC_GOLDENS.items():
        assert prompts.render(name) == golden, f"{name} drifted from its pre-migration text"


def test_classifier_prompt_renders_byte_identical_with_eligible_grounds():
    # Templated (#9): the eligible-grounds list is substituted for $eligible; the surrounding text
    # (incl. the literal JSON braces) must be exactly the pre-migration _system_prompt output.
    expected = (
        "You decide, in real time, whether Opposing Counsel should INTERRUPT the attorney's "
        "in-progress statement with an objection. Follow the rule: object ONLY when the phrasing "
        "genuinely invites one — NOT on every turn. Most fragments should not trigger an "
        "objection. Use the SESSION RECORD to avoid objecting on grounds already ruled. Valid "
        "objection types: leading, hearsay. objection_type MUST be one of these or null. Respond "
        'ONLY with JSON: {"fire": boolean, "objection_type": <one type or null>, "reason": '
        '"<a few words>"}. Set fire=false and objection_type=null unless there is a clear, '
        "well-founded objection."
    )
    assert (
        prompts.render("objection_classifier_system", eligible="leading, hearsay") == expected
    )


def test_classifier_prompt_empty_eligible_matches_old_empty_join():
    # ", ".join(()) == "" — an empty eligible list substitutes to an empty string in place.
    rendered = prompts.render("objection_classifier_system", eligible="")
    assert "Valid objection types: . objection_type MUST be one of these or null." in rendered


def test_oc_continuation_renders_byte_identical():
    expected = (
        'You are mid-reply and have already said aloud: "the prior sentence"\n'
        "Your next sentence was rejected by verification: a contradiction\n"
        "Continue the reply from where you left off. Do not repeat what you have spoken, and do "
        "not restate the rejected claim."
    )
    assert (
        prompts.render(
            "oc_continuation",
            spoken_prefix="the prior sentence",
            failure_reason="a contradiction",
        )
        == expected
    )


def test_oc_continuation_restart_renders_byte_identical():
    expected = (
        "Your draft reply was rejected by verification: a contradiction\n"
        "Respond again, avoiding the rejected claim."
    )
    assert prompts.render("oc_continuation_restart", failure_reason="a contradiction") == expected


def test_personas_load_with_their_immutable_constraint_intact():
    # The personas were already .md files (unchanged); confirm the registry loads them and the
    # no-fabrication constraint region survived the routing change.
    oc = prompts.render("opposing_counsel")
    jd = prompts.render("judge")
    assert oc and jd
    assert "Do not fabricate case law" in oc
    assert "Do not fabricate case law" in jd


def test_static_render_leaves_literal_json_braces_untouched():
    # $-templating (not str.format): a static prompt with JSON braces is returned verbatim, and a
    # templated prompt's braces survive substitution — no KeyError/brace corruption.
    assert '{"ruling":' in prompts.render("judge_ruling_instruction")
    assert '{"fire": boolean' in prompts.render("objection_classifier_system", eligible="x")


def test_registry_and_directory_stay_in_sync():
    # Every registered name has a file, and every .md file is registered (catches an added prompt
    # that forgot a registry entry, or a stale entry).
    files = {p.stem for p in (prompts._PROMPT_DIR).glob("*.md")}
    assert set(prompts.PROMPT_NAMES) == files


def test_warm_cache_preloads_every_prompt():
    prompts._cache.clear()
    prompts.warm_cache()
    assert set(prompts._cache) == set(prompts.PROMPT_NAMES)
