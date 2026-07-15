/**
 * File: src/components/Toaster.tsx
 * Purpose: Renders the app's transient toasts (lib/toast.ts) in a fixed bottom-right stack, color-
 *   coded by variant (red = error, green = success, neutral = info — matching the palette). Each is
 *   dismissible and auto-expires. Mounted once at the app root so every page (incl. Login) has it.
 * Depends on: react, lib/toast.ts, lib/utils (cn)
 * Related: App.tsx (mounts this), lib/toast.ts
 * Security notes: Presentational only — renders UI strings the caller supplied.
 */

import { X } from 'lucide-react';
import { useToastStore, type ToastVariant } from '@/lib/toast';
import { cn } from '@/lib/utils';

const VARIANT_CLASS: Record<ToastVariant, string> = {
  error: 'border-destructive/40 bg-destructive/10 text-destructive',
  success: 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400',
  info: 'border-border bg-background text-foreground',
};

export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed right-4 bottom-4 z-50 flex w-full max-w-sm flex-col gap-2 print:hidden"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={cn(
            'flex items-start justify-between gap-3 rounded-md border px-3 py-2 text-sm shadow-sm',
            'motion-safe:animate-in motion-safe:slide-in-from-bottom-2',
            VARIANT_CLASS[toast.variant],
          )}
        >
          <span className="whitespace-pre-line">{toast.message}</span>
          <button
            type="button"
            aria-label="Dismiss"
            className="shrink-0 opacity-60 hover:opacity-100"
            onClick={() => dismiss(toast.id)}
          >
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
