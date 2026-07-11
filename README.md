# LexPar AI

Voice-immersive courtroom rehearsal platform for solo and independent trial lawyers. An
attorney speaks their argument aloud against an AI Opposing Counsel that can interrupt
mid-sentence with objections, followed by an AI Judge that delivers a spoken ruling and a
scorecard.

Built for the AMD Developer Hackathon (Unicorn track).

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
