/**
 * File: src/lib/objectionEvent.test.ts
 * Purpose: Tests for the pure objection data-channel helpers (Gap 3) — parsing the agent's payload
 *   and mapping it onto a Transcript that TranscriptLine renders with the wasInterruption treatment.
 * Depends on: vitest, lib/objectionEvent
 */

import { describe, expect, it } from 'vitest';
import {
  objectionEventToLine,
  parseJudgeSpeaking,
  parseObjectionData,
  parseRulingData,
  rulingEventToLine,
} from '@/lib/objectionEvent';

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

describe('parseRulingData', () => {
  it('parses a well-formed ruling event', () => {
    const event = parseRulingData(
      '{"type": "ruling", "ruling": "sustained", "reason": "hearsay", "timestamp": 1710}',
    );
    expect(event).toEqual({ ruling: 'sustained', reason: 'hearsay', timestamp: 1710 });
  });

  it('rejects unknown ruling values and other event types', () => {
    expect(parseRulingData('{"type": "ruling", "ruling": "maybe"}')).toBeNull();
    expect(parseRulingData('{"type": "objection", "objection_type": "hearsay"}')).toBeNull();
    expect(parseRulingData('not json')).toBeNull();
  });
});

describe('rulingEventToLine', () => {
  it('maps to a judge Transcript line with the reason', () => {
    const line = rulingEventToLine(
      { ruling: 'overruled', reason: 'goes to weight', timestamp: 1710 },
      'sess-1',
    );
    expect(line.speaker).toBe('judge');
    expect(line.wasInterruption).toBe(false);
    expect(line.content).toBe('Overruled. goes to weight');
    expect(line.sessionId).toBe('sess-1');
  });

  it('omits the reason when empty', () => {
    const line = rulingEventToLine({ ruling: 'sustained', reason: '', timestamp: 1710 }, 's');
    expect(line.content).toBe('Sustained.');
  });
});

describe('parseJudgeSpeaking', () => {
  it('parses a judge_speaking boundary', () => {
    expect(parseJudgeSpeaking('{"type": "judge_speaking", "speaking": true}')).toBe(true);
    expect(parseJudgeSpeaking('{"type": "judge_speaking", "speaking": false}')).toBe(false);
  });

  it('returns null for other events / malformed', () => {
    expect(parseJudgeSpeaking('{"type": "ruling", "ruling": "sustained"}')).toBeNull();
    expect(parseJudgeSpeaking('{"type": "judge_speaking"}')).toBeNull(); // no boolean
    expect(parseJudgeSpeaking('not json')).toBeNull();
  });

  it('is not mistaken for an objection or ruling line', () => {
    const payload = '{"type": "judge_speaking", "speaking": true}';
    expect(parseObjectionData(payload)).toBeNull();
    expect(parseRulingData(payload)).toBeNull();
  });
});
