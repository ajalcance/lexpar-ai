/**
 * File: src/pages/CaseUpload.test.tsx
 * Purpose: Critical-flow test for case upload (DEVELOPER_GUIDELINES §6) — submitting the form
 *   calls api.createCase with the entered title and facts.
 * Depends on: vitest, @testing-library/*, test/utils, pages/CaseUpload, lib/api
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { CaseUpload } from '@/pages/CaseUpload';
import * as api from '@/lib/api';

describe('CaseUpload', () => {
  it('submits the form through api.createCase', async () => {
    const user = userEvent.setup();
    const createCase = vi.spyOn(api, 'createCase');
    renderWithProviders(<CaseUpload />);

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
      });
    });

    createCase.mockRestore();
  });
});
