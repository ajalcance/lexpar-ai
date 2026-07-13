/**
 * File: src/pages/CaseDetail.test.tsx
 * Purpose: Critical-flow tests for the case hub — starting a sparring session sends the REQUIRED
 *   proceeding type (§13 Phase 4): the default (oral argument) when untouched and the selected
 *   value when changed; and the rehearsal history links a completed session to its scorecard.
 * Depends on: vitest, @testing-library/*, test/utils, pages/CaseDetail, lib/api
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders } from '@/test/utils';
import { CaseDetail } from '@/pages/CaseDetail';
import * as api from '@/lib/api';
import type { Case, Session } from '@/lib/types';

const CASE: Case = {
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

const SESSION: Session = {
  id: 's1',
  caseId: 'c1',
  status: 'in_progress',
  proceedingType: 'oral_argument',
  llmBackendUsed: 'fireworks',
  startedAt: '2026-07-10T00:00:00Z',
  endedAt: null,
};

/** Render CaseDetail at /case/c1 so useParams resolves the id. */
function renderAt() {
  return renderWithProviders(
    <Routes>
      <Route path="/case/:id" element={<CaseDetail />} />
    </Routes>,
    '/case/c1',
  );
}

describe('CaseDetail session creation', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts a session with the default proceeding type (oral argument)', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue(CASE);
    vi.spyOn(api, 'getCaseSessions').mockResolvedValue([]);
    const createSession = vi.spyOn(api, 'createSession').mockResolvedValue(SESSION);
    const user = userEvent.setup();
    renderAt();

    await user.click(await screen.findByRole('button', { name: 'Start sparring' }));

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith('c1', 'oral_argument');
    });
  });

  it('shows the untested proceedings for reference but disables them (only oral argument selectable)', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue(CASE);
    vi.spyOn(api, 'getCaseSessions').mockResolvedValue([]);
    renderAt();

    await screen.findByLabelText('Proceeding');
    // Oral argument is selectable; the others are visible ("coming soon") but disabled.
    expect(screen.getByRole('option', { name: 'Oral argument' })).toBeEnabled();
    for (const label of ['Direct examination', 'Cross-examination', 'Motion hearing']) {
      const option = screen.getByRole('option', { name: `${label} — coming soon` });
      expect(option).toBeDisabled();
    }
  });

  it('archives the case (soft default) after an explicit confirm', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue(CASE);
    vi.spyOn(api, 'getCaseSessions').mockResolvedValue([]);
    const archiveCase = vi.spyOn(api, 'archiveCase').mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderAt();

    await user.click(await screen.findByRole('button', { name: 'Archive case' }));
    // two-step: the destructive confirm appears, nothing has been called yet
    expect(archiveCase).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Archive' }));

    await waitFor(() => {
      expect(archiveCase).toHaveBeenCalledWith('c1');
    });
  });

  it('links a completed session in history to its scorecard', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue(CASE);
    vi.spyOn(api, 'getCaseSessions').mockResolvedValue([
      { ...SESSION, id: 's9', status: 'completed', endedAt: '2026-07-10T00:10:00Z' },
    ]);
    renderAt();

    // Button-as-Link (Base UI role=button) — assert the destination via its anchor.
    const link = await screen.findByText('View scorecard');
    expect(link.closest('a')).toHaveAttribute('href', '/session/s9/scorecard');
  });
});
