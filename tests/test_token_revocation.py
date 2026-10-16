from fastapi.testclient import TestClient


def test_logout_revokes_current_access_token(client: TestClient) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@example.com",
            "password": "a-very-long-test-password",
        },
    )
    assert registered.status_code == 201

    issued = client.post(
        "/api/v1/auth/token",
        data={
            "username": "logout@example.com",
            "password": "a-very-long-test-password",
        },
    )
    assert issued.status_code == 200
    token = issued.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logged_out = client.post("/api/v1/auth/logout", headers=headers)
    assert logged_out.status_code == 204

    rejected = client.get("/api/v1/auth/me", headers=headers)
    assert rejected.status_code == 401


def test_logout_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401
