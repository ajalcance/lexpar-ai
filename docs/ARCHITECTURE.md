# LexPar AI — Technical Architecture

**Status:** Living document. Update this whenever an architectural decision changes — it is the
single source of truth for the project across chat sessions, contributors, and Claude Code runs.
Pair it with `CLAUDE.md` at the repo root, which should simply point here for full context.

---

## 1. Overview

LexPar AI is a voice-immersive courtroom rehearsal platform for solo and independent trial
lawyers. An attorney speaks their argument aloud against an AI Opposing Counsel that can
interrupt mid-sentence with objections, followed by an AI Judge that delivers a spoken ruling
and a written scorecard.

Built for the AMD Developer Hackathon (Unicorn track), architected to survive past it as a real
product.

---

## 2. Repository structure

Single monorepo. One repo, one source of truth, no cross-repo version drift for a solo build.

```
lexpar-ai/
├── frontend/                    React + TypeScript (Vite)
│   ├── src/
│   │   ├── components/          Shared UI (shadcn/ui + Tailwind)
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── CaseUpload.tsx
│   │   │   ├── SparringRoom.tsx     LiveKit room UI (live session)
│   │   │   └── Scorecard.tsx
│   │   ├── hooks/
│   │   ├── store/                auth.ts, session.ts (Zustand)
│   │   ├── lib/                  api.ts (REST client), livekit.ts (room client wrapper)
│   │   └── App.tsx                routes + auth guard
│   ├── vite.config.ts
│   └── package.json
│
├── backend/                     FastAPI (non-realtime REST API)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── auth.py           login stub, token issuance
│   │   │   ├── cases.py          case upload / list / detail
│   │   │   ├── sessions.py       session lifecycle, transcript retrieval
│   │   │   ├── scorecards.py
│   │   │   └── livekit_token.py  issues LiveKit room access tokens
│   │   ├── models/               SQLAlchemy models
│   │   ├── db.py
│   │   └── config.py             reads .env
│   ├── requirements.txt
│   └── Dockerfile
│
├── agents/                      LiveKit Agents worker (real-time voice pipeline)
│   ├── main.py                   entrypoint, room join logic
│   ├── opposing_counsel.py       agent persona + prompt
│   ├── judge.py                  agent persona + prompt
│   ├── objection_classifier.py   watches live partial transcript, fires interrupts
│   ├── llm_router.py             switches Fireworks <-> self-hosted vLLM per agent
│   ├── requirements.txt
│   └── Dockerfile
│
├── infra/
│   ├── docker-compose.yml        local dev: postgres, minio (local S3), livekit server
│   ├── docker-compose.prod.yml   AMD Developer Cloud deployment
│   └── deploy.sh
│
├── docs/
│   └── ARCHITECTURE.md           this file
│
├── .github/workflows/ci.yml      lint, test, build images on every push
├── CLAUDE.md                     points Claude Code here + operational notes
└── .env.example
```

---

## 3. System diagram

```mermaid
flowchart TB
    subgraph Client
        A[React + TypeScript app]
    end

    subgraph Realtime[Real-time voice layer]
        B[LiveKit server]
        C[LiveKit Agents worker]
        C1[Opposing Counsel agent]
        C2[Judge agent]
        C3[Objection classifier]
    end

    subgraph LLM[LLM inference - swappable]
        D1[Fireworks AI - Gemma]
        D2[Self-hosted vLLM - AMD MI300X]
    end

    subgraph Speech
        E1[Deepgram STT]
        E2[ElevenLabs TTS]
    end

    F[FastAPI backend]

    subgraph Data[Data layer]
        G1[(Postgres)]
        G2[(Object storage)]
    end

    A -- WebRTC audio --> B
    B --> C
    C --> C1
    C --> C2
    C --> C3
    C1 --> D1
    C1 -. config switch .-> D2
    C2 --> D1
    C --> E1
    C --> E2
    A -- REST / JSON --> F
    F --> G1
    F --> G2
    F -- issues LiveKit token --> A
```

Key point encoded in the diagram: **the Opposing Counsel agent's LLM backend is a config switch,
not two code paths.** Both Fireworks and self-hosted vLLM expose OpenAI-compatible endpoints, so
`llm_router.py` just reads an environment variable.

---

## 4. Frontend

**Stack:** React 18 + TypeScript, Vite, Tailwind CSS + shadcn/ui, Zustand (client state),
TanStack Query (server state), `@livekit/components-react` + `livekit-client` (real-time audio).

**Routes:**

| Route | Purpose | Auth required |
|---|---|---|
| `/login` | Login form | no |
| `/dashboard` | List of cases | yes |
| `/case/new` | Upload case facts / documents | yes |
| `/session/:id` | Live sparring room (LiveKit connection) | yes |
| `/session/:id/scorecard` | Post-session results | yes |

### Login form (placeholder auth)

Included now as real UI, wired to a stub backend — not a mock, an actual login form hitting an
actual endpoint, just with hardcoded credentials behind it for now.

- Form posts `{ username, password }` to `POST /api/auth/login`.
- Backend (see §5) accepts only `admin` / `admin` while `AUTH_MODE=stub`, returns a signed JWT.
- Frontend stores the token in memory (Zustand `auth` store) and attaches it as a Bearer token on
  subsequent requests. Not localStorage — keeps it out of persistent browser storage even in
  placeholder form, so the swap to real auth later doesn't also require a storage migration.

**⚠️ Flagged for replacement:** this must not ship to any real attorney or real case data while
`AUTH_MODE=stub`. Tracked in §11 (Open items).

### Wiring status (frontend ↔ backend)

The frontend now calls the **real** backend through `lib/api.ts` for auth (login + `/api/auth/me`,
which `ProtectedRoute` uses to validate the session), cases (list/create), session creation,
scorecard retrieval, and — once a session is completed — its persisted transcript. Live voice is
the one thing still absent:

- **Live transcript playback** in `SparringRoom` is still a scripted, timer-driven sequence during
  a session (there is no live STT→LLM→TTS producing turns in real time yet). Starting a session
  still exercises real plumbing: it creates a real `sessions` row (POST /api/sessions) and fetches a
  real LiveKit token (GET /api/livekit/token).
- **Completed sessions render real data.** When the agent worker (or `session_end_harness.py`) posts
  `complete` + `scorecard`, the session goes `completed` and the persisted scorecard + transcript are
  written. `Scorecard.tsx` then renders the **real** heuristic score, strengths, weaknesses, and
  verbatim judge ruling (GET `/api/sessions/{id}/scorecard`), plus a **Transcript** section built
  from the real persisted turns (GET `/api/sessions/{id}`, reusing `TranscriptLine` with the
  objection styling). Multi-line strengths/weaknesses use `whitespace-pre-line` so the per-fact and
  per-objection bullet lines survive. Verified end-to-end offline via the harness (Gap 5).
- **Before a scorecard exists** (session still `in_progress`), GET scorecard returns 409/404 and the
  frontend shows an honest "not available yet" fallback rather than fabricating a score.
- **No dedicated ledger/verification UI.** SessionState's ledger (established facts, objections) and
  the verification pass already flow into the scorecard's score/strengths/weaknesses; they are not
  surfaced as a separate section (deliberately — see Gap 5 in tasks/PLAN.md).

---

## 5. Backend (FastAPI)

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/auth/login` | Validates credentials (stub: `admin`/`admin`), issues JWT | no |
| GET | `/api/auth/me` | Returns current user from token | yes |
| POST | `/api/cases` | Upload case facts + documents | yes |
| GET | `/api/cases` | List attorney's cases | yes |
| GET | `/api/cases/{id}` | Case detail | yes |
| POST | `/api/sessions` | Start a new sparring session for a case | yes |
| GET | `/api/sessions/{id}` | Session status + transcript | yes |
| GET | `/api/sessions/{id}/scorecard` | Scorecard after session ends | yes |
| GET | `/api/livekit/token` | Issues a LiveKit room access token for the frontend | yes |
| POST | `/api/sessions/{id}/complete` | (internal) Mark session completed | agent token |
| POST | `/api/sessions/{id}/scorecard` | (internal) Write scorecard + full transcript batch at session end | agent token |

FastAPI does not touch real-time audio at all — that's entirely the LiveKit Agents worker's job.
FastAPI's role is auth, case management, and persisting the results the agents worker produces.

**Internal (agent) routes vs. user routes.** The two `agent token` routes above are written by the
agents worker at session end, authenticated with a **scoped service credential** (`X-Agent-Token`
header, `AGENT_SERVICE_TOKEN`) — a *separate mechanism* from user JWT login (`app/security_agent.py`,
not `app/security.py`). Least privilege (DEV_GUIDELINES §7): the agent token grants only these two
routes and nothing user-facing; a user JWT does not grant them. The scorecard write **batches the
whole transcript in one call** (no per-turn round-trips inside the live voice loop).

---

## 6. Real-time voice layer (LiveKit)

- **LiveKit server**: self-hosted (open-source, Apache-2.0), runs in Docker locally and on the
  AMD droplet in production. Can migrate to LiveKit Cloud later without touching agent code.
- **LiveKit Agents worker** (`agents/main.py`, implemented): Deepgram streaming STT → Opposing
  Counsel (Fireworks, via `opposing_counsel.py`) → verification pass → ElevenLabs **Flash** TTS,
  with Silero VAD + turn detection. Interim transcripts feed the objection classifier; a `fire`
  decision **barges in** (`session.interrupt()` + an immediate short "Objection — <type>." via the
  tested `voice_interrupt.py` glue). `opposing_counsel.py` / `judge.py` / `verification.py` are used
  verbatim — main.py only wires the audio layer around them. Heavy voice deps live in
  `agents/requirements-voice.txt` (out of CI). **The real audio path — room join, mic→STT, TTS
  playback, VAD, barge-in timing — is only verifiable in a live room with a microphone.**
  - `opposing_counsel.py` — cross-examines, objects, counter-argues.
  - `judge.py` — monitors the session, delivers rulings.
  - `objection_classifier.py` — **the custom, differentiating piece** (implemented). Watches the
    live partial transcript and decides, in real time, when Opposing Counsel should interrupt and
    with what objection type, following opposing_counsel.md's "only when genuinely invited — not
    every turn" rule. Two stages so it can run continuously: a cheap, **recall-biased regex gate**
    (`candidate_grounds`, runs on every fragment; no candidates → no LLM call) followed by a fast
    model (`classify_fragment`, gpt-oss-120b JSON) that makes the final fire/type decision.
    `ObjectionClassifier` adds **per-utterance debounce** (no re-firing on a growing fragment) and
    the LLM stage **fails closed** (any error → no interruption). Bespoke logic on top of the
    framework, not something LiveKit provides out of the box.
  - `llm_router.py` — reads `OPPOSING_COUNSEL_LLM_PROVIDER` / `JUDGE_LLM_PROVIDER` env vars and
    points each agent at the correct OpenAI-compatible endpoint.

---

## 6.5 Memory & verification

Two things keep the spoken replies trustworthy under real-time pressure: a structured memory of the
session, and a verification pass before anything is spoken.

### Session memory (`SessionState`)

Each active session holds a structured, in-memory `SessionState` (`agents/session_state.py`) — not
just a chat transcript:

- **case_facts** — the immutable facts supplied when the session starts.
- **established_facts** — a ledger of facts established during the session (entered into evidence,
  stipulated, or stated without objection).
- **objections** — a ledger of objections: the grounds, who raised it, and the judge's ruling
  (`pending` → `sustained` | `overruled`).

This lets Opposing Counsel and the Judge reason about *what's actually on the record* instead of
re-deriving it from raw transcript each turn, and it is the ground truth the verification pass
checks against. It lives in memory for the session's lifetime; durable copies persist through the
backend models (`transcripts`, `scorecards`) — the raw ledger is never logged.

### Verification pass (before TTS)

After the reasoning model drafts a reply, a verification pass runs **before** the reply reaches
TTS. It checks:

1. **Consistency** against `SessionState` — the reply must not contradict `case_facts`,
   `established_facts`, or standing objection rulings (e.g. don't rely on testimony that was just
   stricken on a sustained objection).
2. **Fabricated legal citations** — a heuristic checker (`agents/verification.py`) flags
   citation-shaped text with unrecognized reporters or implausible years; an LLM/DB-backed check
   comes later.

On **fail**, the draft is discarded and the reasoning model regenerates (bounded retries). On
**pass**, the reply goes to TTS.

```mermaid
flowchart TB
    S[SessionState — case facts + ledger] --> R[Reasoning model — drafts the next reply]
    R --> V[Verification pass — consistency + citations]
    V -- fail: regenerate --> R
    V -- pass --> T[Spoken response → TTS]
```

### Co-location

Once the reasoning model is self-hosted on the AMD MI300X (§7), the verification model runs **on the
same GPU** as the reasoning model — the check is a local forward pass, not a network hop, so it fits
inside the turn's latency budget. While both run on Fireworks, verification is simply a second API
call.

### Implemented now vs. pending keys

- **Implemented + tested (no keys):** `SessionState` and its update methods; the regex citation
  heuristic (`find_suspicious_citations`).
- **Implemented, live via Fireworks:** the LLM consistency check (`check_consistency`, small
  verification model), Opposing Counsel + Judge response generation, the objection classifier
  (`objection_classifier.py`, §6), and `llm_router` (§7). Live calls are covered by
  `@pytest.mark.live` tests, excluded from CI. Text-only harnesses (`agents/harness.py`,
  `agents/objection_harness.py`) exercise the draft→verify path and the streaming interrupt logic
  without any voice infrastructure.
- **Implemented, needs a live room to verify:** the real-time voice worker (`agents/main.py`) —
  Deepgram STT + ElevenLabs Flash TTS + objection barge-in. The livekit-free glue (`voice_interrupt.py`)
  is unit-tested; the actual audio path (mic→STT, TTS playback, VAD, barge-in timing) can only be
  validated in a live LiveKit room with a microphone. Verification model GPU co-location arrives with
  self-hosting (§7).

---

## 7. LLM inference routing

| Agent | Model in use now | Post-droplet option | Why |
|---|---|---|---|
| Opposing Counsel | Fireworks `deepseek-v4-pro` | Self-hosted vLLM on AMD MI300X | Proves AMD platform ownership for the hackathon; switch to self-hosted once session volume justifies dedicated GPU uptime |
| Judge | Fireworks `gpt-oss-120b`, JSON-structured (**interim**) | Stays on Fireworks | **Should be Gemma** for bonus-prize eligibility, but no serverless Gemma (2/3/4) is reachable on this account/endpoint — verified against the live `/v1/models` list and direct ID probes (all 404), including the Gemma 3 12B/4B IDs from Fireworks' changelog. Interim: `gpt-oss-120b` via structured `{"ruling": …}` output (fast, reliable). `deepseek-v4-pro` was rejected for the Judge — as a reasoning model it is slow (30–60s) and intermittently returns empty content. Do not self-host this one. |
| Verification | Fireworks `gpt-oss-120b` | Same GPU as reasoning (self-hosted) | Small/fast verifier per §6.5 — deliberately not the reasoning model; needs clean JSON output. |
| Objection classifier | Fireworks `gpt-oss-120b`, JSON (`OBJECTION_LLM_MODEL`) | Fast model, co-located | Most latency-sensitive call (streaming speech), so it only runs on gate candidates and debounces per utterance (§6). gpt-oss picked as the account's fast JSON follower; swap via env if a faster model appears. |

Switching is a config change (`.env` value), never a code change — this is deliberate. **Bonus-eligibility
note:** the Judge must move to a Gemma model before relying on Gemma-track eligibility; tracked as an
open item until a serverless Gemma is available on the account.

**Model-latency note:** Opposing Counsel stays on `deepseek-v4-pro` — benchmarked over repeated live
runs at a median ~4s (3.5–7.8s), every run `finish=stop` with non-empty content. Its direct
"generate a rebuttal" task does not trigger the long deliberation that made deepseek slow (30–60s)
and intermittently empty for the Judge's "rule only if warranted" task — which is why the Judge
runs on `gpt-oss-120b` (JSON-structured) instead. Verification uses `gpt-oss-120b` for clean JSON.

---

## 8. Database schema (Postgres)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    password_hash TEXT,             -- NULL while AUTH_MODE=stub
    firm_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    title TEXT NOT NULL,
    case_facts TEXT,
    storage_path TEXT,               -- object storage key for uploaded file
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id),
    user_id UUID REFERENCES users(id),
    status TEXT DEFAULT 'in_progress',   -- in_progress | completed | abandoned
    llm_backend_used TEXT,               -- 'fireworks' | 'self_hosted'
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ
);

CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    speaker TEXT NOT NULL,               -- 'attorney' | 'opposing_counsel' | 'judge'
    content TEXT NOT NULL,
    was_interruption BOOLEAN DEFAULT false,
    spoken_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE scorecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id) UNIQUE,
    overall_score NUMERIC,
    strengths TEXT,
    weaknesses TEXT,
    judge_ruling TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

## Object storage layout

```
cases/{case_id}/{original_filename}
```

S3-compatible (MinIO locally, DigitalOcean Spaces in production).

### Backend implementation notes (as built)

- **Migrations:** the schema is created and versioned with **Alembic** (`backend/alembic/`), not
  `create_all` on startup. Run `alembic upgrade head` before serving. Tests build the schema from
  `Base.metadata` on SQLite, so CI needs no database service.
- **Portable column types:** models use SQLAlchemy's `Uuid` type and application-side defaults
  (`uuid4`, timezone-aware `datetime.now`) rather than Postgres server defaults
  (`gen_random_uuid()`, `TIMESTAMPTZ`). The same models therefore run unchanged on Postgres
  (prod) and SQLite (tests).
- **Soft deletes:** `users`, `cases`, and `sessions` carry a nullable `deleted_at`; queries
  exclude it (DEVELOPER_GUIDELINES §8), so a retention policy later is a query change, not a
  schema migration.
- **Sensitive fields** (`cases.case_facts`, `transcripts.content`, scorecard text) are tagged
  `# SENSITIVE: attorney work product` in the models and never logged.
- **Who writes what:** the browser client never writes `transcripts` or `scorecards`. The agents
  worker persists them **once at session end** via the internal routes (§5): `POST .../complete` then
  `POST .../scorecard`, which batch-inserts the whole transcript alongside the scorecard. The user
  routes only read them back.

---

## 9. Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `OBJECT_STORAGE_ENDPOINT` / `OBJECT_STORAGE_BUCKET` | S3-compatible file storage |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit server connection |
| `OPPOSING_COUNSEL_LLM_PROVIDER` | `fireworks` \| `self_hosted` |
| `OPPOSING_COUNSEL_LLM_ENDPOINT` | OpenAI-compatible URL for whichever provider is active |
| `OPPOSING_COUNSEL_LLM_MODEL` | Reasoning model id (default: `deepseek-v4-pro`) |
| `JUDGE_LLM_PROVIDER` | keep as `fireworks` (Gemma bonus eligibility once Gemma is deployed) |
| `JUDGE_LLM_ENDPOINT` | Fireworks endpoint |
| `JUDGE_LLM_MODEL` | Judge model id (default: `deepseek-v4-pro`; use Gemma once available) |
| `VERIFICATION_LLM_PROVIDER` / `VERIFICATION_LLM_ENDPOINT` / `VERIFICATION_LLM_MODEL` | Verifier, NOT the reasoning model (§6.5; default `gpt-oss-120b` — swap for a smaller model when deployed) |
| `OBJECTION_LLM_PROVIDER` / `OBJECTION_LLM_ENDPOINT` / `OBJECTION_LLM_MODEL` | Objection classifier — the latency-sensitive streaming call (§6; default `gpt-oss-120b`) |
| `FIREWORKS_API_KEY` / `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` | Provider auth |
| `DEEPGRAM_MODEL` / `ELEVENLABS_MODEL` / `ELEVENLABS_VOICE_ID` | Voice pipeline (agents/main.py); defaults `nova-3` / `eleven_flash_v2_5` / a stock voice |
| `JWT_SECRET` | Token signing — **required, ≥ 32 chars**; the app refuses to start with a blank/missing/weak key (`openssl rand -hex 32`) |
| `AUTH_MODE` | `stub` \| `production` |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API (e.g. the Vite dev server) |
| `AGENT_SERVICE_TOKEN` | Scoped service credential for the agent's internal session-write routes (§5) — NOT user auth. Empty = internal routes locked |
| `AGENT_BACKEND_URL` | (agents worker) Base URL of the backend the worker persists to (default `http://localhost:8000`) |

Never commit `.env` — `.env.example` documents the shape, real values stay local/secrets-managed.

**Frontend env:** the React app reads `VITE_API_BASE_URL` (default `http://localhost:8000`) to reach
the backend — see `frontend/.env.example`. Vite only exposes vars prefixed `VITE_` to the browser.

---

## 10. Deployment

- **Local dev:** `infra/docker-compose.yml` brings up the infra — Postgres, MinIO, and the LiveKit
  server (dev mode, default keys `devkey`/`secret`). The backend, agents, and frontend dev server run
  on the host and point at these via `.env` / `VITE_API_BASE_URL`. Both LLM agents point at Fireworks
  until the AMD droplet exists. Bring it up with
  `docker compose -f infra/docker-compose.yml up -d`; LiveKit answers on `http://localhost:7880`
  (returns `OK`).
- **Agents voice worker:** the heavy voice deps are separate (`agents/requirements-voice.txt`, out
  of CI). Run it against a live LiveKit server with:
  `pip install -r agents/requirements.txt -r agents/requirements-voice.txt` then
  `python agents/main.py dev`.
- **Production (AMD Developer Cloud):** `docker-compose.prod.yml` on the droplet. CI builds and
  tags images on every push; deploy is `docker compose pull && docker compose up -d`.
- **CI (`.github/workflows/ci.yml`):** lint + type-check + test + build images on every push, so
  the droplet only ever pulls images that have already passed CI — never building for the first
  time under deployment pressure.

---

## 11. Open items / roadmap

- [ ] Replace `AUTH_MODE=stub` (admin/admin) with real auth before any real attorney or real case
      data touches the system. (Note: the agents worker's `AGENT_SERVICE_TOKEN` is already a separate,
      scoped credential — not part of the stubbed user auth — so it survives that replacement.)
- [ ] Cut the Opposing Counsel agent over to self-hosted vLLM once the AMD droplet exists and
      hackathon submission is locked in.
- [ ] Move the Judge to a Gemma model (`JUDGE_LLM_MODEL`) for bonus-track eligibility — currently
      running `gpt-oss-120b` (JSON-structured) as an interim because no serverless Gemma is
      reachable on this Fireworks account (§7).
- [ ] Re-evaluate self-hosted vs. Fireworks-only for production once real session volume exists
      (see cost model discussion — fixed GPU cost only pays off at volume).
- [ ] Billing integration (Stripe) — not needed until first paying customer.
- [ ] Data retention / encryption policy written down explicitly before onboarding real attorneys.
