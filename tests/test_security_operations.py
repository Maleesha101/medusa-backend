from sqlalchemy import select

from app.models.security_operations import SecurityEvent
from app.models.user import User


def _register_and_login(client, email: str) -> tuple[str, str]:
    password = "a-very-long-test-password"
    registered = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 201
    response = client.post("/api/v1/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"], password


def _make_admin(client, session_factory, email: str) -> str:
    token, _ = _register_and_login(client, email)
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = "admin"
        db.commit()
    return token


def test_soc_api_is_admin_only_and_uses_persisted_auth_events(client, session_factory):
    token = _make_admin(client, session_factory, "soc-admin@example.com")
    participant_token, password = _register_and_login(client, "soc-user@example.com")
    failed = client.post(
        "/api/v1/auth/token",
        data={"username": "soc-user@example.com", "password": "incorrect-password"},
    )
    assert failed.status_code == 401

    headers = {"Authorization": f"Bearer {token}"}
    events = client.get("/api/v1/soc/events?limit=100", headers=headers)
    assert events.status_code == 200
    login_events = [item for item in events.json()["items"] if item["type"] == "auth.login.failure"]
    assert login_events
    assert login_events[0]["user"] != "soc-user@example.com"
    assert "incorrect-password" not in str(events.json())
    assert events.json()["items"][0]["ip"].endswith(".xxx") or events.json()["items"][0]["ip"] == "—"

    denied = client.get(
        "/api/v1/soc/events",
        headers={"Authorization": f"Bearer {participant_token}"},
    )
    assert denied.status_code == 403

    with session_factory() as db:
        persisted = db.scalars(
            select(SecurityEvent).where(SecurityEvent.event_type == "auth.login.failure")
        ).all()
        assert persisted
        assert all("incorrect-password" not in str(row.details) for row in persisted)


def test_soc_investigations_rules_settings_and_reports_are_persisted(client, session_factory):
    token = _make_admin(client, session_factory, "soc-workflow-admin@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    rules = client.get("/api/v1/soc/rules", headers=headers)
    assert rules.status_code == 200
    rule_rows = rules.json()["items"]
    assert len(rule_rows) == 16
    assert next(row for row in rule_rows if row["id"] == "r_bruteforce")["enabled"] is True
    assert next(row for row in rule_rows if row["id"] == "r_travel")["enabled"] is False
    unsupported = client.patch(
        "/api/v1/soc/rules/r_travel",
        json={"enabled": True},
        headers=headers,
    )
    assert unsupported.status_code == 409

    created = client.post(
        "/api/v1/soc/cases",
        json={"title": "Investigate suspicious login activity", "severity": "High",
              "description": "Repeated authentication failures."},
        headers=headers,
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    note = client.post(
        f"/api/v1/soc/cases/{case_id}/notes",
        json={"text": "Reviewed the source address and account history."},
        headers=headers,
    )
    assert note.status_code == 200
    assert len(note.json()["notes"]) == 1

    decision = client.post(
        f"/api/v1/soc/cases/{case_id}/decisions",
        json={"text": "Escalate for additional account verification."},
        headers=headers,
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "Pending decision"

    settings = client.put(
        "/api/v1/soc/settings",
        json={"retentionDays": 120, "suppressionHours": 4, "notifyCritical": True},
        headers=headers,
    )
    assert settings.status_code == 200
    assert client.get("/api/v1/soc/settings", headers=headers).json()["retentionDays"] == 120

    saved = client.post(
        "/api/v1/soc/saved-views",
        json={"name": "Login failures", "query": "type:auth.login.failure"},
        headers=headers,
    )
    assert saved.status_code == 201
    assert saved.json()["query"] == "type:auth.login.failure"

    report = client.post(
        "/api/v1/soc/reports",
        json={"title": "Authentication activity", "type": "events", "format": "csv", "days": 7},
        headers=headers,
    )
    assert report.status_code == 201
    exported = client.get(
        f"/api/v1/soc/reports/{report.json()['id']}/data",
        headers=headers,
    )
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert "event_type" in exported.text or "type" in exported.text


def test_soc_endpoints_require_authentication(client):
    assert client.get("/api/v1/soc/events").status_code == 401
    assert client.get("/api/v1/soc/cases").status_code == 401
