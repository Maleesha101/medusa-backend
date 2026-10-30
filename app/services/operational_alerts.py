"""Durable operational alert transitions and retryable email delivery."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.email import send_operational_alert_email
from app.models.operational_alert import OperationalAlert, OperationalAlertNotification
from app.models.user import User
from app.services.operational_metrics import collect_operational_metrics

MAX_NOTIFICATION_ATTEMPTS = 8
MAX_NOTIFICATION_BATCH = 100


def _queue_notifications(
    db: Session, alert: OperationalAlert, event_type: str, event_key: str
) -> None:
    recipients = db.scalars(
        select(User.email).where(User.role == "admin", User.is_active.is_(True))
    ).all()
    for email in recipients:
        db.add(
            OperationalAlertNotification(
                alert_id=alert.id,
                event_key=event_key,
                event_type=event_type,
                metric=notification.metric,
                severity=notification.severity,
                value=notification.value,
                threshold=notification.threshold,
                unit=notification.unit,
                recipient_email=email,
            )
        )


def synchronize_operational_alerts(db: Session, settings) -> dict[str, int]:
    """Persist current alert conditions and enqueue only new/escalated/resolved transitions."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73194261)"))
    payload = collect_operational_metrics(db, settings)
    observed_at = datetime.fromisoformat(payload["observed_at"])
    active = {item["id"]: item for item in payload["alerts"]}
    existing = {
        item.alert_key: item
        for item in db.scalars(select(OperationalAlert).with_for_update()).all()
    }
    created = escalated = resolved = 0

    for key, item in active.items():
        alert = existing.get(key)
        if alert is None:
            alert = OperationalAlert(
                alert_key=key,
                metric=item["metric"],
                severity=item["severity"],
                value=item["value"],
                threshold=item["threshold"],
                unit=item["unit"],
                is_active=True,
                first_observed_at=observed_at,
                last_observed_at=observed_at,
            )
            db.add(alert)
            db.flush()
            _queue_notifications(db, alert, "triggered", f"triggered:{uuid4().hex}")
            created += 1
            continue

        was_active = alert.is_active
        previous_severity = alert.severity
        alert.metric = item["metric"]
        alert.value = item["value"]
        alert.threshold = item["threshold"]
        alert.unit = item["unit"]
        alert.last_observed_at = observed_at
        alert.is_active = True
        alert.resolved_at = None
        if not was_active:
            alert.severity = item["severity"]
            alert.first_observed_at = observed_at
            db.flush()
            _queue_notifications(db, alert, "triggered", f"triggered:{uuid4().hex}")
            created += 1
        elif item["severity"] == "critical" and previous_severity != "critical":
            alert.severity = item["severity"]
            db.flush()
            _queue_notifications(db, alert, "escalated", f"escalated:{uuid4().hex}")
            escalated += 1
        else:
            alert.severity = item["severity"]

    for key, alert in existing.items():
        if alert.is_active and key not in active:
            alert.is_active = False
            alert.resolved_at = observed_at
            alert.last_observed_at = observed_at
            db.flush()
            _queue_notifications(db, alert, "resolved", f"resolved:{uuid4().hex}")
            resolved += 1

    db.commit()
    return {"created": created, "escalated": escalated, "resolved": resolved}


def dispatch_operational_alert_notifications(
    db: Session, batch_size: int = MAX_NOTIFICATION_BATCH
) -> dict[str, int]:
    """Send a bounded batch, persisting retry state without exposing SMTP error details."""
    if not 1 <= batch_size <= MAX_NOTIFICATION_BATCH:
        raise ValueError(f"batch_size must be between 1 and {MAX_NOTIFICATION_BATCH}")
    now = datetime.now(UTC)
    query = (
        select(OperationalAlertNotification)
        .where(
            OperationalAlertNotification.status == "pending",
            OperationalAlertNotification.next_attempt_at <= now,
        )
        .order_by(OperationalAlertNotification.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    notifications = db.scalars(query).all()
    sent = failed = exhausted = 0

    for notification in notifications:
        alert = db.get(OperationalAlert, notification.alert_id)
        if alert is None:
            notification.status = "failed"
            notification.last_error_code = "alert_missing"
            exhausted += 1
            continue
        try:
            delivered = send_operational_alert_email(
                notification.recipient_email,
                event_type=notification.event_type,
                metric=alert.metric,
                severity=alert.severity,
                value=alert.value,
                threshold=alert.threshold,
                unit=alert.unit,
                alert_key=alert.alert_key,
            )
            if not delivered:
                notification.last_error_code = "smtp_not_configured"
                notification.attempts = MAX_NOTIFICATION_ATTEMPTS
            else:
                notification.status = "sent"
                notification.sent_at = now
                notification.attempts += 1
                notification.last_error_code = None
                sent += 1
                continue
        except Exception:
            notification.last_error_code = "smtp_delivery_failed"
            notification.attempts += 1

        if notification.attempts >= MAX_NOTIFICATION_ATTEMPTS:
            notification.status = "failed"
            exhausted += 1
        else:
            delay = min(3600, 30 * (2 ** (notification.attempts - 1)))
            notification.next_attempt_at = now + timedelta(seconds=delay)
            failed += 1

    db.commit()
    return {"sent": sent, "retry_scheduled": failed, "exhausted": exhausted}
