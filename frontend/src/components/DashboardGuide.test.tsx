/**
 * File: src/components/DashboardGuide.test.tsx
 * Purpose: The dashboard reviewer guide names the ready demo case and the two-step path — a
 *   hackathon judging aid, so its content is worth guarding.
 * Depends on: vitest, @testing-library/react, components/DashboardGuide, lib/flags
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { DashboardGuide } from '@/components/DashboardGuide';
import { DEMO_CASE_TITLE } from '@/lib/flags';

describe('DashboardGuide', () => {
  it('names the ready demo case and the two-step path', () => {
    renderWithProviders(<DashboardGuide />);
    expect(screen.getByText(DEMO_CASE_TITLE)).toBeInTheDocument();
    expect(screen.getByText(/create a courtroom/)).toBeInTheDocument();
    expect(screen.getByText(/Two ways to test/)).toBeInTheDocument();
  });

  it('links the case name straight to the case when the id is known', () => {
    renderWithProviders(<DashboardGuide demoCaseId="case-123" />);
    const link = screen.getByRole('link', { name: DEMO_CASE_TITLE });
    expect(link).toHaveAttribute('href', '/case/case-123');
  });
});
