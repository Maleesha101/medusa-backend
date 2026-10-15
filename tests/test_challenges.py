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
        organization = Organization(name="Challenge Test University", slug="challenge-test-university")
        db.add(organization)
        db.commit()
        organization_id = organization.id
    return token, organization_id


def create_public_round(client: TestClient, token: str, organization_id: int) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    competition = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": organization_id,
            "name": "Challenge Test CTF",
            "slug": "challenge-test-ctf",
            "is_public": True,
        },
        headers=headers,
    )
    assert competition.status_code == 201
    competition_id = competition.json()["id"]
    published = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert published.status_code == 200
    round_response = client.post(
        f"/api/v1/competitions/{competition_id}/rounds",
        json={"name": "Qualifiers", "slug": "qualifiers", "position": 1},
        headers=headers,
    )
    assert round_response.status_code == 201
    return round_response.json()["id"]


def test_challenge_lifecycle_and_public_catalog(client: TestClient, session_factory) -> None:
    token, organization_id = prepare_organizer(
        client, session_factory, "challenge-organizer@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    round_id = create_public_round(client, token, organization_id)
    payload = {
        "name": "Lost Packet",
        "slug": "lost-packet",
        "description": "Inspect the supplied packet capture and identify the beacon.",
        "category": "Forensics",
        "points": 150,
        "difficulty": "medium",
    }

    created = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json=payload,
        headers=headers,
    )
    assert created.status_code == 201
    challenge = created.json()
    assert challenge["status"] == "draft"
    challenge_id = challenge["id"]

    hidden_detail = client.get(f"/api/v1/challenges/{challenge_id}")
    assert hidden_detail.status_code == 404
    hidden_list = client.get(f"/api/v1/rounds/{round_id}/challenges")
    assert hidden_list.status_code == 200
    assert hidden_list.json() == []

    published = client.patch(
        f"/api/v1/challenges/{challenge_id}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    public_detail = client.get(f"/api/v1/challenges/{challenge_id}")
    assert public_detail.status_code == 200
    assert public_detail.json()["slug"] == "lost-packet"
    public_list = client.get(f"/api/v1/rounds/{round_id}/challenges")
    assert [item["id"] for item in public_list.json()] == [challenge_id]

    updated = client.patch(
        f"/api/v1/challenges/{challenge_id}",
        json={"points": 200, "description": "Inspect the capture and identify the beacon host."},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["points"] == 200

    archived = client.patch(
        f"/api/v1/challenges/{challenge_id}/status",
        json={"status": "archived"},
        headers=headers,
    )
    assert archived.status_code == 200
    assert client.get(f"/api/v1/challenges/{challenge_id}").status_code == 404


def test_participant_cannot_author_challenge(client: TestClient, session_factory) -> None:
    token, organization_id = prepare_organizer(
        client, session_factory, "challenge-owner@example.com"
    )
    round_id = create_public_round(client, token, organization_id)
    participant_token = register_and_login(client, "challenge-participant@example.com")
    response = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json={
            "name": "Unauthorized Challenge",
            "slug": "unauthorized-challenge",
            "description": "This should not be created.",
            "category": "Web",
        },
        headers={"Authorization": f"Bearer {participant_token}"},
    )
    assert response.status_code == 403


def test_duplicate_challenge_slug_and_invalid_points(
    client: TestClient, session_factory
) -> None:
    token, organization_id = prepare_organizer(
        client, session_factory, "challenge-validation@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    round_id = create_public_round(client, token, organization_id)
    payload = {
        "name": "First Challenge",
        "slug": "first-challenge",
        "description": "A test challenge.",
        "category": "Web",
        "points": 100,
    }
    first = client.post(
        f"/api/v1/rounds/{round_id}/challenges", json=payload, headers=headers
    )
    assert first.status_code == 201
    duplicate = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json={**payload, "name": "Second Challenge"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    invalid = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json={**payload, "slug": "invalid-points", "points": 0},
        headers=headers,
    )
    assert invalid.status_code == 422
