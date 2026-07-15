# LexPar AI — CLAUDE.md

> **Reviewers/judges:** this file is internal build guidance for AI coding assistants — start at
> **[README.md](README.md)** (demo, the AMD MI300X story, architecture, how to run it).

LexPar AI is a voice-immersive courtroom rehearsal platform: an attorney argues aloud against
an AI Opposing Counsel (which can interrupt with objections) and an AI Judge that delivers a
spoken ruling and written scorecard. Built for the AMD Developer Hackathon, architected to
survive past it.

Monorepo layout: `frontend/` (React + TypeScript, Vite), `backend/` (FastAPI REST API),
`agents/` (LiveKit Agents worker running the real-time STT → LLM → TTS voice pipeline,
including the bespoke `objection_classifier.py`), `infra/` (docker-compose for local/prod).
The Opposing Counsel's LLM backend (Fireworks vs. self-hosted vLLM on AMD MI300X) is a config
switch, not a code fork.

**UI color theme (keep consistent across new pages):** blue = primary user action, amber =
judge/reviewer/announcement/info highlight, red = OC role / destructive; neutral otherwise. Full
recipes in DEVELOPER_GUIDELINES §11 (Design system).

**Reference docs:**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system diagram, API routes, DB schema, env vars.
- [docs/DEVELOPER_GUIDELINES.md](docs/DEVELOPER_GUIDELINES.md) — coding conventions, testing baseline, pre-merge checklist.
- [docs/LESSONS.md](docs/LESSONS.md) — append-only log of past mistakes and their fixes, so they aren't repeated.
- [tasks/PLAN.md](tasks/PLAN.md) — working plan/task log, written before non-trivial work and checked off as it proceeds.

**Auth:** real bcrypt password auth (register + login-against-hash). The legacy `admin`/`admin`
stub (`AUTH_MODE`) was removed at the production cutover — there is no demo bypass. Create an
account via `POST /api/auth/register` (or the login page's flow). LiveKit dev keys are still a
pre-deploy item (ARCHITECTURE.md §11).

**Single-owner accounts, no roles (migration 0009):** every account is a self-owned island — the
person who signs up owns everything they create (their cases AND their courts/rule corpus) and can
see nothing outside it. There is no admin/attorney distinction. Ownership is structural: every
`{case_id}`/`{court_id}` route resolves through `deps.get_owned_case` / `deps.get_owned_court`.
Court/rule-document setup is a pure UI workflow via `/courts`, never a script (see
DEVELOPER_GUIDELINES §7). Multi-user org accounts + RBAC remain a future, opt-in direction.

**Status:** both agents (Opposing Counsel and Judge) run through Fireworks AI until the AMD
Developer Cloud droplet exists.

**Attribution:** commit and PR attribution for Claude is already disabled via
`.claude/settings.json` — no separate instruction needed here.

Keep this file and the docs above in sync as the project evolves — a stale doc actively
misleads future sessions.

**Self-updating docs:** if a task changes the architecture, introduces a new coding convention,
or produces a lesson worth remembering, update ARCHITECTURE.md, DEVELOPER_GUIDELINES.md, or
LESSONS.md before considering the task done — don't wait to be asked.
