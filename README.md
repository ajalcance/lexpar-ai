# LexPar AI

Voice-immersive courtroom rehearsal platform for solo and independent trial lawyers. An
attorney speaks their argument aloud against an AI Opposing Counsel that can interrupt
mid-sentence with objections, followed by an AI Judge that delivers a spoken ruling and a
scorecard.

Built for the AMD Developer Hackathon (Unicorn track).

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
model does real GPU inference on the MI300X — under load `rocm-smi` showed **100% GPU utilization
and ~174 GB VRAM resident**. The Fireworks ↔ self-hosted split is a one-line config switch
(`OPPOSING_COUNSEL_LLM_PROVIDER`), so local development runs on Fireworks while the hackathon droplet
self-hosts on AMD. Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §7 (routing) and §10.5
(MI300X self-host runbook).

## Stack

React + TypeScript · FastAPI · LiveKit Agents · Fireworks AI / self-hosted vLLM (AMD MI300X) ·
Deepgram · ElevenLabs · Postgres

- Full architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Coding standards: [`docs/DEVELOPER_GUIDELINES.md`](docs/DEVELOPER_GUIDELINES.md)

## Running locally

```bash
cp .env.example .env   # fill in your API keys
docker compose -f infra/docker-compose.yml up
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

## Status

Hackathon build in progress. Auth is real bcrypt password auth — register the first account via
`POST /api/auth/register` (the first registrant auto-bootstraps to admin). The legacy `admin`/`admin`
stub has been removed. Remaining pre-deploy items are tracked in `docs/ARCHITECTURE.md` §11.

## License

All rights reserved. Private during hackathon build.
