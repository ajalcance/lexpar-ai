"""
File: app/services/embedding_service.py
Purpose: Turn text into embedding vectors for the Case Knowledge Base (§12), via Fireworks'
    OpenAI-compatible embeddings endpoint (verified available: nomic-embed-text-v1.5, 768-dim).
    Also the pure cosine-similarity ranking used at retrieval time (embeddings are stored as JSON
    arrays, ranked in Python — see models/case_document.py).
Depends on: openai (Fireworks), math (stdlib); app/config.py
Related: app/services/case_knowledge_service.py
Security notes: Sends pleading text to the configured embeddings endpoint only; never logged.
"""

from __future__ import annotations

import math

from app.config import get_settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Live call to the Fireworks embeddings endpoint."""
    if not texts:
        return []
    from openai import OpenAI  # imported lazily so unit tests that inject an embedder need no dep

    settings = get_settings()
    client = OpenAI(base_url=settings.embedding_endpoint, api_key=settings.fireworks_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in resp.data]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors. Pure."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def top_k(query: list[float], candidates: list[tuple[str, list[float]]], k: int) -> list[str]:
    """Return the `k` candidate texts whose embeddings are most cosine-similar to `query`. Pure —
    brute force is trivial at case scale (~100 chunks); pgvector is the scale-up path (§12)."""
    scored = [(cosine_similarity(query, emb), text) for text, emb in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [text for _score, text in scored[:k]]
