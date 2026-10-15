"""Persist challenge attempts without storing submitted flag values."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChallengeSubmission(Base):
    """One attempt to solve a challenge by a team member."""

    __tablename__ = "challenge_submissions"
    __table_args__ = (
        Index("ix_challenge_submissions_challenge_team", "challenge_id", "team_id"),
        Index("ix_challenge_submissions_team_submitted_at", "team_id", "submitted_at"),
        Index(
            "uq_challenge_submissions_one_correct_solve",
            "challenge_id",
            "team_id",
            unique=True,
            postgresql_where=text("is_correct IS TRUE"),
            sqlite_where=text("is_correct = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
