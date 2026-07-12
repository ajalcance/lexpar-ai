/**
 * File: src/components/ui/skeleton.tsx
 * Purpose: A neutral animated placeholder block for loading states — a shared alternative to the
 *   bare "Loading…" text the app used everywhere, so waits read as "content arriving" rather than
 *   "something broke". Pulses under motion-safe only; a static muted block under reduced motion.
 * Depends on: lib/utils (cn)
 * Related: pages/Dashboard.tsx, pages/Scorecard.tsx (loading states)
 */

import { cn } from '@/lib/utils';

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn('motion-safe:animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  );
}
