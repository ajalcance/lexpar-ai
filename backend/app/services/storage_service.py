"""
File: app/services/storage_service.py
Purpose: Store and fetch uploaded pleadings in S3-compatible object storage (MinIO locally,
    DigitalOcean Spaces in prod) — ARCHITECTURE §8/§12. Keys are `cases/{case_id}/{filename}`.
Depends on: boto3; app/config.py
Related: app/services/case_knowledge_service.py, app/api/cases.py
Security notes: Uploaded pleadings are attorney work product. Use server-side encryption in prod
    (a documented follow-up); never log object contents. Credentials come from settings/env only.
"""

from __future__ import annotations

import boto3
from botocore.config import Config

from app.config import get_settings


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
        region_name=settings.object_storage_region,
        config=Config(signature_version="s3v4"),
    )


def object_key(case_id: str, filename: str) -> str:
    """Deterministic object key for a case's pleading."""
    safe = filename.replace("/", "_").strip() or "pleading"
    return f"cases/{case_id}/{safe}"


def put_object(key: str, data: bytes, content_type: str | None = None) -> str:
    """Upload bytes; return the stored key. Raises on failure (the route surfaces it)."""
    settings = get_settings()
    extra = {"ContentType": content_type} if content_type else {}
    _client().put_object(Bucket=settings.object_storage_bucket, Key=key, Body=data, **extra)
    return key


def get_object(key: str) -> bytes:
    settings = get_settings()
    resp = _client().get_object(Bucket=settings.object_storage_bucket, Key=key)
    return resp["Body"].read()


def delete_object(key: str) -> None:
    """Remove an object — PURGE only (the hard tier of the two-tier deletion design). Archive
    deliberately retains the file. Raises on failure; purge callers treat it as best-effort."""
    settings = get_settings()
    _client().delete_object(Bucket=settings.object_storage_bucket, Key=key)
