from sqlalchemy import select

from app.models.challenge_flag import ChallengeFlag
from app.models.challenge_submission import ChallengeSubmission
from app.models.membership import Membership
from app.models.team import Team
from app.models.user import User

from tests.test_challenges import create_public_round, prepare_organizer, register_and_login


def prepare_active_challenge(client, session_factory):
    organizer_token, organization_id = prepare_organizer(
        client, session_factory, "submission-organizer@example.com"
    )
    organizer_headers = {"Authorization": f"Bearer {organizer_token}"}
    round_id = create_public_round(client, organizer_token, organization_id)

    with session_factory() as db:
        organizer = db.scalar(
            select(User).where(User.email == "submission-organizer@example.com")
        )
        assert organizer is not None
        team = Team(
            organization_id=organization_id,
            name="Packet Hunters",
            captain_user_id=organizer.id,
        )
        db.add(team)
        db.commit()
        team_id = team.id
        db.add(Membership(team_id=team_id, user_id=organizer.id, role="captain"))
        db.commit()

    created = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json={
            "name": "Beacon Trace",
            "slug": "beacon-trace",
            "description": "Identify the beacon in the packet capture.",
            "category": "Forensics",
            "points": 200,
            "difficulty": "medium",
        },
        headers=organizer_headers,
    )
    assert created.status_code == 201
    challenge_id = created.json()["id"]

    configured = client.put(
        f"/api/v1/challenges/{challenge_id}/flag",
        json={"flag": "MEDUSA{packet_beacon_found_2026}"},
        headers=organizer_headers,
    )
    assert configured.status_code == 204

    published_challenge = client.patch(
        f"/api/v1/challenges/{challenge_id}/status",
        json={"status": "published"},
        headers=organizer_headers,
    )
    assert published_challenge.status_code == 200

    with session_factory() as db:
        competition_id = db.get(__import__(
            "app.models.competition_round", fromlist=["CompetitionRound"]
        ).CompetitionRound, round_id).competition_id

    active = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "active"},
        headers=organizer_headers,
    )
    assert active.status_code == 200
    return organizer_token, challenge_id, team_id, organizer_headers


def test_flag_lifecycle_and_submission_replay_protection(client, session_factory):
    token, challenge_id, team_id, headers = prepare_active_challenge(client, session_factory)

    wrong = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": "MEDUSA{definitely_wrong_flag}"},
        headers=headers,
    )
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert "flag" not in wrong.json()

    correct_flag = "MEDUSA{packet_beacon_found_2026}"
    correct = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": correct_flag},
        headers=headers,
    )
    assert correct.status_code == 200
    assert correct.json()["correct"] is True
    assert correct_flag not in correct.text

    repeated = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": correct_flag},
        headers=headers,
    )
    assert repeated.status_code == 409

    with session_factory() as db:
        stored = db.get(ChallengeFlag, challenge_id)
        assert stored is not None
        assert stored.flag_hash != correct_flag
        attempts = list(
            db.scalars(
                select(ChallengeSubmission).where(
                    ChallengeSubmission.challenge_id == challenge_id
                )
            ).all()
        )
        assert len(attempts) == 2
        assert all(not hasattr(attempt, "flag") for attempt in attempts)
        assert sum(attempt.is_correct for attempt in attempts) == 1


def test_cannot_publish_challenge_without_flag(client, session_factory):
    token, organization_id = prepare_organizer(
        client, session_factory, "missing-flag-organizer@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    round_id = create_public_round(client, token, organization_id)
    created = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json={
            "name": "No Flag",
            "slug": "no-flag",
            "description": "A challenge with no configured answer.",
            "category": "Web",
        },
        headers=headers,
    )
    assert created.status_code == 201
    response = client.patch(
        f"/api/v1/challenges/{created.json()['id']}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert response.status_code == 409


def test_non_member_cannot_submit_for_team(client, session_factory):
    organizer_token, challenge_id, team_id, _ = prepare_active_challenge(
        client, session_factory
    )
    outsider_email = "submission-outsider@example.com"
    outsider_password = "a-very-long-test-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": outsider_email, "password": outsider_password},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/token",
        data={"username": outsider_email, "password": outsider_password},
    )
    assert login.status_code == 200
    response = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": "MEDUSA{packet_beacon_found_2026}"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
