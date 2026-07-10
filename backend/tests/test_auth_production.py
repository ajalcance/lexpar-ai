"""
File: tests/test_auth_production.py
Purpose: Tests for real (production) auth — bcrypt registration + login-against-hash, wrong password
    and duplicate-email rejection, and that the stub demo path is gated off in production mode.
Depends on: pytest, fastapi TestClient, app.services.auth_service
"""

import pytest

from app.config import get_settings
from app.security_password import hash_password, verify_password


@pytest.fixture()
def production_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_mode", "production")


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"  # not plaintext
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong", h) is False
    assert verify_password("anything", None) is False  # stub user (NULL hash) can't log in


def test_register_then_login(client, production_mode):
    reg = client.post(
        "/api/auth/register",
        json={"email": "Attorney@Firm.com", "password": "s3curepassword", "firm_name": "Firm LLP"},
    )
    assert reg.status_code == 201
    assert reg.json()["access_token"]

    ok = client.post(
        "/api/auth/login", json={"username": "attorney@firm.com", "password": "s3curepassword"}
    )
    assert ok.status_code == 200  # email is normalized (case-insensitive)

    token = ok.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "attorney@firm.com"


def test_wrong_password_and_duplicate(client, production_mode):
    client.post("/api/auth/register", json={"email": "a@b.com", "password": "password123"})
    bad = client.post("/api/auth/login", json={"username": "a@b.com", "password": "nope"})
    assert bad.status_code == 401
    dup = client.post("/api/auth/register", json={"email": "a@b.com", "password": "password123"})
    assert dup.status_code == 409


def test_short_password_rejected(client, production_mode):
    resp = client.post("/api/auth/register", json={"email": "c@d.com", "password": "short"})
    assert resp.status_code == 422  # min_length=8


def test_registration_disabled_in_stub_mode(client):
    # Default conftest mode is stub — registration must be off so the two paths can't mix.
    resp = client.post("/api/auth/register", json={"email": "x@y.com", "password": "password123"})
    assert resp.status_code == 404
