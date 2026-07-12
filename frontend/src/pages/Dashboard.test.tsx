/**
 * File: src/pages/Dashboard.test.tsx
 * Purpose: Critical-flow test for the Cases list — a case renders and links to its detail page
 *   (where a session is now started). Session creation itself is covered in CaseDetail.test.tsx.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Dashboard, lib/api
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { Dashboard } from '@/pages/Dashboard';
import * as api from '@/lib/api';

const CASE = {
  id: 'c1',
  title: 'Doe v. Roe',
  caseNumber: null,
  petitioner: null,
  respondent: null,
  representedParty: null,
  reliefSought: null,
  caseFacts: 'A contract dispute.',
  courtId: null,
  createdAt: '2026-07-07T00:00:00Z',
};

describe('Dashboard', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists a case linking to its detail page', async () => {
    vi.spyOn(api, 'getCases').mockResolvedValue([CASE]);
    // Each card fetches its own sessions for the rehearsal summary.
    vi.spyOn(api, 'getCaseSessions').mockResolvedValue([]);
    renderWithProviders(<Dashboard />);

    const link = await screen.findByRole('link', { name: /Doe v\. Roe/ });
    expect(link).toHaveAttribute('href', '/case/c1');
  });

  it('offers a New case action', async () => {
    vi.spyOn(api, 'getCases').mockResolvedValue([]);
    renderWithProviders(<Dashboard />);

    // The "New case" control renders as a Base UI Button-as-Link (role=button), so assert the
    // destination via its anchor rather than the link role.
    const newCase = await screen.findByText('New case');
    expect(newCase.closest('a')).toHaveAttribute('href', '/case/new');
  });
});
