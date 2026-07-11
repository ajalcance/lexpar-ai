"""
File: app/security_password.py
Purpose: Password hashing for real auth (the only auth mode, ARCHITECTURE §12) — bcrypt, used
    directly. (We deliberately do NOT use passlib: passlib 1.7.4's import-time self-test is
    incompatible with bcrypt >= 5.0 and raises on any hash — see docs/LESSONS.md.) Isolated so the
    algorithm/cost is one place and the auth service depends on `hash_password`/`verify_password`.
Depends on: bcrypt
Related: app/services/auth_service.py, app/models/user.py (password_hash column)
Security notes: Never log passwords or hashes. bcrypt hashes a max of 72 bytes, so passwords are
    truncated to 72 bytes before hashing/verifying (standard bcrypt practice); the min-length floor
    is enforced at the schema boundary.
"""

from __future__ import annotations

import bcrypt

_MAX_BCRYPT_BYTES = 72


def _prepared(plaintext: str) -> bytes:
    return plaintext.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash for storage. Raises on an empty password (never hash nothing)."""
    if not plaintext:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(_prepared(plaintext), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, hashed: str | None) -> bool:
    """Constant-time bcrypt verify. False for a missing/malformed hash — a stub user (NULL hash)
    can never log in under production auth, and a bad hash denies rather than raising."""
    if not hashed or not plaintext:
        return False
    try:
        return bcrypt.checkpw(_prepared(plaintext), hashed.encode("utf-8"))
    except ValueError:
        return False
