/**
 * File: src/components/SessionFinale.tsx
 * Purpose: The end-of-session "verdict" view shown while the room is still connected and the Judge
 *   composes + delivers the final ruling (before navigating to the Scorecard). Two phases: AWAITING
 *   (dead air — the judge is composing, a slow amber deliberation wave) → RULING (the judge speaks,
 *   the equalizer reacts to the judge's voice). Judge-focused: no presence dots. Render-only — the
 *   audio analysis lives in useAudioVisualization (DEV_GUIDELINES §11); the phase machine is derived
 *   by the caller (SparringRoom) from existing signals.
 * Depends on: react, livekit-client (track type), hooks/useAudioVisualization, lib/rulingPhase
 * Related: pages/SparringRoom.tsx (renders this during `ending`), docs/ARCHITECTURE.md §6.5
 * Security notes: Purely presentational; the canvas is aria-hidden and the heading text is the real
 *   signal of what is happening — the visual is never the only cue.
 */

import { useAudioVisualization, type VisualizedTrack } from '@/hooks/useAudioVisualization';

/** The Judge's color, matching the live visualizer's role tint. */
const JUDGE_COLOR = '#f59e0b';

interface Props {
  /** 'awaiting' (judge composing — dead air) or 'ruling' (judge speaking). */
  phase: 'awaiting' | 'ruling';
  /** The Judge's audio track while speaking (null in AWAITING). */
  track: VisualizedTrack | null;
  /** Reuse of the existing audio-unlock signal (!audioBlocked) to resume the analyser context. */
  audioReady: boolean;
}

const COPY: Record<Props['phase'], { heading: string; sub: string }> = {
  awaiting: {
    heading: 'The judge is deliberating',
    sub: 'Composing the final ruling and scorecard…',
  },
  ruling: {
    heading: 'The judge is delivering the ruling',
    sub: 'Listen for the verdict.',
  },
};

export function SessionFinale({ phase, track, audioReady }: Props) {
  // Enabled throughout the finale so the amber deliberation wave animates even in AWAITING (no
  // track); in RULING the same canvas reacts to the judge's live track. Idle style is the taller,
  // slower "deliberation" wave — distinct from the live session's ambient shimmer.
  const { canvasRef } = useAudioVisualization({
    track,
    enabled: true,
    audioReady,
    color: JUDGE_COLOR,
    idleStyle: 'deliberating',
  });

  const copy = COPY[phase];

  return (
    <div className="flex flex-col items-center gap-4 py-4 text-center">
      <canvas ref={canvasRef} aria-hidden className="h-16 w-full max-w-md" />
      <div className="flex flex-col gap-1">
        <p className="text-base font-medium text-foreground">{copy.heading}</p>
        <p className="text-sm text-muted-foreground">{copy.sub}</p>
      </div>
    </div>
  );
}
