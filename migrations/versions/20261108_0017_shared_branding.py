"""Persist shared MEDUSA header branding.

Revision ID: 20261108_0017
Revises: 20261031_0016
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261108_0017"
down_revision: str | None = "20261031_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "branding_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("header_icon", sa.LargeBinary(), nullable=True),
        sa.Column("header_icon_mime_type", sa.String(length=32), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("branding_settings")
