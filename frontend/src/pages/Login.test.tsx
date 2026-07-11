/**
 * File: src/pages/Login.test.tsx
 * Purpose: Critical-flow test for login (DEVELOPER_GUIDELINES §6) — real credentials authenticate
 *   via the API and store the token; a rejected login surfaces an error and stores nothing.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Login, store/auth, lib/api
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { Login } from '@/pages/Login';
import { useAuthStore } from '@/store/auth';
import * as api from '@/lib/api';

const fakeUser = {
  id: 'u1',
  email: 'attorney@example.com',
  fullName: 'Test Attorney',
  role: 'admin' as const,
  firmName: 'Solo Practice',
};

describe('Login', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('signs in with real credentials and stores the token', async () => {
    vi.spyOn(api, 'login').mockResolvedValue('jwt-token');
    vi.spyOn(api, 'getCurrentUser').mockResolvedValue(fakeUser);
    const user = userEvent.setup();
    renderWithProviders(<Login />);

    await user.type(screen.getByLabelText('Email'), 'attorney@example.com');
    await user.type(screen.getByLabelText('Password'), 'test-password-123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(useAuthStore.getState().token).toBe('jwt-token');
    });
    expect(api.login).toHaveBeenCalledWith('attorney@example.com', 'test-password-123');
  });

  it('rejects invalid credentials with an error message', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new Error('Invalid username or password.'));
    const user = userEvent.setup();
    renderWithProviders(<Login />);

    await user.type(screen.getByLabelText('Email'), 'attorney@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(
      await screen.findByText('Invalid username or password.'),
    ).toBeInTheDocument();
    expect(useAuthStore.getState().token).toBeNull();
  });
});
