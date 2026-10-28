from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User


def register_and_login(client, email: str) -> str:
    password = "a-very-long-test-password"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert token_response.status_code == 200
    return token_response.json()["access_token"]


def prepare_registration(
    client,
    session_factory,
    *,
    closes_at=None,
    opens_at=None,
    max_teams=None,
    min_team_size=None,
    max_team_size=None,
    extra_members=0,
):
    token = register_and_login(client, "team-captain@example.com")
    extra_member_emails = [
        f"team-size-member-{index}@example.com" for index in range(extra_members)
    ]
    for email in extra_member_emails:
        register_and_login(client, email)
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "team-captain@example.com"))
        assert user is not None
        organization = Organization(
            name="Registration University",
            slug="registration-university",
            created_by_user_id=user.id,
        )
        db.add(organization)
        db.flush()
        team = Team(
            organization_id=organization.id,
            name="Registration Team",
            captain_user_id=user.id,
        )
        db.add(team)
        db.flush()
        db.add(Membership(team_id=team.id, user_id=user.id, role="captain"))
        for email in extra_member_emails:
            member = db.scalar(select(User).where(User.email == email))
            assert member is not None
            db.add(Membership(team_id=team.id, user_id=member.id, role="member"))
        competition = Competition(
            organization_id=organization.id,
            created_by_user_id=user.id,
            name="Registration CTF",
            slug="registration-ctf",
            status="published",
            is_public=True,
            max_teams=max_teams,
            min_team_size=min_team_size,
            max_team_size=max_team_size,
            registration_opens_at=opens_at,
            registration_closes_at=closes_at,
        )
        db.add(competition)
        db.commit()
        ids = (competition.id, team.id, organization.id, user.id)
    return token, ids


def test_team_can_register_for_public_competition(client, session_factory):
    token, (competition_id, team_id, _, user_id) = prepare_registration(client, session_factory)
    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["competition_id"] == competition_id
    assert body["team_id"] == team_id
    assert body["registered_by_user_id"] == user_id
    assert body["id"] > 0


def test_duplicate_registration_returns_conflict(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(client, session_factory)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/competitions/{competition_id}/registrations"

    assert client.post(path, json={"team_id": team_id}, headers=headers).status_code == 201
    duplicate = client.post(path, json={"team_id": team_id}, headers=headers)

    assert duplicate.status_code == 409


def test_registration_requires_authentication(client, session_factory):
    _, (competition_id, team_id, _, _) = prepare_registration(client, session_factory)

    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
    )

    assert response.status_code == 401


def test_non_member_cannot_register_team(client, session_factory):
    _, (competition_id, team_id, _, _) = prepare_registration(client, session_factory)
    outsider_token = register_and_login(client, "registration-outsider@example.com")

    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_team_from_another_organization_is_rejected(client, session_factory):
    token, (competition_id, _, _, user_id) = prepare_registration(client, session_factory)
    with session_factory() as db:
        other_org = Organization(
            name="Other University",
            slug="other-university",
            created_by_user_id=user_id,
        )
        db.add(other_org)
        db.flush()
        other_team = Team(
            organization_id=other_org.id,
            name="Other Team",
            captain_user_id=user_id,
        )
        db.add(other_team)
        db.flush()
        db.add(Membership(team_id=other_team.id, user_id=user_id, role="captain"))
        db.commit()
        other_team_id = other_team.id

    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": other_team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_private_or_unpublished_competition_is_not_registerable(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(client, session_factory)
    with session_factory() as db:
        competition = db.get(Competition, competition_id)
        assert competition is not None
        competition.is_public = False
        db.commit()

    private = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert private.status_code == 404

    with session_factory() as db:
        competition = db.get(Competition, competition_id)
        assert competition is not None
        competition.is_public = True
        competition.status = "draft"
        db.commit()

    unpublished = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unpublished.status_code == 404


def test_registration_window_not_open_returns_conflict(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(
        client,
        session_factory,
        opens_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


def test_closed_registration_window_returns_conflict(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(
        client,
        session_factory,
        closes_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


def test_registration_capacity_rejects_additional_team(client, session_factory):
    token, (competition_id, team_id, organization_id, user_id) = prepare_registration(
        client, session_factory, max_teams=1
    )
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/competitions/{competition_id}/registrations"
    first = client.post(path, json={"team_id": team_id}, headers=headers)
    assert first.status_code == 201

    with session_factory() as db:
        second_team = Team(
            organization_id=organization_id,
            name="Registration Team Two",
            captain_user_id=user_id,
        )
        db.add(second_team)
        db.flush()
        db.add(Membership(team_id=second_team.id, user_id=user_id, role="captain"))
        db.commit()
        second_team_id = second_team.id

    second = client.post(path, json={"team_id": second_team_id}, headers=headers)

    assert second.status_code == 409
    assert "capacity" in second.json()["detail"].lower()
    with session_factory() as db:
        registrations = db.scalar(
            select(func.count(CompetitionRegistration.id)).where(
                CompetitionRegistration.competition_id == competition_id
            )
        )
        assert registrations == 1


def test_registration_capacity_is_unlimited_when_not_configured(client, session_factory):
    token, (competition_id, team_id, organization_id, user_id) = prepare_registration(
        client, session_factory
    )
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/competitions/{competition_id}/registrations"
    assert client.post(path, json={"team_id": team_id}, headers=headers).status_code == 201

    with session_factory() as db:
        second_team = Team(
            organization_id=organization_id,
            name="Registration Team Two",
            captain_user_id=user_id,
        )
        db.add(second_team)
        db.flush()
        db.add(Membership(team_id=second_team.id, user_id=user_id, role="captain"))
        db.commit()
        second_team_id = second_team.id

    second = client.post(path, json={"team_id": second_team_id}, headers=headers)

    assert second.status_code == 201


def test_registration_rejects_team_below_minimum_size(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(
        client, session_factory, min_team_size=2
    )
    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert "at least 2 members" in response.json()["detail"]


def test_registration_rejects_team_above_maximum_size(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(
        client, session_factory, max_team_size=1, extra_members=1
    )
    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert "more than 1 members" in response.json()["detail"]


def test_registration_accepts_team_within_size_bounds(client, session_factory):
    token, (competition_id, team_id, _, _) = prepare_registration(
        client, session_factory, min_team_size=1, max_team_size=2
    )
    response = client.post(
        f"/api/v1/competitions/{competition_id}/registrations",
        json={"team_id": team_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
