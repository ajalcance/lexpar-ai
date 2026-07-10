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

---

### Objection classifier (the bespoke real-time interrupt logic) — status: done

**Goal:** Implement `agents/objection_classifier.py` — given a partial fragment of the attorney's
ongoing speech + the current SessionState, decide whether Opposing Counsel should interrupt *now*
and with what objection type (leading, hearsay, speculation, …), honoring opposing_counsel.md's
"only when phrasing genuinely invites one — not every turn" rule. Fully testable without Deepgram/
LiveKit.

**Design — two-stage, so it can run continuously as speech streams (§6):**
- **Stage 1 (offline, runs on every fragment, ~free): `candidate_grounds(fragment) -> list[str]`** —
  regex/keyword heuristic for objection-inviting phrasing (leading tag-questions "isn't it true…",
  "…didn't you?"; hearsay "he told me", "she said that"; speculation "I think / probably / might
  have"). Empty → immediate **no-fire, no LLM call**. This is what makes "runs continuously" feasible.
- **Stage 2 (live, only on candidates): `classify_fragment(fragment, state) -> Decision`** — a fast
  model (gpt-oss-120b, JSON) makes the final fire/no-fire + type decision, applying the "not every
  turn" discipline and SessionState (e.g., don't re-fire grounds just overruled).
- `Decision` dataclass (`fire: bool`, `objection_type: str | None`, `reason: str`); pure
  `_build_messages` + `_parse_decision` for offline tests.

**Model:** reuse `gpt-oss-120b` (fast JSON) — quick live latency check to confirm; add
`OBJECTION_LLM_*` env (config + llm_router `objection_config()`), overridable, default gpt-oss.

**Harness:** `agents/objection_harness.py` — feeds a scripted sequence of sample fragments (leading
Qs, hearsay, speculation, clean statements) and prints each fragment's fire/no-fire + type + reason.
Live (needs key); clean fragments short-circuit (no LLM call).

**Tests:**
- Offline (CI): `tests/test_objection_classifier.py` — labeled sample set on `candidate_grounds`
  (leading/hearsay/speculation flagged; clean not) + `_parse_decision` JSON parsing.
- Live (`@pytest.mark.live`, deselected in CI): append to `tests/test_live_fireworks.py` —
  `classify_fragment` fires on a leading question and on hearsay, and does not fire on a clean
  statement.

**Docs:** ARCHITECTURE §6 (objection_classifier now implemented, two-stage) + §6.5 implemented-list
+ §7 (classifier model row) + §9 (`OBJECTION_LLM_*`); `.env.example`; PLAN updated.

**Refinements (confirmed with user):**
- **Recall-biased gate:** the regex gate errs toward passing candidates through — a too-strict gate
  silently drops real objections before the LLM sees them (invisible failure). False positives just
  cost the LLM a little latency; false negatives are silent misses of the core feature.
- **Debounce per utterance:** a stateful `ObjectionClassifier` tracks the growing utterance and does
  not re-fire once it has objected on it, until a new utterance starts (continuation detected via
  prefix). Injectable decider so the debounce is deterministically unit-tested.
- **Fail closed:** if the stage-2 LLM call errors/times out or returns unparseable output,
  `classify_fragment` returns **no interruption** (never crash/block) — mirrors verification.py.
- **Minimal LLM output:** JSON `{fire, objection_type, reason}` only, small max_tokens, temp 0 —
  this is the most latency-sensitive call in the system.

**Decisions (resolved):** proceed; two-stage heuristic-gate + fast-LLM.

**Result:** Done and live-verified. `objection_classifier.py`: `candidate_grounds` (recall-biased
regex gate over leading/hearsay/speculation/argumentative), `classify_fragment` (gate → gpt-oss-120b
JSON `{fire, objection_type, reason}`, fails closed on error/empty/unparseable), and
`ObjectionClassifier` (per-utterance debounce via prefix continuation, injectable decider). Added an
`objection` role to config/llm_router (`OBJECTION_LLM_*`, default gpt-oss). `objection_harness.py`
streams sample fragments and prints decisions. **Latency-fix flagged:** at max_tokens=120 gpt-oss
returned empty content (hidden reasoning ate the budget) → raised to 512; candidates now decide in
~2–2.5s and clean fragments short-circuit at 0.0s (no LLM). Tests: **42 offline pass (CI)** (labeled
gate set; monkeypatched short-circuit/parse/fail-closed; deterministic debounce) + **7 live pass**
(fires on leading/hearsay, holds on clean; `@pytest.mark.live`, deselected in CI). ruff clean. Docs:
ARCHITECTURE §6 (implemented, two-stage) + §6.5 + §7 (classifier row) + §9 (`OBJECTION_LLM_*`);
`.env.example` updated.

**Post-build addition (user request):** each `Decision` now carries an audit `outcome`
(`gate_rejected` / `llm_no_fire` / `fire` / `fail_closed` / `debounced`), and `ObjectionClassifier`
has an opt-in review log (`record=True`, off by default — retains work product) exposing
`gate_rejected()` vs `llm_no_fire()` so what the recall-biased gate filtered can be reviewed
separately from what the LLM judged. Harness prints the two lists. +3 offline tests → **45 offline,
7 live**, ruff clean.

---

### Real LiveKit Agents voice worker (agents/main.py) — status: done (needs a live room to verify)

**Goal:** Implement `agents/main.py` as a real LiveKit Agents worker — Deepgram streaming STT +
ElevenLabs Flash TTS (§6) — with the objection classifier wired so a `fire` decision actually
barges in: cancels the in-progress attorney turn and has Opposing Counsel object immediately, via
LiveKit's built-in interruption. **Do not modify** opposing_counsel.py / judge.py / verification.py —
only connect the audio layer around them. Frontend untouched.

**Design**
- `main.py` — worker entrypoint (`livekit-agents` 1.x): connect to the room, `AgentSession` with
  Silero VAD, Deepgram STT (interim results on), ElevenLabs Flash TTS. The attorney participant
  speaks → STT.
  - **Interim transcripts →** `ObjectionClassifier.consider(fragment)`; on `fire` → **barge-in**:
    interrupt current handling and Opposing Counsel speaks the objection immediately.
  - **End of turn (no objection) →** `opposing_counsel.generate_reply` → verification pass
    (`find_suspicious_citations` + `check_consistency`, unchanged) → speak via TTS; `judge` rules
    where appropriate. Uses the existing functions verbatim.
- **Testable, livekit-free glue** in `agents/voice_interrupt.py` (no livekit import; operates on a
  duck-typed session): `objection_utterance(decision)` (pure) + `async handle_interim(session,
  classifier, fragment)` — so the "fire → interrupt + speak" wiring is unit-tested with a fake
  session. `main.py` imports and wires this into the real session.
- Config: `DEEPGRAM_MODEL`, `ELEVENLABS_MODEL` (default `eleven_flash_v2_5`), `ELEVENLABS_VOICE_ID`
  in config.py + .env.example + §9. Plugins read DEEPGRAM/ELEVENLABS keys from env; the worker reads
  LIVEKIT_URL/API_KEY/API_SECRET from env (already present).

**Dependencies — kept OUT of CI (heavy media libs CI can't exercise):**
- `agents/requirements-voice.txt` — `livekit-agents`, `livekit-plugins-{deepgram,elevenlabs,silero,
  openai,turn-detector}`. NOT added to `requirements.txt`, so the agents CI job (ruff + offline
  pytest) stays lean and green. `main.py` imports livekit only when run; ruff lints it statically;
  no test imports it.

**Tests (offline / CI only):** `tests/test_voice_interrupt.py` — `objection_utterance` text;
`handle_interim` calls interrupt+say on `fire` and does nothing otherwise (fake async session);
config defaults. No live test (needs a real room + mic).

**⚠️ Cannot verify here — needs a live LiveKit room + a real microphone (flagged):**
- The entire real audio path: room join, mic → Deepgram STT, ElevenLabs TTS playback, VAD/turn
  detection, and the **actual barge-in timing/behavior**.
- The exact `AgentSession` API wiring (interim-transcript event hookup, the interrupt/say method
  names, and integrating our custom blocking `generate_reply` as the LLM step) is written to the
  documented `livekit-agents` 1.x API but can only be validated/tuned against the installed SDK in a
  running room. I'll implement to the current docs and mark residual uncertainty inline.
- Because of this, per your instruction the frontend stays on scripted mock data until we confirm
  this works end to end in a real room.

**Docs:** ARCHITECTURE §6 (main.py implemented; live-vs-needs-room note) + §6.5 + §9 + §10 (how to
run the worker); `.env.example`; PLAN.

**Decisions (resolved):** proceed; voice deps in a separate `requirements-voice.txt`; on `fire`, a
short canned "Objection — <type>." for low-latency barge-in.

**Result:** Implemented. `main.py` — LiveKit Agents worker (verified API via LiveKit docs):
`AgentSession` with Silero VAD, Deepgram STT (interim on), ElevenLabs Flash TTS; Opposing Counsel
routed through `OpposingCounselAgent.llm_node` which calls `opposing_counsel.generate_reply` + the
`verification` pass (both unchanged, off-loop via `asyncio.to_thread`); `user_input_transcribed`
events feed the classifier and a `fire` barges in (`session.interrupt()` + say) via the tested
`voice_interrupt.py`; Judge closing ruling on shutdown (generation wired, delivery flagged). Kept
opposing_counsel/judge/verification verbatim. `requirements-voice.txt` holds the heavy deps (out of
CI); config + `.env.example` + §9 got `DEEPGRAM_MODEL`/`ELEVENLABS_MODEL`/`ELEVENLABS_VOICE_ID`.
**Tests: 48 offline pass** (+3 for the interrupt glue), 7 live deselected, ruff clean, main.py
compiles. **Frontend untouched** (stays on scripted mock per instruction).

**⚠️ Not verified here (needs a live LiveKit room + microphone):** the whole audio path — room join,
mic→Deepgram STT, ElevenLabs playback, VAD/turn detection, and real barge-in timing. The exact
`AgentSession` wiring (`llm_node` signature, event fields, interrupt/say) is written to the
livekit-agents 1.x docs but may need tuning against the installed SDK in a running room. Only the
livekit-free glue (`voice_interrupt.py`), config, and lint are validated. Frontend remains on mock
until this is confirmed end to end.

---

### Frontend ↔ backend/agents gap analysis (read-only — no code changed)

Snapshot of what the frontend does today vs. what backend/ and agents/ can now do. `S` = small
(config/wiring), `L` = substantial (new UI + logic). Libs `@livekit/components-react` +
`livekit-client` are already installed, which lowers the room-join lift.

**Gap 1 — SparringRoom never joins the room or publishes a mic `[L]`.**
- Finding: `SparringRoom.tsx` only calls `api.getLiveKitToken(sessionId)` in a `useQuery` to show a
  "Voice room ready" badge (token fetch success), then plays the **scripted mock** transcript via
  `useSparringSession` → `api.getSessionScript` → `mockTranscript`. `lib/livekit.ts`
  (`connectToRoom`/`disconnectFromRoom`) exists but is **unused**; no `room.connect`, no mic publish,
  no audio subscribe. It behaves exactly as it did before `agents/main.py` existed — token only.
- Replaces: `useSparringSession.ts` + `api.getSessionScript` + `mockTranscript`; the token-only
  `roomReady` `useQuery` in SparringRoom.
- Need: connect with the token (`livekit-client`/`LiveKitRoom`), publish the mic track, subscribe to
  the agent's audio + transcription; drive lifecycle on mount/unmount.

**Gap 2 — No mic-permission request, mute control, or real connection-state UI `[L]`.**
- Finding: because nothing connects, the browser mic-permission prompt never fires. No mute/unmute.
  The `idle/connecting/playing/completed` badge reflects the **scripted timer**, not LiveKit
  `ConnectionState`; "Voice room ready" = token fetch, not a live connection.
- Minimum needed: connecting + publishing mic (triggers the permission prompt); a mute toggle
  (`localParticipant.setMicrophoneEnabled`); a connection indicator from
  `RoomEvent.ConnectionStateChanged` (connecting/connected/reconnecting); a "listening/speaking"
  indicator from active-speaker events (`isSpeaking` / `ActiveSpeakersChanged`).
- Replaces: the mock status badges + "Voice room ready" badge in SparringRoom.

**Gap 3 — A fired objection has no path to the frontend as a structured event `[L]`.**
- Finding: `agents/main.py` on `fire` does `session.interrupt()` + `session.say("Objection — <type>.")`
  — it **speaks** the objection (audible if connected) but publishes **no structured event**. There is
  no LiveKit data-channel message carrying `{objection_type, reason}`, and the frontend subscribes to
  no `DataReceived`/`TranscriptionReceived`. So a real interruption can't render as the visible
  "OBJECTION (leading)" line the mock shows.
- Need (both sides, must be built): agent publishes an objection event (LiveKit data channel via
  `room.localParticipant.publishData`, or transcription metadata) from `main.py`/`voice_interrupt.py`;
  frontend subscribes and renders it. LiveKit Agents can also forward STT/TTS as
  `TranscriptionReceived` — a candidate feed for the live transcript itself.
- Replaces: the `wasInterruption` styling in `mockTranscript`/`TranscriptLine` would be driven by real
  events instead of the scripted flag.

**Gap 4 — Nothing calls `judge.py` to persist a scorecard; `/scorecard` still 409 `[L]`.**
- Finding: `scorecard_service.get_scorecard` requires `status == "completed"` **and** a `Scorecard`
  row. Sessions are created `in_progress`; there is **no API route** to complete one
  (`session_service.transition_status` exists but is unrouted). Nothing writes `Scorecard` rows —
  `judge.generate_ruling` produces text, but `main.py` only **logs** it on shutdown (TODO to persist),
  and there is **no backend write endpoint** for the agent (no POST scorecard/transcript route; agents
  have no service credential — `AUTH_MODE=stub`). So `/api/sessions/{id}/scorecard` returns **409
  regardless** → the frontend "not available yet" fallback always shows.
- Need: (a) complete/end a session (a route the "End session" button calls, or agent-driven on room
  close); (b) an agent persistence path — new backend endpoint(s) to write transcripts + the scorecard,
  plus an agent auth/service credential; (c) then `getScorecard` returns real data.
- Replaces: the 404/409 → "Not available yet" fallback in `Scorecard.tsx` (which would finally render
  a real score).

**Gap 5 — Backend/agents capabilities with no frontend surface at all.**
- **SessionState** (case_facts, established-facts ledger, objections ledger + rulings) `[L]`: agents
  in-memory only — not persisted, no UI. No "what's on the record" / established-facts / objection-
  ledger view.
- **Verification results** (suspicious citations, consistency contradictions) `[L]`: computed in
  agents, discarded, no UI (could surface as a "flagged / regenerated" indicator).
- **Objection type + reason** `[S once Gap 3 exists]`: the real classifier emits `objection_type` +
  `reason`; the mock only shows a generic "Objection" badge via `wasInterruption`. Rendering the real
  type/reason is small **once** the data-event path (Gap 3) exists.
- **Real transcripts** `[L]`: the `transcripts` table + `GET /api/sessions/{id}` (`SessionDetailOut.
  transcripts[]`) exist but are **never written**; the frontend uses `getSessionScript` (mock) instead
  of the real `getSession` transcripts.
- **Judge rulings** (real Fireworks) `[L]`: generated, never persisted or surfaced.

**Two foundations most gaps hinge on:** (A) the frontend actually joining the LiveKit room + mic
(Gaps 1–2), and (B) a persistence + eventing path agents → backend → frontend (Gaps 3–5), which also
needs an **agent auth/service credential** (blocked on replacing `AUTH_MODE=stub`, ARCHITECTURE §11).

---

### Wire SparringRoom to the real LiveKit room + mic (Gaps 1–2) — status: done

**Goal:** SparringRoom actually connects to the LiveKit room (via the existing
`lib/livekit.ts connectToRoom` + the token it already fetches) and publishes the browser mic
(triggering the permission prompt). Add a mute/unmute toggle, a connection-state indicator tied to
LiveKit's real `ConnectionState`, and a listening/speaking indicator from active-speaker events. The
scripted mock transcript becomes a **fallback ONLY** when the connection fails or no agent joins
within a few seconds (Deepgram/ElevenLabs credit pending → the agent won't always be running; keeps
the app demoable). **Objection detection/display is untouched — that's Gap 3.**

**New hook `hooks/useSparringRoom.ts`** (connection lifecycle; logic in a hook per DEV §11):
- fetch token (`api.getLiveKitToken`) → `connectToRoom(access)` → publish mic
  (`localParticipant.setMicrophoneEnabled(true)` — fires the permission prompt) → attach remote agent
  audio tracks so the agent is audible.
- subscribe: `RoomEvent.ConnectionStateChanged` (real state), `ActiveSpeakersChanged`
  (listening/speaking), `ParticipantConnected`/`Disconnected` (agent presence).
- `mode`: `connecting` | `live` | `fallback`. → `fallback` if token/connect fails, or connected but
  **no agent within ~5s**; a later agent join promotes to `live`.
- returns `{ mode, connectionState, isMuted, toggleMute, activeSpeaker, micBlocked }`; mic-denied →
  stay connected, disable mute, flag `micBlocked` (don't fall back — they can still hear the agent).
- cleanup: `disconnectFromRoom` on unmount / End session.

**Modify `hooks/useSparringSession.ts`** — add an `enabled` option so the scripted mock only runs
(and only sets its timers) in fallback mode; no-op when disabled.

**Modify `pages/SparringRoom.tsx`** — use both hooks (`scriptEnabled = mode === 'fallback'`); render
the connection-state indicator, listening/speaking indicator, and mute button; transcript panel shows
the scripted mock in fallback (existing `TranscriptLine`, unchanged) and a "live audio — transcript
view lands with Gap 3" placeholder in live. "End session" disconnects + navigates to the scorecard.
Replaces the old `getLiveKitToken` `useQuery` + "Voice room ready" badge.

**Not touched:** `TranscriptLine`, `mockTranscript`, objection styling (Gap 3); `lib/api.ts`; backend;
agents. `lib/livekit.ts connectToRoom`/`disconnectFromRoom` reused as-is (mic/events/audio handled in
the hook).

**Verification (limits flagged):** I'll bring up the backend + the running LiveKit dev server and
verify in the browser preview that the page connects and — with no agent worker running and no real
mic in the preview browser — **falls back to the scripted mock**, with the connection indicator + mute
control rendering. **Full LIVE (agent audio, active-speaker, real mic input) needs the agent worker +
a real microphone and cannot be verified here** — which is exactly why the fallback exists.

**Decisions (resolved):** proceed; keep the room connected when no agent joins (promote to live if
one joins later).

**Result:** Done and verified (fallback path). New `hooks/useSparringRoom.ts` connects via
`connectToRoom` + the fetched token, publishes the mic (`setMicrophoneEnabled`, prompts permission),
attaches remote audio, and subscribes to `ConnectionStateChanged` / `ActiveSpeakersChanged` /
`ParticipantConnected`; returns `{ mode, connectionState, activeSpeaker, isMuted, micBlocked,
toggleMute }`. `useSparringSession` gained an `enabled` flag so the scripted mock only runs in
fallback. `SparringRoom.tsx` shows the connection-state badge, listening/speaking badge, and mute
toggle, and swaps the transcript panel: mock in fallback (objection styling unchanged — Gap 3),
placeholder in live. Two robustness fixes found during verification: **(a)** defer the connect one
tick so React StrictMode's dev double-mount doesn't fire two same-identity connects; **(b)** an 8s
**connect-timeout** so a *stalled* connection (not just a failed one) falls back. **Verified in the
browser preview** end to end: login → case → session → SparringRoom attempts the real LiveKit
connection, and (no agent + headless browser can't complete WebRTC) **falls back to the scripted mock
with the "Offline (demo)" state + disabled Mute**; objection line styling intact. type-check + lint
clean; existing 5 Vitest tests pass. **Not verifiable here (flagged):** the successful *connected*
path — real mic publish, active-speaker indicator, agent audio, and connected-but-no-agent → the app
needs a real browser (mic + WebRTC) and the agent worker running.

---

### Gap 4 — agent persistence: session-complete + scorecard/transcript write — status: done

**Goal:** Give the agent a scoped, least-privilege service credential + internal routes to end a
session, persist the full transcript (batch, at session end — no per-turn round-trips in the voice
loop), and write a real scorecard derived from the Judge's ruling + SessionState, so
`/api/sessions/{id}/scorecard` finally returns real data. opposing_counsel/judge/verification stay
unchanged.

**Backend — service auth (separate mechanism from user JWT, DEV §7):**
- `config.agent_service_token` (env `AGENT_SERVICE_TOKEN`).
- `app/security_agent.py`: `require_agent_service` dependency — validates an `X-Agent-Token` header
  against the configured token (constant-time compare); missing/empty/mismatch → 401. Loads NO
  user; applied ONLY to the internal routes below. The user JWT does not grant these routes, and this
  token does not grant user routes.

**Backend — internal routes** (`app/api/internal.py`, `dependencies=[Depends(require_agent_service)]`):
- `POST /api/sessions/{id}/complete` → in_progress→completed (reuse `transition_status`), set
  `ended_at`. 404 unknown, 409 if not in_progress.
- `POST /api/sessions/{id}/scorecard` → body `{overall_score, strengths, weaknesses, judge_ruling,
  transcript:[{speaker, content, was_interruption, spoken_at?}]}`; requires completed; creates the
  Scorecard row **and batch-inserts the whole transcript in the same call**; 409 on duplicate. Returns
  ScorecardOut.
- New `schemas/agent.py`, `services/agent_write_service.py`, and
  `session_service.get_session_by_id` (no user scope — internal only).

**Agents — accumulate + persist:**
- `session_state.py`: add `TranscriptTurn` + a `transcript` list + `add_turn(speaker, content,
  was_interruption=False, spoken_at?)` (facts/objections unchanged; snapshot untouched so existing
  tests hold).
- `scorecard_builder.py` (pure): `build_session_end_payload(state, judge_ruling)` → the complete +
  scorecard payloads. Heuristic `overall_score` (penalize per sustained objection), `strengths` (from
  established facts), `weaknesses` (from sustained-objection grounds), `judge_ruling` = the ruling
  text; transcript from `state.transcript`.
- `backend_client.py`: `complete_session(id)` + `write_scorecard(id, payload)` via httpx with the
  `X-Agent-Token` header (config `AGENT_SERVICE_TOKEN`, `AGENT_BACKEND_URL`); tolerate 409 (idempotent
  retry).
- `main.py`: `state.add_turn(...)` as turns happen in the live session, and in the shutdown
  `_closing_ruling` call complete + write_scorecard once with the built payload.
- `config.py`: `AGENT_SERVICE_TOKEN`, `AGENT_BACKEND_URL`; add `httpx` to `requirements.txt`.

**Tests (offline / CI):**
- Backend `tests/test_agent_routes.py` — **the end-to-end persistence via a test backend instance
  (TestClient)**: service-auth accepts the token / rejects missing/wrong/user-JWT; user JWT can't hit
  internal routes and the service token can't hit user routes (least-privilege); /complete
  transitions + 404/409; /scorecard persists scorecard + batch transcript, 409 on dup; then the
  **user** GET /scorecard returns the real scorecard and GET session returns the ordered transcript.
- Agents `tests/test_session_end.py` — `add_turn` accumulates; `build_session_end_payload`
  shape/derivation (pure, offline).
- `agents/session_end_harness.py` — fake SessionState + turns → build payload → print (offline);
  posts to a live backend if configured. Not CI.

**Docs:** ARCHITECTURE §5 (two internal routes + agent-service auth), §8 (agent batch-writes
transcript + scorecard at session end), §9 (`AGENT_SERVICE_TOKEN` / `AGENT_BACKEND_URL`), §11 (scoped
credential ≠ user auth); `.env.example`.

**Cannot verify here (flagged):** the live agent→backend call from inside the running worker (needs a
live room + worker). The persistence path itself is fully verified offline via the backend TestClient
test + agent unit tests + the harness.

**Decisions (resolved):** heuristic scorecard (start 100, −8 per sustained, clamp ≥0; strengths =
established facts, dedup, 5 most recent; weaknesses = unique sustained grounds; edge-case messages;
verbatim ruling); split tests + backend TestClient + printable harness.

**Result:** Done and verified end to end. Backend: `AGENT_SERVICE_TOKEN` config + `security_agent.py`
(`X-Agent-Token`, constant-time, fail-closed, separate from user JWT) + internal router
(`app/api/internal.py`, `dependencies=[require_agent_service]`) with `POST /complete` and
`POST /scorecard` (batch transcript + scorecard) + `agent_write_service.py` +
`session_service.get_session_by_id`. Agents: `SessionState.add_turn`/`transcript`,
`scorecard_builder.build_session_end_payload` (precise heuristic), `backend_client.py` (httpx +
X-Agent-Token, tolerates 409), and `main.py` wiring (accumulate turns; batch write on shutdown).
Tests: backend **19 pass** (incl. 6 new: service-auth + least-privilege both ways, /complete
404/409, /scorecard gating + dup, and the full user-reads-real-scorecard+transcript flow via
TestClient); agents **56 offline pass** (+8: add_turn, score/clamp, strengths cap, unique
weaknesses, edge cases, payload shape). **Live end-to-end verified** against a real uvicorn backend:
user session → GET scorecard 409 → harness writes with the agent token → GET scorecard 200 (score
92, real weaknesses/ruling) + session transcript `[attorney, opposing_counsel, judge]` in order.
ruff clean. Docs: ARCHITECTURE §5 (routes + agent-vs-user auth), §8 (who writes what), §9
(`AGENT_SERVICE_TOKEN`/`AGENT_BACKEND_URL`), §11; `.env.example`. **Not verifiable here:** the write
firing from inside the live LiveKit worker (needs a room + worker) — but the persistence path itself
is proven via the backend test + live harness run.

---

### Gap 3 — objection events over the LiveKit data channel — status: done

**Goal:** When `objection_classifier` fires in the live path, publish a structured event over
LiveKit's data channel — `{type: "objection", objection_type, reason, timestamp}` — at the barge-in
moment (alongside `interrupt()` + `say()`). The frontend subscribes and renders each event with the
**same** `wasInterruption` treatment the mock already uses, by **reusing `TranscriptLine`** (no new
component). Live path only; the scripted fallback is untouched.

**Agents:**
- `voice_interrupt.py` (stays livekit-free/testable): add pure `build_objection_event(decision)` →
  `{type:"objection", objection_type, reason, timestamp}`; extend `handle_interim(..., publish=None)`
  so on a fire, after `interrupt()` + `say()`, it calls the injected `await publish(decision)`.
- `main.py`: a `publish_objection(decision)` closure that JSON-encodes `build_objection_event` and
  calls `ctx.room.local_participant.publish_data(..., reliable=True, topic="objection")`, passed into
  `handle_interim`. (livekit call lives only here.)

**Frontend:**
- `lib/objectionEvent.ts` (pure): `parseObjectionData(text) → ObjectionEvent | null` +
  `objectionEventToLine(event, sessionId) → Transcript` (speaker `opposing_counsel`,
  `wasInterruption: true`, content mirrors the spoken barge-in so `TranscriptLine` renders the red
  "Objection" treatment; objection_type conveyed in the content since `Transcript` has no type field).
- `hooks/useSparringRoom.ts`: subscribe to `RoomEvent.DataReceived`; parse objection events; append
  mapped `Transcript`s to an `objections` list (reset per session); expose it.
- `pages/SparringRoom.tsx`: in **live** mode, render `objections` via the existing `TranscriptLine`.
  Fallback path unchanged.

**Tests (offline / CI):**
- Agents (extend `test_voice_interrupt.py`): `build_objection_event` shape; `handle_interim` calls
  `publish` on fire and not on no-fire (fake session + fake publish).
- Frontend (Vitest): `parseObjectionData` + `objectionEventToLine` — valid event → a `Transcript`
  with `wasInterruption: true`; non-objection / malformed data → null/ignored.

**⚠️ Can't verify without a real room + live agent (flagged):**
- The whole live data path — that `publish_data` actually reaches the browser's `DataReceived`,
  delivery latency/ordering (reliable channel), and whether the objection visual lands **in sync**
  with the audio barge-in. I publish adjacent to `interrupt()`/`say()`, but the true simultaneity
  and end-to-end timing can only be judged in a live room.
- The exact `publish_data` / `DataReceived` signatures (topic, reliable flag) — written to the
  documented livekit API; may need tuning against the installed SDK in a running room.
- This rides on the Gap 1/2 live connection, itself only verifiable with a real browser + mic + agent.

**Decisions (resolved):** proceed; objection line text = `"Objection — <type>: <reason>"` (reason
included), composed on the frontend from the structured event.

**Result:** Done. Agents: `voice_interrupt.build_objection_event(decision)` (pure) +
`handle_interim(..., publish=None)` — on fire, after interrupt()+say(), it awaits the injected
`publish`; `main.py` adds a `publish_objection` closure that JSON-encodes the event and calls
`ctx.room.local_participant.publish_data(reliable=True, topic="objection")`. Frontend:
`lib/objectionEvent.ts` (pure `parseObjectionData` + `objectionEventToLine` → a `wasInterruption`
Transcript); `useSparringRoom` subscribes to `RoomEvent.DataReceived`, parses, appends to an
`objections` list (reset per session); `SparringRoom` renders them in **live** mode via the
**reused `TranscriptLine`** (no new component). Scripted fallback untouched. Tests: agents **57
offline** (event shape + publish-on-fire/no-publish-on-no-fire); frontend **10** (5 new: parse valid
/ non-objection / malformed → null, map to wasInterruption line with type+reason, reason-omitted).
type-check + ruff + lint clean. **Verified in preview:** fallback path unchanged — mock plays, the
Objection styling still renders, no new console errors from the data subscription.

**⚠️ Not verifiable here (flagged):** the live data path — that `publish_data` reaches the browser's
`DataReceived`, delivery latency/ordering, and whether the objection visual lands **in sync** with
the audio barge-in — needs a real room + live agent + a real browser (the headless preview can't
complete WebRTC). The `publish_data`/`DataReceived` signatures are written to the documented API and
may need tuning against the installed SDK in a live room.

---

### Gap 5 — render real scorecard + transcript for completed sessions — status: done

**Goal:** Seed a completed session (scorecard + transcript) via the existing Gap-4 harness/agent
routes (no live voice), verify the frontend renders the REAL data end to end, and fix any rendering
mismatch. Decide on ledger/verification UI (default: none).

**Part 1 — Scorecard renders real data (mismatch already found):**
- `scorecard_builder` produces `strengths`/`weaknesses` as `\n`-joined bullet lists, but
  `Scorecard.tsx` renders `{scorecard.strengths}` in a `<CardContent>` — HTML **collapses the
  newlines** into one run-on line. **Fix:** `whitespace-pre-line` on the strengths / weaknesses
  (and ruling) so the lines render as written.
- Verify: seed → load `/session/:id/scorecard` → real score + multi-line strengths/weaknesses +
  ruling render (not the 409 "not available yet" fallback).

**Part 2 — real persisted transcript renders (instead of the scripted mock):**
- Add `api.getSessionTranscript(sessionId)` → GET `/api/sessions/{id}`, map `transcripts[]` (which
  the backend already returns via `SessionDetailOut`) → `Transcript[]`.
- Render it via the **reused `TranscriptLine`** on the **Scorecard page** (post-session review) —
  see decision below. For a completed session this shows the real attorney / opposing-counsel /
  judge lines (objection styling intact); the scripted mock only ever appears for an *in-progress*
  session with no agent (SparringRoom fallback, unchanged).

**Part 3 — ledger / verification UI decision:** **Agree with the default — no dedicated UI.** The
scorecard's strengths already ARE the established-facts ledger and its weaknesses ARE the sustained
objections; the verification results are generation-time internals (they gate the regenerate loop),
not user-facing artifacts. A separate raw view would duplicate what the scorecard already summarizes.
Not building it — no reason found to disagree.

**Tests (offline / CI):** extend `Scorecard.test.tsx` — multi-line strengths render as separate
lines; add a transcript-section test (mock `getSessionTranscript`). No agent / LiveKit needed.

**Docs:** ARCHITECTURE §4 "Wiring status" (scorecard + transcript now render real for completed
sessions) + a §5 note; PLAN.

**Verify (fully offline — no live voice/LiveKit):** seed a completed session with the existing
`session_end_harness.py` against a real backend, then confirm in the browser preview that the
Scorecard page shows the real score + multi-line strengths/weaknesses + ruling + the real transcript.

**Decisions to confirm:** (1) proceed; (2) where the real transcript renders — a section on the
**Scorecard page** (post-session review) [recommended] vs a **SparringRoom review-mode** for
completed sessions.

**Result:** Done and verified end to end (fully offline — no live voice/LiveKit). **Part 1:** fixed
the newline-collapse mismatch — `Scorecard.tsx` strengths/weaknesses/ruling now use
`whitespace-pre-line` so the `\n`-joined bullet lists render as separate lines. **Part 2:** added
`api.getSessionTranscript(sessionId)` (GET `/api/sessions/{id}` → maps `transcripts[]` →
`Transcript[]`) and a **Transcript** section on the Scorecard page that reuses `TranscriptLine`
(objection styling intact). Query has no `enabled` guard (matches the scorecard query; `sessionId`
always comes from the route). **Part 3:** no dedicated ledger/verification UI (agreed with default).
**Tests:** `Scorecard.test.tsx` rewritten — 4 tests (score/sections/ruling, multi-line strengths
assert `whitespace-pre-line` + both lines, real transcript section, 409 fallback); all mock both
`getScorecard` + `getSessionTranscript`. 12/12 frontend tests pass, type-check + lint clean.
**End-to-end verify:** ran `session_end_harness.py <session_id>` against a scratch backend
(AGENT_SERVICE_TOKEN, scratch SQLite) to seed complete + scorecard + transcript, then loaded
`/session/:id/scorecard` in the browser preview — confirmed **Overall score 92** (100 − 8×1
sustained), two established facts as separate strength lines, `- Sustained objection: hearsay`
weakness, verbatim ruling, and the real persisted Transcript (You (Attorney) / Opposing Counsel with
the red "Objection" badge / Judge) — not the scripted mock. **Docs:** ARCHITECTURE §4 "Wiring status"
updated (completed sessions render real scorecard + transcript; no dedicated ledger/verification UI).

---

### Streaming reply with sentence-level verification — status: done

**Goal (latency audit rec #2):** cut Opposing Counsel's time-to-first-audio from ~7–11 s to
~2.5–4.5 s by streaming the LLM reply, segmenting it into sentences as tokens arrive, verifying
**each sentence** (citation heuristic + consistency vs SessionState) before it is spoken, and
handing verified sentences to TTS one at a time — so **nothing unverified is ever spoken**, but
sentence 2 verifies while sentence 1 is already playing.

**Design — new module `agents/streaming_verify.py` (livekit-free, injectable, testable):**
- **Streaming generation (reuse, not rewrite):** `llm_router.chat_stream` (OpenAI `stream=True`,
  yields deltas) alongside `chat`; `opposing_counsel.stream_reply` reuses `build_messages` verbatim.
  `generate_reply`, `check_consistency`, the citation heuristic, and judge.py are unchanged.
- **Incremental `SentenceSegmenter`:** `feed(delta)`/`flush()`, splitting on `.?!` + next-token
  rules, with a legal-abbreviation guard so "Brown v. Board", "347 U.S. 483", "No. 5", "Mr. Rivera"
  never split mid-citation. Wrong splits are latency noise, not correctness bugs (every piece is
  verified either way).
- **Per-sentence verification with accumulated context:** citation heuristic on the sentence,
  consistency on `verified_prefix + candidate` (pronouns/ellipsis keep context; the prefix already
  passed, so a new contradiction is the candidate's). `check_consistency` reused unchanged.
- **`main.py` wiring:** `llm_node` yields verified sentences from the async bridge
  (`astream_verified_reply`, thread→queue) instead of one blob; `add_turn` records exactly what was
  spoken. Old `_verified_reply`/`MAX_VERIFICATION_RETRIES` removed (repair budget lives in the
  orchestrator, `max_repairs=1`).

**Decisions (resolved):** (1) **Option B** failure mode — on a mid-stream verification failure,
discard the failed sentence + the rest of its stream (later sentences were generated conditioned on
the bad one), request **one** repair continuation from the already-spoken verified prefix (avoiding
the rejected claim), verify it the same way; if the repair also fails, **truncate** at the last
verified sentence (Option A fallback). Fail-closed throughout (verifier/stream error → stop at last
verified sentence; first sentence fails twice → silence over falsehood). (2) A citation-heuristic
hit takes the **same** failure path as a consistency contradiction — one failure path, no
special-casing.

**Harness — `agents/streaming_harness.py` (text-only, no TTS/audio):** feeds a fake streaming LLM +
fake verifier (deterministic delays) and reports **time to first verified sentence** — blocking
baseline vs streaming — plus an Option B failure scenario and the citation-no-split case; `--live`
runs the real Fireworks stream + verifier for wall-clock numbers.

**Result:** Done and measured live. **Measured (live, 2 runs):** time to first verified sentence
**8.8 s / 12.7 s (blocking) → 4.1 s / 4.5 s (streaming)** — 54–65% faster; full reply spoken by
~9.4–10.3 s while speaking starts at ~4 s. Offline harness (deterministic fakes) proves the
mechanism: 3.20 s → 1.58 s, citation not split, Option B repair spoken, the conditioned
sentence-after-the-failure never spoken. **Tests: `tests/test_streaming_verify.py` — 20 offline**
(segmenter ×7, orchestrator clean/context/repair/truncate/empty-prefix/citation-failure ×7,
fail-closed ×2, async bridge, opposing_counsel plumbing ×3, `chat_stream` stub); ruff clean; 7 live
deselected. **Docs:** ARCHITECTURE §6 (worker bullet), §6.5 (streaming verification + new mermaid +
harness list), §7 (reply-latency note). No LESSONS entry — no gotcha emerged. **Remaining first-audio
cost** is deepseek's time-to-first-sentence (~2.5–3 s) + one short verify (~1.3 s); next lever =
faster OC model once self-hosted on the MI300X + co-located verifier (§6.5). **Not verifiable here:**
actual TTS playback overlap in a live room (needs mic + worker) — but the sentence pipeline and its
latency are measured.
### Status review & forward-planning pass (2026-07-08) — read-only, no code changed

Full audit of `frontend/` `backend/` `agents/` `infra/` against the docs, a latency audit of the
voice round-trip, and a "what to build next" recommendation. The AMD migration runbook produced by
this pass lives in **ARCHITECTURE §10.5** (lasting reference), not here.

#### A. Current-state audit — what's built, stubbed, or blocked

**Built & verified (offline / no live voice):**
- **Backend (FastAPI) — complete.** All nine §5 user routes + two internal agent routes
  (`/complete`, `/scorecard`), real HTTPBearer auth stub (admin/admin → JWT), scoped agent service
  token (`X-Agent-Token`, constant-time, separate from user JWT), portable SQLAlchemy models
  (`Uuid` + Python defaults, soft-delete, `# SENSITIVE` tags), Alembic `0001_initial`, CORS. **19
  backend pytest pass.** Fail-closed secrets (JWT_SECRET ≥32 chars, empty AGENT_SERVICE_TOKEN
  rejects all internal calls).
- **Frontend (React/Vite) — complete against the real backend.** All five routes; auth via
  `/api/auth/login` + `/me`; ProtectedRoute; SparringRoom connects to LiveKit + publishes mic with a
  scripted-mock **fallback**; completed sessions render the **real** scorecard + transcript. **12
  Vitest pass**, type-check + lint clean.
- **Agents — logic complete, wired for voice.** `session_state`, `verification` (citation regex +
  live consistency check), `opposing_counsel`, `judge`, `objection_classifier` (two-stage gate→LLM,
  debounce, fail-closed), `llm_router`, `scorecard_builder`, `backend_client`, `voice_interrupt`,
  and `main.py` (LiveKit worker). **57 offline pytest pass; 7 live pass** (`-m live`, deselected in
  CI). Text harnesses (`harness.py`, `objection_harness.py`, `session_end_harness.py`) exercise every
  path without voice infra.
- **All five agents↔backend gaps closed** (Gaps 1–5 above): room+mic, objection data-channel events,
  agent persistence, real scorecard/transcript rendering.

**Stubbed / pending (by design):**
- **Auth is `AUTH_MODE=stub`** (admin/admin) — must not touch real attorney/case data (§11). The
  agent service token is already separate, so replacing user auth won't disturb it.
- **LiveKit dev keys** (`devkey`/`secret`) — safe only because LiveKit is localhost-only today; must
  be regenerated before any off-box deploy (§11).
- **Case file *upload*** — case create is JSON only; MinIO file upload deferred (bucket + endpoint
  exist in compose, no upload route wired).

**Blocked (external dependency):**
- **Live voice end-to-end is UNVERIFIED** — the entire real audio path (room join, mic→Deepgram STT,
  ElevenLabs playback, VAD/turn detection, real barge-in *timing*, and that `publish_data` reaches
  the browser's `DataReceived`) needs a live room + real mic + running worker. Blocked on
  **Deepgram/ElevenLabs credit** (keys/credit pending) and a non-headless browser. Everything up to
  the SDK boundary is unit-tested; the SDK wiring (`llm_node` signature, event fields,
  `interrupt`/`say`, `publish_data` topic/reliable flags) is written to the livekit-agents 1.x docs
  and **may need tuning against the installed SDK in a running room**.
- **AMD MI300X droplet — not yet provisioned.** Both agents run on Fireworks. Cutover runbook is
  pre-worked in **ARCHITECTURE §10.5**; it's a config flip, not a code change.
- **Gemma bonus — blocked.** No serverless Gemma (2/3/4) is reachable on this Fireworks account
  (verified `/v1/models` + direct ID probes, all 404). Judge runs `gpt-oss-120b` (JSON) as interim;
  move to Gemma when one is deployable (self-host on the MI300X is the likely unlock).

**Doc-vs-reality discrepancies found (flagged — not silently edited beyond §10.5):**
1. **ARCHITECTURE §2 lists `infra/docker-compose.prod.yml` and `infra/deploy.sh` — neither exists.**
   `infra/` has only `docker-compose.yml` (local dev). §2 also shows per-service Dockerfiles in the
   tree; only `backend/Dockerfile` exists (frontend/agents images deferred).
2. **ARCHITECTURE §10 overstates CI/CD:** "CI builds and tags images on every push; deploy is
   `docker compose pull && up -d`." Reality: CI `docker-build` only `docker build`s the **backend**
   image locally as a smoke test — no registry, no tag, no push, and no prod compose to pull. The
   production deploy path is aspirational.
3. **§2 repo tree** shows `docs/ARCHITECTURE.md` as the only doc; `LESSONS.md` and
   `DEVELOPER_GUIDELINES.md` also live in `docs/` (minor).
   → Recommend a small "doc-accuracy" cleanup task to fix §2/§10 or create the missing files. Not
   done here (this pass is read-only + the two requested docs).

#### B. Latency audit — the core differentiator (identify + prioritize, don't implement)

Target: turn-taking that feels like Zoom/Meet (~200–500 ms gaps), not a laggy bot. Measured numbers
from prior live runs (§7 + build logs): Opposing Counsel `deepseek-v4-pro` median **~4 s (3.5–7.8 s)**;
Judge / verification / objection classifier `gpt-oss-120b` **~2–3 s**; objection classifier with
`max_tokens=512` decides in **~2–2.5 s** (clean fragments short-circuit at 0 s via the regex gate).

**Round-trip, where time actually goes:**

*Objection path (the signature "interrupt mid-sentence" feature):*
`attorney speech → Deepgram interim (~100–300 ms) → candidate_grounds regex (~0 ms) → classify_fragment
LLM (~2–2.5 s) → interrupt()+say() barge-in`. **The classifier LLM call is the whole latency.** A
real objection lands in ~0.5 s; **2–2.5 s makes the barge-in feel late and breaks the illusion.** Root
cause: `gpt-oss-120b` is a 120B model that *reasons before emitting* (why `max_tokens=512` was needed
— `objection_classifier.py:159`), the single worst model class for a sub-second decision.

*Reply path (end of a clean attorney turn):*
`VAD/turn endpoint (~0.5–1 s silence) → opposing_counsel.generate_reply (blocking, full completion,
~4 s) → verification: find_suspicious_citations (~0) + check_consistency (blocking LLM, ~2–3 s,
ALWAYS runs) → [regenerate on fail: +~6–10 s ×≤2] → ElevenLabs Flash TTS (~0.3 s first audio)`.
**Median ≈ 7–11 s before Opposing Counsel speaks a word.** Two structural causes:
- `main.py`'s `OpposingCounselAgent.llm_node` **yields one fully-formed string** (`main.py:78–83`) —
  it generates the *entire* reply, then verifies, then hands TTS a complete blob. **Nothing streams.**
  LiveKit's native token→TTS streaming is bypassed.
- `check_consistency` is a **second blocking 2–3 s call that runs on every reply** even when the reply
  is obviously clean, sequential with generation.

**Prioritized optimizations (recommend; not implementing):**

- **P0 — Objection classifier: swap model + two-tier gate.** (a) Point `OBJECTION_LLM_MODEL` at a
  small, non-reasoning fast model (8B-class / a Fireworks "fast" JSON model), drop `max_tokens` to
  ~32 → target **300–500 ms**. Env-only change, already anticipated (`config.py:59`). (b) For
  unambiguous gate hits (explicit "isn't it true…", tag-questions), fire the *audio* barge-in
  immediately on the regex gate and use the LLM only to confirm/label — the gate already has the
  ground with high recall. This is the differentiator; 2.5 s is unacceptable.
- **P0 — Stream Opposing Counsel LLM → TTS incrementally.** Replace the single-string `llm_node`
  with a streaming completion feeding ElevenLabs Flash sentence-by-sentence, so TTS starts on the
  first clause while the rest generates. Cuts first-audio from ~4 s to **~1–1.5 s** — the single
  biggest win, and what the user explicitly called out. **Tension:** the post-hoc verification/
  regenerate loop can't gate a reply that's already streaming. Resolution (recommend): move to
  **sentence-level verification** (verify each sentence before speaking it) OR make verification the
  cheap common case (below) and accept optimistic streaming with rare mid-stream correction.
- **P1 — Make verification non-blocking on the clean path.** `check_consistency` runs a 2–3 s LLM
  call every turn. Options: gate it behind a cheap heuristic (only when the reply asserts facts), run
  it **concurrently** with TTS start (optimistic), and/or swap `VERIFICATION_LLM_MODEL` to a genuinely
  small model (also env-only). The regenerate loop (`main.py:88–94`, up to 2×) is a rare tail cost —
  keep it, but don't let the *median* pay a full second generate+verify serialization.
- **P1 — Benchmark a faster Opposing Counsel model.** `deepseek-v4-pro` is a reasoning model chosen
  for quality; for "generate a rebuttal" a fast non-reasoning model that streams may feel far snappier
  at acceptable quality. Ties directly into the AMD model choice (§10.5 Step 3) — pick a
  streaming-friendly model there.
- **P2 — Endpointing/VAD tuning.** Silero VAD + turn-detector silence threshold adds to *every* reply;
  tune the balance between "cut the attorney off" and "feels laggy."
- **P2 — Trim prompt/context + enable prompt caching.** Every call ships the full `SessionState.snapshot()`
  + persona; as the session grows so does TTFT. Cap snapshot size; use Fireworks prompt caching for the
  static persona/system blocks.
- **P2 (arrives with AMD) — co-location removes network hops.** Self-hosting reasoning + verification
  on the MI300X (§6.5, §10.5 Step 8) turns the verification call into a local forward pass and drops
  per-call Fireworks RTT (~50–200 ms each) across the objection, reply, and verify calls.

#### C. Recommendation — what to build next (for review before implementing)

Ranked. Live voice is blocked on external credit, so the highest-*leverage* unblocked work is the
latency layer — which is also the differentiator and pays off the moment credit/droplet land.

1. **Objection classifier fast-model swap + two-tier gate (P0, latency).** Biggest
   differentiator-per-effort; largely env + a focused change in `objection_classifier.py` /
   `voice_interrupt.py`; testable offline via `objection_harness.py`. Makes the signature feature feel
   real. **Recommended first.**
2. **Streaming LLM→TTS for Opposing Counsel (P0, latency).** The other half of "feels like a video
   call." Bigger change (`main.py` `llm_node` + verification strategy) — pair it with the
   verification-non-blocking decision. Do second.
3. **Doc-accuracy cleanup (small, unblocks trust).** Fix ARCHITECTURE §2/§10 (missing prod compose /
   deploy.sh / overstated CI) or create the missing infra files. Cheap; keeps the source-of-truth
   honest for future sessions.
4. **When Deepgram/ElevenLabs credit lands:** the live-room verification pass — tune the SDK wiring
   (`llm_node`, event fields, `interrupt`/`say`, `publish_data`) against the installed SDK, measure
   real barge-in timing, and confirm objection events reach the browser. This validates everything the
   offline suite can't.
5. **When the MI300X droplet lands:** execute ARCHITECTURE §10.5 (Opposing Counsel → self-hosted
   vLLM), then co-locate verification (Step 8). Picks up the P1/P2 latency wins for free.

Deliberately **not** recommending: real auth, billing, retention policy, MinIO upload — all correctly
deferred (§11) and none on the critical path to a compelling live demo.

**Result:** Audit + latency audit + forward plan written here; AMD migration runbook written to
ARCHITECTURE §10.5. No code changed. Awaiting the user's decision on what to build first.

---

### Objection barge-in latency: model benchmark + two-tier gate — status: done

**Goal (latency audit rec #1):** cut objection barge-in from ~2–2.5 s toward real-courtroom timing
(~0.5 s), via two independent levers — (1) a faster/reliable classifier model chosen by *measured*
benchmark, and (2) a true two-tier gate where unambiguous phrasing fires **immediately, with no LLM
call at all**. Preserve every existing decision property (recall bias, fail-closed, per-utterance
debounce, the five-outcome audit trail). This is a speed change, not a redesign.

**Precondition confirmed:** `.env` has a live `FIREWORKS_API_KEY`, so the benchmark (live calls) is
runnable now.

**Step 1 — Benchmark every available chat model for the classifier's specific task**
- [ ] Enumerate the account's real catalog via `GET /v1/models` (don't assume a "fast non-reasoning
      model" exists — the Gemma/gpt-oss history says the catalog is limited).
- [ ] Throwaway benchmark script (in scratchpad, **not committed**): for each chat model, run the
      classifier's *actual* message shape (`_build_messages` on a representative candidate fragment +
      a small `SessionState` snapshot), `temperature=0.0`, `response_format={"type":"json_object"}`,
      N≈7 iterations — the same way gpt-oss-120b was benchmarked. Record per model: **median /
      min / max latency, `finish_reason` (must be `stop`), non-empty content, valid-JSON parse.**
- [ ] Probe `max_tokens` per model to find the safe floor: low enough to be fast, **high enough to
      not reproduce the documented empty-content bug** (reasoning models eat the budget → empty; too
      low for *any* model truncates the JSON → parse fail → fail-closed → silent miss). The floor
      must let `{"fire":…,"objection_type":…,"reason":…}` complete with margin.
- [ ] Pick the genuinely fastest **reliable** model (every run `stop` + non-empty + parseable). Set
      it as `OBJECTION_LLM_MODEL` and its `max_tokens`. If it differs from `gpt-oss-120b`, update
      `config.py` default + `.env.example` + ARCHITECTURE §7/§9. Record the full result table in the
      **Result** below and a distilled finding in LESSONS.md.

**Step 2 — True two-tier gate (the bigger lever): immediate-fire tier**
- [ ] `objection_classifier.py`: add `HIGH_CONFIDENCE` — a **precise subset** of the gate patterns
      that is very unlikely to be a false positive: explicit leading tag-questions (`isn't it true`,
      `wouldn't you agree`, `did/didn't you…`) and explicit hearsay (`he/she told me`, `said that`).
      **Deliberately excludes** the broad recall catch-alls (e.g. `r"\?\s*$"` any trailing question)
      and the context-dependent grounds (speculation / argumentative / assumes_facts) — those stay
      LLM-judged.
- [ ] `high_confidence_grounds(fragment) -> list[str]` (pure, offline).
- [ ] In `classify_fragment`: after the unchanged recall gate, if `high_confidence_grounds` is
      non-empty → return an **immediate** `Decision(fire=True, objection_type=<priority pick>,
      reason="high-confidence <ground> pattern", outcome=FIRE)` **without any network call**. Only
      genuinely ambiguous candidates (candidate but not high-confidence) fall through to the existing
      LLM stage. objection_type priority when several match: leading → hearsay.

**Step 3 — Preserve every existing property (verify, don't rewrite)**
- [ ] Recall bias: `candidate_grounds` unchanged — high-confidence is a *subset check layered on
      top*, it never narrows what reaches the LLM.
- [ ] Fail-closed: the LLM path (`try/except → FAIL_CLOSED`) is untouched.
- [ ] Debounce: `ObjectionClassifier.consider` is untouched — an immediate fire sets `fire=True` so
      `_handled` still latches and a growing utterance won't re-fire.
- [ ] Audit trail: reuse the existing five outcomes; immediate fires carry `outcome=FIRE` (the
      `reason` string — "high-confidence … pattern" — is what distinguishes them from LLM fires).
      **No new outcome category** (honoring "not a redesign").

**Step 4 — Measure it: extend `objection_harness.py` (before/after)**
- [ ] Time each fragment's `consider()`; print per-fragment latency + which tier decided it
      (immediate-fire / LLM / gate-short-circuit / debounced).
- [ ] Run the labeled set in two modes and print a summary delta: **(a) LLM-only** (force all
      candidates through the LLM — simulates today's behavior) vs **(b) two-tier** (new). Reports
      median + total latency for each, so the improvement is measured, not assumed.

**Step 5 — Update offline tests (`tests/test_objection_classifier.py`)**
- [ ] New: `high_confidence_grounds` — clear leading / clear hearsay flagged; a trailing-`?`-only or
      speculation fragment is a *candidate* but **not** high-confidence; clean → empty.
- [ ] New: immediate-fire path — a high-confidence fragment fires with `outcome=FIRE` + correct
      `objection_type` **and does not call the LLM** (monkeypatch `chat` to raise; it still fires,
      proving the LLM was skipped).
- [ ] New: an ambiguous candidate still routes to the LLM (monkeypatch `chat`; assert invoked).
- [ ] Keep all existing tests green (recall gate, fail-closed, debounce, outcomes, review log).

**Step 6 — Docs (self-updating rule)**
- [ ] ARCHITECTURE §6: describe the flow as **three tiers** — recall gate → high-confidence
      immediate-fire (no LLM) → LLM judgment for ambiguous candidates. §7 classifier row: chosen
      model + measured latency. §9: `OBJECTION_LLM_MODEL` default if it changed.
- [ ] LESSONS.md: entry capturing the benchmark finding (what's actually fast/reliable on this
      account) and the two-tier-gate lever / the max_tokens truncation-vs-empty-content tradeoff.
- [ ] PLAN: fill the **Result** with the before/after numbers + model table.

**Step 7 — Verify:** `ruff` + `pytest -m "not live"` green (offline); run the extended harness live to
capture the before/after latency numbers; optionally `pytest -m live` for the classifier.

**Decision (resolved):** immediate fires get their **own** outcome value `fire_immediate`, distinct
from `fire` — completing the same instinct that split `gate_rejected` from `llm_no_fire`. If the
high-confidence gate is ever too aggressive we must see it in the data directly, not blended into
decisions the LLM actually reasoned about. Audit categories become six; the review log gains an
`immediate_fires()` partition alongside `gate_rejected()` / `llm_no_fire()`.

**Result:** Done and measured. **Step 1 benchmark (live, N=7, classifier's real task shape):** the
account catalog is 7 models (one image-gen); `gpt-oss-120b` med **1.26 s** (7/7 `stop` + parseable)
is the *fastest and most reliable* — deepseek-v4-pro 3.42 s, glm-5p1 7.86 s, glm-5p2 10.76 s (fired
0/7), kimi-k2p5 500-errored, kimi-k2p6 6.56 s (4/7 parse). **No sub-second / non-reasoning model
exists here — the model lever is exhausted.** `max_tokens` floor probe confirmed the empty-content
bug: mt=128/64/48/32 all → `finish=length`, 0/7 non-empty, for only ~0.3 s savings → **kept
`gpt-oss-120b` @ max_tokens=512, no config change.** **Step 2 two-tier gate (the whole win):** added
`high_confidence_grounds` (precision-biased subset — explicit leading tag-questions + direct hearsay,
excludes the recall catch-alls and context-dependent grounds) and an immediate-fire branch in
`classify_fragment` that fires with **no LLM call**. **Step 3:** recall gate, fail-closed, and
debounce untouched; new sixth outcome `fire_immediate` (distinct from `fire`) + `immediate_fires()`
review partition. **Step 4 harness (live before/after):** clear leading **~1.1 s → 0.000 s**, clear
hearsay **~2.1 s → 0.000 s**; the ambiguous speculation case correctly still pays the LLM (~2.2 s);
session LLM total 5.11 s → 2.22 s. **Step 5:** tests rewritten for three tiers — high-confidence
grounds, immediate-fire-without-LLM (both leading + hearsay), priority, ambiguous-still-reaches-LLM,
six-outcome categorization, three-way review partition; existing gate/fail-closed/debounce tests
kept. **66 offline pass, ruff clean.** **Step 6 docs:** ARCHITECTURE §6 (three tiers) + §7
(classifier row + benchmark note), LESSONS.md (two entries: gpt-oss empty-content `max_tokens` floor;
benchmark-don't-assume + architectural-latency), this PLAN. Benchmark script was a scratchpad
throwaway (not committed). **Not verified here:** real barge-in *timing in a live room* (needs mic +
worker) — but the decision latency itself is measured via the harness.

---

### Populate the session record so the scorecard/transcript are real — status: done

**Problem (found in the first full live session):** the voice pipeline runs end to end, but the
persisted scorecard is a hollow default — **score always 100, empty strengths/weaknesses, judge says
"no objection has been raised"** even though objections were spoken, and the **transcript is
shredded** into ~15 tiny fragments with the barge-in objections missing. Root cause: the live loop
speaks/publishes objections but **never populates `SessionState`'s ledger** (no `record_objection`,
`rule_on_objection`, or `add_established_fact`), persists an attorney turn **per Deepgram `is_final`**
(not per spoken turn), never persists barge-in objection turns, and starts `SessionState()` with
**empty case facts** (`main.py` TODO). `scorecard_builder` is correct — it just has nothing to work
with.

**Fix 1 — Record + persist fired objections `[S]` (`voice_interrupt.py`, `main.py`).**
On a classifier fire in `handle_interim`, in addition to `interrupt()`+`say()`+`publish`:
- `classifier.state.record_objection(grounds=decision.objection_type or "objection",
  raised_by="opposing_counsel")` → enters it in the objections ledger (pending).
- `classifier.state.add_turn("opposing_counsel", objection_utterance(decision),
  was_interruption=True)` → the barge-in now appears in the saved transcript with the red styling.
Keeps `voice_interrupt` livekit-free (mutates only `classifier.state`). Scoping: the classifier fire
is the *formal* objection signal; `llm_node` replies stay argument turns (unchanged).

**Fix 2 — End-of-session judge assessment (the crux) `[L]` (`judge.py`, `main.py`).**
Replace the single closing `generate_ruling` with **one structured judge call** at shutdown,
`judge.assess_session(state) -> {rulings: [...], established_facts: [...], closing_ruling: str}`:
- **rulings** — sustained/overruled for each pending objection, in ledger order, from the transcript
  + objection context. Applied via `state.rule_on_objection` → drives score (−8/sustained) and
  weaknesses (sustained grounds). Fail-safe: unparseable/short output → remaining default to
  **overruled** (never fabricate a penalty against the attorney).
- **established_facts** — 2–5 key facts the attorney put on the record without a sustained objection
  → `state.add_established_fact` → drives strengths (fixes the empty "no facts established").
- **closing_ruling** — the verbatim judge line, now generated *after* the ledger is populated so it
  reflects what actually happened. One LLM call, fits the existing `_persist_at_end` shutdown flow.

**Fix 3 — Group attorney `is_final`s into coherent turns `[M]` (`main.py`).**
Keep feeding **every** interim/final to the objection classifier (unchanged), but stop adding a
transcript turn per `is_final`. Instead accumulate the attorney's finals and commit **one** turn when
the user's turn ends — via the Agent `on_user_turn_completed(chat_ctx, new_message)` hook (full
committed turn) if it exists in the installed SDK, else buffer-and-flush when `llm_node` starts.
**Needs SDK verification** of the exact hook/event (written to the docs, tuned against the installed
`livekit-agents`).

**Fix 4 — Load case facts at room join `[M]` (backend + `main.py`).**
- Backend: new **agent-authed read route** `GET /api/sessions/{id}/context` (X-Agent-Token, like the
  write routes) → `{case_facts}` (joins session→case). New schema + a `session_service` read + it
  reuses `require_agent_service`.
- Agent: `backend_client.get_session_context(session_id)` at `entrypoint`, seeding
  `SessionState(case_facts=...)` so verification + the judge reason with the real case (the room name
  already encodes the id). Tolerate failure → empty facts (current behavior), never crash the room.

**Tests (offline / CI):**
- `voice_interrupt`: fire now records an objection + adds a `was_interruption` turn; no-fire doesn't.
- `judge.assess_session`: pure `_build_assessment_messages` + `_parse_assessment` (rulings list,
  established facts, closing ruling); short/garbled output → overruled-default fail-safe.
- `scorecard_builder`: already covered — add a case with sustained objections + established facts →
  score < 100, real weaknesses/strengths (mostly exercises existing paths).
- Backend: `test_agent_routes` — the new context route returns case facts for the agent token,
  401s without it; user JWT can't reach it.
- Agent turn-grouping helper (if buffer-and-flush): unit-test the accumulator (joins finals, resets
  per turn) without livekit.
- Live (`@pytest.mark.live`, deselected): `assess_session` returns well-formed rulings on a seeded
  transcript.

**Docs:** ARCHITECTURE §6/§6.5 (live loop now feeds the ledger; judge end-of-session assessment), §5
(new internal context route), §8 (who writes what — unchanged); LESSONS if a gotcha emerges; this
PLAN result.

**Verify:** ruff + `pytest -m "not live"`; extend `session_end_harness.py` to seed a state with
recorded objections → `assess_session` (live) → confirm a scorecard with score < 100, real
weaknesses, established-fact strengths, and a coherent ruling; then a full live room session to
confirm objections + coherent attorney turns land in the persisted transcript.

**Open decisions (please confirm):**
1. **Judge ruling timing — end-of-session batch (recommended) vs. inline per objection?** Batch = one
   LLM call at shutdown, no added live-loop latency, fits current flow, but the judge doesn't rule
   *aloud* mid-session. Inline = more realistic (rules right after each objection, could speak it)
   but adds an LLM call + latency into the barge-in path and is more complex. I recommend **batch**
   for now; inline can layer on later.
2. **Established facts (strengths) — have the judge extract them (part of `assess_session`,
   recommended) vs. leave strengths as a known gap for now?** Extraction makes strengths meaningful
   in the same single call; skipping keeps scope tighter.
3. **Scope check:** OK to add a backend route + touch `judge.py` fairly substantially (Fix 2/4), or
   keep this round to the cheap wins (Fix 1 + Fix 3) and defer the judge assessment + case-facts
   loading to a follow-up?

**Result:** Done, all four, live-verified. **Fix 1:** `voice_interrupt.handle_interim` on a fire now
`record_objection(...)` (pending) + `add_turn(..., was_interruption=True)` via `classifier.state` —
barge-ins land on the record. **Fix 2:** `judge.assess_session(state)` — one structured call
(`_build_assessment_messages` renders the transcript; `_parse_assessment` normalizes rulings, drops
blank facts) returning `{rulings, established_facts, closing_ruling}`, fail-safe on empty/garbage
(→ no rulings/facts + neutral ruling). `main._persist_at_end` applies rulings → `rule_on_objection`,
adds facts, uses the closing ruling. Kept `generate_ruling` (harness/tests). **Fix 3:** attorney
turns committed once per utterance via the agent's `on_user_turn_completed` hook; removed the
per-`is_final` `add_turn` (classifier still fed every interim). **Fix 4:** backend
`GET /api/sessions/{id}/context` (agent-authed) + `agent_write_service.get_session_context` +
`backend_client.get_session_context`; `entrypoint` seeds `SessionState(case_facts=…)`, tolerant of
failure. **Gotcha:** `assess_session` hit the gpt-oss empty-content bug at `max_tokens=512` (heavier
reasoning than the classifier) → raised to **1536** (LESSONS updated: the floor scales with task
complexity). **Verified:** harness with pending objections → live `assess_session` → **score 84**
(100−8×2), real strengths (judge-extracted facts), weaknesses (sustained hearsay + leading), coherent
record-aware closing ruling, transcript with both barge-ins. **Tests: agents 97 offline + 8 live
(new: 3 voice_interrupt ledger, 9 judge assessment, 1 live assess); backend 25 (2 new context-route);
ruff clean.** **Docs:** ARCHITECTURE §5 (context route) + §6.5 (live ledger feeding + end-of-session
assessment); LESSONS (budget-scales-with-complexity). Decisions built as recommended: batch ruling +
judge-extracted facts, all four together. **Not verified here:** a full live *room* session
(needs mic + worker) — but every piece is proven via the harness + unit/live tests.

---

### Session-end flow: spoken judge ruling + scorecard reliably appears — status: done

**Problem (live session):** after "End session" the scorecard showed "Not available yet" (stale
copy), and the judge never spoke. Root cause: the scorecard was written only at *job shutdown*,
which doesn't happen promptly when the attorney leaves (the agent keeps the room non-empty), and the
frontend fetched once (no retry). The judge produced a written ruling but never delivered it aloud.

**Fixes (all four, as approved):**
- **Agent (`main.py`):** refactored persistence into idempotent `_finalize_session(speak)`.
  Triggered by an `end_session` data message (topic `control`) → assess → **judge speaks the closing
  ruling** (`session.say`) → persist → publish `end_complete`. Backstops that finalize *silently*:
  `participant_disconnected` (tab closed) and the shutdown callback. Runs exactly once.
- **Frontend `useSparringRoom`:** `endSession()` publishes `end_session` and resolves on
  `end_complete` (or a 30 s timeout, so a missing agent never hangs); `DataReceived` handles the
  control message.
- **Frontend `SparringRoom`:** "End session" in a live session shows "The judge is delivering the
  ruling…", awaits `endSession()`, then navigates; fallback (no agent) navigates straight.
- **Frontend `Scorecard`:** polls on 409/404 (~30 s, `retry` + 2 s delay) showing a "Scoring your
  session…" state, fetches the transcript only once the scorecard exists, and the stale "isn't wired
  up yet" copy → honest "Scorecard not ready".

**Tests:** agents 97 offline + 8 live, ruff clean; frontend type-check + lint + 12 tests (Scorecard
test updated to assert the polling state). **Docs:** ARCHITECTURE §6.5 (end-of-session handshake +
spoken ruling). **Not verified here:** the live handshake + spoken ruling need a real room + agent —
logic is unit-tested and the fallback path is unchanged.

**Deferred (not in scope):** a spoken judge *during* the session (inline rulings after each
objection) — this delivers only the closing ruling aloud.

---

### Double-fire debounce bug + inline spoken judge rulings — status: done

*(Stacked on the PR #4 branch — the inline rulings interact with `_finalize_session`/assess_session
from that PR.)*

**Bug — objection fired twice for one utterance (traced, not guessed).** The live transcript shows
two "Objection — hearsay." turns around a single attorney utterance, the second ~1 s after speech
stopped. Trace: (1) an *interim* arrives lowercase/unpunctuated ("i i my client told me…") → fires;
debounce stores it as `_prev`. (2) Growing interims pass `current.startswith(prev)` → correctly
debounced (the only case currently tested). (3) After the pause, Deepgram emits the segment's
**final** with smart formatting ("I, I, my client told me… the safety report, quote, wasn't going to
matter…") — finals are **not prefix-stable** with interims (casing, inserted punctuation,
"March third"→"March 3"), so `startswith` fails, `_is_continuation` treats it as a NEW utterance,
the classifier re-arms, and the revised final re-fires on the same content. The "pause" is
Deepgram's endpointing delay before the final lands. `UserInputTranscribedEvent` carries **no
segment id** (verified: transcript/is_final/speaker_id only), so the fix must be text/time-based.

**Fix (two layers, both pure/offline-testable):**
1. **Normalized continuation check** — `_is_continuation` compares a normalized form (lowercase,
   strip non-alphanumeric, collapse whitespace), so punctuation/casing revisions of the same
   utterance no longer look like new speech. (Doesn't cover digit rewrites like "third"→"3" — hence
   layer 2.)
2. **Re-fire cooldown** — after any fire, suppress further fires for `refire_cooldown` seconds
   (default ~5 s), with an **injectable clock** (`time.monotonic`) so tests/harness stay
   deterministic. Robust against any transcript rewrite; realistic (no courtroom double-objection
   within 5 s of being interrupted); and it **doubles as the don't-object-over-the-judge guard**
   (below). Suppressions report as `DEBOUNCED` with a cooldown reason (no new audit category).

**Regression tests (own cases, not just growing-fragment):** interim fires → grown interim
debounced → *pause* → **revised final (casing/punctuation changed, same content) → must NOT fire**;
cooldown with injected clock (non-continuation objectionable fragment at +1 s suppressed, at +6 s
fires); `objection_harness` gains the revised-final sequence with a clock that jumps between
utterances so the demo matches real pacing.

**Feature — inline spoken judge rulings (real courtroom sequence).** When an objection fires
(immediate or LLM-judged) and OC's line is spoken, the Judge immediately follows aloud:
"Sustained." / "Overruled — <one short reason>."

- **`judge.quick_ruling(state, objection, fragment)`** — fast-model call reusing the **objection
  classifier's config** (gpt-oss-120b class; same latency philosophy as classifier/verification; no
  new env vars, swap via `OBJECTION_LLM_*`), temp 0, `max_tokens=512` (the known gpt-oss floor),
  JSON `{"ruling": "sustained"|"overruled", "reason": "<a few words>"}`. Pure `_build`/`_parse`
  split for offline tests.
- **Wiring:** `voice_interrupt.handle_interim` captures the `Objection` returned by
  `record_objection` and calls an **injectable** `judge_rule(objection, fragment)` after OC's line +
  publish (module stays livekit-free). `main.py` provides it: `quick_ruling` off-loop →
  `state.rule_on_objection(objection, ruling)` **immediately** → judge speaks
  (`session.say(..., allow_interruptions=False)`) → `state.add_turn("judge", …)` → publish a
  `{"type": "ruling", …}` data event; frontend renders it as a judge line (small — same parse path
  as objection events).
- **Latency/ordering:** ruling generation starts while OC's objection line is playing;
  `session.say` calls are queued by the SDK, so the judge line plays right after OC's. Expected
  ruling audio ≲1 s after OC's line ends (gpt-oss ~1.3 s ≈ OC line duration).
- **Fail-safe:** quick-ruling error/unparseable → judge stays **silent**, objection stays
  **pending**; the end-of-session `assess_session` backstop rules it. Never fabricate a penalty —
  consistent with every other fail-safe in the pipeline.
- **`assess_session` update:** mechanically it already only rules *pending* objections (the zip is
  over `pending_objections()`), so inline-ruled ones can't be re-ruled; update
  `_ASSESSMENT_INSTRUCTION` so the closing ruling **references/summarizes already-ruled objections**
  (they're in the SESSION RECORD snapshot with their rulings) instead of ignoring them. Scorecard
  needs no change — `sustained_objections()` counts rulings regardless of when they landed.

**Barge-in interaction & interruptibility (the design questions):**
- **Attorney cannot interrupt the Judge mid-ruling** (recommended): ruling spoken with
  `allow_interruptions=False` — courtroom realism (you don't talk over the judge), and it's a 1–2 s
  line. OC's objection line stays interruptible (unchanged).
- **OC cannot object while the Judge is ruling:** a classifier fire during the ruling would call
  `session.interrupt()` and cut the judge off mid-sentence. The **re-fire cooldown covers exactly
  this window** — the ruling always follows a fire, so the classifier is in cooldown (~5 s ≳ OC
  line + ruling generation + ruling speech). One mechanism for both the bug and this guard; no extra
  flag. Residual: a genuinely new objectionable utterance inside the cooldown is suppressed —
  acceptable (un-courtroom-like anyway; end-of-session assessment still sees the transcript).
- **Judge voice = OC voice for now (flagged):** one `AgentSession` has one TTS; a distinct judge
  voice needs a second TTS instance + manual audio playout — follow-up, not here.

**Tests (offline):** the debounce regression set; `voice_interrupt` — on fire, `judge_rule` is
awaited with the recorded Objection (not on no-fire/debounce); `quick_ruling` `_parse` (valid /
unknown-ruling fail-safe / garbage raises) + monkeypatched error path leaves the objection pending;
harness gains an inline-ruling printout (fragment → fire → ruling → ledger state). **⚠️ Needs a live
room:** actual audio sequencing (attorney cut → OC line → judge ruling), non-interruptibility feel,
cooldown vs. real speech pacing, ruling-event rendering.

**Decisions (resolved):** (1) judge ruling not interruptible ✓; (2) failed ruling → silent +
pending, never fabricated ✓; (3) **adjusted:** not a fixed timer alone — re-arming is gated on the
ruling call *actually completing* (success/failure/timeout) AND a 5 s floor
(`hold()`/`release_hold()` + cooldown), so a slow ruling can't be objected over; (4) fast model =
objection classifier config ✓; (5) **adjusted:** the Judge gets a DISTINCT voice now via
`JUDGE_VOICE_ID` (default "Daniel", already free-tier-verified) — judge lines synthesized on a
second TTS instance, played via `session.say(audio=…)`.

**Result:** Done. **Bug fix:** `_is_continuation` compares **normalized** text (casing/punctuation
revisions of the same utterance no longer re-arm) + a **re-fire cooldown** (5 s floor, injectable
clock) + the **ruling hold**. Harness proves the exact regression live: the revised final
("Now, isn't it true…?", +1 s pause) is now **debounced** where it previously re-fired.
**Feature:** `judge.quick_ruling` (fast model; `max_tokens=1024` — 512 was intermittently EMPTY for
this prompt, the LESSONS budget-scales-with-complexity rule again; verified 3/3 live) →
`rule_on_objection` immediately → judge speaks in the **Daniel** voice via `_judge_say`
(`session.say(audio=…)`, not interruptible) → judge turn recorded → `{"type":"ruling"}` data event
rendered live by the frontend (parse + judge line, tests added). The closing ruling also speaks in
the judge voice now. `_ASSESSMENT_INSTRUCTION` updated: already-ruled objections are final —
acknowledge, don't re-rule (mechanically enforced by the pending-only zip). **Tests: agents 110
offline + 10 live** (new: revised-final regression, cooldown timing, hold-gating, normalized
continuation, judge_rule wiring ×3, quick_ruling ×6, live quick_ruling; two pre-existing tests
updated for injected clocks), **frontend 16** (ruling parse/map ×4), ruff + type-check clean.
**Docs:** ARCHITECTURE §6 (debounce/cooldown/hold), §6.5 (inline rulings section), §9
(`JUDGE_VOICE_ID`); LESSONS (STT finals not prefix-stable); `.env.example`. **⚠️ Needs a live room:**
the audio sequencing (attorney cut → OC line → judge ruling in a different voice), the
non-interruptibility feel, cooldown vs. real pacing, and ruling-event rendering.

---

### Elaboration ordering + residual double-fire + immediate-path latency — status: done

**Issue 1 — OC's full elaboration plays AFTER the judge ruling (traced, not guessed).**
Two *independent* Opposing-Counsel utterances exist for one objectionable turn, plus the ruling:
- **Canned objection** — `handle_interim`, fired on an **interim** (mid-speech): `interrupt()` +
  `say("Objection — leading.")`, enqueued immediately at the fire.
- **Judge ruling** — `judge_rule` (also in `handle_interim`): `quick_ruling` (~1–2 s LLM) then
  `_judge_say("Sustained…")`, enqueued ~1–2 s after the fire.
- **Full elaboration** — `OpposingCounselAgent.llm_node`, fired on **turn-end** (turn detector),
  streams `generate_reply` (~1.5 s to first sentence, and turn-end is *after* the fire), enqueued
  last. So through the single TTS output queue the order becomes canned → ruling → elaboration, and
  the elaboration ("Objection, leading the witness…") re-objects *after* the judge already ruled.
Root cause: the end-of-turn full reply is **redundant** on a turn where an objection already fired
and was ruled — it re-objects and races the ruling.
**Recommendation: DROP the end-of-turn elaboration on turns where an objection fired** (not:
serialize elaboration-before-ruling). Why: (a) courtroom realism — OC objects → judge rules →
attorney continues; OC does not then deliver a full argument; (b) removes the duplication; (c)
eliminates the race entirely (nothing to reorder); (d) the full reply still fires on turns with
**no** objection (normal cross-examination), so OC still engages substantively when appropriate. The
"elaboration before ruling" alternative is worse — a full persuasive argument no longer fits once the
judge rules instantly, and serializing it would *delay* the ruling.
**Plan:** a per-turn `objected` flag (shared dict): set on fire (in `judge_rule`), checked+reset at
the top of `llm_node` — if set, `llm_node` returns without generating (stays silent, like the
existing no-verified-sentences path). Offline test via the harness/a fake: fire → flag set →
llm_node yields nothing; no fire → llm_node generates normally.

**Issue 2 — "hearsay" fired twice: investigated, most likely NOT an agent double-fire on current code.**
Evidence: if the agent fired twice, `SessionState.transcript` would hold **two** OC objection turns
→ the persisted **scorecard transcript shows one** hearsay barge-in, while the **live view shows
two**. That asymmetry points away from the agent. Analysis of the current classifier: normalized
debounce + 5 s cooldown + hold suppress same-utterance and within-5 s re-fires — including the
plausible agent-side variant (two hearsay triggers, "told me" then "said", split across a Deepgram
segment boundary at `endpointing_ms=25`): the second segment is a non-continuation but lands inside
the cooldown → suppressed. Ranked causes: **(1)** two *genuinely distinct* hearsay statements > 5 s
apart → **correct**, not a bug; **(2)** the session ran on **pre-fix** code; **(3)** frontend has
**no dedup** — a redelivered data packet or a double-registered `DataReceived` listener double-renders
one event (the mapper mints a random React key each call, so a duplicate can't be de-duplicated).
**Plan:** (a) add an explicit agent regression test for the segment-split-within-cooldown hearsay
case (locks in that cooldown covers it); (b) add **frontend dedup** — carry a stable event id
(the agent's `timestamp` + type) and ignore an event whose id was already appended (defensive
against redelivery/double-listener regardless of root cause); (c) confirm the worker is on the
merged fix.

**Issue 3 — immediate-fire latency: MEASURED (not estimated).**
- Gate decision (`candidate_grounds` + `high_confidence_grounds`): **23 µs** — effectively zero.
- ElevenLabs `/stream` time-to-first-audio-byte (canned "Objection — leading."): **0.11–0.30 s,
  median ~0.14 s** (3 real calls).
- Deepgram STT config: `interim_results=True`, `no_delay=True`, `endpointing_ms=25` (already the
  most aggressive setting for fast interims/finals).
**Key finding:** the immediate objection fires on an **interim (mid-speech)**, so Deepgram
**endpointing is NOT in this path** — tuning endpointing sensitivity will *not* speed the canned
objection (it only affects turn-end finals). The measurable pieces (gate ≈0, TTS ~0.14 s) are fast;
the immediate path is not the slow part. The 2–3 s the user felt earlier is the **elaboration**
(`generate_reply`), which Issue 1's fix removes on objected turns. The two pieces not measurable
offline — Deepgram **interim delivery latency** and **WebRTC playout buffering** — need a live
capture.
**Plan:** add lightweight timestamp instrumentation to the immediate-fire path (interim-received →
gate decision → `say()` called → first audio frame if exposed) behind a debug log, capture from ONE
live session, and report the true end-to-end number. Do **not** change `endpointing_ms` for the
immediate path (wrong lever). Separately flag: `endpointing_ms=25` is very aggressive and could
end the attorney's *turn* prematurely (a distinct end-of-turn-reply concern, not the immediate path)
— worth a look if turns feel cut off, but out of scope here.

**Decisions (resolved):** (1) drop the elaboration on objected turns; (2) agent segment-split
regression test **+** frontend dedup — the worker was **confirmed on the exact PR #4 head during the
double-hearsay test**, so this is genuinely a frontend duplicate-render (not stale code, not an agent
double-fire), making dedup the real fix, not just defensive; (3) add timestamp instrumentation to the
immediate-fire path, do NOT touch `endpointing_ms`.

**Build:**
- **Issue 1:** shared `turn_flags = {"objected": False}` in `entrypoint`; `judge_rule` sets it True
  on fire; `OpposingCounselAgent.llm_node` checks+resets at the top → returns without generating
  when set (stays silent, like the no-verified-sentences path). Non-objected turns reply normally.
- **Issue 2:** agent test — two hearsay triggers ("told me" then "said") split across a segment
  boundary, second inside the cooldown → exactly one fire. Frontend — the agent stamps a `timestamp`
  on the ruling event too; the hook keeps a per-session `seen` set keyed on `type:timestamp` and
  ignores a repeat, so a redelivered packet / double-registered listener can't double-render.
- **Issue 3:** `handle_interim` logs (INFO) the gate-decision time and interrupt+say-dispatch time on
  a fire; capture the interim→audio breakdown from one live run (first-audio-frame needs deeper TTS
  hooks — flagged).

**Result:** Done. **Issue 1:** `turn_flags["objected"]` set on fire (`judge_rule`), checked/reset at
the top of `llm_node` → the full end-of-turn reply is skipped on objected turns (object → rule →
continue); normal turns reply as before. **Issue 2:** agent regression test
`test_two_hearsay_triggers_across_segment_boundary_fire_once` (two triggers, second inside the
cooldown → one fire) + frontend dedup — ruling events now carry a `timestamp`, the hook keeps a
per-session `seen` set keyed `type:timestamp` and drops repeats, so a redelivered packet / double
listener can't double-render (the confirmed real cause: worker was on the PR #4 head, so it's a
frontend duplicate, not agent/stale). **Issue 3:** measured — gate **23 µs**, ElevenLabs `/stream`
TTFB **~0.14 s** (0.11–0.30 s); endpointing (`=25 ms`) is NOT in the immediate path (fires on
interims) so it was left untouched; `voice_interrupt` now logs `decide` + `interrupt+say` times per
fire for a live end-to-end capture. **Tests: agents 111 offline + 9 live; frontend 16; ruff +
type-check clean.** **Docs:** ARCHITECTURE §6.5 (object→rule→continue, latency, dedup). **⚠️ Needs a
live room:** the reordered audio (no elaboration after the ruling), that the double-hearsay is gone,
and the true immediate-path breakdown (Deepgram interim latency + WebRTC playout, not measurable
offline) from the new instrumentation logs.

---

### Live objection→ruling audit: ruling latency, double-ruling, judge mislabel — status: done

Independent trace of three live symptoms across `main.py`, `judge.py`, `voice_interrupt.py`,
`session_state.py`, `useSparringRoom.ts`, `SparringRoom.tsx`, `TranscriptLine.tsx`. They are **not**
one root; two share an architectural cause (the Judge is multiplexed onto the single Opposing-Counsel
`AgentSession`), one is separate.

**Symptom 1 — the "Sustained" arrives too late (root: serialized generation).** `handle_interim`
does `await session.interrupt()` → `await session.say(canned)` → `await judge_rule(...)`. Awaiting the
canned `session.say` blocks until its **playback finishes**; only then does `judge_rule` start
`quick_ruling` (~1.3 s LLM). So the ruling audio lands ≈ canned-playback (~1 s) **+** quick_ruling
(~1.3 s) ≈ 2–3 s after the objection, by which time the attorney has resumed. **Fix:** start
`judge_rule` as a **concurrent task** before awaiting the canned line, so `quick_ruling` overlaps the
canned playback; the ruling's own `session.say` still enqueues *after* the canned (SDK serializes the
speech queue), so order is preserved but the gap drops to ≈ max(canned, quick_ruling) ≈ 1.3 s. The
~1.3 s model floor remains — live-confirm whether it's tight enough.

**Symptom 2 — two "Sustained" for one objection (root: NOT a double ledger-rule; a frontend dup).**
Traced the "ruled twice by two paths" hypothesis and it does **not** happen: inline `judge_rule`
calls `state.rule_on_objection` (→ resolved); end-of-session `assess_session` only rules
`state.pending_objections()`, which excludes resolved ones, and its prompt says already-ruled
objections are final; the inline↔finalize race is handled — whichever loses hits
`rule_on_objection`'s "already ruled" `ValueError`, which both call sites catch. So the ledger is
ruled exactly once and neither path double-publishes. The doubled *display* is a frontend
render-dup — the **ruling-event equivalent of the earlier double-hearsay**, and **PR #5's
ruling-`timestamp` dedup is exactly its fix** (before PR #5 ruling events had no timestamp →
`parseRulingData` fell back to `Date.now()` → two deliveries got different keys → no dedup). So the
observed double was almost certainly pre-PR#5 and is already addressed on current `main`. **Fix
(hardening + regression):** hoist the dedup `seen` set to a `useRef` so it's shared across effect
re-runs (robust even if two `DataReceived` listeners ever coexist), and add a `session_state`
regression test that an already-ruled objection is excluded from `pending_objections()` and cannot be
re-ruled. **Live-confirm** it no longer recurs on current main.

**Symptom 3 — closing ruling labeled "Opposing Counsel" (root: one agent participant; label only).**
The Judge is voiced through the same `AgentSession` as Opposing Counsel (`_judge_say` → `session.say`
on `judge_tts`/`JUDGE_VOICE_ID`). The **audio is correct** (judge voice — verified). But the
active-speaker badge (`SparringRoom.tsx`) is driven by `ActiveSpeakersChanged`, and `updateSpeaker`
maps *any* remote (agent) audio to `opposing_counsel` — so every judge line (inline rulings AND the
closing ruling) shows "Opposing counsel speaking." It's a **label-only** bug. The frontend can't tell
judge from OC from audio (one participant), so it needs a signal. **Fix:** `_judge_say` publishes
`{type:"judge_speaking", speaking:true|false}` around the judge's audio; the hook tracks
`judgeSpeaking`; the badge shows "Judge speaking" when set. Covers inline + closing.

**Shared thread:** Symptoms 1 and 3 both fall out of the Judge sharing the single OC `AgentSession`
(serialized speech queue; single participant identity). A truly separate judge participant would
dissolve both — noted as a larger follow-up; the targeted fixes above are lower-risk for now.

**Tests:** voice_interrupt — ruling generation starts concurrently with the canned line, order
preserved, hold released on success/raise (extend existing); session_state — resolved objection not
re-ruled / excluded from pending; frontend — `parse`/dedup of `judge_speaking` ignored as a line;
existing ruling/objection dedup intact. **⚠️ Needs a live room:** whether ~1.3 s ruling gap is tight
enough, that the double no longer appears, and the "Judge speaking" label during real audio.

**Result:** Done. **S1 (latency):** `handle_interim` starts `judge_rule` as a concurrent task before awaiting the canned line, so `quick_ruling` overlaps its playback; gap ≈ max(canned, ~1.3 s) instead of the sum. **S2 (double):** confirmed NOT a double ledger-rule (verified + regression test `test_inline_ruled_objection_is_not_re_ruled_at_session_end`); it was the ruling-event analog of the double-hearsay, already fixed by PR #5's ruling-`timestamp` dedup — hardened further by hoisting the frontend `seen` set to a shared ref. **S3 (label):** the audio was already the judge voice; only the active-speaker badge was wrong (one agent participant). `_judge_say` now publishes `{type:"judge_speaking"}` boundaries; the hook tracks it and the badge shows "Judge speaking" (inline + closing). **Tests: agents 113 offline + 9 live (+ canned-before-ruling ordering, inline-not-re-ruled); frontend 19 (+ parseJudgeSpeaking); ruff + type-check clean.** **Docs:** ARCHITECTURE §6.5 (concurrency, dedup ref, judge-speaking), LESSONS (say() blocks on playback; attribute multiplexed personas with a signal). **⚠️ Needs a live room:** whether the ~1.3 s ruling gap is tight enough, that the double is gone, and the "Judge speaking" label during real audio.

---

### Judge as a real LiveKit participant (attribution by construction) — status: done (needs live-room confirmation)

**Goal:** give the Judge a genuinely distinct identity in the room, replacing the
`judge_speaking` data-channel workaround. Speaker attribution should be structural — who is
talking is known from *which participant's track is playing*, not inferred from a synthetic event.

**Research (verified against the installed SDK — livekit 1.1.12 / livekit-agents 1.6.4 /
livekit-api 1.1.1; every claim below was import-checked, not assumed):**
- `livekit.api.AccessToken` mints tokens **locally** (pure JWT, no server call) — the worker already
  holds `LIVEKIT_API_KEY/SECRET/URL`, so it can mint a `judge` identity itself. Verified offline.
- A **second independent `rtc.Room` connection** in the same worker process is supported (multiple
  rooms/connections per process is a normal SDK pattern; `Room.connect(url, token)` verified).
- Publishing synthesized speech on it: `rtc.AudioSource(sample_rate, num_channels)` +
  `LocalAudioTrack.create_audio_track` + `publish_track`, pushing the ElevenLabs plugin's
  `SynthesizedAudio.frame`s via `capture_frame`, and **`wait_for_playout()`** exists for
  completion. All verified present.

**Options evaluated:**
1. **Second room participant ("judge") — RECOMMENDED.** Own connection + identity + audio track.
   Attribution is correct by construction *everywhere*: `ActiveSpeakersChanged` reports the judge
   participant (the speaking indicator needs zero inference), track attachment just works
   (frontend already attaches all remote audio), and any future per-speaker feature (live captions,
   volume, avatar) comes free. Judge audio leaves the OC `AgentSession` speech queue → the judge is
   non-interruptible **by construction** (session.interrupt()/VAD can't touch it). Complexity:
   moderate (token mint + one connection + one audio-source pipeline + explicit sequencing, below).
2. **Second audio track under the existing agent participant.** Less code (no second connection),
   but **active-speaker detection is per-participant**, so the "who's speaking" indicator still
   can't distinguish judge from OC — attribution would still be inference (track-name inspection).
   Fails the "by construction" bar. Rejected.
3. **Keep the synthetic `judge_speaking` events (status quo).** Works, but attribution is an
   application-layer claim, ordering-fragile, and invisible to anything that doesn't parse our
   events. Being replaced; retained ONLY as the fallback path (below).

**Design:**
- `agents/judge_participant.py` (livekit-dependent, not imported by CI tests):
  `JudgeParticipant(url, api_key, api_secret, room_name, tts)` — `connect()` mints the token
  (identity `judge`, publish-only grants) and joins; `say(text)` synthesizes on the judge TTS and
  `capture_frame`s + `wait_for_playout()`; `aclose()`.
- `agents/judge_voice.py` (livekit-FREE, CI-tested): `JudgeVoice(primary, fallback)` — try the
  participant; on ANY failure fall back to the current working path (`session.say(audio=…)` +
  `judge_speaking` events) and log loudly. **This is the safety requirement:** if LiveKit refuses
  anything at runtime, the session degrades to exactly today's behavior, never to silence.
- **Sequencing fix (new, required):** today the ruling's `say` is serialized by the session speech
  queue behind the canned line. A separate participant has NO shared queue — a fast `quick_ruling`
  could speak OVER the canned objection. `handle_interim` therefore passes a `wait_for_clear`
  awaitable (an `asyncio.Event` set when the canned `say` returns, i.e. after playout) and
  `judge_rule` awaits it between ledger-update and speaking. Generation still overlaps playback.
- **Frontend:** pure `mapActiveSpeaker(speakers)` helper — identity `judge` → Judge, other remote →
  Opposing Counsel, local → attorney (priority judge > OC); the badge gets "Judge speaking" from
  the real active-speaker signal. The `judge_speaking` event handling is KEPT solely to label the
  fallback path.
- **Cleanup:** `aclose()` on shutdown; the judge participant joining also (harmlessly) satisfies
  the frontend's agent-presence promotion.

**Ruling-gap honesty:** the ~1.3 s gap is dominated by `quick_ruling` generation, which already
overlaps the canned playout (PR #6). This change removes queue-scheduling overhead and any waiting
behind stray queued OC speech (~0–0.2 s), and starts judge audio exactly at canned-done + TTS TTFB
(~0.15 s). **It does NOT materially shrink the generation floor** — the win is correctness of
attribution + non-interruptibility by construction, not latency.

**Tests:** `judge_voice` (primary used; fallback on primary failure; fallback errors surface;
no-primary → straight to fallback); `voice_interrupt` — judge speak gated on canned-say completion
(order: canned → ruling) with the existing concurrency preserved; frontend — `mapActiveSpeaker`
(judge identity wins over OC; remote w/o judge → OC; local only → you; empty → null). Existing
suites stay green. **⚠️ Needs a live room:** the judge participant actually joining (server accepts
the minted token), real active-speaker attribution during judge audio, audio quality via the raw
AudioSource path, and the no-overlap sequencing under real playout timing.

**Result:** Built on `feat/judge-participant` (main untouched — the interim fix stays the safe baseline). **Agent:** `judge_participant.py` (token minted locally, identity `judge`, publish-only grants; own `rtc.Room` connection; lazy `AudioSource` sized from the first TTS frame; `capture_frame` + `wait_for_playout`; per-line lock; `aclose()` on shutdown) and `judge_voice.py` (livekit-free `JudgeVoice`: primary participant, fallback = the previous session-multiplexed path INCLUDING the `judge_speaking` label events — a LiveKit failure degrades to the old behavior, never a silent judge). `voice_interrupt` gained the `wait_for_clear` gate (asyncio.Event set when the canned say returns) because a second participant has NO shared speech queue — the implicit canned→ruling ordering had to become explicit. `config` exposes LIVEKIT_URL/KEY/SECRET. **Frontend:** pure `lib/activeSpeaker.mapActiveSpeaker` (judge identity → Judge > other remote → OC > local → you); hook uses it; badge shows 'Judge speaking' structurally (synthetic event retained only for the fallback path). **Verified against the real local LiveKit server:** the minted token was ACCEPTED, the judge participant CONNECTED (identity `judge`), and `say()` synthesized real ElevenLabs audio, captured frames into the published track, and awaited playout. (A standalone-script failure was traced to the missing job http-context, not the module — in-worker the same plugin path already works today.) **No SDK limitation found** — every mechanism the design relies on exists and worked. **Ruling-gap honesty:** unchanged as predicted — the ~1.3 s floor is quick_ruling generation (already overlapped with canned playback); this removes only queue-scheduling overhead (~0–0.2 s). The win is attribution + non-interruptibility by construction. **Tests: agents 119 offline + 9 live (new: judge_voice ×5, wait_for_clear gating ×1; FakeJudge signatures updated); frontend 23 (mapActiveSpeaker ×4); ruff + type-check clean.** **Docs:** ARCHITECTURE §6.5 (attribution-by-construction bullet), LESSONS (no-shared-queue sequencing). **⚠️ Needs a live room:** hearing judge audio via the raw AudioSource path (quality/timing), the active-speaker badge showing 'Judge speaking' from the real signal, no-overlap sequencing under real playout, and the fallback engaging cleanly if the participant is refused.

---

### Enterprise: Case Knowledge Base (pleading RAG) + real auth + no-audio — status: done

Full three-phase build approved. Feasibility verified: **Fireworks embeddings work**
(`nomic-ai/nomic-embed-text-v1.5`, 768-dim) — no new AI vendor; ElevenLabs synthesis is healthy
(the no-audio is transport, not TTS); the `Case` model already has a `storage_path` placeholder.

**Phase 0 — No-audio (transport, not the brain).** ElevenLabs returns audio fine; the objection/
ruling *text* rides data events independent of audio, so a silent-but-visible agent is autoplay or
fallback, not TTS. Fix: call `room.startAudio()` inside the "Start"/"Enable audio" user gesture so
the browser can't block it, and make live-vs-fallback unmistakable in the UI.

**Phase 2 — Real auth (the gate for real work product).** Replace `admin/admin`: bcrypt password
hashing (passlib), `users.password_hash` populated, register + login-against-hash, a seeded admin
for dev, `AUTH_MODE=production` path. Keeps the existing JWT/HTTPBearer verification. Done first
because a real pleading is real work product (CLAUDE.md gate).

**Phase 1 — Case Knowledge Base (the intelligence).** Upload a pleading → ground every agent
decision in it.
- **Storage:** `storage_service.py` (S3/MinIO via boto3) — `cases/{case_id}/{filename}`.
- **Ingest** (FastAPI BackgroundTask, status pending→ready→failed): extract text (pypdf) → chunk
  (≈800-token windows, overlap) → embed each chunk (Fireworks nomic) → persist.
- **Portable vector store (decision):** embeddings stored as JSON on `case_chunks` and cosine ranked
  in Python — **keeps the SQLite test path working** (a pgvector column can't run on SQLite) and
  needs no infra change; one pleading ≈ 100 chunks so brute-force top-k is <1 ms. pgvector is the
  documented scale-up path (many cases/ANN), not needed at this scale.
- **Structured summary:** one LLM pass at ingest → parties, claims, key dates, stipulations,
  disputed facts → `cases.case_summary`. **Hybrid context:** the summary is ALWAYS in the agent
  prompts (the case's spine); retrieval adds the specific passages on demand (the receipts) — better
  than dumping 30 pages (token blowout) or pure RAG (misses the big picture).
- **Retrieval into all four reasoning paths:** OC reply, objection classifier, judge ruling,
  verification — via an agent-authed `GET /api/sessions/{id}/knowledge?q=…` internal route +
  `agents/case_knowledge.py`.
- **Frontend:** attach-a-pleading upload on case create/detail + ingestion status.

**Enterprise extras folded in (worth doing for production-ready):** structured request logging with
the existing request-id; DB indexes on the new FKs; input-size/content-type guards on upload;
ingestion failure surfaced (status) not swallowed; `# SENSITIVE` tags on document/chunk text; docs
(ARCHITECTURE new §12 Case Knowledge + §5/§8/§9 updates).

**Portability/test story:** all new models use portable types (JSON embeddings, `Uuid`, Python
defaults) so CI stays on SQLite; embedding + LLM calls are behind injectable seams so services are
unit-tested without network; live ingest/retrieval covered by `@pytest.mark.live`.

**⚠️ Needs a live room / live keys:** the no-audio confirmation (autoplay), real end-to-end pleading
ingest against MinIO, and retrieval quality in a live sparring session.

**Result:** Built on `feat/case-knowledge-and-enterprise`. **Phase 0 (no-audio):** confirmed
ElevenLabs healthy (audio synthesizes) → the silence is autoplay/transport; hook now unblocks audio
on the FIRST user interaction anywhere on the page (one-time listener) plus the explicit button.
**Phase 2 (real auth):** bcrypt via `security_password.py` (used directly — passlib is broken with
bcrypt 5.0, LESSONS), `POST /api/auth/register` + login-against-hash (email, case-insensitive),
stub gated to AUTH_MODE=stub. **Phase 1 (Case Knowledge Base):** upload → object storage → background
ingest (pypdf extract → overlap chunk → Fireworks embed → `case_chunks`) + structured-summary LLM
pass → `cases.case_summary`; portable JSON embeddings + Python cosine (SQLite-safe, no infra change);
hybrid context = summary always in every prompt (via `SessionState.snapshot()`) + per-turn passage
retrieval into Opposing Counsel's reply (agent-authed `GET /sessions/{id}/knowledge`); frontend
`PleadingUpload` with live ingest status. **Live-proven:** real Fireworks embeddings + real summary
LLM extracted parties/claims/dates correctly and cosine retrieval returned the relevant passage.
**Tests: backend 38, agents 122 offline + live smoke, frontend 23; ruff + type-check + build clean.**
**Docs:** ARCHITECTURE §12 + LESSONS (passlib/bcrypt). **⚠️ Needs live infra:** full upload→MinIO→
ingest round-trip and retrieval quality in a live sparring session; the no-audio confirmation.

---

### Post-audit doc/header/config cleanup + inert cutover-key fix — status: done

Follow-up to the 2026-07-10 consistency audit. All items are documentation/header drift or a
currently-inert config footgun — **no runtime behavior changes on `main` today**. Explicitly NOT
touching judge-participant logic (`judge_participant.py`, `judge_voice.py`, `activeSpeaker.ts`,
`useSparringRoom.ts` — audit confirmed correct), AUTH_MODE, PR #8, infra compose, or Dockerfiles.

**Phase 1 — doc/header fixes (no code behavior change):**
- [x] `agents/main.py` header `Depends on:` — added `backend_client`, `scorecard_builder`,
      `judge_participant` (JudgeParticipant), `judge_voice` (JudgeVoice), and `llm_router`.
- [x] `agents/judge.py` header — now lists `quick_ruling` as a third API-calling entry point.
- [x] `agents/voice_interrupt.py` top-of-file Purpose — now mentions ledger recording, the barge-in
      turn, the data-event publish, and driving `judge_rule` via the `wait_for_clear` gate.
- [x] `.github/workflows/ci.yml` — replaced the stale skeleton comment with an accurate description
      of the offline suite's coverage.
- [x] `.env.example` + ARCHITECTURE §9 — documented `SELF_HOSTED_API_KEY`; also fixed the §10.5
      Step-0 reference (`llm_router._api_key()` → `api_key_for()`).

**Phase 2 — one real fix (inert today, footgun for the MI300X cutover):**
- [x] `agents/llm_router.py` — promoted `_api_key` → public `api_key_for(provider)` with a
      docstring; `build_endpoint` updated to use it.
- [x] `agents/main.py` base-LLM — `api_key=llm_router.api_key_for(config.OPPOSING_COUNSEL_PROVIDER)`
      (was hardcoded `config.FIREWORKS_API_KEY`); added `import llm_router`.
- [x] Re-ran offline agent suite + ruff — **119 offline pass, 9 live deselected, ruff clean.**

**Result:** Done. All five Phase-1 doc/header fixes applied (three agent file headers, the CI
comment, and `SELF_HOSTED_API_KEY` in both `.env.example` and ARCHITECTURE §9, plus the §10.5
runbook reference). Phase 2: `llm_router._api_key` promoted to a public `api_key_for(provider)`
(both `build_endpoint` and the voice pipeline's base LLM in `main.py` now resolve the key the same
way), so the OC base-LLM object is no longer pinned to the Fireworks key — a `self_hosted` cutover is
now a pure config switch for it too (still inert on `main`: `OpposingCounselAgent.llm_node` overrides
generation, so no runtime behavior changed today). **Tests: 119 offline pass (incl. `test_llm_router`,
which covers the rename), 9 live deselected; ruff clean.** No live room used (per instruction — a
judge-participant live test is running in parallel). No LESSONS entry — the changes were mechanical
and nothing non-obvious surfaced. **Untouched as instructed:** judge-participant/judge-voice logic,
`activeSpeaker.ts`, `useSparringRoom.ts`, AUTH_MODE, PR #8, infra compose, Dockerfiles.

---

### Court & Procedural Rules Grounding + Enterprise Hardening — status: Phases 1-5 done, Phases 6-8 not started

**Why:** the grounding audit (2026-07-10) established the agents have ZERO engineered procedural
grounding — no rules corpus, no jurisdiction prompt; all grounding is the uploaded pleading.
This build adds a Court/rules corpus, dual-corpus retrieval, proceeding-type-aware objections,
and citation provenance. **HARD CONSTRAINT: no statutory/procedural rule text is ever generated,
paraphrased, or invented anywhere in this codebase** — ingestion is generic over operator-supplied
official documents; seed scripts fail loudly on missing input, never fall back to synthesized text.

**Resumability rule:** each phase = implement → tests green → commit → Result note HERE, so a
future session knows exactly what is done vs. not started. **Hard stop after Phase 1** (schema
checkpoint — report the exact schema before Phase 2).

**Phase plan (full):**
1. **Data model** — `Court`, `CourtRuleDocument`, `CourtRuleChunk` (portable types: `Uuid`,
   Python defaults, JSON embeddings — LESSONS/SQLite-CI pattern); `cases.court_id` (FK, nullable
   at DB), `sessions.proceeding_type` (oral_argument | direct_examination | cross_examination |
   motion_hearing; existing rows → oral_argument), `users.role` (attorney default | admin; all
   existing rows explicitly attorney). Alembic `0003`. Objection-taxonomy expansion
   (`relevance`, `mischaracterizes_record`, `calls_for_legal_conclusion`) +
   `PROCEEDING_ELIGIBLE_GROUNDS` mapping (constants only — wiring is Phase 4). Update the two
   schema-coupled fixtures (`test_agent_routes.py:104`, `test_case_knowledge.py:55-85`); leave
   every free-text "Rivera" harness/fixture untouched.
2. **Ingestion + admin gating** — `court_knowledge_service.py` (extract→chunk→embed→persist,
   reusing the §12 pipeline pieces), admin-only `POST /api/courts` + `POST /api/courts/{id}/rules`
   (new `require_admin` dependency), attorney-readable `GET /api/courts`, `scripts/seed_court.py`
   reading operator-supplied files from `seed_data/court_rules/` (gitignored; loud failure if
   empty, pointing at official sources only).
3. **Dual-corpus retrieval (agents)** — `court_id` into SessionState via the context route;
   court-passage retrieval (cosine, scoped by court_id); **fix the Judge's missing RAG** (audit
   bug) — pleading retrieval into quick_ruling/generate_ruling/assess_session; court-rules
   retrieval into those three + OC stream_reply + classifier tier-3; prompts carry two SEPARATE
   blocks (`RELEVANT PLEADING EXCERPTS:` / `RELEVANT PROCEDURAL RULES:`).
4. **Proceeding-type-aware classifier** — session creation requires proceeding_type (backend +
   frontend); eligible-grounds filtering at ALL tiers (ineligible grounds never reach the LLM);
   regex for new grounds where confidently detectable; update both persona `.md` "Inputs"
   sections (already stale per audit).
5. **Citation grounding** — citation-shaped token extraction from OC/Judge output; cross-check
   against the chunks actually in that turn's prompt; structured warning log (flag, don't
   rewrite); `RulingProvenance` table persisted per ruling.
6. **Frontend** — Court selector (case create), Proceeding Type selector (session create),
   citation-grounding indicator on scorecard, minimal admin UI (role-gated both ends).
7. **Testing** — standard pytest for all new pieces + a golden-set legal-reasoning eval
   (~15-20 labeled statements, precision/recall, `@pytest.mark.live`), documented in docs/EVALS.md.
8. **Docs** — ARCHITECTURE §13, persona-prompt accuracy check, LESSONS (only if genuinely earned),
   every phase's Result note present.

**Phase 1 checklist:**
- [x] Models: `court.py` (Court), `court_rule.py` (CourtRuleDocument, CourtRuleChunk;
      `section_reference` nullable — extracted only when confidently parseable, else NULL);
      decided AGAINST `# SENSITIVE` on rule text (public official law, not privileged work
      product — tagging would dilute the tag's grep-value; reasoning in the file header).
- [x] Column adds: `cases.court_id` (nullable FK), `sessions.proceeding_type` (String, default
      oral_argument), `users.role` (String, default attorney). String + code constants, not
      sa.Enum — matches house style (session.status), portable across SQLite/Postgres.
- [x] Alembic `0003_court_grounding` (backfills: proceeding_type=oral_argument,
      role=attorney explicitly; no existing user becomes admin).
- [x] Pydantic: CaseCreate gains `court_id` **optional in Phase 1** (validated-if-present;
      DEVIATION from spec's "required" — the UI cannot supply a court until Phases 2+6 exist, and
      requiring it now breaks live case creation, violating "do not regress"; flips to required
      with Phase 6). CaseOut + court_id; SessionOut + proceeding_type; UserOut + role.
- [x] `case_service.create_case` accepts court_id, 422 on unknown/inactive court.
- [x] `objection_classifier.py`: OBJECTION_TYPES + 3 new grounds; `PROCEEDING_ELIGIBLE_GROUNDS`
      with documented procedural reasoning (leading: direct-only; leading/hearsay NOT eligible in
      oral_argument — the audit-flagged mismatch).
- [x] Tests: new backend court-model/API coverage; updated the two named fixtures; agents
      taxonomy/mapping tests. Full offline suites + ruff green.
- [x] Commit; Result note; **STOP — report exact schema before Phase 2.**

**Phase 1 Result:** Done, tested, committed. **New tables** — `courts` (id Uuid PK, name String
NOT NULL, jurisdiction_description Text NULL, is_active Bool NOT NULL def True, created_at,
deleted_at); `court_rule_documents` (id, court_id FK→courts idx, title String NOT NULL,
source_citation String NULL, source_reference String NULL, storage_path String NOT NULL,
ingestion_status String NOT NULL def 'pending', error Text NULL, chunk_count Int NOT NULL def 0,
uploaded_by_user_id FK→users NULL, created_at, deleted_at); `court_rule_chunks` (id,
court_rule_document_id FK idx, court_id FK idx denormalized, chunk_index Int, chunk_text Text,
embedding JSON, section_reference String NULL, created_at). **Column adds** — cases.court_id
(Uuid FK NULL idx); sessions.proceeding_type (String NOT NULL def 'oral_argument'; enum-in-code
PROCEEDING_TYPES = oral_argument|direct_examination|cross_examination|motion_hearing); users.role
(String NOT NULL def 'attorney'; USER_ROLES = attorney|admin). Alembic `0003_court_grounding`
backfills both. **Taxonomy** — OBJECTION_TYPES now 8 grounds (+relevance,
mischaracterizes_record, calls_for_legal_conclusion); PROCEEDING_ELIGIBLE_GROUNDS mapping with
documented reasoning: witness grounds (leading/hearsay/speculation/argumentative) excluded from
oral_argument + motion_hearing; leading eligible ONLY on direct (permitted on cross);
the four argument-appropriate grounds eligible everywhere. Constants only — gate/LLM wiring is
Phase 4. **API deviations flagged:** CaseCreate.court_id optional (validated-if-present, 422 on
unknown/inactive) until the UI can supply it — spec said required, but that would break live case
creation before Phases 2/6 exist. SessionCreate untouched (proceeding_type defaults; required at
creation in Phase 4 per plan). **Tests: backend 46 (was 38; +8 incl. the two updated fixtures),
agents 126 offline (was 122; +4 taxonomy/mapping), ruff clean both.** **No-fabrication check
passed:** diff greped — no statutory/rule text anywhere; the only citation-shaped string is the
spec's own `source_citation` field example. Frontend untouched.

**Phase 2 Result:** Done, tested, committed. **Ingestion** —
`court_knowledge_service.py`: `ingest_rule_document` (extract → chunk → embed → persist
`CourtRuleChunk` rows with conservative `extract_section_reference` — anchored start-of-chunk
Section/Sec./Rule + number, else NULL), `retrieve_rule_passages` (cosine, scoped by court_id,
verbatim text prefixed "[Section N]" when extracted), status/row helpers. **Deliberately NO LLM
summary pass** (unlike the case pipeline): only verbatim operator text is stored/retrieved — a
model-written rules digest would inject paraphrased rule content into prompts, violating the §13
constraint (documented in the file header). Reuse judgment: `document_service.chunk_text` +
`embedding_service.*` are already standalone shared helpers — called directly, no refactor needed
(a further shared-ingest abstraction for two callers would be premature). **Admin gating** — new
`security.require_admin` (composes get_current_user; 401 invalid token, 403 valid non-admin;
distinct from the agent service credential). Routes (`api/courts.py`, registered in main.py):
`POST /api/courts` (admin), `GET /api/courts` (any authenticated user; active+non-deleted only),
`POST /api/courts/{id}/rules` (admin; multipart w/ optional title/source_citation/
source_reference provenance Form fields; PDF-only, size-capped, stores to
`courts/{court_id}/{filename}`, background-ingests — mirrors pleading upload),
`GET /api/courts/{id}/rules` (admin; ingestion status). `court_service.py` holds catalog CRUD.
**Seed** — `scripts/seed_court.py`: reads operator PDFs from `seed_data/court_rules/`
(gitignored), optional manifest.json for per-file provenance, idempotent court creation
(default name = the spec's suggested forum designation, `--name` to override — no case documents
exist in-repo to derive formal naming from), real ingestion, storage-unreachable fallback records
the local path, `--promote-admin EMAIL` as the explicit operator promotion path. **FAILS LOUDLY**
on a missing/empty rules dir, directing the operator to official government sources and
explicitly forbidding AI-generated/unofficial text — verified by running it (exit 1 + message).
**Tests: backend 58 (was 46; +12 — gating 401/403/OK, catalog filtering, upload route w/
monkeypatched storage+background, section-heading extraction incl. not-at-start/no-number
negatives, ingest persists denormalized court_id + section refs, failure path, retrieval scoped
by court w/ section prefix), agents 126 unchanged, ruff clean (incl. scripts/).**
**No-fabrication check passed:** all fixture text is labeled synthetic placeholder prose
("Placeholder body text… not a real rule"); greped new files for statutory-style language — clean.
ARCHITECTURE §5/§13 doc updates deferred to Phase 8 per the plan.

**Phase 3 Result:** Done, tested, committed — dual-corpus retrieval wired agents-side; suite run
after EVERY meaningful change (baseline 126 held throughout; no live LiveKit session started, per
instruction). **Backend:** `SessionContextOut` + `court_id` + `proceeding_type` (proceeding_type
pulled forward from Phase 4 — same struct, avoids a second schema change); new agent-authed
sibling route `GET /api/sessions/{id}/court-rules?q=&k=` → `agent_write_service.get_court_rules`
(session→case→court_id; `{"passages": []}` fail-open when no court/corpus). Route-shape decision
documented on `CourtRulesOut`: sibling over a `scope` param because the case shape carries a
`summary` field with no rules counterpart (no LLM digest of rules exists, by design). **Agents:**
`SessionState` gained plumbing fields `session_id`/`court_id`/`proceeding_type` (defaults "";
snapshot() unchanged — tested, so every offline harness/test stays retrieval-inert);
`case_knowledge.retrieve_passages` gained a `timeout` param; new `agents/court_knowledge.py` —
`retrieve_court_passages` (fail-open, bounded), `rules_block` (the SEPARATE "RELEVANT PROCEDURAL
RULES:" header, distinct from "RELEVANT PLEADING EXCERPTS:"), `dual_blocks` (parallel two-corpus
fetch via ThreadPoolExecutor, `FAST_TIMEOUT=2.0s` for live paths). **Judge missing-RAG fix (the
audit bug):** all three entry points now grounded — `generate_ruling` (dual blocks on the turn),
`quick_ruling` (targeted query = grounds + objected fragment, FAST_TIMEOUT — runs concurrent with
canned-line playback, so a slow fetch degrades to an ungrounded ruling, never a stall),
`assess_session` (targeted query = pending-objection grounds + last attorney turn); builders take
optional `excerpts`/`rules` (pure, offline-testable). **OC:** `build_messages` + `rules` block;
`stream_reply` fetches both corpora via `dual_blocks`. **Classifier tier-3:** court-rules
retrieval (court corpus only; query = candidate grounds + fragment; FAST_TIMEOUT) gated on
`state.session_id` AND only on the ambiguous path — gate rejects/immediate fires never retrieve.
**main.py:** seeds SessionState with session_id/court_id/proceeding_type from the context route
(judge-participant/judge-voice paths untouched). **Seed script:** operator-supplied forum naming
baked in as defaults ("Regional Trial Court — Special Commercial Court, Taguig City" + NCJR/
Sec. 73 RA 11232 / A.M. No. 01-2-04-SC jurisdiction description — named instruments only, no rule
text). **Tests: backend 61 (was 58; +3 — context carries court_id/proceeding_type, court-rules
route auth + passages), agents 139 offline (was 126; +13 — court_knowledge module, snapshot
purity, judge grounding ×4 incl. tight-timeout + targeted-query assertions, OC block separation,
classifier tier-3-only retrieval + offline-skip + debounce-with-grounding), ruff clean, main.py
compiles.** **No-fabrication check passed** (diff greped; fixture "rules" are labeled
placeholders). ⚠️ Live-room confirmation of the grounded paths remains the user's deliberate
standalone step.

**Phase 4 Result:** Done, tested, committed — suite run after every meaningful change; no live
LiveKit session; no browser preview either (a Dashboard→SparringRoom preview would head into the
LiveKit connect path — verification bar for this phase was the offline suites per instruction).
**Classifier gating (agents):** `eligible_grounds_for(proceeding_type)` (unknown/empty → ALL
grounds, fail-open to pre-§13 behavior); `classify_fragment` filters tier-1 candidates AND tier-2
high-confidence matches through it BEFORE any LLM call — an ineligible-only candidate dies at the
gate with reason "grounds ineligible for <type>" (the audit-flagged trailing-"?"-fires-leading-in-
oral-argument mismatch is now structurally impossible, tested); the tier-3 system prompt's
valid-type list is NARROWED to eligible grounds and the user content states `PROCEEDING TYPE:`;
belt-and-braces post-parse guard suppresses a fire whose type is ineligible/unknown (one
pre-existing fixture used invented type "spec" and was corrected to "speculation" — the guard now
rightly refuses unknown types). New recall patterns for `calls_for_legal_conclusion` ("as a matter
of law", "the court should/must find…", "constitutes/amounts to"); `relevance` +
`mischaracterizes_record` stay LLM-only (comparative, no surface form — documented in-file); NO
new ground joins tier-2 (argument-shaped objections are judgment calls → every oral_argument/
motion_hearing fire is LLM-judged, documented). **Persona prompts:** opposing_counsel.md +
judge.md "Inputs available" sections rewritten to the REAL runtime inputs (case summary, raw
facts, both ledgers, RELEVANT PLEADING EXCERPTS, RELEVANT PROCEDURAL RULES w/ cite-by-section +
never-invent language, proceeding_type, transcript); OC's objection behavior line now
proceeding-aware. **Backend:** `SessionCreate.proceeding_type` REQUIRED, field_validator against
`PROCEEDING_TYPES` (single source, no Literal duplicate) → 422 missing/invalid;
`session_service.create_session` takes it (None → model default for internal callers); 5 test
call sites updated; the Phase-1 "defaults to oral_argument" API test rewritten to the new
contract (422/422/201×4-echo). **Frontend:** `ProceedingType` union + `PROCEEDING_TYPE_LABELS`
(types.ts); `api.createSession(caseId, proceedingType)` + `Session.proceedingType` mapping;
Dashboard gained a per-case labeled Proceeding `<select>` (Tailwind-styled native element;
default oral_argument) feeding the mutation. New `Dashboard.test.tsx` (default + selected value
both assert the createSession payload). **Tests: agents 145 (was 139; +6 gating incl.
LLM-never-called-for-ineligible and narrowed-prompt assertions), backend 61 (net stable; required-
field contract test), frontend 25 Vitest (was 23; +2 Dashboard) + type-check + lint clean — the
existing session-creation flow's coverage passes with the required field.** **No-fabrication
check passed.** ⚠️ Live-room confirmation still the user's deliberate standalone step.

**Phase 5 Result:** Done, tested, committed — citation grounding + provenance audit trail; suite
run after every meaningful change; no live LiveKit session (live pass deferred to after Phase 6
per instruction, so it exercises this work too). **Citation check** — new `agents/citation_check.py`
(pure): `extract_citations` (Section/Sec./Rule/R.A. No./Republic Act No./A.M. No./§ patterns),
`canonical` (variant equivalence: "Section 12"=="SEC. 12"=="§12", "RA 11232"=="R.A. No. 11232"
=="Republic Act No. 11232"), `flag_ungrounded(output, shown_text)`. **TURN-SCOPED by construction:**
the comparison target is `Retrieval.shown_text` — exactly the two blocks assembled for THAT
specific call (each ruling checks against its own retrieval, never the corpus); a real-but-
unretrieved citation still flags (dedicated test). Flags are logged + persisted, never rewritten
out of spoken output. **Chunk-id plumbing** — backend `retrieve_refs`/`retrieve_rule_refs`
((chunk_id, text) pairs; old text-only fns delegate), `chunk_ids` parallel array on KnowledgeOut/
CourtRulesOut; agents `retrieve_passage_refs`/`retrieve_court_refs`; `dual_retrieval` returns a
`Retrieval` dataclass (blocks + shown_text + chunk_ids prefixed "case:"/"court:" so audit rows are
self-describing); `dual_blocks` kept as a thin wrapper. **Judge** — `quick_ruling` now returns a
`QuickRuling` dataclass (ruling, reason, chunk_ids, flagged_citations; reason checked against its
own turn's shown text); `assess_session` dict gains `chunk_ids` + `flagged_citations` (closing
ruling checked; failure path returns empty lists); `generate_ruling` flag-logs (harness path — no
provenance row, it's not wired into the worker). **OC** — `stream_reply` accumulates the streamed
reply and flag-LOGS after completion (log-only per spec; the provenance TABLE is for rulings);
reply text never altered (tested). **Persistence** — `RulingProvenance` model
(`ruling_provenance`: id, session_id FK idx, ruling_type objection_ruling|final_ruling,
chunk_ids_used JSON, citation_flags JSON, created_at; citation LABELS only, no work product) +
Alembic `0004_ruling_provenance`; agent-authed `POST /api/sessions/{id}/provenance` (422 unknown
ruling_type, 404 unknown session, 401 matrix) via `agent_write_service.write_provenance`;
`backend_client.write_provenance`; main.py persists per inline ruling (fire-and-forget task —
provenance never delays the spoken ruling) and for the final ruling in `_finalize_session`
(best-effort). **Known benign-flag sources (deliberate, per spec):** the check compares against
retrieved CHUNKS only — not the (model-written) case summary, not attorney-typed case_facts, not
attorney speech — so a citation echoed from those shown-but-not-verbatim-source inputs still
flags; the flag-don't-rewrite design exists precisely to measure that rate before considering
auto-correction. Old test fixtures updated: exact-body assertions gained `chunk_ids`; quick_ruling
tuple-unpack test → dataclass; three Phase-3 judge tests moved to `dual_retrieval` with new
flag/provenance assertions. **Tests: agents 154 (was 145; +7 citation_check, +2 OC flag-log, and
strengthened judge/dual tests), backend 63 (was 61; +2 provenance/chunk-id routes), ruff clean,
main.py compiles. No-fabrication check passed** (fixtures are labeled placeholders; citation
labels only). ⚠️ Live confirmation (judge-participant + no-audio + citation/provenance) deferred
to after Phase 6 per instruction.
