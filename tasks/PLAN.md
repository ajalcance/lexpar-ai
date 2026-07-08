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
