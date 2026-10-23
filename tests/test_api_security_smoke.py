"""Security smoke tests for authentication and authorization boundaries."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings


def register_and_login(client: TestClient, email: str) -> str:
    password = "a-very-long-test-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_protected_profile_rejects_missing_and_malformed_bearer_tokens(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer definitely-not-a-jwt"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_profile_rejects_expired_token(client: TestClient) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "ver": 0,
            "jti": "expired-security-smoke-test",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
            "iss": settings.token_issuer,
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_protected_profile_rejects_token_signed_with_wrong_secret(
    client: TestClient,
) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "ver": 0,
            "jti": "forged-security-smoke-test",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.token_issuer,
        },
        "not-the-configured-signing-secret",
        algorithm="HS256",
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_participant_cannot_access_organizer_competition_creation(
    client: TestClient,
) -> None:
    token = register_and_login(client, "api-security-participant@example.com")
    response = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": 1,
            "name": "Unauthorized Security Smoke Test",
            "slug": "unauthorized-security-smoke-test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_invalid_login_does_not_issue_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "unknown-security-smoke@example.com", "password": "incorrect"},
    )
    assert response.status_code == 401
    assert "access_token" not in response.json()
