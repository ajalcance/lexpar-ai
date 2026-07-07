# Project Plan & Task Log

**Status:** Working file, not a static reference. Claude writes a plan here before starting any
non-trivial task (3+ steps), checks items off as it goes, and adds a short result note when done.

## How to use this file

- **Before a multi-step task:** write the plan here, confirm it looks right, then start.
- **While working:** check off steps as they're completed.
- **When done:** add a one-line result summary under the task.

## Format

```
### [Task name] — status: in progress | done
- [ ] step one
- [ ] step two

**Result:** short summary once done.
```

## Current plan

### Scaffold frontend (Vite + React + TS + Tailwind + shadcn/ui, mock data) — status: done

**Goal:** Stand up `frontend/` with all five routes from ARCHITECTURE.md §4, driven entirely by
in-memory mock data. Every data access goes through `lib/api.ts` so swapping to the real backend
later is a contained change. No real backend, LiveKit, or auth provider yet.

**Scaffold & tooling**
- [x] `npm create vite` → `frontend/` (react-ts template; strict mode on by default)
- [x] Add Tailwind CSS + configure `@/` path alias in `vite.config.ts` + `tsconfig`
- [x] `shadcn init` non-interactively (defaults), add primitives the pages need
      (button, card, input, label, textarea, badge)
- [x] Install runtime deps: `react-router-dom`, `zustand`, `@tanstack/react-query`,
      `@livekit/components-react`, `livekit-client`

**Data layer (the single contained swap point)**
- [x] `lib/types.ts` — shared types (User, Case, Session, Transcript, Scorecard) using the
      canonical vocabulary from DEVELOPER_GUIDELINES §4
- [x] `lib/mockData.ts` — in-memory fixtures (cases, one scripted session + transcript, scorecard)
- [x] `lib/api.ts` — the ONLY data-access module; async functions returning mock data
      (login, getCases, getCase, createCase, createSession, getSession, getScorecard). Real
      `fetch` calls drop in here later; pages never change.
- [x] `lib/livekit.ts` — thin wrapper over `livekit-client` (connect/disconnect helpers);
      installed and typed now, not yet exercised by the scripted mock

**State**
- [x] `store/auth.ts` — Zustand; token + user in memory only (not localStorage); login via api
- [x] `store/session.ts` — Zustand; active-session UI state

**Pages (one component per file; no fetch/transform logic inside components)**
- [x] `pages/Login.tsx` — form → `api.login` (mock accepts admin/admin) → store token → /dashboard
- [x] `pages/Dashboard.tsx` — list cases via TanStack Query + `api.getCases`
- [x] `pages/CaseUpload.tsx` — case-facts/upload form → `api.createCase` → redirect
- [x] `pages/SparringRoom.tsx` — scripted mock session (see below)
- [x] `pages/Scorecard.tsx` — post-session results from `api.getScorecard`

**SparringRoom scripted mock**
- [x] `hooks/useSparringSession.ts` — drives a hardcoded transcript sequence on a timer
      (logic in the hook, not the component)
- [x] `components/TranscriptLine.tsx` — renders a line by speaker; the one line flagged
      `was_interruption` (opposing-counsel objection) gets distinct treatment (badge + accent)
- [x] "End session" control appears after the script completes → routes to the scorecard

**Routing & guard**
- [x] `App.tsx` — react-router routes for all five paths + `ProtectedRoute` guard
      (redirects to /login when the auth store holds no token)

**File conventions (every file)**
- [x] Mandatory header (Purpose / Depends on / Related; Security notes on auth-touching files),
      strict typing, files kept ~150–300 lines

**Tests (Vitest + React Testing Library — critical flows per DEVELOPER_GUIDELINES §6)**
- [x] Configure Vitest + RTL + jsdom
- [x] `Login` test — admin/admin succeeds, stores token; wrong creds rejected
- [x] `CaseUpload` test — submitting the form calls `api.createCase`
- [x] `Scorecard` test — renders scorecard fields from mock data

**Run**
- [x] `npm run dev`, confirm boot, report the exact localhost URL

**Deferred (flagged, not doing now):** real backend wiring, real LiveKit room connection, real
auth provider.

**Result:** Frontend scaffolded and verified. All five routes work against mock data through
`lib/api.ts`; login (admin/admin) → dashboard → scripted SparringRoom (8 lines on a timer, the
objection line styled distinctly) → scorecard. `type-check`, `build`, and 4 Vitest tests all
pass; `lint` clean (only advisory fast-refresh warnings inside generated shadcn UI files).
Toolchain note: pinned Vite to 7 + plugin-react to 5 for Vitest compatibility (see docs/LESSONS.md).
Dev server: http://localhost:5173/.
