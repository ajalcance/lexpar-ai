"""
File: tests/test_auth.py
Purpose: Auth-check tests (DEV_GUIDELINES §6) — the bearer check is real: missing/invalid tokens
    are rejected, admin/admin succeeds, and /me returns the authenticated user.
Depends on: pytest, fastapi TestClient (via conftest fixtures)
Related: app/api/auth.py, app/security.py, app/services/auth_service.py
"""


def test_health_needs_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_success_returns_token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_rejects_malformed_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


def test_me_returns_current_user(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@lexpar.ai"


def test_protected_route_without_token_is_401(client):
    resp = client.get("/api/cases")
    assert resp.status_code == 401
