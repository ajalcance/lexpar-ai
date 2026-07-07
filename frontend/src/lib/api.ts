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
import type { Case, LiveKitAccess, Scorecard, Session, Transcript, User } from '@/lib/types';

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
}
interface CaseJson {
  id: string;
  title: string;
  case_facts: string | null;
  created_at: string;
}
interface SessionJson {
  id: string;
  case_id: string;
  status: Session['status'];
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
  created_at: string;
}

const toUser = (j: UserJson): User => ({
  id: j.id,
  email: j.email,
  fullName: j.full_name,
  firmName: j.firm_name,
});

const toCase = (j: CaseJson): Case => ({
  id: j.id,
  title: j.title,
  caseFacts: j.case_facts ?? '',
  createdAt: j.created_at,
});

const toSession = (j: SessionJson): Session => ({
  id: j.id,
  caseId: j.case_id,
  status: j.status,
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
  createdAt: j.created_at,
});

// --- API surface ----------------------------------------------------------------------------

/** Authenticate and return the bearer token (stub backend accepts admin/admin). */
export async function login(username: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>('/api/auth/login', {
    method: 'POST',
    body: { username, password },
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

export async function createCase(input: { title: string; caseFacts: string }): Promise<Case> {
  const data = await request<CaseJson>('/api/cases', {
    method: 'POST',
    body: { title: input.title, case_facts: input.caseFacts },
  });
  return toCase(data);
}

export async function createSession(caseId: string): Promise<Session> {
  const data = await request<SessionJson>('/api/sessions', {
    method: 'POST',
    body: { case_id: caseId },
  });
  return toSession(data);
}

export async function getSession(id: string): Promise<Session> {
  return toSession(await request<SessionJson>(`/api/sessions/${id}`));
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
