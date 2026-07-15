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


# --- No roles: every account is a self-owned island ------------------------------------------

def test_me_has_no_role_field(client, auth_headers):
    # Roles were removed (migration 0009): the user shape carries identity only, no role/admin.
    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert "role" not in me
    assert me["email"] == TEST_EMAIL


def test_second_user_is_an_independent_owner(client, auth_headers):
    # A second signup is just another self-owned account — no privileged first user, no gating.
    second = client.post(
        "/api/auth/register", json={"email": "second@example.com", "password": TEST_PASSWORD}
    )
    assert second.status_code == 201
    headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == "second@example.com"
    assert "role" not in me


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


def test_auth_rate_limit_returns_429_after_burst(client):
    # 10/minute per client: the 11th attempt inside the window is refused, and the limit applies
    # to bad-password brute force (the whole point — the demo admin creds are handed out).
    _register(client)
    for _ in range(9):  # register consumed 1 of the 10
        client.post("/api/auth/login", json={"username": TEST_EMAIL, "password": "wrong-pass"})
    resp = client.post(
        "/api/auth/login", json={"username": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 429
    assert "Too many attempts" in resp.json()["detail"]


def test_rate_limiter_window_slides_with_fake_clock():
    from app.rate_limit import SlidingWindowLimiter

    now = {"t": 0.0}
    limiter = SlidingWindowLimiter(limit=2, window_s=60.0, clock=lambda: now["t"])
    assert limiter.allow("ip") and limiter.allow("ip")
    assert not limiter.allow("ip")  # third inside the window
    assert limiter.allow("other")  # independent key
    now["t"] = 61.0
    assert limiter.allow("ip")  # window slid


def test_rate_limit_keys_on_x_forwarded_for(client):
    # Behind Caddy every socket peer is the proxy — the real client is the first XFF entry, so
    # one abuser can't exhaust the shared budget for everyone.
    for i in range(10):
        client.post(
            "/api/auth/login",
            json={"username": "a@b.c", "password": "wrong"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
    blocked = client.post(
        "/api/auth/login",
        json={"username": "a@b.c", "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert blocked.status_code == 429
    other = client.post(
        "/api/auth/login",
        json={"username": "a@b.c", "password": "wrong"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert other.status_code != 429  # different client, own budget
