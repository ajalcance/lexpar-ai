/**
 * File: src/pages/Profile.tsx
 * Purpose: The attorney's profile — a read-only view of their identity (name/email/firm when
 *   present) and role, plus sign out. Scoped deliberately to what is actually wired: everything
 *   shown comes from GET /api/auth/me (the auth store). Editing name/firm and password management
 *   are intentionally absent until a real update endpoint + real auth land (ARCHITECTURE §11) —
 *   no placeholder settings that connect to nothing.
 * Depends on: react-router-dom, store/auth.ts, components/Breadcrumbs, components/ui/*
 * Related: components/UserMenu.tsx (links here), docs/ARCHITECTURE.md §4
 * Security notes: Renders identity only; sign out clears the in-memory token (no persistent store).
 */

import { useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { useAuthStore } from '@/store/auth';

/** One labelled identity row; hidden entirely when the field is empty. */
function Field({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

export function Profile() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: 'Cases', to: '/dashboard' }, { label: 'Profile' }]} />

      <div>
        <h1 className="text-2xl font-semibold">Profile</h1>
        <p className="text-sm text-muted-foreground">Your account details.</p>
      </div>

      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle className="text-lg">Account</CardTitle>
          <CardDescription>
            {user?.role === 'admin'
              ? 'You can manage courts and procedural rules from Court administration.'
              : 'Your identity for this workspace.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Field label="Name" value={user?.fullName ?? null} />
          <Field label="Email" value={user?.email ?? null} />
          <Field label="Firm" value={user?.firmName ?? null} />
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Role</span>
            <div>
              <Badge variant={user?.role === 'admin' ? 'default' : 'secondary'}>
                {user?.role === 'admin' ? 'Administrator' : 'Attorney'}
              </Badge>
            </div>
          </div>
          <div className="pt-2">
            <Button variant="outline" onClick={handleLogout}>
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
