/**
 * File: src/store/session.ts
 * Purpose: Shared UI state for the active sparring session — playback status and the
 *   transcript lines revealed so far. Drives the SparringRoom view; the timing logic that
 *   feeds it lives in hooks/useSparringSession.ts.
 * Depends on: lib/types.ts
 * Related: hooks/useSparringSession.ts (writer), pages/SparringRoom.tsx (reader)
 * Security notes: Holds transcript content (attorney work product). It is rendered in-session
 *   only — never log these lines.
 */

import { create } from 'zustand';
import type { Transcript } from '@/lib/types';

/** Playback state of the scripted (later: live) sparring session. */
export type SparringStatus = 'idle' | 'connecting' | 'playing' | 'completed';

interface SessionState {
  status: SparringStatus;
  revealedLines: Transcript[];
  setStatus: (status: SparringStatus) => void;
  revealLine: (line: Transcript) => void;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  status: 'idle',
  revealedLines: [],
  setStatus: (status) => set({ status }),
  revealLine: (line) =>
    set((state) => ({ revealedLines: [...state.revealedLines, line] })),
  reset: () => set({ status: 'idle', revealedLines: [] }),
}));
