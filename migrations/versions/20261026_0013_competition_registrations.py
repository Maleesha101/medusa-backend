"""Add competition team registrations.

Revision ID: 20261026_0013
Revises: 20261024_0012
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0013"
down_revision: str | None = "20261024_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competition_registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("registered_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "competition_id",
            "team_id",
            name="uq_competition_registrations_competition_team",
        ),
    )
    op.create_index(
        "ix_competition_registrations_competition_id",
        "competition_registrations",
        ["competition_id"],
    )
    op.create_index(
        "ix_competition_registrations_team_id",
        "competition_registrations",
        ["team_id"],
    )
    op.create_index(
        "ix_competition_registrations_registered_by_user_id",
        "competition_registrations",
        ["registered_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_competition_registrations_registered_by_user_id",
        table_name="competition_registrations",
    )
    op.drop_index("ix_competition_registrations_team_id", table_name="competition_registrations")
    op.drop_index(
        "ix_competition_registrations_competition_id",
        table_name="competition_registrations",
    )
    op.drop_table("competition_registrations")
