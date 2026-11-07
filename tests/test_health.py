from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready_when_database_responds(client: TestClient) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_503_when_database_fails(client: TestClient) -> None:
    def unavailable_database():
        class UnavailableSession:
            def execute(self, statement):
                raise SQLAlchemyError("database unavailable")

            def close(self):
                pass

        yield UnavailableSession()

    from app.main import app

    app.dependency_overrides[get_db] = unavailable_database
    try:
        response = client.get("/api/v1/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Required dependency unavailable"}


def test_cors_allows_configured_frontend_origin(client: TestClient) -> None:
    response = client.get(
        "/api/v1/live",
        headers={"Origin": "http://localhost:8080"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_cors_does_not_allow_unknown_origin(client: TestClient) -> None:
    response = client.get(
        "/api/v1/live",
        headers={"Origin": "http://localhost:9999"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
