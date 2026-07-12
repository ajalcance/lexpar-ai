/**
 * File: src/pages/CaseUpload.test.tsx
 * Purpose: Critical-flow test for case creation (DEVELOPER_GUIDELINES §6) — submitting the form
 *   calls api.createCase with the structured CASE PROFILE (caption, number, parties, the side the
 *   attorney represents, relief sought) plus optional context.
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
    title: 'Metrobank v. SARC',
    caseNumber: 'G.R. No. 218738',
    petitioner: 'Metropolitan Bank & Trust Company',
    respondent: 'Salazar Realty Corporation',
    representedParty: 'respondent' as const,
    reliefSought: 'Nullification of the mortgage.',
    caseFacts: '',
    courtId: null,
    createdAt: '2026-07-07T00:00:00Z',
  };

  /** Fill the required profile fields (parties, side, relief). */
  async function fillProfile(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText('Case title'), 'Metrobank v. SARC');
    await user.type(screen.getByLabelText('Case number (optional)'), 'G.R. No. 218738');
    await user.type(
      screen.getByLabelText('Petitioner / plaintiff'),
      'Metropolitan Bank & Trust Company',
    );
    await user.type(
      screen.getByLabelText('Respondent / defendant'),
      'Salazar Realty Corporation',
    );
    await user.selectOptions(screen.getByLabelText('You represent'), 'respondent');
    await user.type(screen.getByLabelText('Relief sought'), 'Nullification of the mortgage.');
  }

  it('submits the case profile without a court when no courts are configured (with notice)', async () => {
    vi.spyOn(api, 'getCourts').mockResolvedValue([]);
    const createCase = vi.spyOn(api, 'createCase').mockResolvedValue(created);
    const user = userEvent.setup();
    renderWithProviders(<CaseUpload />);

    expect(await screen.findByText(/No courts configured yet/)).toBeInTheDocument();
    await fillProfile(user);
    await user.click(screen.getByRole('button', { name: 'Create case' }));

    await waitFor(() => {
      expect(createCase).toHaveBeenCalledWith({
        title: 'Metrobank v. SARC',
        caseNumber: 'G.R. No. 218738',
        petitioner: 'Metropolitan Bank & Trust Company',
        respondent: 'Salazar Realty Corporation',
        representedParty: 'respondent',
        reliefSought: 'Nullification of the mortgage.',
        caseFacts: '',
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

    await screen.findByLabelText('Case title');
    await fillProfile(user);
    await user.selectOptions(await screen.findByLabelText('Court'), 'court-1');
    await user.click(screen.getByRole('button', { name: 'Create case' }));

    await waitFor(() => {
      expect(createCase).toHaveBeenCalledWith(
        expect.objectContaining({
          representedParty: 'respondent',
          courtId: 'court-1',
        }),
      );
    });
  });
});
