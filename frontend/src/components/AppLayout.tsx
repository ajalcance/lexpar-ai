/**
 * File: src/components/AppLayout.tsx
 * Purpose: Shared chrome for authenticated pages — a topbar with the product name, the primary
 *   "Cases" nav item (with active state), a role-gated Court-administration entry styled as a
 *   distinct pill, and the user menu — wrapping the routed page content.
 * Depends on: react-router-dom, store/auth.ts, components/UserMenu, components/ui/*
 * Related: App.tsx (renders this inside the protected branch), components/Breadcrumbs.tsx
 */

import { Link, Outlet, useLocation } from 'react-router-dom';
import { Scale, Shield } from 'lucide-react';
import { UserMenu } from '@/components/UserMenu';
import { useAuthStore } from '@/store/auth';
import { cn } from '@/lib/utils';

export function AppLayout() {
  const location = useLocation();
  const user = useAuthStore((state) => state.user);

  // "Cases" is the home destination; highlight it on the list and any case-scoped page.
  const onCases =
    location.pathname === '/dashboard' || location.pathname.startsWith('/case');
  const onAdmin = location.pathname.startsWith('/admin');

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2 font-semibold">
              <Scale className="size-5 text-primary" />
              LexPar AI
            </Link>
            <nav className="flex items-center gap-1">
              <Link
                to="/dashboard"
                className={cn(
                  'rounded-md px-3 py-1.5 text-sm hover:bg-accent hover:text-foreground',
                  onCases ? 'font-medium text-foreground' : 'text-muted-foreground',
                )}
              >
                Cases
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {user?.role === 'admin' && (
              <Link
                to="/admin"
                className={cn(
                  'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm',
                  onAdmin
                    ? 'border-primary/40 bg-primary/10 text-foreground'
                    : 'border-border text-muted-foreground hover:bg-accent hover:text-foreground',
                )}
              >
                <Shield className="size-4" />
                Court administration
              </Link>
            )}
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
