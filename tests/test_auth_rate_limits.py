from fastapi.testclient import TestClient


def test_registration_is_rate_limited_per_client_ip(client: TestClient) -> None:
    for index in range(5):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"register-limit-{index}@example.com",
                "password": "a-very-long-test-password",
            },
        )
        assert response.status_code == 201

    blocked = client.post(
        "/api/v1/auth/register",
        json={
            "email": "register-limit-blocked@example.com",
            "password": "a-very-long-test-password",
        },
    )
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]


def test_token_endpoint_is_rate_limited_per_account(client: TestClient) -> None:
    payload = {"username": "missing-account@example.com", "password": "incorrect"}
    for _ in range(5):
        response = client.post("/api/v1/auth/token", data=payload)
        assert response.status_code == 401

    blocked = client.post("/api/v1/auth/token", data=payload)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]


def test_token_endpoint_is_rate_limited_per_ip(client: TestClient) -> None:
    for index in range(20):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": f"missing-{index}@example.com", "password": "incorrect"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/token",
        data={"username": "another-missing@example.com", "password": "incorrect"},
    )
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]
