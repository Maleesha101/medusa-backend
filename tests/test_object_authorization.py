"""Regression tests for object-level team membership authorization."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.membership import Membership
from app.models.organization import Organization
from app.models.team import Team
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


def test_user_cannot_leave_another_users_team_membership(
    client: TestClient,
    session_factory,
) -> None:
    owner_token = register_and_login(client, "membership-owner@example.com")
    other_token = register_and_login(client, "membership-other@example.com")

    with session_factory() as db:
        owner = db.scalar(select(User).where(User.email == "membership-owner@example.com"))
        other = db.scalar(select(User).where(User.email == "membership-other@example.com"))
        assert owner is not None
        assert other is not None
        organization = Organization(
            name="Membership Boundary University",
            slug="membership-boundary-university",
        )
        db.add(organization)
        db.commit()
        organization_id = organization.id
        owner_id = owner.id
        other_id = other.id

    created = client.post(
        f"/api/v1/organizations/{organization_id}/teams",
        json={"name": "Owner Team"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    team_id = created.json()["id"]

    unauthorized_leave = client.delete(
        f"/api/v1/teams/{team_id}/leave",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert unauthorized_leave.status_code == 404

    with session_factory() as db:
        owner_membership = db.scalar(
            select(Membership).where(
                Membership.team_id == team_id,
                Membership.user_id == owner_id,
            )
        )
        other_membership = db.scalar(
            select(Membership).where(
                Membership.team_id == team_id,
                Membership.user_id == other_id,
            )
        )
        assert owner_membership is not None
        assert owner_membership.role == "captain"
        assert other_membership is None


def test_member_can_leave_only_their_own_membership(
    client: TestClient,
    session_factory,
) -> None:
    captain_token = register_and_login(client, "membership-captain@example.com")
    member_token = register_and_login(client, "membership-member@example.com")

    with session_factory() as db:
        organization = Organization(
            name="Member Leave University",
            slug="member-leave-university",
        )
        db.add(organization)
        db.commit()
        organization_id = organization.id

    created = client.post(
        f"/api/v1/organizations/{organization_id}/teams",
        json={"name": "Membership Leave Team"},
        headers={"Authorization": f"Bearer {captain_token}"},
    )
    assert created.status_code == 201
    team_id = created.json()["id"]

    joined = client.post(
        f"/api/v1/teams/{team_id}/join",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert joined.status_code == 200

    left = client.delete(
        f"/api/v1/teams/{team_id}/leave",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert left.status_code == 204

    with session_factory() as db:
        team = db.get(Team, team_id)
        assert team is not None
        captain = db.scalar(
            select(User).where(User.email == "membership-captain@example.com")
        )
        member = db.scalar(select(User).where(User.email == "membership-member@example.com"))
        assert captain is not None
        assert member is not None
        captain_membership = db.scalar(
            select(Membership).where(
                Membership.team_id == team_id,
                Membership.user_id == captain.id,
            )
        )
        member_membership = db.scalar(
            select(Membership).where(
                Membership.team_id == team_id,
                Membership.user_id == member.id,
            )
        )
        assert captain_membership is not None
        assert captain_membership.role == "captain"
        assert member_membership is None
