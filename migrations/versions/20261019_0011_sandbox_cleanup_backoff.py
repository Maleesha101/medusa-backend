"""Add provider cleanup retry scheduling.

Revision ID: 20261019_0011
Revises: 20261019_0010
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0011"
down_revision: str | None = "20261019_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sandbox_instances",
        sa.Column("cleanup_next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sandbox_instances", "cleanup_next_attempt_at")
