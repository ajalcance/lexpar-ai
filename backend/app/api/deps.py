"""
File: app/api/deps.py
Purpose: Shared route dependencies that make resource-ownership checks STRUCTURAL instead of
    by-convention. `get_owned_case` resolves the {case_id} path parameter to a Case owned by the
    authenticated user (404 otherwise) — a route that depends on it cannot forget the ownership
    check, closing the IDOR-by-omission gap flagged in docs/AUDIT_REPORT.md (A6). Phase 3
    (organizations) will widen this same dependency to org scoping in ONE place.
Depends on: fastapi, app/security.py, app/db.py, app/services/case_service.py
Related: app/api/cases.py (the consumer), docs/AUDIT_REPORT.md §2 A6 / §3 B6
Security notes: Composes get_current_user, so an invalid token still 401s before any DB read.
    The 404 (not 403) on foreign cases deliberately does not reveal that the id exists.
"""

import uuid

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models.case import Case
from app.models.user import User
from app.security import get_current_user
from app.services import case_service


def get_owned_case(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Case:
    """Resolve {case_id} to a case owned by the authenticated user, or raise 404."""
    return case_service.get_case(db, current_user, case_id)
