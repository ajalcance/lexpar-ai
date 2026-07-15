# LexPar AI — Implementation Audit & Scale/Enterprise Review

**Date:** 2026-07-15 · **Auditor:** Claude (read-only pass) · **Scope:** whole repo, with a deep
dive on the Opposing Counsel + Judge reasoning core through a commercialization lens.

**Method note (honest scope):** Part B (the reasoning core, `agents/`) and the
tenancy/isolation/infra questions were audited by reading the actual implementation of the
critical paths (`objection_classifier`, `session_state`, `llm_router`, `streaming_verify`,
`verification`, `voice_interrupt`, `main.py`, `config.py`, `backend/app/security.py`,
`backend/app/api/cases.py`, `infra/docker-compose.prod.yml`, `frontend/src/lib/api.ts`). Part A is
a **representative** sweep of those files, not an exhaustive line-by-line of every module. Findings
already tracked as deliberate future work in ARCHITECTURE §11 / the PLAN checklist are excluded.

---

## 1. Executive summary — top 5, ranked by impact

1. **[HIGH] Shared thread pool + no LLM-call timeouts = cross-session failure coupling.**
   Every blocking LLM call funnels through the process's **default** executor
   (`asyncio.to_thread` and `run_in_executor(None, …)`), and none of the core LLM calls
   (`llm_router.chat`/`chat_stream`) pass a timeout — so the OpenAI SDK's 600 s default applies.
   One stalled provider connection holds a shared-pool thread for up to 10 minutes, and enough of
   them degrade **every concurrent session on that worker**, not just the affected one. This is the
   main thing between "one session works" and "many stay isolated." (B3/B4/A2)
2. **[HIGH] No tenant boundary; a global admin can purge any user's data.** There is no firm/org
   entity — `users.firm_name` is free text. `admin` is a single global role (first-registrant
   bootstrap), and `purge_case` runs `db.get(Case, case_id)` after `require_admin` with **no
   ownership scoping** (`cases.py:206`). This is the biggest *commercialization* blocker for a firm
   sale and a latent cross-tenant authorization risk. (B6/A6)
3. **[MEDIUM] No inference resilience: single provider, no retry/fallback/metering.** `llm_router`
   resolves one provider per role from env with no retry, backoff, or fallback. A Fireworks blip
   mid-session fails closed → the product goes silent for every session until it recovers. No
   per-tenant token/cost accounting exists for billing or abuse caps. (B8)
4. **[MEDIUM] Court-rules RAG is brute-force and silently degrades under a large corpus.** Retrieval
   is O(chunks) cosine in Python over JSON-array embeddings, on the **live objection path** bounded
   by a fast timeout — so a big rules corpus doesn't error, it quietly returns *ungrounded*
   rulings. Closer to a real limit than the backlog framing suggests. (B5)
5. **[MEDIUM] No metrics/alerting.** Logging is rich (per-decision audit outcomes, dispatch
   latencies) but it's all log lines — no latency percentiles, error-rate counters, or the one
   product-quality canary that matters: a spike in "no verified sentences" (OC going silent). You'd
   learn of a brownout from a customer, not a dashboard. (B7)

**What's genuinely well-built (state it plainly):** session state is cleanly **per-session** with
no module-level mutable singletons in the hot path (the `ObjectionClassifier` lock the docs worried
about is per-instance, not global), and the LLM routing is a real config switch. The agent tier is
architected to scale out horizontally — the gaps below are in shared-resource isolation, tenancy,
and operability, **not** in the core design.

---

## 2. Part A — general code quality & bug findings

| # | Sev | File:line | Finding |
|---|-----|-----------|---------|
| A1 | Low | `agents/config.py:103` & `:178` | **Duplicate `_getfloat` definition.** Defined twice; the first (103–108) is shadowed/dead, and the two bodies differ subtly (first catches `TypeError`/`ValueError` over `os.getenv(name, str(default))`; second reads raw + `None`→default). All callers sit after line 178, so the first never runs. Delete it. Violates the repo's own "one definition / readability" rule. |
| A2 | Medium | `agents/llm_router.py:86`,`108` | **No timeout on core LLM calls.** `chat`/`chat_stream` never pass `timeout=`, and `build_endpoint` builds `OpenAI(...)` with none → SDK default 600 s. The timeout pattern exists elsewhere (`backend_client`=15 s, `quick_ruling` wrapped in `wait_for(10s)`, court retrieval `FAST_TIMEOUT`) but is absent from the reasoning/verification/judge/objection calls that dominate the live path. Feeds A3/B4. |
| A4 | Low | `frontend/src/lib/api.ts:60` | **No client-side abort/timeout** in `request()`. A hung backend leaves the fetch pending indefinitely (no `AbortController`). Minor resilience/UX. |
| A5 | Low | `frontend/src/lib/api.ts:14,530` | **Mock transcript ships in the prod bundle.** `getSessionScript` returns `mockTranscript`. It's an intentional fallback (ARCHITECTURE §4), but the demo fixture is compiled into production; consider gating behind the reviewer flag / tree-shaking. |
| A6 | Info→Sec | `backend/app/api/cases.py` (all routes) | **Ownership is by-convention, not structural.** Every case route re-calls `case_service.get_case(db, current_user, …)` for the 404/ownership check. Correct today, but one new route that forgets it = an IDOR. A shared dependency (`Depends(get_owned_case)`) would enforce it structurally. Ties to B6. |

No correctness bug was found in the streaming/segmentation/verification logic itself — the
sentence segmenter's abbreviation guard, the fail-closed paths, the debounce normalization, and the
judge-floor/`judge_idle` handshake are carefully done and well-commented, and the "wrong splits are
latency noise, not correctness bugs" invariant holds because every piece is verified downstream.

---

## 3. Part B — scale & commercialization deep-dive (the OC/Judge core)

### B1 — Module boundaries / partitioning
**Verdict: logically clean, with two process-global couplings.** Each `entrypoint` builds its own
`SessionState`, `ObjectionClassifier` (per-instance `threading.Lock`), `FloorTracker`,
`TurnRecovery`, and `judge_idle` Event — all per-session, no shared singletons in the hot path. The
lock serializing `consider()` is per-classifier (per-session), so it is **not** a global bottleneck.
The two shared resources are: (a) `llm_router.build_endpoint` constructs a **fresh `OpenAI` client
per call** (no pooled/reused client → new connection setup on every reasoning/verify/objection call),
and (b) all blocking work uses the **shared default thread pool** (see B3/B4).
**Recommend:** inject a reused (pooled) OpenAI client; give the worker a dedicated bounded executor.

### B2 — Horizontal scaling readiness
**Verdict: the agent tier already scales out; the backend is the single-process assumption.** A
LiveKit job (room/session) is dispatched to one worker and its `SessionState` lives entirely in that
process for the session lifetime — so the in-memory state is **not** a horizontal-scaling blocker:
run N `agents` replicas and LiveKit distributes rooms. The real single-process assumptions are on the
**backend**: `rate_limit.py` is explicitly in-memory ("one backend container", per §5), so a second
backend replica silently weakens rate limiting; and the RAG is per-request Python brute force.
**Recommend:** document max concurrent sessions per worker and size accordingly; before running >1
backend replica, move rate limiting to Redis (and RAG to pgvector, B5).

### B3 — Streaming pipeline scalability
**Verdict: correct design, unbounded concurrency.** `astream_verified_reply` runs one producer
thread per active reply on the **default** executor (`run_in_executor(None, …)`), and per sentence
makes a blocking `check_consistency` call with no timeout (A2). Under N concurrent sessions each
streaming a reply, that's N producer threads plus their verification calls contending for
`min(32, cpu+4)` shared threads — no backpressure, no per-session cap, no explicit pool size. On a
modest box (~4 vCPU) this likely begins head-of-line blocking at a handful of concurrent voice
sessions. **Recommend:** a dedicated bounded executor sized to target concurrency, explicit per-call
timeouts, and a semaphore capping in-flight verification calls.

### B4 — Failure isolation
**Verdict: partial.** Good: per-session state, fail-closed verifier/classifier, judge fail-safe
(objection stays pending, never a fabricated penalty), best-effort provenance/publish, non-fatal
context load. Gap: no timeout on the core LLM calls (A2) means a hung provider call holds a
shared-pool thread indefinitely, and the shared default executor (B1/B3) makes that exhaustion cross
session boundaries — a single provider brownout can degrade **every** concurrent session on a worker.
**Recommend:** timeouts on every external call + a bounded/isolated executor + a circuit breaker
around the provider (B8).

### B5 — Data partitioning at the storage layer
**Verdict: fine now, real work at volume — and the sharpest edge is court-rules retrieval, not the
pleading RAG.** pgvector is already flagged (§12) for the pleading case (~100 chunks, genuinely
fast). But the **court-rules** corpus can be far larger and its retrieval sits on the **live
objection path** under a fast timeout — so a big corpus silently degrades to *ungrounded* objections
rather than erroring. Also verify/add an index on `transcripts.session_id` (the fastest-growing
table, read ordered by session). **Recommend:** index the FK columns; migrate court-rules retrieval
to pgvector **before** onboarding a firm with a large rules corpus — treat this as nearer-term than
the pleading-RAG backlog item.

### B6 — Multi-tenancy & enterprise readiness  *(biggest commercialization gap)*
**Verdict: not multi-tenant.** Auth is per-user (`attorney`/`admin`); data is scoped by `user_id`
ownership checks repeated per route (A6); `admin` is a single **global** role (first-registrant
bootstrap) that can `purge_case`/`purge_court` across **all** users with no ownership scoping
(`cases.py:206` — `db.get(Case, case_id)` after `require_admin`). There is **no** organization
entity — `users.firm_name` is a free-text string, not a tenant. Consequences: no firm-level data
isolation, no firm-admin vs platform-admin distinction, no SSO, no per-tenant usage metering/billing.
**Recommend (before the first multi-seat customer — much cheaper pre-production-data):** an
`organizations` table + `user.org_id`; org-scoped queries enforced **structurally** (a shared
`get_owned_case`-style dependency, not per-route discipline); a firm-admin role separate from
platform-admin; per-org isolation guarantees; SSO and per-org metering on the roadmap.

### B7 — Observability at scale
**Verdict: great logging, no metrics/alerting.** Per-decision audit outcomes, per-fire dispatch
latencies, and provenance are all logged — but as log lines, with no latency percentiles, error-rate
counters, or alerting. **Recommend:** emit metrics (Prometheus/OTel) for per-role LLM latency +
error rate, session-completion rate, objection fire rate, and especially the **verification-failure
/ "no verified sentences" rate** — that's the canary for OC silently going quiet, the exact failure
mode the code comments describe fighting live.

### B8 — Cost & inference resilience
**Verdict: single point of failure, no metering.** One provider per role from env; `build_endpoint`
builds one client; no retry/backoff, no fallback provider. A Fireworks outage fails closed → silence
for every session. No per-session/per-tenant token accounting for billing or spend caps.
**Recommend:** retry-with-backoff + a secondary-provider fallback in `llm_router` (the
OpenAI-compatible abstraction makes this a small change); emit per-session token counts for billing.

### B9 — Testing at concurrency
**Verdict: gap, honestly.** ~250 agent tests, all with the model call mocked and exercised
sequentially; the debounce/cooldown/hold/lock state machine is tested for correctness via an injected
decider, but nothing fires **many parallel** `consider()`/`handle_interim` calls under real threads,
and nothing simulates pool exhaustion. **Recommend:** a concurrency test proving lock serialization +
no double-fire under real parallel threads, and a load-shape test for the streaming pool behavior.

---

## 4. Triage — blocking vs. can-wait

**Enterprise / commercialization-blocking (do before the first paying multi-seat firm):**
- **B6 tenancy** — schema + query-layer change; gets far more expensive after production data exists.
- **B4/B3 isolation** — timeouts on all external calls + a bounded, dedicated executor. Relatively
  small change, outsized reliability payoff; do it early.
- **B8 resilience + metering** — retry/fallback provider and per-session token accounting.
- **B7 observability** — you cannot operate this for paying customers blind.

**Can wait (schedule, not urgent):**
- **B5 pgvector for court rules** — until a customer brings a large rules corpus (but before that).
- **B9 concurrency tests** — add alongside the B3/B4 fixes.
- **A1 / A4 / A5** — hygiene; fold into the next touch of those files.

**One opinionated sequencing call:** do **B4/B3** (timeouts + a dedicated bounded executor) **first**.
It's the cheapest change with the largest effect on whether the product survives real concurrent
load, and every other scale item (B7 metrics, B8 circuit breaker, B9 tests) naturally hangs off it.
Tenancy (B6) is the bigger *product* lift and should start in parallel, since it's schema work that
only gets costlier with time.
