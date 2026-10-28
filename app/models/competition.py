"""Competition domain model."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Competition(Base):
    """A CTF event hosted by an organization."""

    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'active', 'completed', 'archived')",
            name="ck_competitions_status",
        ),
        CheckConstraint(
            "max_teams IS NULL OR max_teams > 0",
            name="ck_competitions_max_teams_positive",
        ),
        CheckConstraint(
            "min_team_size IS NULL OR min_team_size > 0",
            name="ck_competitions_min_team_size_positive",
        ),
        CheckConstraint(
            "max_team_size IS NULL OR max_team_size > 0",
            name="ck_competitions_max_team_size_positive",
        ),
        CheckConstraint(
            "min_team_size IS NULL OR max_team_size IS NULL OR min_team_size <= max_team_size",
            name="ck_competitions_team_size_bounds",
        ),
        UniqueConstraint("slug", name="uq_competitions_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_teams: Mapped[int | None] = mapped_column(nullable=True)
    min_team_size: Mapped[int | None] = mapped_column(nullable=True)
    max_team_size: Mapped[int | None] = mapped_column(nullable=True)
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
