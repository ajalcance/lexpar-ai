/**
 * File: src/lib/types.ts
 * Purpose: Shared TypeScript types for the frontend, using the canonical project
 *   vocabulary (user / case / session / transcript / scorecard) so terms never drift
 *   between the API layer, stores, and pages.
 * Depends on: nothing (pure type declarations)
 * Related: backend/app/models/* (the DB shapes these mirror at the API boundary),
 *   docs/ARCHITECTURE.md §8 (schema), docs/DEVELOPER_GUIDELINES.md §4 (vocabulary)
 */

/** Who spoke a given transcript line during a sparring session. */
export type SpeakerRole = 'attorney' | 'opposing_counsel' | 'judge';

/** Lifecycle state of a sparring session. */
export type SessionStatus = 'in_progress' | 'completed' | 'abandoned';

/** Which LLM backend served a session's Opposing Counsel. */
export type LlmBackend = 'fireworks' | 'self_hosted';

/** An authenticated attorney. Mirrors the `users` table (minus secrets). */
export interface User {
  id: string;
  email: string;
  fullName: string | null;
  firmName: string | null;
}

/** A case an attorney is preparing to argue. Mirrors the `cases` table. */
export interface Case {
  id: string;
  userId: string;
  title: string;
  caseFacts: string;
  createdAt: string;
}

/** A single rehearsal session against the AI Opposing Counsel + Judge. */
export interface Session {
  id: string;
  caseId: string;
  userId: string;
  status: SessionStatus;
  llmBackendUsed: LlmBackend | null;
  startedAt: string;
  endedAt: string | null;
}

/** One spoken line within a session transcript. Mirrors the `transcripts` table. */
export interface Transcript {
  id: string;
  sessionId: string;
  speaker: SpeakerRole;
  content: string;
  /** True when this line interrupted the attorney (e.g. an objection). */
  wasInterruption: boolean;
  spokenAt: string;
}

/** The post-session assessment. Mirrors the `scorecards` table. */
export interface Scorecard {
  id: string;
  sessionId: string;
  overallScore: number;
  strengths: string;
  weaknesses: string;
  judgeRuling: string;
  createdAt: string;
}

/** Successful login result: a bearer token plus the authenticated user. */
export interface AuthResult {
  token: string;
  user: User;
}

/** Access credentials for joining a LiveKit room (real wiring deferred). */
export interface LiveKitAccess {
  url: string;
  token: string;
}
