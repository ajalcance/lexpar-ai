/**
 * File: src/pages/SparringRoom.tsx
 * Purpose: The live sparring room. Connects to the real LiveKit room and publishes the mic
 *   (useSparringRoom), showing real connection-state, listening/speaking, and mute controls. If the
 *   connection fails or no agent joins within a few seconds it falls back to the scripted mock
 *   transcript (useSparringSession) so the app stays demoable. On "End session" it stays connected
 *   and shows the verdict finale (SessionFinale: judge deliberating → delivering the ruling) before
 *   navigating to the scorecard. Objection detection/display is unchanged (Gap 3).
 * Depends on: react-router-dom, hooks/useSparringRoom, hooks/useSparringSession, lib/rulingPhase,
 *   components/{TranscriptLine,SparringVisualizer,SessionFinale}, components/ui/*
 * Related: agents/main.py (the worker that joins the same room), pages/Scorecard.tsx
 * Security notes: Renders transcript content (attorney work product) for the session only; never
 *   logged. Microphone audio is published to this session's room only.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Mic, MicOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { SessionFinale } from '@/components/SessionFinale';
import { SparringVisualizer } from '@/components/SparringVisualizer';
import { TranscriptLine } from '@/components/TranscriptLine';
import { useSparringRoom, type ConnStatus } from '@/hooks/useSparringRoom';
import { useSparringSession } from '@/hooks/useSparringSession';
import { latchHasSpoken, rulingPhase } from '@/lib/rulingPhase';

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

  const {
    mode,
    connectionState,
    activeSpeaker,
    activeTrack,
    audioLevels,
    judgeSpeaking,
    isMuted,
    micBlocked,
    audioBlocked,
    ocThinking,
    toggleMute,
    enableAudio,
    endSession,
    transcript,
  } = useSparringRoom(sessionId);
  const { lines } = useSparringSession(sessionId, { enabled: mode === 'fallback' });

  const isConnected = connectionState === 'connected';
  const [ending, setEnding] = useState(false);

  // Session finale (verdict moment): once "End session" is clicked the room stays connected while
  // the judge composes (AWAITING — dead air) then speaks the ruling (RULING). `hasSpoken` latches on
  // the first judge audio so inter-sentence pauses / the persist tail don't flip the copy back.
  const judgeAudio = activeSpeaker === 'judge' || judgeSpeaking;
  const [hasSpoken, setHasSpoken] = useState(false);
  useEffect(() => {
    setHasSpoken((prev) => (ending ? latchHasSpoken(prev, judgeAudio) : false));
  }, [ending, judgeAudio]);
  const phase = rulingPhase(ending, hasSpoken); // 'live' | 'awaiting' | 'ruling'

  // Auto-scroll the live transcript to the newest line as it streams in.
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [transcript.length]);

  const handleEnd = async () => {
    // In a live session, let the judge deliver the spoken ruling + write the scorecard first, then
    // go to the scorecard. In fallback (no agent) there's nothing to wait for — navigate straight.
    if (mode === 'live') {
      setEnding(true);
      await endSession();
    }
    navigate(`/session/${sessionId}/scorecard`);
  };

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs
        items={[{ label: 'Cases', to: '/dashboard' }, { label: 'Sparring session' }]}
      />
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
          {isConnected && !ending && (
            <Badge
              variant={
                judgeSpeaking ||
                activeSpeaker === 'judge' ||
                activeSpeaker === 'opposing_counsel' ||
                ocThinking
                  ? 'destructive'
                  : 'secondary'
              }
            >
              {/* activeSpeaker === 'judge' is structural (the judge participant's own audio);
                  judgeSpeaking is the fallback-path synthetic label. ocThinking bridges the silent
                  gap while OC composes its (non-interruptible) reply — it yields to the real
                  "speaking" label once OC's audio starts. */}
              {judgeSpeaking || activeSpeaker === 'judge'
                ? 'Judge speaking'
                : activeSpeaker === 'opposing_counsel'
                  ? 'Opposing counsel speaking'
                  : ocThinking
                    ? 'Opposing counsel responding — please hold'
                    : 'Listening'}
            </Badge>
          )}
          {/* Mute is hidden during the finale — the attorney is done arguing while the judge rules. */}
          {!ending && (
            <Button
              variant="outline"
              size="sm"
              onClick={toggleMute}
              disabled={!isConnected || micBlocked}
            >
              {isMuted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
              {isMuted ? 'Unmute' : 'Mute'}
            </Button>
          )}
        </div>
      </div>

      {micBlocked && (
        <p className="text-sm text-destructive">
          Microphone blocked — allow mic access in your browser to argue aloud.
        </p>
      )}

      {audioBlocked && (
        <div className="flex items-center gap-3 rounded-md border border-destructive/40 p-3">
          <p className="text-sm text-destructive">
            Your browser blocked audio playback — enable it to hear opposing counsel.
          </p>
          <Button variant="outline" size="sm" onClick={enableAudio}>
            Enable audio
          </Button>
        </div>
      )}

      <div className="flex flex-col gap-4 rounded-lg border bg-card/40 p-6">
        {ending ? (
          // The verdict moment: the room is still connected while the judge composes then speaks the
          // ruling. Judge-focused amber visual + phase copy, before navigating to the scorecard.
          <SessionFinale
            phase={phase === 'ruling' ? 'ruling' : 'awaiting'}
            track={activeSpeaker === 'judge' ? activeTrack : null}
            audioReady={!audioBlocked}
          />
        ) : (
          <>
            {/* Live-audio visual (additive) — equalizer for the active speaker + presence dots. The
                text speaker badge above remains the real attribution; this is aria-hidden. In
                connecting/fallback it shows a neutral idle shimmer rather than looking broken. */}
            <SparringVisualizer
              track={activeTrack}
              activeSpeaker={activeSpeaker}
              levels={audioLevels}
              enabled={mode === 'live'}
              audioReady={!audioBlocked}
            />

            {mode === 'connecting' && (
              <p className="text-sm text-muted-foreground">Connecting to the courtroom…</p>
            )}

            {mode === 'live' && (
              <>
                {transcript.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    You're connected — argue aloud. Your statements, opposing counsel's
                    counter-arguments, and the judge's rulings will appear here as they're spoken.
                  </p>
                ) : (
                  <div className="flex max-h-[28rem] flex-col gap-4 overflow-y-auto pr-1">
                    {transcript.map((line) => (
                      <TranscriptLine key={line.id} line={line} />
                    ))}
                    <div ref={transcriptEndRef} />
                  </div>
                )}
              </>
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
          </>
        )}
      </div>

      {mode !== 'connecting' && (
        <div className="flex items-center justify-end gap-3">
          <Button onClick={handleEnd} disabled={ending}>
            {ending ? 'Wrapping up…' : 'End session & view scorecard'}
          </Button>
        </div>
      )}
    </div>
  );
}
