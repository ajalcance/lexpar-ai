/**
 * File: src/lib/objectionEvent.test.ts
 * Purpose: Tests for the pure objection data-channel helpers (Gap 3) — parsing the agent's payload
 *   and mapping it onto a Transcript that TranscriptLine renders with the wasInterruption treatment.
 * Depends on: vitest, lib/objectionEvent
 */

import { describe, expect, it } from 'vitest';
import { objectionEventToLine, parseObjectionData } from '@/lib/objectionEvent';

describe('parseObjectionData', () => {
  it('parses a well-formed objection event', () => {
    const event = parseObjectionData(
      JSON.stringify({ type: 'objection', objection_type: 'leading', reason: 'tag question', timestamp: 1000 }),
    );
    expect(event).toEqual({ objectionType: 'leading', reason: 'tag question', timestamp: 1000 });
  });

  it('returns null for a non-objection message', () => {
    expect(parseObjectionData(JSON.stringify({ type: 'transcript', text: 'hi' }))).toBeNull();
  });

  it('returns null for malformed data', () => {
    expect(parseObjectionData('not json at all')).toBeNull();
  });
});

describe('objectionEventToLine', () => {
  it('maps to a wasInterruption Transcript with type + reason', () => {
    const line = objectionEventToLine(
      { objectionType: 'assumes_facts', reason: 'no foundation', timestamp: 1000 },
      'sess-1',
    );
    expect(line.speaker).toBe('opposing_counsel');
    expect(line.wasInterruption).toBe(true);
    expect(line.content).toBe('Objection — assumes facts: no foundation');
    expect(line.sessionId).toBe('sess-1');
    expect(line.id).toContain('objection-');
  });

  it('omits the reason when empty', () => {
    const line = objectionEventToLine({ objectionType: 'hearsay', reason: '', timestamp: 1000 }, 's');
    expect(line.content).toBe('Objection — hearsay.');
  });
});
