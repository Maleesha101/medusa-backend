"""Persist operational alert state and per-recipient notification intents.

Revision ID: 20261031_0016
Revises: 20261028_0015
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0016"
down_revision: str | None = "20261028_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_key", sa.String(length=120), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("alert_key", name="uq_operational_alerts_alert_key"),
    )
    op.create_index(
        "ix_operational_alerts_active_updated",
        "operational_alerts",
        ["is_active", "last_observed_at"],
    )
    op.create_table(
        "operational_alert_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["operational_alerts.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "alert_id",
            "event_key",
            "recipient_email",
            name="uq_operational_alert_notification_event_recipient",
        ),
    )
    op.create_index(
        "ix_operational_alert_notifications_due",
        "operational_alert_notifications",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_alert_notifications_due",
        table_name="operational_alert_notifications",
    )
    op.drop_table("operational_alert_notifications")
    op.drop_index("ix_operational_alerts_active_updated", table_name="operational_alerts")
    op.drop_table("operational_alerts")
