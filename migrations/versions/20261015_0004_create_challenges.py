"""Create challenges table.

Revision ID: 20261015_0004
Revises: 20261014_0003
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0004"
down_revision: str | None = "20261014_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("difficulty", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("points > 0", name="ck_challenges_points_positive"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_challenges_status",
        ),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard', 'expert')",
            name="ck_challenges_difficulty",
        ),
        sa.ForeignKeyConstraint(["round_id"], ["competition_rounds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "slug", name="uq_challenges_round_slug"),
    )
    op.create_index("ix_challenges_round_id", "challenges", ["round_id"])


def downgrade() -> None:
    op.drop_index("ix_challenges_round_id", table_name="challenges")
    op.drop_table("challenges")
