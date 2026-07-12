/**
 * File: src/lib/objectionEvent.ts
 * Purpose: Pure helpers for the agent's data-channel events — parse the JSON the agent publishes
 *   ({type:"objection", …} at the barge-in moment, {type:"ruling", …} when the judge rules inline)
 *   and map each to a Transcript so it renders through the EXISTING TranscriptLine (objections get
 *   the `wasInterruption` treatment; rulings render as judge lines — no new component). Kept
 *   pure/livekit-free so it is unit-tested; the hook wires it to RoomEvent.DataReceived.
 * Depends on: lib/types.ts
 * Related: hooks/useSparringRoom.ts, components/TranscriptLine.tsx, agents/voice_interrupt.py,
 *   agents/main.py (judge_rule publishes the ruling event)
 * Security notes: Operates on live objection/ruling text (work product) for in-session render only.
 */

import type { Transcript } from '@/lib/types';

export interface ObjectionEvent {
  objectionType: string | null;
  reason: string;
  timestamp: number;
}

/** Parse a data-channel payload; returns null for anything that isn't a well-formed objection event. */
export function parseObjectionData(text: string): ObjectionEvent | null {
  try {
    const data = JSON.parse(text);
    if (data?.type !== 'objection') {
      return null;
    }
    return {
      objectionType: typeof data.objection_type === 'string' ? data.objection_type : null,
      reason: typeof data.reason === 'string' ? data.reason : '',
      timestamp: typeof data.timestamp === 'number' ? data.timestamp : Date.now(),
    };
  } catch {
    return null;
  }
}

/** Map an objection event onto a Transcript so TranscriptLine renders the red "Objection" treatment. */
export function objectionEventToLine(event: ObjectionEvent, sessionId: string): Transcript {
  const typeLabel = event.objectionType ? event.objectionType.replace(/_/g, ' ') : null;
  const base = typeLabel ? `Objection — ${typeLabel}` : 'Objection';
  const content = event.reason ? `${base}: ${event.reason}` : `${base}.`;
  return {
    id: `objection-${event.timestamp}-${crypto.randomUUID()}`,
    sessionId,
    speaker: 'opposing_counsel',
    content,
    wasInterruption: true,
    spokenAt: new Date(event.timestamp).toISOString(),
  };
}

export interface RulingEvent {
  ruling: 'sustained' | 'overruled';
  reason: string;
  timestamp: number;
}

/** Parse a data-channel payload; returns null for anything that isn't a well-formed ruling event. */
export function parseRulingData(text: string): RulingEvent | null {
  try {
    const data = JSON.parse(text);
    if (data?.type !== 'ruling' || (data.ruling !== 'sustained' && data.ruling !== 'overruled')) {
      return null;
    }
    return {
      ruling: data.ruling,
      reason: typeof data.reason === 'string' ? data.reason : '',
      timestamp: typeof data.timestamp === 'number' ? data.timestamp : Date.now(),
    };
  } catch {
    return null;
  }
}

export interface TranscriptEvent {
  speaker: 'attorney' | 'opposing_counsel' | 'judge';
  content: string;
  timestamp: number;
}

const TRANSCRIPT_SPEAKERS = new Set(['attorney', 'opposing_counsel', 'judge']);

/** Parse a data-channel payload; null unless it's a well-formed transcript turn (a committed
 *  attorney statement, OC counter-argument, or the judge's order line — the live written transcript
 *  the agent publishes on top of the objection/ruling events). */
export function parseTranscriptData(text: string): TranscriptEvent | null {
  try {
    const data = JSON.parse(text);
    if (
      data?.type !== 'transcript' ||
      !TRANSCRIPT_SPEAKERS.has(data.speaker) ||
      typeof data.content !== 'string' ||
      !data.content
    ) {
      return null;
    }
    return {
      speaker: data.speaker,
      content: data.content,
      timestamp: typeof data.timestamp === 'number' ? data.timestamp : Date.now(),
    };
  } catch {
    return null;
  }
}

/** Map a transcript event onto a Transcript line (ordinary speaker styling — no interruption). */
export function transcriptEventToLine(event: TranscriptEvent, sessionId: string): Transcript {
  return {
    id: `transcript-${event.speaker}-${event.timestamp}-${crypto.randomUUID()}`,
    sessionId,
    speaker: event.speaker,
    content: event.content,
    wasInterruption: false,
    spokenAt: new Date(event.timestamp).toISOString(),
  };
}

/** Insert a line into a spokenAt-ordered list (stable: equal timestamps go AFTER existing lines).
 *  The live view orders by WHEN things were said, not when packets arrived — attorney turns are
 *  timestamped at speech START but published at turn END, so arrival order showed an objection
 *  above the statement it interrupted and a cancelled OC reply above the attorney's own words.
 *  Ordering by spokenAt makes the live view read exactly like the saved report. */
export function insertByTime(lines: Transcript[], line: Transcript): Transcript[] {
  const at = Date.parse(line.spokenAt);
  let i = lines.length;
  while (i > 0 && Date.parse(lines[i - 1].spokenAt) > at) {
    i -= 1;
  }
  return [...lines.slice(0, i), line, ...lines.slice(i)];
}

/** Parse a "judge_speaking" boundary event → true/false, or null if it isn't one. The judge shares
 *  the Opposing-Counsel agent participant, so this is how the UI knows to label audio as the Judge. */
export function parseJudgeSpeaking(text: string): boolean | null {
  try {
    const data = JSON.parse(text);
    if (data?.type !== 'judge_speaking' || typeof data.speaking !== 'boolean') {
      return null;
    }
    return data.speaking;
  } catch {
    return null;
  }
}

/** Map an inline ruling onto a Transcript so TranscriptLine renders it as a judge line. */
export function rulingEventToLine(event: RulingEvent, sessionId: string): Transcript {
  const label = event.ruling.charAt(0).toUpperCase() + event.ruling.slice(1);
  const content = event.reason ? `${label}. ${event.reason}` : `${label}.`;
  return {
    id: `ruling-${event.timestamp}-${crypto.randomUUID()}`,
    sessionId,
    speaker: 'judge',
    content,
    wasInterruption: false,
    spokenAt: new Date(event.timestamp).toISOString(),
  };
}
