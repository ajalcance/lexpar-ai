"""
File: app/services/court_service.py
Purpose: Court catalog logic (§13) — create a court (admin action) and list/fetch active courts
    for the case-creation flow. The rule-corpus ingest/retrieval lives separately in
    court_knowledge_service.py (one responsibility per file).
Depends on: fastapi, sqlalchemy, app/models/court.py, app/schemas/court.py
Related: app/api/courts.py, app/services/court_knowledge_service.py, scripts/seed_court.py
Security notes: Court data is public information; the write path is admin-gated at the route
    (app/security.py require_admin), not here.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.court import Court
from app.schemas.court import CourtCreate


def create_court(db: DbSession, data: CourtCreate) -> Court:
    court = Court(name=data.name, jurisdiction_description=data.jurisdiction_description)
    db.add(court)
    db.commit()
    db.refresh(court)
    return court


def list_active_courts(db: DbSession) -> list[Court]:
    """The catalog the case-creation dropdown shows: active, non-deleted courts."""
    stmt = (
        select(Court)
        .where(Court.is_active.is_(True), Court.deleted_at.is_(None))
        .order_by(Court.name)
    )
    return list(db.scalars(stmt))


def get_court(db: DbSession, court_id: uuid.UUID) -> Court:
    court = db.scalar(
        select(Court).where(Court.id == court_id, Court.deleted_at.is_(None))
    )
    if court is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Court not found.")
    return court
