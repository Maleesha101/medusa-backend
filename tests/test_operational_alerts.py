from datetime import UTC, datetime

from sqlalchemy import select

from app.models.operational_alert import OperationalAlert, OperationalAlertNotification
from app.models.user import User
from app.services import operational_alerts


def _metrics(alerts):
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "alerts": alerts,
    }


def _alert(severity="warning", value=82):
    return {
        "id": "medusa.cpu",
        "metric": "host_cpu_percent",
        "severity": severity,
        "value": value,
        "threshold": 80 if severity == "warning" else 95,
        "unit": "percent",
    }


def test_alert_transitions_are_persisted_and_deduplicated(session_factory, monkeypatch):
    monkeypatch.setattr(
        operational_alerts,
        "collect_operational_metrics",
        lambda db, settings: _metrics([_alert()]),
    )
    with session_factory() as db:
        db.add(
            User(
                email="ops-admin@example.com",
                password_hash="not-a-real-password-hash",
                role="admin",
            )
        )
        db.commit()

        assert operational_alerts.synchronize_operational_alerts(db, object()) == {
            "created": 1,
            "escalated": 0,
            "resolved": 0,
        }
        assert operational_alerts.synchronize_operational_alerts(db, object()) == {
            "created": 0,
            "escalated": 0,
            "resolved": 0,
        }
        assert len(db.scalars(select(OperationalAlertNotification)).all()) == 1

        monkeypatch.setattr(
            operational_alerts,
            "collect_operational_metrics",
            lambda db, settings: _metrics([_alert("critical", 97)]),
        )
        assert operational_alerts.synchronize_operational_alerts(db, object()) == {
            "created": 0,
            "escalated": 1,
            "resolved": 0,
        }
        assert len(db.scalars(select(OperationalAlertNotification)).all()) == 2

        monkeypatch.setattr(
            operational_alerts,
            "collect_operational_metrics",
            lambda db, settings: _metrics([]),
        )
        assert operational_alerts.synchronize_operational_alerts(db, object()) == {
            "created": 0,
            "escalated": 0,
            "resolved": 1,
        }
        alert = db.scalar(select(OperationalAlert))
        assert alert.is_active is False
        assert alert.resolved_at is not None
        assert len(db.scalars(select(OperationalAlertNotification)).all()) == 3


def test_notification_delivery_retries_without_exposing_smtp_error(
    session_factory, monkeypatch
):
    monkeypatch.setattr(
        operational_alerts,
        "send_operational_alert_email",
        lambda *args, **kwargs: False,
    )
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
        notification = OperationalAlertNotification(
            alert_id=alert.id,
            event_key="triggered:1",
            event_type="triggered",
            metric="host_cpu_percent",
            severity="warning",
            value=82,
            threshold=80,
            unit="percent",
            recipient_email="ops-admin@example.com",
        )
        db.add(notification)
        db.commit()

        result = operational_alerts.dispatch_operational_alert_notifications(db)

        assert result == {"sent": 0, "retry_scheduled": 0, "exhausted": 1}
        assert notification.status == "failed"
        assert notification.last_error_code == "smtp_not_configured"
        assert notification.attempts == operational_alerts.MAX_NOTIFICATION_ATTEMPTS


def test_notification_smtp_failure_is_retried(session_factory, monkeypatch):
    def fail_delivery(*args, **kwargs):
        raise RuntimeError("private smtp credentials must not leak")

    monkeypatch.setattr(operational_alerts, "send_operational_alert_email", fail_delivery)
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
        notification = OperationalAlertNotification(
            alert_id=alert.id,
            event_key="triggered:2",
            event_type="triggered",
            metric="host_cpu_percent",
            severity="warning",
            value=82,
            threshold=80,
            unit="percent",
            recipient_email="ops-admin@example.com",
        )
        db.add(notification)
        db.commit()

        result = operational_alerts.dispatch_operational_alert_notifications(db)

        assert result == {"sent": 0, "retry_scheduled": 1, "exhausted": 0}
        assert notification.status == "pending"
        assert notification.attempts == 1
        assert notification.last_error_code == "smtp_delivery_failed"
