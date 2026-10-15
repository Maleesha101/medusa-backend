"""Competition round domain model."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompetitionRound(Base):
    """An ordered round within a competition."""

    __tablename__ = "competition_rounds"
    __table_args__ = (
        UniqueConstraint("competition_id", "position", name="uq_rounds_competition_position"),
        UniqueConstraint("competition_id", "slug", name="uq_rounds_competition_slug"),
        CheckConstraint("position >= 1", name="ck_competition_rounds_position_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
