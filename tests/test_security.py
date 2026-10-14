from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_verifies_only_matching_password() -> None:
    hashed = hash_password("a-very-long-test-password")

    assert hashed != "a-very-long-test-password"
    assert verify_password("a-very-long-test-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_contains_identity_but_no_role() -> None:
    token, expires_in = create_access_token("42")
    claims = decode_access_token(token)

    assert expires_in == get_settings().access_token_expire_minutes * 60
    assert claims["sub"] == "42"
    assert claims["iss"] == get_settings().token_issuer
    assert "role" not in claims


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "42",
            "iat": datetime.now(UTC) - timedelta(minutes=10),
            "exp": datetime.now(UTC) - timedelta(minutes=5),
            "iss": settings.token_issuer,
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
