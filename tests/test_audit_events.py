from datetime import datetime, timezone

from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.user import User


def _register_and_login(client, email: str) -> str:
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


def test_audit_events_are_admin_only_and_filterable(client, session_factory):
    admin_token = _register_and_login(client, "audit-admin@example.com")
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "audit-admin@example.com"))
        assert admin is not None
        admin.role = "admin"
        db.commit()
        db.add(
            AuditEvent(
                actor_user_id=admin.id,
                actor_role="admin",
                action="challenge.status_changed",
                outcome="success",
                resource_type="challenge",
                resource_id=42,
                details={"from": "draft", "to": "published"},
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/audit-events?action=challenge.status_changed&limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["resource_id"] == 42
    assert response.json()[0]["details"] == {"from": "draft", "to": "published"}

    participant_token = _register_and_login(client, "audit-participant@example.com")
    denied = client.get(
        "/api/v1/audit-events",
        headers={"Authorization": f"Bearer {participant_token}"},
    )
    assert denied.status_code == 403


def test_audit_events_require_authentication(client):
    response = client.get("/api/v1/audit-events")
    assert response.status_code == 401



def test_organization_and_team_mutations_are_audited(client, session_factory):
    organizer_token = _register_and_login(client, "audit-organizer@example.com")
    with session_factory() as db:
        organizer = db.scalar(
            select(User).where(User.email == "audit-organizer@example.com")
        )
        assert organizer is not None
        organizer.role = "organizer"
        db.commit()

    headers = {"Authorization": f"Bearer {organizer_token}"}
    organization = client.post(
        "/api/v1/organizations",
        json={"name": "Audit University", "slug": "audit-university"},
        headers=headers,
    )
    assert organization.status_code == 201
    organization_id = organization.json()["id"]

    team = client.post(
        f"/api/v1/organizations/{organization_id}/teams",
        json={"name": "Audit Team"},
        headers=headers,
    )
    assert team.status_code == 201
    team_id = team.json()["id"]

    invitation = client.post(
        f"/api/v1/teams/{team_id}/invitation-code", headers=headers
    )
    assert invitation.status_code == 200
    raw_code = invitation.json()["code"]

    member_token = _register_and_login(client, "audit-member@example.com")
    joined = client.post(
        "/api/v1/teams/join",
        json={"code": raw_code},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert joined.status_code == 200

    with session_factory() as db:
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        actions = [event.action for event in events]
        details = [str(event.details) for event in events]

    assert "organization.created" in actions
    assert "team.created" in actions
    assert "team.invitation_code_rotated" in actions
    assert "team.member_joined" in actions
    assert all(raw_code not in item for item in details)



def test_audit_events_filter_by_actor_outcome_and_time_range(client, session_factory):
    admin_token = _register_and_login(client, "audit-filter-admin@example.com")
    with session_factory() as db:
        admin = db.scalar(
            select(User).where(User.email == "audit-filter-admin@example.com")
        )
        assert admin is not None
        admin.role = "admin"
        db.flush()
        actor_id = admin.id
        db.add(
            AuditEvent(
                actor_user_id=actor_id,
                actor_role="admin",
                action="team.member_removed",
                outcome="failure",
                resource_type="team",
                resource_id=7,
                details={"reason": "permission_denied"},
                created_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
            )
        )
        db.add(
            AuditEvent(
                actor_user_id=actor_id,
                actor_role="admin",
                action="team.member_joined",
                outcome="success",
                resource_type="team",
                resource_id=8,
                created_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
            )
        )
        db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.get(
        "/api/v1/audit-events",
        params={
            "actor_user_id": actor_id,
            "outcome": "failure",
            "created_after": "2026-01-01T00:00:00Z",
            "created_before": "2026-01-03T00:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["action"] == "team.member_removed"
    assert response.json()[0]["outcome"] == "failure"

    reversed_range = client.get(
        "/api/v1/audit-events",
        params={
            "created_after": "2026-01-03T00:00:00Z",
            "created_before": "2026-01-01T00:00:00Z",
        },
        headers=headers,
    )
    assert reversed_range.status_code == 422
