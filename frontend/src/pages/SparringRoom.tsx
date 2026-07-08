/**
 * File: src/pages/SparringRoom.tsx
 * Purpose: The live sparring room. Connects to the real LiveKit room and publishes the mic
 *   (useSparringRoom), showing real connection-state, listening/speaking, and mute controls. If the
 *   connection fails or no agent joins within a few seconds it falls back to the scripted mock
 *   transcript (useSparringSession) so the app stays demoable. Objection detection/display is
 *   unchanged (Gap 3).
 * Depends on: react-router-dom, hooks/useSparringRoom, hooks/useSparringSession,
 *   components/TranscriptLine, components/ui/*
 * Related: agents/main.py (the worker that joins the same room), pages/Scorecard.tsx
 * Security notes: Renders transcript content (attorney work product) for the session only; never
 *   logged. Microphone audio is published to this session's room only.
 */

import { useNavigate, useParams } from 'react-router-dom';
import { Mic, MicOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TranscriptLine } from '@/components/TranscriptLine';
import { useSparringRoom, type ConnStatus } from '@/hooks/useSparringRoom';
import { useSparringSession } from '@/hooks/useSparringSession';

const CONNECTION_LABEL: Record<ConnStatus, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  reconnecting: 'Reconnecting…',
  disconnected: 'Disconnected',
  failed: 'Offline (demo)',
};

function connectionVariant(state: ConnStatus): 'outline' | 'secondary' | 'destructive' {
  if (state === 'connected') return 'outline';
  if (state === 'connecting' || state === 'reconnecting') return 'secondary';
  return 'destructive';
}

export function SparringRoom() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const sessionId = id ?? '';

  const { mode, connectionState, activeSpeaker, isMuted, micBlocked, toggleMute } =
    useSparringRoom(sessionId);
  const { lines } = useSparringSession(sessionId, { enabled: mode === 'fallback' });

  const isConnected = connectionState === 'connected';

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Sparring session</h1>
          <p className="text-sm text-muted-foreground">
            Argue aloud. Opposing counsel may object; the judge will rule.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Badge variant={connectionVariant(connectionState)}>
            {CONNECTION_LABEL[connectionState]}
          </Badge>
          {isConnected && (
            <Badge variant={activeSpeaker === 'opposing_counsel' ? 'destructive' : 'secondary'}>
              {activeSpeaker === 'opposing_counsel' ? 'Opposing counsel speaking' : 'Listening'}
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={toggleMute}
            disabled={!isConnected || micBlocked}
          >
            {isMuted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
            {isMuted ? 'Unmute' : 'Mute'}
          </Button>
        </div>
      </div>

      {micBlocked && (
        <p className="text-sm text-destructive">
          Microphone blocked — allow mic access in your browser to argue aloud.
        </p>
      )}

      <div className="flex flex-col gap-4 rounded-lg border bg-card/40 p-6">
        {mode === 'connecting' && (
          <p className="text-sm text-muted-foreground">Connecting to the courtroom…</p>
        )}

        {mode === 'live' && (
          <p className="text-sm text-muted-foreground">
            You're connected — argue aloud and listen for objections. The written transcript view
            arrives with the next update.
          </p>
        )}

        {mode === 'fallback' && (
          <>
            <p className="text-xs text-muted-foreground">
              Demo mode — the live agent isn't running, replaying a sample session.
            </p>
            {lines.length === 0 ? (
              <p className="text-sm text-muted-foreground">Loading sample session…</p>
            ) : (
              lines.map((line) => <TranscriptLine key={line.id} line={line} />)
            )}
          </>
        )}
      </div>

      {mode !== 'connecting' && (
        <div className="flex justify-end">
          <Button onClick={() => navigate(`/session/${sessionId}/scorecard`)}>
            End session &amp; view scorecard
          </Button>
        </div>
      )}
    </div>
  );
}
