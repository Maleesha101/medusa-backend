"""Team domain model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Team(Base):
    """A participant team belonging to one organization."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_teams_organization_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    captain_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
