/**
 * File: src/components/DashboardGuide.test.tsx
 * Purpose: The dashboard reviewer guide names the ready demo case and the two-step path — a
 *   hackathon judging aid, so its content is worth guarding.
 * Depends on: vitest, @testing-library/react, components/DashboardGuide, lib/flags
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DashboardGuide } from '@/components/DashboardGuide';
import { DEMO_CASE_TITLE } from '@/lib/flags';

describe('DashboardGuide', () => {
  it('names the ready demo case and the two-step path', () => {
    render(<DashboardGuide />);
    expect(screen.getByText(DEMO_CASE_TITLE)).toBeInTheDocument();
    expect(screen.getByText(/Court administration/)).toBeInTheDocument();
    expect(screen.getByText(/Two ways to test/)).toBeInTheDocument();
  });
});
