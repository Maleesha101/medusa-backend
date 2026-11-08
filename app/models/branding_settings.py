"""Shared MEDUSA branding settings persisted for the web app and email service."""

from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrandingSettings(Base):
    """Singleton record containing the optional shared header icon."""

    __tablename__ = "branding_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    header_icon: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    header_icon_mime_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
