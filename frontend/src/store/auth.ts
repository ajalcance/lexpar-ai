/**
 * File: src/store/auth.ts
 * Purpose: Client auth state — the bearer token and current user — held in memory via
 *   Zustand. Deliberately NOT persisted to localStorage (per ARCHITECTURE §4) so the later
 *   swap to real auth needs no storage migration and no token sits in persistent storage.
 * Depends on: lib/api.ts (login), lib/types.ts
 * Related: components/ProtectedRoute.tsx (reads token), pages/Login.tsx (calls login)
 * Security notes: Token lives only in memory and is cleared on logout / full reload. Do not
 *   add persistence here without revisiting the auth-replacement plan (ARCHITECTURE §11).
 */

import { create } from 'zustand';
import * as api from '@/lib/api';
import type { User } from '@/lib/types';

interface AuthState {
  token: string | null;
  user: User | null;
  /** Authenticate via the API and store the resulting token + user. Throws on failure. */
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  login: async (username, password) => {
    const { token, user } = await api.login(username, password);
    set({ token, user });
  },
  logout: () => set({ token: null, user: null }),
}));
