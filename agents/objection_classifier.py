"""
File: agents/objection_classifier.py
Purpose: The bespoke, differentiating piece (ARCHITECTURE §6). Decides, as the attorney's speech
    streams in, whether Opposing Counsel should interrupt *now* and with what objection type,
    following opposing_counsel.md's rule: object only when the phrasing genuinely invites one —
    not on every turn.

    Three tiers so it can run continuously on partial transcript *and* barge in at courtroom speed:
      1. `candidate_grounds()` — a cheap, RECALL-biased regex gate that runs on every fragment. If
         it finds no objection-inviting phrasing it returns no candidates and we fire nothing (no
         LLM call). Erring toward passing candidates through is deliberate: a too-strict gate would
         silently drop real objections before the LLM ever sees them.
      2. `high_confidence_grounds()` — a PRECISION-biased subset of the gate: phrasing so
         unambiguous (explicit leading tag-questions, direct "he told me" hearsay) that we fire the
         objection IMMEDIATELY, with **no LLM call at all**. This is the latency win — the account
         has no sub-second model (gpt-oss-120b, the fastest available, still costs ~1.3s), so the
         only way to hit real-courtroom timing (~0.5s) on the clear cases is to skip the model.
      3. `classify_fragment()` — for the remaining AMBIGUOUS candidates (a candidate but not
         high-confidence), the fast model (gpt-oss-120b, JSON) makes the final fire/no-fire + type
         decision, applying the "not every turn" discipline and the SessionState (e.g. don't
         re-object on grounds just overruled). Fails closed: any error/timeout/unparseable output →
         NO interruption.

    Supplementary route — comparative-grounds fallback (NOT a fourth tier; a new way INTO tier-3):
    the comparative grounds (`relevance` / `mischaracterizes_record` / `assumes_facts`) are checked
    against the record, not surface phrasing, so they have no tier-1 regex — a purely
    irrelevant/record-mischaracterizing statement trips no gate and would be dropped pre-model.
    So on a COMPLETED final (never interims — those stay cheap at the regex gate), in a proceeding
    where those grounds are eligible and no witness-examination grounds apply (oral_argument /
    motion_hearing), a final that clears a short length floor is routed to the tier-3 model anyway,
    offering the eligible comparative grounds. It reuses the tier-3 machinery verbatim (fail-closed,
    eligible-guard) and every downstream guard (debounce/cooldown/hold live in `consider`, upstream
    of the decider) — only the ENTRY into tier-3 is new. Its fires/no-fires carry their own audit
    outcomes (FALLBACK_FIRE / FALLBACK_NO_FIRE) so this route is separately reviewable, the same way
    FIRE_IMMEDIATE was split from FIRE.

    Timing by proceeding — interims vs finals: in WITNESS examinations (direct/cross) the classifier
    fires on interims, so it barges in mid-question (you cut off a leading/hearsay question as it's
    asked). In ARGUMENT proceedings (oral_argument / motion_hearing) it evaluates only COMPLETED
    statements (Deepgram finals): the attorney is meant to argue the law and characterize the
    record,
    so objecting mid-clause is premature — every interim defers, and the whole statement is judged
    when its final lands. This is why the comparative fallback is finals-only, and it applies to the
    regex-candidate path too in argument (e.g. `calls_for_legal_conclusion` fires on the completed
    statement, not the instant "as a matter of law" is heard). Restraint has two halves: this timing
    rule, and the prompt's calibration (argument objections are rare; ordinary legal argument is not
    an objection) — see prompts/objection_classifier_system.md.

    `ObjectionClassifier` wraps the above with per-utterance debounce so a growing fragment does not
    trigger repeated objections on the same utterance.
Depends on: json, re, dataclasses; agents/llm_router.py, agents/session_state.py
Related: agents/opposing_counsel.py (acts on the signal), agents/prompts/opposing_counsel.md,
    docs/ARCHITECTURE.md §6, docs/DEVELOPER_GUIDELINES.md §6
Security notes: Operates on live transcript fragments (attorney work product) in memory only, and
    sends them only to the configured classifier endpoint — never logs them.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass

import prompts
from llm_router import chat, objection_config, pooled_endpoint
from session_state import SessionState

# Objection taxonomy the classifier may return (ARCHITECTURE §13). The recall gate detects
# leading/hearsay/speculation/argumentative/calls_for_legal_conclusion heuristically;
# `assumes_facts`, `mischaracterizes_record`, and `relevance` are LLM-judged only —
# context-dependent (against the record / the issues), no reliable surface form.
OBJECTION_TYPES = (
    "leading",
    "hearsay",
    "speculation",
    "argumentative",
    "assumes_facts",
    "relevance",
    "mischaracterizes_record",
    "calls_for_legal_conclusion",
)

# Which objection grounds are ELIGIBLE per proceeding type (§13). Keys MUST match
# backend/app/models/session.py PROCEEDING_TYPES (separate package, no shared import — the
# cross-reference is deliberate). Wired into the gate tiers + LLM stage in Phase 4; until then
# this is the declared taxonomy the docs/tests pin down.
#
# Procedural reasoning (decided, not guessed):
# - The witness-testimony grounds — `leading` (suggesting the answer to a witness), `hearsay`
#   (an out-of-court statement offered through a witness), `speculation` (testimony without
#   personal knowledge) — presuppose a WITNESS answering questions. In `oral_argument` and
#   `motion_hearing` (counsel argues to the bench; no witness is being examined) there is no one
#   to lead and no testimony to be hearsay, so none of the three is eligible. This is exactly the
#   mismatch the grounding audit flagged: the recall gate's trailing-"?" pattern fires `leading`
#   on argument-shaped speech, where the objection is procedurally incoherent.
# - `leading` is eligible ONLY on `direct_examination`: leading questions are generally PERMITTED
#   on cross-examination, so it is excluded from `cross_examination` too.
# - `argumentative` targets badgering/argument-disguised-as-question during EXAMINATION of a
#   witness; argument itself is supposed to be argumentative, so it is excluded from the two
#   argument-shaped types.
# - The argument-appropriate grounds: `relevance` (straying outside the issues), `assumes_facts` /
#   `mischaracterizes_record` (asserting facts not in, or misstating, the record), and
#   `calls_for_legal_conclusion`. The last carries a dual reading, documented deliberately: in
#   examinations it takes its classic meaning (a question improperly asking the witness for a
#   legal conclusion); in argument it targets counsel urging the court to adopt a conclusion with
#   no grounding in the record or cited authority — useful sparring feedback even though pure
#   legal argument is of course proper in argument. All four apply everywhere.
PROCEEDING_ELIGIBLE_GROUNDS: dict[str, tuple[str, ...]] = {
    "oral_argument": (
        "relevance",
        "assumes_facts",
        "mischaracterizes_record",
        "calls_for_legal_conclusion",
    ),
    "direct_examination": (
        "leading",
        "hearsay",
        "speculation",
        "argumentative",
        "assumes_facts",
        "relevance",
        "mischaracterizes_record",
        "calls_for_legal_conclusion",
    ),
    "cross_examination": (
        "hearsay",
        "speculation",
        "argumentative",
        "assumes_facts",
        "relevance",
        "mischaracterizes_record",
        "calls_for_legal_conclusion",
    ),
    "motion_hearing": (
        "relevance",
        "assumes_facts",
        "mischaracterizes_record",
        "calls_for_legal_conclusion",
    ),
}


def eligible_grounds_for(proceeding_type: str) -> tuple[str, ...]:
    """The objection grounds eligible in this proceeding type (§13). Unknown or empty proceeding
    type → ALL grounds (fail-open to pre-§13 behavior: offline harnesses and pre-migration
    sessions carry no proceeding type and must not lose objections to the gate)."""
    return PROCEEDING_ELIGIBLE_GROUNDS.get(proceeding_type, OBJECTION_TYPES)

# Recall-biased phrasing gates. Broad on purpose — the LLM is the judgment layer.
_GATE_PATTERNS: dict[str, list[str]] = {
    "leading": [
        r"isn'?t it (?:true|correct|the case)",
        r"\b(?:did|do|does|was|were|is|are|would|could|had|have|has)n'?t (?:you|he|she|they|it)\b",
        r"wouldn'?t you agree",
        r"\byou would agree\b",
        r"(?:right|correct)\?\s*$",
        r"\?\s*$",  # any trailing question — leading is the prime cross-exam objection
    ],
    "hearsay": [
        r"\b(?:told|informed|texted|emailed) (?:me|him|her|us|them)\b",
        r"\b(?:he|she|they|it|the witness|my client|someone|everyone)\s+"
        r"(?:said|says|stated|claimed|mentioned|testified|reported|told)\b",
        r"according to\b",
        r"\bi (?:heard|was told)\b",
        r"said that\b",
    ],
    "speculation": [
        r"\bi (?:think|believe|guess|assume|suppose|feel|figure)\b",
        r"\b(?:maybe|perhaps|probably|possibly|presumably)\b",
        r"\b(?:might|may|could|would|must|should) have\b",
        r"seems? (?:like|to)\b",
    ],
    "argumentative": [
        r"\b(?:obviously|clearly|undeniably)\b",
        r"everyone knows",
        r"any reasonable person",
    ],
    # §13 new grounds — regex-detectability judgment: `calls_for_legal_conclusion` has recognizable
    # surface phrasing (urging the court to adopt a conclusion / "as a matter of law" framing), so
    # it gets recall-gate patterns; `relevance` and `mischaracterizes_record` are inherently
    # comparative (against the issues / against the record) with no reliable surface form, so they
    # stay LLM-only — the same split the original taxonomy made for `assumes_facts`. NONE of the
    # new grounds joins the tier-2 immediate-fire set: e.g. "as a matter of law" is normal,
    # proper phrasing in argument, so firing on it without judgment would be wrong — argument-shaped
    # objections are inherently judgment calls, which also means every fire in oral_argument /
    # motion_hearing is LLM-judged (tier-2 holds only leading/hearsay, ineligible there).
    "calls_for_legal_conclusion": [
        r"\bas a matter of law\b",
        r"\bthe court (?:should|must) (?:find|hold|rule|conclude|declare)\b",
        r"\b(?:that|this|which) (?:constitutes|amounts to)\b",
    ],
}
_COMPILED = {g: [re.compile(p, re.IGNORECASE) for p in pats] for g, pats in _GATE_PATTERNS.items()}

# PRECISION-biased subset of the gate: phrasing so unambiguous it fires immediately without the LLM
# (tier 2). The opposite bias from the recall gate — only patterns that are almost never a false
# positive belong here. Deliberately EXCLUDES the recall catch-alls (a bare trailing "?", "right?")
# and the context-dependent grounds (speculation / argumentative / assumes_facts), which stay
# LLM-judged. If a pattern here proves too aggressive, its fires show up under FIRE_IMMEDIATE in the
# audit trail (kept distinct from LLM fires on purpose) so we can catch it in the data.
_HIGH_CONFIDENCE_PATTERNS: dict[str, list[str]] = {
    "leading": [
        r"isn'?t it (?:true|correct|the case)",
        r"wouldn'?t you agree",
        r"\byou would agree\b",
        r"\b(?:did|do|does|was|were|is|are|would|could|had|have|has)n'?t (?:you|he|she|they|it)\b",
    ],
    "hearsay": [
        r"\b(?:told|informed|texted|emailed) (?:me|him|her|us|them)\b",
        r"\bi (?:heard|was told)\b",
        # "according to" is intentionally NOT here: it immediate-fired (no LLM) on legitimate
        # citations too ("according to Section 5 of the contract…" is not hearsay). It stays in the
        # tier-1 recall gate, so it still reaches tier-3 where the model judges it — trading ~1.3s
        # of latency on that phrasing for not blind-firing on a citation.
    ],
}
_HC_COMPILED = {
    g: [re.compile(p, re.IGNORECASE) for p in pats]
    for g, pats in _HIGH_CONFIDENCE_PATTERNS.items()
}
# Priority when several high-confidence grounds match one fragment: leading is the prime cross-exam
# objection, so it wins over hearsay.
_IMMEDIATE_PRIORITY = ("leading", "hearsay")


# Decision outcomes — the audit categories. GATE_REJECTED never reached the LLM (the gate filtered
# it); FIRE_IMMEDIATE fired on a high-confidence pattern WITHOUT the LLM (tier 2); LLM_NO_FIRE and
# FIRE reached the LLM (tier 3) via a regex candidate, which declined / fired; FALLBACK_NO_FIRE and
# FALLBACK_FIRE reached the LLM via the comparative-grounds fallback (a completed final with no
# regex candidate, argument proceedings only), which declined / fired; FAIL_CLOSED is a swallowed
# error; DEBOUNCED is a suppressed repeat of an already-objected utterance. Keeping the fallback
# outcomes distinct from FIRE/LLM_NO_FIRE lets us see, in the data, how often the comparative route
# fires vs. over-fires — the same instinct that split FIRE_IMMEDIATE from FIRE.
GATE_REJECTED = "gate_rejected"
FIRE_IMMEDIATE = "fire_immediate"
LLM_NO_FIRE = "llm_no_fire"
FIRE = "fire"
FALLBACK_FIRE = "fallback_fire"
FALLBACK_NO_FIRE = "fallback_no_fire"
FAIL_CLOSED = "fail_closed"
DEBOUNCED = "debounced"


@dataclass
class Decision:
    """Whether to interrupt now, the objection type (if any), and the audit outcome."""

    fire: bool
    objection_type: str | None
    reason: str
    outcome: str = ""


def candidate_grounds(fragment: str) -> list[str]:
    """Tier 1: recall-biased regex gate. Returns the objection grounds the phrasing may invite."""
    text = fragment.strip()
    if not text:
        return []
    return [ground for ground, pats in _COMPILED.items() if any(p.search(text) for p in pats)]


def high_confidence_grounds(fragment: str) -> list[str]:
    """
    Tier 2: precision-biased subset. Returns grounds whose phrasing is unambiguous enough to fire
    immediately, with no LLM call. A subset of `candidate_grounds` — never broadens what fires.
    """
    text = fragment.strip()
    if not text:
        return []
    return [ground for ground, pats in _HC_COMPILED.items() if any(p.search(text) for p in pats)]


def _immediate_objection_type(grounds: list[str]) -> str:
    """Pick the objection type for an immediate fire when several high-confidence grounds match."""
    for ground in _IMMEDIATE_PRIORITY:
        if ground in grounds:
            return ground
    return grounds[0]


# Grounds tier-1 can detect from surface phrasing (the recall-gate keys). Anything eligible but NOT
# here is a comparative ground with no regex — the ones the fallback exists to reach.
_REGEX_GROUNDS = frozenset(_GATE_PATTERNS)
# Witness-examination grounds. If ANY is eligible, a witness is being examined (direct/cross, or the
# fail-open unknown/empty proceeding type that returns ALL grounds) — the comparative fallback stays
# off so it doesn't flood examination turns; those grounds already reach tier-3 via their regex.
_WITNESS_EXAM_GROUNDS = frozenset({"leading", "hearsay", "speculation", "argumentative"})
# Length floor (words) below which a completed final is too trivial to spend an LLM call on ("That's
# irrelevant.", "So what?"). Cheapest check — applied before any proceeding/ground work.
FALLBACK_MIN_WORDS = 8


def _is_argument_proceeding(eligible: tuple[str, ...]) -> bool:
    """True for argument proceedings (oral_argument / motion_hearing): no witness-examination
    ground is eligible, so counsel argues to the bench rather than examining a witness. False for
    direct/cross AND for the fail-open unknown/empty proceeding type (which returns ALL grounds,
    witness grounds included) — so offline harnesses/tests with no proceeding type keep interim
    firing and stay retrieval-inert as before."""
    return not any(g in eligible for g in _WITNESS_EXAM_GROUNDS)


def comparative_fallback_grounds(fragment: str, state: SessionState, is_final: bool) -> list[str]:
    """The comparative grounds to offer when a COMPLETED final trips no eligible tier-1 candidate —
    the supplementary route into tier-3 (see module docstring). Returns [] (→ no fallback,
    ordinary gate-reject) unless ALL hold: it's a final (interims stay cheap); the proceeding is
    argument-only (no witness-exam ground eligible — excludes direct/cross AND the fail-open
    unknown/empty proceeding type); and it clears the length floor. Grounds are derived from
    `eligible_grounds_for` (the single source of truth), filtered to those with no regex — never a
    hardcoded list, so a change to the eligibility map or taxonomy carries through automatically."""
    if not is_final:
        return []
    if len(fragment.split()) < FALLBACK_MIN_WORDS:
        return []
    eligible = eligible_grounds_for(state.proceeding_type)
    if not _is_argument_proceeding(eligible):
        return []
    return [g for g in eligible if g not in _REGEX_GROUNDS]


def _build_messages(
    fragment: str,
    state: SessionState,
    candidates: list[str],
    rules: str = "",
    *,
    via_fallback: bool = False,
) -> list[dict[str, str]]:
    """Assemble the minimal classifier messages (+ the §13 procedural-rules block when retrieval
    produced one; + the proceeding type so the model judges in the right procedural frame).
    Pure — no API call. `via_fallback` reframes the candidate hint: on the comparative fallback the
    grounds were NOT triggered by any surface signal (the fragment matched no regex), so presenting
    them like detected candidates biases the model toward firing — instead they are framed as
    grounds to CONSIDER, with the reminder that usually none applies."""
    if via_fallback:
        hint = (
            "no objection signal was detected — consider whether ANY of these clearly applies to "
            f"the completed statement; usually none does, so default to not firing: "
            f"{', '.join(candidates)}"
        )
    else:
        hint = ", ".join(candidates) if candidates else "none"
    context = f"SESSION RECORD:\n{state.snapshot()}"
    if state.proceeding_type:
        context += f"\n\nPROCEEDING TYPE: {state.proceeding_type}"
    if rules:
        context += f"\n\n{rules}"
    user = (
        f"{context}\n\n"
        f"HEURISTIC CANDIDATES: {hint}\n\n"
        f'ATTORNEY (statement in progress): "{fragment}"'
    )
    return [
        {
            "role": "system",
            "content": prompts.render(
                "objection_classifier_system",
                eligible=", ".join(eligible_grounds_for(state.proceeding_type)),
            ),
        },
        {"role": "user", "content": user},
    ]


def _parse_decision(content: str) -> Decision:
    """Parse the model's JSON decision. Pure — raises on unparseable input (caller fails closed)."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("classifier did not return a JSON object")
    data = json.loads(content[start : end + 1])
    fire = bool(data.get("fire", False))
    raw_type = data.get("objection_type")
    objection_type = str(raw_type).strip().lower() if fire and raw_type else None
    reason = str(data.get("reason", "")).strip()
    outcome = FIRE if fire else LLM_NO_FIRE
    return Decision(fire=fire, objection_type=objection_type, reason=reason, outcome=outcome)


def classify_fragment(fragment: str, state: SessionState, *, is_final: bool = False) -> Decision:
    """
    Tiers 1–3. Tier 1: no gate candidate → no fire (GATE_REJECTED, no LLM). Tier 2: a
    high-confidence candidate → fire IMMEDIATELY (FIRE_IMMEDIATE, no LLM). Tier 3: an ambiguous
    candidate → the fast model makes the call. Fails closed — any error/timeout/unparseable output
    returns NO interruption.

    `is_final` marks a completed Deepgram final (vs. an interim). It ONLY enables the comparative-
    grounds fallback (see module docstring): a final with no eligible tier-1 candidate, in an
    argument proceeding, is routed to the tier-3 model on the comparative grounds instead of being
    gate-rejected. Interims (`is_final=False`, the default) are unaffected — they gate-reject as
    before, so nothing changes on the streaming path or for any existing caller/test.
    """
    # §13 proceeding-type gating: an ineligible ground is filtered at EVERY tier — it never
    # reaches the LLM, and a tier-2 pattern for an ineligible ground (e.g. leading's trailing-"?"
    # in oral argument, the audit-flagged mismatch) can no longer fire at all.
    eligible = eligible_grounds_for(state.proceeding_type)
    # Argument proceedings evaluate COMPLETED statements, not interims: in oral_argument /
    # motion_hearing the attorney is expected to argue the law and characterize the record, so
    # objecting mid-clause is premature — defer every interim and judge the whole statement when
    # its Deepgram final lands. (Witness examinations keep interim barge-in — you cut off an
    # improper question as it's asked.) Also saves an LLM call per interim in argument. This is the
    # timing half of the over-firing fix; the prompt calibration is the judgment half.
    if _is_argument_proceeding(eligible) and not is_final:
        return Decision(
            False,
            None,
            "argument proceeding — awaiting the completed statement",
            outcome=GATE_REJECTED,
        )
    raw_candidates = candidate_grounds(fragment)
    candidates = [g for g in raw_candidates if g in eligible]
    via_fallback = False
    if not candidates:
        # Supplementary route: a completed final in an argument proceeding, no eligible regex
        # candidate → offer the comparative grounds to the model rather than dropping it. Empty
        # unless finals-only + argument-proceeding + length-floor all hold (see the helper).
        fallback = comparative_fallback_grounds(fragment, state, is_final)
        if fallback:
            candidates = fallback
            via_fallback = True
        else:
            reason = (
                f"grounds ineligible for {state.proceeding_type}"
                if raw_candidates
                else "no objection-inviting phrasing"
            )
            return Decision(False, None, reason, outcome=GATE_REJECTED)
    # Tier 2 (high-confidence immediate fire) is regex-only; the comparative fallback offers only
    # grounds with no regex, so `high` is always empty on the fallback route (it flows to tier-3).
    high = [g for g in high_confidence_grounds(fragment) if g in eligible]
    if high:
        ground = _immediate_objection_type(high)
        return Decision(
            True, ground, f"high-confidence {ground} pattern", outcome=FIRE_IMMEDIATE
        )
    try:
        # §13: ground the AMBIGUOUS-candidate judgment in the forum's actual rules. Court corpus
        # only (the snapshot already carries the case summary); query = fragment + the candidate
        # grounds so retrieval is targeted. TIGHT timeout — this sits in the live barge-in path;
        # a slow fetch degrades to an ungrounded (current-behavior) decision, never a stall.
        # Runs ONLY on the tier-3 path (gate rejects and immediate fires never reach here) and
        # ONLY with a live session id — offline harnesses/tests never attempt retrieval.
        rules = ""
        if state.session_id:
            import court_knowledge

            rules = court_knowledge.rules_block(
                court_knowledge.retrieve_court_passages(
                    state.session_id,
                    f"{', '.join(candidates)}: {fragment}",
                    timeout=court_knowledge.FAST_TIMEOUT,
                )
            )
        endpoint = pooled_endpoint(objection_config())
        content = chat(
            endpoint,
            _build_messages(fragment, state, candidates, rules, via_fallback=via_fallback),
            temperature=0.0,
            # gpt-oss reasons before emitting; too small a budget yields EMPTY content (finish=
            # length → fail_closed). The proceeding-aware calibration made the comparative judgments
            # (relevance/mischaracterizes/assumes_facts) reason more, and 512 — the old floor for
            # the simpler prompt — started returning empty on them (verified: finish=length at 512,
            # clean JSON at 1024). Raised to 1024. This is a CEILING, not a target: simple cases
            # (leading/hearsay/CLC) still stop well under it, so no latency cost there. The floor
            # scales with task complexity — re-check with a live call when the prompt changes (see
            # docs/LESSONS.md, the gpt-oss max_tokens entry).
            max_tokens=1024,
            response_format={"type": "json_object"},
            # Tighter than the global LLM_TIMEOUT_S: this call holds THIS session's classifier
            # lock (consider() serializes), so a hang delays every queued interim for the
            # utterance. Healthy calls run ~1.3-3s; past 10s the objection moment has passed
            # anyway — fail closed (no interruption) and move on.
            timeout=10.0,
        )
        decision = _parse_decision(content)
        # Belt-and-braces: the prompt only OFFERS eligible types, but if the model fires with one
        # anyway (or invents a type), a procedurally incoherent objection must never be spoken.
        if decision.fire and decision.objection_type not in eligible:
            decision = Decision(
                False,
                None,
                f"model returned ineligible ground {decision.objection_type!r} "
                f"for {state.proceeding_type or 'unknown proceeding'}",
                outcome=LLM_NO_FIRE,
            )
        # Mark the comparative-fallback route with its own audit outcomes so it's reviewable apart
        # from ordinary regex-candidate LLM decisions (FALLBACK_FIRE / FALLBACK_NO_FIRE).
        if via_fallback:
            decision.outcome = FALLBACK_FIRE if decision.fire else FALLBACK_NO_FIRE
        return decision
    except Exception:
        return Decision(
            False, None, "classifier unavailable — no interruption", outcome=FAIL_CLOSED
        )


@dataclass
class DecisionRecord:
    """One considered fragment and its decision — retained only when review logging is enabled."""

    fragment: str
    decision: Decision


def _normalize(text: str) -> str:
    """Lowercase, strip everything but alphanumerics, collapse whitespace. STT finals rewrite
    casing/punctuation relative to interims of the SAME utterance ("i i my client told me" →
    "I, I, my client told me…"), so continuation must be judged on normalized content, not raw
    strings — an exact-prefix check re-arms the debounce on the revised final and double-fires."""
    return " ".join(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())


# Default seconds after a fire before the classifier may fire again (a FLOOR — re-arming is also
# gated on any in-flight inline ruling completing; see hold()/release_hold()).
DEFAULT_REFIRE_COOLDOWN = 5.0


class ObjectionClassifier:
    """
    Stateful wrapper that debounces a growing utterance: once it has objected on an utterance, it
    will not object again until a new utterance begins (a fragment that no longer extends the
    previous one, compared on NORMALIZED text — see `_normalize`). `decider` is injectable for
    deterministic testing.

    Two additional guards against double-firing (and against objecting over the judge):
    - **Re-fire cooldown (time floor):** after any fire, no further fire for `refire_cooldown`
      seconds (injectable `clock` for deterministic tests). Covers transcript rewrites that
      normalization can't (e.g. "March third" → "March 3").
    - **Ruling hold:** while an inline judge ruling is in flight, `hold()` keeps the classifier
      suppressed regardless of elapsed time; `release_hold()` (always called, on success, failure,
      or timeout) lifts it. Re-arming requires BOTH the floor elapsed AND the hold released, so a
      slow ruling call (network jitter) can't be objected over.

    With `record=True` it keeps a review log so gate-rejected fragments can be inspected separately
    from LLM no-fire decisions (see `gate_rejected()` / `llm_no_fire()`). Off by default because the
    log retains transcript fragments (attorney work product) — enable only for testing/review.

    Thread-safe: the voice worker feeds interim transcripts through `consider()` via
    `asyncio.to_thread`, so several fragments can land in parallel threads. A lock serializes the
    debounce state — the decision is inherently sequential (we never want two overlapping
    classifications racing on the same growing utterance), so serializing it is correct, not merely
    defensive. The lock is held across the decider's (blocking) call, which naturally queues later
    interims behind the in-flight one; the debounce then short-circuits them.
    """

    def __init__(
        self,
        state: SessionState,
        decider=classify_fragment,
        record: bool = False,
        refire_cooldown: float = DEFAULT_REFIRE_COOLDOWN,
        clock=time.monotonic,
    ):
        self.state = state
        self._decide = decider
        self._prev = ""
        self._handled = False
        self._record = record
        self.records: list[DecisionRecord] = []
        self._lock = threading.Lock()
        self._refire_cooldown = refire_cooldown
        self._clock = clock
        self._last_fire_at: float | None = None
        self._held = False

    def hold(self) -> None:
        """Suppress further fires until release_hold() — an inline judge ruling is in flight."""
        with self._lock:
            self._held = True

    def release_hold(self) -> None:
        """Lift the ruling hold (call on ruling success, failure, OR timeout — always)."""
        with self._lock:
            self._held = False

    def _suppressed_reason(self) -> str | None:
        """Why a fire must be suppressed right now (cooldown floor / ruling hold), or None."""
        if self._held:
            return "ruling in progress — no objections over the judge"
        if self._last_fire_at is not None:
            elapsed = self._clock() - self._last_fire_at
            if elapsed < self._refire_cooldown:
                return "re-fire cooldown after the last objection"
        return None

    def consider(self, fragment: str, is_final: bool = False) -> Decision:
        with self._lock:
            frag = fragment.strip()
            if not self._is_continuation(self._prev, frag):
                self._handled = False  # a genuinely new utterance re-arms the classifier
            self._prev = frag
            if self._handled:
                decision = Decision(
                    False, None, "already objected on this utterance", outcome=DEBOUNCED
                )
            elif (reason := self._suppressed_reason()) is not None:
                decision = Decision(False, None, reason, outcome=DEBOUNCED)
            else:
                # is_final only enables the comparative-grounds fallback inside the decider; every
                # debounce/cooldown/hold guard above is upstream and unchanged, so a fallback fire
                # is deduped/cooled/held exactly like any other fire.
                decision = self._decide(frag, self.state, is_final=is_final)
                if decision.fire:
                    self._handled = True
                    self._last_fire_at = self._clock()
            if self._record:
                self.records.append(DecisionRecord(fragment=frag, decision=decision))
            return decision

    @staticmethod
    def _is_continuation(prev: str, current: str) -> bool:
        """True if `current` is the same utterance still growing or a REVISION of it — compared on
        normalized text, because STT finals are not prefix-stable with their interims."""
        norm_prev = _normalize(prev)
        return bool(norm_prev) and _normalize(current).startswith(norm_prev)

    def gate_rejected(self) -> list[DecisionRecord]:
        """Fragments the gate filtered out before any LLM judgment — review the recall bias here."""
        return [r for r in self.records if r.decision.outcome == GATE_REJECTED]

    def immediate_fires(self) -> list[DecisionRecord]:
        """High-confidence fires that skipped the LLM — audit whether the gate is too aggressive."""
        return [r for r in self.records if r.decision.outcome == FIRE_IMMEDIATE]

    def llm_no_fire(self) -> list[DecisionRecord]:
        """Fragments that reached the LLM but were judged not to warrant an objection."""
        return [r for r in self.records if r.decision.outcome == LLM_NO_FIRE]

    def comparative_fallback(self) -> list[DecisionRecord]:
        """Fragments routed to the LLM via the comparative-grounds fallback (finals-only, argument
        proceedings) — fire or no-fire. Review whether this route catches real misses without
        over-firing; read each record's `.decision.fire` for the model's verdict."""
        return [
            r
            for r in self.records
            if r.decision.outcome in (FALLBACK_FIRE, FALLBACK_NO_FIRE)
        ]
