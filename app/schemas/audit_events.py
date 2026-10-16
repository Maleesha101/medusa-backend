"""Response schemas for administrative audit event queries."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventPublic(BaseModel):
    """Safe audit event representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    actor_role: str | None
    action: str
    outcome: str
    resource_type: str
    resource_id: int | None
    details: dict[str, Any] | None
    created_at: datetime
