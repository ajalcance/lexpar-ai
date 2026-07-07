"""
File: app/services/case_service.py
Purpose: Case business logic — create, list, and fetch cases, always scoped to the owning
    attorney and excluding soft-deleted rows.
Depends on: fastapi, sqlalchemy, app/models/case.py, app/schemas/case.py, app/models/user.py
Related: app/api/cases.py
Security notes: All queries filter by user_id (least privilege) so one attorney can never read
    another's cases. case_facts is never logged.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.case import Case
from app.models.user import User
from app.schemas.case import CaseCreate


def create_case(db: DbSession, user: User, data: CaseCreate) -> Case:
    case = Case(user_id=user.id, title=data.title, case_facts=data.case_facts)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_cases(db: DbSession, user: User) -> list[Case]:
    stmt = (
        select(Case)
        .where(Case.user_id == user.id, Case.deleted_at.is_(None))
        .order_by(Case.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_case(db: DbSession, user: User, case_id: uuid.UUID) -> Case:
    stmt = select(Case).where(
        Case.id == case_id, Case.user_id == user.id, Case.deleted_at.is_(None)
    )
    case = db.scalar(stmt)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return case
