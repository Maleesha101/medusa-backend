from fastapi.testclient import TestClient


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready_when_database_responds(client: TestClient) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
