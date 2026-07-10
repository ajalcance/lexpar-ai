/**
 * File: src/hooks/useAudioVisualization.test.ts
 * Purpose: Lifecycle tests for the equalizer hook — it attaches an analyser only for an active
 *   track in a live session, closes the AudioContext (cleanup) on track swap and on unmount,
 *   resumes the context off the audioReady signal, and drops to a static (no-rAF) frame under
 *   reduced motion. The ACTUAL audio-reactive rendering (bars responding to real voice) can only
 *   be confirmed in a live session — not by Vitest.
 * Depends on: vitest, @testing-library/react (renderHook), livekit-client (mocked)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { createAudioAnalyser } from 'livekit-client';
import { useAudioVisualization, type VisualizedTrack } from '@/hooks/useAudioVisualization';

vi.mock('livekit-client', () => ({ createAudioAnalyser: vi.fn() }));

const mockCreate = vi.mocked(createAudioAnalyser);

/** A fake analyser handle whose cleanup/resume we can assert on. */
function makeAnalyser() {
  const cleanup = vi.fn();
  const resume = vi.fn().mockResolvedValue(undefined);
  const handle = {
    analyser: {
      frequencyBinCount: 512,
      getByteFrequencyData: vi.fn(),
      context: { state: 'running', resume },
    },
    calculateVolume: vi.fn(),
    cleanup,
  } as unknown as ReturnType<typeof createAudioAnalyser>;
  return { handle, cleanup, resume };
}

const trackA = { id: 'A' } as unknown as VisualizedTrack;
const trackB = { id: 'B' } as unknown as VisualizedTrack;

let rafSpy: ReturnType<typeof vi.fn>;

function setReducedMotion(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

beforeEach(() => {
  mockCreate.mockReset();
  setReducedMotion(false);
  rafSpy = vi.fn().mockReturnValue(1); // non-recursing: draw runs once, no infinite loop
  vi.stubGlobal('requestAnimationFrame', rafSpy);
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const base = { audioReady: false, color: '#fff' };

describe('useAudioVisualization', () => {
  it('creates an analyser for the active track when live', () => {
    mockCreate.mockReturnValue(makeAnalyser().handle);
    renderHook(() => useAudioVisualization({ ...base, track: trackA, enabled: true }));
    expect(mockCreate).toHaveBeenCalledWith(trackA, expect.objectContaining({ fftSize: 1024 }));
  });

  it('does not create an analyser with no active track', () => {
    renderHook(() => useAudioVisualization({ ...base, track: null, enabled: true }));
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('does not create an analyser when not live (idle shimmer only)', () => {
    renderHook(() => useAudioVisualization({ ...base, track: trackA, enabled: false }));
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('closes the AudioContext (cleanup) when the active track changes', () => {
    const a = makeAnalyser();
    mockCreate.mockReturnValue(a.handle);
    const { rerender } = renderHook((props: { track: VisualizedTrack }) =>
      useAudioVisualization({ ...base, track: props.track, enabled: true }),
      { initialProps: { track: trackA } },
    );
    expect(a.cleanup).not.toHaveBeenCalled();
    rerender({ track: trackB });
    expect(a.cleanup).toHaveBeenCalled();
  });

  it('closes the AudioContext on unmount (no leak across sessions)', () => {
    const a = makeAnalyser();
    mockCreate.mockReturnValue(a.handle);
    const { unmount } = renderHook(() =>
      useAudioVisualization({ ...base, track: trackA, enabled: true }),
    );
    unmount();
    expect(a.cleanup).toHaveBeenCalled();
  });

  it('resumes the context when audioReady flips true (existing unlock path)', () => {
    const a = makeAnalyser();
    mockCreate.mockReturnValue(a.handle);
    const { rerender } = renderHook((props: { audioReady: boolean }) =>
      useAudioVisualization({ track: trackA, enabled: true, color: '#fff', audioReady: props.audioReady }),
      { initialProps: { audioReady: false } },
    );
    a.resume.mockClear(); // ignore the best-effort resume at creation
    rerender({ audioReady: true });
    expect(a.resume).toHaveBeenCalled();
  });

  it('under reduced motion draws a static frame and does NOT start an rAF loop', () => {
    setReducedMotion(true);
    renderHook(() => useAudioVisualization({ ...base, track: null, enabled: false }));
    expect(rafSpy).not.toHaveBeenCalled();
  });

  it('runs the rAF loop when motion is allowed', () => {
    renderHook(() => useAudioVisualization({ ...base, track: null, enabled: false }));
    expect(rafSpy).toHaveBeenCalled();
  });
});
