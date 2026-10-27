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
    op.create_check_constraint(
        "ck_competitions_max_teams_positive",
        "competitions",
        "max_teams IS NULL OR max_teams > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_competitions_max_teams_positive",
        "competitions",
        type_="check",
    )
    op.drop_column("competitions", "max_teams")
