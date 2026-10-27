from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User


def _register_and_login(client, email: str) -> str:
    password = "a-very-long-test-password"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _prepare_registration_lifecycle(client, session_factory, status="published"):
    captain_token = _register_and_login(client, "roster-captain@example.com")
    member_token = _register_and_login(client, "roster-member@example.com")
    organizer_token = _register_and_login(client, "roster-organizer@example.com")
    with session_factory() as db:
        captain = db.scalar(select(User).where(User.email == "roster-captain@example.com"))
        member = db.scalar(select(User).where(User.email == "roster-member@example.com"))
        organizer = db.scalar(select(User).where(User.email == "roster-organizer@example.com"))
        assert captain is not None and member is not None and organizer is not None
        organizer.role = "organizer"
        db.commit()
        organization = Organization(
            name="Registration Lifecycle University",
            slug="registration-lifecycle-university",
            created_by_user_id=organizer.id,
        )
        db.add(organization)
        db.flush()
        team = Team(
            organization_id=organization.id,
            name="Lifecycle Team",
            captain_user_id=captain.id,
        )
        db.add(team)
        db.flush()
        db.add_all(
            [
                Membership(team_id=team.id, user_id=captain.id, role="captain"),
                Membership(team_id=team.id, user_id=member.id, role="member"),
            ]
        )
        competition = Competition(
            organization_id=organization.id,
            created_by_user_id=organizer.id,
            name="Registration Lifecycle CTF",
            slug="registration-lifecycle-ctf",
            status=status,
            is_public=True,
            registration_opens_at=datetime.now(UTC) - timedelta(hours=1),
            registration_closes_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(competition)
        db.flush()
        registration = CompetitionRegistration(
            competition_id=competition.id,
            team_id=team.id,
            registered_by_user_id=captain.id,
        )
        db.add(registration)
        db.commit()
        ids = (competition.id, team.id, registration.id)
    return captain_token, member_token, organizer_token, ids


def test_organizer_can_list_private_registration_roster(client, session_factory):
    _, _, organizer_token, (competition_id, team_id, registration_id) = (
        _prepare_registration_lifecycle(client, session_factory)
    )
    response = client.get(
        f"/api/v1/competitions/{competition_id}/registrations?limit=10&offset=0",
        headers={"Authorization": f"Bearer {organizer_token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["id"] == registration_id
    assert item["team_id"] == team_id
    assert item["team_name"] == "Lifecycle Team"
    assert "email" not in item
    assert "roster-captain@example.com" not in response.text


def test_participant_cannot_list_registration_roster(client, session_factory):
    participant_token, _, _, (competition_id, _, _) = _prepare_registration_lifecycle(
        client, session_factory
    )
    response = client.get(
        f"/api/v1/competitions/{competition_id}/registrations",
        headers={"Authorization": f"Bearer {participant_token}"},
    )

    assert response.status_code == 403


def test_team_captain_can_withdraw_registration_before_activation(client, session_factory):
    captain_token, _, _, (competition_id, team_id, _) = _prepare_registration_lifecycle(
        client, session_factory
    )
    response = client.delete(
        f"/api/v1/competitions/{competition_id}/registrations/{team_id}",
        headers={"Authorization": f"Bearer {captain_token}"},
    )

    assert response.status_code == 204
    with session_factory() as db:
        registration = db.scalar(
            select(CompetitionRegistration).where(
                CompetitionRegistration.competition_id == competition_id,
                CompetitionRegistration.team_id == team_id,
            )
        )
        assert registration is None


def test_non_captain_cannot_withdraw_registration(client, session_factory):
    _, member_token, _, (competition_id, team_id, _) = _prepare_registration_lifecycle(
        client, session_factory
    )
    response = client.delete(
        f"/api/v1/competitions/{competition_id}/registrations/{team_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )

    assert response.status_code == 403


def test_registration_cannot_be_withdrawn_after_competition_activates(client, session_factory):
    captain_token, _, _, (competition_id, team_id, _) = _prepare_registration_lifecycle(
        client, session_factory, status="active"
    )
    response = client.delete(
        f"/api/v1/competitions/{competition_id}/registrations/{team_id}",
        headers={"Authorization": f"Bearer {captain_token}"},
    )

    assert response.status_code == 409
    with session_factory() as db:
        registration = db.scalar(
            select(CompetitionRegistration).where(
                CompetitionRegistration.competition_id == competition_id,
                CompetitionRegistration.team_id == team_id,
            )
        )
        assert registration is not None
