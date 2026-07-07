/**
 * File: src/store/auth.ts
 * Purpose: Client auth state — the bearer token and current user — held in memory via Zustand.
 *   Deliberately NOT persisted to localStorage (per ARCHITECTURE §4) so the token never sits in
 *   persistent browser storage. login() authenticates against the real backend, then loads the
 *   user from /api/auth/me.
 * Depends on: lib/api.ts (login, getCurrentUser), lib/types.ts
 * Related: components/ProtectedRoute.tsx (validates via /me), pages/Login.tsx (calls login)
 * Security notes: Token lives only in memory and is cleared on logout, 401, or full reload. Do
 *   not add persistence here without revisiting the auth-replacement plan (ARCHITECTURE §11).
 */

import { create } from 'zustand';
import * as api from '@/lib/api';
import type { User } from '@/lib/types';

interface AuthState {
  token: string | null;
  user: User | null;
  /** Authenticate, store the JWT, then load the current user. Throws (and rolls back) on failure. */
  login: (username: string, password: string) => Promise<void>;
  /** Replace the cached user (e.g. after ProtectedRoute revalidates via /me). */
  setUser: (user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  login: async (username, password) => {
    const token = await api.login(username, password);
    set({ token });
    try {
      const user = await api.getCurrentUser();
      set({ user });
    } catch (error) {
      set({ token: null, user: null });
      throw error;
    }
  },
  setUser: (user) => set({ user }),
  logout: () => set({ token: null, user: null }),
}));
