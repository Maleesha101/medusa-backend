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


def test_password_reset_email_returns_false_when_smtp_is_not_configured(monkeypatch, caplog):
    monkeypatch.setattr(email_service, "get_settings", lambda: _settings())

    delivered = email_service.send_password_reset_email(
        "person@example.test", "https://frontend.example/reset-password?token=dummy"
    )

    assert delivered is False
    assert "SMTP is not configured" in caplog.text
    assert "person@example.test" not in caplog.text
    assert "dummy" not in caplog.text


def test_password_reset_email_returns_false_on_smtp_failure_without_logging_details(
    monkeypatch, caplog
):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.side_effect = smtplib.SMTPAuthenticationError(
        535, b"authentication failed for person@example.test"
    )
    monkeypatch.setattr(
        email_service,
        "get_settings",
        lambda: _settings(
            smtp_host="mail.internal.example",
            smtp_from_email="noreply@example.test",
            smtp_username="test-user",
            smtp_password="test-password",
        ),
    )
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: smtp)

    delivered = email_service.send_password_reset_email(
        "person@example.test", "https://frontend.example/reset-password?token=dummy"
    )

    assert delivered is False
    assert "Password-reset email delivery failed." in caplog.text
    assert "person@example.test" not in caplog.text
    assert "dummy" not in caplog.text
    assert "test-password" not in caplog.text
    assert "mail.internal.example" not in caplog.text


def test_password_reset_email_sends_multipart_html_with_complete_reset_link(monkeypatch, caplog):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(
        email_service,
        "get_settings",
        lambda: _settings(
            smtp_host="smtp.example.com",
            smtp_from_email="noreply@example.test",
        ),
    )
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: smtp)

    reset_link = "http://localhost:8080/reset-password?token=secret-token"
    delivered = email_service.send_password_reset_email("person@example.test", reset_link)

    assert delivered is True
    message = smtp.send_message.call_args.args[0]
    assert message.is_multipart()
    plain_part = message.get_body(preferencelist=("plain",)).get_content()
    html_part = message.get_body(preferencelist=("html",)).get_content()
    assert reset_link in plain_part
    assert "\\n" not in plain_part
    assert 'href="http://localhost:8080/reset-password?token=secret-token"' in html_part
    assert "Reset password" in html_part
    assert "secret-token" not in caplog.text


def test_password_reset_email_sends_when_smtp_is_configured(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(
        email_service,
        "get_settings",
        lambda: _settings(
            smtp_host="smtp.example.com",
            smtp_from_email="noreply@example.test",
        ),
    )
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: smtp)

    delivered = email_service.send_password_reset_email(
        "person@example.test", "https://frontend.example/reset-password?token=dummy"
    )

    assert delivered is True
    smtp.send_message.assert_called_once()


def test_password_reset_email_embeds_shared_logo_and_uses_medusa_theme(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(
        email_service,
        "get_settings",
        lambda: _settings(
            smtp_host="smtp.example.com",
            smtp_from_email="noreply@example.test",
        ),
    )
    monkeypatch.setattr(email_service, "_load_header_icon", lambda: (b"fake-png", "image/png"))
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: smtp)

    delivered = email_service.send_password_reset_email(
        "person@example.test", "https://frontend.example/reset-password?token=dummy"
    )

    assert delivered is True
    message = smtp.send_message.call_args.args[0]
    mime_parts = list(message.walk())
    html_part = next(part for part in mime_parts if part.get_content_type() == "text/html")
    logo_part = next(
        part for part in mime_parts if part.get("Content-ID") == "<medusa-header-icon>"
    )

    assert logo_part.get_content_type() == "image/png"
    assert logo_part.get_content_disposition() == "inline"
    assert logo_part.get_payload(decode=True) == b"fake-png"
    html_body = html_part.get_content()
    assert "cid:medusa-header-icon" in html_body
    assert "#3ecf5c" in html_body
