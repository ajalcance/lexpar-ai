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
