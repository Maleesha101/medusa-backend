"""Redis-backed access-token revocation."""

import time

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core.rate_limit import _get_redis_client

_REVOKED_TOKEN_PREFIX = "auth:revoked:jti:"


def is_access_token_revoked(token_id: str) -> bool:
    """Return whether a token ID is revoked; fail closed if Redis is unavailable."""
    try:
        return bool(_get_redis_client().exists(f"{_REVOKED_TOKEN_PREFIX}{token_id}"))
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
            headers={"Retry-After": "5"},
        ) from exc


def revoke_access_token(token_id: str, expires_at: int) -> None:
    """Revoke a token until its expiry, avoiding persistent denylist entries."""
    ttl = max(1, int(expires_at) - int(time.time()))
    try:
        _get_redis_client().set(
            f"{_REVOKED_TOKEN_PREFIX}{token_id}",
            "1",
            ex=ttl,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
            headers={"Retry-After": "5"},
        ) from exc
