import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import rate_limit
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import User  # noqa: F401 - ensure metadata is registered


class FakeRedis:
    """Per-test Redis substitute for deterministic API tests."""

    def __init__(self):
        self.counts = {}

    def eval(self, script, key_count, key, window_seconds):
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return count, window_seconds


@pytest.fixture(autouse=True)
def fake_redis_for_tests(monkeypatch):
    monkeypatch.setattr(rate_limit, "_get_redis_client", FakeRedis)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(session_factory) -> TestClient:
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
