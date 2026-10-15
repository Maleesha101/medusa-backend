"""Snapshot points awarded when a team solves a challenge.

Revision ID: 20261015_0006
Revises: 20261015_0005
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0006"
down_revision: str | None = "20261015_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "challenge_submissions",
        sa.Column(
            "points_awarded",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # Preserve scores for any correct solves recorded before this migration.
    op.execute(
        """
        UPDATE challenge_submissions
        SET points_awarded = (
            SELECT challenges.points
            FROM challenges
            WHERE challenges.id = challenge_submissions.challenge_id
        )
        WHERE is_correct IS TRUE
        """
    )


def downgrade() -> None:
    op.drop_column("challenge_submissions", "points_awarded")
