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
budget with a live call, don't assume the old floor carries over. **Confirmed again later:** the
classifier stayed at 512 for a year — until a *prompt* change (proceeding-aware, more nuanced
comparative-grounds judgment) pushed its reasoning past 512 on the hard cases (verified live:
`finish=length`/empty at 512, clean JSON at 1024). The floor moved with the PROMPT, not just the
task — a more demanding prompt on the same call is a "heavier reasoning task." Raised 512 → 1024.

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
**Update (2026-07-12, PAID tier):** the free-tier limitation above was the whole reason for the HTTP
workaround — it does NOT apply on a paid plan, where the `multi-stream-input` websocket works. Carrying
the StreamAdapter regardless left every reply on the slower per-sentence HTTP path (a live pass showed
the canned objection line taking 2–8 s to play). Fix: the transport is now a config switch,
`config.ELEVENLABS_STREAMING` (default **true** = native streaming websocket = audio as the model
generates; set `false` to fall back to the HTTP StreamAdapter). Lesson within the lesson: a workaround
adopted for an account-tier constraint must be revisited when the tier changes — pin such workarounds
behind a flag from the start so lifting them is a config change, not an archaeology dig. Verify on the
box after switching (a websocket that silently yields no audio fails at *synthesis*, not construction).

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

### [Agents/LiveKit] VAD interruption at the 0.5s default cancels the agent before it speaks a frame
**Wrong:** Ran with `"interruption": {"mode": "vad"}` and the SDK default `min_duration=0.5s`. In a
real (non-studio) setting — laptop speakers, room noise, a breath, "um" — 0.5s of voice activity is
constantly detected, which fires `session.interrupt()` and **cancels Opposing Counsel's TTS before a
single audio frame plays.** Live logs were unambiguous: OC's `tts_node` reached `COMPLETE` **zero**
times across two sessions (mostly `CANCELLED after 0 frame(s)`), with an explicit
`agent_false_interruption ("a brief noise/echo was read as the attorney speaking")`. The Judge, on a
**separate non-interruptible participant**, was unaffected — so only the Judge was audible, which
*read as "the Judge is objecting/speaking out of turn."* Headphones removed the echo but the
interruptions continued (the threshold, not just echo, was the problem). It masqueraded as a TTS
bug (delayed/silent audio) for several debugging rounds — audibility was fine; the speech was being
cancelled.
**Right:** Two fixes. (1) Raise the interruption threshold well above 0.5s so only sustained speech
interrupts — `"interruption": {"mode": "vad", "min_duration": 1.0}` (env-tunable,
`INTERRUPTION_MIN_DURATION`; note `min_words` is STT-only and does nothing in pure `vad` mode).
Stay on `vad` mode — `adaptive` (which *would* distinguish backchannels) needs cloud inference we
don't have on self-hosted. (2) Make short, must-complete agent lines **non-interruptible**:
the canned "Objection — <type>." now uses `session.say(..., allow_interruptions=False)`, matching
the judge ruling. General rule: a voice agent's interruption threshold is an environment-dependent
knob, not a set-and-forget default — and diagnose "no audio" by checking whether TTS was *cancelled*
(`tts_node` never COMPLETEs) before blaming synthesis or playback.

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

### [Agents/LiveKit] `await session.say(...)` blocks until PLAYBACK finishes — parallelize the next work
**Wrong:** Sequenced `await session.say(canned_objection)` → then generate the judge's ruling
(`quick_ruling`, ~1.3 s LLM) → then speak it. Awaiting `say()` waits for the audio to finish
*playing*, not just to be enqueued, so ruling generation didn't even start until the objection had
finished playing — the "Sustained" landed ~2-3 s late (canned playback **+** generation), after the
attorney had already resumed.
**Right:** Kick off the next generation **concurrently** (`asyncio.create_task`) before awaiting the
current `say()`, so the LLM call overlaps the audio playback; the next `say()` still enqueues after
the current one (the AgentSession speech queue preserves call order), so ordering holds while the gap
drops to ≈ max(playback, generation). General rule: after any `await session.say(...)`, assume you've
already spent the whole line's duration — start slow follow-up work before it, not after.

### [Frontend/LiveKit] One agent participant can voice multiple personas — attribute with a signal, not the mic
**Wrong:** Labeled the active speaker from `ActiveSpeakersChanged` alone (any remote audio →
"Opposing Counsel"). The Judge is voiced through the *same* `AgentSession`/participant (just a
different TTS voice), so every judge line showed "Opposing counsel speaking" — a label bug even
though the audio was the correct judge voice.
**Right:** When one participant speaks as multiple personas, the client can't attribute from audio —
publish an explicit boundary signal (`{"type":"judge_speaking", speaking:true/false}` around the
judge's audio) and drive the label from that. (A separate participant per persona would avoid the
multiplexing, at more infra cost.)

### [Agents/LiveKit] A second participant means NO shared speech queue — sequence explicitly
**Wrong:** Assumed moving the Judge to its own room participant kept the old ordering for free. It
does the opposite: the ordering between the canned "Objection — <type>." and the judge's ruling had
been *implicitly* guaranteed by the single AgentSession speech queue (both were `session.say`
calls). On a separate participant the judge plays immediately — a fast `quick_ruling` would talk
OVER the still-playing objection line.
**Right:** When speech moves off the session queue, every ordering you relied on must become
explicit. `handle_interim` passes a `wait_for_clear` awaitable (an `asyncio.Event` set when the
canned `say()` returns, i.e. after playout) and the judge awaits it between ledger-update and
speaking — generation still overlaps playback, only the audio is gated. Corollary: the same move
makes the judge non-interruptible by construction (`session.interrupt()` can't touch another
participant's track), which here is a feature — but audit every interruption/ordering assumption
when relocating audio.

### [Agents/RAG] Gate every retrieval on a truthy `session_id` so offline paths are inert by construction
**Wrong:** Wiring court-rules/pleading retrieval into the agents by having each caller decide when to
skip it, or guarding it with a config flag, would mean the whole offline test/harness suite had to
monkeypatch the network everywhere — and a missed patch would make a "unit" test hit the backend, or
fail confusingly, depending on environment.
**Right:** Make the *data* carry the switch: `SessionState.session_id` defaults to `""`, and every
retrieval entry point (`case_knowledge.retrieve_*`, `court_knowledge.retrieve_*` / `dual_retrieval`,
the classifier's tier-3 fetch) returns empty immediately on a falsy `session_id`. The live worker
seeds a real id at room join; every harness/test constructs `SessionState` without one, so retrieval
is skipped with **zero monkeypatching** and the suite stays hermetic. General rule: when a capability
must be live in production but absent in tests, prefer a value on the shared state object that makes
the off-path the natural default, over per-caller conditionals or global flags — the fail-open path
then holds by construction, not by every caller remembering to check.

### [Agents/grounding] Do NOT LLM-summarize corpus text that must stay verbatim (no-fabrication)
**Wrong:** The pleading pipeline (§12) runs a structured-summary LLM pass at ingest and keeps that
digest in every prompt — so the obvious move was to mirror it for the court-rules corpus and keep a
"rules summary" in context too.
**Right:** Rule text is law: a model-written summary is **paraphrase**, and injecting paraphrased law
into prompts is exactly what the §13 no-fabrication constraint forbids. The rules pipeline therefore
has **no summary pass at all** — only chunked *verbatim* official text is stored and retrieved, and
the citation check compares against that verbatim text. General rule: a summarization step that is
fine for one corpus (facts you may restate) can be a correctness/compliance violation for another
(text whose exact wording is the point). Decide per corpus whether paraphrase is acceptable before
copying a pipeline.

### [Backend/auth] First-user-becomes-admin: promote with ONE atomic conditional UPDATE, not check-then-set
**Wrong:** Bootstrapping the first admin as `if not db.query(User).filter(role=='admin').count(): user.role='admin'`
is a check-then-act race: two first-logins can both see "no admin yet" and both promote (and under
real concurrency the ORM read and the write are separate statements with a gap between them).
**Right:** Do it as a single statement whose WHERE clause *is* the guard:
`UPDATE users SET role='admin' WHERE id=:id AND NOT EXISTS (SELECT 1 FROM users WHERE role='admin' AND deleted_at IS NULL)`.
Per-statement atomicity holds on SQLite and Postgres, so there's no ORM-level window. Reason about
and **document the residual race** rather than pretending it's gone: under Postgres READ COMMITTED,
two truly simultaneous first-logins-ever on an admin-less deployment could each evaluate the
NOT-EXISTS before either commits and both be promoted — here that's **benign** (two founding admins
of an empty install), and impossible under today's single-tenant stub auth, so a pg advisory lock /
SERIALIZABLE upgrade is documented but deliberately not taken. Exclude soft-deleted admins from the
guard or a deployment whose only admin was soft-deleted is permanently locked out of bootstrap.
General rule: for "first one wins" promotions, push the guard into the write's WHERE clause, then
still state the residual race and why its worst case is acceptable.

### [Backend/auth] passlib 1.7.4 is broken with bcrypt >= 5.0 — use bcrypt directly
**Wrong:** Reached for `passlib[bcrypt]` (the usual choice) for password hashing. passlib 1.7.4's
import-time backend self-test hashes a >72-byte probe string; bcrypt 5.0 now raises
`ValueError: password cannot be longer than 72 bytes` on it, so EVERY hash/verify blew up
(`_calc_checksum` → `bcrypt.hashpw`), and passing tests wouldn't have caught it — the failure is at
runtime with the installed bcrypt.
**Right:** Use the `bcrypt` library directly (`bcrypt.hashpw` / `bcrypt.checkpw`), truncating the
password to 72 bytes yourself (bcrypt's inherent limit — standard practice). One thin
`security_password.py` wrapper, no passlib. When a "convenience" wrapper lib pins an old release,
check it against the actually-installed backend version before adopting it.

### [Frontend/LiveKit] Attach already-subscribed tracks — a subscribed-but-unattached track is silent yet still "speaking"
**Wrong:** Attached remote audio ONLY from the `RoomEvent.TrackSubscribed` handler, which was
registered AFTER `await room.connect()`. autoSubscribe delivers tracks that were already published
when the browser connects (the agent / judge participant are usually in the room first) DURING
`connect()`, so `TrackSubscribed` fires before the listener exists — those tracks (Opposing Counsel
especially) were never `track.attach()`-ed to an `<audio>` element and played **silently**. The trap
is what still worked: the visualizer's `AnalyserNode` reads the subscribed track's `mediaStreamTrack`
directly, and `ActiveSpeakersChanged` is computed server-side from the published audio — BOTH
independent of the `<audio>` element — so the equalizer bars moved and the "X speaking" badge showed
while the user heard nothing, and no autoplay "enable audio" banner appeared (playback never got as
far as being blocked). It reads exactly like a TTS bug but the audio was reaching the client fine.
**Right:** Either register `TrackSubscribed` BEFORE connecting, or (if a connect helper owns the
connect) sweep `room.remoteParticipants` right after registering the handler and `attach` any
`publication.track` already present — with a **dedup guard** so a track arriving via both the sweep
and the event isn't attached twice (doubled audio). Corollary #1: "bars move / badge says speaking"
proves frames reach the client, NOT that they're audible — audibility is the `<audio>` element +
autoplay unlock, a separate concern; diagnose playback before blaming TTS. Corollary #2: register the
gesture-unblock listeners UNCONDITIONALLY — `canPlaybackAudio` can read `true` before any track plays
and flip `false` later when audio arrives, so gating the unblock on it at connect time skips it and
strands the user with no banner and no recovery but the explicit button.

### [Agents/prompts] A future prompt-customization layer must be structurally unable to reach a safety constraint
**Wrong:** When moving prompts into files (so they're tunable without touching code) and designing
toward an eventual user-customizable-prompt feature, the obvious shape is one editable prompt blob
per persona. That would let a future customization layer edit or drop the no-fabrication /
never-invent-case-law lines along with the tone — silently removing a correctness/compliance
guarantee. Retrofitting a safety boundary onto an already-shipped customization feature is far
harder than designing for it up front.
**Right:** Separate an IMMUTABLE constraints region from the customizable style/persona content from
day one, and shape the loader API so the boundary is *structural*, not a convention someone can
forget: `prompts.render(name, **variables)` NEVER accepts constraint text as a parameter — a
customization layer can only ever pass style/persona `variables`, so it has no surface to touch a
constraint. Two backstops make it defense-in-depth: (1) the real grounding enforcement is CODE, not
prompt (`citation_check.flag_ungrounded` + fail-safe defaults + the verbatim-only rules corpus),
immune to any prompt whatsoever; (2) byte-identical golden tests freeze each prompt's exact text, so
even a direct edit to a constraint line fails CI and shows up as a deliberate, reviewed change.
Process corollary: do the structural migration (move, don't change) and any wording improvement as
SEPARATE commits — mixing them hides a behavior change inside a "just moved it" diff. Deferred by
design (documented, not done): collapsing the duplicated no-fabrication lines into one shared
`_core_constraints.md` is the correct end state, but it changes prompt bytes, so it must be its own
explicit, tested behavior change — never folded into the move.

### [Agents/TTS] Delivery cues (v3 audio tags) must never leak into persisted/displayed text — keep a clean/tagged split
**Wrong:** Authoring ElevenLabs v3 audio tags (`[solemnly]`, `[pauses]`) into the Judge's
`closing_ruling` and using that one string everywhere. It's spoken (good) but the SAME string is also
persisted as the scorecard's `judge_ruling`, rendered in the transcript, and run through
`citation_check` — so literal `[sighs]` leaks into the *written* verdict and the grounding check.
Also naïvely stripping only the known allowlist leaves any tag the model invents off-list to leak.
**Right:** One authored ruling, two derived forms. The **clean** (tag-stripped) text is the single
source of truth — `state.add_turn`, the scorecard, `citation_check`, the frontend all use it; the
**tagged** text is used ONLY as the v3 TTS input and never leaves that one call. Strip with a pattern
that catches BOTH allowlisted and invented tags (lowercase, short, bracketed: `\[[a-z][a-z ]{0,20}\]`)
so an off-list `[grumbles]` can't leak either, while sparing citations (`Section 23`, and
`[Section 23]` with caps/digits don't match the lowercase-only pattern). Fallback corollary: if the
primary (v3 participant) fails, the degraded fallback (flash) must speak the CLEAN text — flash would
otherwise voice a literal `[sighs]`. General rule: when one generated string feeds both **delivery**
(TTS) and the **record** (persistence/display/verification), the delivery-only decorations belong on a
separate derived value, never the shared one. (Separate, quieter gotcha from the same task: leaving
ElevenLabs `voice_settings` unset makes the plugin omit it entirely, so the API uses each voice's flat
default — `style`≈0 — which reads as monotone; pass explicit `voice_settings` to get expressiveness.)

### [Backend/RAG] Retrieval accuracy for citable law: section-aware chunks + exact lookup + a relevance floor that can return nothing
**Wrong:** Chunk statutes with the same fixed-size character windows used for pleadings, store
`section_reference` as descriptive metadata only, and rank purely by cosine with a top-k that ALWAYS
returns k. Three failures compound: (1) a window cuts mid-section, so retrieval hands the model half a
provision missing its proviso/exception, and mid-section chunks aren't even labeled; (2) a query that
literally names "Section 73" depends on embedding rank to surface §73 — there's no direct lookup even
though the section number is known; (3) the 4th-nearest chunk is returned however tenuous (cosine
~0.1), so a weak/irrelevant provision gets shown and can be cited, and the citation check (which only
verifies *shown*) passes it. "Grounded" silently drifts from "correct."
**Right:** Three matched fixes. (A) **Section-aware chunking for the rules corpus** (not pleadings):
split at detected headings so a chunk is a complete provision; an oversized section → windowed
sub-chunks EACH stamped with the parent heading (labeled, not NULL); a no-heading span degrades to
generic windowing (never fails). (B) **Hybrid exact-citation lookup**: canonicalize the query's
section refs (`Section 12`==`Sec. 12`==`§12`) and fetch those chunks by `section_reference`
deterministically, ahead of semantic top-k — a named section no longer depends on embedding rank, and
(with A) returns the whole provision. (D) **Relevance floor with return-fewer-than-k**: drop matches
below τ, so retrieval returns fewer than k — including ZERO. The non-obvious key: returning zero is
SAFER than padding, and it costs nothing to build because it **reuses the existing fail-open
empty-block path** (a below-threshold result is indistinguishable from a retrieval failure, which the
pipeline already handles by proceeding on the case summary with no rules block). "Return nothing
rather than a weak match" beats "always return the best-k-however-tenuous" for citation accuracy.
Permanent boundary to state honestly, not paper over: none of this makes "grounded" equal "legally
correct" — a strong-cosine-but-wrong provision still passes. Semantic similarity ≠ legal relevance;
closing that needs a reranker / labeled eval (the deferred Phase-7 golden set).

### [Backend/testing] A monkeypatched module attribute does NOT reach a def-time default argument
**Wrong:** `def retrieve(..., embedder=embedding_service.embed_text)` — the default is bound to the
function object ONCE at def time. A test's `monkeypatch.setattr(embedding_service, "embed_text", fake)`
replaces the module attribute but NOT the already-bound default, so the function keeps calling the
real (network) embedder. This stayed invisible for months because the old no-floor `top_k` returned
the top-k regardless of a garbage cosine (real 768-dim query vector vs a 3-dim test-embedded chunk →
`len` mismatch → cosine 0.0 → still returned as "top 1"). Adding a relevance floor exposed it: the
0.0-cosine result was now correctly dropped, and the test that "passed" was revealed to have never
used its injected embedder at all.
**Right:** Resolve injectable seams at CALL time, not as a def-time default: `embedder=None` then
`embedder = embedder or embedding_service.embed_text` inside. Now a monkeypatched module attribute is
picked up. General rule: a default of `module.attr` freezes the value; if a test needs to swap it,
either pass it explicitly or resolve it inside the function. And when a "passing" test survives a
change that should have broken it, suspect the test was never exercising the path it claims to.

### [Backend/RAG] Re-upload was ADDITIVE — supersede must be atomic, structural, and provenance-preserving
**Wrong:** Every document upload minted a new row, ingest deleted only the NEW document's (zero)
chunks, and retrieval queried chunks by the denormalized court_id/case_id with no document filter —
so "re-uploading" a corrected statute would have left the old fixed-window chunks retrievable
alongside the new section-aware ones, both eligible per query, non-deterministically (the poison
pill). Worse, the chunk tables have no deleted_at, so soft-deleting the DOCUMENT row would have
changed nothing about retrieval. And a naive fix — hard-delete the old chunks — would sever
RulingProvenance.chunk_ids_used, defeating the audit trail the system deliberately built.
**Right:** Three coupled decisions. (1) **Exclusion is structural, at the query:** retrieval filters
chunks through the parent document's deleted_at (an IN-subquery) — archived chunks are ineligible in
BOTH the exact-citation and semantic paths regardless of rank, while the rows stay for provenance.
(2) **Replace is one explicit, atomic action** — not a filename-matching implicit supersede (a new
document with a similar name would silently archive the old one) and not a manual archive-then-upload
two-step (forgetting step one recreates the hazard: the failure mode of the safety mechanism must not
be the hazard itself). The old version is archived ONLY when the replacement ingests to `ready`, so a
failed ingest can't strand the corpus, and restore of a superseded doc is refused while its
replacement is live. (3) **Two tiers, not one "delete":** Archive keeps everything resolvable
(reversible, low-friction); Purge is admin-only + typed-confirmation and is ALLOWED to break
provenance resolvability — chunk_ids_used are strings, not FKs, so purged ids become honest
tombstones and the display (counts) degrades gracefully instead of erroring; refusing purge would
neuter it for its main use (test/mistake uploads, usually cited only by test sessions). Load-bearing
regression: rig an archived chunk to WIN both ranking mechanisms and assert it can never be
retrieved, at every entry point, on both corpora.

### [Agents/Voice] The judge's FIRST bench ruling was inaudible — track published lazily on first say()
**Wrong:** `JudgeParticipant.connect()` only joined the room; the judge's audio track was published
LAZILY inside `_ensure_track()`, i.e. on the *first* `say()` — which is the first objection ruling,
often minutes into the session. Publishing a brand-new track mid-session means the browser must
still receive the track-published event, subscribe, attach a fresh `<audio>` element, and clear
autoplay (scoped per element — the OC track being unlocked does NOT unlock the judge's new one). The
worker pushed the ~2–4 s ruling into the track and completed `wait_for_playout()` (publisher side)
before the browser was ready, so objection #1's audio went nowhere while the ledger, transcript, and
the reliable data-channel `ruling` event all still recorded it. Diagnostic tell: the agent log shows
the `objection dispatch` line and **no** `inline ruling unavailable` / `falling back` / `could not be
spoken` warning — the ruling was generated and "spoken", just into a track nobody was subscribed to
yet. Every subsequent ruling reused the now-live, unlocked track and was heard — hence the exact
signature "first objection had no ruling, the next 5 did." (NOT a model cold-start: `quick_ruling`'s
10 s timeout never tripped.)
**Right:** Warm the track at session start. `JudgeParticipant.prime()` publishes the track and pushes
a ~200 ms silent frame right after `connect()`, sized from the TTS's own `sample_rate`/`num_channels`
(identical to what `synthesize()` yields, so the pre-published source never mis-rates the real ruling
frames). The browser subscribes + autoplay-unlocks during the join window, so the first real ruling
is audible like the rest. Best-effort and non-fatal: a prime failure just degrades to the old
first-ruling-clip behavior. General rule: any media track that must play a latency-sensitive line
should be published and primed at join time, never lazily on the first real utterance — the
first-published-track subscribe/attach/autoplay window will otherwise swallow that utterance.

### [Agents/Judge] Live oral-argument run came back ALL sustained — the judge ruled blind to the proceeding
**Wrong:** The inline quick-ruling prompt (`judge_quick_ruling.md`) received the objection's ground +
the statement but **not the proceeding type** (`SessionState.snapshot()` never included it), and it
gave no instruction to test the objection's merit — just "Opposing Counsel objected; rule sustained
or overruled." Handed an already-raised objection with no lens and no mandate to push back, the model
**anchored and sustained every time**, back-filling a mismatched reason (sustained an `assumes_facts`
objection with reason "argumentative"). In oral argument that is a category error: no witness is
testifying, so counsel arguing the law and characterizing the record ("this mortgage is ultra vires
as a matter of law," "demand upon the board would have been futile") is *proper* — those are not
statements that "assume facts not in the record." Result: a script written for a sustained/overruled
MIX produced 5/5 sustained, all labeled `assumes_facts`. Tell in the transcript: every `judge` turn
"Sustained. <reason>" with the reason not matching the objection's ground. (The classifier was
already proceeding-aware for RESTRAINT — but proceeding-awareness on the fire side is wasted if the
ruling side rubber-stamps whatever slips through.)
**Right:** Give the judge the same lens the classifier has, on BOTH ruling paths. (1) Inject
`PROCEEDING TYPE` into the inline `quick_ruling` context AND the end-of-session `assess_session`
context (not just the classifier). (2) Both judge prompts now rule **on the merits**: an objection
being raised is not itself grounds to sustain; in an argument proceeding, arguing the law / drawing
inferences / characterizing the record is proper, so `assumes_facts` / `calls_for_legal_conclusion` /
`argumentative` objections are OVERRULED unless the statement genuinely misstates an established fact
or strays from the issues; witness examinations apply ordinary evidentiary grounds. No hard-coded
ruling bias ever existed (the parsers already fail attorney-favorable: quick-ruling raises → stays
pending, assessment defaults unknown → overruled) — the skew was purely the missing lens +
anchoring. Prompt changes are made prompt-and-golden-together (`tests/test_prompts.py` byte-goldens),
never silently. General rule: any LLM handed a decision another component already "pre-approved"
(here: an objection the classifier fired) will anchor toward ratifying it unless explicitly told to
re-adjudicate on the merits with the same context that component used.

### [Agents/OC] Two objection channels, one wired to the judge — "OC objected 5×, judge ruled once"
**Wrong:** The system has TWO ways an objection can appear, but only one produces a ruling. (1) The
objection classifier fires a structured barge-in (`was_interruption=true`) → records to the ledger →
the judge rules. (2) The Opposing Counsel persona was told to "raise objections when the phrasing
invites one," so the REASONING model also *verbalized* objections inside its end-of-turn spoken reply
("Objection, your honor, relevance…", `was_interruption=false`). Channel (2) is just OC's argument
text — it never calls `record_objection` or `judge_rule`, so the judge never rules on it. A live
oral-argument pass: OC said "objection" in 4 of its 5 spoken replies, the classifier barged in once,
and the judge ruled exactly once (correctly overruling the one structured objection). To the user it
looked like the judge ignored 4 objections. Root cause: the persona duplicated the classifier's job
without the ruling wiring, so the two channels diverged.
**Right:** Collapse to ONE objection channel and make it an invariant: the word "objection" may only
come from the structured barge-in (which the judge rules); OC's spoken reply is COUNTER-ARGUMENT ONLY
and must never lodge an objection or say "objection"/"I object" — it makes the same point as argument
("The record does not support that…"). Enforced in the persona (`opposing_counsel.md`) and the
per-turn `oc_reply_style.md`, with a log-only guard in `llm_node` that warns if a reply still lodges
one (never rewrites — mangling spoken text is worse than a logged slip). This keeps OC's strong
argumentation (the user liked it) while guaranteeing every objection the attorney hears gets a bench
ruling. General rule: if two components can both emit the same user-visible signal (here: "an
objection"), exactly one must own it end-to-end — a second, unwired emitter produces outputs the rest
of the pipeline silently drops. Also bumped the inline ruling from "a few words" to one crisp
judicial sentence so the bench reads as authoritative as counsel, not a bare label.

### [Agents/Voice] Judge and OC talked over each other — two audio tracks, no shared floor
**Wrong:** The judge speaks on its OWN LiveKit participant/track (so it's non-interruptible and
attribution is correct by construction), which means judge audio deliberately **bypasses the OC
AgentSession's speech queue**. Great for "VAD can't cut the judge off" — but it also means the two
outputs have no mutual exclusion. When the attorney's speech fragmented into several rapid STT
finals, the classifier fired an objection on one final → the judge ruled (on its track), while OC's
end-of-turn `llm_node` reply to the NEXT final streamed out (on the session track) at the same time.
The `turn_flags["objected"]` skip only suppresses OC's reply for the SAME turn, so it didn't help the
cross-turn collision. Result: judge and OC audibly speaking simultaneously. (The longer, one-sentence
rulings we'd just added widened the collision window.)
**Right:** A shared speaking floor — an `asyncio.Event` (`judge_idle`, SET = judge idle). `judge_rule`
and the closing-ruling path CLEAR it around the bench's speech and ALWAYS release it in a `finally`
(timeout, error, or success); OC's `llm_node` AWAITS it before it starts streaming a reply. The judge
always has priority (it's the court); OC simply waits its turn. General rule: the moment you give a
speaker its own audio track to escape a shared queue, you've also opted out of that queue's implicit
serialization — you must add an explicit floor/mutex back, or independent tracks will overlap exactly
when timing gets tight.
