"""Distributed fixed-window rate limiting backed by Redis."""

from functools import lru_cache

from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

# INCR and EXPIRE must be atomic across API replicas.
_INCREMENT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@lru_cache
def _get_redis_client() -> Redis:
    """Return the process-local client; counters themselves remain shared in Redis."""
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def consume_rate_limit(*, key: str, limit: int, window_seconds: int) -> None:
    """Consume one request from a shared fixed window or raise a safe HTTP error.

    Redis errors fail closed: callers do not bypass rate limiting when Redis is
    unavailable. Keys must contain only non-secret identifiers.
    """
    try:
        count, ttl = _get_redis_client().eval(
            _INCREMENT_SCRIPT,
            1,
            key,
            window_seconds,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Submission protection is temporarily unavailable",
            headers={"Retry-After": str(window_seconds)},
        ) from exc

    if int(count) > limit:
        retry_after = max(1, int(ttl))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Submission rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
