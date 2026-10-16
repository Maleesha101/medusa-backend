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
