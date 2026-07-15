"""
File: app/api/deps.py
Purpose: Shared route dependencies that make resource-ownership checks STRUCTURAL instead of
    by-convention. `get_owned_case` / `get_owned_court` resolve the {case_id}/{court_id} path
    parameter to a resource owned by the authenticated user (404 otherwise) — a route that depends
    on one cannot forget the ownership check, closing the IDOR-by-omission gap flagged in
    docs/AUDIT_REPORT.md (A6/B6). This is the single place per-user scoping is enforced.
Depends on: fastapi, app/security.py, app/db.py, app/services/{case_service,court_service}.py
Related: app/api/cases.py, app/api/courts.py (the consumers), docs/AUDIT_REPORT.md §2 A6 / §3 B6
Security notes: Composes get_current_user, so an invalid token still 401s before any DB read.
    The 404 (not 403) on foreign resources deliberately does not reveal that the id exists.
"""

import uuid

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models.case import Case
from app.models.court import Court
from app.models.user import User
from app.security import get_current_user
from app.services import case_service, court_service


def get_owned_case(
    case_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Case:
    """Resolve {case_id} to a case owned by the authenticated user, or raise 404."""
    return case_service.get_case(db, current_user, case_id)


def get_owned_court(
    court_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Court:
    """Resolve {court_id} to an ACTIVE court owned by the authenticated user, or raise 404.
    (Archived courts are not found here — the purge route fetches archived-inclusive separately,
    still owner-checked, so a retired court stays purgeable.)"""
    return court_service.get_court(db, current_user, court_id)
