# LexPar AI — CLAUDE.md

LexPar AI is a voice-immersive courtroom rehearsal platform: an attorney argues aloud against
an AI Opposing Counsel (which can interrupt with objections) and an AI Judge that delivers a
spoken ruling and written scorecard. Built for the AMD Developer Hackathon, architected to
survive past it.

Monorepo layout: `frontend/` (React + TypeScript, Vite), `backend/` (FastAPI REST API),
`agents/` (LiveKit Agents worker running the real-time STT → LLM → TTS voice pipeline,
including the bespoke `objection_classifier.py`), `infra/` (docker-compose for local/prod).
The Opposing Counsel's LLM backend (Fireworks vs. self-hosted vLLM on AMD MI300X) is a config
switch, not a code fork.

**Reference docs:**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system diagram, API routes, DB schema, env vars.
- [docs/DEVELOPER_GUIDELINES.md](docs/DEVELOPER_GUIDELINES.md) — coding conventions, testing baseline, pre-merge checklist.
- [docs/LESSONS.md](docs/LESSONS.md) — append-only log of past mistakes and their fixes, so they aren't repeated.
- [tasks/PLAN.md](tasks/PLAN.md) — working plan/task log, written before non-trivial work and checked off as it proceeds.

**Known placeholder:** auth is currently stubbed (`admin`/`admin`, `AUTH_MODE=stub`) — must
not touch real attorney or case data until replaced (tracked in ARCHITECTURE.md §11).

**Admin bootstrap:** the first user to authenticate on an admin-less deployment is promoted to
admin automatically (`auth_service.ensure_admin_bootstrap`) — Court/rule-document setup is a pure
UI workflow via `/admin`, never a script (see DEVELOPER_GUIDELINES §7).

**Status:** both agents (Opposing Counsel and Judge) run through Fireworks AI until the AMD
Developer Cloud droplet exists.

**Attribution:** commit and PR attribution for Claude is already disabled via
`.claude/settings.json` — no separate instruction needed here.

Keep this file and the docs above in sync as the project evolves — a stale doc actively
misleads future sessions.

**Self-updating docs:** if a task changes the architecture, introduces a new coding convention,
or produces a lesson worth remembering, update ARCHITECTURE.md, DEVELOPER_GUIDELINES.md, or
LESSONS.md before considering the task done — don't wait to be asked.
