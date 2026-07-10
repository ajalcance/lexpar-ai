/**
 * File: src/lib/rulingPhase.test.ts
 * Purpose: Tests for the session-finale state machine — the hasSpoken latch (stays set once the
 *   judge has produced audio, so pauses/persist-tail don't flip back) and the derived phase
 *   (live → awaiting → ruling). Pure logic; the live audio-reactive feel needs a live session.
 * Depends on: vitest, lib/rulingPhase
 */

import { describe, expect, it } from 'vitest';
import { latchHasSpoken, rulingPhase } from '@/lib/rulingPhase';

describe('latchHasSpoken', () => {
  it('sets on the first judge audio', () => {
    expect(latchHasSpoken(false, true)).toBe(true);
  });

  it('stays set once true, even when the judge pauses (audio drops)', () => {
    expect(latchHasSpoken(true, false)).toBe(true);
  });

  it('stays false while there is no judge audio yet', () => {
    expect(latchHasSpoken(false, false)).toBe(false);
  });
});

describe('rulingPhase', () => {
  it('is live before the session is ended', () => {
    expect(rulingPhase(false, false)).toBe('live');
    expect(rulingPhase(false, true)).toBe('live');
  });

  it('is awaiting once ended but before the judge has spoken (dead air)', () => {
    expect(rulingPhase(true, false)).toBe('awaiting');
  });

  it('is ruling once ended and the judge has begun', () => {
    expect(rulingPhase(true, true)).toBe('ruling');
  });
});
