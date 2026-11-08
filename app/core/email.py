"""Email delivery for password-reset and operational messages."""

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _load_header_icon() -> tuple[bytes, str] | None:
    """Read the shared logo without allowing branding-store errors to block recovery email."""
    from app.db.session import SessionLocal
    from app.models.branding_settings import BrandingSettings

    try:
        with SessionLocal() as db:
            settings = db.get(BrandingSettings, 1)
            if settings and settings.header_icon and settings.header_icon_mime_type:
                return settings.header_icon, settings.header_icon_mime_type
    except SQLAlchemyError:
        logger.warning("Shared email branding could not be loaded.")
    return None


def send_password_reset_email(email: str, reset_link: str) -> bool:
    """Send a branded multipart password-reset email without logging address or token."""
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        logger.warning("Password-reset email delivery is unavailable: SMTP is not configured.")
        return False

    safe_reset_link = html.escape(reset_link, quote=True)
    logo = _load_header_icon()
    logo_markup = (
        '<img src="cid:medusa-header-icon" alt="MEDUSA" '
        'style="display:block;max-width:56px;max-height:56px;object-fit:contain;">'
        if logo
        else '<span style="font-size:22px;font-weight:800;letter-spacing:2px;color:#ffffff;">MEDUSA</span>'
    )

    message = EmailMessage()
    message["Subject"] = "Reset your MEDUSA password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "A password reset was requested for your MEDUSA account.\n\n"
        "Use the link below within the configured validity period:\n"
        f"{reset_link}\n\n"
        "If you did not request this, you can ignore this email.\n"
    )
    message.add_alternative(
        f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Reset your MEDUSA password</title>
  </head>
  <body style="margin:0;padding:32px 12px;background-color:#f3f5f6;font-family:Arial,Helvetica,sans-serif;color:#172033;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;">
      <tr>
        <td style="padding:28px 36px;background:#102b19;color:#ffffff;">
          {logo_markup}
          <div style="margin-top:12px;font-size:13px;letter-spacing:2px;font-weight:700;color:#b8f3c3;">ACCOUNT SECURITY</div>
        </td>
      </tr>
      <tr>
        <td style="padding:36px;">
          <h1 style="margin:0 0 16px;font-size:24px;line-height:1.3;color:#172033;">Reset your password</h1>
          <p style="margin:0 0 18px;font-size:15px;line-height:1.7;color:#526078;">We received a request to reset the password for your MEDUSA account. Use the secure button below to choose a new password.</p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0;">
            <tr>
              <td align="center" bgcolor="#3ecf5c" style="border-radius:8px;">
                <a href="{safe_reset_link}" style="display:inline-block;padding:14px 24px;color:#102b19;text-decoration:none;font-size:15px;font-weight:700;">Reset password</a>
              </td>
            </tr>
          </table>
          <p style="margin:0 0 12px;font-size:13px;line-height:1.6;color:#68758b;">This link is valid for a limited time. If the button does not work, copy and paste this address into your browser:</p>
          <p style="margin:0 0 24px;word-break:break-all;font-size:12px;line-height:1.6;"><a href="{safe_reset_link}" style="color:#218c39;">{safe_reset_link}</a></p>
          <div style="height:1px;background:#e8ecf3;"></div>
          <p style="margin:20px 0 0;font-size:13px;line-height:1.6;color:#68758b;">If you did not request a password reset, you can safely ignore this email. Your password will not change.</p>
        </td>
      </tr>
      <tr>
        <td style="padding:18px 36px;background:#f8faf8;font-size:11px;line-height:1.5;color:#8791a3;">This is an automated security message from MEDUSA. Please do not reply to this email.</td>
      </tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )
    if logo:
        image_data, mime_type = logo
        maintype, subtype = mime_type.split("/", 1)
        html_part = message.get_payload()[-1]
        html_part.add_related(
            image_data,
            maintype=maintype,
            subtype=subtype,
            cid="<medusa-header-icon>",
            disposition="inline",
            filename=f"medusa-logo.{subtype}",
        )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_tls:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
    except (OSError, smtplib.SMTPException):
        # Never log exception details: SMTP errors may contain addresses or host data.
        logger.error("Password-reset email delivery failed.")
        return False
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
