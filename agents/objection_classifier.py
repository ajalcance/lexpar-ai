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

from llm_router import build_endpoint, chat, objection_config
from session_state import SessionState

# Objection taxonomy the classifier may return (ARCHITECTURE §13). The regex gate detects
# leading/hearsay/speculation/argumentative heuristically; `assumes_facts`,
# `mischaracterizes_record`, and `calls_for_legal_conclusion` are LLM-judged (context-dependent,
# not reliably regex-detectable); `relevance` likewise (what is relevant depends on the issues).
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
        r"according to\b",
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
# FIRE reached the LLM (tier 3) which declined / fired; FAIL_CLOSED is a swallowed error; DEBOUNCED
# is a suppressed repeat of an already-objected utterance. Keeping FIRE_IMMEDIATE distinct from FIRE
# is what lets us see, in the data, whether the high-confidence gate is ever firing too aggressively
# — the same instinct that splits GATE_REJECTED from LLM_NO_FIRE.
GATE_REJECTED = "gate_rejected"
FIRE_IMMEDIATE = "fire_immediate"
LLM_NO_FIRE = "llm_no_fire"
FIRE = "fire"
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


_SYSTEM = (
    "You decide, in real time, whether Opposing Counsel should INTERRUPT the attorney's "
    "in-progress statement with an objection. Follow the rule: object ONLY when the phrasing "
    "genuinely invites one — NOT on every turn. Most fragments should not trigger an objection. "
    "Use the SESSION RECORD to avoid objecting on grounds already ruled. Valid objection types: "
    + ", ".join(OBJECTION_TYPES)
    + '. Respond ONLY with JSON {"fire": boolean, "objection_type": <one type or null>, '
    '"reason": "<a few words>"}. Set fire=false and objection_type=null unless there is a clear, '
    "well-founded objection."
)


def _build_messages(
    fragment: str, state: SessionState, candidates: list[str]
) -> list[dict[str, str]]:
    """Assemble the minimal classifier messages. Pure — no API call."""
    hint = ", ".join(candidates) if candidates else "none"
    user = (
        f"SESSION RECORD:\n{state.snapshot()}\n\n"
        f"HEURISTIC CANDIDATES: {hint}\n\n"
        f'ATTORNEY (statement in progress): "{fragment}"'
    )
    return [
        {"role": "system", "content": _SYSTEM},
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


def classify_fragment(fragment: str, state: SessionState) -> Decision:
    """
    Tiers 1–3. Tier 1: no gate candidate → no fire (GATE_REJECTED, no LLM). Tier 2: a
    high-confidence candidate → fire IMMEDIATELY (FIRE_IMMEDIATE, no LLM). Tier 3: an ambiguous
    candidate → the fast model makes the call. Fails closed — any error/timeout/unparseable output
    returns NO interruption.
    """
    candidates = candidate_grounds(fragment)
    if not candidates:
        return Decision(False, None, "no objection-inviting phrasing", outcome=GATE_REJECTED)
    high = high_confidence_grounds(fragment)
    if high:
        ground = _immediate_objection_type(high)
        return Decision(
            True, ground, f"high-confidence {ground} pattern", outcome=FIRE_IMMEDIATE
        )
    try:
        endpoint = build_endpoint(objection_config())
        content = chat(
            endpoint,
            _build_messages(fragment, state, candidates),
            temperature=0.0,
            # gpt-oss reasons before emitting; too small a budget yields empty content, so give it
            # room for the hidden reasoning plus the short JSON decision.
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        return _parse_decision(content)
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

    def consider(self, fragment: str) -> Decision:
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
                decision = self._decide(frag, self.state)
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
