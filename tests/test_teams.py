from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User


def register_and_login(client: TestClient, email: str) -> str:
    password = "a-very-long-test-password"
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        ).status_code
        == 201
    )
    response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_participant_cannot_create_organization(client: TestClient) -> None:
    token = register_and_login(client, "participant@example.com")
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Kelaniya", "slug": "kelaniya"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_organization_team_membership_flow(client: TestClient, session_factory) -> None:
    token = register_and_login(client, "captain@example.com")
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "captain@example.com"))
        assert user is not None
        user.role = "organizer"
        db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "University of Kelaniya", "slug": "uok"},
        headers=headers,
    )
    assert organization_response.status_code == 201
    organization_id = organization_response.json()["id"]

    team_response = client.post(
        f"/api/v1/organizations/{organization_id}/teams",
        json={"name": "ECS-Crew"},
        headers=headers,
    )
    assert team_response.status_code == 201
    team = team_response.json()
    assert team["members"][0]["role"] == "captain"
    assert "email" not in team["members"][0]
    assert "captain@example.com" not in team_response.text
    public_team = client.get(f"/api/v1/teams/{team['id']}")
    assert public_team.status_code == 200
    assert "captain@example.com" not in public_team.text

    member_token = register_and_login(client, "member@example.com")
    member_headers = {"Authorization": f"Bearer {member_token}"}
    joined = client.post(
        f"/api/v1/teams/{team['id']}/join",
        headers=member_headers,
    )
    assert joined.status_code == 200
    assert len(joined.json()["members"]) == 2

    with session_factory() as db:
        team_record = db.get(Team, team["id"])
        assert team_record is not None
        competition = Competition(
            organization_id=organization_id,
            created_by_user_id=team["captain_user_id"],
            name="Roster Lock CTF",
            slug="roster-lock-ctf",
            status="published",
            is_public=True,
        )
        db.add(competition)
        db.flush()
        db.add(
            CompetitionRegistration(
                competition_id=competition.id,
                team_id=team["id"],
                registered_by_user_id=team["captain_user_id"],
            )
        )
        db.commit()
        competition_id = competition.id

    extra_token = register_and_login(client, "extra-member@example.com")
    locked_join = client.post(
        f"/api/v1/teams/{team['id']}/join",
        headers={"Authorization": f"Bearer {extra_token}"},
    )
    assert locked_join.status_code == 409
    assert "membership is locked" in locked_join.json()["detail"]

    locked_leave = client.delete(
        f"/api/v1/teams/{team['id']}/leave",
        headers=member_headers,
    )
    assert locked_leave.status_code == 409
    assert "membership is locked" in locked_leave.json()["detail"]

    duplicate_join = client.post(
        f"/api/v1/teams/{team['id']}/join",
        headers=member_headers,
    )
    assert duplicate_join.status_code == 409

    member_id = next(
        item["user_id"] for item in joined.json()["members"] if item["role"] == "member"
    )
    denied_transfer = client.put(
        f"/api/v1/teams/{team['id']}/captain",
        json={"user_id": team["captain_user_id"]},
        headers=member_headers,
    )
    assert denied_transfer.status_code == 403

    self_transfer = client.put(
        f"/api/v1/teams/{team['id']}/captain",
        json={"user_id": team["captain_user_id"]},
        headers=headers,
    )
    assert self_transfer.status_code == 409

    nonmember_transfer = client.put(
        f"/api/v1/teams/{team['id']}/captain",
        json={"user_id": 999999},
        headers=headers,
    )
    assert nonmember_transfer.status_code == 404

    transfer = client.put(
        f"/api/v1/teams/{team['id']}/captain",
        json={"user_id": member_id},
        headers=headers,
    )
    assert transfer.status_code == 200
    transferred_team = transfer.json()
    assert transferred_team["captain_user_id"] == member_id
    assert {item["user_id"]: item["role"] for item in transferred_team["members"]} == {
        team["captain_user_id"]: "member",
        member_id: "captain",
    }

    locked_former_captain_leave = client.delete(
        f"/api/v1/teams/{team['id']}/leave",
        headers=headers,
    )
    assert locked_former_captain_leave.status_code == 409

    with session_factory() as db:
        registration = db.scalar(
            select(CompetitionRegistration).where(
                CompetitionRegistration.competition_id == competition_id,
                CompetitionRegistration.team_id == team["id"],
            )
        )
        assert registration is not None
        db.delete(registration)
        db.commit()

    left = client.delete(
        f"/api/v1/teams/{team['id']}/leave",
        headers=headers,
    )
    assert left.status_code == 204
    remaining_team = client.get(f"/api/v1/teams/{team['id']}").json()
    assert len(remaining_team["members"]) == 1
    assert remaining_team["captain_user_id"] == member_id

    captain_leave = client.delete(
        f"/api/v1/teams/{team['id']}/leave",
        headers=member_headers,
    )
    assert captain_leave.status_code == 409


def test_duplicate_team_name_is_rejected(client: TestClient, session_factory) -> None:
    token = register_and_login(client, "organizer@example.com")
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "organizer@example.com"))
        assert user is not None
        user.role = "organizer"
        db.commit()
        organization = Organization(name="Test Org", slug="test-org")
        db.add(organization)
        db.commit()
        organization_id = organization.id

    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        f"/api/v1/organizations/{organization_id}/teams",
        json={"name": "Blue Team"},
        headers=headers,
    )
    second = client.post(
        f"/api/v1/organizations/{organization_id}/teams",
        json={"name": "Blue Team"},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409
