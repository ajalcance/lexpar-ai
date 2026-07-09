/**
 * File: src/pages/Scorecard.test.tsx
 * Purpose: Critical-flow tests for scorecard display (DEVELOPER_GUIDELINES §6) — renders the real
 *   score/sections/ruling, preserves line breaks in the multi-line strengths/weaknesses, renders the
 *   real persisted transcript, and shows the honest fallback when no scorecard exists yet.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Scorecard, lib/api
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { Scorecard } from '@/pages/Scorecard';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';

const fakeScorecard = {
  id: 's1',
  sessionId: 'sess1',
  overallScore: 78,
  strengths: 'Clear framing of the good-faith argument.',
  weaknesses: 'Drifted from the record.',
  judgeRuling: 'The position holds up with cleaner sequencing.',
  createdAt: '2026-07-07T00:00:00Z',
};

describe('Scorecard', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the score, sections, and ruling from the API', async () => {
    vi.spyOn(api, 'getScorecard').mockResolvedValue(fakeScorecard);
    vi.spyOn(api, 'getSessionTranscript').mockResolvedValue([]);
    renderWithProviders(<Scorecard />);

    expect(await screen.findByText('78')).toBeInTheDocument();
    expect(screen.getByText('Strengths')).toBeInTheDocument();
    expect(screen.getByText('Weaknesses')).toBeInTheDocument();
    expect(screen.getByText(fakeScorecard.strengths)).toBeInTheDocument();
    expect(screen.getByText(fakeScorecard.judgeRuling)).toBeInTheDocument();
  });

  it('preserves the newlines in multi-line strengths (whitespace-pre-line)', async () => {
    vi.spyOn(api, 'getScorecard').mockResolvedValue({
      ...fakeScorecard,
      strengths: '- Established fact one.\n- Established fact two.',
    });
    vi.spyOn(api, 'getSessionTranscript').mockResolvedValue([]);
    renderWithProviders(<Scorecard />);

    const strengths = await screen.findByText(/Established fact one/);
    expect(strengths).toHaveClass('whitespace-pre-line');
    expect(strengths.textContent).toContain('- Established fact one.');
    expect(strengths.textContent).toContain('- Established fact two.');
  });

  it('renders the real persisted transcript when present', async () => {
    vi.spyOn(api, 'getScorecard').mockResolvedValue(fakeScorecard);
    vi.spyOn(api, 'getSessionTranscript').mockResolvedValue([
      {
        id: 't1',
        sessionId: 'sess1',
        speaker: 'attorney',
        content: 'My client acted in good faith.',
        wasInterruption: false,
        spokenAt: '2026-07-07T00:00:00Z',
      },
      {
        id: 't2',
        sessionId: 'sess1',
        speaker: 'opposing_counsel',
        content: 'Objection — hearsay.',
        wasInterruption: true,
        spokenAt: '2026-07-07T00:00:01Z',
      },
    ]);
    renderWithProviders(<Scorecard />);

    expect(await screen.findByText('Transcript')).toBeInTheDocument();
    expect(screen.getByText('My client acted in good faith.')).toBeInTheDocument();
    expect(screen.getByText('Objection — hearsay.')).toBeInTheDocument();
  });

  it('shows a scoring/polling state while the scorecard is still being written', async () => {
    // 409 = session not yet completed. The page polls (does not fabricate or hard-error), so it
    // shows the "scoring" state rather than a fallback until the judge finishes writing it.
    vi.spyOn(api, 'getScorecard').mockRejectedValue(
      new ApiError('Scorecard is available only after the session is completed.', 409),
    );
    vi.spyOn(api, 'getSessionTranscript').mockResolvedValue([]);
    renderWithProviders(<Scorecard />);

    expect(await screen.findByText(/Scoring your session/)).toBeInTheDocument();
  });
});
