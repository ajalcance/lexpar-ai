/**
 * File: src/components/DashboardGuide.tsx
 * Purpose: A reviewer/judge aid on the Cases dashboard (companion to the sparring DemoScript) —
 *   two ways to test: open the ready SARC case, or build one in two steps (create a courtroom in
 *   Court administration, then a case). Because all reviewers share the demo account, the case
 *   list grows; this points them at the flagged "Start here" case so they don't get lost.
 * Depends on: lib/flags (DEMO_CASE_TITLE), lib/utils (cn)
 * Related: pages/Dashboard.tsx (renders this in the left column), components/DemoScript.tsx
 */

import { Link } from 'react-router-dom';
import { DEMO_CASE_TITLE } from '@/lib/flags';
import { cn } from '@/lib/utils';

/** `demoCaseId` (when the ready case is in the list) makes the case name a direct link — wired from
 *  the live case's real id in Dashboard, so it never hardcodes a UUID that would break on recreate. */
export function DashboardGuide({
  className,
  demoCaseId,
}: {
  className?: string;
  demoCaseId?: string;
}) {
  return (
    <aside
      className={cn(
        'flex flex-col gap-4 rounded-lg border border-amber-500/30 bg-muted/30 p-5 text-sm',
        className,
      )}
    >
      <div>
        <p className="text-xs font-medium tracking-wide text-amber-600 uppercase dark:text-amber-500">
          For reviewers &amp; judges
        </p>
        <h2 className="mt-1 text-base font-semibold">Two ways to test</h2>
      </div>

      <div className="flex flex-col gap-1">
        <p className="font-medium">1. Fastest — open the ready case</p>
        <p className="text-xs text-muted-foreground">
          {demoCaseId ? (
            <Link
              to={`/case/${demoCaseId}`}
              className="font-medium text-amber-600 underline underline-offset-2 hover:text-amber-700 dark:text-amber-500"
            >
              {DEMO_CASE_TITLE}
            </Link>
          ) : (
            <strong>{DEMO_CASE_TITLE}</strong>
          )}{' '}
          is set up and ready (or find the{' '}
          <span className="font-medium text-amber-600 dark:text-amber-500">Start here</span> tag
          below). Start a session and the page shows a read-aloud script — just read it.
        </p>
      </div>

      <div className="flex flex-col gap-1 border-t pt-3">
        <p className="font-medium">2. Or build your own in two steps</p>
        <ol className="ml-4 list-decimal text-xs text-muted-foreground [&>li]:mt-1">
          <li>
            Open <strong>Court administration</strong> (top-right) and create a courtroom, then
            upload its rule PDF.
          </li>
          <li>
            Click <strong>New case</strong>, fill in the parties and the side you represent, and
            attach the pleading (PDF). Then start a session.
          </li>
        </ol>
      </div>

      <p className="border-t pt-3 text-[11px] leading-relaxed text-muted-foreground">
        Everyone shares this demo account, so cases other reviewers create appear here too — the{' '}
        <span className="font-medium text-amber-600 dark:text-amber-500">Start here</span> case is
        the one to test.
      </p>
    </aside>
  );
}
