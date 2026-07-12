/**
 * File: src/pages/Admin.test.tsx
 * Purpose: Critical-flow tests for the §13 admin surface — role gating in the frontend (an
 *   attorney sees a denial, never the forms; defense in depth over the backend's 403) and court
 *   creation calling the API for an admin.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Admin, lib/api, store/auth
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { Admin } from '@/pages/Admin';
import * as api from '@/lib/api';
import { useAuthStore } from '@/store/auth';
import type { User } from '@/lib/types';

const attorney: User = {
  id: 'u1',
  email: 'a@example.com',
  fullName: 'Demo Attorney',
  firmName: null,
  role: 'attorney',
};

describe('Admin', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it('denies a non-admin without rendering any management UI', () => {
    useAuthStore.setState({ user: attorney, token: 't' });
    renderWithProviders(<Admin />);

    expect(screen.getByText(/Administrator role required/)).toBeInTheDocument();
    expect(screen.queryByText('Create a court')).not.toBeInTheDocument();
  });

  it('lets an admin create a court through the API (form auto-opens on an empty catalog)', async () => {
    useAuthStore.setState({ user: { ...attorney, role: 'admin' }, token: 't' });
    vi.spyOn(api, 'getCourts').mockResolvedValue([]);
    const createCourt = vi.spyOn(api, 'createCourt').mockResolvedValue({
      id: 'court-1',
      name: 'Test Commercial Court',
      jurisdictionDescription: 'test forum',
      isActive: true,
      archived: false,
    });
    const user = userEvent.setup();
    renderWithProviders(<Admin />);

    await user.type(await screen.findByLabelText('Court name'), 'Test Commercial Court');
    await user.type(screen.getByLabelText('Jurisdiction description'), 'test forum');
    await user.click(screen.getByRole('button', { name: 'Create court' }));

    await waitFor(() => {
      expect(createCourt).toHaveBeenCalledWith({
        name: 'Test Commercial Court',
        jurisdictionDescription: 'test forum',
      });
    });
  });

  it('lands on the courts list — every forum visible, archived ones badged, create form closed', async () => {
    useAuthStore.setState({ user: { ...attorney, role: 'admin' }, token: 't' });
    const getCourts = vi.spyOn(api, 'getCourts').mockResolvedValue([
      {
        id: 'court-1',
        name: 'Special Commercial Court',
        jurisdictionDescription: 'Commercial disputes',
        isActive: true,
        archived: false,
      },
      {
        id: 'court-2',
        name: 'Retired Forum',
        jurisdictionDescription: null,
        isActive: false,
        archived: true,
      },
    ]);
    renderWithProviders(<Admin />);

    // The catalog is the landing view — both forums listed, the archived one badged.
    expect(await screen.findByText('Special Commercial Court')).toBeInTheDocument();
    expect(screen.getByText('Retired Forum')).toBeInTheDocument();
    expect(screen.getByText('Archived')).toBeInTheDocument();
    // The admin catalog is requested (archived included), and the create form stays closed
    // when courts exist (creation is a toggled affordance, not the landing view).
    expect(getCourts).toHaveBeenCalledWith({ includeArchived: true });
    expect(screen.queryByLabelText('Court name')).not.toBeInTheDocument();
  });

});
