"""Add competition team-size eligibility bounds.

Revision ID: 20261028_0015
Revises: 20261027_0014
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0015"
down_revision: str | None = "20261027_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("competitions", sa.Column("min_team_size", sa.Integer(), nullable=True))
    op.add_column("competitions", sa.Column("max_team_size", sa.Integer(), nullable=True))
    with op.batch_alter_table("competitions") as batch_op:
        batch_op.create_check_constraint(
            "ck_competitions_min_team_size_positive",
            "min_team_size IS NULL OR min_team_size > 0",
        )
        batch_op.create_check_constraint(
            "ck_competitions_max_team_size_positive",
            "max_team_size IS NULL OR max_team_size > 0",
        )
        batch_op.create_check_constraint(
            "ck_competitions_team_size_bounds",
            "min_team_size IS NULL OR max_team_size IS NULL OR min_team_size <= max_team_size",
        )


def downgrade() -> None:
    with op.batch_alter_table("competitions") as batch_op:
        batch_op.drop_constraint("ck_competitions_team_size_bounds", type_="check")
        batch_op.drop_constraint("ck_competitions_max_team_size_positive", type_="check")
        batch_op.drop_constraint("ck_competitions_min_team_size_positive", type_="check")
        batch_op.drop_column("max_team_size")
        batch_op.drop_column("min_team_size")
