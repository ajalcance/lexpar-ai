# LexPar AI — CLAUDE.md

LexPar AI is a voice-immersive courtroom rehearsal platform: an attorney argues aloud against
an AI Opposing Counsel (which can interrupt with objections) and an AI Judge that delivers a
spoken ruling and written scorecard. Built for the AMD Developer Hackathon, architected to
survive past it.

Monorepo layout: `frontend/` (React + TypeScript, Vite), `backend/` (FastAPI REST API),
`agents/` (LiveKit Agents worker running the real-time STT → LLM → TTS voice pipeline,
including the bespoke `objection_classifier.py`), `infra/` (docker-compose for local/prod).
The Opposing Counsel's LLM backend (Fireworks vs. self-hosted vLLM on AMD MI300X) is a config
switch, not a code fork. Full details, system diagram, API routes, DB schema, and env vars:
see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Build standard: readability over cleverness, one responsibility per file (~150–300 lines,
split past ~400), every file gets a header comment (Purpose/Depends on/Related/Security
notes), strict typing (TypeScript strict mode, Python type hints + Pydantic at every
boundary), and security-by-design even at hackathon scope (bearer auth on every endpoint,
no secrets or sensitive data in logs, soft deletes). Full conventions, testing baseline, and
the pre-merge checklist: see [docs/DEVELOPER_GUIDELINES.md](docs/DEVELOPER_GUIDELINES.md).

**Known placeholder:** auth is currently stubbed (`admin`/`admin`, `AUTH_MODE=stub`) — must
not touch real attorney or case data until replaced (tracked in ARCHITECTURE.md §11).

Keep this file, `docs/ARCHITECTURE.md`, and `docs/DEVELOPER_GUIDELINES.md` in sync as the
project evolves — a stale doc actively misleads future sessions.
