/**
 * File: src/lib/mockData.ts
 * Purpose: The one remaining piece of mock data — the scripted courtroom transcript the
 *   SparringRoom replays on a timer. Everything else (auth, cases, sessions, scorecards) now
 *   comes from the real backend via lib/api.ts. This stays until the agents pipeline streams a
 *   live transcript. Exactly one line is flagged `wasInterruption` (the opposing-counsel
 *   objection) so the UI can give it a distinct treatment.
 * Depends on: lib/types.ts
 * Related: lib/api.ts (getSessionScript), agents/objection_classifier.py (its eventual replacement)
 * Security notes: Illustrative sample content only — never add real transcript content here.
 */

import type { Transcript } from '@/lib/types';

/** The hardcoded exchange SparringRoom plays back, line by line, on a timer. */
export const mockTranscript: Transcript[] = [
  {
    id: 't-1',
    sessionId: 'scripted',
    speaker: 'attorney',
    content:
      'Your Honor, the evidence will show my client acted in good faith throughout the transaction.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:05Z',
  },
  {
    id: 't-2',
    sessionId: 'scripted',
    speaker: 'opposing_counsel',
    content: 'Good faith? The record shows three missed disclosure deadlines.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:18Z',
  },
  {
    id: 't-3',
    sessionId: 'scripted',
    speaker: 'attorney',
    content:
      'Those delays were administrative, and opposing counsel was notified in writing each time—',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:31Z',
  },
  {
    id: 't-4',
    sessionId: 'scripted',
    speaker: 'opposing_counsel',
    content: 'Objection, Your Honor — counsel is testifying to facts not in evidence.',
    wasInterruption: true,
    spokenAt: '2026-07-05T16:00:36Z',
  },
  {
    id: 't-5',
    sessionId: 'scripted',
    speaker: 'judge',
    content: "Sustained. Counsel, confine yourself to what's in the record.",
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:44Z',
  },
  {
    id: 't-6',
    sessionId: 'scripted',
    speaker: 'attorney',
    content: 'Understood, Your Honor. The written notices are entered as Exhibits 4 through 6.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:58Z',
  },
  {
    id: 't-7',
    sessionId: 'scripted',
    speaker: 'opposing_counsel',
    content: 'Exhibits that postdate the deadlines they were meant to satisfy.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:01:10Z',
  },
  {
    id: 't-8',
    sessionId: 'scripted',
    speaker: 'judge',
    content: "Noted. Let's proceed to the substance of the claim.",
    wasInterruption: false,
    spokenAt: '2026-07-05T16:01:22Z',
  },
];
