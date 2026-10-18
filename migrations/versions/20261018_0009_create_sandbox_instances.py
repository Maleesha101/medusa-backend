"""Create persisted challenge sandbox lifecycle metadata.

Revision ID: 20261018_0009
Revises: 20261016_0008
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261018_0009"
down_revision: str | None = "20261016_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sandbox_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "challenge_id",
            sa.Integer(),
            sa.ForeignKey("challenges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("provider_instance_id", sa.String(length=255), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'stopped', 'failed', 'expired')",
            name="ck_sandbox_instances_state",
        ),
        sa.UniqueConstraint("provider_instance_id", name="uq_sandbox_instances_provider_instance_id"),
    )
    op.create_index("ix_sandbox_instances_challenge_id", "sandbox_instances", ["challenge_id"])
    op.create_index("ix_sandbox_instances_owner_user_id", "sandbox_instances", ["owner_user_id"])
    op.create_index("ix_sandbox_instances_state_expires_at", "sandbox_instances", ["state", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sandbox_instances_state_expires_at", table_name="sandbox_instances")
    op.drop_index("ix_sandbox_instances_owner_user_id", table_name="sandbox_instances")
    op.drop_index("ix_sandbox_instances_challenge_id", table_name="sandbox_instances")
    op.drop_table("sandbox_instances")
