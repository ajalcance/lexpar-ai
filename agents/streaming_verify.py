"""
File: agents/streaming_verify.py
Purpose: Streaming sentence-level verification for Opposing Counsel's replies (ARCHITECTURE §6.5).
    Instead of generating the full reply and then running one blocking verification pass (~7-11s to
    first audio), this streams the LLM's output, segments it into sentences as tokens arrive
    (SentenceSegmenter, with a legal-abbreviation guard so "Brown v. Board" and "347 U.S. 483"
    never split), and verifies EACH sentence — citation heuristic on the sentence, consistency
    check on the accumulated verified prefix + candidate — before yielding it to TTS. Nothing
    unverified is ever spoken; sentence 2 verifies while sentence 1 is already playing.

    Mid-stream failure (Option B, PLAN): the failed sentence and the rest of its stream are
    discarded, and ONE repair continuation is requested (continue from the verified prefix,
    avoiding the rejected claim); the repair is verified the same way. If the repair also fails,
    fall back to truncation at the last verified sentence. A citation-heuristic hit is treated
    exactly like a consistency failure (one failure path). Fail-closed throughout: a verifier or
    stream error stops the reply at the last verified sentence — never speak on doubt.

    Generation, repair, and consistency are injectable, so the whole pipeline is offline-testable;
    the defaults are the real opposing_counsel / verification functions.
Depends on: asyncio (bridge only); agents/opposing_counsel.py, agents/verification.py,
    agents/session_state.py
Related: agents/main.py (consumes astream_verified_reply in llm_node),
    agents/streaming_harness.py, docs/ARCHITECTURE.md §6.5
Security notes: Operates on draft reply text (attorney work product) in memory only. Logs counts
    and exception types, never sentence content.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterable, Iterator

import opposing_counsel
import verification
from session_state import SessionState

logger = logging.getLogger("lexpar.agents.streaming")

# Injectable call shapes (defaults are the real live functions).
Consistency = Callable[[str, SessionState], list[str]]
StreamFactory = Callable[[SessionState, str], Iterable[str]]
RepairFactory = Callable[[SessionState, str, str, str], Iterable[str]]

_TERMINATORS = frozenset(".!?")
_CLOSING_QUOTES = frozenset("\"'”’")

# Words whose trailing period is an abbreviation, not a sentence end. Lowercased for comparison.
# Single-letter tokens (initials, "F.", the "S" in "U.S.") are guarded structurally, not listed.
_ABBREVIATIONS = frozenset(
    {
        "v", "vs", "no", "nos", "mr", "ms", "mrs", "dr", "jr", "sr", "st", "hon",
        "etc", "inc", "corp", "co", "ltd", "supp", "fed", "cir", "dist", "app",
        "art", "sec", "para", "ex", "id", "cf", "al",
    }
)


class SentenceSegmenter:
    """
    Incremental sentence segmenter for streaming text. `feed(delta)` returns any sentences that
    completed with that delta; `flush()` returns the trailing fragment at stream end. A sentence
    closes on . ! ? followed by whitespace and a non-lowercase next token — with an abbreviation
    guard for periods so citation-shaped text ("v.", "U.S.", "F. Supp.", "No. 5") never splits.
    Wrong splits are latency noise, not correctness bugs (every piece is verified either way), so
    the guard is pragmatic, not exhaustive.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        """Append a text delta; return the sentences (if any) it completed, in order."""
        self._buffer += delta
        sentences: list[str] = []
        while True:
            split = self._find_split(self._buffer)
            if split is None:
                break
            sentence = self._buffer[:split].strip()
            self._buffer = self._buffer[split:]
            if sentence:
                sentences.append(sentence)
        return sentences

    def flush(self) -> str | None:
        """Return the trailing fragment (a sentence the stream ended mid-way), if any."""
        tail = self._buffer.strip()
        self._buffer = ""
        return tail or None

    @staticmethod
    def _find_split(text: str) -> int | None:
        """Index just past the first confirmed sentence terminator, or None if none is confirmed."""
        for i, char in enumerate(text):
            if char not in _TERMINATORS:
                continue
            end = i + 1
            if end < len(text) and text[end] in _CLOSING_QUOTES:
                end += 1  # keep a closing quote with its sentence
            if end >= len(text) or not text[end].isspace():
                continue  # mid-token ("F.3d", "3.5") or still waiting for the next character
            nxt = end
            while nxt < len(text) and text[nxt].isspace():
                nxt += 1
            if nxt >= len(text):
                continue  # next token not visible yet — wait rather than guess
            if char == ".":
                if text[nxt].islower():
                    continue  # sentences don't start lowercase; likely an abbreviation
                if _ends_with_abbreviation(text, i):
                    continue
            return end
        return None


def _ends_with_abbreviation(text: str, dot_index: int) -> bool:
    """True if the token ending at text[dot_index] == '.' is an abbreviation, not a sentence end."""
    start = dot_index
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "."):
        start -= 1
    word = text[start:dot_index]
    if not word:
        return False
    last_segment = word.rsplit(".", 1)[-1]
    if len(last_segment) == 1 and last_segment.isalpha():
        return True  # initials and reporter-style tokens: "F.", "U.S.", "N.W."
    return word.lower() in _ABBREVIATIONS


def _sentences(deltas: Iterable[str]) -> Iterator[str]:
    """Segment a delta stream into complete sentences, flushing the trailing fragment at the end."""
    segmenter = SentenceSegmenter()
    for delta in deltas:
        yield from segmenter.feed(delta)
    tail = segmenter.flush()
    if tail:
        yield tail


def _verify_sentence(
    sentence: str, spoken: list[str], state: SessionState, consistency: Consistency
) -> str | None:
    """
    Verify one candidate sentence (§6.5): citation heuristic on the sentence itself, consistency
    on the accumulated verified prefix + candidate (so pronouns/ellipsis have context; the prefix
    already passed, so any new contradiction is the candidate's). Returns the failure reason, or
    None on pass. A citation hit is the same kind of failure as a contradiction — one path.
    """
    findings = verification.find_suspicious_citations(sentence)
    if findings:
        details = "; ".join(f"{f.citation} ({f.reason})" for f in findings)
        return f"suspicious citation: {details}"
    draft = " ".join([*spoken, sentence])
    contradictions = consistency(draft, state)
    if contradictions:
        return "contradicts the session record: " + "; ".join(contradictions)
    return None


def stream_verified_reply(
    state: SessionState,
    attorney_turn: str,
    *,
    generate: StreamFactory | None = None,
    repair: RepairFactory | None = None,
    consistency: Consistency | None = None,
    max_repairs: int = 1,
) -> Iterator[str]:
    """
    Stream Opposing Counsel's reply as VERIFIED sentences, ready for TTS the moment each is
    yielded. On a mid-stream verification failure: discard the failed sentence and the rest of its
    stream, request one repair continuation from the verified prefix (Option B), verify it the same
    way; if repairs are exhausted, truncate at the last verified sentence (Option A fallback).
    Fail-closed: any stream/verifier error also truncates. May yield nothing (silence over
    falsehood) if the very first sentence fails and the repair fails too.
    """
    generate = generate or opposing_counsel.stream_reply
    repair = repair or opposing_counsel.stream_continuation
    consistency = consistency or verification.check_consistency

    spoken: list[str] = []
    repairs_left = max_repairs
    stream: Iterable[str] = generate(state, attorney_turn)

    while True:
        failure: str | None = None
        try:
            for sentence in _sentences(stream):
                reason = _verify_sentence(sentence, spoken, state, consistency)
                if reason is not None:
                    failure = reason
                    break
                spoken.append(sentence)
                yield sentence
        except Exception as exc:  # fail closed — stop at the last verified sentence
            logger.warning(
                "streaming reply stopped early after %d verified sentences (%s)",
                len(spoken),
                type(exc).__name__,
            )
            return
        if failure is None:
            return  # stream finished clean
        if repairs_left <= 0:
            logger.info(
                "verification failure with no repairs left — truncating at %d sentences",
                len(spoken),
            )
            return
        repairs_left -= 1
        stream = repair(state, attorney_turn, " ".join(spoken), failure)


_DONE = object()


async def astream_verified_reply(
    state: SessionState, attorney_turn: str, **kwargs
) -> AsyncIterator[str]:
    """
    Async bridge for the voice pipeline (main.py's llm_node): runs the blocking generate/verify
    pipeline in a worker thread and yields verified sentences as they become available, keeping
    the audio event loop responsive.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _produce() -> None:
        try:
            for sentence in stream_verified_reply(state, attorney_turn, **kwargs):
                loop.call_soon_threadsafe(queue.put_nowait, sentence)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    producer = loop.run_in_executor(None, _produce)
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            yield item
    finally:
        await producer
