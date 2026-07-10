/**
 * File: src/lib/rulingPhase.ts
 * Purpose: Pure state machine for the session-end "verdict" moment. Once the attorney ends the
 *   session (`ending`), the finale runs two phases — AWAITING (the judge composes the ruling, dead
 *   air) → RULING (the judge speaks it aloud) — using only signals that already exist on the client:
 *   `ending`, whether the judge is currently producing audio, and a latch that stays set once the
 *   judge has begun. Kept pure so the transitions are unit-tested without a live session.
 * Depends on: nothing
 * Related: pages/SparringRoom.tsx (owns the latch + renders the finale), components/SessionFinale.tsx
 */

export type RulingPhase = 'live' | 'awaiting' | 'ruling';

/** Latch that stays true once the judge has produced any audio during the finale (so inter-sentence
 *  pauses and the short persist tail before `end_complete` don't flip the copy back to "awaiting"). */
export function latchHasSpoken(previous: boolean, judgeAudio: boolean): boolean {
  return previous || judgeAudio;
}

/** The current finale phase. Not ending → 'live'; ending but the judge hasn't spoken yet → the
 *  dead-air 'awaiting' window; ending and the judge has begun → 'ruling'. */
export function rulingPhase(ending: boolean, hasSpoken: boolean): RulingPhase {
  if (!ending) return 'live';
  return hasSpoken ? 'ruling' : 'awaiting';
}
