from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User


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


def prepare_organizer(client: TestClient, session_factory, email: str) -> tuple[str, int]:
    token = register_and_login(client, email)
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = "organizer"
        db.commit()
        organization = Organization(name="Test University", slug="test-university")
        db.add(organization)
        db.commit()
        organization_id = organization.id
    return token, organization_id


def test_participant_cannot_create_competition(client: TestClient) -> None:
    token = register_and_login(client, "participant@example.com")
    response = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": 1,
            "name": "Test CTF",
            "slug": "test-ctf",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_competition_round_lifecycle(client: TestClient, session_factory) -> None:
    token, organization_id = prepare_organizer(client, session_factory, "organizer@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": organization_id,
            "name": "MEDUSA Qualifiers",
            "slug": "medusa-qualifiers",
            "is_public": True,
        },
        headers=headers,
    )
    assert created.status_code == 201
    competition = created.json()
    competition_id = competition["id"]
    assert competition["status"] == "draft"

    hidden_from_public_list = client.get("/api/v1/competitions")
    assert hidden_from_public_list.status_code == 200
    assert all(item["id"] != competition_id for item in hidden_from_public_list.json())

    published = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    round_response = client.post(
        f"/api/v1/competitions/{competition_id}/rounds",
        json={"name": "Web Recon", "slug": "web-recon", "position": 1},
        headers=headers,
    )
    assert round_response.status_code == 201
    assert round_response.json()["position"] == 1

    duplicate_position = client.post(
        f"/api/v1/competitions/{competition_id}/rounds",
        json={"name": "Forensics", "slug": "forensics", "position": 1},
        headers=headers,
    )
    assert duplicate_position.status_code == 409

    rounds = client.get(f"/api/v1/competitions/{competition_id}/rounds")
    assert rounds.status_code == 200
    assert [item["slug"] for item in rounds.json()] == ["web-recon"]

    invalid_transition = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "archived"},
        headers=headers,
    )
    assert invalid_transition.status_code == 409


def test_competition_schedule_validation(client: TestClient, session_factory) -> None:
    token, organization_id = prepare_organizer(client, session_factory, "schedule@example.com")
    response = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": organization_id,
            "name": "Invalid Schedule",
            "slug": "invalid-schedule",
            "registration_opens_at": "2026-10-20T12:00:00Z",
            "registration_closes_at": "2026-10-19T12:00:00Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
