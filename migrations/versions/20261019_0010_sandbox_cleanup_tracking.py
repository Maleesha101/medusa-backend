"""Track sandbox provider cleanup retries.

Revision ID: 20261019_0010
Revises: 20261018_0009
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0010"
down_revision: str | None = "20261018_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sandbox_instances",
        sa.Column(
            "cleanup_status",
            sa.String(length=16),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column(
        "sandbox_instances",
        sa.Column("cleanup_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sandbox_instances",
        sa.Column("cleanup_error_code", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_sandbox_instances_cleanup_status",
        "sandbox_instances",
        "cleanup_status IN ('not_required', 'pending', 'cleaned', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_sandbox_instances_cleanup_status",
        "sandbox_instances",
        type_="check",
    )
    op.drop_column("sandbox_instances", "cleanup_error_code")
    op.drop_column("sandbox_instances", "cleanup_attempts")
    op.drop_column("sandbox_instances", "cleanup_status")
