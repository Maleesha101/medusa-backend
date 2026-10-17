"""Password hashing and signed access-token helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password using the recommended Argon2 configuration."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a candidate password against its stored hash."""
    try:
        return _password_hash.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, auth_version: int = 0) -> tuple[str, int]:
    """Create a short-lived signed token; authorization is loaded from the database."""
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "ver": auth_version,
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "iss": settings.token_issuer,
    }
    token = jwt.encode(claims, settings.auth_secret_key, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature, expiry, issuer, and required subject claim."""
    settings = get_settings()
    claims = jwt.decode(
        token,
        settings.auth_secret_key,
        algorithms=["HS256"],
        issuer=settings.token_issuer,
        options={"require": ["sub", "jti", "iat", "exp", "iss"]},
    )
    if not isinstance(claims.get("sub"), str) or not claims["sub"].isdigit():
        raise jwt.InvalidTokenError("Invalid subject")
    # Tokens issued before auth-version support remain valid at version zero.
    # Once a password reset increments the stored version, those tokens fail.
    if "ver" not in claims:
        claims["ver"] = 0
    if not isinstance(claims.get("ver"), int) or claims["ver"] < 0:
        raise jwt.InvalidTokenError("Invalid authentication version")
    if not isinstance(claims.get("jti"), str) or not claims["jti"]:
        raise jwt.InvalidTokenError("Invalid token identifier")
    return claims
