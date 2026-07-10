/**
 * File: src/pages/Dashboard.test.tsx
 * Purpose: Critical-flow test for session creation (§13 Phase 4) — starting a sparring session
 *   sends the REQUIRED proceeding type: the default (oral argument) when untouched, and the
 *   selected value when changed.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Dashboard, lib/api
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { Dashboard } from '@/pages/Dashboard';
import * as api from '@/lib/api';
import type { Session } from '@/lib/types';

const CASE = {
  id: 'c1',
  title: 'Doe v. Roe',
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

describe('Dashboard session creation', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts a session with the default proceeding type (oral argument)', async () => {
    vi.spyOn(api, 'getCases').mockResolvedValue([CASE]);
    const createSession = vi.spyOn(api, 'createSession').mockResolvedValue(SESSION);
    const user = userEvent.setup();
    renderWithProviders(<Dashboard />);

    await user.click(await screen.findByRole('button', { name: 'Start sparring' }));

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith('c1', 'oral_argument');
    });
  });

  it('sends the selected proceeding type', async () => {
    vi.spyOn(api, 'getCases').mockResolvedValue([CASE]);
    const createSession = vi.spyOn(api, 'createSession').mockResolvedValue({
      ...SESSION,
      proceedingType: 'cross_examination',
    });
    const user = userEvent.setup();
    renderWithProviders(<Dashboard />);

    await user.selectOptions(
      await screen.findByLabelText('Proceeding'),
      'cross_examination',
    );
    await user.click(screen.getByRole('button', { name: 'Start sparring' }));

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith('c1', 'cross_examination');
    });
  });
});
