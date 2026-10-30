"""Minimal SMTP delivery for password-reset messages."""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings


def send_password_reset_email(email: str, reset_link: str) -> bool:
    """Send a reset link without logging the address or token.

    Returns False when SMTP is not configured (useful for local development).
    Production configuration validation requires SMTP_HOST and SMTP_FROM_EMAIL.
    """
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        return False

    message = EmailMessage()
    message["Subject"] = "Reset your MEDUSA password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "A password reset was requested for your MEDUSA account. "
        "Use the link below within the configured validity period. "
        "If you did not request this, you can ignore this email.\n\n"
        f"{reset_link}\n"
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_use_tls:
            client.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)
    return True


def send_operational_alert_email(
    email: str,
    *,
    event_type: str,
    metric: str,
    severity: str,
    value: float,
    threshold: float,
    unit: str,
    alert_key: str,
) -> bool:
    """Send a concise operational alert without exposing infrastructure internals."""
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        return False

    labels = {
        "triggered": "Operational alert triggered",
        "escalated": "Operational alert escalated",
        "resolved": "Operational alert resolved",
    }
    subject = labels.get(event_type, "MEDUSA operational alert")
    message = EmailMessage()
    message["Subject"] = f"MEDUSA: {subject}"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        f"Alert: {alert_key}\n"
        f"Event: {event_type}\n"
        f"Metric: {metric}\n"
        f"Severity: {severity}\n"
        f"Observed value: {value} {unit}\n"
        f"Threshold: {threshold} {unit}\n"
        "Review the administrator operations metrics in MEDUSA.\n"
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_use_tls:
            client.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)
    return True
