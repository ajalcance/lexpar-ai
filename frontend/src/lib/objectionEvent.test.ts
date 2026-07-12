/**
 * File: src/lib/objectionEvent.test.ts
 * Purpose: Tests for the pure objection data-channel helpers (Gap 3) — parsing the agent's payload
 *   and mapping it onto a Transcript that TranscriptLine renders with the wasInterruption treatment.
 * Depends on: vitest, lib/objectionEvent
 */

import { describe, expect, it } from 'vitest';
import {
  insertByTime,
  objectionEventToLine,
  parseJudgeSpeaking,
  parseMatterData,
  parseObjectionData,
  parseOcThinking,
  parseRulingData,
  parseTranscriptData,
  rulingEventToLine,
  transcriptEventToLine,
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

describe('parseMatterData', () => {
  it('parses a matter event', () => {
    expect(
      parseMatterData('{"type": "matter", "matter": "Whether the third-party mortgage is void."}'),
    ).toBe('Whether the third-party mortgage is void.');
  });

  it('returns null for other events / empty / malformed', () => {
    expect(parseMatterData('{"type": "transcript", "speaker": "judge", "content": "x"}')).toBeNull();
    expect(parseMatterData('{"type": "matter", "matter": ""}')).toBeNull();
    expect(parseMatterData('{"type": "matter"}')).toBeNull();
    expect(parseMatterData('not json')).toBeNull();
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

describe('parseTranscriptData', () => {
  it('parses a well-formed transcript turn', () => {
    const turn = parseTranscriptData(
      JSON.stringify({
        type: 'transcript',
        speaker: 'attorney',
        content: 'The mortgage is void ab initio.',
        timestamp: 4200,
      }),
    );
    expect(turn).toEqual({
      speaker: 'attorney',
      content: 'The mortgage is void ab initio.',
      timestamp: 4200,
    });
  });

  it('accepts all three speakers, rejects unknown speakers and empty content', () => {
    for (const speaker of ['attorney', 'opposing_counsel', 'judge']) {
      expect(
        parseTranscriptData(JSON.stringify({ type: 'transcript', speaker, content: 'x' }))?.speaker,
      ).toBe(speaker);
    }
    expect(
      parseTranscriptData(JSON.stringify({ type: 'transcript', speaker: 'witness', content: 'x' })),
    ).toBeNull();
    expect(
      parseTranscriptData(JSON.stringify({ type: 'transcript', speaker: 'attorney', content: '' })),
    ).toBeNull();
  });

  it('is not mistaken for an objection, ruling, or judge_speaking event (and vice versa)', () => {
    const payload = JSON.stringify({ type: 'transcript', speaker: 'judge', content: 'Order.' });
    expect(parseObjectionData(payload)).toBeNull();
    expect(parseRulingData(payload)).toBeNull();
    expect(parseJudgeSpeaking(payload)).toBeNull();
    // and a real objection/ruling is not read as a transcript turn
    expect(parseTranscriptData('{"type": "objection", "objection_type": "leading"}')).toBeNull();
    expect(parseTranscriptData('{"type": "ruling", "ruling": "sustained"}')).toBeNull();
  });

  it('maps a transcript event onto an ordinary (non-interruption) line', () => {
    const line = transcriptEventToLine(
      { speaker: 'opposing_counsel', content: 'The record does not support that.', timestamp: 900 },
      'session-1',
    );
    expect(line.speaker).toBe('opposing_counsel');
    expect(line.wasInterruption).toBe(false);
    expect(line.content).toBe('The record does not support that.');
    expect(line.sessionId).toBe('session-1');
  });
});

describe('insertByTime', () => {
  const line = (id: string, iso: string): import('@/lib/types').Transcript => ({
    id,
    sessionId: 's',
    speaker: 'attorney',
    content: id,
    wasInterruption: false,
    spokenAt: iso,
  });

  it('appends when newest (the common case)', () => {
    const out = insertByTime([line('a', '2026-07-12T00:00:01Z')], line('b', '2026-07-12T00:00:02Z'));
    expect(out.map((l) => l.id)).toEqual(['a', 'b']);
  });

  it('inserts an earlier-spoken line above later ones (attorney turn committed after an objection)', () => {
    // objection fired mid-statement (t=5), attorney turn committed later but STARTED at t=3
    const objection = line('objection', '2026-07-12T00:00:05Z');
    const out = insertByTime([objection], line('statement', '2026-07-12T00:00:03Z'));
    expect(out.map((l) => l.id)).toEqual(['statement', 'objection']);
  });

  it('is stable: equal timestamps keep arrival order', () => {
    const out = insertByTime([line('first', '2026-07-12T00:00:04Z')], line('second', '2026-07-12T00:00:04Z'));
    expect(out.map((l) => l.id)).toEqual(['first', 'second']);
  });
});

describe('parseOcThinking', () => {
  it('parses an oc_thinking boundary', () => {
    expect(parseOcThinking('{"type": "oc_thinking", "thinking": true}')).toBe(true);
    expect(parseOcThinking('{"type": "oc_thinking", "thinking": false}')).toBe(false);
  });

  it('returns null for other events / malformed, and is not confused with judge_speaking', () => {
    expect(parseOcThinking('{"type": "judge_speaking", "speaking": true}')).toBeNull();
    expect(parseOcThinking('{"type": "oc_thinking"}')).toBeNull(); // no boolean
    expect(parseOcThinking('not json')).toBeNull();
    expect(parseJudgeSpeaking('{"type": "oc_thinking", "thinking": true}')).toBeNull();
  });
});
