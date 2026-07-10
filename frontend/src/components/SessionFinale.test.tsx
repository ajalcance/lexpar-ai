/**
 * File: src/components/SessionFinale.test.tsx
 * Purpose: Render test for the verdict finale — the correct phase copy shows for AWAITING (judge
 *   deliberating, dead air) vs RULING (judge delivering the ruling). The audio-reactive behavior
 *   itself lives in useAudioVisualization (cleanup + reduced-motion already covered there) and its
 *   real feel needs a live session — not Vitest.
 * Depends on: vitest, @testing-library/react, components/SessionFinale
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SessionFinale } from '@/components/SessionFinale';

beforeEach(() => {
  // Non-recursing rAF + a matchMedia stub so the reused visualization hook runs cleanly in jsdom.
  // jsdom has no 2D canvas; return null so the hook's guarded draw is skipped (no noisy warning).
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  vi.stubGlobal('requestAnimationFrame', vi.fn().mockReturnValue(1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('SessionFinale', () => {
  it('shows the deliberating copy in the awaiting (dead-air) phase', () => {
    render(<SessionFinale phase="awaiting" track={null} audioReady />);
    expect(screen.getByText('The judge is deliberating')).toBeInTheDocument();
    expect(screen.getByText(/Composing the final ruling/)).toBeInTheDocument();
  });

  it('shows the delivering-ruling copy in the ruling phase', () => {
    render(<SessionFinale phase="ruling" track={null} audioReady />);
    expect(screen.getByText('The judge is delivering the ruling')).toBeInTheDocument();
    expect(screen.getByText('Listen for the verdict.')).toBeInTheDocument();
  });
});
