/**
 * File: src/pages/Scorecard.test.tsx
 * Purpose: Critical-flow test for scorecard display (DEVELOPER_GUIDELINES §6) — renders the score
 *   and sections from the API, and shows the honest fallback when no scorecard exists yet (the
 *   Judge agent isn't built).
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
    renderWithProviders(<Scorecard />);

    expect(await screen.findByText('78')).toBeInTheDocument();
    expect(screen.getByText('Strengths')).toBeInTheDocument();
    expect(screen.getByText('Weaknesses')).toBeInTheDocument();
    expect(screen.getByText(fakeScorecard.strengths)).toBeInTheDocument();
    expect(screen.getByText(fakeScorecard.judgeRuling)).toBeInTheDocument();
  });

  it('shows a fallback when the scorecard is not generated yet', async () => {
    vi.spyOn(api, 'getScorecard').mockRejectedValue(
      new ApiError('Scorecard is available only after the session is completed.', 409),
    );
    renderWithProviders(<Scorecard />);

    expect(await screen.findByText('Not available yet')).toBeInTheDocument();
  });
});
