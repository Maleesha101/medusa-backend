from datetime import UTC, datetime

from app.models.operational_alert import OperationalAlert, OperationalAlertNotification
from app.models.user import User


def _admin_token(client, session_factory, email):
    password = "a-very-long-test-password"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    with session_factory() as db:
        user = db.query(User).filter_by(email=email).one()
        user.role = "admin"
        db.commit()
    return login.json()["access_token"]


def test_operational_alert_history_is_admin_only(client, session_factory):
    participant_password = "a-very-long-test-password"
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "alert-participant@example.com",
            "password": participant_password,
        },
    )
    login = client.post(
        "/api/v1/auth/token",
        data={
            "username": "alert-participant@example.com",
            "password": participant_password,
        },
    )
    denied = client.get(
        "/api/v1/admin/operations/alerts",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert denied.status_code == 403

    token = _admin_token(client, session_factory, "alert-admin@example.com")
    with session_factory() as db:
        alert = OperationalAlert(
            alert_key="medusa.cpu",
            metric="host_cpu_percent",
            severity="warning",
            value=82,
            threshold=80,
            unit="percent",
            is_active=True,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )
        db.add(alert)
        db.flush()
        db.add(
            OperationalAlertNotification(
                alert_id=alert.id,
                event_key="triggered:test",
                event_type="triggered",
                metric="host_cpu_percent",
                severity="warning",
                value=82,
                threshold=80,
                unit="percent",
                recipient_email="private-recipient@example.com",
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/admin/operations/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()[0]["alert_key"] == "medusa.cpu"
    assert "recipient_email" not in response.json()[0]
