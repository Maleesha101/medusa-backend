"""Create persistent SOC event, alert, investigation, rule, and analyst data.

Revision ID: 20261116_0019
Revises: 20261108_0018
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.db.base import Base
from app.models import security_operations  # noqa: F401

revision: str = "20261116_0019"
down_revision: str | None = "20261108_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "soc_events",
    "soc_cases",
    "soc_alerts",
    "soc_rules",
    "soc_rule_changes",
    "soc_watchlist",
    "soc_settings",
    "soc_response_actions",
    "soc_saved_views",
    "soc_reports",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in _TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    op.add_column(
        "users",
        sa.Column("force_password_reset", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    op.drop_column("users", "force_password_reset")
