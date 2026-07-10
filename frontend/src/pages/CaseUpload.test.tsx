/**
 * File: src/pages/CaseUpload.test.tsx
 * Purpose: Critical-flow test for case upload (DEVELOPER_GUIDELINES §6) — submitting the form
 *   calls api.createCase with the entered title and facts.
 * Depends on: vitest, @testing-library/*, test/utils, pages/CaseUpload, lib/api
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { CaseUpload } from '@/pages/CaseUpload';
import * as api from '@/lib/api';

describe('CaseUpload', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const created = {
    id: 'c1',
    title: 'Doe v. Roe',
    caseFacts: 'A contract dispute over delivery terms.',
    courtId: null,
    createdAt: '2026-07-07T00:00:00Z',
  };

  it('submits without a court when no courts are configured (with notice)', async () => {
    vi.spyOn(api, 'getCourts').mockResolvedValue([]);
    const createCase = vi.spyOn(api, 'createCase').mockResolvedValue(created);
    const user = userEvent.setup();
    renderWithProviders(<CaseUpload />);

    expect(await screen.findByText(/No courts configured yet/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Case title'), 'Doe v. Roe');
    await user.type(
      screen.getByLabelText('Case facts'),
      'A contract dispute over delivery terms.',
    );
    await user.click(screen.getByRole('button', { name: 'Create case' }));

    await waitFor(() => {
      expect(createCase).toHaveBeenCalledWith({
        title: 'Doe v. Roe',
        caseFacts: 'A contract dispute over delivery terms.',
        courtId: null,
      });
    });
  });

  it('requires and sends the selected court when the catalog has courts (§13)', async () => {
    vi.spyOn(api, 'getCourts').mockResolvedValue([
      {
        id: 'court-1',
        name: 'Test Commercial Court',
        jurisdictionDescription: null,
        isActive: true,
      },
    ]);
    const createCase = vi
      .spyOn(api, 'createCase')
      .mockResolvedValue({ ...created, courtId: 'court-1' });
    const user = userEvent.setup();
    renderWithProviders(<CaseUpload />);

    await user.type(await screen.findByLabelText('Case title'), 'Doe v. Roe');
    await user.type(screen.getByLabelText('Case facts'), 'Facts.');
    await user.selectOptions(await screen.findByLabelText('Court'), 'court-1');
    await user.click(screen.getByRole('button', { name: 'Create case' }));

    await waitFor(() => {
      expect(createCase).toHaveBeenCalledWith({
        title: 'Doe v. Roe',
        caseFacts: 'Facts.',
        courtId: 'court-1',
      });
    });
  });
});
