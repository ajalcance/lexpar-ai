/**
 * File: src/lib/mockData.ts
 * Purpose: In-memory fixtures backing the mock API during frontend scaffolding.
 *   Kept separate from api.ts so the API module stays about the *interface*, and this
 *   file is the obvious thing to delete once a real backend is wired in.
 * Depends on: lib/types.ts
 * Related: lib/api.ts (the only consumer), docs/ARCHITECTURE.md §5 (real API this stands in for)
 * Security notes: Contains no real attorney data — illustrative sample content only.
 *   Do not add real case facts or transcripts here.
 */

import type { Case, Scorecard, Session, Transcript, User } from '@/lib/types';

/** The single stub user that `admin`/`admin` resolves to while AUTH_MODE=stub. */
export const mockUser: User = {
  id: 'user-1',
  email: 'admin@lexpar.ai',
  fullName: 'Demo Attorney',
  firmName: 'Solo Practice',
};

export const mockCases: Case[] = [
  {
    id: 'case-1',
    userId: 'user-1',
    title: 'Rivera v. Coastal Logistics',
    caseFacts:
      'Wrongful-termination claim. Plaintiff alleges retaliation after reporting safety ' +
      'violations; defendant asserts documented performance issues predating the report.',
    createdAt: '2026-06-28T14:00:00Z',
  },
  {
    id: 'case-2',
    userId: 'user-1',
    title: 'State v. Okafor',
    caseFacts:
      'Motion to suppress. Defense argues the vehicle search exceeded the scope of consent; ' +
      'the stop began as a routine equipment violation.',
    createdAt: '2026-07-02T09:30:00Z',
  },
];

export const mockSession: Session = {
  id: 'session-1',
  caseId: 'case-1',
  userId: 'user-1',
  status: 'completed',
  llmBackendUsed: 'fireworks',
  startedAt: '2026-07-05T16:00:00Z',
  endedAt: '2026-07-05T16:12:00Z',
};

/**
 * A hardcoded courtroom exchange the SparringRoom replays on a timer. Exactly one line
 * is flagged `wasInterruption` (the opposing-counsel objection) so the UI can give it a
 * distinct treatment.
 */
export const mockTranscript: Transcript[] = [
  {
    id: 't-1',
    sessionId: 'session-1',
    speaker: 'attorney',
    content:
      'Your Honor, the evidence will show my client acted in good faith throughout the transaction.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:05Z',
  },
  {
    id: 't-2',
    sessionId: 'session-1',
    speaker: 'opposing_counsel',
    content: 'Good faith? The record shows three missed disclosure deadlines.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:18Z',
  },
  {
    id: 't-3',
    sessionId: 'session-1',
    speaker: 'attorney',
    content:
      'Those delays were administrative, and opposing counsel was notified in writing each time—',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:31Z',
  },
  {
    id: 't-4',
    sessionId: 'session-1',
    speaker: 'opposing_counsel',
    content: 'Objection, Your Honor — counsel is testifying to facts not in evidence.',
    wasInterruption: true,
    spokenAt: '2026-07-05T16:00:36Z',
  },
  {
    id: 't-5',
    sessionId: 'session-1',
    speaker: 'judge',
    content: "Sustained. Counsel, confine yourself to what's in the record.",
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:44Z',
  },
  {
    id: 't-6',
    sessionId: 'session-1',
    speaker: 'attorney',
    content: 'Understood, Your Honor. The written notices are entered as Exhibits 4 through 6.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:00:58Z',
  },
  {
    id: 't-7',
    sessionId: 'session-1',
    speaker: 'opposing_counsel',
    content: 'Exhibits that postdate the deadlines they were meant to satisfy.',
    wasInterruption: false,
    spokenAt: '2026-07-05T16:01:10Z',
  },
  {
    id: 't-8',
    sessionId: 'session-1',
    speaker: 'judge',
    content: "Noted. Let's proceed to the substance of the claim.",
    wasInterruption: false,
    spokenAt: '2026-07-05T16:01:22Z',
  },
];

export const mockScorecard: Scorecard = {
  id: 'scorecard-1',
  sessionId: 'session-1',
  overallScore: 78,
  strengths:
    'Clear framing of the good-faith argument and effective use of documentary exhibits to ' +
    'anchor the narrative.',
  weaknesses:
    'Drifted into facts not yet in evidence, drawing a sustained objection. Establish the ' +
    'record before asserting conclusions from it.',
  judgeRuling:
    'The good-faith argument is viable but was undercut by an early misstep on the evidentiary ' +
    'record. With cleaner sequencing of the exhibits, this position holds up.',
  createdAt: '2026-07-05T16:12:30Z',
};
