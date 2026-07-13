/**
 * File: src/lib/flags.ts
 * Purpose: Build-time feature flags (Vite `import.meta.env`, VITE_-prefixed). Kept in one place so
 *   a page doesn't parse env strings inline.
 * Related: backend/app/config.py (the server-side counterparts — the real enforcement)
 */

/** Archive/purge UI (Danger Zones). Off on the public hackathon demo so a shared-credential
 *  visitor can't delete/hide the demo data. The BACKEND is the real control
 *  (DESTRUCTIVE_ACTIONS_ENABLED → 403); this only hides the buttons. Default on. */
export const DESTRUCTIVE_ACTIONS_ENABLED =
  import.meta.env.VITE_DESTRUCTIVE_ACTIONS_ENABLED !== 'false';

/** Reviewer/judge aids (the sparring read-aloud script + the dashboard "how to test" guide).
 *  On by default; the same VITE_SHOW_DEMO_SCRIPT flag toggles them together. */
export const SHOW_REVIEWER_AIDS = import.meta.env.VITE_SHOW_DEMO_SCRIPT !== 'false';

/** The ready-made demo case reviewers should test first — flagged with a "Start here" marker on
 *  the dashboard so it's obvious among cases other reviewers create (all share the demo account).
 *  Override with VITE_DEMO_CASE_TITLE if the case is renamed. */
export const DEMO_CASE_TITLE =
  (import.meta.env.VITE_DEMO_CASE_TITLE as string | undefined)?.trim() ||
  'Metrobank v. Salazar Realty Corporation (SARC)';

/** True for the case that carries the ready demo (exact, case-insensitive title match). */
export function isDemoCase(title: string): boolean {
  return title.trim().toLowerCase() === DEMO_CASE_TITLE.toLowerCase();
}
