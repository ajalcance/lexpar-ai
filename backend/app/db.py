"""
File: app/db.py
Purpose: SQLAlchemy engine, session factory, declarative Base, and the get_db FastAPI
    dependency. DB sessions are provided via dependency injection only (DEV_GUIDELINES §5),
    never a module-level connection shared across requests.
Depends on: sqlalchemy, app/config.py
Related: app/models/*, app/main.py, tests/conftest.py (overrides get_db with a SQLite session)
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from."""


_settings = get_settings()

# SQLite (used in tests) needs check_same_thread disabled; Postgres ignores connect_args.
_connect_args = (
    {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(_settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[DbSession, None, None]:
    """Yield a request-scoped DB session and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
