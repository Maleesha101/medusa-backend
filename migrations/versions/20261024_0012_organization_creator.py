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
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_organizations_created_by_user_id_users",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_organizations_created_by_user_id",
            ["created_by_user_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_index("ix_organizations_created_by_user_id")
        batch_op.drop_constraint(
            "fk_organizations_created_by_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("created_by_user_id")
