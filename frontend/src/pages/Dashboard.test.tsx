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
  // Rehearsal summary now rides on the case payload (one grouped query — no per-card N+1).
  sessionCount: 2,
  bestScore: 88,
  lastRehearsedAt: '2026-07-09T00:00:00Z',
};

describe('Dashboard', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists a case with its rehearsal summary, linking to its detail page', async () => {
    vi.spyOn(api, 'getCases').mockResolvedValue([CASE]);
    const getSessions = vi.spyOn(api, 'getCaseSessions');
    renderWithProviders(<Dashboard />);

    const link = await screen.findByRole('link', { name: /Doe v\. Roe/ });
    expect(link).toHaveAttribute('href', '/case/c1');
    // The summary comes from the list payload — no per-card session fetch (no N+1).
    expect(screen.getByText(/2 rehearsals/)).toBeInTheDocument();
    expect(screen.getByText('Best 88')).toBeInTheDocument();
    expect(getSessions).not.toHaveBeenCalled();
  });

  it('offers a New case action', async () => {
    vi.spyOn(api, 'getCases').mockResolvedValue([]);
    renderWithProviders(<Dashboard />);

    // The "New case" control renders as a Base UI Button-as-Link — assert via its anchor. Several
    // "New case" texts exist now (header + empty-state buttons + the reviewer guide's instruction
    // text), so assert at least one sits inside an anchor to /case/new (the guide text does not).
    const texts = await screen.findAllByText('New case');
    const hrefs = texts.map((el) => el.closest('a')?.getAttribute('href'));
    expect(hrefs).toContain('/case/new');
  });
});
