# Lessons & Gotchas

**Status:** Append-only log of mistakes Claude Code has made on this project, and the fix — so
they don't repeat. Referenced by `CLAUDE.md`. Keep entries short and specific.

## How to use this file

When Claude Code gets something wrong and you correct it, end the correction with:
"Add this to docs/LESSONS.md so you don't make that mistake again." Claude writes the entry.

## Format

```
### [Area] Short description of the mistake
**Wrong:** what Claude did
**Right:** what it should do instead
```

## Entries

### [Frontend/tooling] Vite 8 breaks the Vitest toolchain
**Wrong:** Kept `create-vite`'s defaults (Vite 8 + `@vitejs/plugin-react` 6). Vitest 3.2 pulled
its own Vite 7, producing two Vite copies — `vitest/config` typed `test` against Vite 7 while the
app's `defineConfig` was Vite 8, so plugin types clashed and the config wouldn't type-check.
**Right:** Pin `vite` to `^7` and `@vitejs/plugin-react` to `^5` until Vitest supports Vite 8.
Keep a single Vite version across the app and the test runner (`npm ls vite` should show one).

### [Frontend/shadcn] The default shadcn style is Base UI, not Radix
**Wrong:** Composed buttons with Radix's `asChild` prop (`<Button asChild><Link/></Button>`).
**Right:** The current shadcn style ("base-nova") renders on `@base-ui/react`. Compose with the
`render` prop instead — `<Button render={<Link to="…" />}>label</Button>` — and add
`nativeButton={false}` when the rendered element is not a real `<button>` (e.g. a link).

### [Backend/SQLAlchemy] Keep models portable so tests run on SQLite
**Wrong:** Reaching for Postgres-only server defaults (`gen_random_uuid()`, `TIMESTAMPTZ`) would
force pytest to run against a real Postgres and add a DB service to CI.
**Right:** Use SQLAlchemy's `Uuid` type + application-side defaults (`uuid4`,
`datetime.now(timezone.utc)`). The same models then run on Postgres (prod/Alembic) and SQLite
(tests) unchanged, so CI's backend job needs no database.

### [Backend/naming] `Session` model vs SQLAlchemy `Session`
**Wrong:** Importing both the ORM `Session` model and SQLAlchemy's `Session` in one module collides.
**Right:** Alias the DB session type — `from sqlalchemy.orm import Session as DbSession` — and keep
`Session` for the domain model. `DbSession` also reads clearly as "database session."

### [Backend/security] Never give a secret an insecure default — fail loud instead
**Wrong:** `jwt_secret: str = "dev-insecure-change-me"`. A missing `JWT_SECRET` silently fell back to
a guessable, source-committed key (tokens forgeable by anyone who read the repo); a blank one didn't
fail at startup — it crashed later at the first login (`HMAC key must not be empty`).
**Right:** No default for signing keys. Validate at startup (a pydantic `field_validator` requiring
≥ 32 chars) so the app **refuses to boot** with a blank/missing/weak secret, with an actionable
message (`openssl rand -hex 32`). Supply it via env/`.env`; give tests a real (long) value in
conftest. Prefer fail-closed defaults for other credentials too (e.g. an empty `AGENT_SERVICE_TOKEN`
rejects all internal calls rather than allowing them).

### [Backend/config] Anchor the `.env` path to the file, not the working directory
**Wrong:** `SettingsConfigDict(env_file=".env")`. That path is resolved against the current working
directory. Running `uvicorn app.main:app` from inside `backend/` made pydantic look for
`backend/.env` (which doesn't exist), so `JWT_SECRET` came up blank and the app died at startup with
"JWT_SECRET must be set" — even though a real value was in the project-root `.env`. It only worked
when launched from the repo root, a CWD-dependent trap.
**Right:** Resolve the env file absolutely from the module's own location:
`ENV_FILE = Path(__file__).resolve().parents[2] / ".env"` (from `backend/app/config.py`), then
`env_file=ENV_FILE`. Now `.env` loads the same whether uvicorn starts from the repo root or from
inside `backend/`. General rule: config/asset paths should be anchored to `__file__`, never to the
CWD.

### [Agents/LLM] gpt-oss returns EMPTY content when `max_tokens` is too low
**Wrong:** Treated `gpt-oss-120b` like a normal model and set a tight `max_tokens` (e.g. 120, or the
32–128 range that "should" fit a one-line JSON decision) to cut latency. It reasons *before* emitting;
the hidden reasoning consumes the whole budget, the response hits `finish_reason=length`, and
`content` comes back **empty** — which then fails closed (silent no-fire) or crashes a JSON parse.
Benchmarked: at mt=128/64/48/32 the objection classifier got 0/7 non-empty; only mt≥512 is reliable,
and it buys only ~0.3 s anyway.
**Right:** Give reasoning models room — keep `max_tokens` ≥ 512 for gpt-oss even for a tiny JSON
answer, and always assert non-empty + parseable in the benchmark. If you need lower latency, the
budget is the wrong lever — change the model or skip the call (see next entry).

### [Agents/LLM] Don't assume a "fast small model" exists — benchmark the actual account catalog
**Wrong:** Planned to cut objection barge-in latency by swapping `OBJECTION_LLM_MODEL` to "a fast
non-reasoning model," assuming one was available. This account's Fireworks catalog is tiny (7 models,
one image-gen) — the same limitation that blocked Gemma (§7). deepseek/glm/kimi are all slower or
unreliable (CoT leakage, 500s); `gpt-oss-120b` (~1.3 s) is already the *fastest reliable* option.
**Right:** Benchmark every model on the *actual* task shape before assuming a faster one exists. When
the model lever is exhausted, get the latency architecturally instead: the objection classifier added
a **tier-2 high-confidence regex gate** that fires clear leading/hearsay objections with **no model
call at all** (~1–2 s → ~0 s), keeping the model only for genuinely ambiguous phrasing. Precision-bias
that immediate tier (opposite of the recall gate) and give it its own audit outcome (`fire_immediate`)
so an over-eager gate is visible in the data.

### [Agents/concurrency] Shared mutable state reached via `asyncio.to_thread` is a data race
**Wrong:** `ObjectionClassifier.consider()` mutated debounce state (`_prev` / `_handled` / `records`)
and was called from the voice worker via `asyncio.to_thread` on *every* interim transcript. Interims
arrive faster than the (~1 s) classifier call returns, so multiple fragments ran `consider()` in
parallel thread-pool threads — a genuine race that could double-fire or drop a debounce. Passing
offline tests hid it (they call `consider()` sequentially).
**Right:** Anything handed to `to_thread` (or otherwise run off the loop) that touches shared mutable
state needs a lock. Guard `consider()` with a `threading.Lock`; holding it across the blocking model
call is intended here — the barge-in decision is inherently sequential, so later interims queue and
the debounce short-circuits them. When logic runs single-threaded in tests but concurrently in the
real worker, reason about the worker's concurrency, not the test's.

### [Frontend/LiveKit] The agent is silent unless you call `room.startAudio()` on a user gesture
**Wrong:** Attached the agent's remote audio track to a hidden `<audio>` element and assumed it would
play. Browsers block audio playback that isn't tied to a user gesture; navigating into the room is not
one, so the agent could be **silently inaudible with no error** — the single most confusing way for a
"working" voice session to look broken.
**Right:** Call `room.startAudio()` (optimistically during connect, in case the click's gesture
context still applies) and subscribe to `RoomEvent.AudioPlaybackStatusChanged` / read
`room.canPlaybackAudio`; when blocked, surface an explicit "enable audio" button that calls
`startAudio()` from a real gesture. Also handle the terminal `RoomEvent.Disconnected` (auto-reconnect
only covers transient drops) and `detach()` tracks + remove listeners on unmount so repeated sessions
don't leak.
