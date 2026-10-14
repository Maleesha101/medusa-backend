from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import require_roles
from app.core.security import verify_password
from app.main import app
from app.models.user import User


def test_registration_hashes_password_and_ignores_role_escalation(
    client: TestClient, session_factory
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Participant@example.com",
            "password": "a-very-long-test-password",
            "role": "admin",
            "is_active": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "participant@example.com"
    assert body["role"] == "participant"
    assert body["is_active"] is True
    assert "password_hash" not in body

    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "participant@example.com"))
        assert user is not None
        assert user.password_hash != "a-very-long-test-password"
        assert verify_password("a-very-long-test-password", user.password_hash)


def test_registration_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )

    assert response.status_code == 422


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    payload = {"email": "same@example.com", "password": "a-very-long-test-password"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_login_and_current_user_profile(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "a-very-long-test-password"},
    )
    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": "login@example.com", "password": "a-very-long-test-password"},
    )

    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert profile.status_code == 200
    assert profile.json()["email"] == "login@example.com"
    assert profile.json()["role"] == "participant"
    assert "password_hash" not in profile.json()


def test_invalid_credentials_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "missing@example.com", "password": "not-the-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_inactive_user_token_is_rejected(client: TestClient, session_factory) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "inactive@example.com", "password": "a-very-long-test-password"},
    )
    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": "inactive@example.com", "password": "a-very-long-test-password"},
    )
    token = token_response.json()["access_token"]

    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "inactive@example.com"))
        assert user is not None
        user.is_active = False
        db.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_role_guard_denies_participant(client: TestClient) -> None:
    admin_guard = require_roles("admin")

    def admin_only(user: User = Depends(admin_guard)) -> dict[str, bool]:
        return {"ok": True}

    app.add_api_route("/_test/admin-only", admin_only, methods=["GET"])
    try:
        client.post(
            "/api/v1/auth/register",
            json={"email": "role@example.com", "password": "a-very-long-test-password"},
        )
        token_response = client.post(
            "/api/v1/auth/token",
            data={"username": "role@example.com", "password": "a-very-long-test-password"},
        )
        token = token_response.json()["access_token"]
        response = client.get("/_test/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
    finally:
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) != "/_test/admin-only"
        ]
