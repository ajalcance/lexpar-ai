/**
 * File: src/components/AppLayout.tsx
 * Purpose: Shared chrome for authenticated pages — a top bar with the app name, the current
 *   user, and a logout button — wrapping the routed page content.
 * Depends on: react-router-dom, store/auth.ts, components/ui/button
 * Related: App.tsx (renders this inside the protected branch)
 */

import { Link, Outlet, useNavigate } from 'react-router-dom';
import { LogOut, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/store/auth';

export function AppLayout() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link to="/dashboard" className="flex items-center gap-2 font-semibold">
            <Scale className="size-5 text-primary" />
            LexPar AI
          </Link>
          <div className="flex items-center gap-4">
            {user && (
              <span className="text-sm text-muted-foreground">{user.email}</span>
            )}
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="size-4" />
              Log out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
