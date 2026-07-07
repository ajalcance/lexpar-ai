/**
 * File: src/pages/Scorecard.test.tsx
 * Purpose: Critical-flow test for scorecard display (DEVELOPER_GUIDELINES §6) — the page
 *   renders the score, section headings, and ruling from the API data.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Scorecard, lib/mockData
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { Scorecard } from '@/pages/Scorecard';
import { mockScorecard } from '@/lib/mockData';

describe('Scorecard', () => {
  it('renders the score, sections, and ruling from the API', async () => {
    renderWithProviders(<Scorecard />);

    expect(
      await screen.findByText(String(mockScorecard.overallScore)),
    ).toBeInTheDocument();
    expect(screen.getByText('Strengths')).toBeInTheDocument();
    expect(screen.getByText('Weaknesses')).toBeInTheDocument();
    expect(screen.getByText(mockScorecard.strengths)).toBeInTheDocument();
    expect(screen.getByText(mockScorecard.judgeRuling)).toBeInTheDocument();
  });
});
