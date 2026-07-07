/**
 * File: src/pages/SparringRoom.tsx
 * Purpose: The live sparring room. For this scaffold it replays a scripted transcript on a
 *   timer (via useSparringSession); the objection line renders with a distinct treatment.
 *   When the script finishes, the attorney can end the session and view the scorecard.
 * Depends on: react-router-dom, hooks/useSparringSession, components/TranscriptLine,
 *   components/ui/*
 * Related: agents/* (the real voice pipeline that will replace the script), pages/Scorecard.tsx
 * Security notes: Renders transcript content (attorney work product) for the session only;
 *   never logged.
 */

import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TranscriptLine } from '@/components/TranscriptLine';
import { useSparringSession } from '@/hooks/useSparringSession';
import * as api from '@/lib/api';

const STATUS_LABEL = {
  idle: 'Idle',
  connecting: 'Connecting…',
  playing: 'Live',
  completed: 'Session ended',
} as const;

export function SparringRoom() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const sessionId = id ?? '';
  const { status, lines } = useSparringSession(sessionId);

  // Real backend plumbing: fetch a LiveKit room token for this session on load. The scripted
  // transcript above is still mock (no agents pipeline yet), but this exercises the token route.
  const { isSuccess: roomReady } = useQuery({
    queryKey: ['livekit-token', sessionId],
    queryFn: () => api.getLiveKitToken(sessionId),
    enabled: !!sessionId,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Sparring session</h1>
          <p className="text-sm text-muted-foreground">
            Argue aloud. Opposing counsel may object; the judge will rule.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {roomReady && <Badge variant="outline">Voice room ready</Badge>}
          <Badge variant={status === 'playing' ? 'destructive' : 'secondary'}>
            {STATUS_LABEL[status]}
          </Badge>
        </div>
      </div>

      <div className="flex flex-col gap-4 rounded-lg border bg-card/40 p-6">
        {lines.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {status === 'connecting' ? 'Connecting to the courtroom…' : 'Waiting to begin…'}
          </p>
        ) : (
          lines.map((line) => <TranscriptLine key={line.id} line={line} />)
        )}
      </div>

      {status === 'completed' && (
        <div className="flex justify-end">
          <Button onClick={() => navigate(`/session/${sessionId}/scorecard`)}>
            End session &amp; view scorecard
          </Button>
        </div>
      )}
    </div>
  );
}
