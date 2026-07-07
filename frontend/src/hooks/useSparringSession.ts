/**
 * File: src/hooks/useSparringSession.ts
 * Purpose: Drives the scripted mock sparring session — loads the transcript for a session
 *   and reveals its lines one at a time on a timer, updating the session store. Keeping this
 *   logic in a hook (not the component) matches DEVELOPER_GUIDELINES §11: components stay
 *   presentational.
 * Depends on: lib/api.ts (getSessionScript), store/session.ts
 * Related: pages/SparringRoom.tsx (consumer)
 * Security notes: Transcript lines are attorney work product; this hook only moves them into
 *   in-memory UI state and never logs them.
 */

import { useEffect } from 'react';
import * as api from '@/lib/api';
import { useSessionStore } from '@/store/session';

/** Delay between revealed transcript lines, in milliseconds. */
const LINE_INTERVAL_MS = 1600;

/**
 * Replays the scripted transcript for `sessionId`. Returns the current playback status and
 * the lines revealed so far (both sourced from the session store).
 */
export function useSparringSession(sessionId: string) {
  const status = useSessionStore((state) => state.status);
  const lines = useSessionStore((state) => state.revealedLines);
  const setStatus = useSessionStore((state) => state.setStatus);
  const revealLine = useSessionStore((state) => state.revealLine);
  const reset = useSessionStore((state) => state.reset);

  useEffect(() => {
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];

    reset();
    setStatus('connecting');

    api.getSessionScript(sessionId).then((script) => {
      if (cancelled) {
        return;
      }
      setStatus('playing');
      script.forEach((line, index) => {
        const timer = setTimeout(() => {
          revealLine(line);
          if (index === script.length - 1) {
            setStatus('completed');
          }
        }, index * LINE_INTERVAL_MS);
        timers.push(timer);
      });
    });

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [sessionId, reset, setStatus, revealLine]);

  return { status, lines };
}
