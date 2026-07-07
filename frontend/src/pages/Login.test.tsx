/**
 * File: src/pages/Login.test.tsx
 * Purpose: Critical-flow test for login (DEVELOPER_GUIDELINES §6) — admin/admin succeeds and
 *   stores the token; wrong credentials are rejected with an error and no token.
 * Depends on: vitest, @testing-library/*, test/utils, pages/Login, store/auth
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { Login } from '@/pages/Login';
import { useAuthStore } from '@/store/auth';

describe('Login', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  it('signs in with admin/admin and stores the token', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Login />);

    await user.type(screen.getByLabelText('Username'), 'admin');
    await user.type(screen.getByLabelText('Password'), 'admin');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(useAuthStore.getState().token).toBe('stub-token-admin');
    });
  });

  it('rejects invalid credentials with an error message', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Login />);

    await user.type(screen.getByLabelText('Username'), 'admin');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(
      await screen.findByText('Invalid username or password.'),
    ).toBeInTheDocument();
    expect(useAuthStore.getState().token).toBeNull();
  });
});
