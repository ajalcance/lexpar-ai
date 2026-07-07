/**
 * File: src/components/ProtectedRoute.tsx
 * Purpose: Route guard for authenticated pages. Redirects to /login when the auth store
 *   holds no token; otherwise renders the nested routes.
 * Depends on: react-router-dom, store/auth.ts
 * Related: App.tsx (wraps the protected route branch)
 * Security notes: This is the single client-side gate for authed routes. It is a UX guard,
 *   not a security boundary — the backend still enforces bearer auth on every request.
 */

import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

export function ProtectedRoute() {
  const token = useAuthStore((state) => state.token);

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
