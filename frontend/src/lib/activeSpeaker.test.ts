/**
 * File: src/lib/activeSpeaker.test.ts
 * Purpose: Tests for the structural active-speaker mapping (lib/activeSpeaker.ts) — the judge
 *   participant identity wins, other remote participants read as Opposing Counsel, the local
 *   participant as the attorney.
 * Depends on: vitest, lib/activeSpeaker
 */

import { describe, expect, it } from 'vitest';
import { JUDGE_IDENTITY, mapActiveSpeaker } from '@/lib/activeSpeaker';

const judge = { isLocal: false, identity: JUDGE_IDENTITY };
const agent = { isLocal: false, identity: 'agent-AJ_abc123' };
const attorney = { isLocal: true, identity: 'user-uuid' };

describe('mapActiveSpeaker', () => {
  it('attributes the judge participant structurally (identity, not inference)', () => {
    expect(mapActiveSpeaker([judge])).toBe('judge');
  });

  it('judge wins when several speak at once (you do not talk over the judge)', () => {
    expect(mapActiveSpeaker([agent, judge])).toBe('judge');
    expect(mapActiveSpeaker([attorney, judge])).toBe('judge');
  });

  it('any other remote participant is Opposing Counsel', () => {
    expect(mapActiveSpeaker([agent])).toBe('opposing_counsel');
    expect(mapActiveSpeaker([attorney, agent])).toBe('opposing_counsel');
  });

  it('local participant alone is the attorney; silence is null', () => {
    expect(mapActiveSpeaker([attorney])).toBe('you');
    expect(mapActiveSpeaker([])).toBeNull();
  });
});
