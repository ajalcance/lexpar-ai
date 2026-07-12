"""
File: tests/test_auth.py
Purpose: Auth-check tests (DEV_GUIDELINES §6) — the bearer check is real: missing/invalid tokens
    are rejected, a registered user's real (bcrypt) credentials succeed, and /me returns the
    authenticated user. (The legacy admin/admin stub path was removed at the production cutover.)
Depends on: pytest, fastapi TestClient (via conftest fixtures)
Related: app/api/auth.py, app/security.py, app/services/auth_service.py
"""

from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def _register(client, email=TEST_EMAIL, password=TEST_PASSWORD):
    resp = client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201
    return resp


def test_health_needs_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_success_returns_token(client):
    _register(client)
    resp = client.post(
        "/api/auth/login", json={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(client):
    _register(client)
    resp = client.post("/api/auth/login", json={"username": TEST_EMAIL, "password": "nope"})
    assert resp.status_code == 401


def test_admin_admin_no_longer_authenticates(client):
    # The stub bypass is gone: admin/admin is just an unknown email → 401, never a login.
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
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
    assert resp.json()["email"] == TEST_EMAIL


def test_protected_route_without_token_is_401(client):
    resp = client.get("/api/cases")
    assert resp.status_code == 401


# --- §13 UI-native admin bootstrap: first login becomes admin ---------------------------------

def test_first_login_promotes_then_second_user_does_not(client, auth_headers, db_session):
    from app.models.user import User
    from app.services import auth_service

    # first authenticated user (the registration behind auth_headers) → admin
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["role"] == "admin"

    # a second, subsequent user does NOT become admin — the guard sees an active admin
    second = User(email="second@example.com", full_name="Second User")
    db_session.add(second)
    db_session.commit()
    auth_service.ensure_admin_bootstrap(db_session, second)
    db_session.refresh(second)
    assert second.role == "attorney"


def test_bootstrap_guard_holds_even_when_precheck_would_pass(db_session):
    # The guard in isolation (the atomic-statement condition, not the caller's state): with an
    # active admin present, calling the bootstrap on an attorney must never promote — this is the
    # exact property that makes the check-then-act race harmless at the statement level.
    from app.models.user import User
    from app.services import auth_service

    admin = User(email="root@example.com", role="admin")
    attorney = User(email="a@example.com")
    db_session.add_all([admin, attorney])
    db_session.commit()

    auth_service.ensure_admin_bootstrap(db_session, attorney)
    db_session.refresh(attorney)
    assert attorney.role == "attorney"


def test_bootstrap_ignores_soft_deleted_admins(db_session):
    # A deployment whose only admin was soft-deleted is admin-LESS — the next login must be able
    # to bootstrap, or the instance is permanently locked out of /admin.
    from datetime import datetime, timezone

    from app.models.user import User
    from app.services import auth_service

    gone = User(email="gone@example.com", role="admin", deleted_at=datetime.now(timezone.utc))
    fresh = User(email="fresh@example.com")
    db_session.add_all([gone, fresh])
    db_session.commit()

    auth_service.ensure_admin_bootstrap(db_session, fresh)
    db_session.refresh(fresh)
    assert fresh.role == "admin"


def test_bootstrap_is_idempotent_across_repeat_logins(client, auth_headers):
    # Logging in again (same user, already admin) is a no-op, not an error.
    again = client.post(
        "/api/auth/login", json={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert again.status_code == 200
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["role"] == "admin"


def test_register_gate_blocks_signup_but_not_login(client, monkeypatch):
    # ALLOW_REGISTRATION=false (public deployment with accounts provisioned): the unauthenticated
    # register route closes — but existing accounts still log in.
    from app.config import get_settings

    _register(client)  # provision the account while registration is open
    monkeypatch.setattr(get_settings(), "allow_registration", False)
    blocked = client.post(
        "/api/auth/register", json={"email": "late@example.com", "password": TEST_PASSWORD}
    )
    assert blocked.status_code == 403
    assert "disabled" in blocked.json()["detail"]
    login = client.post(
        "/api/auth/login", json={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
