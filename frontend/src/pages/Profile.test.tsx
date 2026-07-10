/**
 * File: src/pages/Profile.test.tsx
 * Purpose: Tests for the read-only profile — it renders the identity from the auth store and the
 *   correct role badge (Attorney vs Administrator), and offers Sign out.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Profile, store/auth
 */

import { afterEach, describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { Profile } from '@/pages/Profile';
import { useAuthStore } from '@/store/auth';
import type { User } from '@/lib/types';

const attorney: User = {
  id: 'u1',
  email: 'a@example.com',
  fullName: 'Demo Attorney',
  firmName: 'Solo Practice',
  role: 'attorney',
};

describe('Profile', () => {
  afterEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  it('shows the attorney identity and role badge', () => {
    useAuthStore.setState({ user: attorney, token: 't' });
    renderWithProviders(<Profile />);

    expect(screen.getByText('Demo Attorney')).toBeInTheDocument();
    expect(screen.getByText('a@example.com')).toBeInTheDocument();
    expect(screen.getByText('Solo Practice')).toBeInTheDocument();
    expect(screen.getByText('Attorney')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign out/ })).toBeInTheDocument();
  });

  it('shows the Administrator badge for an admin', () => {
    useAuthStore.setState({ user: { ...attorney, role: 'admin' }, token: 't' });
    renderWithProviders(<Profile />);

    expect(screen.getByText('Administrator')).toBeInTheDocument();
  });
});
