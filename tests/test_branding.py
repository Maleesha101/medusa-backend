from base64 import b64encode

from sqlalchemy import select

from app.models.branding_settings import BrandingSettings
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


def test_header_icon_is_publicly_readable_and_admin_writable(client, session_factory):
    admin_token = _register_and_login(client, "branding-admin@example.com")
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "branding-admin@example.com"))
        assert admin is not None
        admin.role = "admin"
        db.commit()

    image = b"\x89PNG\r\n\x1a\n" + b"test-image"
    data_url = f"data:image/png;base64,{b64encode(image).decode('ascii')}"
    saved = client.put(
        "/api/v1/branding/header-icon",
        json={"image_data_url": data_url},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert saved.status_code == 200
    assert saved.json()["image_data_url"] == data_url

    public = client.get("/api/v1/branding/header-icon")
    assert public.status_code == 200
    assert public.json()["image_data_url"] == data_url

    with session_factory() as db:
        stored = db.get(BrandingSettings, 1)
        assert stored is not None
        assert stored.header_icon == image
        assert stored.header_icon_mime_type == "image/png"

    cleared = client.put(
        "/api/v1/branding/header-icon",
        json={"image_data_url": None},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["image_data_url"] is None


def test_header_icon_cannot_be_changed_by_participant(client):
    token = _register_and_login(client, "branding-participant@example.com")
    response = client.put(
        "/api/v1/branding/header-icon",
        json={"image_data_url": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_header_icon_rejects_invalid_image_data(client, session_factory):
    token = _register_and_login(client, "branding-invalid@example.com")
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "branding-invalid@example.com"))
        assert user is not None
        user.role = "admin"
        db.commit()

    response = client.put(
        "/api/v1/branding/header-icon",
        json={"image_data_url": "data:image/png;base64,not-an-image"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
