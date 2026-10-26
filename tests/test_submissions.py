from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.challenge_flag import ChallengeFlag
from app.models.challenge_submission import ChallengeSubmission
from app.models.competition_registration import CompetitionRegistration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User


def _register_and_login(client, email: str) -> str:
    password = "a-very-long-test-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _prepare_organizer(client, session_factory, email: str) -> tuple[str, int]:
    token = _register_and_login(client, email)
    with session_factory() as db:
        organizer = db.scalar(select(User).where(User.email == email))
        assert organizer is not None
        organizer.role = "organizer"
        db.commit()
        organization = Organization(
            name="Submission Test University",
            slug="submission-test-university",
            created_by_user_id=organizer.id,
        )
        db.add(organization)
        db.commit()
        organization_id = organization.id
    return token, organization_id


def _create_round(client, token: str, organization_id: int) -> tuple[int, int]:
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": organization_id,
            "name": "Submission Test CTF",
            "slug": "submission-test-ctf",
            "is_public": True,
        },
        headers=headers,
    )
    assert response.status_code == 201
    competition_id = response.json()["id"]
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
    return competition_id, round_response.json()["id"]


def _prepare_active_challenge(client, session_factory):
    organizer_email = "submission-organizer@example.com"
    organizer_token, organization_id = _prepare_organizer(client, session_factory, organizer_email)
    headers = {"Authorization": f"Bearer {organizer_token}"}
    competition_id, round_id = _create_round(client, organizer_token, organization_id)

    with session_factory() as db:
        organizer = db.scalar(select(User).where(User.email == organizer_email))
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
        headers=headers,
    )
    assert created.status_code == 201
    challenge_id = created.json()["id"]

    configured = client.put(
        f"/api/v1/challenges/{challenge_id}/flag",
        json={"flag": "MEDUSA{packet_beacon_found_2026}"},
        headers=headers,
    )
    assert configured.status_code == 204

    published_challenge = client.patch(
        f"/api/v1/challenges/{challenge_id}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert published_challenge.status_code == 200

    active = client.patch(
        f"/api/v1/competitions/{competition_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert active.status_code == 200

    with session_factory() as db:
        organizer = db.scalar(select(User).where(User.email == organizer_email))
        assert organizer is not None
        db.add(
            CompetitionRegistration(
                competition_id=competition_id,
                team_id=team_id,
                registered_by_user_id=organizer.id,
            )
        )
        db.commit()
    return organizer_token, challenge_id, team_id, headers, competition_id


def test_flag_lifecycle_and_submission_replay_protection(client, session_factory):
    _, challenge_id, team_id, headers, competition_id = _prepare_active_challenge(
        client, session_factory
    )

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
    with session_factory() as db:
        solved = db.scalar(
            select(ChallengeSubmission).where(
                ChallengeSubmission.challenge_id == challenge_id,
                ChallengeSubmission.is_correct.is_(True),
            )
        )
        assert solved is not None
        assert solved.points_awarded == 200
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
                select(ChallengeSubmission).where(ChallengeSubmission.challenge_id == challenge_id)
            ).all()
        )
        assert len(attempts) == 2
        assert all(not hasattr(attempt, "flag") for attempt in attempts)
        assert sum(attempt.is_correct for attempt in attempts) == 1
        assert sum(attempt.points_awarded for attempt in attempts) == 200

    scoreboard = client.get(f"/api/v1/competitions/{competition_id}/scoreboard")
    assert scoreboard.status_code == 200
    assert scoreboard.json()["entries"][0]["team_id"] == team_id
    assert scoreboard.json()["entries"][0]["points"] == 200
    assert scoreboard.json()["entries"][0]["solves"] == 1

    # A later challenge-point edit must not rewrite an already-earned score.
    updated_challenge = client.patch(
        f"/api/v1/challenges/{challenge_id}",
        json={"points": 500},
        headers=headers,
    )
    assert updated_challenge.status_code == 200
    unchanged_scoreboard = client.get(f"/api/v1/competitions/{competition_id}/scoreboard")
    assert unchanged_scoreboard.json()["entries"][0]["points"] == 200

    with session_factory() as db:
        submission_events = list(
            db.scalars(select(AuditEvent).where(AuditEvent.action == "challenge.submission")).all()
        )
        assert {event.outcome for event in submission_events} == {"correct", "incorrect"}
        assert all(event.resource_type == "challenge" for event in submission_events)
        assert all("flag" not in (event.details or {}) for event in submission_events)
        all_events = list(db.scalars(select(AuditEvent)).all())
        assert any(event.action == "challenge.flag_configured" for event in all_events)


def test_cannot_publish_challenge_without_flag(client, session_factory):
    token, organization_id = _prepare_organizer(
        client, session_factory, "missing-flag-organizer@example.com"
    )
    headers = {"Authorization": f"Bearer {token}"}
    _, round_id = _create_round(client, token, organization_id)
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
    _, challenge_id, team_id, _, _ = _prepare_active_challenge(client, session_factory)
    outsider_email = "submission-outsider@example.com"
    outsider_token = _register_and_login(client, outsider_email)
    response = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": "MEDUSA{packet_beacon_found_2026}"},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert response.status_code == 403


def test_flag_endpoint_rejects_participant(client, session_factory):
    token, organization_id = _prepare_organizer(
        client, session_factory, "flag-permission-organizer@example.com"
    )
    _, round_id = _create_round(client, token, organization_id)
    challenge = client.post(
        f"/api/v1/rounds/{round_id}/challenges",
        json={
            "name": "Protected Flag",
            "slug": "protected-flag",
            "description": "Organizer-only flag setup.",
            "category": "Web",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert challenge.status_code == 201
    participant_token = _register_and_login(client, "flag-permission-participant@example.com")
    response = client.put(
        f"/api/v1/challenges/{challenge.json()['id']}/flag",
        json={"flag": "MEDUSA{must_not_be_set_by_participant}"},
        headers={"Authorization": f"Bearer {participant_token}"},
    )
    assert response.status_code == 403


def test_incorrect_submission_limit_is_shared_by_team_and_challenge(client, session_factory):
    _, challenge_id, team_id, headers, _ = _prepare_active_challenge(client, session_factory)

    for attempt_number in range(10):
        response = client.post(
            f"/api/v1/challenges/{challenge_id}/submissions",
            json={"team_id": team_id, "flag": f"MEDUSA{{wrong_{attempt_number}}}"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["correct"] is False

    blocked = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": "MEDUSA{eleventh_wrong_attempt}"},
        headers=headers,
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1

    with session_factory() as db:
        attempts = list(
            db.scalars(
                select(ChallengeSubmission).where(
                    ChallengeSubmission.challenge_id == challenge_id,
                    ChallengeSubmission.team_id == team_id,
                )
            ).all()
        )
        assert len(attempts) == 10



def test_unregistered_team_cannot_submit_flags(client, session_factory):
    _, challenge_id, team_id, headers, _ = _prepare_active_challenge(client, session_factory)
    with session_factory() as db:
        registration = db.scalar(
            select(CompetitionRegistration).where(CompetitionRegistration.team_id == team_id)
        )
        assert registration is not None
        db.delete(registration)
        db.commit()

    response = client.post(
        f"/api/v1/challenges/{challenge_id}/submissions",
        json={"team_id": team_id, "flag": "MEDUSA{packet_beacon_found_2026}"},
        headers=headers,
    )

    assert response.status_code == 409
    assert "register" in response.json()["detail"].lower()
    with session_factory() as db:
        submission_id = db.scalar(
            select(ChallengeSubmission.id).where(ChallengeSubmission.team_id == team_id)
        )
        assert submission_id is None


def test_registration_for_another_competition_does_not_allow_submission(
    client, session_factory
):
    organizer_token, challenge_id, team_id, headers, competition_a_id = _prepare_active_challenge(
        client, session_factory
    )
    with session_factory() as db:
        organizer = db.scalar(select(User).where(User.email == "submission-organizer@example.com"))
        assert organizer is not None
        organization_id = db.scalar(
            select(Team.organization_id).where(Team.id == team_id)
        )
        assert organization_id is not None

    created_competition = client.post(
        "/api/v1/competitions",
        json={
            "organization_id": organization_id,
            "name": "Submission Test CTF B",
            "slug": "submission-test-ctf-b",
            "is_public": True,
        },
        headers=headers,
    )
    assert created_competition.status_code == 201
    competition_b_id = created_competition.json()["id"]
    published = client.patch(
        f"/api/v1/competitions/{competition_b_id}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert published.status_code == 200
    round_response = client.post(
        f"/api/v1/competitions/{competition_b_id}/rounds",
        json={"name": "Qualifiers B", "slug": "qualifiers-b", "position": 1},
        headers=headers,
    )
    assert round_response.status_code == 201
    challenge_response = client.post(
        f"/api/v1/rounds/{round_response.json()['id']}/challenges",
        json={
            "name": "Beacon Trace B",
            "slug": "beacon-trace-b",
            "description": "Cross-competition registration regression.",
            "category": "Forensics",
            "points": 200,
            "difficulty": "medium",
        },
        headers=headers,
    )
    assert challenge_response.status_code == 201
    challenge_b_id = challenge_response.json()["id"]
    configured = client.put(
        f"/api/v1/challenges/{challenge_b_id}/flag",
        json={"flag": "MEDUSA{packet_beacon_found_2026}"},
        headers=headers,
    )
    assert configured.status_code == 204
    published_challenge = client.patch(
        f"/api/v1/challenges/{challenge_b_id}/status",
        json={"status": "published"},
        headers=headers,
    )
    assert published_challenge.status_code == 200
    activated = client.patch(
        f"/api/v1/competitions/{competition_b_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert activated.status_code == 200

    # The team is registered for A, but has no registration for B.
    response = client.post(
        f"/api/v1/challenges/{challenge_b_id}/submissions",
        json={"team_id": team_id, "flag": "MEDUSA{packet_beacon_found_2026}"},
        headers=headers,
    )

    assert competition_a_id != competition_b_id
    assert response.status_code == 409
