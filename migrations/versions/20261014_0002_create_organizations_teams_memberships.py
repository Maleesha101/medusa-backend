"""Create organizations, teams, and team memberships.

Revision ID: 20261014_0002
Revises: 20261013_0001
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0002"
down_revision: str | None = "20261013_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=False)

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("captain_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["captain_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_teams_organization_name"),
    )
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"], unique=False)
    op.create_index("ix_teams_captain_user_id", "teams", ["captain_user_id"], unique=False)

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("role IN ('captain', 'member')", name="ck_team_memberships_role"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"], unique=False)
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_team_memberships_user_id", table_name="team_memberships")
    op.drop_index("ix_team_memberships_team_id", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_index("ix_teams_captain_user_id", table_name="teams")
    op.drop_index("ix_teams_organization_id", table_name="teams")
    op.drop_table("teams")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
