"""Add optional competition team capacity.

Revision ID: 20261027_0014
Revises: 20261026_0013
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0014"
down_revision: str | None = "20261026_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("competitions", sa.Column("max_teams", sa.Integer(), nullable=True))
    with op.batch_alter_table("competitions") as batch_op:
        batch_op.create_check_constraint(
            "ck_competitions_max_teams_positive",
            "max_teams IS NULL OR max_teams > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("competitions") as batch_op:
        batch_op.drop_constraint(
            "ck_competitions_max_teams_positive",
            type_="check",
        )
        batch_op.drop_column("max_teams")
