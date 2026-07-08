"""
File: tests/conftest.py
Purpose: Pytest fixtures — an isolated in-memory SQLite database per test (schema built from
    Base.metadata, so no Postgres is needed in CI), a TestClient with get_db overridden onto it,
    and helpers for an authenticated request.
Depends on: pytest, fastapi, sqlalchemy, app/*
Related: tests/test_auth.py, tests/test_sessions.py, docs/DEVELOPER_GUIDELINES.md §6
"""

import os

os.environ.setdefault("AUTH_MODE", "stub")
os.environ.setdefault("AGENT_SERVICE_TOKEN", "test-agent-token")
# JWT_SECRET is required (>= 32 chars) — provide a valid one for the test suite.
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789-abcdefghijklmnop")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
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


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """Log in as the stub user and return a ready-to-use Authorization header."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
