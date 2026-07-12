# LexPar AI

Voice-immersive courtroom rehearsal platform for solo and independent trial lawyers. An
attorney speaks their argument aloud against an AI Opposing Counsel that can interrupt
mid-sentence with objections, followed by an AI Judge that delivers a spoken ruling and a
scorecard.

Built for the AMD Developer Hackathon (Unicorn track).

## Live demo

Deployed on the AMD Developer Cloud (MI300X droplet) — the full stack runs in Docker behind Caddy
with automatic TLS:

**→ https://165-245-129-142.sslip.io/login**

Reviewer credentials are provided with the submission (self-service registration is disabled on the
public deployment). Best experienced with a headset mic: you argue aloud and hear Opposing Counsel
object and the Judge rule in real time.

## AMD Compute Usage

**Every LLM call in LexPar's pipeline runs on AMD Instinct hardware** — directly on the MI300X we
self-host, or through Fireworks AI, which serves its models on AMD MI300X accelerators. There is no
non-AMD inference anywhere in the product.

| Role | Model | Runs on |
|------|-------|---------|
| **Opposing Counsel** (real-time reasoning) | Qwen2.5-72B-Instruct | **AMD Instinct MI300X — self-hosted (vLLM / ROCm)** |
| Judge · Verification · Objection classifier | gpt-oss-120B | Fireworks AI (served on AMD MI300X) |
| Embeddings (case + rule-document RAG) | nomic-embed-text-v1.5 | Fireworks AI (served on AMD MI300X) |

**Verified live on the AMD Developer Cloud droplet (2026-07-11):** the self-hosted Opposing Counsel
model does real GPU inference on the MI300X — under load `rocm-smi` showed **100% GPU utilization and
~174 GB VRAM resident**. The Fireworks ↔ self-hosted split is a one-line config switch
(`OPPOSING_COUNSEL_LLM_PROVIDER`), so local development runs on Fireworks while the hackathon droplet
self-hosts on AMD. Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §7 (routing) and §10.5
(MI300X self-host runbook).

## Stack

React + TypeScript · FastAPI · LiveKit Agents (Deepgram STT · ElevenLabs TTS) · Fireworks AI /
self-hosted vLLM on AMD MI300X · Postgres + pgvector · MinIO · Docker / Caddy

- Full architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Coding standards: [`docs/DEVELOPER_GUIDELINES.md`](docs/DEVELOPER_GUIDELINES.md)

## Local development

The same stack runs locally in Docker (all models route to Fireworks — the AMD self-host is a
droplet-only config switch, so local dev is unaffected):

```bash
cp .env.example .env   # fill in your API keys
docker compose -f infra/docker-compose.yml up
```

- Frontend: http://localhost:5173 · Backend API: http://localhost:8000

## Auth

Real bcrypt password authentication. On the public deployment, self-service registration is gated
(`ALLOW_REGISTRATION`) and login is rate-limited; the reviewer account is provided with the
submission. There is no demo bypass — the legacy `admin`/`admin` stub was removed at the production
cutover.

## License

All rights reserved. Private during hackathon build.
