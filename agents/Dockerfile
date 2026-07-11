# Agents worker image for the LexPar AI LiveKit voice pipeline (production deploy only — local
# dev keeps `python agents/main.py dev` on the host).
# Build context is ./agents (see infra/docker-compose.prod.yml).
#
# Installs BOTH requirement sets: requirements.txt (LLM/agent logic, what CI tests) and
# requirements-voice.txt (the heavy livekit-agents + Deepgram/ElevenLabs/Silero media stack that
# is deliberately kept out of CI — see requirements-voice.txt).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements-voice.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-voice.txt

COPY . .

# Prefetch inference model files (Silero VAD, local turn detector) into the image so a worker
# restart on the droplet never re-downloads them at job start.
RUN python main.py download-files

# `start` = livekit-agents production mode (no dev hot-reload). The worker registers with the
# LiveKit server named by LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET and joins rooms as
# sessions are created.
CMD ["python", "main.py", "start"]
