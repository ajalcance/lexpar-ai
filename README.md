# LexPar AI

**Voice-immersive courtroom rehearsal for trial lawyers.** An attorney argues aloud; an AI
**Opposing Counsel** interrupts in real time with spoken objections; an AI **Judge** rules from the
bench and delivers a scored verdict — all as live, bidirectional voice.

Built for the **AMD Developer Hackathon — Act II** (Track 3 · Unicorn).

---

## For judges & reviewers

| | |
|---|---|
| 🎥 **Demo video** | _<!-- paste the submission video URL here -->_ |
| 🌐 **Live app** | **https://165-245-129-142.sslip.io/login** — runs on an AMD Instinct MI300X |
| 🔑 **Credentials** | Provided with the submission (self-service registration is disabled on the public deploy) |

**60-second walkthrough (no legal knowledge needed):** log in → open the case → **Start session**.
The session page shows a **read-aloud script on the left** — just read each line into your mic.
Opposing Counsel objects mid-sentence ("Objection — assumes facts") → the Judge rules from the
bench (the script's baits alternate overruled/sustained so you see both) → **End session** → get a
spoken closing ruling + a 0–100 scorecard with a per-criterion performance breakdown.

**Where to look in the code:**
- The AMD MI300X self-host runbook + LLM routing → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §7, §10.5
- The real-time voice loop (STT → objection → ruling) → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §6 / §6.5
- The bespoke 3-tier objection engine → [`agents/objection_classifier.py`](agents/objection_classifier.py)
- The LiveKit voice worker (the hard part) → [`agents/main.py`](agents/main.py)

---

## 🔴 The AMD centerpiece

**Every LLM call in LexPar runs on AMD Instinct hardware** — directly on the MI300X we self-host, or
through Fireworks AI, which serves its models on AMD MI300X accelerators. There is no non-AMD
inference anywhere in the product.

**Opposing Counsel's reasoning model runs entirely on AMD hardware** —
**Qwen2.5-72B-Instruct** (72B params) self-hosted on an **AMD Instinct MI300X (192 GB HBM3)** via
**vLLM on ROCm**. Not a demo shim: the *same production code path* drives it. LLM routing is a config
switch, not a code fork — flipping one environment variable (`OPPOSING_COUNSEL_LLM_PROVIDER`) moves
Opposing Counsel between cloud inference and the on-box MI300X, with a one-line rollback.

**Verified under load** (AMD Developer Cloud droplet, 2026-07-11): `rocm-smi` showed **100% GPU
utilization and ~174 GB VRAM resident** during generation.

| Role | Model | Runs on |
|------|-------|---------|
| **Opposing Counsel** (real-time reasoning) | **Qwen2.5-72B-Instruct** | **AMD Instinct MI300X — self-hosted (vLLM / ROCm)** |
| Judge (rulings, structured JSON) | gpt-oss-120B | Fireworks AI (served on AMD MI300X) |
| Verification (anti-hallucination) | gpt-oss-120B | Fireworks AI (served on AMD MI300X) |
| Objection classifier | gpt-oss-120B | Fireworks AI (served on AMD MI300X) |
| Embeddings (case + rule-document RAG) | nomic-embed-text-v1.5 | Fireworks AI (served on AMD MI300X) |

All endpoints are OpenAI-compatible — which is exactly why the MI300X cutover is a config change, not
a rewrite. Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §7 (routing), §10.5 (MI300X runbook).

**Deployment hardware (AMD Developer Cloud droplet):** AMD Instinct MI300X · 192 GB HBM3 (CDNA3 /
gfx942, ROCm) · 20 vCPU · 235 GB RAM · 697 GB NVMe · Ubuntu 24.04 LTS.

---

## What makes it novel

- **Real-time objection engine** — a bespoke **3-tier objection classifier**: a regex gate fires
  clear objections (leading/hearsay) with *zero model latency*, and an LLM judges the ambiguous
  ones. Objections are **proceeding-type-aware** (e.g. hearsay is ineligible in oral argument).
- **Streaming sentence-level verification** — every spoken sentence is checked for fabricated legal
  citations and contradictions against a structured session memory *before it's voiced*. Cut
  time-to-first-audio ~50% vs. verify-everything-then-speak.
- **Dual-corpus grounding + citation provenance** — separate RAG over the uploaded pleading and the
  official court rules (verbatim, never paraphrased), with a per-ruling audit trail of exactly which
  passages each ruling cited.
- **Structured session memory** — a live ledger of established facts + objection rulings, so the
  agents reason over *what's on the record*, not the raw transcript.

---

## Stack

**Frontend** — React 18 + TypeScript (Vite) · Tailwind + shadcn/ui · Zustand · TanStack Query ·
`@livekit/components-react` (real-time WebRTC audio + live visualizer) · static bundle via nginx.

**Backend** — FastAPI (Python 3.11) over a service layer · PostgreSQL 16 (SQLAlchemy + Alembic) ·
Pydantic at every boundary · bcrypt + JWT auth, scoped service-token for the agent worker,
first-registrant → admin bootstrap · MinIO (S3-compatible) for pleadings & rule PDFs.

**Real-time voice pipeline** — LiveKit (self-hosted, open-source WebRTC media server) + LiveKit
Agents worker · Deepgram streaming STT (nova-3) · ElevenLabs TTS (distinct voices for Opposing
Counsel vs. Judge) · Silero VAD + LiveKit turn detection · full-duplex barge-in, with the Judge
joining the room as a separate voice participant.

**LLM inference** — an OpenAI-compatible routing layer (see the table above) spanning the
self-hosted MI300X and Fireworks AI.

**Infra / DevOps** — Docker Compose (frontend · backend · agents · Postgres · MinIO · LiveKit · vLLM)
· Caddy 2 reverse proxy (automatic HTTPS/WSS via Let's Encrypt) · GitHub Actions CI (lint,
type-check, tests, image smoke-build) · deployed from a pinned Git commit, secrets generated on-box.

**Monorepo:** `frontend/` (React) · `backend/` (FastAPI) · `agents/` (LiveKit voice worker) ·
`infra/` (Docker/Caddy) · `docs/` (architecture, guidelines).

---

## Local development

The same stack runs locally in Docker (all models route to Fireworks — the AMD self-host is a
droplet-only config switch, so local dev is unaffected):

```bash
cp .env.example .env   # fill in your API keys
docker compose -f infra/docker-compose.yml up
```

- Frontend: http://localhost:5173 · Backend API: http://localhost:8000

More: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/DEVELOPER_GUIDELINES.md`](docs/DEVELOPER_GUIDELINES.md)

## Auth

Real bcrypt password authentication. On the public deployment, self-service registration is gated
(`ALLOW_REGISTRATION`) and login is rate-limited; the reviewer account ships with the submission.
There is no demo bypass — the legacy `admin`/`admin` stub was removed at the production cutover.

## License

[MIT](LICENSE) © 2026 Albert Alcance.
