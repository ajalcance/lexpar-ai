/**
 * File: src/lib/api.ts
 * Purpose: The single data-access boundary for the frontend. Every page and store goes through
 *   these functions — never fetch() directly. They call the real FastAPI backend, attach the
 *   bearer token from the auth store, and map the API's snake_case JSON onto the camelCase
 *   frontend types so components don't change shape.
 * Depends on: store/auth.ts (token), lib/types.ts, lib/mockData.ts (scripted transcript only)
 * Related: backend/app/api/* (the REST routes), docs/ARCHITECTURE.md §5
 * Security notes: The bearer token is read from the in-memory auth store and sent only to the
 *   configured API base URL. On a 401 the store is cleared so the guard redirects to /login.
 *   Never log request/response bodies (they carry credentials and work product).
 */

import { mockTranscript } from '@/lib/mockData';
import { useAuthStore } from '@/store/auth';
import type {
  Case,
  Court,
  CourtRuleDocument,
  LiveKitAccess,
  ProceedingType,
  ProvenanceRecord,
  Scorecard,
  Session,
  Transcript,
  User,
} from '@/lib/types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** Error carrying the HTTP status so callers (e.g. Scorecard) can branch on 404/409. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Skip attaching the bearer token (used by login, which has no token yet). */
  anonymous?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, anonymous = false } = options;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  if (!anonymous) {
    const token = useAuthStore.getState().token;
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401) {
    // Stale/invalid token — clear auth so ProtectedRoute redirects to /login.
    useAuthStore.getState().logout();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }

  if (!response.ok) {
    throw new ApiError(await extractError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Pull FastAPI's `{ detail }` message when present, else fall back to the status text. */
async function extractError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === 'string') {
      return data.detail;
    }
  } catch {
    // non-JSON body — ignore
  }
  return response.statusText || 'Request failed';
}

// --- Response mappers (API snake_case -> frontend camelCase) --------------------------------

interface UserJson {
  id: string;
  email: string;
  full_name: string | null;
  firm_name: string | null;
  role: User['role'];
}
interface CaseJson {
  id: string;
  title: string;
  case_facts: string | null;
  court_id: string | null;
  created_at: string;
}
interface CourtJson {
  id: string;
  name: string;
  jurisdiction_description: string | null;
  is_active: boolean;
}
interface CourtRuleDocumentJson {
  id: string;
  title: string;
  source_citation: string | null;
  source_reference: string | null;
  ingestion_status: CourtRuleDocument['ingestionStatus'];
  chunk_count: number;
  error: string | null;
  archived: boolean;
  superseded: boolean;
}
interface ProvenanceJson {
  id: string;
  ruling_type: ProvenanceRecord['rulingType'];
  chunk_ids_used: string[];
  citation_flags: string[];
  created_at: string;
}
interface SessionJson {
  id: string;
  case_id: string;
  status: Session['status'];
  proceeding_type: Session['proceedingType'];
  llm_backend_used: Session['llmBackendUsed'];
  started_at: string;
  ended_at: string | null;
}
interface ScorecardJson {
  id: string;
  session_id: string;
  overall_score: number | null;
  strengths: string | null;
  weaknesses: string | null;
  judge_ruling: string | null;
  criteria: { name: string; score: number }[] | null;
  created_at: string;
}
interface TranscriptJson {
  id: string;
  speaker: Transcript['speaker'];
  content: string;
  was_interruption: boolean;
  spoken_at: string;
}
interface SessionDetailJson extends SessionJson {
  transcripts: TranscriptJson[];
}

const toUser = (j: UserJson): User => ({
  id: j.id,
  email: j.email,
  fullName: j.full_name,
  firmName: j.firm_name,
  role: j.role ?? 'attorney',
});

const toCase = (j: CaseJson): Case => ({
  id: j.id,
  title: j.title,
  caseFacts: j.case_facts ?? '',
  courtId: j.court_id,
  createdAt: j.created_at,
});

const toCourt = (j: CourtJson): Court => ({
  id: j.id,
  name: j.name,
  jurisdictionDescription: j.jurisdiction_description,
  isActive: j.is_active,
});

const toCourtRuleDocument = (j: CourtRuleDocumentJson): CourtRuleDocument => ({
  id: j.id,
  title: j.title,
  sourceCitation: j.source_citation,
  sourceReference: j.source_reference,
  ingestionStatus: j.ingestion_status,
  chunkCount: j.chunk_count,
  error: j.error,
  archived: j.archived ?? false,
  superseded: j.superseded ?? false,
});

const toSession = (j: SessionJson): Session => ({
  id: j.id,
  caseId: j.case_id,
  status: j.status,
  proceedingType: j.proceeding_type,
  llmBackendUsed: j.llm_backend_used,
  startedAt: j.started_at,
  endedAt: j.ended_at,
});

const toScorecard = (j: ScorecardJson): Scorecard => ({
  id: j.id,
  sessionId: j.session_id,
  overallScore: j.overall_score ?? 0,
  strengths: j.strengths ?? '',
  weaknesses: j.weaknesses ?? '',
  judgeRuling: j.judge_ruling ?? '',
  criteria: j.criteria ?? [],
  createdAt: j.created_at,
});

// --- API surface ----------------------------------------------------------------------------

/** Authenticate with email + password and return the bearer token. The backend's login field is
 *  named `username` but carries the email (auth is email-based). */
export async function login(email: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>('/api/auth/login', {
    method: 'POST',
    body: { username: email, password },
    anonymous: true,
  });
  return data.access_token;
}

/** Fetch the authenticated user (GET /api/auth/me) — used to validate the session. */
export async function getCurrentUser(): Promise<User> {
  return toUser(await request<UserJson>('/api/auth/me'));
}

export async function getCases(): Promise<Case[]> {
  const data = await request<CaseJson[]>('/api/cases');
  return data.map(toCase);
}

export async function getCase(id: string): Promise<Case> {
  return toCase(await request<CaseJson>(`/api/cases/${id}`));
}

export async function createCase(input: {
  title: string;
  caseFacts: string;
  courtId?: string | null;
}): Promise<Case> {
  const data = await request<CaseJson>('/api/cases', {
    method: 'POST',
    body: {
      title: input.title,
      case_facts: input.caseFacts,
      ...(input.courtId ? { court_id: input.courtId } : {}),
    },
  });
  return toCase(data);
}

/** The active-court catalog (§13) — feeds the case-creation Court selector. */
export async function getCourts(): Promise<Court[]> {
  const data = await request<CourtJson[]>('/api/courts');
  return data.map(toCourt);
}

/** Create a court (admin only — the backend enforces the role). */
export async function createCourt(input: {
  name: string;
  jurisdictionDescription?: string;
}): Promise<Court> {
  const data = await request<CourtJson>('/api/courts', {
    method: 'POST',
    body: {
      name: input.name,
      ...(input.jurisdictionDescription
        ? { jurisdiction_description: input.jurisdictionDescription }
        : {}),
    },
  });
  return toCourt(data);
}

/** Rule-document ingestion statuses for a court (admin only). */
export async function getCourtRules(courtId: string): Promise<CourtRuleDocument[]> {
  const data = await request<CourtRuleDocumentJson[]>(`/api/courts/${courtId}/rules`);
  return data.map(toCourtRuleDocument);
}

/** Upload an OFFICIAL rule document PDF for a court (admin only; multipart — its own path,
 *  not the JSON `request` helper). Provenance fields record where the operator says it's from. */
export async function uploadCourtRule(
  courtId: string,
  file: File,
  meta: { title?: string; sourceCitation?: string; sourceReference?: string } = {},
): Promise<CourtRuleDocument> {
  const form = new FormData();
  form.append('file', file);
  if (meta.title) form.append('title', meta.title);
  if (meta.sourceCitation) form.append('source_citation', meta.sourceCitation);
  if (meta.sourceReference) form.append('source_reference', meta.sourceReference);
  const token = useAuthStore.getState().token;
  const response = await fetch(`${API_BASE_URL}/api/courts/${courtId}/rules`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) {
    throw new ApiError(await extractError(response), response.status);
  }
  return toCourtRuleDocument((await response.json()) as CourtRuleDocumentJson);
}

// --- Two-tier deletion (archive/replace vs purge, §13) ---------------------------------------

/** Replace a rule document with a corrected/newer version (atomic supersede: the old version
 *  stays in retrieval until the new one ingests to 'ready'). Admin only. */
export async function replaceCourtRule(
  courtId: string,
  documentId: string,
  file: File,
): Promise<CourtRuleDocument> {
  const form = new FormData();
  form.append('file', file);
  const token = useAuthStore.getState().token;
  const response = await fetch(
    `${API_BASE_URL}/api/courts/${courtId}/rules/${documentId}/replace`,
    { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form },
  );
  if (!response.ok) {
    throw new ApiError(await extractError(response), response.status);
  }
  return toCourtRuleDocument((await response.json()) as CourtRuleDocumentJson);
}

/** Archive (soft, reversible): exclude a rule document from retrieval; rows + file kept. */
export async function archiveCourtRule(
  courtId: string,
  documentId: string,
): Promise<CourtRuleDocument> {
  const data = await request<CourtRuleDocumentJson>(
    `/api/courts/${courtId}/rules/${documentId}`,
    { method: 'DELETE' },
  );
  return toCourtRuleDocument(data);
}

/** Undo an archive (refused with 409 while a live replacement supersedes it). */
export async function restoreCourtRule(
  courtId: string,
  documentId: string,
): Promise<CourtRuleDocument> {
  const data = await request<CourtRuleDocumentJson>(
    `/api/courts/${courtId}/rules/${documentId}/restore`,
    { method: 'POST' },
  );
  return toCourtRuleDocument(data);
}

/** The loud pre-purge warning: how many past rulings cite this document's chunks. */
export async function getCourtRulePurgeImpact(
  courtId: string,
  documentId: string,
): Promise<{ provenanceRulings: number; chunkCount: number }> {
  const data = await request<{ provenance_rulings: number; chunk_count: number }>(
    `/api/courts/${courtId}/rules/${documentId}/impact`,
  );
  return { provenanceRulings: data.provenance_rulings, chunkCount: data.chunk_count };
}

/** PURGE (hard, irreversible, admin): delete the document, its chunks, and the stored file. */
export async function purgeCourtRule(courtId: string, documentId: string): Promise<void> {
  await request<void>(`/api/courts/${courtId}/rules/${documentId}/purge`, { method: 'POST' });
}

/** Archive a court (soft): retires the forum + its corpus; referencing cases keep running. */
export async function archiveCourt(courtId: string): Promise<void> {
  await request<unknown>(`/api/courts/${courtId}/archive`, { method: 'POST' });
}

/** PURGE a court (hard; 409 while any case references it). */
export async function purgeCourt(courtId: string): Promise<void> {
  await request<void>(`/api/courts/${courtId}/purge`, { method: 'POST' });
}

/** Archive a case (soft, owner action): hidden from lists; sessions/scorecards kept. */
export async function archiveCase(caseId: string): Promise<void> {
  await request<void>(`/api/cases/${caseId}`, { method: 'DELETE' });
}

/** PURGE a case (hard, admin): the case and everything under it, gone. */
export async function purgeCase(caseId: string): Promise<void> {
  await request<void>(`/api/cases/${caseId}/purge`, { method: 'POST' });
}

/** The §13 ruling-provenance audit trail for a session (owner-scoped) — which sources each AI
 *  ruling was grounded in, and any citations flagged as ungrounded. */
export async function getSessionProvenance(sessionId: string): Promise<ProvenanceRecord[]> {
  const data = await request<ProvenanceJson[]>(`/api/sessions/${sessionId}/provenance`);
  return data.map((j) => ({
    id: j.id,
    rulingType: j.ruling_type,
    chunkIdsUsed: j.chunk_ids_used,
    citationFlags: j.citation_flags,
    createdAt: j.created_at,
  }));
}

export interface PleadingStatus {
  id: string;
  filename: string;
  status: 'pending' | 'ready' | 'failed';
  chunkCount: number;
  error: string | null;
}

interface PleadingJson {
  id: string;
  filename: string;
  status: PleadingStatus['status'];
  chunk_count: number;
  error: string | null;
}

const toPleading = (p: PleadingJson): PleadingStatus => ({
  id: p.id,
  filename: p.filename,
  status: p.status,
  chunkCount: p.chunk_count,
  error: p.error,
});

/** Upload a pleading PDF to a case (multipart — its own path, not the JSON `request` helper). */
export async function uploadPleading(caseId: string, file: File): Promise<PleadingStatus> {
  const form = new FormData();
  form.append('file', file);
  const token = useAuthStore.getState().token;
  const response = await fetch(`${API_BASE_URL}/api/cases/${caseId}/documents`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) {
    throw new ApiError(await extractError(response), response.status);
  }
  return toPleading((await response.json()) as PleadingJson);
}

export async function listPleadings(caseId: string): Promise<PleadingStatus[]> {
  const data = await request<PleadingJson[]>(`/api/cases/${caseId}/documents`);
  return data.map(toPleading);
}

/** Start a session. `proceedingType` is required (§13) — it drives which objection grounds the
 *  AI opposing counsel may raise. */
export async function createSession(
  caseId: string,
  proceedingType: ProceedingType,
): Promise<Session> {
  const data = await request<SessionJson>('/api/sessions', {
    method: 'POST',
    body: { case_id: caseId, proceeding_type: proceedingType },
  });
  return toSession(data);
}

export async function getSession(id: string): Promise<Session> {
  return toSession(await request<SessionJson>(`/api/sessions/${id}`));
}

/** A case's rehearsal history — its sessions, newest first (GET /api/cases/{id}/sessions). */
export async function getCaseSessions(caseId: string): Promise<Session[]> {
  const data = await request<SessionJson[]>(`/api/cases/${caseId}/sessions`);
  return data.map(toSession);
}

/** The session's real persisted transcript (attorney / opposing counsel / judge lines). */
export async function getSessionTranscript(id: string): Promise<Transcript[]> {
  const data = await request<SessionDetailJson>(`/api/sessions/${id}`);
  return data.transcripts.map((t) => ({
    id: t.id,
    sessionId: id,
    speaker: t.speaker,
    content: t.content,
    wasInterruption: t.was_interruption,
    spokenAt: t.spoken_at,
  }));
}

export async function getScorecard(sessionId: string): Promise<Scorecard> {
  return toScorecard(await request<ScorecardJson>(`/api/sessions/${sessionId}/scorecard`));
}

export async function getLiveKitToken(sessionId: string): Promise<LiveKitAccess> {
  return request<LiveKitAccess>(`/api/livekit/token?session_id=${sessionId}`);
}

/**
 * The scripted transcript SparringRoom replays. Still mocked — there is no agents pipeline
 * producing a live transcript yet (ARCHITECTURE §4 "Wiring status").
 */
export async function getSessionScript(sessionId: string): Promise<Transcript[]> {
  return Promise.resolve(mockTranscript.map((line) => ({ ...line, sessionId })));
}
