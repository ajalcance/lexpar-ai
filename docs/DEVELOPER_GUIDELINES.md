# LexPar AI — Developer Guidelines

**Status:** Living document. Pairs with `docs/ARCHITECTURE.md` (what we're building) and
`CLAUDE.md` (pointer file for AI-assisted sessions). This document is the "how we build it" —
apply it to every file, whether written by a human or by Claude Code.

---

## 1. Core principles

1. **Readability over cleverness.** Code is read far more often than it's written. If a
   reviewer (human or AI) needs to pause to decode intent, simplify it.
2. **One responsibility per file.** A file should do one thing well enough that its purpose
   fits in a single sentence.
3. **Explicit over implicit.** No hidden magic, no "clever" metaprogramming that saves five
   lines but costs ten minutes of comprehension.
4. **Security and compliance readiness are default-on**, not a phase-two concern. We are not
   fully implementing every control for the hackathon — but nothing we build now should have
   to be torn out later to add them.
5. **Small, composable pieces beat monoliths.** Every rule below is really a variation on this
   one.

---

## 2. File size & modularity

- **Target:** 150–300 lines per file.
- **Hard signal to split:** if a file crosses ~400 lines, stop and split it before continuing.
- **The smell test:** if you can't describe what a file does in one sentence without using
  "and," it's doing too much.

Concrete splitting patterns for this codebase:

| Layer | Don't | Do |
|---|---|---|
| FastAPI | One `routes.py` with everything | `api/cases.py` (routes, thin) → calls → `services/case_service.py` (logic) → uses → `models/case.py` (DB shape) |
| React | A 600-line `SparringRoom.tsx` | `SparringRoom.tsx` (layout) + `hooks/useSparringSession.ts` (state/logic) + smaller subcomponents |
| Agents | Prompt text inline inside `opposing_counsel.py` | Logic in `opposing_counsel.py`, prompt text in `prompts/opposing_counsel.md` |

Splitting by responsibility, not by line count for its own sake — a 350-line file that does one
coherent thing is fine; a 150-line file doing three unrelated things is not.

---

## 3. File header convention (mandatory on every file)

Every file starts with a short header. This is not decoration — it's the fastest way for the
next person (or the next Claude Code session) to know whether this file is relevant to the task
at hand, without reading the whole thing.

**Python:**
```python
"""
File: app/api/cases.py
Purpose: REST endpoints for uploading, listing, and retrieving case files.
Depends on: services/case_service.py, models/case.py
Related: frontend/src/pages/CaseUpload.tsx (the UI that calls this)
Security notes: All routes require a valid bearer token. Uploaded case_facts
    content is attorney work product — never log it in plaintext.
"""
```

**TypeScript / React:**
```typescript
/**
 * File: src/pages/CaseUpload.tsx
 * Purpose: Lets an attorney upload case facts/documents to start a new case.
 * Depends on: lib/api.ts (upload endpoint), store/auth.ts (bearer token)
 * Related: backend/app/api/cases.py (the API this calls)
 */
```

Include a `Security notes:` line whenever a file touches auth, case data, or transcripts —
even a one-liner. Omit it when genuinely not applicable (a pure UI layout component, for
instance).

---

## 4. Naming conventions

- **Python:** `snake_case` for files, functions, variables. `PascalCase` for classes.
- **TypeScript:** `camelCase` for functions/variables, `PascalCase` for components and types,
  `PascalCase.tsx` for component filenames, `camelCase.ts` for utility filenames.
- **Shared vocabulary, no drift.** `case`, `session`, `transcript`, `scorecard` mean the same
  thing in the database, the API, and the UI. Don't let "session" become "hearing" in one layer
  and "matter" in another — a single vocabulary is what lets anyone (or any AI session) move
  between frontend, backend, and agents without translating terms in their head.

---

## 5. Type safety

- TypeScript: `strict` mode on. No implicit `any`.
- Python: type hints on every function signature. Pydantic models at every API boundary —
  request and response shapes are never raw dicts.
- A Pydantic schema and a SQLAlchemy model are **not the same thing** and should not be
  conflated — the API's request/response shape can (and often should) differ from the DB shape.

---

## 6. Testing baseline

Tests are the guardrail that makes AI-assisted development safe to move fast with — they catch
a plausible-looking but wrong change before it ships, which matters more here than in
hand-written code, not less.

- **Backend:** pytest. Minimum coverage: auth checks, session state transitions, scorecard
  generation logic.
- **Frontend:** Vitest + React Testing Library for the critical flows — login, case upload,
  scorecard display.
- **Agents — highest priority to test:** `objection_classifier.py` in isolation. Feed it sample
  attorney transcripts (leading questions, hearsay, clean statements) and assert it fires or
  doesn't fire correctly. This is your bespoke logic and the piece most likely to regress
  silently if untested.

---

## 7. Security-by-design (hackathon scope, production posture)

We are not building a compliance program this week. We are making sure nothing we build this
week has to be undone to build one later.

- Every endpoint requires a bearer token. Auth is real bcrypt password auth (register +
  login-against-hash); the legacy `admin`/`admin` stub was removed at the production cutover.
- Input validation via Pydantic on every request, no exceptions.
- Secrets live in environment variables only. `.env` is gitignored; `.env.example` documents
  the shape with no real values.
- Never log case facts, transcripts, or scorecard content in plaintext application logs.
  Log identifiers (`case_id`, `session_id`), not content.
- Least privilege: API keys and DB roles scoped to what a service actually needs, not broad
  admin credentials reused everywhere.
- **Admin bootstrap is first-login, UI-native (§13):** on a deployment with no active admin, the
  FIRST user to authenticate (login or register) is promoted to admin automatically — one atomic
  conditional UPDATE in `auth_service.ensure_admin_bootstrap`, a no-op forever after the first
  active admin exists (it can never escalate anyone on a bootstrapped deployment). Consequence:
  **Court and rule-document setup is a pure UI workflow** — log in → `/admin` → create the Court →
  upload the official PDFs. No script or CLI is ever part of the normal operator path
  (`scripts/seed_court.py` remains only as optional CI/headless-automation tooling).
- Design sensitive columns (`cases.case_facts`, `transcripts.content`) as if field-level
  encryption is coming — don't build anything that would make adding it later a schema
  migration nightmare (e.g., don't scatter raw text access across a dozen unrelated queries).
- No direct production database access outside of tracked migrations.

---

## 8. Compliance-readiness (not implementing now, but not blocking later)

- **Data residency:** note where data physically lives (AMD Developer Cloud region, object
  storage region) in `ARCHITECTURE.md` once decided — attorneys will ask.
- **Retention:** use soft deletes (`deleted_at` column) instead of hard deletes from the start.
  Enforcing an actual retention policy later becomes a query change, not a schema change.
- **Sensitive-field tagging:** mark PII/privileged fields with a consistent code comment
  (`# SENSITIVE: attorney work product`) so a future audit can grep for them instead of
  re-reading the whole schema.
- **AI disclosure:** voice-AI-specific regulation is actively developing (the EU's general-purpose
  AI obligations are a relevant example). Not urgent for the hackathon, but flag in
  `ARCHITECTURE.md` §11 as a roadmap item before serving any EU users.
- **Audit trail:** structured logging with a request/session correlation ID from day one, even
  though nothing consumes it yet. Cheap now, painful to retrofit.

---

## 9. Git & workflow conventions

- Branches: `feature/...`, `fix/...`.
- Commits: conventional style — `feat:`, `fix:`, `chore:`, `docs:`.
- Open a PR even solo — reviewing your own diff before merging catches mistakes an in-editor
  view doesn't, and it leaves a clean, auditable history if this ever needs to survive
  due-diligence review.
- CI (lint, type-check, tests) must pass before merge, no exceptions for "it's just a small
  change."

---

## 10. AI-assisted coding practices (Claude Code specific)

- **Keep `ARCHITECTURE.md` and `CLAUDE.md` current.** A stale architecture doc doesn't just fail
  to help an AI session — it actively misleads it.
- **Descriptive names over abbreviations.** This isn't just a human-readability rule — a
  well-named function is context an AI session doesn't have to re-derive from usage.
- **Small files reduce the context an AI needs per task**, which directly improves how
  reliably it can make correct, contained edits instead of guessing at scope.
- **Docstrings and type hints double as inline context** for Claude Code — treat them as part
  of the interface, not optional polish.
- **Match subagents to these module boundaries** (frontend / backend / agents / infra) — this
  guidelines doc is what keeps each subagent's output consistent with the others.
- **Prompt text lives in its own files, loaded through the prompt registry** — never inline in
  Python. **Every** LLM prompt (personas AND sub-task system/instruction prompts: objection
  classifier, quick ruling, session assessment, consistency verifier, pleading summarizer) is one
  `.md` file, loaded via `agents/prompts.py` (`prompts.render(name, **vars)`) in the worker, or its
  twin `backend/app/prompts/prompt_loader.py` in the backend. The two are **separate loaders, no
  shared import** — the packages deploy independently. Rules:
  - **One `.md` per prompt**; the registry reads once and caches for the process lifetime (immutable
    during a run; a deploy restarts and re-reads). The worker calls `prompts.warm_cache()` at startup
    so no live-path call does file I/O mid-session.
  - **Templating is `string.Template` (`$name`), never `str.format`** — several prompts contain
    literal JSON braces (`{"ruling": …}`) that `str.format` would choke on; `$`-placeholders leave
    `{}` untouched. Escape a literal `$` as `$$`. Static prompts are returned verbatim (no
    substitution).
  - **Byte-identity is enforced by golden tests** (`agents/tests/test_prompts.py`,
    `backend/tests/test_prompts.py`) — any prompt file that drifts by a byte fails CI. A *deliberate*
    wording change is made by updating the golden alongside it (that's the review signal that model
    behavior is intended to change).
  - **Safety boundary (immutable constraints):** the no-fabrication / never-invent-case-law
    constraint sections are each prompt file's immutable region. `render()` **never** accepts
    constraint text as a parameter — a future user-customization layer may substitute only
    style/persona `**variables`, so it structurally cannot reach a constraint. The real enforcement
    stays code-side (`citation_check` + fail-safe defaults), independent of any prompt. (See LESSONS.)

---

## 11. Stack-specific conventions

### Frontend (React + TypeScript)
- One component per file; colocate its types.
- No business logic inside components — components call into `lib/api.ts`, they don't contain
  fetch logic or data transformation themselves.
- Hooks in `hooks/`, shared state in `store/`.
- Tailwind utility classes + shadcn/ui primitives only — no ad hoc CSS files.

#### Design system — the color theme (use these, don't invent new hues)
The UI runs on **two accent roles** plus the neutral `primary`/`muted`/`border` tokens. Reach for
an accent only when it carries meaning; default to neutral. Alpha tints (`/5`, `/30`) adapt to dark
mode automatically — prefer them over solid fills.

- **Blue (`blue-500`) = a primary user ACTION** — "do this here." At most one per screen.
  - Accented card recipe: `border border-blue-500/30 border-l-4 border-l-blue-500 bg-blue-500/5 shadow-sm`
    (see the Start-a-sparring card in `CaseDetail.tsx`, the Create-a-court card in `Admin.tsx`).
  - Primary link text: `text-blue-600 underline underline-offset-2 dark:text-blue-500`.
- **Amber (`amber-500`) = judge / reviewer / announcement / INFO highlight** — anything the reader
  should notice but not act on. Reserve it for callouts.
  - Panel recipe: `border border-amber-500/30 bg-muted/30` with an amber eyebrow
    (`text-xs font-medium uppercase text-amber-600 dark:text-amber-500`) — see `DemoScript.tsx`,
    `DashboardGuide.tsx`, the "matter before the court" banner, the "Start here" badge.
- **Speaker / role identity** (transcript, visualizer, scorecard) is a fixed mapping — keep it:
  **blue = You (attorney)**, **red (`red-500`) = Opposing Counsel**, **amber = Judge**. (Amber does
  double duty as the judge color and the info-highlight color — intentional; the bench is the
  authoritative/informational voice.)
- **Score bands** (`ScoreDial`, criteria bars): green ≥ 75, amber 50–74, red < 50.

Rule of thumb: neutral by default; **blue** for the one action you want taken; **amber** for
information/aids; **red** only for destructive/error or the OC role. Don't add a new accent hue —
extend these.

### Backend (FastAPI)
- Routes stay thin: parse request → call a service function → return response. If a route
  handler has business logic in it, that logic belongs in a service module instead.
- Pydantic schema ≠ SQLAlchemy model — keep the API shape and the DB shape as separate,
  intentional decisions.
- DB sessions via dependency injection, never a module-level global connection.

### Agents (LiveKit)
- One file per persona (`opposing_counsel.py`, `judge.py`).
- Prompts in `agents/prompts/*.md`, loaded via the `prompts.py` registry (`prompts.render`) —
  never inlined in logic files (see §10 for the full convention + safety boundary).
- `objection_classifier.py` stays isolated and independently testable — it's the module most
  likely to need rapid iteration as you tune interruption behavior.

---

## 12. Checklist before merging any file

- [ ] File has a header comment explaining its purpose
- [ ] File is under ~300 lines, or has a documented reason not to be
- [ ] No secrets or hardcoded credentials
- [ ] No sensitive data (case facts, transcripts) in log statements
- [ ] Types/schemas defined at every boundary
- [ ] Tests exist for new business logic
