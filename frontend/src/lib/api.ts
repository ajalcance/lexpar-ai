/**
 * File: src/lib/api.ts
 * Purpose: The single data-access boundary for the frontend. Every page and store reads
 *   and writes through these functions — never fetch() directly. Today they resolve
 *   in-memory mock data; swapping to the real FastAPI backend is a contained change
 *   isolated to this file, so no page needs to change.
 * Depends on: lib/mockData.ts, lib/types.ts
 * Related: backend/app/api/* (the REST routes these will call), docs/ARCHITECTURE.md §5
 * Security notes: login() is a STUB standing in for POST /api/auth/login (admin/admin while
 *   AUTH_MODE=stub). The returned token is not a real credential. When wiring the real
 *   backend, attach the bearer token to every request from here — do not scatter auth
 *   handling across pages.
 */

import {
  mockCases,
  mockScorecard,
  mockSession,
  mockTranscript,
  mockUser,
} from '@/lib/mockData';
import type {
  AuthResult,
  Case,
  LiveKitAccess,
  Scorecard,
  Session,
  Transcript,
} from '@/lib/types';

/** Simulated network latency so loading states behave like the real thing. */
const LATENCY_MS = 350;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));
}

/** Mutable in-memory copy so createCase() is reflected by later getCases() calls. */
const cases: Case[] = [...mockCases];

/**
 * Stub login. Accepts only admin/admin (matching AUTH_MODE=stub) and rejects everything
 * else. Real implementation will POST credentials to /api/auth/login.
 */
export async function login(username: string, password: string): Promise<AuthResult> {
  if (username === 'admin' && password === 'admin') {
    return delay({ token: 'stub-token-admin', user: mockUser });
  }
  throw new Error('Invalid username or password.');
}

export async function getCases(): Promise<Case[]> {
  return delay([...cases]);
}

export async function getCase(id: string): Promise<Case> {
  const found = cases.find((c) => c.id === id);
  if (!found) {
    throw new Error(`Case ${id} not found.`);
  }
  return delay(found);
}

/** Create a new case from attorney-supplied facts and append it to the in-memory list. */
export async function createCase(input: {
  title: string;
  caseFacts: string;
}): Promise<Case> {
  const created: Case = {
    id: `case-${cases.length + 1}-${Date.now()}`,
    userId: mockUser.id,
    title: input.title,
    caseFacts: input.caseFacts,
    createdAt: new Date().toISOString(),
  };
  cases.push(created);
  return delay(created);
}

/** Start a sparring session for a case. Returns the fixed mock session for now. */
export async function createSession(caseId: string): Promise<Session> {
  return delay({ ...mockSession, caseId, status: 'in_progress', endedAt: null });
}

export async function getSession(id: string): Promise<Session> {
  return delay({ ...mockSession, id });
}

/**
 * The scripted transcript the SparringRoom replays on a timer. In the real system these
 * lines stream in live from the LiveKit agents worker; here they are a fixed sequence.
 */
export async function getSessionScript(sessionId: string): Promise<Transcript[]> {
  return delay(mockTranscript.map((line) => ({ ...line, sessionId })));
}

export async function getScorecard(sessionId: string): Promise<Scorecard> {
  return delay({ ...mockScorecard, sessionId });
}

/**
 * Stub for GET /api/livekit/token. Returned values are placeholders; the scripted mock
 * session does not connect to a real room yet.
 */
export async function getLiveKitToken(sessionId: string): Promise<LiveKitAccess> {
  return delay({ url: 'ws://localhost:7880', token: `stub-livekit-${sessionId}` });
}
