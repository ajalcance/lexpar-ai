/**
 * File: src/lib/audioBars.test.ts
 * Purpose: Unit tests for the pure amplitude→bar math — binning, idle shimmer, static frame, and
 *   the asymmetric smoothing step. (The live audio-reactive feel needs a real session; only the
 *   math is Vitest-verifiable.)
 * Depends on: vitest, lib/audioBars
 */

import { describe, expect, it } from 'vitest';
import {
  ATTACK,
  BAR_COUNT,
  DECAY,
  DELIBERATE_BASE,
  DELIBERATE_SWING,
  IDLE_BASE,
  IDLE_SWING,
  STATIC_LEVEL,
  binFrequencies,
  deliberatingBars,
  idleBars,
  smoothBars,
  staticBars,
} from '@/lib/audioBars';

describe('binFrequencies', () => {
  it('returns barCount values, all normalized to 0..1', () => {
    const freq = new Uint8Array(200).fill(128);
    const bars = binFrequencies(freq, BAR_COUNT);
    expect(bars).toHaveLength(BAR_COUNT);
    for (const b of bars) {
      expect(b).toBeGreaterThanOrEqual(0);
      expect(b).toBeLessThanOrEqual(1);
    }
    // 128/255 ≈ 0.502 for a uniform spectrum
    expect(bars[0]).toBeCloseTo(128 / 255, 5);
  });

  it('maps full-scale magnitudes to ~1 and silence to 0', () => {
    expect(binFrequencies(new Uint8Array(200).fill(255))[0]).toBeCloseTo(1, 5);
    expect(binFrequencies(new Uint8Array(200).fill(0))).toEqual(new Array(BAR_COUNT).fill(0));
  });

  it('is safe on an empty array (returns zeros)', () => {
    expect(binFrequencies(new Uint8Array(0))).toEqual(new Array(BAR_COUNT).fill(0));
  });
});

describe('idleBars', () => {
  it('stays a low shimmer within [IDLE_BASE, IDLE_BASE+IDLE_SWING] and is not flat over time', () => {
    const a = idleBars(BAR_COUNT, 0);
    const b = idleBars(BAR_COUNT, 700);
    expect(a).toHaveLength(BAR_COUNT);
    for (const v of [...a, ...b]) {
      expect(v).toBeGreaterThanOrEqual(IDLE_BASE - 1e-9);
      expect(v).toBeLessThanOrEqual(IDLE_BASE + IDLE_SWING + 1e-9);
    }
    // motion over time — not a frozen frame
    expect(a).not.toEqual(b);
  });
});

describe('staticBars', () => {
  it('is a flat low frame at STATIC_LEVEL (reduced-motion)', () => {
    expect(staticBars(BAR_COUNT)).toEqual(new Array(BAR_COUNT).fill(STATIC_LEVEL));
  });
});

describe('deliberatingBars', () => {
  it('stays within [DELIBERATE_BASE, DELIBERATE_BASE+DELIBERATE_SWING] and animates over time', () => {
    const a = deliberatingBars(BAR_COUNT, 0);
    const b = deliberatingBars(BAR_COUNT, 1200);
    expect(a).toHaveLength(BAR_COUNT);
    for (const v of [...a, ...b]) {
      expect(v).toBeGreaterThanOrEqual(DELIBERATE_BASE - 1e-9);
      expect(v).toBeLessThanOrEqual(DELIBERATE_BASE + DELIBERATE_SWING + 1e-9);
    }
    expect(a).not.toEqual(b); // it's a moving wave, not frozen
  });

  it('is taller than the ambient idle shimmer (reads as "the judge is working")', () => {
    // Peak of the deliberation wave clears the entire idle-shimmer band.
    expect(DELIBERATE_BASE).toBeGreaterThan(IDLE_BASE + IDLE_SWING);
  });
});

describe('smoothBars', () => {
  it('rises fast toward a higher target (attack)', () => {
    expect(smoothBars([0], [1])).toEqual([ATTACK]); // 0 + (1-0)*ATTACK
  });

  it('falls slowly toward a lower target (decay)', () => {
    expect(smoothBars([1], [0])).toEqual([1 - DECAY]); // 1 + (0-1)*DECAY
  });

  it('matches the target length and treats missing current as 0', () => {
    const out = smoothBars([], [0.5, 0.5]);
    expect(out).toHaveLength(2);
    expect(out[0]).toBeCloseTo(0.5 * ATTACK, 5);
  });
});
