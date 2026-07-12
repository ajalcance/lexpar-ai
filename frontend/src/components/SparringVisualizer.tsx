/**
 * File: src/components/SparringVisualizer.tsx
 * Purpose: The live-audio visual for the sparring room (additive, above the transcript) — an
 *   equalizer for whoever is currently speaking (via useAudioVisualization) plus three always-
 *   present presence dots (You / Opposing Counsel / Judge) that brighten with each participant's
 *   coarse audio level. Render-only: all canvas analysis/animation lives in the hook
 *   (DEV_GUIDELINES §11); the `ocThinking` cue below is pure declarative CSS (no rAF).
 *   When `ocThinking` is true (OC drafting its non-interruptible reply, no audio flowing yet) a
 *   soft red halo breathes around the wave box and the Opposing Counsel dot pulses — a peripheral
 *   companion to the "responding — please hold" text badge, which stays the real signal.
 * Depends on: react, livekit-client (Track type), hooks/useAudioVisualization, lib/activeSpeaker,
 *   lib/utils (cn)
 * Related: pages/SparringRoom.tsx (places this at the top of the transcript panel)
 * Security notes: Purely presentational; aria-hidden — the text speaker badge remains the real
 *   attribution source, so this never becomes the only way to tell who is speaking.
 */

import { useAudioVisualization, type VisualizedTrack } from '@/hooks/useAudioVisualization';
import type { ActiveSpeaker, AudioLevels } from '@/lib/activeSpeaker';
import { cn } from '@/lib/utils';

/** Concrete bar/dot colors per role (canvas fillStyle needs a literal color, not a CSS var). */
const ROLE_COLOR: Record<'you' | 'opposing_counsel' | 'judge' | 'idle', string> = {
  you: '#3b82f6',
  opposing_counsel: '#ef4444',
  judge: '#f59e0b',
  idle: '#9ca3af',
};

const DOTS: { key: keyof AudioLevels; label: string }[] = [
  { key: 'you', label: 'You' },
  { key: 'opposing_counsel', label: 'Opposing Counsel' },
  { key: 'judge', label: 'Judge' },
];

interface Props {
  /** Active speaker's audio track (null → idle). */
  track: VisualizedTrack | null;
  activeSpeaker: ActiveSpeaker;
  levels: AudioLevels;
  /** True only in a live session — gates the analyser (idle shimmer otherwise). */
  enabled: boolean;
  /** Existing audio-unlock signal (!audioBlocked), reused to resume the analyser context. */
  audioReady: boolean;
  /** OC is composing its (non-interruptible) reply — no audio yet. Drives the breathing red cue. */
  ocThinking?: boolean;
}

export function SparringVisualizer({
  track,
  activeSpeaker,
  levels,
  enabled,
  audioReady,
  ocThinking = false,
}: Props) {
  const color = ROLE_COLOR[activeSpeaker ?? 'idle'];
  const { canvasRef, reducedMotion } = useAudioVisualization({ track, enabled, audioReady, color });
  // Under reduced motion the cue holds a steady soft glow instead of breathing.
  const pulse = ocThinking && !reducedMotion;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-full max-w-md">
        <canvas ref={canvasRef} aria-hidden className="h-16 w-full" />
        {ocThinking && (
          <div
            aria-hidden
            className={cn(
              'pointer-events-none absolute -inset-1 rounded-xl ring-2 ring-[#ef4444]/60',
              'shadow-[0_0_24px_4px_rgba(239,68,68,0.45)]',
              pulse ? 'animate-oc-pulse' : 'opacity-70',
            )}
          />
        )}
      </div>
      <div className="flex items-center justify-center gap-6">
        {DOTS.map(({ key, label }) => {
          const level = Math.min(1, levels[key]);
          const isThinking = key === 'opposing_counsel' && ocThinking;
          const active = level > 0.05 || isThinking;
          return (
            <div key={key} className="flex items-center gap-2">
              <span
                aria-hidden
                className={cn(
                  'size-2.5 rounded-full transition-transform',
                  isThinking && pulse && 'animate-oc-pulse',
                )}
                style={{
                  backgroundColor: active ? ROLE_COLOR[key] : ROLE_COLOR.idle,
                  // While thinking, let the animation (or steady red) own opacity/scale.
                  opacity: isThinking ? undefined : active ? 0.5 + 0.5 * level : 0.3,
                  transform: reducedMotion || isThinking ? undefined : `scale(${1 + level * 0.5})`,
                }}
              />
              <span className={cn('text-xs', active ? 'text-foreground' : 'text-muted-foreground')}>
                {label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
