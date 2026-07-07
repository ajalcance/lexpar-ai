/**
 * File: src/components/ProtectedRoute.tsx
 * Purpose: Route guard for authenticated pages. Redirects to /login when there is no token, and
 *   otherwise validates the session against the real backend (GET /api/auth/me) before rendering
 *   the nested routes — a stale/expired token is rejected, not trusted on presence alone.
 * Depends on: react-router-dom, @tanstack/react-query, lib/api.ts, store/auth.ts
 * Related: App.tsx (wraps the protected route branch)
 * Security notes: This is a UX guard; the backend still enforces bearer auth on every request.
 *   On a 401 the api layer clears the token, which also trips the redirect here.
 */

import { useEffect } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as api from '@/lib/api';
import { useAuthStore } from '@/store/auth';

export function ProtectedRoute() {
  const token = useAuthStore((state) => state.token);
  const setUser = useAuthStore((state) => state.setUser);

  const { data: user, isLoading, isError } = useQuery({
    queryKey: ['me'],
    queryFn: api.getCurrentUser,
    enabled: !!token,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (user) {
      setUser(user);
    }
  }, [user, setUser]);

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Checking your session…
      </div>
    );
  }

  if (isError) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
