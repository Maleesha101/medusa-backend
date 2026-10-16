import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import rate_limit


class FakeRedis:
    def __init__(self):
        self.counts = {}

    def eval(self, script, key_count, key, window_seconds):
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return count, window_seconds


def test_rate_limit_allows_requests_up_to_limit(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: client)

    rate_limit.consume_rate_limit(key="test:user:1", limit=2, window_seconds=60)
    rate_limit.consume_rate_limit(key="test:user:1", limit=2, window_seconds=60)


def test_rate_limit_returns_429_after_limit(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: client)
    rate_limit.consume_rate_limit(key="test:user:1", limit=1, window_seconds=60)

    with pytest.raises(HTTPException) as error:
        rate_limit.consume_rate_limit(key="test:user:1", limit=1, window_seconds=60)

    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "60"


def test_rate_limit_keys_are_independent(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: client)

    rate_limit.consume_rate_limit(key="test:user:1", limit=1, window_seconds=60)
    rate_limit.consume_rate_limit(key="test:user:2", limit=1, window_seconds=60)


def test_rate_limit_fails_closed_when_redis_is_unavailable(monkeypatch):
    class BrokenRedis:
        def eval(self, *args):
            raise RedisConnectionError("connection refused")

    monkeypatch.setattr(rate_limit, "_get_redis_client", lambda: BrokenRedis())

    with pytest.raises(HTTPException) as error:
        rate_limit.consume_rate_limit(key="test:user:1", limit=2, window_seconds=60)

    assert error.value.status_code == 503
