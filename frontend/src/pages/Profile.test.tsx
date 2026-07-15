/**
 * File: src/pages/Profile.test.tsx
 * Purpose: Tests for the read-only profile — it renders the identity from the auth store and
 *   offers Sign out. No roles: every account is a self-owned island (no role badge).
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
};

describe('Profile', () => {
  afterEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  it('shows the account identity and Sign out', () => {
    useAuthStore.setState({ user: attorney, token: 't' });
    renderWithProviders(<Profile />);

    expect(screen.getByText('Demo Attorney')).toBeInTheDocument();
    expect(screen.getByText('a@example.com')).toBeInTheDocument();
    expect(screen.getByText('Solo Practice')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign out/ })).toBeInTheDocument();
  });

  it('renders no role badge (roles were removed)', () => {
    useAuthStore.setState({ user: attorney, token: 't' });
    renderWithProviders(<Profile />);

    expect(screen.queryByText('Administrator')).not.toBeInTheDocument();
    expect(screen.queryByText('Attorney')).not.toBeInTheDocument();
  });
});
