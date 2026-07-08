"""
File: tests/test_config.py
Purpose: Lock in that the app refuses to start with a blank/missing/weak JWT_SECRET (fails loudly)
    instead of silently falling back to a guessable signing key.
Depends on: pytest, pydantic, app/config.py
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_blank_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        Settings(jwt_secret="")


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        Settings(jwt_secret="too-short")


def test_old_insecure_default_is_rejected():
    # The previous hardcoded default was 22 chars — now below the minimum, so it can't be used.
    with pytest.raises(ValidationError):
        Settings(jwt_secret="dev-insecure-change-me")


def test_strong_jwt_secret_is_accepted():
    secret = "x" * 40
    assert Settings(jwt_secret=secret).jwt_secret == secret
