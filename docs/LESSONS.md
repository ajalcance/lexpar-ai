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
budget is the wrong lever — change the model or skip the call (see next entry). The floor **scales
with task complexity, not output size**: the objection classifier is fine at 512, but the judge's
end-of-session assessment (rule every objection + extract facts + closing ruling) reasons far more
and came back empty at 512 — it needed **1536**. When you add a heavier reasoning task, re-check the
budget with a live call, don't assume the old floor carries over.

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

### [Agents/config] Pass provider keys EXPLICITLY — plugin default env-var names don't match ours
**Wrong:** Constructed `elevenlabs.TTS(model=…, voice_id=…)` without an `api_key`, trusting the
plugin to read the key from the environment. The ElevenLabs plugin looks for **`ELEVEN_API_KEY`**,
but our project convention (ARCHITECTURE §9, `.env`, `config.py`) is **`ELEVENLABS_API_KEY`** — so the
worker crashed at job start with "ElevenLabs API key is required … set ELEVEN_API_KEY". It only *seemed*
to work for Deepgram because that plugin's default (`DEEPGRAM_API_KEY`) happens to match our name.
**Right:** Read every provider key from our own env names in `config.py` and pass it **explicitly**
into the plugin (`elevenlabs.TTS(api_key=config.ELEVENLABS_API_KEY)`, `deepgram.STT(api_key=…)`), never
relying on each plugin's implicit lookup. One config is the single source of truth; a plugin changing
(or already having) a different default env-var name can't silently break us. Silero VAD needs no key.

### [Agents/TLS] aiohttp "failed to connect" on macOS — python.org builds ship NO CA bundle
**Wrong:** Read the worker's `failed to connect to deepgram` as a Deepgram problem (key, credit,
network). The key was valid, the account had credit, and curl reached the API fine. The real cause:
python.org macOS builds have `ssl` default `cafile=None`, so **every aiohttp TLS connection** fails
`CERTIFICATE_VERIFY_FAILED` — which the LiveKit plugins surface as generic "failed to connect". The
trap is asymmetric: httpx-based clients (openai, backend_client) bundle certifi and work, so LLM
calls succeeding "proves" the network while the aiohttp-based voice plugins (Deepgram, ElevenLabs,
LiveKit inference) all fail together.
**Right:** When aiohttp-based things all fail to connect while httpx/curl work, suspect the CA bundle
first — reproduce with a 5-line aiohttp GET and look for `SSLCertVerificationError`. Fix in one place:
`os.environ.setdefault("SSL_CERT_FILE", certifi.where())` at the top of `agents/config.py` (respects
an explicit override; certifi added to requirements). Diagnose provider errors with direct REST calls
before blaming the provider.

### [Agents/TTS] A valid ElevenLabs key is not enough — the VOICE must be usable on the plan
**Wrong:** Assumed key-level checks proved TTS would work. The default voice id we shipped
(`21m00Tcm4TlvDq8ikWAM`, "Rachel") is a legacy **library** voice: free-tier API synthesis against it
fails `402 payment_required ("Free users cannot use library voices via the API")` — at *synthesis*
time, i.e. mid-session, not at construction. Also: scoped keys (TTS-only) 401 on `/v1/user` and
`/v1/voices`, so key-validity probes against those endpoints mislead.
**Right:** Verify TTS with a real tiny synthesis call (`POST /v1/text-to-speech/{voice_id}` with a
two-word body) against the exact voice + model you ship. Default to a current **premade** voice
(config default is now "George", `JBFqnCBsd6RMkjVDRZzb` — verified 200/audio on the free tier).

### [Agents/TTS] ElevenLabs multi-stream websocket returns no audio on free tier — use StreamAdapter
**Wrong:** Used `elevenlabs.TTS(...)` directly as the AgentSession TTS. The livekit plugin's
streaming path (`.stream()`) hardcodes the **`multi-stream-input`** websocket, which on our
free-tier account opens but yields **zero audio frames**, so the socket closed `1006` ("closed
unexpectedly") and every reply went out as text only (the objection *text* rides the data channel,
so classification looked fine — only the voice was missing). The downstream "speech not done in time
after interruption, cancelling" error was just this: audio that never arrived, timed out at 5s.
**Right:** The plugin's non-streaming `synthesize()` uses the plain HTTP `/text-to-speech/{voice}/
stream` endpoint, which *does* work on this account (verified 200/MP3). Wrap the TTS in the agents'
`StreamAdapter(tts=elevenlabs.TTS(...))` — it drives TTS sentence-by-sentence over that HTTP endpoint
instead of the websocket. When diagnosing a websocket TTS, test the specific endpoint the plugin uses
(single-stream vs multi-stream-input vs HTTP /stream) individually; they have different plan/account
support, and "the key works" (REST 200) doesn't prove the websocket path does.

### [Infra/LiveKit] Docker-on-macOS: signaling connects but WebRTC fails without `--node-ip`
**Wrong:** Ran `livekit-server --dev` in Docker and assumed mapped ports (7880/7881/7882) were
enough. Signaling worked (token accepted, room joined, `curl localhost:7880` → OK), but the browser
died with `ConnectionError: could not establish pc connection` — the server auto-detects its
**container-internal IP** and advertises it in ICE candidates, which the host browser can't reach
(Docker Desktop runs containers in a VM). The deceptive part: everything *up to* the media path
works, so it looks like a frontend bug.
**Right:** For same-machine dev, run the server with `--node-ip 127.0.0.1` (now in
`infra/docker-compose.yml`) so ICE candidates point at localhost; confirm the startup log shows
`"nodeIP": "127.0.0.1"`. A real deployment instead advertises its actual reachable address. If
signaling works but the connection dies ~5–15 s later with a pc/ICE error, suspect advertised
addresses first, not the client.

### [Agents/LiveKit] Self-hosted server: pin LOCAL turn handling — the SDK defaults to Cloud
**Wrong:** Left `AgentSession` turn handling on auto-detect while running against a self-hosted
LiveKit server. The SDK prefers LiveKit **Cloud** services: interruption auto-picked "adaptive"
(cloud inference → ~5 s of connect retries per session) and dev mode resolves the turn detector to
the cloud "v1" (→ a 401 before falling back to the local mini model). Every session start paid
retry latency + warning noise for services we don't have.
**Right:** On self-hosted, pin both knobs to local:
`turn_handling={"turn_detection": inference.TurnDetector(version="v1-mini"), "interruption":
{"mode": "vad"}}` — "v1-mini" *is* the local fallback model, used directly with no cloud transport.
Also note `livekit.plugins.turn_detector` (EnglishModel/MultilingualModel) is deprecated in favor of
`livekit.agents.inference.TurnDetector`, and the plugin models only construct inside a job context —
verify SDK usage against the installed version, not remembered docs.

### [Agents/STT] Deepgram finals are NOT prefix-stable with their interims — don't debounce on raw text
**Wrong:** The objection debouncer decided "same utterance still growing" with an exact string check
(`current.startswith(prev)`). Interims arrive lowercase/unpunctuated ("i i my client told me…");
after the endpointing pause, the segment's **final** arrives with smart formatting applied —
capitalized, commas inserted, numbers rewritten ("March third" → "March 3"). The final fails the
prefix check, gets treated as a NEW utterance, re-arms the debounce, and **the same objection fires
twice** — the second time "with no new speech" (the pause was just Deepgram finalizing). The SDK's
`UserInputTranscribedEvent` has no segment id to key on (transcript/is_final/speaker_id only).
**Right:** Two layers. (1) Compare continuation on **normalized** text (lowercase, alphanumerics
only) so revisions of the same utterance don't re-arm. (2) A **re-fire cooldown** (time floor,
injectable clock for tests) catches what normalization can't (digit rewrites), and doubles as the
"don't object over the judge" guard — re-arming additionally gated on the inline ruling completing
(`hold()`/`release_hold()`), not just the timer. General rule: anything keyed on interim STT text
must survive the final's rewrite; test with a revised-final case, not just growing fragments.
