"""Track organization creators for tenant-scoped authorization.

Revision ID: 20261024_0012
Revises: 20261019_0011
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0012"
down_revision: str | None = "20261019_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_created_by_user_id_users",
        "organizations",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_organizations_created_by_user_id",
        "organizations",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_created_by_user_id", table_name="organizations")
    op.drop_constraint(
        "fk_organizations_created_by_user_id_users",
        "organizations",
        type_="foreignkey",
    )
    op.drop_column("organizations", "created_by_user_id")
