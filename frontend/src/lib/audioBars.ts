/**
 * File: src/lib/audioBars.ts
 * Purpose: Pure amplitude→bar math for the sparring-room equalizer visual — binning FFT
 *   magnitudes into a few bars, an idle "resting shimmer", a static reduced-motion frame, and
 *   an asymmetric (fast-rise / slow-fall) smoothing step. Kept DOM-free and pure so the mapping
 *   is unit-tested without any audio hardware (the live audio-reactive feel needs a live session).
 * Depends on: nothing (pure functions)
 * Related: hooks/useAudioVisualization.ts (the loop that calls these), lib/audioBars.test.ts
 */

/** Number of equalizer bars rendered for the active speaker. */
export const BAR_COUNT = 5;

// Voice energy sits in the lower frequencies; the upper FFT bins carry little vocal motion, so we
// bin only the lower slice of the spectrum into bars (using the whole spectrum would flatten them).
const VOICE_BIN_FRACTION = 0.25;

/** Average the voice-relevant slice of an FFT magnitude array (0..255) into `barCount` bars, 0..1. */
export function binFrequencies(freq: Uint8Array, barCount = BAR_COUNT): number[] {
  if (freq.length === 0) return new Array(barCount).fill(0);
  const usable = Math.max(barCount, Math.floor(freq.length * VOICE_BIN_FRACTION));
  const per = Math.max(1, Math.floor(usable / barCount));
  const bars: number[] = [];
  for (let b = 0; b < barCount; b += 1) {
    const start = b * per;
    const end = Math.min(start + per, usable);
    let sum = 0;
    for (let i = start; i < end; i += 1) sum += freq[i];
    const count = Math.max(1, end - start);
    bars.push(sum / count / 255);
  }
  return bars;
}

/** Low resting shimmer so the bars breathe between turns / before connection, never a frozen flat line. */
export const IDLE_BASE = 0.06;
export const IDLE_SWING = 0.04;
export function idleBars(barCount = BAR_COUNT, timeMs = 0): number[] {
  const t = timeMs / 500;
  const bars: number[] = [];
  for (let i = 0; i < barCount; i += 1) {
    bars.push(IDLE_BASE + IDLE_SWING * (0.5 + 0.5 * Math.sin(t + i * 0.9)));
  }
  return bars;
}

/** Flat low bars for the reduced-motion / static state (no animation). */
export const STATIC_LEVEL = 0.12;
export function staticBars(barCount = BAR_COUNT): number[] {
  return new Array(barCount).fill(STATIC_LEVEL);
}

/** A slow, pronounced amber "deliberation" wave for the session-finale dead-air window (the judge
 *  composing the ruling) — deliberately taller and slower than the ambient `idleBars` shimmer so it
 *  reads as "the judge is working", not a quiet room. A traveling sine across the bars. */
export const DELIBERATE_BASE = 0.22;
export const DELIBERATE_SWING = 0.5;
export function deliberatingBars(barCount = BAR_COUNT, timeMs = 0): number[] {
  const t = timeMs / 900; // slower than idle (idle divides by 500)
  const bars: number[] = [];
  for (let i = 0; i < barCount; i += 1) {
    bars.push(DELIBERATE_BASE + DELIBERATE_SWING * (0.5 + 0.5 * Math.sin(t - i * 0.7)));
  }
  return bars;
}

/** One asymmetric smoothing step toward `target` — fast rise, slow fall (VU-meter feel). */
export const ATTACK = 0.6;
export const DECAY = 0.12;
export function smoothBars(
  current: number[],
  target: number[],
  attack = ATTACK,
  decay = DECAY,
): number[] {
  return target.map((t, i) => {
    const c = current[i] ?? 0;
    const k = t > c ? attack : decay;
    return c + (t - c) * k;
  });
}
