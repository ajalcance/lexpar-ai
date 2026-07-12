/**
 * File: src/lib/types.ts
 * Purpose: Shared TypeScript types for the frontend, using the canonical project
 *   vocabulary (user / case / session / transcript / scorecard) so terms never drift
 *   between the API layer, stores, and pages. Also the proceeding-type display labels
 *   (the one value export — kept here so the taxonomy and its labels stay together).
 * Depends on: nothing (type declarations + one label map)
 * Related: backend/app/models/* (the DB shapes these mirror at the API boundary),
 *   docs/ARCHITECTURE.md §8 (schema), docs/DEVELOPER_GUIDELINES.md §4 (vocabulary)
 */

/** Who spoke a given transcript line during a sparring session. */
export type SpeakerRole = 'attorney' | 'opposing_counsel' | 'judge';

/** Lifecycle state of a sparring session. */
export type SessionStatus = 'in_progress' | 'completed' | 'abandoned';

/** Which LLM backend served a session's Opposing Counsel. */
export type LlmBackend = 'fireworks' | 'self_hosted';

/** Which kind of proceeding a session rehearses (§13) — drives eligible objection grounds.
 *  Mirrors backend PROCEEDING_TYPES (app/models/session.py). */
export type ProceedingType =
  | 'oral_argument'
  | 'direct_examination'
  | 'cross_examination'
  | 'motion_hearing';

/** Display labels for the proceeding-type selector. */
export const PROCEEDING_TYPE_LABELS: Record<ProceedingType, string> = {
  oral_argument: 'Oral argument',
  direct_examination: 'Direct examination',
  cross_examination: 'Cross-examination',
  motion_hearing: 'Motion hearing',
};

/** An authenticated attorney. Mirrors the `users` table (minus secrets). */
export interface User {
  id: string;
  email: string;
  fullName: string | null;
  firmName: string | null;
  /** 'attorney' | 'admin' (§13) — gates the admin UI; the backend enforces the real check. */
  role: 'attorney' | 'admin';
}

/** A case an attorney is preparing to argue. Mirrors the `cases` table (API-visible fields). */
export interface Case {
  id: string;
  title: string;
  caseFacts: string;
  /** The forum whose procedural rules ground this case's sessions (§13). Null on pre-§13 cases. */
  courtId: string | null;
  createdAt: string;
}

/** A court in the catalog (§13) — the forum whose rules ground a case. */
export interface Court {
  id: string;
  name: string;
  jurisdictionDescription: string | null;
  isActive: boolean;
}

/** Ingestion status of an admin-uploaded court rule document (§13). */
export interface CourtRuleDocument {
  id: string;
  title: string;
  sourceCitation: string | null;
  sourceReference: string | null;
  ingestionStatus: 'pending' | 'ready' | 'failed';
  chunkCount: number;
  error: string | null;
  /** Two-tier deletion state: archived = excluded from retrieval (soft, restorable unless
   *  superseded); superseded = archived because a Replace uploaded a newer version. */
  archived: boolean;
  superseded: boolean;
}

/** §13 audit trail for one AI ruling — which sources it was shown, which citations flagged. */
export interface ProvenanceRecord {
  id: string;
  rulingType: 'objection_ruling' | 'final_ruling';
  chunkIdsUsed: string[];
  citationFlags: string[];
  createdAt: string;
}

/** A single rehearsal session against the AI Opposing Counsel + Judge. */
export interface Session {
  id: string;
  caseId: string;
  status: SessionStatus;
  proceedingType: ProceedingType;
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

/** One rubric dimension of the judge's performance breakdown (name + 0-100 sub-score). */
export interface ScoreCriterion {
  name: string;
  score: number;
}

/** The post-session assessment. Mirrors the `scorecards` table. */
export interface Scorecard {
  id: string;
  sessionId: string;
  overallScore: number;
  strengths: string;
  weaknesses: string;
  judgeRuling: string;
  /** Per-dimension rubric breakdown; empty when the judge gave no breakdown. */
  criteria: ScoreCriterion[];
  createdAt: string;
}

/** Access credentials for joining a LiveKit room. */
export interface LiveKitAccess {
  url: string;
  token: string;
}
