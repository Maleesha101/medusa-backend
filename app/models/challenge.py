"""Challenge authoring and catalog domain model."""

from datetime import datetime

from sqlalchemy import (
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


class Challenge(Base):
    """A challenge belonging to a competition round."""

    __tablename__ = "challenges"
    __table_args__ = (
        UniqueConstraint("round_id", "slug", name="uq_challenges_round_slug"),
        CheckConstraint("points > 0", name="ck_challenges_points_positive"),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_challenges_status",
        ),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard', 'expert')",
            name="ck_challenges_difficulty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(
        ForeignKey("competition_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    points: Mapped[int] = mapped_column(nullable=False, default=100)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
