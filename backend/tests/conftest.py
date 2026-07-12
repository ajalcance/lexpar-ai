"""
File: tests/conftest.py
Purpose: Pytest fixtures — an isolated in-memory SQLite database per test (schema built from
    Base.metadata, so no Postgres is needed in CI), a TestClient with get_db overridden onto it,
    and helpers for an authenticated request.
Depends on: pytest, fastapi, sqlalchemy, app/*
Related: tests/test_auth.py, tests/test_sessions.py, docs/DEVELOPER_GUIDELINES.md §6
"""

import os

os.environ.setdefault("AGENT_SERVICE_TOKEN", "test-agent-token")
# JWT_SECRET is required (>= 32 chars) — provide a valid one for the test suite.
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789-abcdefghijklmnop")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session as DbSession  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401  (register models on Base.metadata)
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def db_session() -> DbSession:
    """A fresh in-memory SQLite session, shared (StaticPool) so the app and test see one DB."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does NOT enforce foreign keys by default — a delete-order bug (child rows still
    # referencing a deleted parent) passed the whole suite and then failed live on Postgres
    # (the case-purge ForeignKeyViolation; see LESSONS). Enforce FKs so tests match production.
    @event.listens_for(engine, "connect")
    def _enforce_sqlite_fks(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: DbSession) -> TestClient:
    """TestClient wired to the same in-memory session as the test body."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# Shared test account (real bcrypt auth). Being the first registrant on each fresh in-memory DB,
# this user auto-bootstraps to admin (§13 first-login rule) — the same privilege the old stub user
# had, now via the real registration path.
TEST_EMAIL = "attorney@example.com"
TEST_PASSWORD = "test-password-123"


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """Register the shared test user (real bcrypt) and return a ready-to-use Authorization header.
    First registrant on the fresh DB → admin via the §13 bootstrap."""
    resp = client.post(
        "/api/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "full_name": "Test Attorney"},
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    # The auth limiter is module-global (in-memory, per-process); the suite fires many auth calls
    # well inside one window, so isolate tests from each other — and from the limiter tests.
    from app.rate_limit import auth_limiter

    auth_limiter.reset()
    yield
