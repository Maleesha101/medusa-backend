import smtplib
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core import email as email_service


def _settings(**overrides):
    values = {
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_username": None,
        "smtp_password": None,
        "smtp_from_email": None,
        "smtp_use_tls": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_password_reset_email_returns_false_when_smtp_is_not_configured(
    monkeypatch, caplog
):
    monkeypatch.setattr(email_service, "get_settings", lambda: _settings())

    delivered = email_service.send_password_reset_email(
        "private-user@example.com", "https://frontend.example/reset-password?token=secret-token"
    )

    assert delivered is False
    assert "SMTP is not configured" in caplog.text
    assert "private-user@example.com" not in caplog.text
    assert "secret-token" not in caplog.text


def test_password_reset_email_returns_false_on_smtp_failure_without_logging_details(
    monkeypatch, caplog
):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.side_effect = smtplib.SMTPAuthenticationError(
        535, b"auth failed for private-user@example.com"
    )
    monkeypatch.setattr(email_service, "get_settings", lambda: _settings(
        smtp_host="mail.internal.example",
        smtp_from_email="noreply@example.com",
        smtp_username="smtp-user",
        smtp_password="smtp-secret",
    ))
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: smtp)

    delivered = email_service.send_password_reset_email(
        "private-user@example.com", "https://frontend.example/reset-password?token=secret-token"
    )

    assert delivered is False
    assert "Password-reset email delivery failed." in caplog.text
    assert "private-user@example.com" not in caplog.text
    assert "secret-token" not in caplog.text
    assert "smtp-secret" not in caplog.text
    assert "mail.internal.example" not in caplog.text


def test_password_reset_email_sends_when_smtp_is_configured(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(email_service, "get_settings", lambda: _settings(
        smtp_host="smtp.example.com",
        smtp_from_email="noreply@example.com",
    ))
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: smtp)

    delivered = email_service.send_password_reset_email(
        "user@example.com", "https://frontend.example/reset-password?token=one-time-token"
    )

    assert delivered is True
    smtp.send_message.assert_called_once()
