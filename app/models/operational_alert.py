"""Durable operational alert state and email outbox records."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationalAlert(Base):
    """Current state for one stable metric alert identity."""

    __tablename__ = "operational_alerts"
    __table_args__ = (
        UniqueConstraint("alert_key", name="uq_operational_alerts_alert_key"),
        Index("ix_operational_alerts_active_updated", "is_active", "last_observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(120), nullable=False)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalAlertNotification(Base):
    """Per-recipient durable email intent with bounded retry metadata."""

    __tablename__ = "operational_alert_notifications"
    __table_args__ = (
        UniqueConstraint(
            "alert_id",
            "event_key",
            "recipient_email",
            name="uq_operational_alert_notification_event_recipient",
        ),
        Index("ix_operational_alert_notifications_due", "status", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("operational_alerts.id", ondelete="CASCADE"), nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
