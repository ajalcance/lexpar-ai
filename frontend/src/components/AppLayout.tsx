/**
 * File: src/components/AppLayout.tsx
 * Purpose: Shared chrome for authenticated pages — a topbar with the product name, the primary
 *   "Cases" and "Courts" nav items (with active state), and the user menu — wrapping the routed
 *   page content. No roles: every account manages its own courts (Courts is always shown).
 * Depends on: react-router-dom, store/auth.ts, components/UserMenu, components/ui/*
 * Related: App.tsx (renders this inside the protected branch), components/Breadcrumbs.tsx
 */

import { Link, Outlet, useLocation } from 'react-router-dom';
import { Scale } from 'lucide-react';
import { UserMenu } from '@/components/UserMenu';
import { cn } from '@/lib/utils';

export function AppLayout() {
  const location = useLocation();

  // "Cases" is the home destination; highlight it on the list and any case-scoped page.
  const onCases =
    location.pathname === '/dashboard' || location.pathname.startsWith('/case');
  const onCourts = location.pathname.startsWith('/courts');

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b print:hidden">
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
              <Link
                to="/courts"
                className={cn(
                  'rounded-md px-3 py-1.5 text-sm hover:bg-accent hover:text-foreground',
                  onCourts ? 'font-medium text-foreground' : 'text-muted-foreground',
                )}
              >
                Courts
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-3">
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
