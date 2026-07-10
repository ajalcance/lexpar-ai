/**
 * File: src/components/UserMenu.tsx
 * Purpose: The authenticated user's identity + menu in the topbar — replaces the old inert email
 *   text. A disclosure button (name or email) opens a small panel with a Profile link and Sign
 *   out. Built as a plain accessible disclosure (button + aria-expanded + click-outside) because
 *   no shadcn dropdown primitive is installed in this project (house pattern: minimal, native).
 * Depends on: react, react-router-dom, store/auth.ts, components/ui/button
 * Related: components/AppLayout.tsx (renders this), pages/Profile.tsx (the linked page)
 * Security notes: Sign out clears the in-memory token; it never touches persistent storage.
 */

import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronDown, LogOut, User as UserIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/store/auth';

export function UserMenu() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on any click outside the menu, so it behaves like a normal dropdown.
  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  // Prefer the attorney's name; fall back to their email so the trigger is never empty.
  const label = user?.fullName || user?.email || 'Account';

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <UserIcon className="size-4" />
        <span className="max-w-[12rem] truncate">{label}</span>
        <ChevronDown className="size-3.5" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-2 w-48 rounded-md border bg-popover p-1 shadow-md"
        >
          <Link
            to="/profile"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
          >
            <UserIcon className="size-4" />
            Profile
          </Link>
          <div className="my-1 h-px bg-border" />
          <div className="px-1 pb-1">
            <Button
              variant="outline"
              size="sm"
              className="w-full justify-start"
              onClick={handleLogout}
            >
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
