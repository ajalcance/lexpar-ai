# Backend image for the LexPar AI FastAPI service.
# Build context is ./backend (see .github/workflows/ci.yml docker-build).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Schema is owned by Alembic; run `alembic upgrade head` before/at deploy, then serve.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
