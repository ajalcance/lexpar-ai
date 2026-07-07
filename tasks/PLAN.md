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

---

### Build backend (fully) + agents skeleton — status: done

**Scope split (explicit):**
- **Backend — FULLY IMPLEMENTED:** models, schemas, services, all §5 routes, real bearer-token
  auth stub, pytest tests, Dockerfile. Runnable end to end.
- **Agents — SKELETON ONLY (pending API keys):** five `.py` files, each a header docstring +
  eventual-responsibility description + `# TODO: implement once Fireworks/Deepgram/ElevenLabs
  keys are available`. No logic, no requirements/Dockerfile, NOT wired into CI.
- **Infra:** docker-compose for Postgres + MinIO (local dev).
- **Frontend:** untouched — stays on mock data.

**Backend — app skeleton & config**
- [ ] `app/config.py` (pydantic-settings, reads .env per §9), `app/db.py` (engine, Base, `get_db`
      DI dependency), `app/main.py` (app, router registration, `/health`, request-id log middleware)
- [ ] Portable models so prod=Postgres and tests=SQLite share one schema: SQLAlchemy `Uuid` type +
      Python-side `uuid4` / `datetime.now(tz)` defaults (no `gen_random_uuid()` / `TIMESTAMPTZ`
      server defaults). This is what lets pytest run on SQLite with no Postgres in CI.

**Backend — models (§8)** `models/{user,case,session,transcript,scorecard}.py`
- [ ] users, cases, sessions, transcripts, scorecards per §8; add `deleted_at` (soft delete,
      DEV_GUIDELINES §8) to content tables; tag `# SENSITIVE: attorney work product` on
      `case_facts` / `transcript.content` / scorecard fields

**Backend — schemas (Pydantic ≠ SQLAlchemy, §5/DEV §5)** `schemas/*`
- [ ] auth (LoginRequest, TokenResponse, UserOut), case (CaseCreate, CaseOut), session
      (SessionCreate, SessionOut, TranscriptOut, SessionDetailOut), scorecard (ScorecardOut),
      livekit (LiveKitTokenOut)

**Backend — auth (real bearer check, NOT a bypass)**
- [ ] `security.py` — JWT create/decode (PyJWT + JWT_SECRET), `get_current_user` HTTPBearer
      dependency → 401 on missing/invalid token (the check is real; only the provider is stubbed)
- [ ] `services/auth_service.py` — AUTH_MODE=stub accepts admin/admin only and issues a JWT for
      the stub user; non-stub mode → 501 Not Implemented

**Backend — services (logic) + routes (thin, §5)**
- [ ] `services/` + `api/`: auth (login, me), cases (create/list/detail, owner-scoped), sessions
      (create, detail+transcript), scorecards (get; requires completed), livekit_token (mint)
- [ ] `session_service.transition_status` — enforce in_progress→completed / in_progress→abandoned;
      terminal states reject further transitions (this is the tested state machine)

**Backend — LiveKit token (§5)**
- [ ] `services/livekit_service.py` — mint a real LiveKit-format JWT (video grant, signed with
      LIVEKIT_API_SECRET). Endpoint works now; the room isn't exercised until the agents land.

**Migrations (Alembic — chosen)**
- [ ] Alembic configured (`env.py` reads DATABASE_URL from settings, `target_metadata=Base.metadata`)
      + hand-written `0001_initial` creating all five tables. Prod/dev runs `alembic upgrade head`;
      tests build the schema via `Base.metadata.create_all` on SQLite (no Alembic in the test path).

**Infra**
- [ ] `infra/docker-compose.yml` — Postgres 16 + MinIO (+ bucket-init); `backend/Dockerfile`
      (uvicorn `app.main:app`)

**Tests (pytest, DEV §6) — backend only**
- [ ] `tests/conftest.py` — SQLite engine + `get_db` override + TestClient + auth-token fixtures
- [ ] `tests/test_auth.py` — no token→401, bad token→401, admin/admin→token, `/me`→user,
      wrong creds→401, protected route without token→401
- [ ] `tests/test_sessions.py` — valid transitions succeed; terminal→other rejected; scorecard
      gated on a completed session

**Agents — SKELETON ONLY (no impl, pending keys)**
- [ ] `agents/{main,opposing_counsel,judge,objection_classifier,llm_router}.py` — header docstring
      + eventual responsibility + `# TODO: implement once Fireworks/Deepgram/ElevenLabs keys are
      available`. Prompts already exist in `agents/prompts/`.

**CI**
- [ ] Remove the `agents` job from `.github/workflows/ci.yml`; scope `docker-build` matrix to
      `[backend]` (frontend/agents images need Dockerfiles — deferred). Backend job (ruff + pytest)
      stays and must pass.

**Docs (self-updating rule)**
- [ ] Update ARCHITECTURE §8 to note `deleted_at` soft-delete columns + the portable-types
      (`Uuid` / Python defaults) decision; append a LESSONS.md entry if a gotcha emerges

**Verify**
- [ ] Bring up Postgres via compose, run `uvicorn`, confirm `GET /health`; provide a curl recipe
      for login → `/me`

**Decisions (resolved):** Alembic migrations now; LiveKit token mints a real JWT; case create is
JSON now with MinIO file upload deferred.

**Result:** Backend fully implemented and verified. All nine §5 routes live (auth login/me, cases
CRUD, sessions create/detail, scorecard, livekit token) + `/health`; real HTTPBearer auth stub
(admin/admin → JWT; missing/invalid token → 401). SQLAlchemy models (portable `Uuid` + Python
defaults, soft-delete `deleted_at`, `# SENSITIVE` tags), Pydantic schemas, thin routes over a
service layer, Alembic `0001_initial`, `backend/Dockerfile`, and `infra/docker-compose.yml`
(Postgres + MinIO). **ruff clean; 13 pytest tests pass** (auth checks + session state
transitions). Verified live: `alembic upgrade head` on SQLite, then curl through health → login →
/me (401 without token) → create case → create session → livekit token. Agents: five
header-only skeletons with the `# TODO … keys` marker, removed from the CI test job (`docker-build`
scoped to `[backend]`). ARCHITECTURE §8 + LESSONS.md updated. Frontend untouched.

Verify locally: `docker compose -f infra/docker-compose.yml up -d` → (in `backend/`, with deps
installed) `alembic upgrade head` → `uvicorn app.main:app` → `curl localhost:8000/health`.
