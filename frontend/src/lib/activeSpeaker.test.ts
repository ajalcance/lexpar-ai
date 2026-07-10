/**
 * File: src/lib/activeSpeaker.test.ts
 * Purpose: Tests for the structural active-speaker mapping (lib/activeSpeaker.ts) — the judge
 *   participant identity wins, other remote participants read as Opposing Counsel, the local
 *   participant as the attorney.
 * Depends on: vitest, lib/activeSpeaker
 */

import { describe, expect, it } from 'vitest';
import { JUDGE_IDENTITY, mapActiveSpeaker, mapAudioLevels } from '@/lib/activeSpeaker';

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

describe('mapAudioLevels', () => {
  it('routes each participant audioLevel to its role; absent roles stay 0', () => {
    const levels = mapAudioLevels([
      { ...attorney, audioLevel: 0.7 },
      { ...judge, audioLevel: 0.4 },
    ]);
    expect(levels).toEqual({ you: 0.7, opposing_counsel: 0, judge: 0.4 });
  });

  it('treats any non-judge remote as Opposing Counsel and keeps the loudest of duplicates', () => {
    const levels = mapAudioLevels([
      { ...agent, audioLevel: 0.3 },
      { isLocal: false, identity: 'agent-other', audioLevel: 0.9 },
    ]);
    expect(levels.opposing_counsel).toBe(0.9);
    expect(levels.you).toBe(0);
    expect(levels.judge).toBe(0);
  });

  it('is all zeros when no one is speaking', () => {
    expect(mapAudioLevels([])).toEqual({ you: 0, opposing_counsel: 0, judge: 0 });
  });
});
