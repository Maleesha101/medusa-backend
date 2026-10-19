"""Persisted metadata for isolated challenge runtime instances."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SandboxInstance(Base):
    """A lifecycle record; it does not itself create or control a runtime."""

    __tablename__ = "sandbox_instances"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'running', 'stopped', 'failed', 'expired')",
            name="ck_sandbox_instances_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Provider-assigned opaque identifier only; never accept it from participant requests.
    provider_instance_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    cleanup_status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_required")
    cleanup_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    cleanup_error_code: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
