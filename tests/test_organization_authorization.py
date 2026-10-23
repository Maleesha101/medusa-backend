"""Regression tests for organization-scoped organizer authorization."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.user import User


def register_organizer(client: TestClient, session_factory, email: str) -> str:
    password = "a-very-long-test-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = "organizer"
        db.commit()
    response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_organizers_are_scoped_to_organizations_they_created(
    client: TestClient,
    session_factory,
) -> None:
    owner_token = register_organizer(
        client, session_factory, "organization-owner@example.com"
    )
    other_token = register_organizer(
        client, session_factory, "organization-other@example.com"
    )

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    owner_org_response = client.post(
        "/api/v1/organizations",
        json={"name": "Owner University", "slug": "owner-university"},
        headers=owner_headers,
    )
    assert owner_org_response.status_code == 201
    owner_org_id = owner_org_response.json()["id"]

    other_org_response = client.post(
        "/api/v1/organizations",
        json={"name": "Other University", "slug": "other-university"},
        headers=other_headers,
    )
    assert other_org_response.status_code == 201

    owner_competition = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": owner_org_id,
            "name": "Owner Competition",
            "slug": "owner-competition",
        },
        headers=owner_headers,
    )
    assert owner_competition.status_code == 201
    competition_id = owner_competition.json()["id"]

    denied_create = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": owner_org_id,
            "name": "Foreign Competition",
            "slug": "foreign-competition",
        },
        headers=other_headers,
    )
    assert denied_create.status_code == 403

    denied_status = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "published"},
        headers=other_headers,
    )
    assert denied_status.status_code == 403

    denied_round = client.post(
        f"/api/v1/competitions/{competition_id}/rounds",
        json={"name": "Foreign Round", "slug": "foreign-round", "position": 1},
        headers=other_headers,
    )
    assert denied_round.status_code == 403

    allowed_status = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "published"},
        headers=owner_headers,
    )
    assert allowed_status.status_code == 200

    allowed_round = client.post(
        f"/api/v1/competitions/{competition_id}/rounds",
        json={"name": "Owner Round", "slug": "owner-round", "position": 1},
        headers=owner_headers,
    )
    assert allowed_round.status_code == 201
