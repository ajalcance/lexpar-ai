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

---

### Connect frontend to the real backend — status: done

**Goal:** Replace mock data access with real HTTP calls for auth, cases, session creation, and
scorecard, while keeping SparringRoom's transcript scripted (no agents pipeline yet). All wiring
stays inside `lib/api.ts` (the swap point) so components barely change.

**Backend**
- [ ] `app/config.py`: add `cors_origins` (default `http://localhost:5173,http://127.0.0.1:5173`)
- [ ] `app/main.py`: add `CORSMiddleware` for those origins (methods/headers `*`, no credentials —
      we use a bearer header, not cookies)
- [ ] `.env.example` + ARCHITECTURE §9: document `CORS_ORIGINS`

**Frontend — API boundary (the real rewrite)**
- [ ] `frontend/.env.example`: `VITE_API_BASE_URL=http://localhost:8000`
- [ ] `lib/api.ts`: rewrite to `fetch` the real API with a shared `request()` helper that attaches
      `Authorization: Bearer <token>` (read from the auth store) and, on 401, clears auth. Maps the
      API's snake_case JSON → the existing camelCase frontend types so components/types don't change:
  - [ ] `login` → POST /api/auth/login (returns the JWT)
  - [ ] `getCurrentUser` (new) → GET /api/auth/me
  - [ ] `getCases` / `getCase` → GET /api/cases[/{id}]; `createCase` → POST /api/cases
  - [ ] `createSession` → POST /api/sessions; `getScorecard` → GET /api/sessions/{id}/scorecard
  - [ ] `getLiveKitToken` → GET /api/livekit/token
  - [ ] `getSessionScript` → **stays mocked** (scripted transcript; no agents yet)

**Frontend — auth**
- [ ] `store/auth.ts`: `login()` calls `api.login` (store JWT) then `api.getCurrentUser` (store user);
      rollback + throw on failure
- [ ] `components/ProtectedRoute.tsx`: validate the session against real GET /api/auth/me
      (TanStack Query, `enabled: !!token`) — redirect to /login on no-token or 401, brief "checking"
      state while it resolves

**Frontend — session start plumbing (SparringRoom)**
- [ ] `pages/SparringRoom.tsx`: on load, GET /api/livekit/token for the session (real call, shows a
      "voice room ready" indicator), then run the existing scripted playback unchanged. POST
      /api/sessions already fires from Dashboard's "Start sparring" (real) — see decision below.

**Frontend — scorecard gap (DECISION — flagging, not guessing)**
- [ ] Chosen: **frontend fallback message**. Since no agent generates scorecards yet, the session
      stays `in_progress` and GET scorecard returns 409 (or 404). `Scorecard.tsx` will detect that and
      render an honest "not available yet — the AI Judge that writes this isn't wired up until the
      agents pipeline lands" panel instead of an error. Rationale: don't write fake assessment data
      into the DB. (Alternative was a backend placeholder scorecard — confirm below.)

**Tests**
- [ ] Update the 3 Vitest tests (Login, CaseUpload, Scorecard) to spy on the `api` functions instead
      of relying on mock data; add a Scorecard "fallback when unavailable" test

**Docs (self-updating)**
- [ ] ARCHITECTURE §4/§9: note the frontend now calls the real API, `VITE_API_BASE_URL`, and
      `CORS_ORIGINS`; note the scorecard-gap handling

**Verify**
- [ ] Bring up backend (compose + alembic + uvicorn) and frontend (`npm run dev`), walk the full
      real flow in the browser; confirm real rows via curl/DB

**Decisions (resolved):** (1) scorecard gap = **frontend fallback** message; (2) POST /api/sessions
fires from **Dashboard's "Start sparring"** button (route-consistent), SparringRoom then GETs the
LiveKit token.

**Result:** Frontend now talks to the real backend. `lib/api.ts` rewritten to `fetch` with a shared
`request()` (bearer from the auth store, 401 → logout) and snake→camel mapping; `getSessionScript`
stays mocked. Auth store logs in via `/api/auth/login` then loads `/api/auth/me`; ProtectedRoute
validates the session against `/api/auth/me`. SparringRoom fetches a real LiveKit token on load
("Voice room ready"). Scorecard shows an honest "Not available yet" fallback on 404/409 (no fake
data). Backend gained CORS for the Vite origin. **type-check clean, 5 Vitest tests pass, lint clean.**
Verified in-browser end to end (real DB): login → /me → create case (POST 201) → start session
(POST 201) → livekit token (200) → scorecard (409 → fallback); all CORS preflights 200.

**Scorecard gap handling (flagged):** chose the **frontend fallback**, not a backend placeholder —
the backend stays truthful (no fabricated scores in the DB); the session legitimately has no
scorecard until the Judge agent exists.

---

### Memory & verification: docs + two no-key modules — status: done

**Goal:** Document the memory/verification design in ARCHITECTURE, then implement + test only the
two pieces that need no API keys (SessionState, citation heuristic). Leave the LLM consistency
check as a stub.

**Docs**
- [ ] ARCHITECTURE: new "## 6.5 Memory & verification" section (placed after §6, no renumbering) —
      structured in-memory SessionState (case facts, established facts, objections ledger); a
      verification pass before TTS checking (a) consistency vs SessionState and (b) fabricated
      legal citations; verification model co-located on the same GPU as the reasoning model once
      self-hosted (Fireworks = a second call until then). Include a small mermaid flow
      (SessionState → Reasoning → Verification → fail:regenerate / pass:TTS) and note what's
      implemented now vs stubbed.

**Implement — `agents/session_state.py`** (pure Python, no keys)
- [ ] `Objection` dataclass (grounds, raised_by, ruling: pending|sustained|overruled) + `SessionState`
      dataclass (case_facts, established_facts ledger, objections ledger) with update methods:
      `add_established_fact`, `record_objection`, `rule_on_objection` (validates ruling; rejects
      re-ruling a resolved one), `pending_objections` / `sustained_objections`, and a compact
      `snapshot()` for use as verifier/prompt context

**Implement — `agents/verification.py`** (regex heuristic, no keys)
- [ ] `find_suspicious_citations(text) -> list[CitationFinding]` + `has_suspicious_citation(text)`:
      regex-detect "volume reporter page (year)" case citations, flag (i) unrecognized reporter
      abbreviations (not in a known allowlist) and (ii) implausible years (future / pre-1789)
- [ ] `check_consistency(reply, state)` — LLM-based consistency check left as a
      `# TODO: implement once Fireworks/AMD keys are available` stub (raises NotImplementedError)

**Tests (pytest)**
- [ ] `agents/tests/test_session_state.py` — sample turns: empty init, add facts (dedupe), record +
      rule objections, invalid/duplicate ruling raises, pending/sustained filters, snapshot content
- [ ] `agents/tests/test_verification.py` — sample sentences: clean citations (Brown v. Board /
      F.3d) not flagged, fabricated-looking (bogus reporter, future year) flagged, plain sentence
      not flagged; consistency stub raises NotImplementedError
- [ ] `agents/conftest.py` (empty — puts `agents/` on sys.path) + `agents/requirements.txt`
      (pytest, ruff) for local runs

**Decision (resolved):** added a minimal agents CI test job (installs `agents/requirements.txt`,
runs `ruff check` + `pytest`) covering only the no-key modules; the LLM-pipeline files stay
skeletons and aren't imported by the tests.

**Result:** Done. ARCHITECTURE gained "## 6.5 Memory & verification" (SessionState memory,
pre-TTS verification pass, GPU co-location, mermaid flow, implemented-vs-stubbed note).
`agents/session_state.py` implements `SessionState` + `Objection` with validated update methods
(add/dedupe facts, record objection, rule with re-ruling/unknown-ruling guards, pending/sustained
filters, `snapshot()`). `agents/verification.py` implements `find_suspicious_citations` /
`has_suspicious_citation` (regex flags unrecognized reporters + implausible years) and leaves
`check_consistency` as a `# TODO … Fireworks/AMD keys` stub (raises NotImplementedError). Tests:
`agents/tests/` — 19 passing (SessionState sample turns; clean vs fabricated citation sentences;
stub contract). Added `agents/pyproject.toml` (ruff + pytest `pythonpath`) and
`agents/requirements.txt`. **ruff clean, 19 pytest pass.** CI now has an agents job.

---

### Wire up Fireworks: llm_router, consistency check, opposing counsel + judge — status: done

**Goal:** Make the agents actually generate + verify responses via Fireworks (OpenAI-compatible),
with a text-only harness so it's testable without any voice infra. main.py stays a skeleton.
Split every module into offline-testable pure logic (CI) vs live API calls (excluded from CI).

**Config & routing**
- [ ] `agents/config.py` — load repo-root `.env` (python-dotenv), expose per-role provider /
      endpoint / model + `FIREWORKS_API_KEY`. New model env vars (defaults, Fireworks):
      `OPPOSING_COUNSEL_LLM_MODEL`, `JUDGE_LLM_MODEL` (Gemma per §7), `VERIFICATION_LLM_MODEL`
      (small/fast, *not* the reasoning model), plus `VERIFICATION_LLM_PROVIDER/ENDPOINT`
- [ ] `agents/llm_router.py` (per §7) — `LlmConfig` resolver per role (opposing_counsel / judge /
      verification) from env, `build_client()` (OpenAI client → Fireworks now, self-hosted vLLM
      later — same code path), and a `chat()` helper. Offline-testable (no network on construction).

**Verification (finish the stub)**
- [ ] `verification.check_consistency(reply, state)` — call the small verification model with the
      `SessionState.snapshot()` + draft reply; model returns JSON `{consistent, contradictions[]}`.
      Factor pure `_build_consistency_messages` + `_parse_consistency` (offline-tested); the live
      call is behind them. Fail-closed on unparseable verifier output. Citation heuristic unchanged.

**Agents (first working generation logic)**
- [ ] `opposing_counsel.py` — load `prompts/opposing_counsel.md`, pure `build_messages(state, turn)`
      (persona + state snapshot + attorney turn), live `generate_reply(state, turn)` via Fireworks
- [ ] `judge.py` — load `prompts/judge.md`, pure `build_messages(...)`, live `generate_ruling(...)`

**Text-only harness (no voice)**
- [ ] `agents/harness.py` — feed fake case facts + a fake attorney transcript turn; generate the
      opposing-counsel reply; run verification (citation heuristic + live consistency check); print
      the reply and verification result. Runnable as `python harness.py` (needs the key). main.py
      stays a skeleton.

**Tests — offline (CI) vs live (excluded, not skipped)**
- [ ] Offline (run in CI): llm_router config resolution + client base_url/model; prompt loading;
      `build_messages` for both agents; verification `_build_consistency_messages` /
      `_parse_consistency`; plus existing session_state + citation tests
- [ ] Live (excluded from CI): `@pytest.mark.live` on real Fireworks calls (check_consistency finds
      a planted contradiction; generate_reply/ruling return non-empty). Register the `live` marker;
      `addopts = -m "not live"` so the default run + CI **deselect** them (reported as deselected,
      not silently skipped); run them with `pytest -m live`. CI step becomes `pytest -m "not live"`.

**Deps / docs**
- [ ] `agents/requirements.txt`: add `openai`, `python-dotenv`
- [ ] `.env.example` + ARCHITECTURE §9: document the new model env vars; note §6.5/§7 are now
      partially live (Fireworks), STT/TTS still pending Deepgram/ElevenLabs

**Verify**
- [ ] `ruff` + `pytest -m "not live"` green; optionally run the harness + live tests (fake data)

**Decisions (resolved):** confirmed to build + run live verification. **Model reality (flagged):**
the confirmed llama/gemma defaults are NOT deployed on this Fireworks account (404). Available chat
models: deepseek-v4-pro, glm-5p1/5p2, gpt-oss-120b, kimi-k2p5/6 (GLM/Kimi emit chain-of-thought,
unusable). Final assignment: opposing counsel = `deepseek-v4-pro`; verification = `gpt-oss-120b`
(clean JSON); judge = `gpt-oss-120b` via structured JSON. **Judge/Gemma follow-up:** confirmed with
the user there is no serverless Gemma on this account (verified `/v1/models` + direct probes of
Gemma 2/3/4 IDs incl. the changelog's Gemma 3 12B/4B — all 404). Per the user, using the best
*working* model as interim: `deepseek-v4-pro` was rejected for the Judge (reasoning model: 30–60s
and intermittently empty content); `gpt-oss-120b` (JSON) is fast (~2–3s) + reliable. Recorded in
ARCHITECTURE §7/§11; move to Gemma once deployed.

**Result:** Done and live-verified. `agents/config.py` (dotenv + per-role provider/endpoint/model)
and `agents/llm_router.py` (§7: OpenAI-compatible client per role + `chat()` helper) implemented.
`verification.check_consistency` now calls the small verifier model, returns JSON contradictions,
fails closed on unparseable output (pure `_build_consistency_messages`/`_parse_consistency` for
offline tests). `opposing_counsel.py` + `judge.py` generate replies/rulings from the persona
prompts (judge uses structured JSON output for clean, non-empty rulings). `agents/harness.py` runs
the full draft→verify path text-only (no voice); confirmed clean end to end: sharp OC rebuttal,
verification PASS→TTS, crisp judge ruling. main.py stays a skeleton. Tests: **32 offline pass (CI),
4 live pass** (`pytest -m live`); live tests marked `@pytest.mark.live` and **deselected** in CI via
`addopts = -m "not live"` (CI runs `pytest -m "not live"`) — deselected, not skipped. ruff clean.
Docs: ARCHITECTURE §6.5 (now live) + §7 (actual model IDs, Gemma-blocked note) + §9 model env vars;
`.env.example` updated. Deepgram/ElevenLabs voice pipeline still pending.
