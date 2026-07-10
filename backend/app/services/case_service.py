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
from app.models.court import Court
from app.models.user import User
from app.schemas.case import CaseCreate


def create_case(db: DbSession, user: User, data: CaseCreate) -> Case:
    # §13: when a court is named it must be a real, active one — a case grounded in a
    # nonexistent/retired forum would silently produce ungrounded sessions later.
    if data.court_id is not None:
        court = db.scalar(
            select(Court).where(
                Court.id == data.court_id,
                Court.is_active.is_(True),
                Court.deleted_at.is_(None),
            )
        )
        if court is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown or inactive court.",
            )
    case = Case(
        user_id=user.id,
        title=data.title,
        case_facts=data.case_facts,
        court_id=data.court_id,
    )
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
