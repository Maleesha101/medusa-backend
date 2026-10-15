"""Create challenge flag and submission tables.

Revision ID: 20261015_0005
Revises: 20261015_0004
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0005"
down_revision: str | None = "20261015_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "challenge_flags",
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("flag_hash", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("challenge_id"),
    )

    op.create_table(
        "challenge_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_challenge_submissions_challenge_id",
        "challenge_submissions",
        ["challenge_id"],
    )
    op.create_index(
        "ix_challenge_submissions_team_id",
        "challenge_submissions",
        ["team_id"],
    )
    op.create_index(
        "ix_challenge_submissions_user_id",
        "challenge_submissions",
        ["user_id"],
    )
    op.create_index(
        "ix_challenge_submissions_challenge_team",
        "challenge_submissions",
        ["challenge_id", "team_id"],
    )
    op.create_index(
        "ix_challenge_submissions_team_submitted_at",
        "challenge_submissions",
        ["team_id", "submitted_at"],
    )
    op.create_index(
        "uq_challenge_submissions_one_correct_solve",
        "challenge_submissions",
        ["challenge_id", "team_id"],
        unique=True,
        postgresql_where=sa.text("is_correct IS TRUE"),
        sqlite_where=sa.text("is_correct = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_challenge_submissions_one_correct_solve",
        table_name="challenge_submissions",
    )
    op.drop_index(
        "ix_challenge_submissions_team_submitted_at",
        table_name="challenge_submissions",
    )
    op.drop_index(
        "ix_challenge_submissions_challenge_team",
        table_name="challenge_submissions",
    )
    op.drop_index("ix_challenge_submissions_user_id", table_name="challenge_submissions")
    op.drop_index("ix_challenge_submissions_team_id", table_name="challenge_submissions")
    op.drop_index(
        "ix_challenge_submissions_challenge_id",
        table_name="challenge_submissions",
    )
    op.drop_table("challenge_submissions")
    op.drop_table("challenge_flags")
