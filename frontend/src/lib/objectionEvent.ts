/**
 * File: src/lib/objectionEvent.ts
 * Purpose: Pure helpers for the objection data-channel event (Gap 3) — parse the JSON the agent
 *   publishes ({type:"objection", objection_type, reason, timestamp}) and map it to a Transcript so
 *   it renders through the EXISTING TranscriptLine with the same `wasInterruption` treatment (no new
 *   component). Kept pure/livekit-free so it is unit-tested; the hook wires it to RoomEvent.DataReceived.
 * Depends on: lib/types.ts
 * Related: hooks/useSparringRoom.ts, components/TranscriptLine.tsx, agents/voice_interrupt.py
 * Security notes: Operates on live objection text (work product) for in-session render only.
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
