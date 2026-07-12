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
        "Respond as opposing counsel in ONE or TWO short, punchy sentences — this is fast verbal "
        "sparring, never a speech. Output only the words you say aloud in the courtroom — no "
        "analysis, headings, quotation marks, or preamble. Argue the merits as direct "
        "counter-argument — do NOT lodge an objection or use the words "
        '"objection" or "I object"; state the point as argument instead (e.g. "The record does '
        'not support that…").'
    ),
    "judge_ruling_instruction": (
        "If you cite a rule, name only a section heading that appears in RELEVANT PROCEDURAL "
        "RULES; otherwise rule without naming a specific citation. "
        'Respond ONLY with JSON: {"ruling": "<what you say aloud from the bench>"}.'
    ),
    "judge_assessment": (
        "Review the full session below. Then, as the presiding judge:\n"
        "1. For EACH objection still marked [pending] in the SESSION RECORD, in the order listed, "
        "rule 'sustained' or 'overruled' on the MERITS given the PROCEEDING TYPE — an objection "
        "being raised is not itself grounds to sustain it. In an ARGUMENT proceeding (oral "
        "argument, motion hearing) no witness is testifying: counsel may argue the law, draw "
        "inferences, characterize the record, and urge legal conclusions, so objections that the "
        'argument "assumes facts not in the record," "calls for a legal conclusion," or is '
        '"argumentative" are usually IMPROPER and should be OVERRULED unless the statement '
        "genuinely misstates an established fact or strays entirely from the issues; in a WITNESS "
        "EXAMINATION apply the ordinary evidentiary grounds normally. SUSTAIN when a statement "
        "asserted a specific unestablished fact as though proven, misstated or mischaracterized "
        "the record, the pleading, or the parties, or strayed from the matter before the court; "
        "do not default to either disposition. Objections already "
        "marked [sustained] or [overruled] were ruled from the bench DURING the session — do NOT "
        "re-rule them; treat those rulings as final.\n"
        "2. List 2-5 key facts the attorney genuinely established on the record (supported by the "
        "transcript and not undercut by a sustained objection). Return an empty array if none.\n"
        "3. Give a one- to two-sentence closing ruling from the bench that reflects the session as "
        "a whole, including a brief acknowledgment of the objections already ruled during the "
        "session. If you cite a rule, name only a section heading that appears in RELEVANT "
        "PROCEDURAL RULES; otherwise rule without naming a specific citation.\n"
        "4. Grade the attorney's performance 0-100 (`performance_score`), judged on: command of "
        "the record (arguing from the established facts and pleading, not invention), "
        "responsiveness to rulings (adjusting after a sustained objection rather than repeating "
        "the fault), argument structure (a coherent, advancing line of argument rather than "
        "repetition), and procedural discipline (drawing few sustained objections). Grade like a "
        "judge, not a cheerleader: 85+ only for a genuinely strong showing; a session that merely "
        "avoided sustained objections is not automatically excellent. Also list 1-3 "
        "`performance_notes` — specific, constructive weaknesses you observed in the transcript "
        "(empty array only if the performance was genuinely without fault). Give a 0-100 sub-score "
        "for each of those four dimensions in `performance_criteria` — keys `command_of_record`, "
        "`responsiveness`, `argument_structure`, `procedural_discipline` — consistent with the "
        "overall grade.\n"
        'Respond ONLY with JSON: {"rulings": ["sustained"|"overruled", ...], "established_facts": '
        '["<fact>", ...], "closing_ruling": "<what you say aloud>", "performance_score": <0-100>, '
        '"performance_notes": ["<specific weakness>", ...], "performance_criteria": '
        '{"command_of_record": <0-100>, "responsiveness": <0-100>, "argument_structure": <0-100>, '
        '"procedural_discipline": <0-100>}}. The rulings array must have '
        "exactly one entry per [pending] objection, in the same order (empty array if none are "
        "pending)."
    ),
    "judge_quick_ruling": (
        "You are the presiding judge in a courtroom rehearsal. Opposing Counsel just objected to "
        "the attorney's statement. Rule IMMEDIATELY from the bench — but rule on the MERITS: an "
        "objection being raised is not itself a reason to sustain it. Sustain only when the "
        "statement actually violates a rule appropriate to the current PROCEEDING TYPE; otherwise "
        "overrule.\n"
        "\n"
        "In an ARGUMENT proceeding (oral argument, motion hearing) no witness is testifying — "
        "counsel may argue the law, draw inferences, characterize the record, and urge legal "
        'conclusions. Objections aimed at the FORM of genuine argument ("assumes facts not in '
        'the record," "calls for a legal conclusion," "argumentative") are usually IMPROPER '
        "here: OVERRULE them. But the merits test cuts BOTH ways — SUSTAIN when the statement "
        "(a) asserts a specific unestablished fact as though proven (an event, a document's "
        "contents, a party's act, knowledge, or intent that the SESSION RECORD and case "
        "materials do not support), (b) misstates or mischaracterizes the record, the pleading, "
        "or the parties, or (c) strays from the MATTER BEFORE THE COURT — judge relevance "
        "against that matter, never against your own guess at the issues. Identifying the case — "
        "its docket or case number, its caption or parties, or its procedural posture — is "
        "routine housekeeping, not a factual assertion: OVERRULE objections to it. In a WITNESS "
        "EXAMINATION (direct or cross) apply the ordinary evidentiary grounds normally.\n"
        "\n"
        "Do not default to either disposition: do not sustain merely because the objection names "
        "a ground, and do not overrule merely because argument is broadly permitted — test "
        "whether the ground actually fits this statement in this proceeding. "
        "State one crisp, judicial sentence "
        "(spoken aloud) that gives your reasoning and MATCHES your ruling and the objection's "
        "ground — authoritative and specific, not a bare label. Do not restate the ruling word "
        '("Sustained"/"Overruled") inside the reason; it is spoken separately. If you cite a rule, '
        "name only a section heading that appears in RELEVANT PROCEDURAL RULES; otherwise rule "
        'without naming a specific citation. Respond ONLY with JSON: {"ruling": '
        '"sustained"|"overruled", "reason": "<one sentence>"}.'
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
    # Templated (#9): the eligible-grounds list is substituted for $eligible. This golden was
    # DELIBERATELY updated with the per-ground reasoning-cue addition (same pattern as R1-R4:
    # a behavior change is made by changing prompt + golden together, never silently) — the cues
    # describe recognition patterns/advocacy skill, NEVER what any jurisdiction's law requires.
    expected = (
        "You decide, in real time, whether Opposing Counsel should INTERRUPT the attorney's "
        "in-progress statement with an objection. Follow the rule: object ONLY when the phrasing "
        "genuinely invites one — NOT on every turn. Most statements should NOT trigger an "
        "objection; when in doubt, do not object. Use the SESSION RECORD to avoid objecting on "
        "grounds already ruled.\n"
        "\n"
        "Recognize each ground by its pattern, not by keywords alone — these cues describe every "
        "ground, but you may CHOOSE only from the Valid objection types listed at the end:\n"
        "- leading: the question supplies its own answer (tag questions, \"isn't it true…\").\n"
        "- hearsay: repeating an out-of-court statement to prove the thing it asserts "
        '("he told me…", "according to…").\n'
        "- speculation: asserting another person's knowledge, intent, or hypothetical conduct "
        "without personal knowledge.\n"
        "- argumentative: arguing a conclusion at the witness, or badgering, instead of asking "
        "a question.\n"
        "- assumes_facts: presupposing a specific fact that appears nowhere in the SESSION "
        "RECORD.\n"
        "- relevance: the statement bears on NO issue in dispute — ask what fact of consequence "
        "it advances; only if there is plainly none is it objectionable.\n"
        "- mischaracterizes_record: the statement misstates or distorts a SPECIFIC thing the "
        "SESSION RECORD establishes — compare its wording against the established facts and case "
        "summary; a fair characterization or ordinary emphasis is not this.\n"
        "- calls_for_legal_conclusion: pressing the court to adopt a legal conclusion with NO "
        "record support or cited authority — NOT ordinary legal argument. Arguing \"as a matter "
        'of law the court should find X" is proper advocacy, not an objection.\n'
        "\n"
        "Calibrate like a competent opposing counsel: object only on a clear, seizable flaw one "
        "would ACTUALLY rise for — a real misstatement of an established fact, a genuinely "
        "irrelevant aside, a conclusion urged with no support — never merely because a statement "
        "is arguable, forceful, or one you disagree with. In an argument proceeding the attorney "
        "is SUPPOSED to argue the law and characterize the record; interruptions there are rare, "
        "so hold the bar high. Routine case identification and procedural housekeeping — stating "
        "the case's number or caption, naming the parties, or describing the proceeding — is "
        "never objectionable: never fire on it. For relevance and mischaracterizes_record, make "
        "the comparison "
        "against the SESSION RECORD explicitly first — usually there is no clear mismatch, so "
        "usually do not fire.\n"
        "\n"
        "Valid objection types: leading, hearsay. objection_type MUST be one of these or null. "
        'Respond ONLY with JSON: {"fire": boolean, "objection_type": <one type or null>, '
        '"reason": "<a few words>"}. Set fire=false and objection_type=null unless there is a '
        "clear, well-founded objection."
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


def test_expressive_assessment_is_the_default_plus_a_tag_addendum():
    # Track B: the expressive variant MUST be the byte-identical default assessment prompt plus an
    # appended audio-tag-authoring addendum — so the default (non-v3) path is provably unchanged.
    default = STATIC_GOLDENS["judge_assessment"]
    assert prompts.render("judge_assessment") == default  # default path unchanged
    expressive = prompts.render("judge_assessment_expressive")
    assert expressive.startswith(default + "\n")
    addendum = expressive[len(default) + 1 :]
    assert "[solemnly]" in addendum
    assert "delivery only" in addendum  # frames tags as delivery, not content


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
