"""
File: app/api/cases.py
Purpose: Case routes — create, list, and fetch cases for the authenticated attorney.
Depends on: fastapi, app/services/case_service.py, app/security.py, app/schemas/case.py
Related: docs/ARCHITECTURE.md §5, frontend Dashboard.tsx / CaseUpload.tsx
Security notes: Every route requires a bearer token; the service scopes all data to current_user.
    Document upload to object storage is deferred — case_facts is JSON only for now.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models.user import User
from app.schemas.case import CaseCreate, CaseOut
from app.security import get_current_user
from app.services import case_service

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CaseOut:
    return case_service.create_case(db, current_user, payload)


@router.get("", response_model=list[CaseOut])
def list_cases(
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[CaseOut]:
    return case_service.list_cases(db, current_user)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> CaseOut:
    return case_service.get_case(db, current_user, case_id)
