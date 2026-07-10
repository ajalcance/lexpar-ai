/**
 * File: src/hooks/useAudioVisualization.ts
 * Purpose: Drives the sparring-room equalizer for the CURRENT active speaker. Attaches a LiveKit
 *   AnalyserNode to the active speaker's track (createAudioAnalyser — a non-playing tap, so no
 *   duplicate audio), swapping the analysed track when the speaker changes, and runs ONE
 *   requestAnimationFrame loop that reads FFT magnitudes and draws bars to a <canvas> imperatively
 *   (no per-frame React state). Idle/reduced-motion/cleanup all handled here so the component that
 *   uses it stays render-only (DEVELOPER_GUIDELINES §11).
 * Depends on: react, livekit-client (createAudioAnalyser), lib/audioBars.ts
 * Related: components/SparringVisualizer.tsx (renders the canvas), hooks/useSparringRoom.ts
 *   (supplies the active track + audioReady), docs/ARCHITECTURE.md §6.5
 * Security notes: Analyses audio energy only (never content); the tap never connects to output.
 */

import { useEffect, useRef, useState } from 'react';
import { createAudioAnalyser } from 'livekit-client';
import type { LocalAudioTrack, RemoteAudioTrack } from 'livekit-client';
import { BAR_COUNT, binFrequencies, idleBars, smoothBars, staticBars } from '@/lib/audioBars';

/** The kinds of track the equalizer analyses (the active speaker's audio). */
export type VisualizedTrack = LocalAudioTrack | RemoteAudioTrack;

interface AnalyserHandle {
  analyser: AnalyserNode;
  context: AudioContext;
  cleanup: () => Promise<void> | void;
}

interface Options {
  /** The active speaker's audio track (null → idle, e.g. between turns or not live). */
  track: VisualizedTrack | null;
  /** Analyse only when the session is genuinely live; false → idle shimmer. */
  enabled: boolean;
  /** Reuse of the existing gesture-unlock signal (audioBlocked→false) to resume the context. */
  audioReady: boolean;
  /** Concrete CSS color for the bars (role tint from the caller; grey when idle). */
  color: string;
}

/** True when the user asked for reduced motion; updates if they change it mid-session. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

function drawBars(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  bars: number[],
  color: string,
): void {
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = color;
  const n = bars.length;
  const gap = w * 0.04;
  const barW = (w - gap * (n - 1)) / n;
  for (let i = 0; i < n; i += 1) {
    const bh = Math.max(2, Math.min(1, bars[i]) * h * 0.9);
    const x = i * (barW + gap);
    const y = (h - bh) / 2;
    const r = Math.min(barW / 2, bh / 2, 4);
    ctx.beginPath();
    if (typeof ctx.roundRect === 'function') ctx.roundRect(x, y, barW, bh, r);
    else ctx.rect(x, y, barW, bh);
    ctx.fill();
  }
}

export function useAudioVisualization({ track, enabled, audioReady, color }: Options) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const analyserRef = useRef<AnalyserHandle | null>(null);
  const freqRef = useRef<Uint8Array<ArrayBuffer>>(new Uint8Array(0));
  const barsRef = useRef<number[]>(new Array(BAR_COUNT).fill(0));
  const colorRef = useRef(color);
  const rafRef = useRef<number | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  // Latest color without restarting the draw loop.
  colorRef.current = color;

  // Attach/detach the analyser to the active speaker's track. React runs the previous effect's
  // cleanup (closing the old AudioContext) before re-running on a track swap — so there is at most
  // one AudioContext at a time, closed on every swap and on unmount (never leaked across sessions).
  useEffect(() => {
    if (!track || !enabled) return;
    let handle: AnalyserHandle | null = null;
    try {
      // minDecibels/maxDecibels set the dynamic range mapped onto 0..255. The plugin default
      // (-100..-80) is far too low — normal speech playback sits well above -80 dBFS, so every bin
      // pegs at 255 and all bars max out. Widen it so voice varies visibly (tunable for live feel).
      const a = createAudioAnalyser(track, {
        fftSize: 1024,
        smoothingTimeConstant: 0.8,
        minDecibels: -85,
        maxDecibels: -20,
      });
      handle = {
        analyser: a.analyser,
        context: a.analyser.context as AudioContext,
        cleanup: a.cleanup,
      };
      analyserRef.current = handle;
      freqRef.current = new Uint8Array(a.analyser.frequencyBinCount);
      void handle.context.resume().catch(() => undefined); // best-effort (usually already running)
    } catch {
      analyserRef.current = null;
    }
    return () => {
      if (analyserRef.current === handle) analyserRef.current = null;
      void handle?.cleanup();
    };
  }, [track, enabled]);

  // Resume the analyser's context off the EXISTING gesture-unlock path (the audioBlocked→false
  // signal driven by enableAudio / the one-time pointerdown/keydown listeners) — not a new gesture.
  useEffect(() => {
    if (audioReady) void analyserRef.current?.context.resume().catch(() => undefined);
  }, [audioReady]);

  // Size the canvas backing store to its CSS box (crisp on HiDPI), once + on resize — never per frame.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    };
    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  // The single draw loop. Reduced motion draws one static frame and stops (no rAF).
  useEffect(() => {
    const draw = () => {
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext('2d') ?? null;
      const handle = analyserRef.current;
      let target: number[];
      if (reducedMotion) {
        target = staticBars();
      } else if (handle && handle.context.state === 'running') {
        handle.analyser.getByteFrequencyData(freqRef.current);
        target = binFrequencies(freqRef.current);
      } else {
        target = idleBars(BAR_COUNT, typeof performance !== 'undefined' ? performance.now() : 0);
      }
      barsRef.current = reducedMotion ? target : smoothBars(barsRef.current, target);
      if (ctx && canvas) drawBars(ctx, canvas, barsRef.current, colorRef.current);
      if (!reducedMotion) rafRef.current = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [reducedMotion]);

  return { canvasRef, reducedMotion };
}
