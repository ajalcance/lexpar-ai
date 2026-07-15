/**
 * File: src/pages/Courts.test.tsx
 * Purpose: Critical-flow tests for the §13 Courts surface under the PER-USER model (no roles): any
 *   authenticated user manages their OWN courts — court creation calls the API, and the catalog is
 *   the landing view with archived forums badged.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Courts, lib/api, store/auth
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { Courts } from '@/pages/Courts';
import * as api from '@/lib/api';
import { useAuthStore } from '@/store/auth';
import type { User } from '@/lib/types';

const user: User = {
  id: 'u1',
  email: 'a@example.com',
  fullName: 'Demo Attorney',
  firmName: null,
};

describe('Courts', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it('creates a court through the API (form auto-opens on an empty catalog)', async () => {
    useAuthStore.setState({ user, token: 't' });
    vi.spyOn(api, 'getCourts').mockResolvedValue([]);
    const createCourt = vi.spyOn(api, 'createCourt').mockResolvedValue({
      id: 'court-1',
      name: 'Test Commercial Court',
      jurisdictionDescription: 'test forum',
      isActive: true,
      archived: false,
    });
    const u = userEvent.setup();
    renderWithProviders(<Courts />);

    await u.type(await screen.findByLabelText('Court name'), 'Test Commercial Court');
    await u.type(screen.getByLabelText('Jurisdiction description'), 'test forum');
    await u.click(screen.getByRole('button', { name: 'Create court' }));

    await waitFor(() => {
      expect(createCourt).toHaveBeenCalledWith({
        name: 'Test Commercial Court',
        jurisdictionDescription: 'test forum',
      });
    });
  });

  it('lands on the courts list — every forum visible, archived ones badged, create form closed', async () => {
    useAuthStore.setState({ user, token: 't' });
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
    renderWithProviders(<Courts />);

    // The catalog is the landing view — both forums listed, the archived one badged.
    expect(await screen.findByText('Special Commercial Court')).toBeInTheDocument();
    expect(screen.getByText('Retired Forum')).toBeInTheDocument();
    expect(screen.getByText('Archived')).toBeInTheDocument();
    // The full (owner) catalog is requested with archived included, and the create form stays
    // closed when courts exist (creation is a toggled affordance, not the landing view).
    expect(getCourts).toHaveBeenCalledWith({ includeArchived: true });
    expect(screen.queryByLabelText('Court name')).not.toBeInTheDocument();
  });
});
