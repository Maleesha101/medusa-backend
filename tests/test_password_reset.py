from datetime import UTC, datetime, timedelta
import hashlib

from sqlalchemy import select

from app.api import auth as auth_api
from app.models.password_reset_token import PasswordResetToken


def _register_and_login(client, email="recover@example.com", password="a-very-long-test-password"):
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _capture_reset_emails(monkeypatch):
    delivered = []
    monkeypatch.setattr(
        auth_api,
        "send_password_reset_email",
        lambda email, link: delivered.append((email, link)),
    )
    return delivered


def _request_reset(client, email="recover@example.com"):
    return client.post("/api/v1/auth/password-reset/request", json={"email": email})


def _extract_token(delivered, index=0):
    return delivered[index][1].split("token=", 1)[1]


def _confirm_reset(client, token, new_password="a-different-long-password"):
    return client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": new_password},
    )


def test_reset_request_has_same_response_for_existing_and_missing_accounts(client, monkeypatch):
    delivered = _capture_reset_emails(monkeypatch)
    _register_and_login(client)

    existing = _request_reset(client)
    missing = _request_reset(client, "absent@example.com")

    assert existing.status_code == missing.status_code == 202
    assert existing.json() == missing.json()
    assert len(delivered) == 1
    assert "token=" in delivered[0][1]


def test_password_reset_changes_password_and_invalidates_existing_access_tokens(
    client, monkeypatch
):
    delivered = _capture_reset_emails(monkeypatch)
    old_token = _register_and_login(client)
    assert _request_reset(client).status_code == 202

    reset = _confirm_reset(client, _extract_token(delivered))
    assert reset.status_code == 204
    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401

    new_login = client.post(
        "/api/v1/auth/token",
        data={
            "username": "recover@example.com",
            "password": "a-different-long-password",
        },
    )
    assert new_login.status_code == 200
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
    ).status_code == 200


def test_reset_token_is_single_use(client, monkeypatch):
    delivered = _capture_reset_emails(monkeypatch)
    _register_and_login(client)
    _request_reset(client)

    token = _extract_token(delivered)
    assert _confirm_reset(client, token).status_code == 204
    assert _confirm_reset(client, token, "another-long-password-123").status_code == 400


def test_invalid_and_expired_reset_tokens_are_rejected(client, session_factory, monkeypatch):
    delivered = _capture_reset_emails(monkeypatch)
    _register_and_login(client)
    _request_reset(client)
    raw_token = _extract_token(delivered)

    assert _confirm_reset(client, "x" * 40).status_code == 400

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with session_factory() as db:
        record = db.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    assert _confirm_reset(client, raw_token).status_code == 400


def test_new_reset_request_invalidates_previous_token(client, monkeypatch):
    delivered = _capture_reset_emails(monkeypatch)
    _register_and_login(client)
    assert _request_reset(client).status_code == 202
    assert _request_reset(client).status_code == 202

    assert _confirm_reset(client, _extract_token(delivered, 0)).status_code == 400
    assert _confirm_reset(client, _extract_token(delivered, 1)).status_code == 204


def test_password_reset_rate_limits_requests_per_ip(client):
    for index in range(10):
        response = _request_reset(client, f"rate-{index}@example.com")
        assert response.status_code == 202

    blocked = _request_reset(client, "rate-blocked@example.com")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]


def test_password_reset_requires_valid_payloads(client):
    short_password = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "x" * 40, "new_password": "short"},
    )
    invalid_email = _request_reset(client, "not-an-email")
    assert short_password.status_code == 422
    assert invalid_email.status_code == 422
