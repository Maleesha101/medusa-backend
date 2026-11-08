"""Shared MEDUSA branding settings."""

import base64

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models.branding_settings import BrandingSettings
from app.models.user import User
from app.schemas.branding import HeaderIconPublic, HeaderIconUpdate

router = APIRouter(prefix="/branding", tags=["branding"])


@router.get("/header-icon", response_model=HeaderIconPublic)
def read_header_icon(db: Session = Depends(get_db)) -> HeaderIconPublic:
    """Return the shared header icon for participant/admin headers and email previews."""
    settings = db.get(BrandingSettings, 1)
    if settings is None or settings.header_icon is None or settings.header_icon_mime_type is None:
        return HeaderIconPublic(image_data_url=None)
    encoded = base64.b64encode(settings.header_icon).decode("ascii")
    return HeaderIconPublic(
        image_data_url=f"data:{settings.header_icon_mime_type};base64,{encoded}"
    )


@router.put("/header-icon", response_model=HeaderIconPublic)
def update_header_icon(
    payload: HeaderIconUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> HeaderIconPublic:
    """Replace or clear the shared icon; only platform administrators may update it."""
    settings = db.get(BrandingSettings, 1)
    if settings is None:
        settings = BrandingSettings(id=1)
        db.add(settings)

    if payload.image_data_url is None:
        settings.header_icon = None
        settings.header_icon_mime_type = None
    else:
        header, encoded = payload.image_data_url.split(",", 1)
        settings.header_icon = base64.b64decode(encoded, validate=True)
        settings.header_icon_mime_type = header[5:].split(";", 1)[0]

    db.commit()
    return read_header_icon(db)
